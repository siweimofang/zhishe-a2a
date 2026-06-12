"""
LLM 调用封装
主力:DeepSeek-V4-Pro(3/6 元/百万 tokens)
备份:MiniMax M3(4.20/16.80 元/百万 tokens,故障切)

V1.0 简化:用 httpx 直连 DeepSeek(OpenAI 兼容)
"""
import asyncio
import logging
import httpx

from app.config import settings

log = logging.getLogger("llm")

DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_CHAT = f"{DEEPSEEK_BASE}/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-pro"


async def chat_with_skill(user_text: str) -> str:
    """
    处理千问发来的用户消息,返回 Agent 回复文本
    """
    from app.prompts.xiaozhi import XIAOZHI_SYSTEM_PROMPT

    messages = [
        {
            "role": "system",
            "content": XIAOZHI_SYSTEM_PROMPT,
            # DeepSeek prompt cache:标记 system prompt 缓存
            # 多次请求中相同的 system prompt 命中 cache,降低首字延迟
            "cache_control": {"type": "ephemeral"},
        },
        {"role": "user", "content": user_text},
    ]

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1200,
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
