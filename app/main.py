"""FastAPI 应用入口：提供穿搭推荐接口和前端页面。"""
import base64
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.graph.workflow import run_recommendation

app = FastAPI(title="i-clothes 智能穿搭助手", version="0.1.0")

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@app.get("/")
async def index() -> FileResponse:
    """返回前端首页。"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    """健康检查，同时返回千问是否已配置。"""
    return {"status": "ok", "qianwen_configured": bool(settings.QIANWEN_API_KEY)}


@app.post("/api/recommend")
async def recommend(
    images: list[UploadFile] = File(...),
    description: str = Form(""),
) -> dict:
    """接收参考照片和文字说明，返回穿搭建议。"""
    if not images:
        raise HTTPException(status_code=400, detail="请至少上传一张照片")

    if len(images) > settings.MAX_UPLOAD_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"最多上传 {settings.MAX_UPLOAD_COUNT} 张照片",
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    image_urls: list[str] = []

    for image in images:
        if image.content_type not in settings.ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的图片格式：{image.content_type}，仅支持 JPG/PNG",
            )
        data = await image.read()
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"图片 {image.filename} 超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制",
            )
        b64 = base64.b64encode(data).decode("utf-8")
        image_urls.append(f"data:{image.content_type};base64,{b64}")

    try:
        suggestion = await run_recommendation(image_urls, description)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"suggestion": suggestion}


# 静态资源（CSS/JS）
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
