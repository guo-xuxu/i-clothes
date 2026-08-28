"""已导入文档登记表（幂等）：记录哪些文档已抽取入图，支持增量跳过。

落盘位置：app/knowledge/data/processed_docs.json

结构：
{
  "version": 1,
  "documents": {
    "body-shape/梨形身材的修饰.md": {
      "hash": "sha256:...",
      "dimension": "body-shape",
      "processed_at": "2026-08-27T11:30:00",
      "chunks": 3,
      "entities": 45,
      "triples": 40
    }
  }
}

判断「已处理」的依据：相对路径 + 内容哈希。
文档内容改动 → 哈希变化 → 判定为未处理 → 重新抽取入图。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class ProcessedDocRegistry:
    """已导入文档登记表。

    用法：
        registry = ProcessedDocRegistry(DATA_DIR / "processed_docs.json")
        if registry.is_processed(rel_path, content_hash):
            ...  # 跳过
        registry.mark(rel_path, content_hash, dimension=..., chunks=..., entities=..., triples=...)
        registry.save()
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._records: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------
    def _load(self) -> None:
        """从文件加载登记表；文件不存在或损坏时视为空表。"""
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._records = data.get("documents", {})
        except (json.JSONDecodeError, OSError):
            self._records = {}

    def save(self) -> None:
        """将登记表序列化落盘（覆盖写）。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "documents": self._records}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # 查询与记录
    # ------------------------------------------------------------------
    def is_processed(self, rel_path: str, content_hash: str) -> bool:
        """判断某文档是否已抽取入图且内容未变化。

        Args:
            rel_path: 文档相对 docs 根目录的路径（如 "body-shape/梨形.md"）。
            content_hash: 文档内容的 sha256 十六进制串。

        Returns:
            True 表示已处理且内容未变（可跳过）。
        """
        rec = self._records.get(rel_path)
        return bool(rec) and rec.get("hash") == content_hash

    def mark(
        self,
        rel_path: str,
        content_hash: str,
        *,
        dimension: str | None,
        chunks: int,
        entities: int,
        triples: int,
    ) -> None:
        """登记一篇已处理的文档（覆盖写同路径旧记录）。"""
        self._records[rel_path] = {
            "hash": content_hash,
            "dimension": dimension,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "chunks": chunks,
            "entities": entities,
            "triples": triples,
        }

    def __len__(self) -> int:
        return len(self._records)
