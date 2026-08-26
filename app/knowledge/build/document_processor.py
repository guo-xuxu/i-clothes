"""文档处理：单篇知识文档的原子操作编排（切块 + 联合抽取）。

职责（见 docs/RAG知识图谱规划.md 3.2）：
- 以「单篇文档」为原子单位：切块 → 逐块联合抽取（实体 + 关系）→ 组装结果；
- 内存上界 = 单篇文章（处理完一篇即返回并释放，由 import_docs 逐篇调度）；
- 单个 chunk 抽取失败不中断整篇（跳过该块的抽取结果，保留 chunk 正文）。

设计原则：
- 不在此处做任何落盘 / 建图 / 写库，仅负责「把一篇文档变成结构化结果」；
- 抽取采用联合抽取（extract.GraphExtractor，单次 LLM 调用）；
- 落盘由上层 import_docs 逐篇调用后执行，保持原子单元纯净、可测试。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.knowledge.build.document_reader import Document
from app.knowledge.build.extract.graph_extractor import GraphExtractor
from app.knowledge.build.text_chunk import TextChunk, TextChunker


@dataclass
class ChunkWithTriples:
    """一个文本块及其联合抽取结果。

    Attributes:
        chunk: 文本块本体。
        triples: 该块抽取出的三元组列表（抽取失败时为空列表）。
        entities: 该块抽取出的实体列表（含名称/类型/描述）。
        content_keywords: 该块抽取出的内容级关键词。
    """

    chunk: TextChunk
    triples: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    content_keywords: list[str] = field(default_factory=list)


@dataclass
class ProcessedDocument:
    """一篇文档处理后的结构化结果。

    Attributes:
        source: 来源文件路径字符串。
        title: 文档标题。
        dimension: 所属维度目录名；无则为 None。
        dimension_name: 维度中文名；无则为 None。
        chunks: 各文本块及其三元组，按文档内顺序。
    """

    source: str
    title: str
    dimension: str | None
    dimension_name: str | None
    chunks: list[ChunkWithTriples] = field(default_factory=list)

    @property
    def all_triples(self) -> list[dict]:
        """汇总该文档的全部三元组（扁平列表）。"""
        return [t for c in self.chunks for t in c.triples]


class DocumentProcessor:
    """单篇文档处理器（原子操作编排）。

    用法：
        processor = DocumentProcessor()
        result = await processor.process(doc)
    """

    def __init__(
        self,
        chunker: TextChunker | None = None,
        extractor: GraphExtractor | None = None,
        concurrency: int = 1,
    ):
        """初始化处理器。

        Args:
            chunker: 文本切块器；默认新建 TextChunker()。
            extractor: 联合抽取器；默认新建 GraphExtractor()。
            concurrency: 同一文档内 chunk 抽取的并发数（>1 时可并行抽取）。
        """
        self._chunker = chunker or TextChunker()
        self._extractor = extractor or GraphExtractor()
        if concurrency < 1:
            raise ValueError("concurrency 必须 >= 1")
        self._concurrency = concurrency

    async def _extract_chunk(self, chunk: TextChunk) -> ChunkWithTriples:
        """对单个 chunk 执行联合抽取（实体 + 关系）。

        Args:
            chunk: 待抽取的文本块。

        Returns:
            ChunkWithTriples（含三元组、实体、关键词；失败时均为空）。
        """
        result = await self._extractor.extract(chunk)
        return self._build_chunk_result(chunk, result)

    def _extract_chunk_sync(self, chunk: TextChunk) -> ChunkWithTriples:
        """同步版：对单个 chunk 执行联合抽取。"""
        result = self._extractor.extract_sync(chunk)
        return self._build_chunk_result(chunk, result)

    @staticmethod
    def _build_chunk_result(chunk: TextChunk, result) -> ChunkWithTriples:
        """将抽取结果组装为 ChunkWithTriples。"""
        return ChunkWithTriples(
            chunk=chunk,
            triples=result.triples,
            entities=result.entities,
            content_keywords=result.content_keywords,
        )

    async def process(self, doc: Document) -> ProcessedDocument:
        """处理单篇文档：切块 → 逐块联合抽取 → 组装结果。

        Args:
            doc: 待处理的 Document。

        Returns:
            ProcessedDocument（含各 chunk 及其三元组、实体、关键词）。
        """
        result = ProcessedDocument(
            source=str(doc.path),
            title=doc.title,
            dimension=doc.dimension,
            dimension_name=doc.dimension_name,
        )

        chunks = list(self._chunker.iter_chunks(doc))
        if not chunks:
            return result

        if self._concurrency == 1:
            # 串行：逐块两阶段抽取，单块失败不影响其余块
            for chunk in chunks:
                result.chunks.append(await self._extract_chunk(chunk))
        else:
            # 并发抽取（信号量限流），再按 chunk 顺序归位
            sem = asyncio.Semaphore(self._concurrency)

            async def _extract_one(chunk: TextChunk) -> ChunkWithTriples:
                async with sem:
                    return await self._extract_chunk(chunk)

            results = await asyncio.gather(*(_extract_one(c) for c in chunks))
            # gather 保序，直接按顺序装入
            result.chunks.extend(results)

        return result

    def process_sync(self, doc: Document) -> ProcessedDocument:
        """同步版：处理单篇文档（切块 → 逐块联合抽取 → 组装结果）。

        供脚本/受限环境使用，逐块串行抽取。

        Args:
            doc: 待处理的 Document。

        Returns:
            ProcessedDocument（含各 chunk 及其三元组、实体、关键词）。
        """
        result = ProcessedDocument(
            source=str(doc.path),
            title=doc.title,
            dimension=doc.dimension,
            dimension_name=doc.dimension_name,
        )

        for chunk in self._chunker.iter_chunks(doc):
            result.chunks.append(self._extract_chunk_sync(chunk))

        return result
