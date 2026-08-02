"""
API 鉴权依赖(铁律 75 v2 第 7 项:默认私有而非公开)
复用于:Skill 列表 / 城市价格数据 / 任何敏感端点
用法:from app.api.auth import require_api_key
     @router.get("/xxx", dependencies=[Depends(require_api_key)])
"""
from typing import Optional
from fastapi import Header, HTTPException

from app.config import settings


def _verify_api_key(authorization: Optional[str]) -> bool:
    """统一鉴权函数(铁律 75 v2 第 7 项)

    行为:
    - 未配 A2A_API_KEY:本地联调放行(返回 True)
    - 已配 A2A_API_KEY:必 Bearer 鉴权通过
    - 错误:返回 False
    """
    if not settings.A2A_API_KEY:
        return True  # 本地联调
    if not authorization:
        return False
    token = authorization.replace("Bearer ", "").strip()
    return token == settings.A2A_API_KEY


async def require_api_key(authorization: Optional[str] = Header(default=None)):
    """FastAPI 依赖:任何路由加 dependencies=[Depends(require_api_key)] 即可鉴权

    失败返回 401 + {"detail": "Invalid API key"}
    """
    if not _verify_api_key(authorization):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return authorization