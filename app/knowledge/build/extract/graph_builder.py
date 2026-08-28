"""知识图谱构建（阶段 3）：三元组增量合并进 networkx 有向图。

职责（见 docs/RAG知识图谱规划.md 3.2）：
- 输入阶段 2 产出的三元组列表，增量合并进一张 networkx 图；
- 实体规范化（同义合并：如「西服/西装」归一到规范名）；
- 边去重（相同 head-relation-tail 只保留一条）；
- 支持逐批 add（增量添加），而非每次全量重建。

设计原则：
- 纯代码逻辑（networkx），不调用 LLM；
- 图对象可序列化（graph.json）供 retrieve/graph_store 加载；
- 实体规范化规则以配置形式注入，便于扩展。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from app.knowledge.config import GRAPH_PATH

logger = logging.getLogger(__name__)


@dataclass
class GraphBuilder:
    """知识图谱增量构建器。

    用法：
        builder = GraphBuilder()
        builder.add_triples(triples)          # 增量合并一批三元组
        builder.add_triple("上松下紧", "相关", "阔腿裤")
        builder.save()                        # 序列化到 graph.json

    Attributes:
        graph: 内部维护的 networkx 有向图（DiGraph）。
        entity_aliases: 同义实体映射 {别名: 规范名}。
    """

    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    entity_aliases: dict[str, str] = field(default_factory=dict)
    _entity_ids: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _next_id: int = field(default=1, init=False, repr=False)

    def __post_init__(self) -> None:
        """初始化图元数据（构建信息）。"""
        if not self.graph.graph:
            self.graph.graph["schema"] = "triple"
            self.graph.graph["entity_count"] = 0
            self.graph.graph["edge_count"] = 0

    # ------------------------------------------------------------------
    # 实体规范化
    # ------------------------------------------------------------------
    def register_alias(self, alias: str, canonical: str) -> None:
        """注册一对同义实体映射：alias → canonical。

        Args:
            alias: 别名（如「西服」）。
            canonical: 规范名（如「西装」）。
        """
        alias, canonical = alias.strip(), canonical.strip()
        if alias and canonical:
            self.entity_aliases[alias] = canonical

    def register_aliases(self, mapping: dict[str, str]) -> None:
        """批量注册同义实体映射。"""
        for alias, canonical in mapping.items():
            self.register_alias(alias, canonical)

    def canonicalize(self, entity: str) -> str:
        """将实体归一化到规范名。

        规则：
        1. 直接命中映射（含自身是别名）→ 返回规范名；
        2. 多级别名（规范名本身又是别名）→ 递归上溯，防环；
        3. 无映射 → 原样返回。

        Args:
            entity: 待归一化的实体。

        Returns:
            规范名。
        """
        current = entity.strip()
        seen: set[str] = set()
        while current in self.entity_aliases and current not in seen:
            seen.add(current)
            current = self.entity_aliases[current]
        return current

    # ------------------------------------------------------------------
    # 实体编号
    # ------------------------------------------------------------------
    def get_entity_id(self, name: str) -> int | None:
        """查询实体编号（内存 hashmap，O(1)）。

        Args:
            name: 实体名（规范名）。

        Returns:
            该实体的编号 eid；不存在返回 None。
        """
        return self._entity_ids.get(name)

    def ensure_node(self, name: str) -> int:
        """确保节点存在，并分配/复用实体编号（公开，孤立实体也可调用）。

        Returns:
            该实体的编号 eid。
        """
        eid = self._entity_ids.get(name)
        if not self.graph.has_node(name):
            if eid is None:
                eid = self._next_id
                self._entity_ids[name] = eid
                self._next_id += 1
            self.graph.add_node(
                name,
                eid=eid,
                type="",
                description="",
                dimension="",
                sources=[],
                aliases=[],
            )
            self.graph.graph["entity_count"] += 1
        return eid

    def add_entity(
        self,
        name: str,
        *,
        type: str = "",
        description: str = "",
        dimension: str = "",
        source: str = "",
    ) -> int:
        """添加/更新实体节点（含完整属性），返回 eid。

        属性合并策略：
        - type/description/dimension：首次出现时记录，后续出现保留首次值；
        - sources：累加去重（同一实体来自多篇文档）；
        - aliases：预留空列表，供后续实体归并时填充同义词。

        Args:
            name: 实体名（会自动 canonicalize）。
            type: 实体类型。
            description: 实体描述。
            dimension: 所属维度中文名。
            source: 来源文档（相对路径）。

        Returns:
            该实体的编号 eid。
        """
        name = self.canonicalize(name)
        eid = self.ensure_node(name)
        node = self.graph.nodes[name]

        if not node.get("type") and type:
            node["type"] = type
        if not node.get("description") and description:
            node["description"] = description
        if not node.get("dimension") and dimension:
            node["dimension"] = dimension

        if source:
            sources = node.setdefault("sources", [])
            if source not in sources:
                sources.append(source)

        node.setdefault("aliases", [])
        return eid

    # ------------------------------------------------------------------
    # 增量添加
    # ------------------------------------------------------------------
    def add_triple(
        self,
        head: str,
        relation: str,
        tail: str,
        strength: int | None = None,
        keywords: list[str] | None = None,
    ) -> bool:
        """增量添加一条三元组（含规范化与去重）。

        Args:
            head: 头实体。
            relation: 关系。
            tail: 尾实体。
            strength: 关系强度（可选，作为边属性存储）。
            keywords: 关系关键词列表（可选，作为边属性存储）。

        Returns:
            True 表示新增了节点或边；False 表示该边已存在（去重跳过）。
        """
        h = self.canonicalize(head)
        r = relation.strip()
        t = self.canonicalize(tail)
        if not h or not r or not t:
            return False
        # 自环过滤：实体归并后 head/tail 可能归一到同一节点（如「A型体型 --相似--> 梨形身材」
        # 归并成「梨形身材 --相似--> 梨形身材」），自环无信息量且污染图遍历，直接跳过。
        if h == t:
            return False

        self.ensure_node(h)
        self.ensure_node(t)

        # 边去重：同 head-relation-tail 只保留一条
        if self.graph.has_edge(h, t) and self.graph.get_edge_data(h, t).get("relation") == r:
            return False

        # 若已存在 (h, t) 边但关系不同，作为多重关系累加进 relation 列表
        if self.graph.has_edge(h, t):
            existing = self.graph.get_edge_data(h, t)
            rels = existing.get("relations", [existing.get("relation")])
            if r not in rels:
                rels.append(r)
                self.graph[h][t]["relations"] = rels
            return True

        edge_attrs: dict = {"relation": r}
        if strength is not None:
            edge_attrs["strength"] = strength
        if keywords:
            edge_attrs["keywords"] = keywords

        self.graph.add_edge(h, t, **edge_attrs)
        self.graph.graph["edge_count"] += 1
        return True

    def add_triples(self, triples: list[dict]) -> int:
        """批量增量添加三元组。

        Args:
            triples: 三元组列表，每个元素形如
                {"head","relation","tail"}，可选 "strength"、"keywords"。

        Returns:
            实际新增的（边或节点）数量。
        """
        added = 0
        for t in triples:
            if not isinstance(t, dict):
                continue
            if self.add_triple(
                t.get("head", ""),
                t.get("relation", ""),
                t.get("tail", ""),
                strength=t.get("strength"),
                keywords=t.get("keywords"),
            ):
                added += 1
        return added

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """将图导出为可 JSON 序列化的字典（节点 + 边 + 元数据）。"""
        nodes = [
            {"id": n, **self.graph.nodes[n]}
            for n in self.graph.nodes()
        ]
        edges = [
            {"head": h, "tail": t, **self.graph.edges[h, t]}
            for h, t in self.graph.edges()
        ]
        return {
            "meta": dict(self.graph.graph),
            "nodes": nodes,
            "edges": edges,
        }

    def save(self, path: str | Path = GRAPH_PATH) -> None:
        """将图序列化到 graph.json。

        使用 networkx 的 node_link_data 之外的简化格式（to_dict），
        保证节点/边字段清晰，供 retrieve/graph_store 加载。

        Args:
            path: 落盘路径；默认 config.GRAPH_PATH。
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        import json

        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("图谱已落盘: %s（%d 节点, %d 边）",
                    target, self.graph.number_of_nodes(), self.graph.number_of_edges())

    def load(self, path: str | Path = GRAPH_PATH) -> "GraphBuilder":
        """从 graph.json 加载图（用于增量构建：先载入已有图，再追加新三元组）。

        Args:
            path: graph.json 路径。

        Returns:
            self，支持链式调用。
        """
        import json

        target = Path(path)
        if not target.is_file():
            logger.info("图谱文件不存在，从空图开始: %s", target)
            return self

        data = json.loads(target.read_text(encoding="utf-8"))
        self.graph = nx.DiGraph()
        self.graph.graph.update(data.get("meta", {}))
        self._entity_ids = {}
        self._next_id = 1

        for n in data.get("nodes", []):
            nid = n.get("id")
            if nid is None:
                continue
            self.graph.add_node(nid, **{k: v for k, v in n.items() if k != "id"})
            eid = n.get("eid")
            if eid is not None:
                self._entity_ids[nid] = eid
                self._next_id = max(self._next_id, eid + 1)

        for e in data.get("edges", []):
            h, t = e.get("head"), e.get("tail")
            if not h or not t:
                continue
            self.graph.add_edge(h, t, **{k: v for k, v in e.items() if k not in ("head", "tail")})

        # 重算计数，比信任 meta 更可靠
        self.graph.graph["entity_count"] = self.graph.number_of_nodes()
        self.graph.graph["edge_count"] = self.graph.number_of_edges()
        logger.info(
            "已加载图谱: %s（%d 节点, %d 边）",
            target, self.graph.number_of_nodes(), self.graph.number_of_edges(),
        )
        return self
