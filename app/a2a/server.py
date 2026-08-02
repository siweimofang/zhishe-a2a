"""
A2A 0.2.5 协议服务端

实现端点:
- POST /a2a/message/send:同步 JSON-RPC 调用
- POST /a2a/message/stream:SSE 流式(STREAMING_ENABLED=true 时启用)
"""
import uuid
import json
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, AsyncIterator

from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.llm import chat_with_skill
from app.services.wait_self_check import wait_self_check_before_llm
from app.services.quote import parse_user_intent
from app.config import settings

router = APIRouter()
log = logging.getLogger("a2a")


def _jsonrpc_ok(id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_err(id: str, code: int, message: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": id,
        "error": {"code": code, "message": message},
    }


def _verify_api_key(authorization: Optional[str]) -> bool:
    """验证千问调你时的 X-API-Key"""
    if not settings.A2A_API_KEY:
        return True  # 未配置则不校验(本地联调)
    if not authorization:
        return False
    token = authorization.replace("Bearer ", "").strip()
    return token == settings.A2A_API_KEY


@router.post("/message/send")
async def message_send(request: Request):
    """
    A2A JSON-RPC 同步端点
    接收千问发来的 user message,返回 Agent 回复
    """
    auth = request.headers.get("X-API-Key") or request.headers.get("Authorization")
    if not _verify_api_key(auth):
        raise HTTPException(status_code=401, detail="Invalid API Key")

    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(_jsonrpc_err("unknown", -32700, f"Parse error: {e}"))

    req_id = body.get("id", "unknown")
    method = body.get("method", "")
    params = body.get("params", {})

    log.info("a2a_call", extra={"extra_method": method, "extra_req_id": req_id})

    # === method 检查(先于 parts 检查,符合 A2A 协议惯例)===
    # 流式分支
    if method == "message/stream":
        if not settings.STREAMING_ENABLED:
            return JSONResponse(_jsonrpc_err(
                req_id, -32601,
                "Streaming not enabled. Set STREAMING_ENABLED=true in .env to use message/stream."
            ))
        # 流式响应必须先有 user_text,流式不需要重新提取
        message = params.get("message", {})
        parts = message.get("parts", [])
        user_text = ""
        for part in parts:
            if part.get("kind") == "text":
                user_text += part.get("text", "")
        if not user_text:
            return JSONResponse(_jsonrpc_err(
                req_id, -32602, "No text content in message"
            ))
        return StreamingResponse(
            _stream_llm_response(req_id, user_text, message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 同步分支:非 message/send 都返 -32601
    if method != "message/send":
        return JSONResponse(_jsonrpc_err(
            req_id, -32601, f"Method not found: {method}"
        ))

    # 提取 message(同步路径)
    message = params.get("message", {})
    parts = message.get("parts", [])
    user_text = ""
    for part in parts:
        if part.get("kind") == "text":
            user_text += part.get("text", "")
    if not user_text:
        return JSONResponse(_jsonrpc_err(
            req_id, -32602, "No text content in message"
        ))

    log.info("a2a_llm_start", extra={"extra_text_len": len(user_text), "extra_req_id": req_id})

    # === Phase 1 Wait! 自纠错(2026-06-25 接入)===
    # 先 parse 出 package/tier/area,触发自纠错
    intent = parse_user_intent(user_text)
    wait_text = ""
    if intent.get("package") and intent.get("tier") and intent.get("area"):
        try:
            wait_text = wait_self_check_before_llm(
                package=intent["package"],
                tier=intent["tier"],
                area=float(intent["area"]),
                user_text=user_text,
                city=None,  # V1.3 未解析 city,V2.0 加城市字段
            )
            if wait_text:
                log.info(
                    "wait_self_check_triggered",
                    extra={
                        "extra_req_id": req_id,
                        "extra_confidence": "see_wait_text",
                        "extra_warnings_count": wait_text.count("Wait!"),
                    },
                )
        except Exception as e:
            log.warning(f"wait_self_check_failed: {e}")
            wait_text = ""

    # 合并 Wait! 警告到 LLM prompt
    llm_input = user_text
    if wait_text:
        llm_input = user_text + "\n\n" + wait_text

    # 调 LLM
    t0 = time.perf_counter()
    try:
        agent_text = await chat_with_skill(llm_input)
    except Exception as e:
        log.exception("LLM call failed")
        return JSONResponse(_jsonrpc_err(
            req_id, -32603, f"Internal error: {str(e)}"
        ))
    llm_ms = round((time.perf_counter() - t0) * 1000, 1)

    log.info(
        "a2a_llm_done",
        extra={
            "extra_req_id": req_id,
            "extra_llm_latency_ms": llm_ms,
            "extra_reply_len": len(agent_text),
        },
    )

    # 构造 A2A Task 响应
    task_id = f"task-{uuid.uuid4()}"
    context_id = message.get("contextId", f"ctx-{uuid.uuid4()}")

    response_task = {
        "id": task_id,
        "contextId": context_id,
        "kind": "task",
        "status": {
            "state": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "artifacts": [
            {
                "artifactId": f"art-{uuid.uuid4()}",
                "parts": [
                    {"kind": "text", "text": agent_text}
                ],
            }
        ],
    }

    return JSONResponse(_jsonrpc_ok(req_id, response_task))


async def _stream_llm_response(
    req_id: str, user_text: str, message: Dict[str, Any]
) -> AsyncIterator[bytes]:
    """
    流式响应生成器(假流式:V1.0 简化 —— 同步调 LLM,再 SSE 一段段发)
    真正的 token 级流式需要换 LLM SDK(支持 stream=True),V2.0+ 再做
    """
    from app.prompts.xiaozhi import XIAOZHI_SYSTEM_PROMPT  # 留作升级真流式用

    log = logging.getLogger("a2a")
    log.info("a2a_stream_start", extra={"extra_req_id": req_id, "extra_text_len": len(user_text)})

    t0 = time.perf_counter()
    try:
        # V1.0 简化:还是同步调,得到完整文本后切成多段 SSE 发
        # 真流式要 httpx stream=True + DeepSeek stream=True,V2.0 做
        full_text = await chat_with_skill(user_text)
    except Exception as e:
        log.exception("Stream LLM call failed")
        err_event = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
        }
        yield f"data: {json.dumps(err_event, ensure_ascii=False)}\n\n".encode("utf-8")
        return

    llm_ms = round((time.perf_counter() - t0) * 1000, 1)
    log.info(
        "a2a_stream_done",
        extra={"extra_req_id": req_id, "extra_llm_latency_ms": llm_ms, "extra_reply_len": len(full_text)},
    )

    # 切分成 ~50 字符一段,逐段发
    chunk_size = 50
    task_id = f"task-{uuid.uuid4()}"
    context_id = message.get("contextId", f"ctx-{uuid.uuid4()}")
    artifact_id = f"art-{uuid.uuid4()}"

    for i in range(0, len(full_text), chunk_size):
        chunk = full_text[i : i + chunk_size]
        event = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "id": task_id,
                "contextId": context_id,
                "kind": "task",
                "status": {
                    "state": "working" if i + chunk_size < len(full_text) else "completed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "artifacts": [
                    {
                        "artifactId": artifact_id,
                        "parts": [{"kind": "text", "text": chunk}],
                    }
                ],
            },
        }
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
        # 真实场景下这里不该 await,客户端拉得动才发 —— V2.0+ 优化
        await asyncio.sleep(0.05)  # 让出事件循环,客户端能持续收到

    # 结束标记
    yield b"data: [DONE]\n\n"
