"""向量存储：Chroma 持久化，实体向量 + chunk 向量，余弦检索。

职责（见 app/knowledge/IMPLEMENTATION.md 5.2）：
- 实体向量：id = 实体编号 eid，与 GraphBuilder 图节点通过 eid 关联；
- chunk 向量：id = document_id#index，metadata 记录来源文档；
- 检索：余弦相似度 top-k，返回命中实体/chunk + 元数据 + 分数。

设计原则：
- 只负责「存取与检索」，不生成 embedding（embedding 由 model_repo 提供）；
- 增量幂等：upsert_chunks 先按 document_id 删除旧块再插入；
- 本地持久化（Chroma PersistentClient），MVP 单实例够用。
"""
from __future__ import annotations

import chromadb

from app.knowledge.config import CHROMA_DIR


class VectorStore:
    """Chroma 向量库（entities + chunks 两个 collection）。"""

    ENTITIES_COLLECTION = "entities"
    CHUNKS_COLLECTION = "chunks"

    def __init__(self, path: str | None = None):
        self._client = chromadb.PersistentClient(path=str(path or CHROMA_DIR))
        # hnsw:sync_threshold 设最小合法值 3（须 > 2）：让 HNSW 索引在进程内即落盘。
        # 默认 1000 时，数据量 < 1000 的索引会留在内存、进程退出不 flush，
        # 导致跨进程查询报 "Error creating hnsw segment reader: Nothing found on disk"。
        self._entities = self._client.get_or_create_collection(
            name=self.ENTITIES_COLLECTION,
            metadata={"hnsw:space": "cosine", "hnsw:sync_threshold": 3},
        )
        self._chunks = self._client.get_or_create_collection(
            name=self.CHUNKS_COLLECTION,
            metadata={"hnsw:space": "cosine", "hnsw:sync_threshold": 3},
        )

    # ------------------------------------------------------------------
    # 实体向量
    # ------------------------------------------------------------------
    def upsert_entities(self, entities: list[dict]) -> None:
        """写入/更新实体向量。

        Args:
            entities: 元素形如 {"eid": int, "name": str, "type": str,
                "dimension": str, "description": str, "embedding": list[float]}。
        """
        if not entities:
            return
        self._entities.upsert(
            ids=[str(e["eid"]) for e in entities],
            embeddings=[e["embedding"] for e in entities],
            documents=[e["name"] for e in entities],
            metadatas=[
                {
                    "name": e["name"],
                    "type": e.get("type", ""),
                    "dimension": e.get("dimension", ""),
                    "description": e.get("description", ""),
                }
                for e in entities
            ],
        )

    def query_entities(
        self, embedding: list[float], top_k: int = 3, dimension: str | None = None
    ) -> list[dict]:
        """余弦检索最相似实体。

        Args:
            embedding: 查询向量。
            top_k: 返回数量。
            dimension: 若指定，仅检索同维度实体（跨维度不参与比对）。

        Returns:
            元素形如 {"eid", "name", "type", "dimension", "description", "score"}，
            按相似度降序（score 为 cosine distance，越小越相似）。
        """
        where = {"dimension": dimension} if dimension else None
        # 先取匹配数量，避免 n_results 超过实际匹配数
        if where:
            matching = self._entities.get(where=where).get("ids", [])
        else:
            matching = self._entities.get().get("ids", [])
        total = len(matching)
        if total == 0:
            return []
        res = self._entities.query(
            query_embeddings=[embedding],
            n_results=min(top_k, total),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return [
            {
                "eid": int(res["ids"][0][i]),
                "name": res["documents"][0][i],
                "type": (res["metadatas"][0][i] or {}).get("type", ""),
                "dimension": (res["metadatas"][0][i] or {}).get("dimension", ""),
                "description": (res["metadatas"][0][i] or {}).get("description", ""),
                "score": res["distances"][0][i],
            }
            for i in range(len(res["ids"][0]))
        ]

    def delete_entity(self, eid: int) -> None:
        """删除单个实体向量（供实体归并后清理被合并实体的向量，预留 L3 用）。"""
        self._entities.delete(ids=[str(eid)])

    # ------------------------------------------------------------------
    # chunk 向量
    # ------------------------------------------------------------------
    def upsert_chunks(self, document_id: str, chunks: list[dict]) -> None:
        """写入某篇文档的 chunk 向量（先删旧块再插入，保证增量幂等）。

        Args:
            document_id: 文档相对路径（如 "body-shape/梨形.md"）。
            chunks: 元素形如 {"content": str, "embedding": list[float]}。
        """
        self._chunks.delete(where={"document_id": document_id})
        if not chunks:
            return
        self._chunks.upsert(
            ids=[f"{document_id}#{i}" for i in range(len(chunks))],
            embeddings=[c["embedding"] for c in chunks],
            documents=[c["content"] for c in chunks],
            metadatas=[
                {"document_id": document_id, "index": i}
                for i in range(len(chunks))
            ],
        )

    def query_chunks(self, embedding: list[float], top_k: int = 3) -> list[dict]:
        """余弦检索最相似文本块。

        Returns:
            元素形如 {"id", "content", "document_id", "score"}，按相似度降序。
        """
        total = self._chunks.count()
        if total == 0:
            return []
        res = self._chunks.query(
            query_embeddings=[embedding],
            n_results=min(top_k, total),
            include=["documents", "metadatas", "distances"],
        )
        return [
            {
                "id": res["ids"][0][i],
                "content": res["documents"][0][i],
                "document_id": (res["metadatas"][0][i] or {}).get("document_id", ""),
                "score": res["distances"][0][i],
            }
            for i in range(len(res["ids"][0]))
        ]

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def counts(self) -> dict:
        """返回两个 collection 的向量数量。"""
        return {"entities": self._entities.count(), "chunks": self._chunks.count()}
