# 变更日志

本文档记录 i-clothes 项目的所有代码修改和版本变更。

## 格式说明

每个版本包含：
- **版本号**：遵循语义化版本（major.minor.patch）
- **发布日期**
- **变更类型**：Added（新增）、Changed（修改）、Fixed（修复）、Removed（移除）
- **影响文件**：列出所有修改的文件
- **变更原因**：说明为什么要做这个修改

---

## [1.0.0] - 2026-08-31（v1 发布：RAG 在线检索 + 流式输出 + 双服务生产部署）

### Added
- 创建 PRD.md - 产品需求文档
- 创建 CHANGELOG.md - 版本变更记录文档
- 搭建后端框架（FastAPI）：配置模块、上传接口、健康检查、静态资源服务
- 搭建前端上传界面（原生 HTML/CSS/JS）：支持点击/拖拽上传、预览、文字说明
- 引入 LangGraph 作为 agent 工作流框架，穿搭推荐以状态图（StateGraph）组织
- 集中式模型 provider（`app/providers.py`）：所有大模型客户端在此构造
- 千问多模态接入：通过 `ChatOpenAI` 指向 DashScope OpenAI 兼容端点
- 后端分层骨架：`app/api/routers/`（接口层）、`app/services/`（业务层）、
  `app/repositories/`（数据访问层，含 `base.py` Repository 抽象基类、
  `model_repo.py` 模型仓库）

### Changed
- 千问调用逻辑从直连 httpx 改造为 LangGraph 节点 + 集中 provider
- `main.py` 由直接调用服务改为调用工作流 `run_recommendation`
- 分层重构：`main.py` 路由拆至 `app/api/routers/`，业务编排收敛到
  `app/services/recommendation.py`，`app/providers.py` 迁至
  `app/repositories/model_repo.py`（`ModelRepository`），graph 节点改从仓库取模型
- 前端从原生 HTML/JS 升级为 Vite + Vue3 + Element Plus（对话式界面）
- **架构决策**：由"Java 全量重写 Python 后端"改为**双服务架构**——Java 业务后端
  （Spring Boot：CRUD + 并发 + Redis + 限流）承接前端契约，Python 收敛为
  **无状态 AI-Agent 服务**（仅保留推理，移除会话管理）；设计文档
  `docs/superpowers/specs/2026-08-17-springboot-migration-design.md` 更新至 v2，
  PRD.md 更新至 v2.0

### Added
- 对话式聊天界面（DeepSeek/豆包风格）：左侧会话列表 + 右侧聊天区，
  支持多轮对话、图片附件、会话新建/切换/删除、自动起标题
- 意图路由节点 `app/graph/nodes/intent_router.py`：纯关键词规则判断
  "推荐 vs 闲聊"，有图一律走推荐
- 闲聊节点 `app/graph/nodes/chat_reply.py`：DeepSeek 多轮对话
- 无照片纯文字推荐：推荐分支无图时跳过体征分析，直接按文字推荐
- 会话接口：`POST/GET/DELETE /api/conversations`、`GET /api/conversations/{id}`、
  `POST /api/chat`（多轮）
- 内存会话存储 `app/services/conversation_store.py`（MVP，重启丢失，
  后续迁正式 DB）
- 前端生产构建产物由 FastAPI 伺服（`frontend/dist`），开发时 Vite
  代理 `/api` 到后端

### Removed
- `app/services/qianwen.py`（逻辑迁移至 `app/graph/` 与 `app/providers.py`）
- `app/providers.py`（逻辑迁移至 `app/repositories/model_repo.py`）

### Changed
- 架构重构为双服务：Java 业务后端（Spring Boot 3.5.3 + MyBatis-Plus + Redis，
  会话 CRUD/并发锁/限流）+ Python 无状态 AI-Agent 服务（FastAPI + LangGraph）
- 会话持久化：内存存储 → PostgreSQL（重启不丢）；新增 Redis 会话写锁与限流

### Added
- Python `/api/agent/chat` 无状态契约接口（Java 调用，不落库）
- Java 7 端点（health/recommend/conversations CRUD/chat）逐字节兼容前端
- Docker compose 四件套交付物（pg + redis + python + java）

### Removed
- Python `app/services/`（会话存储/编排）、`/api/chat`、`/api/recommend` 路由
  （职责移交 Java；AI 推理逻辑完整保留）

### Added
- 知识子系统 `app/knowledge/`：穿搭知识的知识图谱构建与混合检索（RAG）骨架，
  规划见 `docs/RAG知识图谱规划.md`
- 知识文档读取器 `app/knowledge/build/document_reader.py`：递归扫描 `docs/`
  下 `.md`/`.txt`，按子目录推断 9 大知识维度（廓形/身材/面料/风格/图案/配饰/场合/颜色/肤色），
  输出统一 `Document` 结构
- 内置知识文档目录 `app/knowledge/docs/`：9 维度子目录 + `README.md`（维度约定
  与 RAG 写作要求），首个样例文档 `silhouette/穿搭公式.md`
- 落盘目录 `app/knowledge/data/`（图谱 `graph.json` / 历史快照 / 切块中间产物）
- 检索骨架 `app/knowledge/retrieve/`：`graph_store.py`（networkx 图加载/序列化）、
  `vector_store.py`（PG `knowledge_chunks` 余弦检索）、`retriever.py`（图遍历 + 向量混合召回）
- `ModelRepository.get_deepseek_extractor()`：知识图谱三元组抽取专用模型
  （temperature=0 + 长超时，用于结构化、确定性抽取）
- `docs/RAG知识图谱规划.md`：图谱 + 向量混合 RAG 实施规划（上传接口契约、
  离线建图流水线、在线召回节点、PG 数据模型、里程碑 M0-M3）
- 实体归一 `build/entity_normalizer.py`：L1 字符串归一（去空白/全角转半角 NFKC）+
  L2 同义词典（`data/synonyms.json`，可扩展接口 register_normalizer / register_synonyms）
- 实体归并 `build/entity_merger.py`：边抽边并——同维度向量检索 top-k + 阈值过滤 +
  LLM 判定（1 新实体 vs 多候选，Agno 结构化输出）；归并结果回写词典（词典自增长）
- 增量导入 `build/import_all.py` + 登记表 `build/import_registry.py`：
  「相对路径 + 内容 sha256」幂等判断，已处理且内容未变的文档跳过
- 千问 embedding `QianwenEmbedder`（`repositories/model_repo.py`）：openai 客户端直连
  `text-embedding-v3`（1024 维，自动分批）
- 实体编号 eid：图节点整数自增编号，作为「图节点 ↔ 实体向量」的统一关联键

### Changed
- 向量存储由 PG `float8[]`（自算余弦）改为 **Chroma**（`retrieve/vector_store.py`）：
  实体向量（id=eid 关联图节点）+ chunk 向量两个 collection，自带余弦检索与持久化

### Fixed
- 自环边过滤：实体归并后 head==tail 的边（如「A型体型--相似-->梨形身材」归并成自环）
  在图构建时跳过
- chromadb 跨进程索引丢失：数据量 < 默认 `hnsw:sync_threshold`(1000) 时 HNSW 索引
  不落盘、进程退出即丢，collection metadata 设 `hnsw:sync_threshold=3` 强制进程内落盘

### Added
- 入库接口 `app/knowledge/service.py` + `app/api/routers/knowledge.py`：
  `POST /api/knowledge/import`（后台线程增量入库，单飞——已在跑返回 409；body 可选
  `{"paths": [...]}`，缺省全量扫描）+
  `GET /api/knowledge/import/status`（`idle|running|failed` + 最近一次 `last_stats`）
- 全量入库完成：46 篇知识文档 → 图谱 **1277 节点 / 1900 边**、实体向量 1277（与图节点
  1:1 对齐）、chunk 向量 89，9 大维度全覆盖；耗时约 1 小时 10 分（新增 33 / 跳过 13 / 失败 0）

### Changed
- `app/knowledge/data/`（图谱 / Chroma / 登记表 / 同义词典，构建产物）移出 git 跟踪并加入
  `.gitignore`——可随时经 `POST /api/knowledge/import` 重建；同时清理误提交的
  `.git.bak-*`、`.workbuddy/` 目录

### Added
- 意图分析节点 `app/graph/nodes/query_analyzer.py`：对每条消息输出 intent（outfit/match/style/color/chat）
  + dimension（9 大知识维度 + general，闲聊也归类）+ photo_type（全身/半身/大头/unknown）
  + 必要信息（体型/肤色/脸型/当前穿着/场合）；有图走千问多模态一次调用（Pydantic 校验、fail-open），
  无图走关键词规则（零成本）

### Changed
- `intent_router.py`（关键词 recommend|chat 二分类）与 `analyze_appearance.py` 合并进
  `query_analyzer.py`——对外契约不变（响应 intent 仍为 recommend|chat，前端零改动），
  新字段（intent_detail/dimension/photo_type/analysis）只在内部流转，供后续检索消费

### Added
- 查询改写节点 `app/graph/nodes/query_rewriter.py`（检索前置）：DeepSeek 把用户问题改写成检索查询
  `{query, keywords}`——代词指代消解（结合会话历史）+ 规范/同义表达 + 保留核心检索词；
  输入带意图/维度定向；chat 意图跳过（不检索不花钱）；失败回退原文（fail-open）

### Added
- 在线混合召回（检索链路接通）：
  - `retrieve/graph_store.py`：graph.json 加载 + 内存缓存（只读，构建后 reload）+ 实体子串匹配
    （查询文本 + 改写关键词双通道）+ 出/入边 1-2 跳去重遍历
  - `retrieve/retriever.py`：混合召回——图路（2 跳关系上下文）+ 向量路（改写查询 embedding →
    Chroma chunk top-k，余弦距离阈值 0.5 + **维度白名单过滤**，维度由 intent/照片类型推导）；
    任一路失败降级（fail-open）
  - `graph/nodes/retrieve_context.py`：LangGraph 召回节点，输出 `state["rag_context"]`；
    `recommend_outfit` prompt 注入【参考知识】段（无关则忽略）
- 可观测：`app/main.py` 启用应用 INFO 日志（意图分析/在线召回/改写调用在服务端控制台可见）

### Added
- **流式输出（SSE）**：
  - Python `POST /api/agent/chat/stream`：`workflow.astream(stream_mode=["messages","updates"])`
    逐 token 输出（仅转发生成节点 chat_reply/recommend_outfit），done 事件携带 intent；
    intent 从 query_analyzer 的 updates 输出获取（不重跑工作流）
  - Java `POST /api/chat/stream`：SseEmitter + JDK `java.net.http.HttpClient` 流式代理，
    虚拟线程执行；done 后按非流式相同事务落库并推送 `{conversation_id, title}` 元数据事件；
    错误/断开 → completeWithError
  - 前端：`api.js.streamChat`（fetch + ReadableStream 解析 SSE）+ `App.vue` 打字机渲染
    （流式光标、内容滚动跟随），会话绑定用元数据事件
  - 兼容：原 `POST /api/chat` / `POST /api/agent/chat` 保留

### Fixed
- **Java→Python 流式 body 丢失（FastAPI 422 missing body）**：JDK `HttpClient` 默认协商
  HTTP/2（ALPN），而 uvicorn/h11 仅支持 HTTP/1.1，协商异常时请求体被丢弃；
  客户端显式 `version(HTTP_1_1)` 修复（非流式 RestClient 本就是 HTTP/1.1 故未触发）
- **流式结束事件缺失**：Java 代理收到 Python `done` 后只落库发元数据、未转发 `done`
  事件，前端判定"流式响应未正常结束"而报错；`onDone` 现在先转发 `{done, intent}`
  再发 `{conversation_id, title}` 元数据
- **前端文字"卡在光标"（响应式更新失效）**：流式占位气泡是 push 前的原始对象，
  直接改其属性不触发 Vue 响应式；改为通过 `messages.value[lastIdx]`（reactive 数组
  索引）更新
- **前端 SSE 解析兼容 Spring 无空格格式**：Spring SseEmitter 输出 `data:{...}`
  （无空格），解析器按 `data:` 前缀 lenient 匹配，Python `data: {...}` 与
  Spring `data:{...}` 均兼容

### Changed
- **生产部署（阿里云 ECS）**：Docker compose 四件套（pg/redis/python/java）上线，
  公网 `http://47.103.144.20:8080`；Docker Hub 不可达 → DaoCloud 镜像加速；
  pip 走阿里云 PyPI 镜像；`.env` 管理密钥；知识库数据挂卷 `knowledge-data` 持久化
- **依赖收敛（部署红线）**：移除 agno 与 arize-phoenix 服务器本体（与 langchain-openai
  的 openai<2 约束物理冲突，Phoenix 追踪保留）；`main.py` 优雅跳过缺失的追踪服务器；
  前端 dist 缺失时跳过静态挂载（Python 容器仅服务 API）
- 知识库数据 `app/knowledge/data/` 曾误入 git 跟踪（`7e241b1`），构建产物保持
  gitignore，可经 `POST /api/knowledge/import` 全量重建（46 篇 / 1277 节点 /
  实体向量 1277 / chunk 向量 89）

**变更原因**：完成 MVP 前 3 步（项目结构、后端、前端）。采用 LangGraph
便于后续扩展 DeepSeek 识别/生图、季节/主题节点；模型调用集中封装，换模型只改一处。
MVP 阶段即确立 api/services/repositories 分层边界，为后续用户信息（SQL）、
向量检索、知识图谱等数据源预留统一接入契约，避免后期推倒重来。
第二轮迭代：将产品从"上传表单"升级为"对话式助手"，新增意图路由（推荐/闲聊）、
多轮会话与前端 Vue3 界面，无照片也可文字推荐。

**影响文件**：
- `PRD.md`、`CHANGELOG.md`（更新）
- `requirements.txt`、`.env.example`、`.gitignore`（新建/更新）
- `app/config.py`、`app/main.py`（新建/更新）
- `app/api/routers/{__init__,health,recommend}.py`、`app/services/{__init__,recommendation}.py`、
  `app/repositories/{__init__,base,model_repo}.py`（新建）
- `app/graph/nodes/{analyze_appearance,recommend_outfit}.py`（import 更新）
- `app/providers.py`（删除）
- `app/api/routers/chat.py`、`app/services/{conversation_store,chat_service}.py`（新建）
- `app/graph/nodes/{intent_router,chat_reply}.py`（新建）
- `app/graph/{state,workflow}.py`（更新）
- `frontend/`（重构为 Vite + Vue3 项目：package.json、vite.config.js、
  `src/{main.js,style.css,api.js,App.vue}`、`src/components/*.vue`）
- `app/knowledge/`（新建：`__init__.py`、`build/{__init__,document_reader,text_chunk}.py`、
  `retrieve/{__init__,graph_store,vector_store,retriever}.py`、
  `docs/`（9 维度子目录 + `README.md` + `silhouette/穿搭公式.md`）、`data/README.md`）
- `app/repositories/model_repo.py`（新增 `get_deepseek_extractor()`）
- `docs/RAG知识图谱规划.md`（新建）
- `app/knowledge/build/{entity_normalizer,entity_merger,import_registry,import_all}.py`（新建）
- `app/knowledge/data/synonyms.json`（新建，同义词典，归并结果回写）
- `app/knowledge/retrieve/vector_store.py`（Chroma 实现，替代 PG 方案）
- `app/knowledge/build/extract/graph_builder.py`（实体编号、自环过滤、load 增量恢复）
- `app/repositories/model_repo.py`（新增 `get_embedding()` / `QianwenEmbedder`）
- `app/config.py`（`QIANWEN_EMBEDDING_MODEL`）、`app/knowledge/config.py`
  （`CHROMA_DIR`、`SYNONYMS_PATH`、`MERGE_THRESHOLD`、`MERGE_TOP_K`）
- `app/knowledge/IMPLEMENTATION.md`（实现方案文档）
- `app/knowledge/service.py`（新增，入库服务：后台线程 + 单飞 + 状态机）
- `app/api/routers/knowledge.py`（新增，`POST /api/knowledge/import` + `GET .../status`）
- `app/main.py`（挂载 knowledge 路由）、`test/test_knowledge_import.py`（新增，契约/状态机测试）
- `.gitignore`（`app/knowledge/data/`、`.git.bak-*/`、`.workbuddy/`）

---

## [0.0.1] - 2026-08-11

### Added
- 初始化 Git 仓库
- 创建 README.md

**变更原因**：项目初始化

**影响文件**：
- `README.md` (新建)
- `.git/` (初始化)

---

## 版本规划

### v1.0.0 ✅ 已发布（2026-08-31）
**目标**：对话式 MVP + 双服务架构 + RAG 知识检索 + 流式输出，生产部署上线
- [x] 后端框架搭建（FastAPI + LangGraph）与前端对话界面（Vue3）
- [x] 双服务架构（Java 业务后端 + Python 无状态 Agent）与 Docker compose 四件套
- [x] 意图分析（5 类意图 + 9 维度 + 照片类型）与查询改写
- [x] 知识图谱 + 向量混合检索（46 篇文档 / 1277 节点，在线召回接入推荐）
- [x] 流式输出（SSE：Python → Java 代理 → 前端打字机）
- [x] 生产部署（阿里云 ECS，公网可访问）

### v1.1.0 (计划中)
**目标**：检索质量与体验优化
- 检索调优：top-k / 距离阈值 / 改写策略按维度差异化
- 推荐质量评估与提示词迭代
- 多模态识别增强（照片信息抽取接入推荐）

### v2.0.0 (计划中)
**目标**：完整推荐与场景增强
- 生图功能
- 季节判断、主题穿搭
- 用户画像与历史记录

---

**文档维护**：每次代码提交前更新此文档  
**最后更新**：2026-08-31
