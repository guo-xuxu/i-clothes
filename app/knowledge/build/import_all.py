"""全量导入入口：抽取所有知识文档 → 三元组入图 → graph.json 落盘 → 登记已处理文档。

与 build/import_docs.py 的区别：import_docs 是「调度 + sink 回调」的抽象层；
本模块是**真正的落盘实现**（graph 落盘 + 增量登记），供离线批量构建调用。

运行：
    python -m app.knowledge.build.import_all
    # 或指定路径：
    python -m app.knowledge.build.import_all app/knowledge/docs/body-shape

设计要点：
- 增量幂等：用 ProcessedDocRegistry 记录「相对路径 + 内容哈希」，
  已处理且内容未变的文档直接跳过，不重复调 LLM。
- 边抽边并：抽取一篇就 merge 进 GraphBuilder（含 canonicalize 同义归一），
  不是全量抽取后再集中合并。
- 单篇失败不中断：某篇抽取异常时跳过该篇，继续处理其余文档。
"""
from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

from app.knowledge.build.document_processor import DocumentProcessor
from app.knowledge.build.document_reader import DocumentReader
from app.knowledge.build.entity_merger import EntityMerger, MergeDecision
from app.knowledge.build.entity_normalizer import EntityNormalizer
from app.knowledge.build.extract.graph_builder import GraphBuilder
from app.knowledge.build.import_registry import ProcessedDocRegistry
from app.knowledge.config import DATA_DIR, DOCS_DIR, GRAPH_PATH
from app.knowledge.retrieve.vector_store import VectorStore
from app.repositories.model_repo import ModelRepository

logger = logging.getLogger(__name__)

REGISTRY_PATH = DATA_DIR / "processed_docs.json"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rel_path(path: Path) -> str:
    """返回文档相对 docs 根目录的路径（POSIX 风格，作登记表键）。"""
    try:
        return path.resolve().relative_to(DOCS_DIR).as_posix()
    except ValueError:
        return path.name


def _read_content(path: Path) -> str:
    """读文档内容；失败返回空串（空串文档会被哈希判断跳过或按空处理）。"""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return ""


def import_all(paths: list[str] | None = None) -> dict:
    """全量导入（增量幂等）。

    Args:
        paths: 待导入路径列表；None 表示全量扫描 DOCS_DIR。

    Returns:
        统计信息 dict：{"processed", "skipped", "nodes", "edges"}。
    """
    reader = DocumentReader(DOCS_DIR)
    registry = ProcessedDocRegistry(REGISTRY_PATH)
    processor = DocumentProcessor()
    builder = GraphBuilder()
    if GRAPH_PATH.is_file():
        builder.load(GRAPH_PATH)
    embedder = ModelRepository.get_embedding()
    vector_store = VectorStore()
    normalizer = EntityNormalizer()
    merger = EntityMerger(builder, normalizer, vector_store, embedder)

    if paths:
        docs = []
        for p in paths:
            docs.extend(reader.read_path(p))
    else:
        docs = reader.scan()

    processed = 0
    skipped = 0
    failed = 0

    for doc in docs:
        rel = _rel_path(doc.path)
        content = _read_content(doc.path)
        content_hash = _sha256(content)

        if registry.is_processed(rel, content_hash):
            skipped += 1
            continue

        if not content.strip():
            logger.warning("跳过空文档: %s", rel)
            continue

        try:
            result = processor.process_sync(doc)
        except Exception as exc:  # noqa: BLE001 - 单篇失败不中断
            logger.error("抽取失败 %s: %s", rel, exc)
            failed += 1
            continue

        triples = result.all_triples

        # 收集去重实体（name -> {type, description}）
        entity_map: dict[str, dict] = {}
        for cw in result.chunks:
            for e in cw.entities:
                if e.get("name") and e["name"] not in entity_map:
                    entity_map[e["name"]] = e
        # 兜底：三元组 head/tail 若未出现在 entities 列表，补空实体（保证有来源/维度）
        for t in triples:
            for role in ("head", "tail"):
                n = t.get(role, "")
                if n and n not in entity_map:
                    entity_map[n] = {"name": n, "type": "", "description": ""}

        # 1. 实体归并解析：逐个判定归并目标，注册映射（让 add_triples/add_entity 自动归一）
        resolved: dict[str, MergeDecision] = {}
        for raw, e in entity_map.items():
            decision = merger.resolve(
                raw,
                type=e.get("type", ""),
                description=e.get("description", ""),
                dimension=doc.dimension_name or "",
                source=rel,
            )
            resolved[raw] = decision
            if raw != decision.canonical:
                builder.register_alias(raw, decision.canonical)
            # 回写词典：归并发现的同义关系沉淀（后续文档直接 L2 命中，免重复 LLM 判定）
            if decision.aliases:
                normalizer.register_synonyms({a: decision.canonical for a in decision.aliases})

        # 2. 加边（head/tail 经 canonicalize 自动归一到规范名，边自然连到规范节点）
        builder.add_triples(triples)

        # 3. 实体入图（用规范名）+ 记录别名
        for raw, e in entity_map.items():
            d = resolved[raw]
            builder.add_entity(
                d.canonical,
                type=e.get("type", ""),
                description=e.get("description", ""),
                dimension=doc.dimension_name or "",
                source=rel,
            )
            if d.aliases:
                node = builder.graph.nodes[d.canonical]
                for a in d.aliases:
                    if a not in node["aliases"]:
                        node["aliases"].append(a)

        # 4. 实体向量：只 embed 新增实体（归并到已有的实体不重复 embed）
        new_entities: dict[str, dict] = {}
        for raw, e in entity_map.items():
            d = resolved[raw]
            if d.is_new and d.canonical not in new_entities:
                new_entities[d.canonical] = e
        if new_entities:
            names = list(new_entities.keys())
            entity_texts = [
                f"{n}：{new_entities[n]['description']}" if new_entities[n].get("description") else n
                for n in names
            ]
            entity_vecs = embedder.embed_documents(entity_texts)
            vector_store.upsert_entities(
                [
                    {
                        "eid": builder.get_entity_id(n),
                        "name": n,
                        "type": new_entities[n].get("type", ""),
                        "dimension": doc.dimension_name or "",
                        "description": new_entities[n].get("description", ""),
                        "embedding": v,
                    }
                    for n, v in zip(names, entity_vecs)
                ]
            )

        # chunk 向量：chunk 文本 → embedding → Chroma
        chunk_texts = [cw.chunk.content for cw in result.chunks]
        if chunk_texts:
            chunk_vecs = embedder.embed_documents(chunk_texts)
            vector_store.upsert_chunks(
                rel,
                [{"content": t, "embedding": v} for t, v in zip(chunk_texts, chunk_vecs)],
            )

        registry.mark(
            rel,
            content_hash,
            dimension=doc.dimension_name,
            chunks=len(result.chunks),
            entities=len(entity_map),
            triples=len(triples),
        )
        processed += 1
        logger.info(
            "已导入 %s（%d chunk, %d 实体, %d 三元组）",
            rel, len(result.chunks), len(entity_map), len(triples),
        )

    # 落盘：图 + 登记表 + 同义词典（归并新增的同义关系沉淀到 synonyms.json）
    builder.save(GRAPH_PATH)
    registry.save()
    normalizer.persist()

    vcounts = vector_store.counts()
    # embedding 去重检查：实体向量数应等于图节点数（一个节点一个向量，无重复/遗漏）
    if vcounts["entities"] != builder.graph.number_of_nodes():
        logger.warning(
            "实体向量数(%d)与图节点数(%d)不一致，可能存在重复向量或遗漏",
            vcounts["entities"], builder.graph.number_of_nodes(),
        )
    stats = {
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "nodes": builder.graph.number_of_nodes(),
        "edges": builder.graph.number_of_edges(),
        "entity_vectors": vcounts["entities"],
        "chunk_vectors": vcounts["chunks"],
    }
    logger.info(
        "导入完成：处理 %d、跳过 %d、失败 %d；图 %d 节点 / %d 边；已落盘 %s",
        processed, skipped, failed, stats["nodes"], stats["edges"], GRAPH_PATH,
    )
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = sys.argv[1:] or None
    stats = import_all(args)
    print(f"\n完成：处理 {stats['processed']} 篇，跳过 {stats['skipped']} 篇，失败 {stats['failed']} 篇")
    print(f"图谱：{stats['nodes']} 节点 / {stats['edges']} 边 → {GRAPH_PATH}")
