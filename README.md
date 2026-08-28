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

## 知识子系统（RAG）

穿搭知识文档（`app/knowledge/docs/`，9 大维度：廓形/身材/面料/风格/图案/配饰/场合/颜色/肤色）
经离线构建生成**知识图谱 + 向量库**：

```
docs/*.md → 切块 → DeepSeek 联合抽取（实体/关系/关键词）
          → 实体归并（L1/L2 同义词典 + 同维度向量候选 + LLM 判定）
          → networkx 建图（graph.json）+ Chroma 向量落盘（实体向量 + chunk 向量）
```

- **增量入库**：`POST /api/knowledge/import`（后台线程执行、单飞——已在跑返回 409；
  body 可选 `{"paths": [...]}`，缺省全量扫描；只处理未入库/内容变化的文档）
- **状态查询**：`GET /api/knowledge/import/status` → `{"status": "idle|running|failed",
  "last_stats": {...}}`
- 实现方案：`app/knowledge/IMPLEMENTATION.md`；规划：`docs/RAG知识图谱规划.md`
- 数据产物在 `app/knowledge/data/`（git-ignored，可随时重建）；在线混合召回
  （`app/knowledge/retrieve/`）接入中

## 快速启动

按顺序启动（前置：PostgreSQL :5432 与 Redis :6379 已运行）：

1. **Python Agent 服务**（:8000）
2. **Java 业务后端**（:8080）
3. **前端开发模式**（Vite :5173，代理 /api 到 8080，浏览器访问 http://127.0.0.1:5173）

具体命令见 [`常用指令`](./常用指令)。
