"""健康检查接口。"""
from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/api/health")
async def health() -> dict:
    """健康检查，同时返回千问是否已配置。"""
    return {"status": "ok", "qianwen_configured": bool(settings.QIANWEN_API_KEY)}
