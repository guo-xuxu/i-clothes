"""图谱存储：加载 graph.json → 内存缓存（只读）+ 在线图遍历。

设计（见 docs/RAG知识图谱规划.md §3.3）：
- 图是构建产物读入内存的只读缓存，不构成跨请求状态，保证 Python 服务无状态；
- 构建完成后调用 reload_graph 刷新缓存；
- 查询：节点名子串匹配（text + 改写关键词双通道）+ 出/入边 1..max_hops 去重遍历。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import networkx as nx

from app.knowledge.config import GRAPH_PATH

DEFAULT_MAX_HOPS = 2


@lru_cache(maxsize=8)
def _load_cached(path: str) -> nx.DiGraph | None:
    """读取 graph.json 并重建 networkx 图（按路径缓存）。"""
    p = Path(path)
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    g = nx.DiGraph()
    for n in data.get("nodes", []):
        nid = n.get("id")
        if nid:
            g.add_node(nid, **{k: v for k, v in n.items() if k != "id"})
    for e in data.get("edges", []):
        h, t = e.get("head"), e.get("tail")
        if h and t:
            g.add_edge(h, t, **{k: v for k, v in e.items() if k not in ("head", "tail")})
    return g


def get_graph(path: str | Path = GRAPH_PATH) -> nx.DiGraph | None:
    """返回内存缓存中的图；文件不存在返回 None。"""
    return _load_cached(str(path))


def reload_graph(path: str | Path = GRAPH_PATH) -> None:
    """清空图缓存（构建/更新后调用）。"""
    _load_cached.cache_clear()


def is_ready(path: str | Path = GRAPH_PATH) -> bool:
    """知识库就绪门槛：graph.json 存在且非空。"""
    g = get_graph(path)
    return g is not None and g.number_of_nodes() > 0


def query_entities(
    text: str,
    keywords: list[str] | None = None,
    path: str | Path = GRAPH_PATH,
) -> set[str]:
    """查询文本/关键词命中的实体（节点名子串匹配，在线零成本实体抽取）。

    Args:
        text: 改写后的查询文本。
        keywords: 改写提取的关键检索词（任一命中即算命中）。
        path: 图文件路径（默认 GRAPH_PATH，测试可注入临时文件）。

    Returns:
        命中的节点名集合。
    """
    g = get_graph(path)
    if g is None:
        return set()
    haystacks = [t for t in [text] + (keywords or []) if t]
    if not haystacks:
        return set()
    return {n for n in g.nodes if n and any(n in h for h in haystacks)}


def collect_neighbors(
    entities: set[str],
    max_hops: int = DEFAULT_MAX_HOPS,
    path: str | Path = GRAPH_PATH,
) -> list[dict]:
    """1..max_hops 跳内的出边+入边（去重），返回 [{"source","relation","target"}]。

    Args:
        entities: 起始实体集合。
        max_hops: 最大跳数。
        path: 图文件路径（测试可注入临时文件）。
    """
    g = get_graph(path)
    if g is None or not entities:
        return []
    seen: set[tuple[str, str, str]] = set()
    result: list[dict] = []
    frontier = set(entities)
    visited = set(entities)
    for _ in range(max_hops):
        nxt: set[str] = set()
        for node in frontier:
            for u, v, d in g.edges(node, data=True):
                key = (u, d.get("relation", ""), v)
                if key not in seen:
                    seen.add(key)
                    result.append({"source": u, "relation": d.get("relation", ""), "target": v})
                if v not in visited:
                    visited.add(v)
                    nxt.add(v)
            for u, _, d in g.in_edges(node, data=True):
                key = (u, d.get("relation", ""), node)
                if key not in seen:
                    seen.add(key)
                    result.append({"source": u, "relation": d.get("relation", ""), "target": node})
                if u not in visited:
                    visited.add(u)
                    nxt.add(u)
        frontier = nxt
        if not frontier:
            break
    return result
