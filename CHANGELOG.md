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

## [Unreleased] - 开发中

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

### v0.1.0 (计划中)
**目标**：实现 MVP 基础功能
- 后端框架搭建（FastAPI）
- 前端上传界面
- 千问 API 集成
- Docker 配置
- 部署脚本

### v0.2.0 (计划中)
**目标**：完整推荐功能
- DeepSeek API 集成
- 图片识别功能
- 生图功能
- 结果展示优化

### v0.3.0 (计划中)
**目标**：场景增强
- 季节判断
- 主题穿搭
- UI/UX 优化

---

**文档维护**：每次代码提交前更新此文档  
**最后更新**：2026-08-25
