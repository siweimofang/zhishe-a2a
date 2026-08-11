"""
LLM 调用封装
主力:DeepSeek-V4-Pro(3/6 元/百万 tokens)
备份:MiniMax M3(4.20/16.80 元/百万 tokens,故障切)

V1.0 简化:用 httpx 直连 DeepSeek(OpenAI 兼容)

V1.0 报价数据注入(2026-06-13):
- 解析用户输入(package/tier/area)
- 调 quote.estimate() 查表拿精确数据
- 注入到 system prompt 后面,让 LLM 不瞎编
"""
import asyncio
import logging
import httpx

from app.config import settings
from app.services.quote import estimate, parse_user_intent, format_estimate_for_llm
from app.services.knowledge import search as kb_search, format_for_llm as kb_format_for_llm
from app.services.knowledge import search_src as kb_search_src, format_src_for_llm as kb_format_src_for_llm

log = logging.getLogger("llm")

DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_CHAT = f"{DEEPSEEK_BASE}/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-pro"


async def chat_with_skill(user_text: str, max_tokens: int = 350) -> str:
    """
    处理千问发来的用户消息,返回 Agent 回复文本

    V1.0 报价增强流程:
    1. 解析用户输入的 (package, tier, area)
    2. 如果三者都齐了 → 调 quote.estimate() 查表
    3. 把精确数据拼到 system prompt 后面
    4. 让 LLM 基于真实数据组织语言,而不是瞎编

    V1.7.10(2026-08-08):max_tokens 参数化——咨询问答默认 350(性能优先),
    文案创作类请求由调用方传入更大上限(如 2000),避免创作输出被截断。
    """
    # V1.7 接线(2026-08-04):全国+沈阳双层定位正式上线(此前 v17 写好未引用)
    # 说明:V1.7 已含 V1.7.3 合规强化(身份边界声明,依据 2026-07-15 新规)
    from app.prompts.xiaozhi_v17 import XIAOZHI_SYSTEM_PROMPT_V17

    # === V1.0 报价数据注入 ===
    quote_data_block = ""
    intent = parse_user_intent(user_text)
    if intent["package"] and intent["area"]:
        # 关键参数齐了,查表
        tier = intent["tier"] or "中端"  # 没指定就默认中端
        est = estimate(intent["package"], tier, intent["area"])
        if est:
            quote_data_block = "\n\n" + format_estimate_for_llm(est)
            log.info(
                "quote_estimate_injected",
                extra={
                    "extra_package": intent["package"],
                    "extra_tier": tier,
                    "extra_area": intent["area"],
                    "extra_total_median": est.get("total_median"),
                },
            )

    # === V1.0 RAG 知识库注入(2026-06-13)===
    kb_results = kb_search(user_text, top_k=2)
    kb_block = kb_format_for_llm(kb_results) if kb_results else ""
    if kb_block:
        log.info("kb_results_injected", extra={"extra_kb_count": len(kb_results)})

    # === 原文库注入(2026-08-11):《选择、价值与决策》全书原文块 ===
    src_results = kb_search_src(user_text, top_k=1)
    src_block = kb_format_src_for_llm(src_results) if src_results else ""
    if src_block:
        log.info("kb_src_injected", extra={"extra_src_count": len(src_results)})

    # 2026-08-06 提速:system 只放固定 V17(保证 DeepSeek prompt cache 命中),
    # 可变的报价注入/kb 注入移到 user 消息末尾——此前拼在 system 里导致前缀变化,
    # 缓存永不命中,每次都要完整预填充 3000+tokens(实测 14-16s 的固定成本);
    # 缓存命中时同链路仅需约 4s(实测 198 字回答 4.1s)
    system_content = XIAOZHI_SYSTEM_PROMPT_V17
    user_content = user_text
    if quote_data_block:
        user_content += quote_data_block
    if kb_block:
        user_content += "\n\n" + kb_block
    if src_block:
        user_content += "\n\n" + src_block

    messages = [
        {
            "role": "system",
            "content": system_content,
            # DeepSeek prompt cache:标记 system prompt 缓存
            # 多次请求中相同的 system prompt 命中 cache,降低首字延迟
            "cache_control": {"type": "ephemeral"},
        },
        {"role": "user", "content": user_content},
    ]

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.7,
        # 2026-08-06:1200→600→450→300→350。实测拆解:网络1.1s+预填充(缓存命中后~1s)+生成~30-40tokens/s。
        # 300tokens实测9-12s但复杂问题被截断(付款比例仅110字),350tokens+提示词压缩引导兼顾完整与速度
        "max_tokens": max_tokens,
    }

    # 压测发现 30s 太短,提高到 90s;失败重试 1 次
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(DEEPSEEK_CHAT, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
            break
        except Exception as e:
            last_err = e
            log.warning(f"DeepSeek call attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(1.0)  # 重试前等 1 秒
    else:
        raise last_err  # type: ignore[misc]

    choice = data.get("choices", [{}])[0]
    reply = choice.get("message", {}).get("content", "")
    if not reply:
        log.warning(f"Empty LLM reply: {data}")
        return "抱歉,我这边临时有点状况,稍等再聊~"

    # 末尾兜底加 AI 标识
    if not reply.rstrip().endswith("(以上内容由 AI 生成,仅供参考)"):
        reply = reply.rstrip() + "\n\n(以上内容由 AI 生成,仅供参考)"

    return reply


async def check_llm_ready() -> bool:
    """检查 LLM 是否就绪"""
    if not settings.DEEPSEEK_API_KEY:
        return False
    try:
        headers = {
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(DEEPSEEK_CHAT, headers=headers, json=payload)
            return resp.status_code == 200
    except Exception as e:
        log.warning(f"LLM check failed: {e}")
        return False
