"""
LLM 调用封装
主力: 千问百炼 qwen3.8-max (阿里生态内, 数据合规)
备份: DeepSeek-V4-Pro (3/6 元/百万 tokens, 故障自动切换)
兜底: 智谱 GLM-4-Flash (免费, 前两个都挂了就靠它)

V2.1 抗负载升级 (2026-08-26):
- 指数退避重试: 2s→4s→8s + 随机抖动(防雷群效应)
- 错误分类: 负载高/限流→重试; 鉴权/内容→立即放弃(不浪费重试次数)
- 响应体错误检测: HTTP 200 但 body 含 error 也能识别
- 熔断器: 连续失败 3 次 → 熔断 60 秒, 避免反复打已挂的 API
- 三级降级链: 百炼 → DeepSeek → GLM-4-Flash(免费)

V2.0 百炼主力迁移 (2026-08-20):
- 通过 PRIMARY_MODEL 配置项控制主力/兜底角色
- 一行切换: .env 改 PRIMARY_MODEL=bailian|deepseek 即生效
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
import random
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
# 错误分类: 区分"可重试"和"不可重试"
# ---------------------------------------------------------------------------

class LLMErrorType:
    OVERLOAD = "overload"          # 模型负载高/限流 (429/529/503) → 指数退避重试
    CONNECTION = "connection"      # 网络超时/连接失败 → 重试
    AUTH = "auth"                  # 鉴权失败 (401/403) → 不重试
    CONTENT = "content"            # 内容过滤 (400) → 不重试
    UNKNOWN = "unknown"            # 其他 → 有限重试


def classify_error(status_code: int | None, error_text: str = "") -> str:
    """
    根据 HTTP 状态码和错误文本判断错误类型。
    返回 LLMErrorType 常量。
    """
    error_text_lower = error_text.lower()

    # 负载高/限流 → 可重试
    if status_code in (429, 503, 529):
        return LLMErrorType.OVERLOAD
    if any(kw in error_text_lower for kw in (
        "负载", "overload", "rate limit", "too many", "capacity",
        "busy", "unavailable", "throttl", "quota",
    )):
        return LLMErrorType.OVERLOAD

    # 鉴权失败 → 不重试
    if status_code in (401, 403):
        return LLMErrorType.AUTH
    if any(kw in error_text_lower for kw in ("api key", "unauthorized", "forbidden", "invalid key")):
        return LLMErrorType.AUTH

    # 内容过滤 → 不重试
    if status_code == 400 and any(kw in error_text_lower for kw in ("content", "safety", "filter", "moderation")):
        return LLMErrorType.CONTENT

    # 网络/连接问题 → 可重试
    if status_code is None:
        return LLMErrorType.CONNECTION

    return LLMErrorType.UNKNOWN


# ---------------------------------------------------------------------------
# 熔断器: 连续失败 N 次后暂时跳过该模型, 避免反复打已挂的 API
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    每个 provider 独立熔断。
    连续失败 failure_threshold 次 → 熔断 open → recovery_seconds 后自动半开探测。
    """

    def __init__(self, failure_threshold: int = 3, recovery_seconds: float = 60.0):
        self._failures: dict[str, int] = {}
        self._open_since: dict[str, float] = {}
        self._threshold = failure_threshold
        self._recovery = recovery_seconds

    def is_open(self, provider: str) -> bool:
        """检查该 provider 是否处于熔断状态"""
        if provider not in self._open_since:
            return False
        import time
        elapsed = time.monotonic() - self._open_since[provider]
        if elapsed >= self._recovery:
            # 半开: 允许一次探测
            del self._open_since[provider]
            self._failures[provider] = 0
            log.info("circuit_breaker_half_open", extra={"extra_provider": provider})
            return False
        return True

    def record_failure(self, provider: str):
        """记录一次失败, 达到阈值则熔断"""
        self._failures[provider] = self._failures.get(provider, 0) + 1
        if self._failures[provider] >= self._threshold:
            import time
            self._open_since[provider] = time.monotonic()
            log.warning(
                "circuit_breaker_open",
                extra={"extra_provider": provider, "extra_failures": self._failures[provider]},
            )

    def record_success(self, provider: str):
        """成功则重置计数"""
        self._failures.pop(provider, None)
        self._open_since.pop(provider, None)


# 全局熔断器实例
breaker = CircuitBreaker(failure_threshold=3, recovery_seconds=60.0)


# ---------------------------------------------------------------------------
# 指数退避工具
# ---------------------------------------------------------------------------

async def backoff_sleep(attempt: int, base: float = 2.0, cap: float = 8.0):
    """
    指数退避 + 随机抖动。
    attempt=0 → ~2s, attempt=1 → ~4s, attempt=2 → ~8s (封顶)。
    加 ±25% 抖动避免多实例同步重试(雷群效应)。
    """
    delay = min(base * (2 ** attempt), cap)
    jitter = delay * random.uniform(-0.25, 0.25)
    await asyncio.sleep(delay + jitter)


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

    V2.0 重试升级 (2026-08-26):
    - 3 次重试 + 指数退避(2s→4s→8s) + 随机抖动
    - 错误分类: 负载高/限流 → 重试; 鉴权/内容 → 立即放弃
    - 响应体错误检测(HTTP 200 但 body 含 error)
    - 熔断器联动
    """
    # 熔断检查
    if breaker.is_open("deepseek"):
        log.warning("DeepSeek 熔断中, 跳过调用")
        return None

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
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(DEEPSEEK_CHAT, headers=headers, json=payload)

                # 检查响应体中的错误(有些 API 返回 200 但 body 含 error)
                body_text = resp.text
                if resp.status_code == 200:
                    body = resp.json()
                    if "error" in body:
                        err_msg = body["error"].get("message", str(body["error"]))
                        err_type = classify_error(None, err_msg)
                        log.warning(f"DeepSeek 响应体错误 (attempt {attempt + 1}): {err_msg}")
                        if err_type in (LLMErrorType.AUTH, LLMErrorType.CONTENT):
                            breaker.record_failure("deepseek")
                            return None
                        # 负载类错误, 继续重试
                        last_err = Exception(err_msg)
                        await backoff_sleep(attempt)
                        continue
                    data = body
                    break
                else:
                    # HTTP 错误
                    err_type = classify_error(resp.status_code, body_text)
                    log.warning(
                        f"DeepSeek HTTP {resp.status_code} (attempt {attempt + 1}), "
                        f"错误类型={err_type}"
                    )

                    if err_type in (LLMErrorType.AUTH, LLMErrorType.CONTENT):
                        # 不可重试, 立即放弃
                        breaker.record_failure("deepseek")
                        return None

                    last_err = Exception(f"HTTP {resp.status_code}: {body_text[:200]}")
                    if attempt < max_attempts - 1:
                        await backoff_sleep(attempt)

        except httpx.TimeoutException as e:
            last_err = e
            log.warning(f"DeepSeek 超时 (attempt {attempt + 1}/{max_attempts})")
            if attempt < max_attempts - 1:
                await backoff_sleep(attempt)
        except httpx.ConnectError as e:
            last_err = e
            log.warning(f"DeepSeek 连接失败 (attempt {attempt + 1}/{max_attempts}): {e}")
            if attempt < max_attempts - 1:
                await backoff_sleep(attempt)
        except Exception as e:
            last_err = e
            err_type = classify_error(None, str(e))
            log.warning(f"DeepSeek call attempt {attempt + 1} failed: {e} (type={err_type})")
            if err_type in (LLMErrorType.AUTH, LLMErrorType.CONTENT):
                breaker.record_failure("deepseek")
                return None
            if attempt < max_attempts - 1:
                await backoff_sleep(attempt)

    if data is None:
        breaker.record_failure("deepseek")
        return None

    breaker.record_success("deepseek")
    choice = data.get("choices", [{}])[0]
    reply = choice.get("message", {}).get("content", "")
    return reply if reply else None


# ---------------------------------------------------------------------------
# 第三兜底: 智谱 GLM-4-Flash (免费, 前两个都挂了就靠它)
# ---------------------------------------------------------------------------

async def _call_glm_flash(messages: list[dict], max_tokens: int) -> str | None:
    """
    调用智谱 GLM-4-Flash (免费模型) 作为最后兜底。
    只有 ZHIPU_API_KEY 配置了才能用, 否则直接返回 None。
    只重试 1 次(免费模型, 不值得花太多时间)。
    """
    if not settings.ZHIPU_API_KEY:
        log.info("ZHIPU_API_KEY 未配置, 跳过 GLM-4-Flash 兜底")
        return None

    if breaker.is_open("zhipu"):
        log.warning("智谱 熔断中, 跳过 GLM-4-Flash 兜底")
        return None

    url = f"{settings.ZHIPU_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }
    # GLM 不支持 cache_control, 剥离
    clean_messages = [{k: v for k, v in msg.items() if k != "cache_control"} for msg in messages]
    payload = {
        "model": settings.ZHIPU_MODEL,
        "messages": clean_messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }

    data = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    body = resp.json()
                    if "error" not in body:
                        data = body
                        break
                    err_msg = body["error"].get("message", "")
                    log.warning(f"GLM-4-Flash 响应体错误: {err_msg}")
                else:
                    log.warning(f"GLM-4-Flash HTTP {resp.status_code}")
                if attempt == 0:
                    await backoff_sleep(0, base=1.0, cap=3.0)
        except Exception as e:
            log.warning(f"GLM-4-Flash attempt {attempt + 1} 失败: {e}")
            if attempt == 0:
                await backoff_sleep(0, base=1.0, cap=3.0)

    if data is None:
        breaker.record_failure("zhipu")
        return None

    breaker.record_success("zhipu")
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
    used_model = chosen_model  # 实际成功使用的模型(用于成本记录)

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
                if reply:
                    used_model = fallback
            if reply is None:
                # 第二兜底: 百炼
                log.warning("DeepSeek 全部失败, 切换百炼兜底")
                reply = await _call_bailian(messages, max_tokens)
                if reply:
                    used_model = "qwen3.8-max"
        if reply is None:
            # 第三兜底: GLM-4-Flash (免费)
            log.warning("百炼也失败, 切换 GLM-4-Flash 最后兜底")
            reply = await _call_glm_flash(messages, max_tokens)
            if reply:
                used_model = "glm-4-flash"

    elif chosen_provider == "bailian":
        # 百炼系 (Qwen3.8-Max 等)
        reply = await _call_bailian(messages, max_tokens)
        if reply is None:
            # 第一兜底: DeepSeek
            fallback = routing.get("fallback_model", "")
            if fallback and fallback.startswith("deepseek"):
                log.warning("百炼失败, 切换 DeepSeek %s 兜底" % fallback)
                reply = await _call_deepseek(messages, max_tokens, with_cache=False, model=fallback)
                if reply:
                    used_model = fallback
            else:
                log.warning("百炼失败, 切换 DeepSeek V4-Pro 兜底")
                reply = await _call_deepseek(messages, max_tokens, with_cache=False)
                if reply:
                    used_model = DEEPSEEK_MODEL
        if reply is None:
            # 第二兜底: GLM-4-Flash (免费)
            log.warning("百炼+DeepSeek 均失败, 切换 GLM-4-Flash 最后兜底")
            reply = await _call_glm_flash(messages, max_tokens)
            if reply:
                used_model = "glm-4-flash"

    # 记录成本(GLM-4-Flash 免费, 记 0)
    actual_cost = 0.0 if used_model == "glm-4-flash" else est_cost
    tracker.record(used_model, actual_cost)

    if not reply:
        log.error("三模型均不可用 (百炼+DeepSeek+GLM-4-Flash)")
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
        "glm_flash": False,
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

    # 检查智谱 GLM-4-Flash
    if settings.ZHIPU_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {settings.ZHIPU_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.ZHIPU_MODEL,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }
            url = f"{settings.ZHIPU_BASE_URL}/chat/completions"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                result["glm_flash"] = resp.status_code == 200
        except Exception as e:
            log.warning(f"GLM-4-Flash check failed: {e}")

    return result
