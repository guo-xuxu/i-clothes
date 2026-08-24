"""混合召回：图遍历 + 向量检索，拼接为【参考知识】上下文。

职责（见 docs/RAG知识图谱规划.md 3.3）：
1. query 实体抽取；
2. 图遍历 1-2 跳 → 关系上下文；
3. query embedding → 向量 top-3 → 文本上下文；
4. 两路拼接为 state["rag_context"]，注入 chat_reply / recommend_outfit 的 prompt。
"""
