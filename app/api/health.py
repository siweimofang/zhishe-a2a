"""健康检查"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health():
    return {"status": "ok", "service": "zhishe-ai-renovation"}


@router.get("/ready")
async def ready():
    """就绪检查:LLM 是否通"""
    from app.services.llm import check_llm_ready
    llm_ok = await check_llm_ready()
    return {
        "status": "ok" if llm_ok else "degraded",
        "llm_ready": llm_ok,
    }
