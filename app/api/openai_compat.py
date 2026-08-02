"""
OpenAI-compatible 端点(V2.0,2026-06-13 + V6.0 升级 2026-06-26)
让百炼「我的模型」→「+ 导入模型」能直接接入 zhishe-a2a

POST /v1/chat/completions
- request body: OpenAI ChatCompletionRequest 格式
- response: OpenAI ChatCompletionResponse 格式
- 流式:支持,但 V1.0 默认非流式(SSE 可选)

V6.0 升级(Anthropic Skills 集成):
- 请求前:pre_request_hooks(token + 隐私)
- 触发 orchestrator(C/B 端链路)
- 响应后:post_response_hooks(隐私)

鉴权:Authorization: Bearer <A2A_API_KEY> (OpenAI 标准)
复用 chat_with_skill() 的报价+RAG 注入逻辑
"""
import json
import time
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.services.llm import chat_with_skill

# V6.0 升级:导入 Skills 架构
try:
    from app.services.hook_runner import pre_request_hooks, post_response_hooks, run_orchestrator_if_needed, extract_intent_and_params
    from app.services.orchestrator import dispatch as orchestrator_dispatch
    SKILLS_ENABLED = True
except ImportError as e:
    log.warning(f"Skills 架构未启用: {e}")
    SKILLS_ENABLED = False

router = APIRouter()
log = logging.getLogger("openai_compat")


# ============================================================
# OpenAI ChatCompletionRequest 模型(Pydantic-free,简单 dict 校验)
# ============================================================

OPENAI_ERROR_INVALID_REQUEST = -40001  # 内部 error code (非 OpenAI 标准)


def _verify_api_key(authorization: Optional[str]) -> bool:
    """OpenAI 标准鉴权:Authorization: Bearer xxx"""
    if not settings.A2A_API_KEY:
        return True  # 配了就严格,没配放行(本地联调)
    if not authorization:
        return False
    token = authorization.replace("Bearer ", "").strip()
    return token == settings.A2A_API_KEY


def _messages_to_text(messages: List[Dict[str, Any]]) -> str:
    """OpenAI 的 messages 列表 → 单一文本(V1.0 简化:取最后一个 user message)
    V2.0 完整版要支持多轮对话上下文
    """
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            # OpenAI 多模态格式:content 是 list of parts
            if isinstance(content, list):
                text_parts = [
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                return " ".join(text_parts)
    return ""


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible ChatCompletion 端点

    V1.0: 仅支持非流式
    鉴权: Authorization: Bearer <A2A_API_KEY>
    """
    # 鉴权
    auth = request.headers.get("Authorization")
    if not _verify_api_key(auth):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # 解析 body
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": f"Invalid JSON: {e}",
                    "type": "invalid_request_error",
                    "code": OPENAI_ERROR_INVALID_REQUEST,
                }
            },
        )

    messages = body.get("messages", [])
    if not messages:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": "messages is required and must be non-empty",
                    "type": "invalid_request_error",
                    "code": OPENAI_ERROR_INVALID_REQUEST,
                }
            },
        )

    model_name = body.get("model", "zhishe-a2a")
    stream = body.get("stream", False)
    temperature = body.get("temperature", 0.7)
    max_tokens = body.get("max_tokens", 1200)

    user_text = _messages_to_text(messages)
    if not user_text:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": "No text content in messages",
                    "type": "invalid_request_error",
                    "code": OPENAI_ERROR_INVALID_REQUEST,
                }
            },
        )

    log.info(
        "openai_compat_call",
        extra={
            "extra_model": model_name,
            "extra_text_len": len(user_text),
            "extra_stream": stream,
            "extra_temperature": temperature,
        },
    )

    # V6.0 升级:请求前 hooks + orchestrator
    if SKILLS_ENABLED:
        # 1. 请求前 hooks
        try:
            pre_results = await pre_request_hooks(body, token_count=0, max_tokens=8000)
            for r in pre_results:
                if r.severity == "critical" and not r.passed:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "message": f"Hook 拦截: {r.message}",
                                "type": "invalid_request_error",
                                "code": "hook_blocked",
                            }
                        },
                    )
        except Exception as e:
            log.exception(f"pre_request_hooks 异常: {e}")

        # 2. orchestrator(C/B 端链路)
        try:
            info = extract_intent_and_params(messages)
            orch_result = await run_orchestrator_if_needed(
                user_intent=info.get("user_intent", ""),
                user_id=info.get("user_id", "anonymous"),
                params=info.get("params", {}),
            )
            if orch_result:
                # 把 orchestrator 结果作为 RAG 注入到 LLM
                rag_inject = json.dumps(orch_result.to_dict(), ensure_ascii=False, indent=2)
                body = {**body, "messages": messages + [{
                    "role": "system",
                    "content": f"[Skills 编排结果]以下是 C 端装修咨询的结构化结果,作为精确数据注入:\n{rag_inject}\n请基于这些数据回答用户问题。",
                }]}
                log.info(f"orchestrator 注入: path={orch_result.path}, steps={len(orch_result.steps)}")
        except Exception as e:
            log.exception(f"orchestrator 异常: {e}")

    # 非流式
    if not stream:
        t0 = time.perf_counter()
        try:
            assistant_text = await chat_with_skill(user_text)
        except Exception as e:
            log.exception("chat_completions LLM call failed")
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": f"Internal error: {str(e)}",
                        "type": "server_error",
                        "code": "internal_error",
                    }
                },
            )
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        log.info(
            "openai_compat_done",
            extra={
                "extra_model": model_name,
                "extra_latency_ms": latency_ms,
                "extra_reply_len": len(assistant_text),
            },
        )

        return JSONResponse(
            {
                "id": f"chatcmpl-{uuid.uuid4()}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": assistant_text,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": len(user_text),  # 近似,实际要 tokenizer
                    "completion_tokens": len(assistant_text),
                    "total_tokens": len(user_text) + len(assistant_text),
                },
            }
        )

    # 流式(SSE 格式,与 OpenAI 一致)
    async def event_generator():
        try:
            # V1.0 简化:还是同步调,再切段发
            full_text = await chat_with_skill(user_text)
            chunk_id = f"chatcmpl-{uuid.uuid4()}"
            # 按 ~50 字符切
            for i in range(0, len(full_text), 50):
                chunk_text = full_text[i : i + 50]
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": chunk_text},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            # 结束 chunk
            end_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_name,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            log.exception("Stream LLM call failed")
            err_chunk = {
                "error": {
                    "message": f"Internal error: {str(e)}",
                    "type": "server_error",
                }
            }
            yield f"data: {json.dumps(err_chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
