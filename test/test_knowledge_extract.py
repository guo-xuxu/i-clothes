"""最小化测试：验证「分词 + graph_extractor 联合抽取」效果。

流程：
1. 用真实知识文档（app/knowledge/docs/silhouette/穿搭公式.md）跑 TextChunker 分词；
2. 取第一个 chunk，用 GraphExtractor 真实调用 DeepSeek 提取实体与三元组；
3. 结果写入文件（绕开终端 stdout 回显异常），供人工检查提取效果。

运行：
    python test/test_knowledge_extract.py

结果文件：
    test/extract_result.txt
"""
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.knowledge.build.document_reader import DocumentReader
from app.knowledge.build.extract.graph_extractor import GraphExtractor
from app.knowledge.build.text_chunk import TextChunker
from app.knowledge.config import DOCS_DIR

RESULT_FILE = Path(__file__).parent / "extract_result.txt"


def main() -> None:
    lines: list[str] = []
    sep = "=" * 60

    lines.append(sep)
    lines.append("最小化测试：分词 + graph_extractor 联合抽取")
    lines.append(sep)

    # 1. 定位一篇真实知识文档
    reader = DocumentReader(DOCS_DIR)
    docs = reader.scan()
    if not docs:
        lines.append("✗ 未找到任何知识文档，请确认 docs/ 目录下有 .md/.txt 文件")
        _write(lines)
        return
    doc = docs[0]
    lines.append(f"\n[文档] {doc.title}（维度: {doc.dimension_name}）")

    # 2. 分词，取第一个 chunk
    chunker = TextChunker()
    chunks = list(chunker.iter_chunks(doc))
    if not chunks:
        lines.append("✗ 该文档切分为空")
        _write(lines)
        return
    chunk = chunks[0]
    lines.append(f"[分词] 共 {len(chunks)} 个 chunk，取第 1 个：")
    lines.append("-" * 60)
    lines.append(chunk.content)
    lines.append("-" * 60)

    # 3. 联合抽取（真实调用 DeepSeek，同步）
    extractor = GraphExtractor()
    lines.append("\n[抽取] 正在调用 DeepSeek 提取实体与三元组 ...\n")
    result = extractor.extract_sync(chunk)

    # 4. 输出结果
    lines.append(sep)
    lines.append("提取结果")
    lines.append(sep)

    lines.append(f"\n--- 实体（{len(result.entities)} 个）---")
    for e in result.entities:
        lines.append(f"  · {e['name']}  [{e['type']}]  {e['description']}")

    lines.append(f"\n--- 关系 / 三元组（{len(result.relationships)} 条）---")
    for r in result.relationships:
        lines.append(
            f"  · {r['source']} --({', '.join(r['keywords'])})--> {r['target']}"
            f"  [强度 {r['strength']}]"
        )

    lines.append("\n--- 内容级关键词 ---")
    if result.content_keywords:
        lines.append("  " + ", ".join(result.content_keywords))
    else:
        lines.append("  （无）")

    lines.append("\n" + sep)
    lines.append("测试完成")
    lines.append(sep)

    _write(lines)


def _write(lines: list[str]) -> None:
    RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
