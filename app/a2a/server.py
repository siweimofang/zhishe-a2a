"""
A2A 0.2.5 协议服务端

实现端点:
- POST /a2a/message/send:同步 JSON-RPC 调用
- POST /a2a/message/stream:SSE 流式(V1.0 不支持)
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse

from app.services.llm import chat_with_skill
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

    log.info(f"A2A call: method={method}, id={req_id}")

    if method == "message/stream":
        return JSONResponse(_jsonrpc_err(
            req_id, -32601,
            "Streaming not supported in V1.0, use message/send instead"
        ))

    if method != "message/send":
        return JSONResponse(_jsonrpc_err(
            req_id, -32601, f"Method not found: {method}"
        ))

    # 提取 message
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

    # 调 LLM
    try:
        agent_text = await chat_with_skill(user_text)
    except Exception as e:
        log.exception("LLM call failed")
        return JSONResponse(_jsonrpc_err(
            req_id, -32603, f"Internal error: {str(e)}"
        ))

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
