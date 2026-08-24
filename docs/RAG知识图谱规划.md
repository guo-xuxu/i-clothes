# 知识图谱 + 向量混合 RAG 实施规划（待启动）

> **状态**：设计方向已确认，**未排期**。启动条件：双服务迁移 PR 合并到 `main` 后，
> 从 `main` 拉新分支 `feat/knowledge-graph-rag` 开工。
> 关联：本规划是 `docs/superpowers/specs/2026-08-17-springboot-migration-design.md`
> 的后续功能规划；开工前据此另立 spec 与实施计划。

## 0. 为什么现在不做

双服务迁移（Java 业务后端 + Python 无状态 AI-Agent）刚落地，当前优先事项是
**把现有进度稳定下来、测试守住、PR 合并**。RAG 是新功能，等基座稳定后从干净的
`main` 分支开始，避免在未合并的迁移分支上叠加风险。

## 1. 目标与范围

**目标**：用户可上传穿搭知识文档 → 系统工程化构建**知识图谱 + embedding 向量库**
并**落盘** → 在线问答时做**图谱+向量混合召回**，增强 AI 回答的专业性。

**本期明确不做**：用户历史个性化检索、多租户、Neo4j 迁移、前端管理页（API 先行）。

## 2. 总体架构（已确认的决策）

```
【上传】用户端 → Java（对外唯一入口，遵循现有原则）
   POST /api/knowledge/documents  → 存 knowledge_documents 表 → 触发异步构建

【构建】Python 工程化流水线（离线/异步）
   文档 → 分节 → DeepSeek 抽取三元组 (实体, 关系, 目标)
        → 实体规范化（同义合并：西服/西装）→ networkx 建图 → graph.json 落盘
   文档 → 切块 → 千问 text-embedding-v3 → PG knowledge_chunks(float8[]) 落盘

【召回】在线（LangGraph 新增节点 retrieve_context，推荐+闲聊都走）
   query → 实体抽取 → 图遍历 1-2 跳 → 关系上下文
   query → embedding → 向量 top-3 → 文本上下文
   → 两路拼接 → 【参考知识】段 → 拼进 chat_reply / recommend_outfit 的 prompt
```

| 决策点 | 结论（已确认） |
|---|---|
| 检索方案 | **图谱 + 向量混合**（微软 GraphRAG / LightRAG 成熟做法） |
| 建图方式 | **LLM 离线抽取**（DeepSeek） |
| 图谱存储 | **networkx + graph.json 落盘**（MVP）；未来量级上来再评估 Neo4j |
| 向量存储 | **现有 PG + float8[] 列 + Python 余弦**（实测 pgvector 未安装；千级 chunk 内毫秒级，超 5k chunk 再升级 pgvector/Milvus） |
| Embedding | 千问 `text-embedding-v3`（已实测可用，dim=1024） |
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

### 3.2 工程化构建（Python `knowledge/` 包）

```
knowledge/
  docs/               # 内置示例知识文档（3-5 篇：色彩/场合/体型/风格/面料）
  graph_builder.py    # 文档 → 三元组抽取（DeepSeek）→ 实体规范化 → networkx → graph.json
  vector_builder.py   # 文档切块 → embedding → 写 PG knowledge_chunks
  graph_store.py      # 图加载/序列化（启动时载入内存缓存，重建后刷新）
  vector_store.py     # PG 读写（asyncpg/psycopg），余弦检索 top-k
  retriever.py        # 混合召回：图遍历 1-2 跳 + 向量 top-3 → 拼接上下文
```

**落盘清单（"图谱库和 embedding 落盘"的具体形态）：**
1. `knowledge/graph/graph.json` — 知识图谱（节点/边 + 构建元数据），
   可选追加 `knowledge/graph/history/` 留构建历史
2. PG 表 `knowledge_chunks` — 文本块 + `float8[]` 向量 + 来源
3. PG 表 `knowledge_documents` — 上传原文与构建状态（状态机，幂等）

**幂等与更新策略（v1 简单可靠）**：新增/更新文档 → 全量重建图 + 重写向量表
（知识库小，重建秒级）；重复上传同一文档 → 覆盖 + 重建。

### 3.3 在线召回（LangGraph 新节点 `retrieve_context`）

插入位置：`intent_router` 之后、`chat_reply`/`recommend_outfit` 之前。
```
状态里新增字段：state["rag_context"] = "【参考知识】\n- 婚礼 → 正式/西装/礼服\n- ..."
两个 prompt 增加"可引用以下参考知识"指示。
```
**契约不变、Java 零改动、Python 保持无状态**（图是构建产物读入内存的只读缓存，
不是跨请求状态；向量库是共享 PG）。

## 4. 数据模型（PG，新增，只归知识子系统）

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

CREATE TABLE knowledge_chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    embedding   float8[] NOT NULL,   -- v1 无 pgvector：Python 侧余弦
    source      TEXT
);
CREATE INDEX idx_knowledge_chunks_doc ON knowledge_chunks(document_id);
```

## 5. 里程碑与工作量

| 里程碑 | 内容 | 估计 |
|---|---|---|
| M0 | 上传接口 + documents 表 + 状态机 + Java MockMvc 测试 | ~0.5 天 |
| M1 | graph_builder + vector_builder + 落盘 + dry-run 脚本 + 知识文档样例 | ~1 天 |
| M2 | retrieve_context 节点接入 chat/recommend + 混合拼接 + Python 单测（mock 抽取/embedding） | ~0.5 天 |
| M3 | 端到端验收（上传→构建→问答引用知识）+ 调优（top-k/跳数/拼接格式） | ~0.5 天 |
| 合计 | | ~2.5 天 |

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
| LLM 抽取质量不稳 | 实体规范化（同义合并）是图谱质量关键；M1 提供 dry-run 人工检查图谱 JSON |
| float8[] 全表余弦随知识量线性变慢 | 千级 chunk 毫秒级；>5k chunk 升级 pgvector 或 Milvus（路径已明确） |
| 上传→构建异步化 | MVP 后台线程即可；量大换 Redis 队列（基础设施已有） |
| 构建失败无感知 | 状态机 + `error` 字段 + Java 侧日志；验收覆盖 failed 路径 |
| 成本 | 建图离线一次性（DeepSeek 批量，几十块）；在线每条消息多一次 embedding（便宜）+ 一次实体抽取（小调用） |

## 8. 启动清单（PR 合并后）

1. 从 main 拉 `feat/knowledge-graph-rag`
2. 本规划 → 正式 spec（`docs/superpowers/specs/`）+ 实施计划（`docs/superpowers/plans/`）
3. 按 M0→M3 执行（Subagent-Driven 或单实施者+评审，届时定）
4. 验收通过后合并，回归测试守住
