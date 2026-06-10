"""
知设 AI 装修顾问 · 自建 Agent 版
A2A 0.2.5 协议服务端
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.a2a.server import router as a2a_router
from app.a2a.agent_card import get_agent_card
from app.api.health import router as health_router


app = FastAPI(
    title="知设 AI 装修顾问",
    description="沈阳本地化装修报价 · A2A 0.2.5 协议",
    version="1.0.0",
)

app.include_router(a2a_router, prefix="/a2a", tags=["a2a"])
app.include_router(health_router, prefix="/health", tags=["health"])


@app.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card():
    """千问通过这个端点发现 Agent 能力(A2A 规范要求)"""
    return JSONResponse(content=get_agent_card().model_dump(exclude_none=True))


@app.get("/")
async def root():
    return {
        "service": "zhishe-ai-renovation",
        "version": "1.0.0",
        "protocol": "A2A 0.2.5",
        "agent_card": "/.well-known/agent.json",
        "endpoints": {
            "message_send": "/a2a/message/send",
            "message_stream": "/a2a/message/stream",
        },
    }
