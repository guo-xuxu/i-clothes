# 知识图谱 + 向量混合 RAG 实施规划（已启动）

> **状态**：**已启动，离线构建链路已落地**。在 `feat/knowledge-graph-rag` 分支实现中。
> 已完成：文档读取 → 切块 → DeepSeek 联合抽取 → 实体归并 → networkx 建图 →
> graph.json 落盘；实体/chunk embedding → Chroma 落盘；增量幂等构建。
> 待接入：在线混合召回（retrieve_context 节点）与上传接口。
> 详细实现记录见 `app/knowledge/IMPLEMENTATION.md`（**临时文档**，本规划为长期权威）。

## 0. 实现进展

（原「为什么现在不做」已过期，改为记录当前进展）

离线构建链路已完成并端到端验证（已入库 12 篇：图 359 节点 / Chroma 359 实体向量 +
25 chunk 向量，三方对齐）。核心模块见 §3.2；剩余工作为在线召回（§3.3）与上传接口（§3.1）。

## 1. 目标与范围

**目标**：用户可上传穿搭知识文档 → 系统工程化构建**知识图谱 + embedding 向量库**
并**落盘** → 在线问答时做**图谱+向量混合召回**，增强 AI 回答的专业性。

**本期明确不做**：用户历史个性化检索、多租户、Neo4j 迁移、前端管理页（API 先行）。

## 2. 总体架构（已确认的决策）

```
【上传】用户端 → Java（对外唯一入口，遵循现有原则）
   POST /api/knowledge/documents  → 存 knowledge_documents 表 → 触发异步构建

【构建】Python 工程化流水线（离线/异步）
   文档 → 切块 → DeepSeek 联合抽取三元组 (实体, 关系, 关键词)
        → 实体归并（L1/L2 + 向量候选 + LLM 判定）→ networkx 建图 → graph.json 落盘
   文档 → 切块 → 千问 text-embedding-v3 → Chroma（实体 + chunk 向量）落盘

【召回】在线（LangGraph 新增节点 retrieve_context，推荐+闲聊都走）
   query → 实体抽取 → 图遍历 1-2 跳 → 关系上下文
   query → embedding → 向量 top-3 → 文本上下文
   → 两路拼接 → 【参考知识】段 → 拼进 chat_reply / recommend_outfit 的 prompt
```

| 决策点 | 结论（已确认） |
|---|---|
| 检索方案 | **图谱 + 向量混合**（微软 GraphRAG / LightRAG 成熟做法） |
| 建图方式 | **LLM 离线抽取**（DeepSeek，单 chunk 联合抽取实体+关系+关键词） |
| 图谱存储 | **networkx + graph.json 落盘**（MVP）；未来量级上来再评估 Neo4j |
| 向量存储 | **Chroma**（本地持久化 + 自带余弦检索）；最初方案 PG `float8[]` 因无 pgvector、需手写余弦而弃用 |
| Embedding | 千问 `text-embedding-v3`（已实测可用，dim=1024，单次 batch ≤10 自动分批） |
| 实体归并 | **边抽边并**：L1 字符串归一 + L2 同义词典（`synonyms.json`，归并结果回写、词典自增长）+ 同维度向量检索候选 + LLM 判定（阈值 distance<0.20） |
| 实体编号 | 整数自增 eid，作为「图节点 ↔ 实体向量」的统一关联键（内存 hashmap，从 graph.json 重建） |
| 增量构建 | `processed_docs.json` 登记「相对路径 + 内容 sha256」，已处理且内容未变则跳过 |
| 边界 | 用户数据归 Java；知识数据（文档/图/向量）归知识子系统（Python 主理、Java 收口上传） |
| 分支 | 迁移 PR 合并后从 main 拉 `feat/knowledge-graph-rag` |

## 3. 功能模块设计

### 3.1 知识文档上传接口（暴露到用户端）

**对外（Java，契约草案）：**

| 接口 | 方法 | 说明 |
|---|---|---|
| `POST /api/knowledge/documents` | POST | multipart：`title` + `file`(.md/.txt) 或 `content` 文本 → 校验（≤1MB、文本格式）→ 落库 → 触发构建 → `{"id","status":"pending"}` |
| `GET /api/knowledge/documents/{id}` | GET | `{"id","title","status","error?","created_at","updated_at"}`，status: `pending\|building\|ready\|failed` |
| `GET /api/knowledge/documents` | GET | 列表（状态 + 时间倒序） |

**Java ↔ Python（对内）：** `POST /api/agent/knowledge/build`，请求
`{"document_id", "content"}` → Python 执行构建，完成/失败后回写状态
（或 Java 轮询状态，MVP 用"Python 同步构建 + Java 异步触发"最简方案，量大再上 Redis 队列）。

### 3.2 工程化构建（Python `app/knowledge/` 包）

```
app/knowledge/
  config.py                 # 路径 / 切块 / 归并参数（阈值、top-k）集中配置
  docs/                     # 内置知识文档（9 维度 × 5 篇）
  data/                     # 构建产物落盘目录
    graph/graph.json        # 知识图谱（节点/边 + 构建元数据）
    chroma/                 # Chroma 向量库（entities + chunks 两个 collection）
    processed_docs.json     # 已处理文档登记表（增量幂等）
    synonyms.json           # 同义词典（归并结果回写，词典自增长）
  build/                    # 离线构建流水线
    document_reader.py      # 扫描 docs/、按子目录推断 9 大维度
    text_chunk.py           # langchain RecursiveCharacterTextSplitter 切块
    document_processor.py   # 逐 chunk 调度联合抽取
    entity_normalizer.py    # L1 字符串归一 + L2 同义词典（可扩展接口）
    entity_merger.py        # 边抽边并：同维度向量候选 + LLM 判定
    import_registry.py      # 增量登记表（路径 + sha256）
    import_all.py           # 全量导入入口（抽取→归并→入图→落盘→登记）
    extract/
      graph_extractor.py    # DeepSeek 联合抽取（实体+关系+关键词）
      graph_builder.py      # 三元组入 networkx 图（实体编号、自环过滤、load）
  retrieve/                 # 在线召回
    vector_store.py         # Chroma 读写 + 余弦检索（实体/chunk）
    graph_store.py          # 图加载/序列化
    retriever.py            # 混合召回（图遍历 + 向量，待实现）
```

**落盘清单（"图谱库和 embedding 落盘"的具体形态）：**
1. `data/graph/graph.json` — 知识图谱：节点含 `{id, eid, type, description, dimension, sources, aliases}`，边含 `{head, relation, tail, strength, keywords}`
2. `data/chroma/` — Chroma 向量库：`entities`（id=eid，与图节点关联）+ `chunks`（按 document_id）两个 collection
3. `data/processed_docs.json` — 已处理文档登记表（「相对路径 + 内容 sha256」，幂等判断）
4. `data/synonyms.json` — 同义词典（L2 归并 + LLM 归并结果回写，词典自增长）

**幂等与更新策略（增量幂等）**：每篇文档用「相对路径 + 内容 sha256」判断——已处理且
内容未变则跳过；内容变了哈希变，自动重抽。采用**边抽边并**：每篇抽取后立即归并入图
（L1/L2 归一 + 同维度向量候选 + LLM 判定），不做全量重建。

### 3.3 在线召回（LangGraph 新节点 `retrieve_context`）

插入位置：`intent_router` 之后、`chat_reply`/`recommend_outfit` 之前。
```
状态里新增字段：state["rag_context"] = "【参考知识】\n- 婚礼 → 正式/西装/礼服\n- ..."
两个 prompt 增加"可引用以下参考知识"指示。
```
**契约不变、Java 零改动、Python 保持无状态**（图是构建产物读入内存的只读缓存，
不是跨请求状态；向量库是共享 PG）。

## 4. 数据模型（知识子系统）

**PG（仅上传接口的状态机，归 Java 主理）：**

```sql
CREATE TABLE knowledge_documents (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    status     VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending|building|ready|failed
    error      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**向量与图谱（归 Python 知识子系统，不落 PG 表）：**

- 图谱：`data/graph/graph.json`（networkx 序列化，节点/边含完整属性）
- 实体向量：Chroma `entities` collection（id = eid，与图节点关联）
- 文本块向量：Chroma `chunks` collection（按 document_id 组织）

> 原 `knowledge_chunks` 表（PG `float8[]` 自算余弦）已弃用，改由 Chroma 持久化（自带余弦检索）。

## 5. 里程碑与工作量

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 上传接口 + documents 表 + 状态机 + Java MockMvc 测试 | 待做 |
| M1 | 抽取 + 建图 + 实体归并 + embedding + 落盘 + 增量幂等 + 知识文档（45 篇） | ✅ 已完成（离线构建链路） |
| M2 | retrieve_context 节点接入 chat/recommend + 混合拼接 + Python 单测（mock 抽取/embedding） | 待做 |
| M3 | 端到端验收（上传→构建→问答引用知识）+ 调优（top-k/跳数/拼接格式） | 待做 |

## 6. 测试与验收

- **Java**：上传接口 MockMvc（校验 / 状态机 / 触发构建 mock）；`knowledge_documents` CRUD 集成测试
- **Python**：契约测试 mock 抽取与 embedding（不花钱）；图遍历单测（一跳/二跳/孤立实体）；
  构建脚本 dry-run（不写库、不调 LLM）
- **端到端验收**：上传一篇"婚礼着装"文档 → 构建 ready → 问"参加婚礼穿什么" →
  回复引用图谱关系（婚礼→西装）与向量细节（面料建议）；问无关问题不引用
- **回归**：现有 Java 42 + IT 2 + Python 9 全绿，契约键名/错误格式不回归

## 7. 风险与权衡

| 风险 | 对策 |
|---|---|
| LLM 抽取质量不稳 | 实体归并（L1/L2 + 向量候选 + LLM 判定）是图谱质量关键；已提供 dry-run 与全量后人工 review |
| 向量检索随知识量变慢 | Chroma 自带 HNSW 索引，千级向量毫秒级；量级上来再评估 Qdrant/Milvus |
| 上传→构建异步化 | MVP 后台线程即可；量大换 Redis 队列（基础设施已有） |
| 构建失败无感知 | 状态机 + `error` 字段 + Java 侧日志；验收覆盖 failed 路径 |
| 成本 | 建图离线一次性（DeepSeek 批量，几十块）；在线每条消息多一次 embedding（便宜）+ 一次实体抽取（小调用） |

## 8. 启动清单（PR 合并后）

1. 从 main 拉 `feat/knowledge-graph-rag`
2. 本规划 → 正式 spec（`docs/superpowers/specs/`）+ 实施计划（`docs/superpowers/plans/`）
3. 按 M0→M3 执行（Subagent-Driven 或单实施者+评审，届时定）
4. 验收通过后合并，回归测试守住
