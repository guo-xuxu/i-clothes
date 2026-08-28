"""LLM 模型仓库：集中构造并复用所有大模型客户端。

从原 `app/providers.py` 迁入。新增/替换模型（如 DeepSeek 识别、生图）
只需修改本文件，其他模块从 `ModelRepository` 获取实例。
"""
from functools import lru_cache

from langchain_openai import ChatOpenAI
from openai import OpenAI

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

    @staticmethod
    @lru_cache(maxsize=1)
    def get_deepseek_extractor() -> ChatOpenAI:
        """返回知识图谱三元组抽取专用模型（低温度 + JSON 输出）。

        与 get_deepseek 的区别：
        - temperature=0：抽取是结构化任务，需要确定性输出，避免发散；
        - timeout 更长：离线批量抽取可能耗时较久；
        - 建议配合 prompt 要求输出 JSON，或由调用方传 response_format。

        Raises:
            RuntimeError: API Key 未配置。
        """
        if not settings.DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")

        return ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=0,
            timeout=120,
        )

    @staticmethod
    @lru_cache(maxsize=1)
    def get_embedding() -> "QianwenEmbedder":
        """返回通义千问 embedding（text-embedding-v3，用于知识库向量化）。

        直接用 openai 客户端封装而非 langchain OpenAIEmbeddings：
        当前 langchain-openai 版本会把 embedding 的 input 包装成
        {"contents": ...}，导致千问兼容端点报 400（input.contents 格式错误）。

        Raises:
            RuntimeError: API Key 未配置。
        """
        if not settings.QIANWEN_API_KEY:
            raise RuntimeError("QIANWEN_API_KEY 未配置，请在 .env 中设置")

        return QianwenEmbedder()


class QianwenEmbedder:
    """千问 embedding 封装（openai 客户端直连）。

    提供 embed_query / embed_documents 两个方法，接口对齐 langchain
    OpenAIEmbeddings，供 import_all / retriever 调用。
    """

    def __init__(self):
        self._client = OpenAI(
            api_key=settings.QIANWEN_API_KEY,
            base_url=settings.QIANWEN_BASE_URL,
        )
        self._model = settings.QIANWEN_EMBEDDING_MODEL

    def embed_query(self, text: str) -> list[float]:
        """单个文本 embedding。"""
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文本 embedding（按输入顺序返回）。

        千问 text-embedding-v3 单次 batch 上限 10，故自动分批请求后合并。
        """
        if not texts:
            return []
        batch_size = 10
        results: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self._client.embeddings.create(model=self._model, input=batch)
            ordered = sorted(resp.data, key=lambda d: d.index)
            results.extend(d.embedding for d in ordered)
        return results
