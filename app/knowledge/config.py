"""知识子系统配置：集中管理构建 / 检索相关参数。

职责：将知识图谱构建与混合检索中可调参数（切块、embedding、
图遍历跳数、向量 top-k 等）集中于此，避免散落在各模块的魔法数字。

用法：
    from app.knowledge.config import CHUNK_SIZE, CHUNK_OVERLAP
    # 或
    from app.knowledge import config
    config.CHUNK_SIZE
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# 文本切块（build/text_chunk.py）
# ---------------------------------------------------------------------------
# 每个文本块的最大字符数：平衡 embedding 语义完整性与检索颗粒度。
CHUNK_SIZE = 500
# 相邻文本块之间的重叠字符数：保留上下文衔接，减少跨块语义断裂。
CHUNK_OVERLAP = 50

# ---------------------------------------------------------------------------
# 检索（retrieve/retriever.py、retrieve/vector_store.py）
# ---------------------------------------------------------------------------
# 图遍历的邻居跳数（一跳/二跳）。
GRAPH_HOPS = 2
# 向量检索返回的 top-k 文本块数量。
VECTOR_TOP_K = 3

# ---------------------------------------------------------------------------
# 路径（供构建 / 检索定位知识文档与落盘产物）
# ---------------------------------------------------------------------------
# 知识子系统根目录（app/knowledge）。
KNOWLEDGE_DIR = Path(__file__).resolve().parent
# 内置知识文档根目录。
DOCS_DIR = KNOWLEDGE_DIR / "docs"
# 构建产物落盘目录（graph.json、历史快照、切块中间产物）。
DATA_DIR = KNOWLEDGE_DIR / "data"
# 知识图谱序列化文件路径。
GRAPH_PATH = DATA_DIR / "graph" / "graph.json"
# 切块中间产物目录（每篇文档的 chunk + 三元组 JSON 落盘于此）。
CHUNKS_DIR = DATA_DIR / "chunks"

# ---------------------------------------------------------------------------
# 抽取（build/extract/graph_extractor.py）
# ---------------------------------------------------------------------------
# 抽取输出分隔符（GraphRAG 风格协议，选取不易与正文冲突的字符）。
TUPLE_DELIMITER = "<|>"
RECORD_DELIMITER = "##"
COMPLETION_DELIMITER = "<|COMPLETE|>"
