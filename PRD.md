# 产品需求文档 (PRD)

## 1. 产品概述

**产品名称**：i-clothes 智能穿搭助手

**产品定位**：基于AI多模态分析的个性化穿搭推荐系统。用户通过**对话式界面**上传参考照片
或文字描述，即可获得专业的穿搭建议；支持多轮对话、意图路由（推荐/闲聊）与会话管理。

**目标用户**：
- 对穿搭有需求但缺乏灵感的普通用户
- 需要快速解决特定场景穿搭问题的用户

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
- **意图路由**：关键词规则判断"穿搭推荐 vs 闲聊"，有图一律走推荐
- **多轮对话**：上下文随会话传递（闲聊 10 条 / 推荐 6 条用户消息）
- **无照片文字推荐**：无图时跳过体征分析，直接按文字描述推荐
- **会话管理**：新建/切换/删除会话、自动标题（首条消息前 20 字符）、
  历史持久化（PostgreSQL，重启不丢）
- 图片附件：输入框直接附加照片（≤3 张），随消息一起分析

## 3. 技术架构

### 3.1 技术栈（双服务架构）

**前端**：
- Vue3 + Element Plus（Vite 构建）
- 原生 Fetch 调用 `/api/*`，不感知后端语言

**Java 业务后端**（`iclothes-server/`，对外唯一入口）：
- Java 21 + Spring Boot 3.5.3（虚拟线程）
- MyBatis-Plus 3.5.7（ORM）+ PostgreSQL 16（业务数据）+ Flyway（schema 版本）
- Redis（会话写锁 / 限流 / 故障降级）
- RestClient（HTTP 调用 Python Agent 服务）
- 职责：会话/消息 CRUD、并发控制、限流、伺服前端、编排 Agent 调用

**Python AI-Agent 服务**（`app/`，无状态推理）：
- Python 3.12（conda 环境，位于项目内 `.conda/`）
- FastAPI + **LangGraph**（状态图编排：意图路由 → 闲聊/推荐节点）
- LangChain（`ChatOpenAI`）统一接入千问/DeepSeek（OpenAI 兼容端点）
- Phoenix（OTLP 追踪，可观测）
- 职责：意图路由、多轮闲聊、体征分析、穿搭推荐、LLM 调用
- **无状态**：不落库、不带会话 id，可水平扩展

**基础设施**：
- Docker Compose：postgres + redis + python-agent + java 四件套
- 环境变量管理密钥（`QIANWEN_*`、`DEEPSEEK_*`、`DB_*`）

### 3.2 系统架构

```
用户 → Vue3 前端（frontend/）
            │  /api/*（契约不变）
            ▼
      Java 业务后端 :8080
      ├─ Conversation/Message CRUD → PostgreSQL
      ├─ Redis：会话写锁 + 限流
      └─ RestClient ── POST /api/agent/chat ──► Python Agent 服务 :8000
              {message, images, history}          │
                                                  ▼
                                        LangGraph（意图路由 → chat/recommend）
                                                  │
                                     ┌────────────┴────────────┐
                                     ▼                        ▼
                                DeepSeek（闲聊/推荐）     千问多模态（体征分析）
```

### 3.3 后端目录结构

```
iclothes-server/           # Java 业务后端（Spring Boot）
  src/main/java/com/iclothes/
    controller/            # Health / Chat / Conversation / Recommend / Static
    service/               # ChatService（编排）、ConversationService（CRUD+裁剪）
    agent/                 # PythonAgentClient（RestClient 封装）
    repository/            # ConversationMapper / MessageMapper（MyBatis-Plus）
    entity/ dto/ config/
  src/main/resources/      # application.yml、db/migration/（Flyway）
app/                       # Python AI-Agent 服务（FastAPI + LangGraph）
  api/routers/agent_chat.py    # 无状态 /api/agent/chat（对外内部契约）
  graph/                       # intent_router / chat_reply / recommend 节点
  repositories/model_repo.py   # 模型工厂（千问/DeepSeek）
```

## 4. 功能优先级

### P0 (必须实现 - MVP)
- [x] 照片上传功能
- [x] 千问API集成（场景分析）
- [x] 基础推荐结果展示
- [x] 对话式界面 + 意图路由 + 多轮会话
- [ ] 双服务架构落地（Java 业务层 + Python Agent 服务 + Redis + PG 持久化）
- [ ] 部署到服务器

### P1 (第二版本)
- [ ] DeepSeek API集成（识别）
- [ ] 文字描述输入
- [ ] 效果图生成

### P2 (后续迭代)
- [ ] 季节适配（春夏秋冬）
- [ ] 主题穿搭（商务/约会/运动）
- [ ] 用户历史记录
- [ ] 收藏功能
- [ ] 向量检索（PostgreSQL pgvector）/ 知识图谱

## 5. 迭代计划

### v0.1.0 - MVP基础版（当前版本）
**目标**：实现最小可用产品（对话式）
- 照片上传、千问分析、文字推荐结果
- 对话式界面、意图路由、多轮会话
- **进行中**：双服务架构迁移（Java 业务后端 + Python Agent 服务）

**预计时间**：已完成主体功能；架构迁移预计 3-5 天

### v0.2.0 - 完整推荐
- 集成DeepSeek 识别
- 添加生图功能
- 优化推荐逻辑

### v0.3.0 - 场景增强
- 季节判断
- 主题穿搭
- UI优化

## 6. 技术约束

- API调用成本控制：Redis 限流（默认 60 次/分钟/IP）+ LLM 请求**不自动重试**（防重复扣费）
- 图片存储策略（临时存储，定期清理）
- 响应时间：< 10秒（含 Python Agent 调用；Java 侧读取超时 60s 兜底）
- 并发支持：初期 10 个并发请求；同一会话写入经 Redis 锁串行化（等待 ≤3s，超时 503）
- Redis 故障降级：锁降级 JVM 内锁、限流 fail-open，应用不中断

## 7. 非功能需求

- **安全性**：API密钥安全存储（环境变量），Redis/PG 密码不落代码
- **性能**：图片压缩，避免超大文件；Java 虚拟线程 + 连接池
- **可维护性**：代码模块化，日志完整（Java SLF4J / Python logging），Phoenix 追踪
- **可扩展性**：Python Agent 无状态可水平扩展；契约先行，AI 层演进不影响业务层
- **可用性**：Agent 服务不可达 → 502 友好提示，业务服务不宕

## 8. 待确认问题

- [ ] 千问和DeepSeek的具体API版本和定价
- [ ] 服务器配置（CPU/内存/带宽）
- [ ] 是否需要用户登录系统（P2）
- [ ] Redis 部署形态（托管 vs 自建，随服务器部署一起定）

---

**文档版本**：v2.0
**创建时间**：2026-08-11
**负责人**：Claude (PM)
**最后更新**：2026-08-17（v2.0：双服务架构 + 对话式功能）
