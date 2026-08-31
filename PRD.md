# 产品需求文档 (PRD)

## 1. 产品概述

**产品名称**：i-clothes 智能穿搭助手

**产品定位**：基于AI多模态分析的个性化穿搭推荐系统。用户通过**对话式界面**上传参考照片
或文字描述，即可获得专业的穿搭建议；支持多轮对话、意图路由（推荐/闲聊）、
**RAG 知识库增强（知识图谱 + 向量混合检索）**、**流式输出（打字机效果）**与会话管理。

**目标用户**：
- 对穿搭有需求但缺乏灵感的普通用户
- 需要快速解决特定场景穿搭问题的用户

**当前状态**：v1.0.0 已发布（2026-08-31），双服务架构生产部署上线（阿里云 ECS）

## 2. 核心功能

### MVP版本 (v0.1.0)

#### 2.1 照片上传
- 支持上传1-3张参考照片（场景照片、活动照片、风格参考）
- 支持JPG、PNG格式
- 单张照片限制：5MB以内

#### 2.2 文字描述（可选）
- 用户可补充文字说明，如"参加婚礼""日常通勤""约会"
- 字数限制：200字以内

#### 2.3 AI分析与推荐
**分析模型**：
- **千问（通义千问）**：主分析模型
  - 场景识别（正式/休闲/运动等）
  - 风格分析（简约/复古/街头等）
  - 色调提取
  - 氛围感知

**识别与生图模型**：
- **DeepSeek**：辅助模型
  - 识别照片中的具体单品
  - 可选：生成穿搭效果图

#### 2.4 推荐结果展示
- 文字穿搭建议：
  - 整体风格定位
  - 推荐色系
  - 单品建议（上衣、下装、鞋子、配饰）
  - 搭配技巧
- 可选：AI生成的穿搭效果图

#### 2.5 对话式交互（多轮）
- 对话式界面（DeepSeek/豆包风格）：左侧会话列表 + 右侧聊天区
- **意图分析**：每条消息识别 5 类意图（outfit 推荐 / match 搭配 / style 风格 / color 颜色 /
  chat 闲聊）+ 9 大知识维度（廓形/身材/面料/风格/图案/配饰/场合/颜色/肤色，闲聊也归类）
  + 照片类型（全身/半身/大头/unknown）+ 必要信息抽取（体型/肤色/脸型/穿着/场合）；
  有图走千问多模态一次调用，无图走关键词规则（零成本）；对外契约保持 recommend|chat
- **多轮对话**：上下文随会话传递（闲聊 10 条 / 推荐 6 条用户消息）
- **无照片文字推荐**：无图时跳过体征分析，直接按文字描述推荐
- **会话管理**：新建/切换/删除会话、自动标题（首条消息前 20 字符）、
  历史持久化（PostgreSQL，重启不丢）
- 图片附件：输入框直接附加照片（≤3 张），随消息一起分析

#### 2.6 知识库增强（RAG）
- 离线构建：46 篇穿搭知识文档 → LLM 三元组抽取 + 实体归并 + 同义词典 →
  知识图谱（**1277 节点 / 1900 边**）+ Chroma 向量（实体 1277 + 文本块 89），
  增量导入幂等（sha256 登记）
- 在线检索：查询改写（DeepSeek，结合历史消解指代）→ 图谱 2 跳遍历 +
  维度白名单过滤的向量 top-k → `rag_context` 注入推荐 prompt
- 闲聊意图不检索（省成本）；检索任一路失败自动降级（fail-open）

#### 2.7 流式输出（SSE）
- 推荐/闲聊回复逐 token 流式返回，前端打字机效果（流式光标、滚动跟随）
- 链路：Python SSE → Java SseEmitter 代理 → 前端 ReadableStream 解析；
  流结束事件携带 intent，元数据事件绑定会话 id 与标题
- 原同步接口保留（`POST /api/chat` / `POST /api/agent/chat`）

## 3. 技术架构

### 3.1 技术栈（双服务架构）

**前端**：
- Vue3 + Element Plus（Vite 构建）
- 原生 Fetch 调用 `/api/*`，不感知后端语言

**Java 业务后端**（`iclothes-server/`，对外唯一入口）：
- Java 21 + Spring Boot 3.5.3（虚拟线程）
- MyBatis-Plus 3.5.7（ORM）+ PostgreSQL 16（业务数据）+ Flyway（schema 版本）
- Redis（会话写锁 / 限流 / 故障降级）
- RestClient（同步调用 Python Agent）+ JDK HttpClient（**流式 SSE 代理**，
  显式 HTTP/1.1——uvicorn 不支持 HTTP/2）
- 职责：会话/消息 CRUD、并发控制、限流、伺服前端、编排 Agent 调用、流式转发与落库

**Python AI-Agent 服务**（`app/`，无状态推理）：
- Python 3.12（conda 环境，位于项目内 `.conda/`）
- FastAPI + **LangGraph**（状态图编排：query_analyzer → query_rewriter →
  retrieve_context → chat_reply / recommend_outfit）
- LangChain（`ChatOpenAI`）统一接入千问/DeepSeek（OpenAI 兼容端点）
- Phoenix（OTLP 追踪，可观测；部署时服务器本体移除，追踪保留）
- 职责：意图分析（5 类 + 9 维度 + 照片类型）、查询改写（DeepSeek）、多轮闲聊、
  体征分析、穿搭推荐、**知识图谱构建与在线混合检索（RAG）**、
  **SSE 流式输出**（`/api/agent/chat/stream`）
- **无状态**：不落库、不带会话 id，可水平扩展

**基础设施**：
- Docker Compose：postgres + redis + python-agent + java 四件套（生产部署于阿里云 ECS）
- 环境变量管理密钥（`QIANWEN_*`、`DEEPSEEK_*`、`DB_*`）
- 知识库数据挂卷 `knowledge-data` 持久化（重建容器不丢）

### 3.2 系统架构

```
用户 → Vue3 前端（frontend/）
            │  /api/*（契约不变，SSE 流式 /api/chat/stream）
            ▼
      Java 业务后端 :8080
      ├─ Conversation/Message CRUD → PostgreSQL
      ├─ Redis：会话写锁 + 限流
      ├─ RestClient ── POST /api/agent/chat ──────────► Python Agent 服务 :8000
      └─ JDK HttpClient ── POST /api/agent/chat/stream ──►（SSE 逐 token 转发）
              {message, images, history}                       │
                                                               ▼
                                              LangGraph（query_analyzer → query_rewriter
                                                → retrieve_context → chat/recommend）
                                                               │
                                     ┌──────────────┬──────────┴──────────┐
                                     ▼              ▼                     ▼
                              DeepSeek（闲聊/   DeepSeek（查询改写）   千问多模态（体征分析）
                               推荐生成）
                                     │              │
                                     └── rag_context 注入推荐 prompt（图谱2跳 + 维度过滤向量 top-k）
```

> 说明：流式链路中 Java 以 SseEmitter 代理 Python SSE，结束事件携带 intent，
> 元数据事件绑定会话 id/标题，done 后按同步接口相同事务落库。

### 3.3 后端目录结构

```
iclothes-server/           # Java 业务后端（Spring Boot）
  src/main/java/com/iclothes/
    controller/            # Health / Chat / Conversation / Recommend / Static
    service/               # ChatService（编排+流式落库）、ConversationService（CRUD+裁剪）
    agent/                 # PythonAgentClient（RestClient 同步 + JDK HttpClient 流式代理）
    repository/            # ConversationMapper / MessageMapper（MyBatis-Plus）
    entity/ dto/ config/ exception/
  src/main/resources/      # application.yml、db/migration/（Flyway）
app/                       # Python AI-Agent 服务（FastAPI + LangGraph）
  api/routers/agent.py     # 无状态 /api/agent/chat + /api/agent/chat/stream（SSE）
  graph/                   # query_analyzer / query_rewriter / retrieve_context /
                           #   chat_reply / recommend_outfit（LangGraph 状态图）
  knowledge/               # RAG：build/（文档读取、三元组抽取、实体归并、增量导入）、
                           #   retrieve/（graph_store + vector_store + retriever）、docs/
  repositories/model_repo.py   # 模型工厂（千问多模态 / DeepSeek / Embedding）
```

## 4. 功能优先级

### P0 (必须实现 - MVP) — v1.0.0 全部完成 ✅
- [x] 照片上传功能
- [x] 千问API集成（场景分析）
- [x] 基础推荐结果展示
- [x] 对话式界面 + 意图分析（5 类）+ 多轮会话
- [x] 双服务架构落地（Java 业务层 + Python Agent 服务 + Redis + PG 持久化）
- [x] 知识图谱 + 向量混合检索（RAG 在线召回接入推荐）
- [x] 流式输出（SSE 打字机效果）
- [x] 部署到服务器（阿里云 ECS，公网可访问）

### P1 (第二版本)
- [x] DeepSeek API集成（识别/检索改写）
- [x] 文字描述输入（无照片文字推荐）
- [ ] 效果图生成

### P2 (后续迭代)
- [ ] 季节适配（春夏秋冬）
- [ ] 主题穿搭（商务/约会/运动）
- [ ] 用户历史记录 / 用户画像
- [ ] 收藏功能
- [ ] 检索质量调优（top-k / 距离阈值 / 改写策略）
- [ ] 多模态识别增强（照片信息抽取接入推荐）

## 5. 迭代计划

### v1.0.0 - MVP 基础版 ✅ 已发布（2026-08-31）
**目标**：最小可用产品（对话式）+ 生产部署
- 照片上传、千问分析、文字推荐结果
- 对话式界面、意图分析（5 类 + 9 维度）、多轮会话
- 双服务架构（Java 业务后端 + Python 无状态 Agent）+ PostgreSQL + Redis
- 知识图谱 + 向量混合检索（RAG 在线召回）
- 流式输出（SSE 打字机效果）
- Docker Compose 四件套生产部署（阿里云 ECS）

### v1.1.0 - 检索质量与体验优化
- 检索调优：top-k / 距离阈值 / 改写策略按维度差异化
- 推荐质量评估与提示词迭代
- 多模态识别增强（照片信息抽取接入推荐）

### v2.0.0 - 完整推荐与场景增强
- 效果图生成
- 季节判断、主题穿搭
- 用户画像与历史记录
- UI/UX 优化

## 6. 技术约束

- API调用成本控制：Redis 限流（默认 60 次/分钟/IP）+ LLM 请求**不自动重试**（防重复扣费）；
  推荐意图消息最多 3 次 LLM 调用（查询改写 + embedding + 回复生成），闲聊不检索
- 图片存储策略（临时存储，定期清理）
- 响应时间：首 token 延迟目标 < 10 秒（流式）；Java 侧 Python 读取超时 120s 兜底
- 并发支持：初期 10 个并发请求；同一会话写入经 Redis 锁串行化（等待 ≤3s，超时 503）
- Redis 故障降级：锁降级 JVM 内锁、限流 fail-open，应用不中断
- 检索降级：图/向量任一路失败 fail-open，保证回复可用；流式连接断开 → 终止流并释放锁

## 7. 非功能需求

- **安全性**：API密钥安全存储（环境变量），Redis/PG 密码不落代码
- **性能**：图片压缩，避免超大文件；Java 虚拟线程 + 连接池
- **可维护性**：代码模块化，日志完整（Java SLF4J / Python logging），Phoenix 追踪
- **可扩展性**：Python Agent 无状态可水平扩展；契约先行，AI 层演进不影响业务层
- **可用性**：Agent 服务不可达 → 502 友好提示，业务服务不宕

## 8. 待确认问题

- [x] 千问和DeepSeek的具体API版本和定价（生产用 qwen3.7-max / deepseek-v4-flash）
- [x] 服务器配置（CPU/内存/带宽）（阿里云 ECS 47.103.144.20）
- [ ] 是否需要用户登录系统（P2）
- [x] Redis 部署形态（Docker compose 自建）
- [ ] 8000/5432/6379 端口收敛为仅内网（安全加固，待办）

---

**文档版本**：v3.0（对应产品 v1.0.0）
**创建时间**：2026-08-11
**负责人**：Claude (PM)
**最后更新**：2026-08-31（v3.0：v1.0.0 发布——双服务架构 + RAG 在线检索 + 流式输出 + 生产部署上线）
