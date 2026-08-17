# i-clothes

智能穿搭助手：上传照片或描述场景，获得 AI 穿搭推荐与闲聊建议。

## 架构

**双服务架构**：Java 业务后端（Spring Boot 3.5.3 + MyBatis-Plus + Redis，:8080）
承接前端全部契约（会话 CRUD、并发写锁、限流，数据持久化到 PostgreSQL）；
Python 收敛为无状态 AI-Agent 服务（FastAPI + LangGraph，:8000），仅保留 AI 推理，
由 Java 通过 `/api/agent/chat` 调用，不落库、可水平扩展。

```
前端 (Vite :5173) ──/api──> Java 业务后端 (:8080) ──/api/agent/chat──> Python Agent (:8000)
                              │                                             │
                        PostgreSQL + Redis                              LLM（DeepSeek/千问）
```

## 快速启动

按顺序启动（前置：PostgreSQL :5432 与 Redis :6379 已运行）：

1. **Python Agent 服务**（:8000）
2. **Java 业务后端**（:8080）
3. **前端开发模式**（Vite :5173，代理 /api 到 8080，浏览器访问 http://127.0.0.1:5173）

具体命令见 [`常用指令`](./常用指令)。
