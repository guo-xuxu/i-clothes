"""实体归一化：L1 字符串归一 + L2 同义词典（零成本、可扩展）。

职责（见 app/knowledge/IMPLEMENTATION.md 3.2）：
- L1 字符串归一：去首尾空白、折叠内部空白、全角转半角（NFKC）；
- L2 同义词典：别名 → 规范名映射（从 synonyms.json 加载，递归防环）；
- 可扩展：register_normalizer 追加 L1 规则、register_synonyms 运行时补映射。

设计原则：
- 纯函数、不调用 LLM、无 IO 依赖（词典加载一次）；
- 词典从 JSON 文件加载，改文件即可改映射，无需改代码；
- 作为 EntityMerger 的第一道归并（边抽边并的最廉价环节）。
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Callable

from app.knowledge.config import SYNONYMS_PATH


class EntityNormalizer:
    """实体归一化器（L1 规则管道 + L2 同义词典）。"""

    def __init__(self, synonym_path: str | Path | None = SYNONYMS_PATH):
        # L1 归一规则管道（按顺序依次应用）。
        self._normalizers: list[Callable[[str], str]] = [
            self._normalize_whitespace,
            self._normalize_fullwidth,
        ]
        # L2 同义映射 {别名: 规范名}。
        self._synonyms: dict[str, str] = {}
        # 词典文件路径（persist 时写回；None 表示不落盘）。
        self._synonym_path: Path | None = Path(synonym_path) if synonym_path is not None else None
        if synonym_path is not None:
            self._load_synonyms(synonym_path)

    # ------------------------------------------------------------------
    # L1 规则
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """折叠连续空白为单个空格。"""
        return " ".join(text.split())

    @staticmethod
    def _normalize_fullwidth(text: str) -> str:
        """全角转半角（NFKC，如 Ａ→A、１２→12、全角标点→半角）。"""
        return unicodedata.normalize("NFKC", text)

    def _apply_l1(self, text: str) -> str:
        current = text.strip()
        for fn in self._normalizers:
            current = fn(current)
        return current

    # ------------------------------------------------------------------
    # 扩展接口
    # ------------------------------------------------------------------
    def register_normalizer(self, fn: Callable[[str], str]) -> None:
        """追加一条 L1 归一规则（如以后加简繁转换）。"""
        self._normalizers.append(fn)

    def register_synonyms(self, mapping: dict[str, str]) -> None:
        """运行时补充同义映射（key/value 会先做 L1 归一）。"""
        for alias, canonical in mapping.items():
            a = self._apply_l1(alias)
            c = self._apply_l1(canonical)
            if a and c and a != c:
                self._synonyms[a] = c

    # ------------------------------------------------------------------
    # L2 词典加载
    # ------------------------------------------------------------------
    def _load_synonyms(self, path: str | Path) -> None:
        p = Path(path)
        if not p.is_file():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            self.register_synonyms(data)

    def persist(self, path: str | Path | None = None) -> None:
        """把当前同义映射写回词典文件（合并新增的同义关系沉淀，词典自增长）。

        Args:
            path: 目标路径；默认写回构造时传入的 synonym_path。
        """
        target = Path(path) if path else self._synonym_path
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        # sort 保证输出稳定，便于 diff 与人工 review。
        target.write_text(
            json.dumps(dict(sorted(self._synonyms.items())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # 归一
    # ------------------------------------------------------------------
    def normalize(self, name: str) -> str:
        """归一化实体名：先 L1 字符串归一，再 L2 词典递归上溯（防环）。

        Returns:
            规范名；无映射时返回 L1 归一后的名字。
        """
        current = self._apply_l1(name)
        seen: set[str] = set()
        while current in self._synonyms and current not in seen:
            seen.add(current)
            current = self._synonyms[current]
        return current
