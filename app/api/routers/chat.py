"""聊天接口：会话管理 + 多轮对话。"""
import base64
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.chat_service import handle_message
from app.services.conversation_store import store

router = APIRouter()

DATA_URL_RE = re.compile(r"^data:image/(jpeg|png);base64,")


class ChatRequest(BaseModel):
    """发消息请求体。"""

    conversation_id: str | None = None
    message: str = Field(default="", max_length=2000)
    images: list[str] = Field(default_factory=list)


def _validate_images(images: list[str]) -> list[str]:
    """校验图片 data URL：格式、数量、大小。"""
    if len(images) > settings.MAX_UPLOAD_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"最多上传 {settings.MAX_UPLOAD_COUNT} 张照片",
        )
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    validated: list[str] = []
    for url in images:
        m = DATA_URL_RE.match(url)
        if not m:
            raise HTTPException(
                status_code=400,
                detail="不支持的图片格式，仅支持 JPG/PNG",
            )
        # 估算 base64 解码后的大小（去掉 data URL 前缀）
        payload_len = len(url) - m.end()
        approx_bytes = int(payload_len * 3 / 4)
        if approx_bytes > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"图片超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制",
            )
        validated.append(url)
    return validated


@router.post("/api/conversations")
async def create_conversation() -> dict:
    """新建一个空会话。"""
    conv = await store.create()
    return {"id": conv.id, "title": conv.title}


@router.get("/api/conversations")
async def list_conversations() -> list[dict]:
    """会话列表（按更新时间倒序）。"""
    return await store.list_summaries()


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict:
    """会话详情（含全部消息）。"""
    conv = await store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "images": m.images,
                "created_at": m.created_at,
            }
            for m in conv.messages
        ],
    }


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict:
    """删除会话。"""
    if not await store.delete(conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.post("/api/chat")
async def chat(payload: ChatRequest) -> dict:
    """发送一条消息，返回回复与意图。"""
    message = payload.message.strip()
    images = _validate_images(payload.images)

    if not message and not images:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    result = await handle_message(
        conversation_id=payload.conversation_id,
        message=message,
        images=images,
    )
    return result
