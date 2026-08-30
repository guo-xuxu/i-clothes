"""混合召回：图遍历 + 向量 top-k → 拼接【参考知识】上下文（fail-open）。

职责（见 docs/RAG知识图谱规划.md §3.3）：
1. 图路：改写查询 + 关键检索词 → 节点子串匹配实体 → 图遍历 1-2 跳 → 关系上下文；
2. 向量路：改写查询 embedding → Chroma chunk top-k（距离阈值 + 维度过滤）→ 文本上下文；
3. 维度过滤：intent/照片类型决定维度白名单，chunk 按来源文档维度过滤；
4. 两路拼接为 rag_context，注入 recommend_outfit 的 prompt；任一路失败降级，绝不抛异常。
"""
from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache
from pathlib import Path

from app.knowledge.retrieve import graph_store
from app.knowledge.config import DATA_DIR, GRAPH_HOPS, GRAPH_PATH, VECTOR_TOP_K
from app.knowledge.retrieve.vector_store import VectorStore
from app.repositories.model_repo import ModelRepository
logger = logging.getLogger(__name__)

MAX_GRAPH_EDGES = 10
CHUNK_DISTANCE_THRESHOLD = 0.5  # Chroma 余弦距离，越小越相似；>0.5 视为不相关
CHUNK_TOP_K_MULTIPLIER = 2      # 先取 top_k*2 再过滤，留出维度过滤余量

# 照片类型 → 检索维度倾向（spec D4：影响检索维度）
PHOTO_TYPE_DIMENSION_HINTS = {
    "full_body": {"身材比例与修饰", "廓形与版型"},
    "half_body": {"配饰与点缀", "图案与纹理"},
    "head_shot": {"肤色与个人色彩"},
}


def dimension_allowlist(dimension: str, photo_type: str) -> set[str]:
    """由 query_analyzer 的维度 + 照片类型推导检索维度白名单（空集 = 不过滤）。"""
    dims: set[str] = set()
    if dimension and dimension != "general":
        dims.add(dimension)
    dims |= PHOTO_TYPE_DIMENSION_HINTS.get(photo_type, set())
    return dims


def format_graph_context(edges: list[dict], limit: int = MAX_GRAPH_EDGES) -> str:
    return "\n".join(
        f"- {e['source']} → {e['relation']} → {e['target']}" for e in edges[:limit]
    )


def format_chunk_context(hits: list[dict]) -> str:
    """chunk 命中 → 文本（来源用文档名 stem，正文截断 150 字）。"""
    lines = []
    for h in hits:
        doc_id = h.get("document_id") or ""
        stem = Path(doc_id).stem if doc_id else ""
        prefix = f"（{stem}）" if stem else ""
        content = (h.get("content") or "").replace("\n", " ")[:150]
        lines.append(f"- {prefix} {content}".strip())
    return "\n".join(lines)


def filter_by_dimension(
    hits: list[dict], doc_to_dim: dict[str, str], allow_dims: set[str]
) -> list[dict]:
    """按来源文档维度过滤；白名单为空时不过滤。"""
    if not allow_dims:
        return hits
    return [h for h in hits if doc_to_dim.get(h.get("document_id")) in allow_dims]


@lru_cache(maxsize=1)
def _doc_dimension_map() -> dict[str, str]:
    """登记表（processed_docs.json）→ {文档相对路径: 维度中文名}，构建后自动可见（进程内缓存）。"""
    path = DATA_DIR / "processed_docs.json"
    try:
        reg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {p: v.get("dimension", "") for p, v in reg.get("documents", {}).items()}


def _embed_query(query: str) -> list[float]:
    """同步 embedding 调用（供 asyncio.to_thread 包装）。"""
    embedder = ModelRepository.get_embedding()
    return embedder.embed_query(query)


_vector_store: VectorStore | None = None


def _get_vector_store() -> VectorStore:
    """进程内复用的 Chroma 向量库单例（懒创建）。"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


async def retrieve(
    query: str,
    keywords: list[str] | None = None,
    dimension: str = "",
    photo_type: str = "unknown",
    top_k: int = VECTOR_TOP_K,
    max_hops: int = GRAPH_HOPS,
    graph_path: str | Path = GRAPH_PATH,
    vector_store: VectorStore | None = None,
) -> str:
    """图谱+向量混合召回 → 【参考知识】文本；任一环节失败降级，绝不抛异常。

    Args:
        query: 改写后的检索查询。
        keywords: 改写提取的关键检索词。
        dimension: 知识维度（query_analyzer 输出）。
        photo_type: 照片类型（影响检索维度白名单）。
        top_k: 向量 top-k。
        max_hops: 图遍历最大跳数。
        graph_path: 图文件路径（默认 GRAPH_PATH，测试可注入）。
        vector_store: 向量库实例（默认进程单例；测试可注入 fake）。
    """
    query = (query or "").strip()
    if not query or not graph_store.is_ready(graph_path):
        return ""

    parts: list[str] = []

    # 图路
    entities = graph_store.query_entities(query, keywords, graph_path)
    edges = graph_store.collect_neighbors(entities, max_hops, graph_path)
    if edges:
        parts.append(format_graph_context(edges))

    # 向量路（失败降级为仅图路）
    try:
        vec = await asyncio.to_thread(_embed_query, query)
        if vec:
            store = vector_store or _get_vector_store()
            hits = store.query_chunks(vec, top_k=top_k * CHUNK_TOP_K_MULTIPLIER)
            hits = [h for h in hits if h["score"] < CHUNK_DISTANCE_THRESHOLD]
            allow = dimension_allowlist(dimension, photo_type)
            hits = filter_by_dimension(hits, _doc_dimension_map(), allow)
            if hits:
                parts.append(format_chunk_context(hits[:top_k]))
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.warning("向量召回降级（仅用图谱上下文）: %s", exc)

    if not parts:
        return ""
    return "【参考知识】\n" + "\n".join(parts)
