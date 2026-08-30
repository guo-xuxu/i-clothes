"""图谱存储单测：加载/就绪/实体匹配/图遍历（用临时 graph.json，不依赖真实数据）。"""
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.knowledge.retrieve import graph_store  # noqa: E402


def _write_graph(tmp_path: Path, triples: list[dict]) -> Path:
    """把三元组写成 graph.json 格式（nodes/edges 结构，与 GraphBuilder.to_dict 一致）。"""
    nodes = {}
    for h, _, t in triples:
        nodes.setdefault(h, {"id": h})
        nodes.setdefault(t, {"id": t})
    edges = [
        {"head": h, "relation": r, "tail": t}
        for h, r, t in triples
    ]
    data = {"meta": {"entity_count": len(nodes), "edge_count": len(edges)},
            "nodes": list(nodes.values()), "edges": edges}
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


TINY = [
    ("婚礼", "适合", "正式"),
    ("正式", "可选单品", "西装"),
    ("正式", "可选单品", "礼服"),
    ("通勤", "适合", "衬衫"),
]


def test_load_and_ready(tmp_path):
    p = _write_graph(tmp_path, TINY)
    graph_store.reload_graph()
    assert graph_store.is_ready(p) is True
    g = graph_store.get_graph(p)
    assert g.number_of_nodes() == 6
    assert g.number_of_edges() == 4


def test_not_ready_when_missing(tmp_path):
    graph_store.reload_graph()
    assert graph_store.is_ready(tmp_path / "nope.json") is False


def test_query_entities_text_and_keywords(tmp_path):
    p = _write_graph(tmp_path, TINY)
    graph_store.reload_graph()
    assert graph_store.query_entities("参加婚礼穿什么", None, p) == {"婚礼"}
    # keywords 兜底：改写的关键检索词也能命中（"西服"→ 图中"西装"需别名，这里验证 keywords 通道）
    assert graph_store.query_entities("随便聊聊", ["礼服"], p) == {"礼服"}
    assert graph_store.query_entities("随便聊聊", [], p) == set()


def test_collect_neighbors_one_hop(tmp_path):
    p = _write_graph(tmp_path, TINY)
    graph_store.reload_graph()
    edges = graph_store.collect_neighbors({"婚礼"}, max_hops=1, path=p)
    assert {"source": "婚礼", "relation": "适合", "target": "正式"} in edges
    # 入边：正式 → 礼服 不应出现在婚礼的 1 跳内
    targets = {e["target"] for e in edges}
    assert targets == {"正式"}


def test_collect_neighbors_two_hops(tmp_path):
    p = _write_graph(tmp_path, TINY)
    graph_store.reload_graph()
    edges = graph_store.collect_neighbors({"婚礼"}, max_hops=2, path=p)
    targets = {e["target"] for e in edges}
    assert {"正式", "西装", "礼服"} <= targets


def test_collect_neighbors_isolated(tmp_path):
    p = _write_graph(tmp_path, [("孤立实体", "属于", "孤立实体")])
    graph_store.reload_graph()
    edges = graph_store.collect_neighbors({"孤立实体"}, max_hops=2, path=p)
    assert len(edges) == 1
