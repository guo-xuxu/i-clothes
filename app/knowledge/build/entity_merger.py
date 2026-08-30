"""实体归并：边抽边并（L1/L2 归一 + 同维度向量候选 + LLM 判定）。

职责（见 app/knowledge/IMPLEMENTATION.md 3.2、3.3）：
- 对每个新抽取的实体，判定它应归并到图里哪个已有节点；
- 判定顺序（成本从低到高）：
  1. L1 字符串归一 + L2 同义词典（EntityNormalizer，零成本）；
  2. 同维度向量检索 top-k，distance < 阈值 的作为「疑似同义」候选；
  3. 只对疑似候选调 LLM 判定「是否同义、归并到谁」。
- 归并联动：返回规范名 + 别名（由 import_all 注册映射、补别名、复用 eid）。

设计原则：
- 不做全量集中聚类，只做「新实体 vs 已有实体」的增量归并；
- 向量检索限定同维度（消歧靠维度标签，跨维度不参与比对）；
- LLM 判定 1 个新实体 vs 多个候选，输出简短 JSON（langchain ChatOpenAI + 手动解析）。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ValidationError

from app.knowledge.build.entity_normalizer import EntityNormalizer
from app.knowledge.config import MERGE_THRESHOLD, MERGE_TOP_K
from app.knowledge.retrieve.vector_store import VectorStore
from app.repositories.model_repo import ModelRepository

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.S)


# ---------------------------------------------------------------------------
# LLM 判定输出模型（简短）
# ---------------------------------------------------------------------------
class MergeJudgement(BaseModel):
    """实体归并判定结果。"""

    merge: bool = Field(description="是否将新实体合并到某个候选实体")
    canonical_name: str = Field(
        description="若 merge=true，填目标候选实体的名称（须为候选列表中的名称）；否则填空字符串"
    )
    reason: str = Field(description="一句话说明判定理由")


# 归并判定提示词（要求输出简短 JSON）。
_MERGE_PROMPT = """你是穿搭知识图谱的实体归并判定器。判断「新实体」是否与某个「候选实体」是同一概念（同义），若是则应合并为同一个节点。

新实体：
- 名称：{name}
- 类型：{type}
- 描述：{description}

候选实体列表（JSON，可能为空）：
{candidates}

判定规则：
1. 只有「同义 / 同一概念」才合并，例如「梨型身材」与「梨形身材」、「西服」与「西装」。
2. 上下位关系不合并（如「包袋」与「通勤包」是包含关系，不是同义）。
3. 若新实体与某个候选同义：merge=true，canonical_name 填该候选的名称。
4. 若都不相同：merge=false，canonical_name 填空字符串。
5. reason 用一句话说明理由即可，不要展开。

只输出 JSON，不要任何多余文字。
"""


def parse_judgement(raw: str) -> MergeJudgement | None:
    """解析 LLM 输出为 MergeJudgement；失败返回 None（fail-open）。"""
    if not raw:
        return None
    m = _JSON_RE.search(raw)
    if not m:
        return None
    try:
        return MergeJudgement(**json.loads(m.group(0)))
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("归并判定 JSON 解析失败: %.120s (%s)", raw, exc)
        return None


@dataclass
class MergeDecision:
    """一次实体归并解析的结果。"""

    canonical: str                # 最终规范名（应入图的节点名）
    aliases: list[str] = field(default_factory=list)  # 需记入 canonical 节点的别名
    is_new: bool = False          # True = canonical 是图里新节点，需新建并 embedding


class EntityMerger:
    """增量实体归并器（边抽边并）。

    用法：
        merger = EntityMerger(builder, normalizer, vector_store, embedder)
        decision = merger.resolve(name, type, description, dimension, source)
        # decision.canonical 即该实体应归并到的节点名
    """

    def __init__(
        self,
        builder,
        normalizer: EntityNormalizer,
        vector_store: VectorStore,
        embedder,
        *,
        judge_model=None,
        threshold: float = MERGE_THRESHOLD,
        top_k: int = MERGE_TOP_K,
    ):
        self.builder = builder
        self.normalizer = normalizer
        self.vector_store = vector_store
        self.embedder = embedder
        self.threshold = threshold
        self.top_k = top_k
        self._judge_model = judge_model if judge_model is not None else ModelRepository.get_deepseek()

    # ------------------------------------------------------------------
    # 归并解析
    # ------------------------------------------------------------------
    def resolve(
        self,
        name: str,
        type: str = "",
        description: str = "",
        dimension: str = "",
        source: str = "",
    ) -> MergeDecision:
        """解析一个实体应归并到的规范名。

        判定顺序：
        1. L1/L2 归一（normalizer.normalize）；
        2. 图里已有规范名 → 直接复用；
        3. 无可比对象（空图/空向量库）→ 新建；
        4. 同维度向量检索 top_k，distance < threshold 的候选送 LLM；
        5. LLM 判定合并 → 归并到候选；否则新建。

        Args:
            name: 实体原始名。
            type: 实体类型。
            description: 实体描述。
            dimension: 所属维度（用于向量检索的同维度过滤）。
            source: 来源文档（当前未直接使用，保留扩展）。

        Returns:
            MergeDecision。
        """
        raw = (name or "").strip()
        if not raw:
            return MergeDecision(raw, [], True)

        canonical = self.normalizer.normalize(raw)
        aliases: list[str] = []
        if canonical != raw:
            aliases.append(raw)  # L1/L2 归一产生的别名

        # 1. 图里已有规范名 → 复用（add_entity 稍后补 sources）
        if self.builder.graph.has_node(canonical):
            return MergeDecision(canonical, aliases, False)

        # 2. 无可比对象 → 新建
        if self.builder.graph.number_of_nodes() == 0 or self.vector_store.counts()["entities"] == 0:
            return MergeDecision(canonical, aliases, True)

        # 3. 同维度向量检索
        text = f"{canonical}：{description}" if description else canonical
        try:
            vec = self.embedder.embed_query(text)
            candidates = self.vector_store.query_entities(
                vec, top_k=self.top_k, dimension=dimension
            )
        except Exception as exc:  # noqa: BLE001 - 向量检索失败降级为新建
            logger.warning("向量检索失败 %s: %s", raw, exc)
            return MergeDecision(canonical, aliases, True)

        close = [c for c in candidates if c["score"] < self.threshold and c["name"] != canonical]
        if not close:
            return MergeDecision(canonical, aliases, True)

        # 4. LLM 判定（1 个新实体 vs 所有低于阈值的候选）
        try:
            judgement = self._judge(canonical, type, description, close)
        except Exception as exc:  # noqa: BLE001 - 判定失败降级为不合并
            logger.warning("LLM 归并判定失败 %s: %s", raw, exc)
            return MergeDecision(canonical, aliases, True)

        if judgement and judgement.merge and judgement.canonical_name and judgement.canonical_name != canonical:
            if canonical not in aliases:
                aliases.append(canonical)  # 被归并掉的 canonical 名记为别名
            return MergeDecision(judgement.canonical_name, aliases, False)

        return MergeDecision(canonical, aliases, True)

    def _judge(self, name: str, type: str, description: str, candidates: list[dict]) -> MergeJudgement | None:
        """调用 LLM 判定新实体是否与某个候选同义（DeepSeek 结构化 JSON）。"""
        cand_json = json.dumps(
            [
                {"name": c["name"], "type": c.get("type", ""), "description": c.get("description", "")}
                for c in candidates
            ],
            ensure_ascii=False,
        )
        prompt = _MERGE_PROMPT.format(
            name=name, type=type, description=description, candidates=cand_json
        )
        response = self._judge_model.invoke([HumanMessage(content=prompt)])
        return parse_judgement(response.content)
