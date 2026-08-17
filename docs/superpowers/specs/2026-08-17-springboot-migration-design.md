# 双服务架构设计：Java 业务后端 + Python AI-Agent 服务（i-clothes）

| 项 | 值 |
|---|---|
| 日期 | 2026-08-17（v2，替代 v1 的"Java 全量重写"方案） |
| 状态 | 待评审 |
| 范围 | 前端契约不变；Java 承接业务（CRUD + 并发 + Redis），Python 收敛为无状态 Agent 服务 |
| 关联 | PRD.md v1.0 |

## 1. 背景与目标

i-clothes 现有 Python 后端（FastAPI + LangGraph）已具备推荐、多轮聊天、意图路由、
Phoenix 可观测。经评估：**AI-Agent 生态以 Python 为主**（LangGraph/工具调用/RAG），
而业务后端 Java 生态（Spring Boot/事务/中间件）是工程惯例。因此采用**双服务架构**：
AI 能力留在 Python，业务由 Java 承接，两边 HTTP 通信。

### 目标
1. **Java 业务后端**：承接前端全部 `/api/*` 契约；会话/消息 CRUD 落 PostgreSQL；
   并发安全（会话级串行化 + 连接池 + 虚拟线程）；Redis 做会话写锁与限流。
2. **Python Agent 服务**：收敛为**无状态**推理服务（意图路由/闲聊/推荐/LLM 调用），
   不落库、不带会话状态；对外暴露统一契约 `POST /api/agent/chat`。
3. 前端 `frontend/` 零改动；接口契约与现状逐字节兼容。
4. 双服务 + PostgreSQL + Redis 可 Docker compose 一键编排（交付物）。

### 非目标（本期明确不做）
- P1/P2 功能（单品识别、生图、用户体系、收藏、向量检索、知识图谱）
- 意图路由升级为 LLM 判断、SSE 流式输出（保持一次性返回）
- Python 侧接入 RAG/工具调用（下期，架构已为此预留：无状态 + 统一契约）

## 2. 总体架构

```
┌──────────┐   /api/* (契约不变)   ┌───────────────────────────────┐
│  Vue3    │ ───────────────────► │  Java 业务后端 :8080          │
│ 前端(不动)│ ◄─────────────────── │  controller / service /       │
└──────────┘                      │  repository(MyBatis-Plus)     │
                                  │  ├─ PostgreSQL（业务数据）      │
                                  │  └─ Redis（写锁/限流）          │
                                  └──────────────┬────────────────┘
                                                 │ POST /api/agent/chat
                                                 │ {message, images, history}
                                                 ▼
                                   ┌───────────────────────────────┐
                                   │  Python Agent 服务 :8000       │
                                   │  FastAPI + LangGraph（无状态） │
                                   │  意图路由 / 闲聊 / 推荐 / LLM   │
                                   └───────────────────────────────┘
```

**职责边界与数据所有权：**
- **数据归 Java**：conversations/messages 全部存 PG，由 Java 读写；Python 不碰数据。
- **推理归 Python**：所有 LLM 调用、prompt、意图路由在 Python 内完成。
- **状态收口**：Java 每次调用 Python 时携带完整历史（最近 N 条），Python 无会话状态
  ——多实例部署天然支持，无粘性会话问题。

## 3. 现状基线（契约与行为对照源）

### 3.1 对外接口契约（Java 必须逐字节兼容，前端零改动）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | `{"status":"ok","qianwen_configured":bool}` |
| `/api/recommend` | POST | multipart：`images`(≤3, JPG/PNG, ≤5MB) + `description` → `{"suggestion":str}` |
| `/api/conversations` | POST | 新建空会话 → `{"id","title"}` |
| `/api/conversations` | GET | 列表（更新时间倒序，含 preview） |
| `/api/conversations/{id}` | GET | 详情（含 messages；不存在 404） |
| `/api/conversations/{id}` | DELETE | 删除；不存在 404 |
| `/api/chat` | POST | JSON：`{conversation_id?, message, images?[]}` → `{"conversation_id","reply","intent","title"}` |

### 3.2 行为清单（Java 实现必须对齐）
- 图片校验：格式（仅 JPEG/PNG）、数量（≤3）、大小（≤5MB）→ 400；消息空且无图 → 400
- 意图规则（Python 侧，保持不变）：有图必 recommend；recommend 关键词优先于 chat；兜底 chat
- 推荐回复无照片时以「没有照片的情况下…」开头（Prompt 行为，Python 侧不变）
- 多轮上下文：chat 模式最近 10 条；recommend 模式最近 6 条用户消息（Python 侧消费）
- 自动标题：新会话取首条用户消息前 20 字符（Java 侧）
- 会话历史裁剪：单会话最多保留 50 条（Java 侧）

## 4. Python Agent 服务设计（无状态化改造）

### 4.1 对内契约（Java ↔ Python）

| 项 | 值 |
|---|---|
| 端点 | `POST /api/agent/chat` |
| 请求 | `{"message": str, "images": [dataURL...], "history": [{"role":"user"\|"assistant","content":str}...]}` |
| 响应 | `{"reply": str, "intent": "recommend"\|"chat"}` |
| 错误 | 校验失败 400 `{"detail"}`；LLM 未配置/调用失败 502 `{"detail"}` |
| 约束 | **无状态**：不落库、不带会话 id、可水平扩展 |

### 4.2 改造点（相对现状）
- **移除**：`app/services/conversation_store.py`、`app/services/chat_service.py`（会话职责）、
  conversations 系列路由（`app/api/routers/chat.py` 中的会话端点）
- **改造**：`/api/chat` 改为 `/api/agent/chat` 无状态接口——接收 message/images/history，
  经 LangGraph（intent_router → chat_reply / recommend）返回 `{reply, intent}`；图片校验保留
- **保留**：`config.py`、`repositories/model_repo.py`、`graph/` 全部节点、
  Phoenix 追踪、`/api/health`
- **新增**：契约测试（pytest，mock LLM）验证请求/响应/错误格式

### 4.3 无状态化收益
- Java 多实例可随意调；Python 侧可独立扩缩容
- 后续加 RAG/工具调用只改 Python 内部，契约不变

## 5. Java 业务后端设计

### 5.1 项目结构（单模块 Maven）

```
iclothes-server/
  pom.xml / Dockerfile
  src/main/java/com/iclothes/
    IclothesApplication.java
    config/           # ModelProperties(重命名为 AppProperties)、WebConfig、RedisConfig
    controller/       # Health / Chat / Conversation / Recommend / Static
    service/          # ChatService（编排）、ConversationService（CRUD+裁剪）、RateLimiter
    agent/            # PythonAgentClient（RestClient 封装）+ AgentChatRequest/Response DTO
    repository/       # ConversationMapper / MessageMapper（MyBatis-Plus）
    entity/           # Conversation / Message
    dto/              # 对外 DTO（与契约一一对应）
  src/main/resources/ application.yml / db/migration/V1__init.sql
  src/test/java/...   # 单测 + 集成测试（本地 PG + Redis）
```

### 5.2 ChatService 编排（等价"Java 管数据 + Python 管推理"）

```
POST /api/chat
  1. 校验（图片格式/数量/大小；空消息）→ 400
  2. 会话解析：id 无效/不存在 → 新建（PG insert）
  3. 取历史：messages 表按 conversation_id 升序取最近 20 条
  4. Redis 会话写锁：SET conversation:{id}:lock NX EX 5
     - 获取失败 → 等待重试（最多 3s）→ 仍失败 503
  5. 调 Python：POST /api/agent/chat {message, images, history}
  6. 落库：user 消息（含 images）+ assistant 消息（含 intent）
  7. 裁剪历史至 50 条（DELETE 最旧）
  8. 自动标题（新会话首条消息前 20 字符）
  9. 释放锁；返回 {conversation_id, reply, intent, title}
```

### 5.3 并发与 Redis（用户指定重点）

| 关注点 | 方案 |
|---|---|
| 同一会话并发写 | Redis 分布式锁串行化（锁键 `conversation:{id}:lock`，TTL 5s，失败重试 3s 后 503） |
| 成本控制（防刷） | Redis 限流：`INCR rate:{clientIp}:{yyyyMMddHHmm}` + TTL 60s，阈值可配（默认 60 次/分钟/IP） |
| 吞吐 | Java 21 虚拟线程（`spring.threads.virtual.enabled=true`）+ HikariCP 默认池 + Lettuce 连接池 |
| Python 调用 | `RestClient`（Spring 6）：连接超时 3s / 读取超时 60s |
| Redis 故障降级 | 锁降级为 JVM 内 `ReentrantLock`（单实例有效）；限流 fail-open（放行 + 日志告警） |
| 重试策略 | **不自动重试**：LLM 请求已发出，重试会造成重复扣费；超时/失败 → 502 提示用户重试 |

### 5.4 技术栈（Java 侧）

| 项 | 选择 |
|---|---|
| 语言/框架 | Java 21 + Spring Boot 3.5.3 + 虚拟线程 |
| 构建 | Maven |
| ORM | MyBatis-Plus 3.5.7（`mybatis-plus-spring-boot3-starter`） |
| 数据库 | PostgreSQL 16（Flyway 管 schema） |
| 缓存/锁/限流 | Redis（spring-boot-starter-data-redis，Lettuce） |
| HTTP 客户端 | Spring `RestClient` |
| 测试 | JUnit5 + Mockito + MockMvc + Testcontainers（可选） |

### 5.5 Python 侧技术栈（保持现状）

FastAPI + LangGraph + LangChain4j 无（Python 侧用 LangChain `ChatOpenAI`，现状保留）；
依赖清单不变（`requirements.txt`），移除会话相关代码。

## 6. 数据模型（PostgreSQL，Java 所有）

```sql
-- V1__init.sql
CREATE TABLE conversations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title      VARCHAR(100) NOT NULL DEFAULT '新对话',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL,           -- user | assistant
    content         TEXT NOT NULL,
    intent          VARCHAR(16) NOT NULL DEFAULT '',-- assistant 消息：recommend|chat
    images          JSONB NOT NULL DEFAULT '[]',    -- user 消息：data URL 数组
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);
CREATE INDEX idx_conversations_updated ON conversations(updated_at DESC);
```

## 7. 接口契约实现要点

- 对外 7 端点严格对齐 §3.1；错误统一 `{status, {"detail": "..."}}`（400/404/502/503）
- `/api/health`：Java 以 2s 超时调 Python `/api/health`，`qianwen_configured` 取自其响应；
  Python 不可达时仍返回 200 `{"status":"ok","qianwen_configured":false}`（API 存活但推理降级），
  保持契约逐字节兼容
- `vite.config.js` 代理目标 8000 → 8080（一行）
- 生产：Java 伺服 `frontend/dist`（`StaticController` + `/assets/**`，目录经 `iclothes.frontend.dir` 配置）
- Python 服务默认 `:8000`，Java 经 `iclothes.agent.base-url` 配置指向（环境变量 `AGENT_BASE_URL`）

## 8. 边界情况与失败模式

| 场景 | 处理 |
|---|---|
| Python 服务不可达/超时 | Java 捕获 → 502 `{"detail":"AI 服务暂不可用，请稍后重试"}`；不落库 |
| Python 返回 400（校验） | Java 透传 400 detail（不应发生，Java 已先校验，作防御） |
| Redis 不可用 | 锁降级 JVM 内锁；限流 fail-open；应用继续工作（日志告警） |
| 锁竞争（同一会话并发） | 等待 ≤3s → 503 `{"detail":"请求过于频繁，请稍后重试"}` |
| LLM 调用失败 | Python 侧 502 → Java 透传；不重试（避免重复扣费） |
| 会话不存在 | GET/DELETE → 404；chat 时自动新建（与现状一致） |
| 图片超限 | Java 校验 → 400（与现状消息逐字一致） |

## 9. 测试与验收

### 9.1 单元测试
- Java：ConversationService（CRUD/裁剪/标题）、ChatService 编排（mock PythonAgentClient 与 Mapper）、
  校验逻辑（图片/空消息）
- Python：`/api/agent/chat` 契约测试（mock LLM：请求/响应/400/502）、意图路由 6 用例

### 9.2 集成测试（本地 PG + Redis）
- Repository 冒烟（CRUD/CASCADE/摘要查询/裁剪）
- 端到端：起 PG + Redis + Python（真实 key 可选）+ Java → 前端契约全流程

### 9.3 验收标准
1. Java 单测 + Python 契约测试全绿
2. `docker compose up` 一键起四件套（pg + redis + python + java），`/api/health` OK
   （本机无 Docker 时降级：本地 PG/Redis + 两服务进程，验收项等价）
3. 浏览器全流程：新建会话 → 闲聊 → 文字推荐 → 传图推荐 → 切换/删除会话 →
   刷新后历史仍在（PG 持久化）→ **并发双开同一会话发消息不丢不乱**
4. 前端代码除 vite 代理端口外零改动

## 10. 迁移步骤

1. Python 无状态化改造 + 契约测试（§4.2）
2. 导出/确认对内契约（`/api/agent/chat`）与对外契约存档
3. Java 脚手架（Spring Boot 3.5.3 + MyBatis-Plus + Redis + RestClient）
4. PG schema（§6）+ 实体 + Mapper + CRUD 测试
5. Redis 基础设施（锁 + 限流）+ 测试
6. `PythonAgentClient` + 契约测试（mock Python）
7. `ChatService` 编排（§5.2）+ 并发路径测试
8. Controller/DTO 对齐契约 + 统一异常（400/404/502/503）
9. 前端联通（代理 8080 + 静态伺服）+ 端到端验收（§9.3）
10. Docker compose 交付物（pg + redis + python + java）
11. 清理：Python 会话代码移除确认、`常用指令`/CHANGELOG 更新

## 11. 假设与开放项

- 假设：双服务同仓库（`iclothes-server/` Java + `app/` Python 保留）；端口 Java 8080 / Python 8000
- 开放项：Redis 限流阈值默认 60 次/分钟/IP（可配）；是否需要用户体系（P2，本次不做）
- Python 删除范围：只删会话相关代码，AI-Agent 代码完整保留
