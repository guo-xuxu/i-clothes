# Spring Boot 迁移设计：i-clothes 后端

| 项 | 值 |
|---|---|
| 日期 | 2026-08-17 |
| 状态 | 已评审，待实施（writing-plans 后动工） |
| 范围 | 等价 MVP：FastAPI/LangGraph 后端 → Java Spring Boot |
| 关联 | PRD.md v1.0 |

## 1. 背景与目标

i-clothes 当前后端为 Python（FastAPI + LangGraph），已具备：上传推荐
（`/api/recommend`）、对话式界面（Vue3 前端 + `/api/chat`）、关键词意图路由、
内存会话。现决定将后端迁移至 **Java Spring Boot**（技术栈由团队确认）。

### 目标
1. Java 后端实现与 Python 版**等价能力**：推荐、多轮聊天、意图路由、会话持久化。
2. **前端 `frontend/` 零改动**——接口契约保持逐字节兼容。
3. 会话数据落 **PostgreSQL**（Python 版为内存存储，重启丢失，此为有意的能力提升）。
4. 全链路在 Docker compose 下可一键运行，验收后切换默认后端。

### 非目标（本期明确不做）
- P1 功能（DeepSeek 单品识别、生图）、P2（用户体系、收藏、向量检索、知识图谱）
- 意图路由升级为 LLM 判断（保持关键词规则，行为等价）
- SSE 流式输出（保持一次性返回）
- 前端重构

## 2. 现状基线（验收对照源）

### 2.1 接口清单（契约基准 = 当前 FastAPI `/openapi.json`，迁移第一步导出存档）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | `{"status":"ok","qianwen_configured":bool}` |
| `/api/recommend` | POST | multipart：`images`(≤3, JPG/PNG, ≤5MB) + `description` → `{"suggestion":str}` |
| `/api/conversations` | POST | 新建空会话 → `{"id","title"}` |
| `/api/conversations` | GET | 列表（更新时间倒序，含 preview） |
| `/api/conversations/{id}` | GET | 详情（含 messages；不存在 404） |
| `/api/conversations/{id}` | DELETE | 删除；不存在 404 |
| `/api/chat` | POST | JSON：`{conversation_id?, message, images?[]}` → `{"conversation_id","reply","intent","title"}` |

### 2.2 行为清单（Java 实现必须对齐）
- 图片校验：格式（仅 JPEG/PNG）、数量（≤3）、大小（≤5MB）→ 400；消息空且无图 → 400
- 意图规则：有图必 recommend；关键词命中 recommend 优先于 chat；兜底 chat
- 推荐回复在无照片时以「没有照片的情况下…」开头（Prompt 行为）
- 多轮上下文：聊天模式携带最近 10 条历史；推荐模式携带最近 6 条用户消息
- 自动标题：新会话取首条用户消息前 20 字符
- 会话历史裁剪：单会话最多保留 50 条

### 2.3 模型配置（迁移到 `application.yml` 环境变量）
- 千问（多模态）：`QIANWEN_API_KEY/BASE_URL/MODEL`（OpenAI 兼容端点）
- DeepSeek（文本）：`DEEPSEEK_API_KEY/BASE_URL/MODEL`

## 3. 技术栈决策（已确认）

| 项 | 选择 | 理由 |
|---|---|---|
| 语言/框架 | Java 21 + Spring Boot 3.x | LTS + 主流 |
| 构建 | Maven | 默认 |
| AI 层 | **LangChain4j** | 用户选择；Agent/工具调用思路与 LangGraph 一脉相承 |
| 数据库 | **PostgreSQL 16** | 用户选择；JSONB + pgvector 覆盖未来向量需求 |
| ORM | **MyBatis-Plus** | 用户选择；SQL 可控、Mapper 对应 DAO 层 |
| 迁移 | 数据库版本 | Flyway |
| 部署 | Docker compose（`postgres:16` + app） | 沿用现有思路 |

## 4. 项目结构与代码组织

Java 工程位于同一仓库新目录 **`iclothes-server/`**（与 `frontend/` 并列；
Python 的 `app/` 在切换完成后删除）。

```
iclothes-server/
  pom.xml
  Dockerfile
  src/main/java/com/iclothes/
    IclothesApplication.java
    config/       # 模型配置属性、上传限制、CORS（dev 允许 5173/8000）
    controller/   # ChatController、ConversationController、HealthController、RecommendController
    service/      # ChatService（编排）、ConversationService
    ai/           # ModelFactory（千问/DeepSeek ChatModel）、IntentRouter、prompt 常量
    repository/   # ConversationMapper、MessageMapper（MyBatis-Plus）
    entity/       # Conversation、Message
    dto/          # 请求/响应 DTO（与契约一一对应）
  src/main/resources/
    application.yml
    db/migration/（Flyway V1__init.sql）
    mapper/（XML，按需）
  src/test/java/com/iclothes/
    IntentRouterTest / ChatServiceTest / 集成冒烟
```

分层依赖：`controller → service → repository/ai`；AI 与 DB 同属数据访问，
service 只面向抽象（IntentRouter、Mapper 接口）。

## 5. 数据模型（PostgreSQL）

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

- `gen_random_uuid()` 需 `pgcrypto`（PG 13+ 内置，无需额外扩展）
- 历史裁剪（50 条）由 service 层在追加后执行（DELETE 最旧），与 Python 行为一致
- 图片以 data URL JSONB 存储，与现有 Message.images 语义一致

## 6. AI 层设计（LangChain4j）

- **模型工厂** `ModelFactory`：
  - `qianwenVl()`：`OpenAiChatModel`（baseUrl 千问兼容端点，支持 image content）
  - `deepseek()`：`OpenAiChatModel`（baseUrl DeepSeek）
  - 单例复用，Key 缺失：启动日志警告，调用时报 502（与 Python 行为一致）
- **意图路由** `IntentRouter`：关键词规则**原样移植**（recommend 优先、chat 兜底、有图必 recommend），纯函数、可单测
- **编排** `ChatService`（等价 LangGraph 节点链，顺序执行）：
  1. 意图路由 → chat / recommend
  2. chat：组装最近 10 条历史 + 本轮 → `deepseek().generate()`
  3. recommend：有图 → 千问多模态体征分析 → DeepSeek 推荐；无图 → 直接 DeepSeek 推荐（空体征分析 + 「没有照片的情况下…」开头）
  4. 落库（用户消息 + 助手消息 + intent）、自动标题、裁剪历史
- 本期**不用** AiServices/agent（YAGNI）；接口已留好，未来 agent 化可平滑接入

## 7. 接口契约实现要点

- Controller 与 DTO 严格对齐 §2.1；`/api/chat` 与 `/api/recommend` 的校验错误
  统一 `400 + {"detail": "..."}` 格式（与前端 `api.js` 的 `data.detail` 解析一致）
- LLM 调用异常 → `502 + {"detail": "..."}`（对齐现状）
- 前端 dev 代理 `vite.config.js`：`/api` 目标从 `127.0.0.1:8000` 改 `127.0.0.1:8080`（一行）
- 生产：Spring Boot 以静态资源伺服仓库根目录下 `frontend/dist`（`/` 与 `/assets/**`，
  容器工作目录为仓库根，等价现在 main.py 行为）

## 8. 配置与部署

```yaml
# application.yml（敏感项走环境变量）
iclothes:
  qianwen: { base-url: ${QIANWEN_BASE_URL}, api-key: ${QIANWEN_API_KEY}, model: ${QIANWEN_MODEL} }
  deepseek: { base-url: ${DEEPSEEK_BASE_URL}, api-key: ${DEEPSEEK_API_KEY}, model: ${DEEPSEEK_MODEL} }
  upload: { max-count: 3, max-size-mb: 5 }
spring:
  datasource: { url: ${DB_URL:jdbc:postgresql://localhost:5432/iclothes}, username: ${DB_USER}, password: ${DB_PASSWORD} }
```

`docker-compose.yml`（项目根）：`postgres:16`（volume + healthcheck）+ `iclothes-server`（8080，depends_on pg healthy）+ 可选前端 dev。

## 9. 边界情况与失败模式

| 场景 | 处理 |
|---|---|
| LLM 超时/网络错误 | ChatService 捕获 → 502；不落库未完成的助手消息 |
| Key 未配置 | 启动日志警告；调用时 502（与 Python 行为一致） |
| 并发写同一会话 | 追加消息串行化（会话级锁或乐观更新），裁剪操作幂等 |
| 会话不存在 | 404（GET/DELETE）；chat 时 conversation_id 无效 → 自动新建（与 Python 行为一致） |
| 超大图片 data URL | 接口层按 base64 长度估算校验（≤5MB）→ 400 |
| 前端拿到 4xx/5xx | `api.js` 已按 `data.detail` 展示错误，无需改动 |

## 10. 测试与验收

### 10.1 单元测试
- `IntentRouterTest`：§2.2 意图规则 6 用例（含历史回退、有图必推荐）等价迁移
- `ChatServiceTest`：mock ChatModel 验证编排（chat/recommend/无图推荐/自动标题/裁剪）
- 校验逻辑测试（图片格式/数量/大小、空消息）

### 10.2 集成冒烟（对照 Python 版行为清单 §2.2）
- conversations CRUD、chat 全流程、意图值与回复结构、400/404/502 各错误路径

### 10.3 验收标准（全部满足才算完成）
1. `iclothes-server` 测试全绿
2. Docker compose 一键起（pg + app），`/api/health` OK
3. 浏览器打开前端（dev 代理 8080 或生产 dist），完整走一遍：新建会话 → 闲聊 → 文字推荐（无图）→ 传图推荐 → 切换/删除会话 → 刷新后历史仍在（PG 持久化）
4. 前端代码除 `vite.config.js` 代理端口外**零改动**

## 11. 迁移步骤

1. 导出 FastAPI `/openapi.json` 存档为契约基准（`docs/`）
2. `iclothes-server/` Maven 脚手架（Spring Boot 3 + MyBatis-Plus + langchain4j 依赖）
3. Flyway schema（§5）+ entity + mapper
4. `ModelFactory` + `IntentRouter` + prompt 常量
5. `ChatService` 编排 + `ConversationService`
6. Controller/DTO 对齐契约 + 统一异常处理（400/404/502）
7. 单测 + 集成冒烟，对照 §2.2 行为清单
8. Docker compose 联调；前端代理切 8080；验收（§10.3）
9. 切换默认后端，删除 Python `app/`、`requirements.txt` 等（保留 PRD/CHANGELOG/spec）

## 12. 假设与开放项

- 假设：同一仓库 monorepo（`iclothes-server/` 目录）；如需独立仓库，仅调整 §4 路径
- 开放项（不影响本期动工）：Java 包名 `com.iclothes` 是否最终；CI/CD 是否本期引入（默认不引入）
- 删除 Python 代码的时机：验收通过后的单独提交
