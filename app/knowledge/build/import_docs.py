"""知识文档导入：遍历文档，逐篇处理并落盘（调度层）。

职责（见 docs/RAG知识图谱规划.md 3.2、3.1）：
- 定位待导入的文档（单文件或目录），逐篇调用 DocumentProcessor.process；
- 每篇处理完立即「落盘」，处理完即释放，内存峰值 = 单篇文章；
- 落盘为「逐篇增量」：图谱逐篇 merge、向量逐篇写入（v1 简化为逐篇调用落盘回调）。

设计原则：
- 本模块只做「调度 + 落盘衔接」，不直接操作 LLM / 切块细节；
- 落盘动作通过 sink 回调注入，便于 dry-run（不落盘）与单测（mock sink）。
- 当前图谱/向量的实际落盘实现待 graph_builder / vector_builder 补齐，
  这里以回调形式预留，避免与未实现模块强耦合。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path

from app.knowledge.build.document_processor import DocumentProcessor, ProcessedDocument
from app.knowledge.build.document_reader import DocumentReader
from app.knowledge.config import DOCS_DIR

logger = logging.getLogger(__name__)

# 落盘回调签名：接收一篇处理结果，返回 None（或 await 后返回 None）。
Sink = Callable[[ProcessedDocument], Awaitable[None] | None]


async def _noop_sink(_doc: ProcessedDocument) -> None:
    """默认空落盘（dry-run 用，仅打印统计）。"""


async def import_documents(
    paths: str | Path | Iterable[str | Path] | None = None,
    *,
    processor: DocumentProcessor | None = None,
    sink: Sink | None = None,
    concurrency: int = 1,
) -> list[ProcessedDocument]:
    """逐篇处理并落盘知识文档。

    Args:
        paths: 待导入的路径，可为单个文件、目录，或多个路径的可迭代对象；
            默认取 config.DOCS_DIR（内置知识文档目录）。
        processor: 文档处理器；默认新建 DocumentProcessor(concurrency=concurrency)。
        sink: 落盘回调，逐篇调用；默认 _noop_sink（dry-run）。
        concurrency: 处理文档的并发数（处理器内部的 chunk 抽取并发另由 processor 控制）。

    Returns:
        处理结果列表（与导入顺序一致）。注意：这是逐篇处理的汇总结果，
        调用方通常无需保留全部；如需省内存可改用 import_documents_stream。

    Raises:
        FileNotFoundError: 指定路径不存在。
    """
    result = DocumentProcessor(concurrency=concurrency) if processor is None else processor
    sink_fn = sink or _noop_sink
    reader = DocumentReader(DOCS_DIR)

    docs = _resolve_docs(reader, paths)

    processed: list[ProcessedDocument] = []
    for doc in docs:
        out = await result.process(doc)
        processed.append(out)
        await _run_sink(sink_fn, out)
    return processed


async def _run_sink(sink: Sink, doc: ProcessedDocument) -> None:
    """执行落盘回调，兼容同步/异步两种签名。"""
    ret = sink(doc)
    if ret is not None:
        await ret


def _resolve_docs(
    reader: DocumentReader,
    paths: str | Path | Iterable[str | Path] | None,
) -> list:
    """将输入路径解析为 Document 列表（去重、保序）。"""
    if paths is None:
        return reader.scan()

    if isinstance(paths, (str, Path)):
        paths = [paths]

    docs: list = []
    seen: set[str] = set()
    for p in paths:
        for doc in reader.read_path(p):
            key = str(doc.path)
            if key not in seen:
                seen.add(key)
                docs.append(doc)
    return docs


async def import_documents_stream(
    paths: str | Path | Iterable[str | Path] | None = None,
    *,
    processor: DocumentProcessor | None = None,
    sink: Sink | None = None,
) -> "AsyncIterator[ProcessedDocument]":  # noqa: F821
    """流式逐篇处理并落盘（生成器），处理一篇 yield 一篇。

    与 import_documents 的区别：不一次性返回全部结果，便于内存受限场景。

    Args:
        paths: 待导入路径（同 import_documents）。
        processor: 文档处理器。
        sink: 落盘回调。

    Yields:
        每篇处理完成的 ProcessedDocument。
    """
    proc = processor or DocumentProcessor()
    sink_fn = sink or _noop_sink
    reader = DocumentReader(DOCS_DIR)

    for doc in _resolve_docs(reader, paths):
        out = await proc.process(doc)
        await _run_sink(sink_fn, out)
        yield out


if __name__ == "__main__":
    # 手动导入入口（dry-run）：python -m app.knowledge.build.import_docs [路径...]
    import sys

    async def _main() -> None:
        args = sys.argv[1:] or None
        async for out in import_documents_stream(args):
            n = len(out.all_triples)
            logger.info("[dry-run] %s: %d chunks, %d triples", out.title, len(out.chunks), n)
            print(f"{out.title}: {len(out.chunks)} chunks, {n} triples")

    asyncio.run(_main())
