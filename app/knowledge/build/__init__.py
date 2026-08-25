"""离线建图流程：知识文档 → 图谱 + 向量 落盘。

包含：
- graph_builder   文档 → 三元组抽取 → networkx 建图 → graph.json
- vector_builder  文档 → 切块 → embedding → PG knowledge_chunks
- import_docs     手动导入脚本入口
"""
