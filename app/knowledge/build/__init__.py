"""离线建图流程：知识文档 → 图谱 + 向量 落盘。

包含：
- document_reader  扫描/定位知识文档，返回 Document 元信息
- text_chunk       切块（单文档粒度，流式 iter_chunks）
- extract/         联合抽取 + 增量建图
    - graph_extractor   联合抽取（单 chunk → 实体 + 关系，单次调用）
    - graph_builder     增量合并知识图谱（networkx）
- document_processor  原子操作编排：单篇文档 → 切块 + 联合抽取
- import_docs      调度层：遍历文档逐篇处理并落盘

待实现：
- vector_builder  切块 → embedding → PG knowledge_chunks
"""
