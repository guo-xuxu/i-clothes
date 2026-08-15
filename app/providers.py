"""模型提供方封装。

所有大模型客户端的构造集中在此，其他模块只从这里获取模型实例，
不直接构造。新增/替换模型（如后续接入 DeepSeek）只需修改本文件。
"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings


@lru_cache(maxsize=2)
def get_qianwen_vl() -> ChatOpenAI:
    """返回通义千问多模态模型（通过 OpenAI 兼容端点）。

    Raises:
        RuntimeError: API Key 未配置。
    """
    if not settings.QIANWEN_API_KEY:
        raise RuntimeError("QIANWEN_API_KEY 未配置，请在 .env 中设置")

    return ChatOpenAI(
        model=settings.QIANWEN_MODEL,
        api_key=settings.QIANWEN_API_KEY,
        base_url=settings.QIANWEN_BASE_URL,
        temperature=0.7,
        timeout=60,
    )


# 后续版本：DeepSeek 识别/生图模型
@lru_cache(maxsize=2)
def get_deepseek() -> ChatOpenAI:
    if not settings.DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.7,
        timeout=60,
    )
