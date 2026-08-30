"""实体归并判定解析单测（mock DeepSeek，不花钱）。"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.knowledge.build import entity_merger as em  # noqa: E402
from app.repositories.model_repo import ModelRepository  # noqa: E402


def test_parse_judgement_valid():
    j = em.parse_judgement('{"merge": true, "canonical_name": "梨形身材", "reason": "同义"}')
    assert j is not None
    assert j.merge is True
    assert j.canonical_name == "梨形身材"


def test_parse_judgement_no_merge():
    j = em.parse_judgement('{"merge": false, "canonical_name": "", "reason": "不同义"}')
    assert j is not None
    assert j.merge is False


def test_parse_judgement_invalid_none():
    assert em.parse_judgement("不是JSON") is None
    assert em.parse_judgement("") is None


def test_judge_calls_model(monkeypatch):
    class FakeDs:
        def invoke(self, messages):
            return SimpleNamespace(content=(
                '{"merge": false, "canonical_name": "", "reason": "上下位关系不合并"}'))

    merger = em.EntityMerger(
        builder=object(), normalizer=object(), vector_store=object(), embedder=object(),
        judge_model=FakeDs(),
    )
    j = merger._judge("毛衣", "服装单品", "描述",
                      [{"name": "保暖毛衣", "type": "服装单品", "description": "x"}])
    assert j is not None
    assert j.merge is False


def test_resolve_fails_open_on_judge_error():
    """判定模型异常 → resolve 降级为新建（不中断整篇导入）。"""
    import networkx as nx

    class BoomDs:
        def invoke(self, messages):
            raise RuntimeError("provider error")

    class FakeNormalizer:
        def normalize(self, name):
            return name

    class FakeVectorStore:
        def counts(self):
            return {"entities": 1}

        def query_entities(self, vec, top_k, dimension=None):
            # 返回低于阈值的候选，确保走到 LLM 判定
            return [{"name": "保暖毛衣", "score": 0.1, "type": "服装单品", "description": "x"}]

    class FakeEmbedder:
        def embed_query(self, text):
            return [0.1, 0.2]

    g = nx.DiGraph()
    g.add_node("已有节点", eid=1)
    builder = type("B", (), {"graph": g})()

    merger = em.EntityMerger(
        builder=builder, normalizer=FakeNormalizer(), vector_store=FakeVectorStore(),
        embedder=FakeEmbedder(), judge_model=BoomDs(),
    )
    decision = merger.resolve("毛衣", "服装单品", "描述", "面料与材质")
    assert decision.is_new is True
    assert decision.canonical == "毛衣"
