"""知识子系统：穿搭知识的知识图谱构建与混合检索（RAG）。

职责边界（见 docs/RAG知识图谱规划.md）：
- 本期知识来源为「内置文档 + 手动导入脚本」，无 HTTP 上传接口。
- 离线建图：文档 → 三元组抽取 → networkx 建图 → graph.json 落盘；
            文档 → 切块 → embedding → PG knowledge_chunks 落盘。
- 在线召回：query → 图遍历 + 向量 top-k → 拼接【参考知识】→ 注入 LangGraph 节点。

子目录：
- docs/      内置穿搭知识文档（色彩/场合/体型/风格/面料）
- data/      构建产物落盘（graph.json、历史快照等）
- build/     离线建图流程（graph_builder / vector_builder / import_docs）
- retrieve/  在线检索流程（graph_store / vector_store / retriever）
"""
