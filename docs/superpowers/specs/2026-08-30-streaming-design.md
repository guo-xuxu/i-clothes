# 流式输出（SSE）设计

| 项 | 值 |
|---|---|
| 日期 | 2026-08-30 |
| 状态 | 已评审（用户确认：Java 转发代理 + 新增 stream 接口保留原接口） |
| 分支 | main |
| 范围 | 聊天回复流式输出（打字机效果）：Python SSE 生成 → Java SseEmitter 代理 → 前端 ReadableStream 消费 |

## 1. 目标

把一次性的 `POST /api/chat` 回复升级为**逐 token 流式输出**（SSE），前端打字机渲染；
同时保留原非流式接口（兼容旧客户端与第三方调用）。

## 2. 链路与契约

```
前端 fetch(SSE) → Java POST /api/chat/stream（SseEmitter 代理）
  → Python POST /api/agent/chat/stream（SSE）
```

### 2.1 Python（`app/api/routers/agent.py` 新增）

- `POST /api/agent/chat/stream`：请求体与 `/api/agent/chat` 完全一致（校验复用：图片格式/数量/大小、空消息 400）
- 执行：`workflow.astream(inputs, stream_mode=["messages", "updates"])`
  - `messages` 模式：仅转发 `chat_reply` / `recommend_outfit` 节点的 token（`langgraph_node` 过滤）；
    `query_analyzer`/`query_rewriter`/`retrieve_context` 的耗时在首 token 前，不进流
  - `updates` 模式：从 `query_analyzer` 的节点输出取映射后的 `intent`（recommend|chat），
    避免流结束后重跑工作流（不重复计费）
- 响应：`text/event-stream`，事件（每行 `data: <json>` + 空行）：
  - `{"delta": "..."}` 逐 token
  - `{"done": true, "intent": "recommend"|"chat"}` 结束
  - `{"error": "..."}` 中途异常（LLM 失败；校验类 400 在流开始前以 HTTP 状态码返回）
- 新增 `workflow.stream_chat(message, images, history)` 异步生成器（`yield (delta, intent|None)`），
  与 `run_chat` 并列

### 2.2 Java（`ChatController` + `ChatService` + `PythonAgentClient` 新增）

- `POST /api/chat/stream`（`produces=text/event-stream`）：校验/限流与 `/api/chat` 一致；
  返回 `SseEmitter`（超时 120s）
- `ChatService.chatStream(...)`：会话解析/写锁/取历史与 `chat()` 一致；虚拟线程内调
  `PythonAgentClient.streamChat`，逐事件转发前端并**累积全文**；收到 done 事件后按非流式
  相同事务落库（user + assistant + touch + trim + 标题），再 `emitter.complete()`
- `PythonAgentClient.streamChat(...)`：用 **JDK `java.net.http.HttpClient`**（零新依赖，
  `BodyHandlers.ofLines` 流式读 SSE）代理 Python；无 400/429 预检错误（Java 已先校验），
  非 200 或 IO 异常 → `emitter.completeWithError`（前端收到错误终止）
- 错误映射同非流式：400（校验）/ 429（限流）/ 502 语义经 error 事件

### 2.3 前端（`api.js` + `App.vue`）

- `api.js` 新增 `streamChat(message)`：`fetch` + `ReadableStream` 逐行解析 SSE
  （`data:` 前缀 → JSON），`yield` delta；返回 `{stream, promise(done intent)}` 或
  async generator + 结束回调
- `App.vue`：发送时新建"流式气泡"，逐 delta append（打字机）；done 事件后置 intent 标签、
  落库刷新会话；error 事件显示错误

## 3. 兼容与回归

- 原 `POST /api/chat`、`POST /api/agent/chat` **保留**（契约逐字节不变）
- 键名 snake_case、错误体 `{"detail"}` 不变
- 现有测试：Python 契约 10 + 分析/改写/检索 69 + Java 单测/集成全绿

## 4. 里程碑（TDD）

| M | 内容 |
|---|---|
| M1 | Python：`stream_chat` 生成器 + `/api/agent/chat/stream` SSE 端点 + 契约测试（mock 工作流产出序列） |
| M2 | Java：`PythonAgentClient.streamChat`（JDK HttpClient 流式）+ `ChatController`/`ChatService` 流式端点 + 测试（本地 HttpServer 供 SSE） |
| M3 | 前端：`api.js` streamChat + `App.vue` 打字机渲染 |
| M4 | 回归 + 服务器更新 + 实机 curl SSE 验证 |
