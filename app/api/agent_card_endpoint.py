"""
HarmonyOS 7 / A2A 标准 Agent Card 端点
路径:/.well-known/agent-card.json 和 /agent-card.json
(A2A 0.3.0 标准 RFC 8615)
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.a2a.agent_card import get_agent_card
from app.config import settings

router = APIRouter()


@router.get("/.well-known/agent-card.json", include_in_schema=False)
@router.get("/agent-card.json", include_in_schema=False)
async def agent_card_standard():
    """A2A 0.3.0 标准 Agent Card(HarmonyOS 7 / 跨平台兼容)"""
    card = get_agent_card(base_url=settings.PUBLIC_BASE_URL)
    return JSONResponse(content=card.model_dump(exclude_none=True))