"""LLM 模型仓库：集中构造并复用所有大模型客户端。

从原 `app/providers.py` 迁入。新增/替换模型（如 DeepSeek 识别、生图）
只需修改本文件，其他模块从 `ModelRepository` 获取实例。
"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings
from app.repositories.base import Repository


class ModelRepository(Repository):
    """大模型客户端仓库：每个模型一个获取方法，客户端全局复用。"""

    @staticmethod
    @lru_cache(maxsize=1)
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

    @staticmethod
    @lru_cache(maxsize=1)
    def get_deepseek() -> ChatOpenAI:
        """返回 DeepSeek 模型（后续版本用于单品识别/生图）。

        Raises:
            RuntimeError: API Key 未配置。
        """
        if not settings.DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")

        return ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=0.7,
            timeout=60,
        )
