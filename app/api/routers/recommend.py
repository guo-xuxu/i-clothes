"""穿搭推荐接口：接收参考照片与文字描述，返回穿搭建议。"""
import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.services.recommendation import recommend as recommend_service

router = APIRouter()


@router.post("/api/recommend")
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
        suggestion = await recommend_service(image_urls, description)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"suggestion": suggestion}
