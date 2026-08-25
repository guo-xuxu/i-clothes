"""知识抽取包：联合抽取 + 增量建图。

包含：
- graph_extractor  联合抽取：单 chunk → 实体 + 关系（单次 LLM 调用，GraphRAG 风格）
- graph_builder    图谱构建：三元组 → 增量合并进 networkx 图

对外统一入口：
    from app.knowledge.build.extract import GraphExtractor, GraphBuilder

分层关系（供参考）：
    build/text_chunk.py     切块（一篇文章怎么切）
    build/extract/          抽取 + 建图（chunk → 实体/关系 → 图）
    build/document_processor.py  原子操作编排（单篇文档粒度）
    build/import_docs.py    调度层（遍历文档逐篇处理）
"""
from app.knowledge.build.extract.graph_builder import GraphBuilder
from app.knowledge.build.extract.graph_extractor import ExtractionResult, GraphExtractor

__all__ = ["GraphExtractor", "GraphBuilder", "ExtractionResult"]
