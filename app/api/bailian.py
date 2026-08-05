"""
百炼 Agent 2.0 适配端点(2026-08-05)
==============================================
让百炼新版智能体应用通过 HTTP 插件 → MCP 服务挂载知设后端
(B 方案:百炼作外壳,业务逻辑全走知设 V1.7 后端)

POST /bailian/proxy
- request : {"prompt": "用户问题", "session_id": "可选"}
- response: {"text": "知设回答", "session_id": "会话ID"}
- 鉴权    : X-API-Key: <A2A_API_KEY>(百炼插件自定义 Header)
            或 Authorization: Bearer <A2A_API_KEY>(兼容现有调用方)

与 OpenAI 兼容端点(/v1/chat/completions)行为对齐:
- 复用 chat_with_skill() 的 V1.7 报价注入 + RAG 知识库链路
- 复用 pre_request_hooks(隐私拦截) + orchestrator(C/B 端链路)

已知限制(与 openai_compat 一致):知设后端当前为无状态单轮,
多轮上下文由调用方(百炼平台短期记忆)维护;session_id 透传回显,
为未来接入会话记忆预留接口。
"""
import json
import logging
import time
import uuid

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.llm import chat_with_skill

# V6.0 Skills 架构(与 openai_compat 相同导入方式)
try:
    from app.services.hook_runner import (
        pre_request_hooks,
        run_orchestrator_if_needed,
        extract_intent_and_params,
    )
    SKILLS_ENABLED = True
except ImportError as e:
    logging.getLogger("bailian").warning(f"Skills 架构未启用: {e}")
    SKILLS_ENABLED = False

router = APIRouter()
log = logging.getLogger("bailian")


def _verify_api_key(request: Request) -> bool:
    """百炼兼容鉴权:X-API-Key 头优先(百炼插件自定义 Header),
    兼容 Authorization: Bearer(现有调用方风格)。
    未配 A2A_API_KEY 时本地联调放行,与 auth.py 行为一致。
    """
    if not settings.A2A_API_KEY:
        return True
    x_key = request.headers.get("X-API-Key")
    if x_key:
        return x_key.strip() == settings.A2A_API_KEY
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip() == settings.A2A_API_KEY
    return False


@router.post("/proxy")
async def bailian_proxy(request: Request):
    """百炼 Agent 2.0 HTTP 插件适配入口

    请求体(百炼插件入参定义):
      prompt     string  必填  用户问题(百炼"大模型识别"自动填充)
      session_id string  可选  会话 ID(百炼"业务透传"可配置)
    """
    # 1. 鉴权
    if not _verify_api_key(request):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # 2. 解析与校验
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {e}"})

    prompt = body.get("prompt")
    session_id = body.get("session_id", "")
    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "prompt is required (non-empty string)"},
        )
    prompt = prompt.strip()

    log.info(
        "bailian_proxy_call",
        extra={
            "extra_text_len": len(prompt),
            "extra_session": bool(session_id),
        },
    )

    # 3. 请求前 hooks + orchestrator(与 openai_compat 对齐)
    if SKILLS_ENABLED:
        messages = [{"role": "user", "content": prompt}]

        # 3.1 隐私/合规拦截 hooks
        try:
            pre_results = await pre_request_hooks(
                {"messages": messages}, token_count=0, max_tokens=8000
            )
            for r in pre_results:
                if r.severity == "critical" and not r.passed:
                    return JSONResponse(
                        status_code=400,
                        content={"error": f"Hook 拦截: {r.message}"},
                    )
        except Exception as e:
            log.exception(f"pre_request_hooks 异常: {e}")

        # 3.2 orchestrator(C/B 端链路),编排结果拼入 prompt 供 LLM 参考
        try:
            info = extract_intent_and_params(messages)
            orch_result = await run_orchestrator_if_needed(
                user_intent=info.get("user_intent", ""),
                user_id=info.get("user_id", "anonymous"),
                params=info.get("params", {}),
            )
            if orch_result:
                rag_inject = json.dumps(
                    orch_result.to_dict(), ensure_ascii=False, indent=2
                )
                prompt = prompt + f"\n\n[Skills 编排结果]结构化数据参考:\n{rag_inject}"
                log.info(
                    f"orchestrator 注入: path={orch_result.path}, steps={len(orch_result.steps)}"
                )
        except Exception as e:
            log.exception(f"orchestrator 异常: {e}")

    # 4. 核心调用:复用 V1.7 报价注入 + RAG 知识库链路
    t0 = time.perf_counter()
    try:
        assistant_text = await chat_with_skill(prompt)
    except Exception as e:
        log.exception("bailian_proxy LLM call failed")
        return JSONResponse(status_code=500, content={"error": f"Internal error: {str(e)}"})

    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    # 5. session_id:传入则原样回显(调用方维护),否则新生成(留位)
    if not session_id:
        session_id = uuid.uuid4().hex

    log.info(
        "bailian_proxy_done",
        extra={
            "extra_latency_ms": latency_ms,
            "extra_reply_len": len(assistant_text),
        },
    )

    return JSONResponse({"text": assistant_text, "session_id": session_id})
