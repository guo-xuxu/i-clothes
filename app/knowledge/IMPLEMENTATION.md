# 知识子系统（RAG）实现方案

> 状态：讨论定稿，抽取链路已实现，归并/增量/检索待实现  
> 关联：`docs/RAG知识图谱规划.md`（方向）、本模块 `__init__.py`（职责边界）  
> 更新：2026-08-26

本文记录知识图谱 + 向量混合 RAG 的**实现决策**，是 `docs/RAG知识图谱规划.md`  
方向确定后的落地细则。讨论中已定稿的结论以「✅ 已定」标注。

---

## 0. 当前进度

| 模块                                 | 状态                                                 |
| ---------------------------------- | -------------------------------------------------- |
| `build/document_reader.py`         | ✅ 已实现（扫描 docs、推断维度、读文档）                            |
| `build/text_chunk.py`              | ✅ 已实现（langchain RecursiveCharacterTextSplitter 切块） |
| `build/document_processor.py`      | ✅ 已实现（切块 + 联合抽取编排）                                 |
| `build/extract/graph_extractor.py` | ✅ 已实现（Agno+DeepSeek 联合抽取，prompt 已优化）               |
| `build/extract/graph_builder.py`   | ✅ 已实现（networkx 建图、canonicalize、去重、序列化）             |
| `build/import_docs.py`             | ⚠️ 有骨架，增量逻辑待接入                                     |
| `retrieve/*`                       | ⚠️ 空壳（docstring 占位）                                |
| 实体归一（L1/L2）                        | ❌ 待实现                                              |
| 实体归并（L3 LLM 聚类）                    | ❌ 待实现                                              |
| 增量记录（processed_docs.json）          | ❌ 待实现                                              |

---

## 1. 总体架构与数据流

```
[离线构建]  docs/*.md
              │  DocumentReader 扫描（带维度标签）
              ▼
              │  TextChunker 切块（langchain）
              ▼
              │  GraphExtractor 联合抽取（DeepSeek 单次调用）
              │    ├─ 指代消解：藏在 prompt（还原代词）
              │    └─ 实体消歧：挂维度标签
              ▼
              │  EntityNormalizer（L1 字符串归一 + L2 同义词典）
              ▼
              │  GraphBuilder 建图（唯一节点 + 边记来源）→ graph.json
              │  + import_registry 记录已处理文档（幂等）
              ▼
[全量归并]  按维度分桶 → LLM 聚类（L3）→ 回写 aliases/合并节点
              ▼
[在线召回]  retrieve_context：图遍历 1-2 跳 + 向量 top-k → rag_context
```



---

## 2. 抽取层

### 2.1 联合抽取（单次调用）

以单个 chunk 为输入，Agno + DeepSeek 一次产出实体 + 关系 + 内容关键词，  
用 Pydantic 约束输出结构（`ExtractionSchema`）。DeepSeek 不支持 json_schema  
response_format，故关闭 structured outputs，由 output_schema 在解析环节校验。

### 2.2 prompt 设计要点（✅ 已定并落地）

| 点     | 决策                                              |
| ----- | ----------------------------------------------- |
| 编号    | 实体 1-4、关系 5-8、关键词 9（修复了编号重复）                    |
| 实体粒度  | 规则 4：抽「带限定条件的子实体」（如「色彩相近」而非「色彩」），并配 few-shot 样例 |
| 关系词   | **不做白名单**，LLM 自由输出（「先平铺」）                       |
| 关系数量  | 搭配单品**多多益善**，不压制                                |
| 强度区分度 | 核心关系 9-10、泛化关系（搭配单品）5-6，拉开区分度                   |
| 关系映射  | **暂缓**（等全量抽取、关系词收敛后再做归一映射）                      |

### 2.3 指代消解（✅ 已定：藏 prompt）

不做独立模块。在 `_EXTRACT_PROMPT` 增加显式规则：

> 遇到代词（它/这种/前者等），先还原为其实际指代的实体名，再作为实体名输出。

当前结果已隐含处理（直接输出「上松下紧」而非「这种穿法」），只是未显式成文。

---

## 3. 实体消歧与对齐

### 3.1 实体消歧（✅ 已定：维度标签轻做）

穿搭领域同名异义少，不引入重型上下文向量消歧。用 `document_reader` 已推断的  
`dimension` 标签消歧：**只在同一维度内做对齐**，跨维度的同名实体天然不归并。

### 3.2 实体对齐 / 同指归并（三层）

| 层         | 手段                   | 时机    | 成本 |
| --------- | -------------------- | ----- | -- |
| L1 字符串归一  | 全半角、简繁、空白、标点统一       | 入图前实时 | 零  |
| L2 同义词典   | 穿搭领域人工维护初始表（西服→西装）   | 入图前实时 | 低  |
| L3 LLM 聚类 | 全量实体按维度分桶，LLM 输出归并映射 | 全量抽取后 | 中  |

### 3.3 目标：一个节点 + 记录来源（✅ 已定）

同一概念（如「梨形身材」）无论多少写法、来自多少文档，**图里只能有一个节点**；  
冲突/多来源不硬消解，而是**在边上记录来源**。

---

## 4. 知识融合与冲突

### 4.1 关系合并

同 `head-relation-tail` 去重（GraphBuilder 已做），强度取 max 或按来源加权。

### 4.2 冲突策略（✅ 已定：软知识保留多来源）

穿搭知识是软知识（建议类），两篇文档说法矛盾时**不硬性裁决**，保留多条边并记录  
来源，检索时按 strength / 来源排序。不引入事实性知识图谱的冲突裁决机制。

---

## 5. 存储方案

### 5.1 图谱（✅ 已定：networkx + JSON）

networkx 建图 → `graph.json` 落盘 → 检索时整图加载内存（只读缓存，保无状态）。  
**不上数据库、不上 Neo4j**（networkx 无数据库适配器，只有文件格式；规模不需要）。

### 5.2 向量（PG）

文本块 + float8[] 向量写 PG `knowledge_chunks`，Python 侧计算余弦（v1 无 pgvector）。

### 5.3 规模评估（✅ 已定）

- 100 篇文档 ≈ 200-300 chunk、去重后约 1000-2000 实体、2000-3000 边
- networkx 内存占用几 MB，**远低于其能力边界（1 万节点内毫秒级遍历）**
- **真正瓶颈是 LLM 抽取调用次数（100 篇 × 2-3 chunk ≈ 200-300 次）**，不是图存储

---

## 6. 增量构建（幂等）

### 6.1 记录文件

`app/knowledge/data/processed_docs.json`，记录已抽取文档：

```json
{
  "version": 1,
  "documents": {
    "body-shape/梨形身材的修饰.md": {
      "hash": "sha256:...",
      "dimension": "body-shape",
      "processed_at": "2026-08-26T22:58:00",
      "chunks": 3,
      "entities": 45,
      "triples": 40
    }
  }
}
```

### 6.2 判断逻辑（✅ 已定：路径 + 内容哈希）

```
对每篇文档：读内容 → 算哈希 → 查记录
  路径在 && 哈希相同 → 跳过（已抽取、未变化）
  否则 → 抽取 + 建图 + 写记录
```

用「路径 + 内容哈希」而非仅路径，保证文档内容改动后自动重抽。

### 6.3 内容哈希实现（✅ 已定：方案 B）

给 `Document` 加 `content` 字段，`DocumentReader` 读文件时顺手带上，切块与哈希共用，  
避免「记录判断读一次、切块又读一次」的重复 IO。

---

## 7. 数据模型（节点 / 边）

**节点（唯一 id + 别名 + 来源）：**

```json
{
  "id": "梨形身材",
  "type": "身材类型",
  "dimension": "body-shape",
  "aliases": ["梨型身材", "A型身材"],
  "sources": ["几种常见体型的穿搭建议.md", "梨形身材的修饰.md"]
}
```

**边（关系 + 来源）：**

```json
{
  "head": "梨形身材",
  "relation": "适合",
  "tail": "A字裙",
  "strength": 9,
  "sources": ["梨形身材的修饰.md"]
}
```

---

## 8. 待办清单

- [ ] `Document` 加 `content` 字段（方案 B）
- [ ] `EntityNormalizer`（L1 字符串归一 + L2 同义词典文件）
- [ ] `GraphBuilder` 支持节点属性（type/dimension/aliases/sources）+ 边来源
- [ ] `import_registry.py`（ProcessedDocRegistry）+ `import_docs` 增量接入
- [ ] `retrieve/graph_store.py`（加载 graph.json + 一跳/二跳遍历）
- [ ] `retrieve/vector_store.py`（PG chunks 读写 + 余弦 top-k）
- [ ] `retrieve/retriever.py`（混合召回 → rag_context）
- [ ] 全量抽取后：L3 LLM 聚类归并脚本
- [ ] 关系词归一映射（等关系词收敛后）
