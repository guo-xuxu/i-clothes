"""混合召回单测：维度白名单/格式化/维度过滤 + retrieve（mock 图、向量与 embedding）。"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.graph.nodes.retrieve_context import retrieve_context as retriever_node  # noqa: E402
from app.knowledge.retrieve import graph_store, retriever, vector_store  # noqa: E402
from app.repositories.model_repo import ModelRepository  # noqa: E402


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------

def test_dimension_allowlist_general():
    assert retriever.dimension_allowlist("general", "unknown") == set()


def test_dimension_allowlist_dimension_only():
    assert retriever.dimension_allowlist("风格定位", "unknown") == {"风格定位"}


def test_dimension_allowlist_photo_hint_full_body():
    dims = retriever.dimension_allowlist("general", "full_body")
    assert dims == {"身材比例与修饰", "廓形与版型"}


def test_dimension_allowlist_combines():
    dims = retriever.dimension_allowlist("颜色搭配", "head_shot")
    assert "颜色搭配" in dims
    assert "肤色与个人色彩" in dims


def test_format_graph_context():
    edges = [
        {"source": "婚礼", "relation": "适合", "target": "正式"},
        {"source": "正式", "relation": "可选单品", "target": "西装"},
    ]
    text = retriever.format_graph_context(edges)
    assert "婚礼 → 适合 → 正式" in text
    assert "可选单品" in text


def test_format_chunk_context_stem_prefix():
    hits = [{"content": "婚礼建议正式着装", "document_id": "occasion/婚礼着装.md", "score": 0.1}]
    text = retriever.format_chunk_context(hits)
    assert "婚礼着装" in text
    assert "婚礼建议正式着装" in text


def test_filter_by_dimension():
    hits = [
        {"content": "a", "document_id": "color/x.md"},
        {"content": "b", "document_id": "fabric/y.md"},
    ]
    doc_dim = {"color/x.md": "颜色搭配", "fabric/y.md": "面料与材质"}
    filtered = retriever.filter_by_dimension(hits, doc_dim, {"颜色搭配"})
    assert len(filtered) == 1
    assert filtered[0]["content"] == "a"


def test_filter_by_dimension_empty_allow_keeps_all():
    hits = [{"content": "a", "document_id": "color/x.md"}]
    assert len(retriever.filter_by_dimension(hits, {}, set())) == 1


# ---------------------------------------------------------------------------
# retrieve（mock 图/向量/embedding，不触网不花钱）
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_graph(monkeypatch):
    """图就绪 + 固定实体/边。"""
    monkeypatch.setattr(graph_store, "is_ready", lambda path=None: True)
    monkeypatch.setattr(graph_store, "query_entities",
                        lambda text, keywords=None, path=None: {"婚礼"})
    monkeypatch.setattr(graph_store, "collect_neighbors",
                        lambda entities, max_hops=2, path=None: [
                            {"source": "婚礼", "relation": "适合", "target": "正式"}])
    return None


def test_retrieve_empty_when_graph_not_ready(monkeypatch):
    monkeypatch.setattr(graph_store, "is_ready", lambda path=None: False)
    assert asyncio.run(retriever.retrieve("参加婚礼穿什么")) == ""


def test_retrieve_graph_only_when_embedding_fails(fake_graph, monkeypatch):
    def _boom(query):
        raise RuntimeError("embedding 不可用")

    monkeypatch.setattr(ModelRepository, "get_embedding", staticmethod(
        lambda: SimpleNamespace(embed_query=_boom)))

    ctx = asyncio.run(retriever.retrieve("参加婚礼穿什么"))
    assert "婚礼 → 适合 → 正式" in ctx


def test_retrieve_hybrid(fake_graph, monkeypatch):
    class FakeStore:
        def query_chunks(self, vec, top_k):
            return [
                {"content": "婚礼场合适合正式着装", "document_id": "occasion/婚礼着装.md", "score": 0.2},
                {"content": "无关内容", "document_id": "fabric/y.md", "score": 0.9},
            ]

    monkeypatch.setattr(ModelRepository, "get_embedding", staticmethod(
        lambda: SimpleNamespace(embed_query=lambda q: [0.1, 0.2])))
    monkeypatch.setattr(retriever, "_doc_dimension_map",
                        lambda: {"occasion/婚礼着装.md": "场合与季节", "fabric/y.md": "面料与材质"})

    ctx = asyncio.run(retriever.retrieve(
        "参加婚礼穿什么", dimension="场合与季节", vector_store=FakeStore()))
    assert "婚礼 → 适合 → 正式" in ctx       # 图路
    assert "婚礼场合适合正式着装" in ctx      # 向量路（维度过滤后保留）
    assert "无关内容" not in ctx             # score 阈值 + 维度过滤剔除


# ---------------------------------------------------------------------------
# retrieve_context 节点（mock retriever.retrieve）
# ---------------------------------------------------------------------------

def test_node_skips_chat_intent(monkeypatch):
    called = []

    async def _fake(**kwargs):
        called.append(1)
        return "不应调用"

    monkeypatch.setattr(retriever, "retrieve", _fake)

    out = asyncio.run(retriever_node(
        {"intent_detail": "chat", "rewritten_query": "你好呀", "rewrite_keywords": []}))
    assert out["rag_context"] == ""
    assert called == []


def test_node_calls_retriever(monkeypatch):
    async def _fake(query, **kwargs):
        return "【参考知识】\n- 婚礼 → 适合 → 正式"

    monkeypatch.setattr(retriever, "retrieve", _fake)

    out = asyncio.run(retriever_node(
        {"intent_detail": "outfit", "rewritten_query": "婚礼 正装 穿搭",
         "rewrite_keywords": ["婚礼", "正装"], "dimension": "场合与季节",
         "photo_type": "unknown"}))
    assert "婚礼" in out["rag_context"]


def test_node_fails_open(monkeypatch):
    async def _boom(query, **kwargs):
        raise RuntimeError("召回失败")

    monkeypatch.setattr(retriever, "retrieve", _boom)

    out = asyncio.run(retriever_node(
        {"intent_detail": "style", "rewritten_query": "风格", "rewrite_keywords": []}))
    assert out["rag_context"] == ""
