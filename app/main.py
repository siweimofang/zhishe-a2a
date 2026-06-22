"""
知设 AI 装修顾问 · 自建 Agent 版
A2A 0.2.5 协议服务端
"""
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os

from app.a2a.server import router as a2a_router
from app.a2a.agent_card import get_agent_card
from app.api.health import router as health_router
from app.api.openai_compat import router as openai_router
from app.config import settings
from app.observability import setup_logging, TimingMiddleware


# === 结构化日志 + 响应时间中间件 ===
setup_logging(settings.LOG_LEVEL)
logging.getLogger("startup").info("app_boot", extra={"extra_version": "1.0.0"})

app = FastAPI(
    title="知设 AI 装修顾问",
    description="沈阳本地化装修报价 · A2A 0.2.5 协议 + OpenAI-compatible",
    version="1.0.0",
)

app.add_middleware(TimingMiddleware)

app.include_router(a2a_router, prefix="/a2a", tags=["a2a"])
app.include_router(openai_router, prefix="/v1", tags=["openai-compat"])  # /v1/chat/completions
app.include_router(health_router, prefix="/health", tags=["health"])

# === 静态文件服务(AGC 智能体隐私政策 + HAP 下载) ===
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card():
    """千问通过这个端点发现 Agent 能力(A2A 规范要求)"""
    return JSONResponse(content=get_agent_card(base_url=settings.PUBLIC_BASE_URL).model_dump(exclude_none=True))


@app.get("/")
async def root():
    return {
        "service": "zhishe-ai-renovation",
        "version": "1.0.0",
        "protocol": "A2A 0.2.5 + OpenAI-compatible",
        "agent_card": "/.well-known/agent.json",
        "endpoints": {
            "message_send": "/a2a/message/send",
            "message_stream": "/a2a/message/stream",
            "openai_chat_completions": "/v1/chat/completions",
        },
    }
