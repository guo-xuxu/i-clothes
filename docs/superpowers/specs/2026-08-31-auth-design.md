# 用户认证与会话隔离设计

| 项 | 值 |
|---|---|
| 日期 | 2026-08-31 |
| 状态 | 已评审（用户确认：recommend 用 history 故也隔离、注册开放） |
| 分支 | feat/rag-on-springboot |
| 范围 | 用户账密注册/登录（JWT）+ 会话按用户隔离（上下文天然按会话 id 隔离，本次补「用户」层） |

## 1. 目标

给 i-clothes 加「用户」层：账密登录换取 JWT，所有会话/聊天按用户隔离。
**不改 Python Agent**（保持无状态），改动集中在 Java 业务侧 + 前端。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| 认证方式 | JWT（HS256，有效期 7 天） |
| 登录方式 | 用户名 + 密码（BCrypt 加密） |
| 未登录访问 | 强制登录（未认证 401，前端跳登录页） |
| 用户规模 | 少数人内部用（不引入完整 Spring Security，手写轻量 filter） |
| 注册方式 | 开放注册（POST /api/auth/register） |
| 存量会话 | 清空（当前为测试数据） |

## 3. 数据模型

### 3.1 users（新增，V2 迁移）

```sql
CREATE TABLE users (
    id         BIGSERIAL PRIMARY KEY,
    username   VARCHAR(64) NOT NULL UNIQUE,
    password   VARCHAR(100) NOT NULL,          -- BCrypt 结果
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.2 conversations（加 user_id）

```sql
ALTER TABLE conversations ADD COLUMN user_id BIGINT NOT NULL REFERENCES users(id);
-- 存量数据直接清空（决策：少数人内部用，不迁移）
```

## 4. 认证契约

### 4.1 注册

```
POST /api/auth/register
请求: {"username": "string(3-64)", "password": "string(6-72)"}
响应 200: {"id": 1, "username": "alice"}
错误 400: {"detail": "用户名或密码不合法"}     # 校验失败
错误 409: {"detail": "用户名已存在"}
```

### 4.2 登录

```
POST /api/auth/login
请求: {"username": "string", "password": "string"}
响应 200: {"token": "eyJ...", "user": {"id": 1, "username": "alice"}}
错误 401: {"detail": "用户名或密码错误"}
```

### 4.3 当前用户

```
GET /api/auth/me
Header: Authorization: Bearer <token>
响应 200: {"id": 1, "username": "alice"}
错误 401: {"detail": "未认证"}
```

### 4.4 JWT 结构

- 算法 HS256；密钥读环境变量 `JWT_SECRET`
- payload：`{"sub": "<userId>", "username": "<name>", "iat": <ts>, "exp": <ts>}`
- 有效期 7 天
- 前端存 localStorage，请求带 `Authorization: Bearer <token>`

## 5. 会话隔离契约

所有会话/聊天接口需认证；**越权返回 404（不区分「不存在」和「无权」，防探测）**。

| 接口 | 隔离规则 |
|---|---|
| `POST /api/conversations` | 新建会话绑定当前 user_id |
| `GET /api/conversations` | 仅返回当前用户的会话（where user_id = ?） |
| `GET /api/conversations/{id}` | 会话不属于当前用户 → 404 |
| `DELETE /api/conversations/{id}` | 同上 → 404 |
| `POST /api/chat` | 会话归属校验，越权 404 |
| `POST /api/recommend` | 认证 + 隔离（依赖会话历史） |

## 6. 错误语义

| 状态码 | 含义 |
|---|---|
| 401 | 未带 token / token 无效 / 过期 |
| 404 | 会话不存在（含越权访问） |
| 409 | 用户名冲突 |
| 400 | 参数校验失败 |

错误体统一 `{"detail": "..."}`（与现有 GlobalExceptionHandler 一致）。

## 7. 前端改动

- 新增登录页 + 注册页
- `api.js`：请求带 `Authorization: Bearer <token>`；收到 401 时清 token 跳登录
- 启动时无 token → 跳登录

## 8. 兼容与回归

- Python Agent 零改动
- 现有 `/api/chat`、`/api/conversations/*` 响应字段不变，仅新增认证 header 要求
- 现有 Java 会话单测/集成测试需补 user 参数

## 9. 里程碑（TDD）

| M | 内容 |
|---|---|
| M1 | V2 迁移（users + conversations.user_id）+ User/UserMapper + AuthService/AuthController + JwtUtil + 契约测试（register/login/me） |
| M2 | AuthFilter（解析 JWT → 请求上下文）+ 会话隔离（Service/Controller 加 user_id 过滤）+ 越权测试（访问他人会话 404） |
| M3 | 前端登录/注册页 + token 管理 + 401 跳转 |
| M4 | 回归 + 服务器更新 + 实机 curl 验证 |
