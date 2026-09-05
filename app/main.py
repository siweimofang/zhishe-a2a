"""
知设 AI 装修顾问 · 自建 Agent 版
A2A 0.2.5 协议服务端
V1.4 V6.0:集成 Anthropic Skills(8 Skill + 5 Hook + orchestrator)
"""
import logging

from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os

from app.a2a.server import router as a2a_router
from app.a2a.agent_card import get_agent_card
from app.api.agent_card_endpoint import router as agent_card_endpoint_router
from app.api.auth import require_api_key
from app.api.health import router as health_router
from app.api.openai_compat import router as openai_router
from app.api.bailian import router as bailian_router
from app.api.gotchas_api import router as gotchas_router, admin_router as gotchas_admin_router
from app.config import settings
from app.observability import setup_logging, TimingMiddleware


# === 结构化日志 + 响应时间中间件 ===
setup_logging(settings.LOG_LEVEL)
logging.getLogger("startup").info("app_boot", extra={"extra_version": "1.4.0-V6.0-skills"})

app = FastAPI(
    title="知设 AI 装修顾问",
    description="沈阳本地化装修报价 · A2A 0.2.5 协议 + OpenAI-compatible + Anthropic Skills 8 个",
    version="1.4.0",
)

app.add_middleware(TimingMiddleware)

app.include_router(a2a_router, prefix="/a2a", tags=["a2a"])
app.include_router(openai_router, prefix="/v1", tags=["openai-compat"])  # /v1/chat/completions
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(agent_card_endpoint_router, tags=["agent-card"])
app.include_router(gotchas_router)  # /gotchas/* — Gotchas库V1.1知识库API
app.include_router(gotchas_admin_router)  # /admin/* — Gotchas运维管理端点(P2/P3)
app.include_router(bailian_router, prefix="/bailian", tags=["bailian"])  # /bailian/proxy — 百炼 Agent 2.0 适配端点

# === V6.0 升级:Anthropic Skills 路由 ===
SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


@app.get("/skills/{skill_name}/{file_path:path}", include_in_schema=False, dependencies=[Depends(require_api_key)])
async def serve_skill_file(skill_name: str, file_path: str):
    """提供 Skill 文件访问(SKILL.md / gotchas.md / scripts/*.py) — 铁律 75 v2 第 7 项:默认私有"""
    full_path = os.path.join(SKILLS_DIR, skill_name, file_path)
    if not os.path.isfile(full_path):
        return JSONResponse(status_code=404, content={"error": f"Skill file not found: {skill_name}/{file_path}"})
    return FileResponse(full_path, media_type="text/plain; charset=utf-8")


@app.get("/skills", include_in_schema=False, dependencies=[Depends(require_api_key)])
async def list_skills():
    """列出所有 Skill — 铁律 75 v2 第 7 项:默认私有"""
    skills = []
    if os.path.isdir(SKILLS_DIR):
        for d in sorted(os.listdir(SKILLS_DIR)):
            skill_md = os.path.join(SKILLS_DIR, d, "SKILL.md")
            if os.path.isfile(skill_md):
                skills.append({
                    "name": d,
                    "skill_md": f"/skills/{d}/SKILL.md",
                    "gotchas_md": f"/skills/{d}/gotchas.md",
                })
    return {"skills": skills, "total": len(skills)}


@app.get("/data/{file_path:path}", include_in_schema=False, dependencies=[Depends(require_api_key)])
async def serve_data_file(file_path: str):
    """提供 data 目录文件访问(city_pricing.json / memory/*.json) — 铁律 75 v2 第 7 项:默认私有"""
    full_path = os.path.join(DATA_DIR, file_path)
    if not os.path.isfile(full_path):
        return JSONResponse(status_code=404, content={"error": f"Data file not found: {file_path}"})
    if file_path.endswith(".json"):
        return FileResponse(full_path, media_type="application/json; charset=utf-8")
    return FileResponse(full_path)


# === 静态文件服务(AGC 智能体隐私政策 + HAP 下载) ===
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def _static_path(name: str) -> str:
    """返回 static/ 目录下文件的绝对路径"""
    return os.path.join(STATIC_DIR, name)


@app.get("/privacy", include_in_schema=False)
async def privacy_page():
    """隐私政策 — tunnel.zhishe.top/privacy (小艺审核要求)"""
    p = _static_path("privacy.html")
    if os.path.isfile(p):
        return FileResponse(p, media_type="text/html; charset=utf-8")
    return JSONResponse(status_code=404, content={"error": "隐私政策页面不存在"})


@app.get("/terms", include_in_schema=False)
async def terms_page():
    """用户协议 — tunnel.zhishe.top/terms"""
    p = _static_path("terms.html")
    if os.path.isfile(p):
        return FileResponse(p, media_type="text/html; charset=utf-8")
    return JSONResponse(status_code=404, content={"error": "用户协议页面不存在"})


@app.get("/faq-gb-standards", include_in_schema=False)
async def faq_gb_page():
    """国标知识库 FAQ"""
    p = _static_path("faq-gb-standards.html")
    if os.path.isfile(p):
        return FileResponse(p, media_type="text/html; charset=utf-8")
    return JSONResponse(status_code=404, content={"error": "FAQ 页面不存在"})


@app.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card():
    """千问通过这个端点发现 Agent 能力(A2A 规范要求)"""
    return JSONResponse(content=get_agent_card(base_url=settings.PUBLIC_BASE_URL).model_dump(exclude_none=True))


@app.get("/v1/models", include_in_schema=False)
async def openai_models():
    """OpenAI 兼容端点 /v1/models"""
    return JSONResponse(content={
        "object": "list",
        "data": [
            {
                "id": "zhishe-a2a",
                "object": "model",
                "created": 1700000000,
                "owned_by": "zhishe",
            }
        ]
    })


@app.get("/")
async def root():
    return {
        "service": "zhishe-ai-renovation",
        "version": "1.4.0",
        "protocol": "A2A 0.2.5 + OpenAI-compatible",
        "agent_card": "/.well-known/agent.json",
        "endpoints": {
            "message_send": "/a2a/message/send",
            "message_stream": "/a2a/message/stream",
            "openai_chat_completions": "/v1/chat/completions",
        },
    }
