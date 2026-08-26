"""整篇文档提取测试：对一篇知识文档的所有 chunk 做联合抽取，汇总输出。

流程：
1. 定位一篇真实知识文档；
2. 用 DocumentProcessor.process_sync 逐块抽取（切块 + 联合抽取）；
3. 汇总输出整篇的实体、关系三元组、内容关键词到文件。

运行：
    python test/test_document_extract.py

结果文件：
    test/document_extract_result.txt
"""
import sys
import traceback
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.knowledge.build.document_processor import DocumentProcessor
from app.knowledge.build.document_reader import DocumentReader
from app.knowledge.config import DOCS_DIR

RESULT_FILE = Path(__file__).parent / "document_extract_result.txt"


def log(msg: str) -> None:
    with open(RESULT_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    RESULT_FILE.write_text("", encoding="utf-8")
    sep = "=" * 60
    log(sep)
    print("整篇文档提取测试")
    log("整篇文档提取测试")
    log(sep)

    try:
        reader = DocumentReader(DOCS_DIR)
        docs = reader.scan()
        if not docs:
            print("✗ 未找到任何知识文档")
            log("✗ 未找到任何知识文档")
            return
        doc = docs[0]
        print(f"[文档] {doc.title}（维度: {doc.dimension_name}）")
        log(f"\n[文档] {doc.title}（维度: {doc.dimension_name}）\n")

        processor = DocumentProcessor()
        print("[处理] 开始逐块抽取整篇文档 ...\n")
        log("[处理] 开始逐块抽取整篇文档 ...\n")
        result = processor.process_sync(doc)
        print("[处理] 完成\n")
        log("[处理] 完成\n")

        # 汇总
        all_entities: list[dict] = []
        all_triples: list[dict] = []
        all_keywords: list[str] = []
        seen_entity: set[str] = set()

        for cw in result.chunks:
            for e in cw.entities:
                if e["name"] not in seen_entity:
                    seen_entity.add(e["name"])
                    all_entities.append(e)
            all_triples.extend(cw.triples)
            for k in cw.content_keywords:
                if k not in all_keywords:
                    all_keywords.append(k)

        log(sep)
        print("提取结果汇总")
        log("提取结果汇总")
        log(sep)
        print(f"\n--- 实体（去重后 {len(all_entities)} 个）---")
        log(f"\n--- 实体（去重后 {len(all_entities)} 个）---")
        for e in all_entities:
            print(f"  · {e['name']}  [{e['type']}]  {e['description']}")
            log(f"  · {e['name']}  [{e['type']}]  {e['description']}")
        print(f"\n--- 关系 / 三元组（{len(all_triples)} 条）---")
        log(f"\n--- 关系 / 三元组（{len(all_triples)} 条）---")
        for t in all_triples:
            kw = ", ".join(t.get("keywords", []))
            print(f"  · {t['head']} --({kw})--> {t['tail']}  [强度 {t.get('strength', 1)}]")
            log(f"  · {t['head']} --({kw})--> {t['tail']}  [强度 {t.get('strength', 1)}]")

        log(f"\n--- 内容级关键词（{len(all_keywords)} 个）---")
        log("  " + ", ".join(all_keywords))

        log("\n" + sep)
        print(f"测试完成：{len(result.chunks)} 个 chunk，{len(all_entities)} 实体，{len(all_triples)} 关系")
        log(f"测试完成：{len(result.chunks)} 个 chunk，{len(all_entities)} 实体，{len(all_triples)} 关系")
        log(sep)
    except Exception:
        log("\n=== 异常 ===\n")
        log(traceback.format_exc())


if __name__ == "__main__":
    main()
