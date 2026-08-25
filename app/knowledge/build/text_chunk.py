"""文本切块：将单篇知识文档切分为适合 embedding 检索的文本块。

职责（见 docs/RAG知识图谱规划.md 3.2）：
- 读取单篇文档内容（复用 build.document_reader 定位文件）；
- 使用 langchain-text-splitters 的 RecursiveCharacterTextSplitter 做递归切分；
- 输出带来源元信息（维度、标题、序号）的 TextChunk。

设计原则（原子操作粒度）：
- 只针对「单篇文档」切块，不提供批量扫描全库的入口；
- 内存上界 = 单篇文档的 chunk 数，由下游 document_processor 逐篇消费；
- 提供生成器 iter_chunks 供流式消费，避免一次性持有整篇 chunk 列表。

切分策略说明：
- 中文文本优先按换行 / 标点 / 句末切分，避免切断语义；
- chunk_size 控制在 embedding 模型与检索颗粒度之间的平衡（默认 500 字符）；
- overlap 保留上下文衔接（默认 50 字符），减少跨块语义断裂。
"""
from collections.abc import Iterator
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.knowledge.build.document_reader import Document
from app.knowledge.config import CHUNK_OVERLAP, CHUNK_SIZE


@dataclass
class TextChunk:
    """一个切分后的文本块及其来源元信息。

    Attributes:
        content: 切块后的文本内容。
        dimension: 所属知识维度目录名（如 "silhouette"）；无则为 None。
        dimension_name: 维度中文名；无则为 None。
        title: 来源文档标题（文件名去扩展名）。
        source: 来源文件路径字符串。
        index: 该文档内切块的序号（从 0 开始）。
    """

    content: str
    dimension: str | None
    dimension_name: str | None
    title: str
    source: str
    index: int
    metadata: dict = field(default_factory=dict)


class TextChunker:
    """知识文档文本切块器（单文档粒度）。

    用法：
        chunker = TextChunker()
        chunks = chunker.split_document(doc)   # 一次性拿该篇全部 chunk
        for c in chunker.iter_chunks(doc): ... # 流式逐块消费
    """

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        separators: list[str] | None = None,
    ):
        """初始化切块器。

        Args:
            chunk_size: 每个文本块的最大字符数。
            chunk_overlap: 相邻文本块之间的重叠字符数。
            separators: 递归切分的分隔符优先级列表；默认面向中文文本。
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须为正整数")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._separators = separators or [
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            "；",
            "，",
            " ",
            "",
        ]
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=self._separators,
        )

    def _read_content(self, doc: Document) -> str:
        """读取文档的纯文本内容。

        Args:
            doc: Document 对象（path 为文件绝对路径）。

        Returns:
            文件文本内容；若文件不存在或读取失败则返回空串。
        """
        try:
            return doc.path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, UnicodeDecodeError):
            # 读取失败时返回空串，交由上游决定是否跳过（避免整个流程中断）
            return ""

    def _build_chunk(self, doc: Document, piece: str, index: int) -> TextChunk:
        """由切分片段构造带来源元信息的 TextChunk。"""
        return TextChunk(
            content=piece.strip(),
            dimension=doc.dimension,
            dimension_name=doc.dimension_name,
            title=doc.title,
            source=str(doc.path),
            index=index,
        )

    def iter_chunks(self, doc: Document) -> Iterator[TextChunk]:
        """流式切分单篇文档，逐块产出 TextChunk。

        与 split_document 的区别：不一次性返回列表，而是生成器，
        供下游逐块消费（配合三元组抽取，内存峰值更低）。

        Args:
            doc: 待切分的 Document。

        Yields:
            该文档的每个非空 TextChunk，按文档内顺序。
        """
        content = self._read_content(doc)
        if not content.strip():
            return

        index = 0
        for piece in self._splitter.split_text(content):
            if not piece.strip():
                continue
            yield self._build_chunk(doc, piece, index)
            index += 1

    def split_document(self, doc: Document) -> list[TextChunk]:
        """切分单篇文档为文本块列表（一次性返回）。

        Args:
            doc: 待切分的 Document。

        Returns:
            TextChunk 列表（内容为空则返回空列表）。
        """
        return list(self.iter_chunks(doc))
