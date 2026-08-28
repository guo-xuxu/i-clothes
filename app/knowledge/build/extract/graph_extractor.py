"""联合抽取：一次调用同时产出实体与关系（Agno 结构化输出）。

职责（见 docs/RAG知识图谱规划.md 3.2）：
- 以「单个 chunk」为输入，调用 DeepSeek 一次完成实体识别 + 关系提取；
- 用 Agno 的 Agent + output_schema 约束输出为 Pydantic 模型；
- 返回带描述的实体、带强度与关键词的关系、以及内容级关键词。

设计原则：
- 单次调用（不做实体/关系二次调用）；
- 中文输出，实体名保持原文，与下游中文检索/回答对齐；
- 关系有方向（source → target），与 GraphBuilder 的有向图匹配；
- 用 Agno 的 OpenAILike 接入 DeepSeek（OpenAI 兼容端点）。
"""
from __future__ import annotations

import logging

from agno.agent import Agent
from agno.models.openai.like import OpenAILike
from pydantic import BaseModel, Field

from app.config import settings
from app.knowledge.build.text_chunk import TextChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic 输出模型
# ---------------------------------------------------------------------------
class Entity(BaseModel):
    """一个知识实体。"""

    name: str = Field(description="实体名称，简洁规范，只保留核心名词短语，不加修饰语")
    type: str = Field(description="实体类型，概括本质类别，如穿搭法则/服装单品/身材类型/搭配原则")
    description: str = Field(description="对实体属性和活动的全面描述")


class Relationship(BaseModel):
    """一对相关实体之间的有向关系。"""

    source: str = Field(description="源实体名称（须为已识别实体的规范名）")
    target: str = Field(description="目标实体名称（须为已识别实体的规范名）")
    description: str = Field(description="解释为何两者相关")
    keywords: list[str] = Field(description="概括关系性质的1-3个关键字，只描述关系性质，不含实体属性词")
    strength: int = Field(description="关系强度分数，1-10", ge=1, le=10)


class ExtractionSchema(BaseModel):
    """联合抽取的完整输出结构。"""

    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    content_keywords: list[str] = Field(default_factory=list)


# 联合抽取提示词。
_EXTRACT_PROMPT = """你是一个穿搭知识抽取器。请从下面的文本中识别所有实体以及实体之间的所有关系，用于构建穿搭知识图谱。

- 实体提取规则 -
1. 识别所有实体。每个实体包含：name（实体名称）、type（实体类型）、description（对实体属性和活动的全面描述）。
2. 实体命名要求：
   - name 必须简洁、规范，只保留核心名词短语，不要堆砌形容词修饰语（如「风衣」而非「帅气挺括的风衣」）。
   - 不要把一句完整的话或长规则当作实体，应拆解为独立的概念（如「三层搭配原则」是实体，而「内层最薄、外层最瘦」应作为该实体的描述或单独概念）。
   - 同一概念的不同说法合并为同一个实体，避免「风衣」「帅气显瘦的风衣」并存。
3. type 应概括实体的本质类别（如「穿搭法则」「服装单品」「身材类型」「搭配原则」），不要用「错误搭配」这类评价性标签。
4. 实体粒度细分：当一个大类概念在不同语境下有不同表现时，应抽取「带限定条件的子实体」作为关系节点，而不是用泛化大类直接相连。例如原文说「颜色相近导致单调」，应抽取「色彩相近」作为实体（而非笼统的「色彩」），因为「色彩」本身不会导致单调，只有「色彩相近」这个具体状态才会。

- 关系提取规则 -
5. 从已识别实体中，识别彼此明显相关的所有对。每个关系包含：source（源实体名称）、target（目标实体名称）、description（解释为何两者相关）、keywords（概括关系性质的 1-3 个高级关键字）、strength（关系强度分数，1-10 的整数）。
6. keywords 只能描述「两者之间的关系的性质」（如「搭配」「适合」「对比」「违背」「包含」），不要放入实体自身的属性词（如「内层」「外窄」「第二层」这类描述单个实体的词）。
7. 同一对实体之间只保留一条最关键的关系，不要把同一关系拆成多条（如「对比」和「相对」属于同一关系，只保留一条）。
8. 强度要拉开区分度：核心关系（如「适合某身材」「违背某原则」）给 9-10，泛化关系（如「搭配某单品」）给 5-6，让不同重要程度的关系在强度上可区分。

- 内容级关键词 -
9. 识别概括整篇文章主要概念、主题的高级关键字，存入 content_keywords（控制在 10 个以内，只保留最具代表性的）。

- 示例（学习以下抽取的颗粒度、命名规范与关系表达方式）-
示例输入文本：
"上松下紧是最经典的穿搭公式，适合梨形身材和苹果型身材的人。具体搭配时，上半身选择宽松的衬衫，下半身搭配紧身的小脚裤，既能修饰腿型，又显瘦。如果上下都宽松，就会违背松紧结合的原则，显得臃肿。颜色相近容易导致单调感。"

示例输出：
{{
  "entities": [
    {{"name": "上松下紧", "type": "穿搭公式", "description": "上半身宽松、下半身紧身的经典穿搭公式"}},
    {{"name": "梨形身材", "type": "身材类型", "description": "下半身较丰满的身材类型"}},
    {{"name": "苹果型身材", "type": "身材类型", "description": "上半身较丰满的身材类型"}},
    {{"name": "衬衫", "type": "服装单品", "description": "上半身常穿的宽松上衣"}},
    {{"name": "小脚裤", "type": "服装单品", "description": "紧身修腿型的长裤"}},
    {{"name": "松紧结合", "type": "搭配原则", "description": "宽松与紧身单品搭配的原则"}},
    {{"name": "色彩相近", "type": "色彩状态", "description": "多个颜色之间色调接近的状态"}},
    {{"name": "单调感", "type": "穿搭效果", "description": "颜色相近导致的整体造型平淡"}}
  ],
  "relationships": [
    {{"source": "上松下紧", "target": "梨形身材", "description": "该公式能修饰下半身偏丰满的体型", "keywords": ["适合"], "strength": 9}},
    {{"source": "上松下紧", "target": "苹果型身材", "description": "该公式同样适用于上半身偏丰满的体型", "keywords": ["适合"], "strength": 9}},
    {{"source": "上松下紧", "target": "衬衫", "description": "该公式中上半身应选宽松衬衫", "keywords": ["搭配"], "strength": 6}},
    {{"source": "上松下紧", "target": "小脚裤", "description": "该公式中下半身应搭配紧身小脚裤", "keywords": ["搭配"], "strength": 6}},
    {{"source": "上松下紧", "target": "松紧结合", "description": "该公式是松紧结合原则的体现", "keywords": ["体现"], "strength": 7}},
    {{"source": "色彩相近", "target": "单调感", "description": "颜色过于接近会显得平淡", "keywords": ["导致"], "strength": 8}}
  ],
  "content_keywords": ["上松下紧", "松紧结合", "显瘦", "修饰腿型"]
}}

文本：
{text}
"""


class GraphExtractor:
    """联合抽取器（单 chunk 粒度，单次调用，Agno 结构化输出）。

    用法：
        extractor = GraphExtractor()
        result = extractor.extract_sync(chunk)   # 同步
        result = await extractor.extract(chunk)  # 异步
    """

    def __init__(self, agent: Agent | None = None):
        """初始化抽取器。

        Args:
            agent: Agno Agent；默认按 config 里的 DeepSeek 配置构造。
        """
        if agent is not None:
            self._agent = agent
        else:
            self._agent = self._build_agent()

    @staticmethod
    def _build_agent() -> Agent:
        """按配置构造接入 DeepSeek 的 Agno Agent。

        DeepSeek 的 OpenAI 兼容端点不支持 json_schema 类型的 response_format，
        因此关闭 structured/json_schema outputs，让 Agno 回退到 json_object 模式，
        再由 output_schema（Pydantic）在响应解析环节做结构化校验。
        """
        model = OpenAILike(
            id=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=0,
            supports_native_structured_outputs=False,
            supports_json_schema_outputs=False,
        )
        return Agent(
            model=model,
            output_schema=ExtractionSchema,
            description="穿搭知识实体与关系抽取器，输出结构化 JSON。",
        )

    async def extract(self, chunk: TextChunk) -> "ExtractionResult":
        """从单个 chunk 联合抽取实体与关系（异步）。

        Args:
            chunk: 待抽取的文本块。

        Returns:
            ExtractionResult；内容为空或抽取失败时返回空结果。
        """
        text = (chunk.content or "").strip()
        if not text:
            return ExtractionResult()

        try:
            response = await self._agent.arun(_EXTRACT_PROMPT.format(text=text))
            return ExtractionResult.from_output(response.content)
        except Exception as exc:  # noqa: BLE001 - 单块失败不中断整篇/整批
            logger.warning("联合抽取失败 (source=%s index=%d): %s", chunk.source, chunk.index, exc)
            return ExtractionResult()

    def extract_sync(self, chunk: TextChunk) -> "ExtractionResult":
        """从单个 chunk 联合抽取实体与关系（同步）。

        Args:
            chunk: 待抽取的文本块。

        Returns:
            ExtractionResult；内容为空或抽取失败时返回空结果。
        """
        text = (chunk.content or "").strip()
        if not text:
            return ExtractionResult()

        try:
            response = self._agent.run(_EXTRACT_PROMPT.format(text=text))
            return ExtractionResult.from_output(response.content)
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

    @classmethod
    def from_output(cls, output: BaseModel | None) -> "ExtractionResult":
        """从 Agno 结构化输出（Pydantic 实例）构造结果。

        Args:
            output: Agent 返回的 output_schema 实例（ExtractionSchema）。

        Returns:
            ExtractionResult；output 为空或类型不符时返回空结果。
        """
        if output is None:
            return cls()
        if isinstance(output, ExtractionSchema):
            return cls(
                entities=[e.model_dump() for e in output.entities],
                relationships=[r.model_dump() for r in output.relationships],
                content_keywords=list(output.content_keywords),
            )
        # 兜底：尝试按属性提取（兼容可能的包装类型）
        try:
            return cls(
                entities=[e.model_dump() for e in output.entities],
                relationships=[r.model_dump() for r in output.relationships],
                content_keywords=list(output.content_keywords),
            )
        except Exception:  # noqa: BLE001
            logger.debug("无法从输出提取结构化结果: %r", type(output))
            return cls()

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
