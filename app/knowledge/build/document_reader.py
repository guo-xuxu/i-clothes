"""文档读取器：扫描 knowledge/docs 目录并读入知识文档。

职责：
- 递归扫描 docs/ 下的 .md / .txt 文件；
- 从文件所在子目录推断其所属「知识维度」；
- 返回统一的 Document 数据结构，供后续 graph_builder / vector_builder 消费。

维度约定（见 docs/RAG知识图谱规划.md 3.1.1 与 knowledge/docs/README.md）：
    目录名 → 维度
    silhouette  → ① 廓形与版型
    body-shape  → ② 身材比例与修饰
    fabric      → ③ 面料与材质
    style       → ④ 风格定位
    pattern     → ⑤ 图案与纹理
    accessory   → ⑥ 配饰与点缀
    occasion    → ⑦ 场合与季节
    color       → ⑧ 颜色搭配
    skin-tone   → ⑨ 肤色与个人色彩
"""
from dataclasses import dataclass
from pathlib import Path

# 目录名 → 维度中文名（用于标注来源，非强制约束）
DIMENSION_NAMES = {
    "silhouette": "廓形与版型",
    "body-shape": "身材比例与修饰",
    "fabric": "面料与材质",
    "style": "风格定位",
    "pattern": "图案与纹理",
    "accessory": "配饰与点缀",
    "occasion": "场合与季节",
    "color": "颜色搭配",
    "skin-tone": "肤色与个人色彩",
}

# 支持的文档扩展名
SUPPORTED_SUFFIXES = {".md", ".txt"}

# 扫描时跳过的文件名（不含扩展名）
SKIP_NAMES = {"README"}


@dataclass
class Document:
    """一篇知识文档的读取结果。

    Attributes:
        path: 文件绝对路径。
        dimension: 所属维度目录名（如 "silhouette"）；非维度目录下的文件为 None。
        dimension_name: 维度中文名；无法识别时为 None。
        title: 文档标题（取文件名去扩展名）。
    """

    path: Path
    dimension: str | None
    dimension_name: str | None
    title: str


class DocumentReader:
    """知识文档读取器：扫描目录并读入文档。

    用法：
        reader = DocumentReader(docs_root)
        docs = reader.scan()          # 读入 docs_root 下全部文档
        docs = reader.read_one(path)  # 读入单个文件
    """

    def __init__(self, docs_root: str | Path = str(Path(__file__).parent.parent / "docs")):
        """初始化读取器。

        Args:
            docs_root: docs 根目录路径（绝对或相对）。
        """
        self.docs_root = Path(docs_root).resolve()

    def scan(self) -> list[Document]:
        """递归扫描 docs_root，读入所有受支持的知识文档。

        Returns:
            Document 列表（按路径排序，保证构建顺序稳定）。
        """
        if not self.docs_root.is_dir():
            raise NotADirectoryError(f"docs 目录不存在: {self.docs_root}")

        docs: list[Document] = []
        for path in sorted(self.docs_root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if path.stem in SKIP_NAMES:
                continue
            docs.append(self._read(path))
        return docs

    def read_one(self, path: str | Path) -> Document:
        """读取单个文档文件。

        Args:
            path: 文档文件路径（绝对或相对）。

        Returns:
            Document 对象。

        Raises:
            ValueError: 文件类型不支持。
            FileNotFoundError: 文件不存在。
        """
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"文件不存在: {p}")
        if p.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"不支持的文件类型: {p.suffix}（仅支持 {SUPPORTED_SUFFIXES}）")
        return self._read(p)

    def read_path(self, target: str | Path) -> list[Document]:
        """读取指定路径：可以是单个文件，也可以是目录。

        Args:
            target: 文件或目录路径。

        Returns:
            Document 列表。
        """
        p = Path(target)
        if p.is_file():
            return [self.read_one(p)]
        if p.is_dir():
            return self.scan_from(p)
        raise FileNotFoundError(f"路径不存在: {p}")

    def scan_from(self, directory: str | Path) -> list[Document]:
        """扫描任意目录（不限于 docs_root），用于导入指定目录。

        维度推断仍以 self.docs_root 为基准。

        Args:
            directory: 目录路径。

        Returns:
            Document 列表。
        """
        d = Path(directory)
        if not d.is_dir():
            raise NotADirectoryError(f"目录不存在: {d}")

        docs: list[Document] = []
        for path in sorted(d.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if path.stem in SKIP_NAMES:
                continue
            docs.append(self._read(path))
        return docs

    def _read(self, path: Path) -> Document:
        """读取单个文件并构造 Document。"""

        dimension = self._infer_dimension(path)
        return Document(
            path=path.resolve(),
            dimension=dimension,
            dimension_name=DIMENSION_NAMES.get(dimension) if dimension else None,
            title=path.stem
        )

    def _infer_dimension(self, path: Path) -> str | None:
        """根据文件相对 docs_root 的路径推断维度目录名。

        仅当文件位于某个已知维度子目录下（或其子目录）时返回维度名，
        否则返回 None（例如文档直接放在 docs 根目录下）。
        """
        try:
            rel = path.resolve().relative_to(self.docs_root)
        except ValueError:
            return None

        parts = rel.parts
        if not parts:
            return None
        top = parts[0]
        return top if top in DIMENSION_NAMES else None


