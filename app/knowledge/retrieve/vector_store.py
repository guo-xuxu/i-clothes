"""向量存储：PG knowledge_chunks 的读写与余弦检索。

职责：
- 写入文本块 + float8[] 向量（供 build.vector_builder 调用）；
- 余弦相似度检索 top-k（v1 无 pgvector，Python 侧计算余弦）；
- 返回匹配文本 + 来源，供 retriever 使用。

注意：v1 千级 chunk 内毫秒级；超过 5k chunk 再评估 pgvector/Milvus。
"""
