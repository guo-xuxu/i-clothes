"""Agent 服务契约接口：无状态推理入口（Java 业务后端调用）。"""
import logging
import re

import httpx
import openai
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.graph.workflow import run_chat

logger = logging.getLogger(__name__)

router = APIRouter()

DATA_URL_RE = re.compile(r"^data:image/(jpeg|png);base64,")


class AgentChatRequest(BaseModel):
    """无状态请求：message/images/history 一次带全。"""

    message: str = Field(default="", max_length=2000)
    images: list[str] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    reply: str
    intent: str


def _validate_images(images: list[str]) -> list[str]:
    """图片 data URL 校验：格式/数量/大小（与旧 /api/chat 校验一致）。"""
    if len(images) > settings.MAX_UPLOAD_COUNT:
        raise HTTPException(status_code=400, detail=f"最多上传 {settings.MAX_UPLOAD_COUNT} 张照片")
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    validated: list[str] = []
    for url in images:
        m = DATA_URL_RE.match(url)
        if not m:
            raise HTTPException(status_code=400, detail="不支持的图片格式，仅支持 JPG/PNG")
        payload_len = len(url) - m.end()
        approx_bytes = int(payload_len * 3 / 4)
        if approx_bytes > max_bytes:
            raise HTTPException(status_code=400, detail=f"图片超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")
        validated.append(url)
    return validated


@router.post("/api/agent/chat", response_model=AgentChatResponse)
async def agent_chat(payload: AgentChatRequest) -> AgentChatResponse:
    """无状态推理：意图路由 → chat/recommend 分支 → 返回回复与意图。"""
    message = payload.message.strip()
    images = _validate_images(payload.images)
    if not message and not images:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    try:
        result = await run_chat(message, images, payload.history)
    except HTTPException:
        # 校验类异常保持原状（当前 run_chat 内部不抛，仅防御性保留）
        raise
    except (openai.APIError, httpx.HTTPError, RuntimeError) as exc:
        # 仅"LLM 未配置/调用失败"映射 502（spec v2 §4.1）：model_repo 缺 API Key 抛
        # RuntimeError，openai/httpx 为提供方调用失败。其余编码类异常（KeyError/TypeError
        # 等）不再被 502 掩盖，交给 FastAPI 兜底记 500 —— 评审 I2 收窄 + 可观测性
        logger.exception("Agent 推理失败（LLM 未配置或调用失败）: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    return AgentChatResponse(reply=result["reply"], intent=result["intent"])
