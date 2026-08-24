"""在线检索流程：query → 图遍历 + 向量召回 → 拼接【参考知识】。

包含：
- graph_store   图谱加载/序列化/图遍历
- vector_store  向量读写与余弦检索
- retriever     混合召回，产出 rag_context 供 LangGraph 节点注入
"""
