"""
LLM 调用封装
主力: 千问百炼 qwen3.8-max (阿里生态内, 数据合规)
备份: DeepSeek-V4-Pro (3/6 元/百万 tokens, 故障自动切换)

V2.0 百炼主力迁移 (2026-08-20):
- 通过 PRIMARY_MODEL 配置项控制主力/兜底角色
- 一行切换: .env 改 PRIMARY_MODEL=bailian|deepseek 即生效
- 两个内部调用函数: _call_bailian / _call_deepseek (主力/兜底共用)
- 知识库/报价/A2A 协议层完全不受影响

V1.0 报价数据注入 (2026-06-13):
- 解析用户输入 (package/tier/area)
- 调 quote.estimate() 查表拿精确数据
- 注入到 user 消息末尾, 让 LLM 不瞎编

V1.1 千问故障切换 (2026-08-18):
- DeepSeek 两次重试均失败 → 自动切千问百炼 API
- 剥离 cache_control 字段以兼容千问 OpenAI 接口
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


# ---------------------------------------------------------------------------
# 内部调用函数: 主力/兜底共用
# ---------------------------------------------------------------------------

async def _call_bailian(messages: list[dict], max_tokens: int) -> str | None:
    """
    调用百炼 API (通用, 主力/兜底共用)。
    返回回复文本, 失败返回 None。
    """
    from app.services import bailian
    reply = await bailian.chat(messages, max_tokens=max_tokens, temperature=0.7)
    return reply if reply else None


async def _call_deepseek(messages: list[dict], max_tokens: int, with_cache: bool = False, model: str = None) -> str | None:
    """
    调用 DeepSeek API (通用, 主力/兜底共用)。
    with_cache=True 时附加 cache_control (仅主力模式使用)。
    model: 指定模型 (deepseek-v4-pro 或 deepseek-v4-flash), 默认 V4-Pro。
    返回回复文本, 失败返回 None。
    """
    actual_model = model or DEEPSEEK_MODEL
    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    # 主力模式: 附加 cache_control 标记 system prompt
    if with_cache:
        call_messages = []
        for msg in messages:
            if msg["role"] == "system":
                call_messages.append({**msg, "cache_control": {"type": "ephemeral"}})
            else:
                call_messages.append(msg)
    else:
        # 兜底模式: 剥离 cache_control 以兼容
        call_messages = [{k: v for k, v in msg.items() if k != "cache_control"} for msg in messages]

    payload = {
        "model": actual_model,
        "messages": call_messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }

    last_err: Exception | None = None
    data = None
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
                await asyncio.sleep(1.0)

    if data is None:
        return None

    choice = data.get("choices", [{}])[0]
    reply = choice.get("message", {}).get("content", "")
    return reply if reply else None


async def chat_with_skill(user_text: str, max_tokens: int = 350) -> str:
    """
    处理千问发来的用户消息, 返回 Agent 回复文本。

    V2.0 (2026-08-20): 配置驱动的双模型调度
    - PRIMARY_MODEL=bailian → 百炼主力, DeepSeek 兜底
    - PRIMARY_MODEL=deepseek → DeepSeek 主力, 百炼兜底

    V1.0 报价数据注入:
    1. 解析用户输入的 (package, tier, area)
    2. 如果三者都齐了 → 调 quote.estimate() 查表
    3. 把精确数据拼到 user 消息末尾
    4. 让 LLM 基于真实数据组织语言, 而不是瞎编

    V1.7.10 (2026-08-08): max_tokens 参数化——咨询问答默认 350 (性能优先),
    文案创作类请求由调用方传入更大上限 (如 2000), 避免创作输出被截断。
    """
    from app.prompts.xiaozhi_v17 import XIAOZHI_SYSTEM_PROMPT_V17

    # === 报价数据注入 ===
    quote_data_block = ""
    intent = parse_user_intent(user_text)
    if intent["package"] and intent["area"]:
        tier = intent["tier"] or "中端"
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

    # === RAG 知识库注入 ===
    kb_results = kb_search(user_text, top_k=2)
    kb_block = kb_format_for_llm(kb_results) if kb_results else ""
    if kb_block:
        log.info("kb_results_injected", extra={"extra_kb_count": len(kb_results)})

    # === 原文库注入 ===
    src_results = kb_search_src(user_text, top_k=1)
    src_block = kb_format_src_for_llm(src_results) if src_results else ""
    if src_block:
        log.info("kb_src_injected", extra={"extra_src_count": len(src_results)})

    # === 消息拼装 ===
    # 2026-08-06 提速: system 只放固定 V17 (保证 DeepSeek prompt cache 命中),
    # 可变的报价注入/kb 注入移到 user 消息末尾。
    # 百炼主力时无 cache_control 概念, 但结构保持一致便于切换。
    system_content = XIAOZHI_SYSTEM_PROMPT_V17
    user_content = user_text
    if quote_data_block:
        user_content += quote_data_block
    if kb_block:
        user_content += "\n\n" + kb_block
    if src_block:
        user_content += "\n\n" + src_block

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    # === V2.1 成本路由 (2026-08-20) ===
    # 根据任务复杂度 + 峰谷时段 + 缓存状态, 自动选性价比最高的模型
    from app.services.cost_router import select_model, tracker

    has_quote = bool(quote_data_block)
    routing = select_model(user_text, max_tokens, has_quote)
    chosen_model = routing["model"]
    chosen_provider = routing["provider"]
    est_cost = routing["estimated_cost"]

    log.info(
        "cost_route",
        extra={
            "model": chosen_model,
            "provider": chosen_provider,
            "task": routing["task_type"],
            "period": routing["period"],
            "est_cost": est_cost,
            "reason": routing["reason"],
        },
    )

    reply = None

    if chosen_provider == "deepseek":
        # DeepSeek 系 (V4-Pro 或 V4-Flash)
        with_cache = True  # DeepSeek 主力时启用 prompt cache
        ds_model = chosen_model  # deepseek-v4-pro 或 deepseek-v4-flash
        reply = await _call_deepseek(messages, max_tokens, with_cache=with_cache, model=ds_model)
        if reply is None:
            # 兜底: 切换到另一个 DeepSeek 模型
            fallback = routing.get("fallback_model", "")
            if fallback and fallback.startswith("deepseek"):
                log.warning("DeepSeek %s 失败, 切换 %s 兜底" % (ds_model, fallback))
                reply = await _call_deepseek(messages, max_tokens, with_cache=False, model=fallback)
            else:
                # 兜底到百炼
                log.warning("DeepSeek 全部失败, 切换百炼兜底")
                reply = await _call_bailian(messages, max_tokens)
    elif chosen_provider == "bailian":
        # 百炼系 (Qwen3.8-Max 等)
        reply = await _call_bailian(messages, max_tokens)
        if reply is None:
            # 兜底: DeepSeek
            fallback = routing.get("fallback_model", "")
            if fallback and fallback.startswith("deepseek"):
                log.warning("百炼失败, 切换 DeepSeek %s 兜底" % fallback)
                reply = await _call_deepseek(messages, max_tokens, with_cache=False, model=fallback)
            else:
                log.warning("百炼失败, 切换 DeepSeek V4-Pro 兜底")
                reply = await _call_deepseek(messages, max_tokens, with_cache=False)

    # 记录成本
    tracker.record(chosen_model, est_cost)

    if not reply:
        log.error("双模型均不可用")
        return "抱歉, 服务暂时不可用, 请稍后再试~"

    # 末尾兜底加 AI 标识
    if not reply.rstrip().endswith("(以上内容由 AI 生成, 仅供参考)"):
        reply = reply.rstrip() + "\n\n(以上内容由 AI 生成, 仅供参考)"

    return reply


async def check_llm_ready() -> dict:
    """检查 LLM 服务就绪状态, 返回各模型可用性 + 当前主力"""
    result = {
        "primary_model": settings.PRIMARY_MODEL,
        "deepseek": False,
        "bailian": False,
    }

    # 检查 DeepSeek
    if settings.DEEPSEEK_API_KEY:
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
                result["deepseek"] = resp.status_code == 200
        except Exception as e:
            log.warning(f"DeepSeek check failed: {e}")

    # 检查千问百炼
    from app.services import bailian
    result["bailian"] = await bailian.check_bailian_ready()

    return result
