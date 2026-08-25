"""联合抽取（GraphRAG 风格）：一次调用同时产出实体与关系。

职责（见 docs/RAG知识图谱规划.md 3.2）：
- 以「单个 chunk」为输入，调用 DeepSeek 一次完成实体识别 + 关系提取；
- 输出带描述的实体、带强度与关键词的关系、以及内容级关键词；
- 采用分隔符协议（tuple/record/completion）结构化解析，比纯 JSON 更健壮。

设计原则：
- 单次调用（不做实体/关系二次调用），降低延迟与成本；
- 中文输出，实体名保持原文，与下游中文检索/回答对齐；
- 关系有方向（source → target），与 GraphBuilder 的有向图匹配。
"""
from __future__ import annotations

import json
import logging
import re

from app.knowledge.build.text_chunk import TextChunk
from app.knowledge.config import (
    COMPLETION_DELIMITER,
    RECORD_DELIMITER,
    TUPLE_DELIMITER,
)
from app.repositories.model_repo import ModelRepository

logger = logging.getLogger(__name__)

# 联合抽取提示词（GraphRAG 模板中文版）。
_EXTRACT_PROMPT = """-目标-
给定可能与此活动相关的文本文档，从文本中识别出所有实体以及所识别实体之间的所有关系。

-步骤-
1. 识别所有实体。对于每个已识别的实体，提取以下信息：
- entity_name：实体名称，保持原文
- entity_type：根据文本内容提取实体的类型
- entity_description：对实体属性和活动的全面描述
将每个实体格式化为（"entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>）

2. 从步骤 1 中识别的实体中，识别彼此明显相关的所有对（source_entity, target_entity）。
对于每对相关实体，提取以下信息：
- source_entity：源实体的名称，如步骤 1 中所标识
- target_entity：目标实体的名称，如步骤 1 中所标识
- relationship_description：解释为什么你认为源实体和目标实体是相互关联的
- relationship_strength：一个数字分数，表示源实体和目标实体之间关系的强度（1-10）
- relationship_keywords：一个或多个高级关键字，总结关系的总体性质，侧重于概念或主题，而不是具体细节
将每个关系格式化为（"relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_keywords>{tuple_delimiter}<relationship_strength>）

3. 识别概括整篇文章主要概念、主题或主题的高级关键字。这些应该捕捉到文件中存在的总体想法。
将内容级关键字格式化为（"content_keywords"{tuple_delimiter}<high_level_keywords>）

4. 返回中文输出，作为步骤 1 和 2 中识别的所有实体和关系的单个列表。使用 **{record_delimiter}** 作为列表分隔符。

5. 完成后，输出 {completion_delimiter}

文本：
{{text}}
"""

# 记录前缀类型
_ENTITY = "entity"
_RELATIONSHIP = "relationship"
_CONTENT_KEYWORDS = "content_keywords"


class GraphExtractor:
    """联合抽取器（单 chunk 粒度，异步，单次调用）。

    用法：
        extractor = GraphExtractor()
        result = await extractor.extract(chunk)
        # result.entities / result.relationships / result.content_keywords
    """

    def __init__(self, model=None):
        """初始化抽取器。

        Args:
            model: 抽取用的 LLM 客户端；默认取 ModelRepository.get_deepseek_extractor()。
        """
        self._model = model if model is not None else ModelRepository.get_deepseek_extractor()

    async def extract(self, chunk: TextChunk) -> "ExtractionResult":
        """从单个 chunk 联合抽取实体与关系。

        Args:
            chunk: 待抽取的文本块。

        Returns:
            ExtractionResult（实体列表、关系列表、内容级关键词）。
            内容为空或抽取失败时返回空结果。
        """
        text = (chunk.content or "").strip()
        if not text:
            return ExtractionResult()

        prompt = _EXTRACT_PROMPT.format(
            tuple_delimiter=TUPLE_DELIMITER,
            record_delimiter=RECORD_DELIMITER,
            completion_delimiter=COMPLETION_DELIMITER,
        )
        # 注意：prompt 模板里 {text} 被转义为 {{text}}，此处用字符串替换填入
        prompt = prompt.replace("{text}", text)

        try:
            response = await self._model.ainvoke(prompt)
            raw = _extract_text(response)
            return _parse(raw)
        except Exception as exc:  # noqa: BLE001 - 单块失败不中断整篇/整批
            logger.warning("联合抽取失败 (source=%s index=%d): %s", chunk.source, chunk.index, exc)
            return ExtractionResult()

    def extract_sync(self, chunk: TextChunk) -> "ExtractionResult":
        """同步版联合抽取（内部用 invoke，供脚本/受限环境使用）。

        与 extract 逻辑一致，仅将异步调用替换为同步调用，
        用于规避部分环境下 httpx 异步流处理的问题。

        Args:
            chunk: 待抽取的文本块。

        Returns:
            ExtractionResult；内容为空或抽取失败时返回空结果。
        """
        text = (chunk.content or "").strip()
        if not text:
            return ExtractionResult()

        prompt = _EXTRACT_PROMPT.format(
            tuple_delimiter=TUPLE_DELIMITER,
            record_delimiter=RECORD_DELIMITER,
            completion_delimiter=COMPLETION_DELIMITER,
        )
        prompt = prompt.replace("{text}", text)

        try:
            response = self._model.invoke(prompt)
            raw = _extract_text(response)
            return _parse(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("联合抽取失败 (source=%s index=%d): %s", chunk.source, chunk.index, exc)
            return ExtractionResult()


class ExtractionResult:
    """一次联合抽取的结构化结果。

    Attributes:
        entities: 实体列表，每个元素 {"name","type","description"}。
        relationships: 关系列表，每个元素
            {"source","target","description","keywords","strength"}。
        content_keywords: 内容级关键词列表。
    """

    def __init__(
        self,
        entities: list[dict] | None = None,
        relationships: list[dict] | None = None,
        content_keywords: list[str] | None = None,
    ):
        self.entities = entities or []
        self.relationships = relationships or []
        self.content_keywords = content_keywords or []

    @property
    def triples(self) -> list[dict]:
        """将关系转换为三元组列表（兼容下游建图）。

        每个元素形如 {"head","relation","tail","strength","keywords"}，
        其中 relation 取关系的首个关键字（作为边标签的简写）。
        """
        triples: list[dict] = []
        for r in self.relationships:
            head = r.get("source", "")
            tail = r.get("target", "")
            if not head or not tail:
                continue
            keywords = r.get("keywords", [])
            relation = keywords[0] if keywords else "相关"
            triples.append(
                {
                    "head": head,
                    "relation": relation,
                    "tail": tail,
                    "strength": r.get("strength", 1),
                    "keywords": keywords,
                }
            )
        return triples


def _extract_text(response) -> str:
    """从 LLM 响应对象中提取文本内容（兼容 str / 消息对象 / 多段列表）。"""
    if isinstance(response, str):
        return response
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for seg in content:
            if isinstance(seg, str):
                parts.append(seg)
            elif isinstance(seg, dict) and isinstance(seg.get("text"), str):
                parts.append(seg["text"])
        return "".join(parts)
    return str(content)


def _split_records(raw: str) -> list[str]:
    """按 record 分隔符切分记录，剥离完成标记与空段。"""
    text = raw.strip()
    if COMPLETION_DELIMITER in text:
        text = text.split(COMPLETION_DELIMITER, 1)[0]
    records = [seg.strip() for seg in text.split(RECORD_DELIMITER) if seg.strip()]
    return records


def _parse(raw: str) -> ExtractionResult:
    """解析 LLM 输出为结构化结果。

    采用分隔符协议解析，容错：
    - 逐条记录按 tuple 分隔符切分；
    - 记录前缀决定类型（entity / relationship / content_keywords）；
    - 无法解析的记录跳过，不中断整体。

    Args:
        raw: LLM 原始文本输出。

    Returns:
        ExtractionResult。
    """
    result = ExtractionResult()
    for record in _split_records(raw):
        _parse_record(record, result)
    return result


def _parse_record(record: str, result: ExtractionResult) -> None:
    """解析单条记录并归入结果。"""
    parts = [p.strip() for p in record.split(TUPLE_DELIMITER)]
    if not parts:
        return
    kind = parts[0].strip().strip('"（）()')
    fields = parts[1:]

    if kind == _ENTITY:
        if len(fields) >= 3:
            result.entities.append(
                {"name": fields[0], "type": fields[1], "description": fields[2]}
            )
    elif kind == _RELATIONSHIP:
        if len(fields) >= 5:
            strength = _to_int(fields[4])
            result.relationships.append(
                {
                    "source": fields[0],
                    "target": fields[1],
                    "description": fields[2],
                    "keywords": _split_keywords(fields[3]),
                    "strength": strength,
                }
            )
    elif kind == _CONTENT_KEYWORDS:
        if fields:
            result.content_keywords = _split_keywords(fields[0])


def _split_keywords(raw: str) -> list[str]:
    """将关键词字段拆分为列表（兼容逗号/顿号/竖线分隔）。"""
    return [k.strip() for k in re.split(r"[,，、|/]", raw) if k.strip()]


def _to_int(raw: str) -> int:
    """解析强度分数为整数，失败时回退为 1。"""
    try:
        return int(float(raw.strip()))
    except (ValueError, TypeError):
        return 1
