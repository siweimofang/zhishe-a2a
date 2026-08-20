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
    llm_status = await check_llm_ready()
    any_ok = any(v for k, v in llm_status.items() if isinstance(v, bool))
    return {
        "status": "ok" if any_ok else "degraded",
        "llm_ready": llm_status,
    }


@router.get("/cost")
async def cost_status():
    """成本状态: 当前路由决策 + 累计成本"""
    from app.services.cost_router import tracker, get_period, is_peak_hour, pricing_report
    summary = tracker.summary()
    return {
        "status": "ok",
        "cost_tracking": summary,
        "pricing_report": pricing_report(),
    }
