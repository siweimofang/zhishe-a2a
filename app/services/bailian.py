"""
千问百炼 API 调用封装 (2026-08-17)

V2.0 (2026-08-20): 升级为 LLM 主力模型
- 通过 PRIMARY_MODEL=bailian 激活 (llm.py 调度)
- DeepSeek 降为兜底

V2.1 重试升级 (2026-08-26):
- 3 次重试 + 指数退避(2s→4s→8s)
- 错误分类: 负载高 → 重试; 鉴权/内容 → 立即放弃
- 响应体错误检测 + 熔断器联动

主力模型: qwen3.8-max (OpenAI 兼容接口)
Base URL: 从 .env BAILIAN_BASE_URL 读取 (业务空间专属域名)

用途:
- 主力 LLM 后端 (llm.py chat_with_skill 调度)
- DeepSeek 的备用 LLM 后端 (故障切换)
- 知识条目批量生成 (从文档/书籍提取结构化知识)
- 语义增强检索 (本地关键词搜索的补充)
"""
import asyncio
import logging
import httpx
import json
import re

from app.config import settings

log = logging.getLogger("bailian")

BAILIAN_CHAT_URL = f"{settings.BAILIAN_BASE_URL}/chat/completions"
BAILIAN_MODEL = settings.BAILIAN_MODEL


async def chat(
    messages: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """
    调用千问 API 获取回复文本。

    V2.1 (2026-08-26): 3 次重试 + 指数退避 + 错误分类 + 熔断器

    Args:
        messages: OpenAI 兼容的消息列表 [{role, content}, ...]
        max_tokens: 最大输出 token 数
        temperature: 采样温度(0=确定性, 1=创造性)

    Returns:
        回复文本,失败时返回空字符串并记录日志
    """
    if not settings.BAILIAN_API_KEY:
        log.warning("BAILIAN_API_KEY 未配置,跳过千问调用")
        return ""

    # 延迟导入避免循环依赖
    from app.services.llm import breaker, backoff_sleep, classify_error, LLMErrorType

    # 熔断检查
    if breaker.is_open("bailian"):
        log.warning("百炼 熔断中, 跳过调用")
        return ""

    headers = {
        "Authorization": f"Bearer {settings.BAILIAN_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": BAILIAN_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_err = None
    data = None
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(BAILIAN_CHAT_URL, headers=headers, json=payload)
                body_text = resp.text

                if resp.status_code == 200:
                    body = resp.json()
                    # 检查响应体中的错误
                    if "error" in body:
                        err_msg = body["error"].get("message", str(body["error"]))
                        err_type = classify_error(None, err_msg)
                        log.warning(f"百炼 响应体错误 (attempt {attempt + 1}): {err_msg}")
                        if err_type in (LLMErrorType.AUTH, LLMErrorType.CONTENT):
                            breaker.record_failure("bailian")
                            return ""
                        last_err = Exception(err_msg)
                        await backoff_sleep(attempt)
                        continue
                    data = body
                    break
                else:
                    err_type = classify_error(resp.status_code, body_text)
                    log.warning(
                        f"百炼 HTTP {resp.status_code} (attempt {attempt + 1}), "
                        f"错误类型={err_type}"
                    )
                    if err_type in (LLMErrorType.AUTH, LLMErrorType.CONTENT):
                        breaker.record_failure("bailian")
                        return ""
                    last_err = Exception(f"HTTP {resp.status_code}: {body_text[:200]}")
                    if attempt < max_attempts - 1:
                        await backoff_sleep(attempt)

        except httpx.TimeoutException as e:
            last_err = e
            log.warning(f"百炼 超时 (attempt {attempt + 1}/{max_attempts})")
            if attempt < max_attempts - 1:
                await backoff_sleep(attempt)
        except httpx.ConnectError as e:
            last_err = e
            log.warning(f"百炼 连接失败 (attempt {attempt + 1}/{max_attempts}): {e}")
            if attempt < max_attempts - 1:
                await backoff_sleep(attempt)
        except Exception as e:
            last_err = e
            err_type = classify_error(None, str(e))
            log.warning(f"百炼 attempt {attempt + 1} 失败: {e} (type={err_type})")
            if err_type in (LLMErrorType.AUTH, LLMErrorType.CONTENT):
                breaker.record_failure("bailian")
                return ""
            if attempt < max_attempts - 1:
                await backoff_sleep(attempt)

    if data is None:
        breaker.record_failure("bailian")
        log.error(f"百炼 调用最终失败: {last_err}")
        return ""

    breaker.record_success("bailian")
    choice = data.get("choices", [{}])[0]
    reply = choice.get("message", {}).get("content", "")

    usage = data.get("usage", {})
    log.info(
        "bailian_call_done",
        extra={
            "model": BAILIAN_MODEL,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    )

    return reply


async def chat_with_rag(
    user_query: str,
    kb_results: list[dict],
    max_tokens: int = 1024,
) -> str:
    """
    千问 RAG 增强问答:本地知识库结果 + 千问语义理解。

    流程:
    1. 本地关键词搜索获取 top_k 结果
    2. 将结果注入 prompt 作为上下文
    3. 千问基于上下文生成回答

    Args:
        user_query: 用户原始问题
        kb_results: knowledge.py search() 返回的结果列表
        max_tokens: 最大输出 token 数

    Returns:
        增强后的回答文本
    """
    from app.services.knowledge import format_for_llm as kb_format

    kb_block = kb_format(kb_results) if kb_results else ""

    system_prompt = (
        "你是知设装修顾问,基于以下知识库内容回答用户问题。"
        "如果知识库内容不足以回答,请明确告知用户并给出通用建议。"
        "回答要专业、简洁、实用,避免空泛。"
    )

    user_content = user_query
    if kb_block:
        user_content += f"\n\n以下知识库内容供参考:\n{kb_block}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    return await chat(messages, max_tokens=max_tokens)


async def generate_knowledge_entries(
    source_text: str,
    category: str,
    max_entries: int = 20,
) -> list[dict]:
    """
    从文档/书籍文本中批量生成知识库条目。

    用途:投喂新书籍时,将原文拆解为结构化知识条目(ku_id/question/answer/tags/category)。

    Args:
        source_text: 原始文本(章节/段落)
        category: 目标类目(如"施工工艺"/"住宅空间设计")
        max_entries: 最大生成条目数

    Returns:
        知识条目列表 [{"question": str, "answer": str, "tags": list[str]}]
    """
    if not settings.BAILIAN_API_KEY:
        log.warning("BAILIAN_API_KEY 未配置,无法生成知识条目")
        return []

    system_prompt = (
        "你是装修知识库条目生成器。将用户提供的文本拆解为结构化的问答条目。"
        "每个条目包含:\n"
        "- question: 用户可能问的具体问题(8字以上,具体场景,禁止宽泛词如'注意''安全''应该')\n"
        "- answer: 基于原文的精准回答(200-500字,含具体数据/步骤/标准)\n"
        "- tags: 3-5个标签(从原文提取,用于检索匹配)\n\n"
        "要求:\n"
        "1. question 必须是具体场景问题,禁止用'有什么''怎么做'等泛问\n"
        "2. answer 必须从原文提取,禁止编造\n"
        "3. tags 要覆盖核心关键词,便于检索命中\n"
        "4. 条目之间不重复,覆盖原文所有知识点\n"
        f"5. 目标类目: {category}\n"
        f"6. 最多生成 {max_entries} 条\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": source_text},
    ]

    reply = await chat(messages, max_tokens=4096, temperature=0.3)
    if not reply:
        return []

    try:
        entries = json.loads(reply)
        if isinstance(entries, list):
            return entries
    except (json.JSONDecodeError, ValueError):
        pass

    json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", reply, re.DOTALL)
    if json_match:
        try:
            entries = json.loads(json_match.group(1))
            if isinstance(entries, list):
                return entries
        except (json.JSONDecodeError, ValueError):
            pass

    entries = _parse_text_entries(reply, category)
    return entries


def _parse_text_entries(text: str, category: str) -> list[dict]:
    """从非 JSON 文本中解析问答条目。"""
    entries = []

    qa_pairs = re.findall(
        r"(?:Q[：:]\s*|问题[：:]\s*)(.+?)(?:\n|。)(?:A[：:]\s*|回答[：:]\s*)(.+?)(?=\n\s*(?:Q[：:]|问题[：:]|\d+[.．]|\Z))",
        text,
        re.DOTALL,
    )

    for q, a in qa_pairs:
        q = q.strip().rstrip("。").strip()
        a = a.strip().rstrip("。").strip()
        if len(q) >= 8 and len(a) >= 20:
            tags = _extract_tags(q + " " + a)
            entries.append({
                "question": q,
                "answer": a,
                "tags": tags,
                "category": category,
            })

    if not entries:
        blocks = re.split(r"\n\s*(?:\d+[.．]\s*|\*\s*)", text)
        for block in blocks:
            block = block.strip()
            if len(block) < 30:
                continue
            parts = re.split(r"(?:回答[：:]|答[：:]|答案[：:])", block, maxsplit=1)
            if len(parts) == 2:
                q, a = parts[0].strip().rstrip("。"), parts[1].strip().rstrip("。")
                if len(q) >= 8 and len(a) >= 20:
                    tags = _extract_tags(q + " " + a)
                    entries.append({
                        "question": q,
                        "answer": a,
                        "tags": tags,
                        "category": category,
                    })

    return entries[:20]


def _extract_tags(text: str) -> list[str]:
    """从文本中提取核心关键词作为标签(简化版)"""
    words = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
    seen = set()
    tags = []
    for w in words:
        if w not in seen and len(w) >= 2:
            seen.add(w)
            tags.append(w)
        if len(tags) >= 5:
            break
    return tags if tags else ["装修", "知识"]


async def check_bailian_ready() -> bool:
    """检查千问 API 是否可用"""
    if not settings.BAILIAN_API_KEY:
        return False
    try:
        reply = await chat(
            [{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        return bool(reply)
    except Exception:
        return False
