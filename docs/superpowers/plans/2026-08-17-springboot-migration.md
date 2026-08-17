# 双服务架构（Java 业务后端 + Python AI-Agent 服务）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 i-clothes 后端重构为双服务架构——Java 业务后端（Spring Boot：会话 CRUD + Redis 锁/限流 + 并发安全）承接前端契约，Python 收敛为无状态 AI-Agent 服务（LangGraph 推理），前端零改动。

**Architecture:** 前端 → Java `:8080`（controller/service/repository + Redis + RestClient）→ Python `:8000`（FastAPI + LangGraph，无状态 `POST /api/agent/chat`）。数据归 Java（PostgreSQL），推理归 Python（LLM）。Java 每次调用携带完整历史，Python 不落库可水平扩展。

**Tech Stack:** Java 21 + Spring Boot 3.5.3（虚拟线程）+ MyBatis-Plus 3.5.7 + PostgreSQL 16 + Redis（Lettuce）+ RestClient；Python 侧保持 FastAPI + LangGraph（现状）；JUnit5 + Mockito + MockMvc + pytest。

**Spec:** `docs/superpowers/specs/2026-08-17-springboot-migration-design.md`（v2 双服务架构，本计划逐节覆盖它；执行者必须同时阅读 spec 与计划）

## Global Constraints

- Java 21 + Spring Boot `3.5.3`（parent POM）+ `spring.threads.virtual.enabled=true`；MyBatis-Plus `3.5.7`（`mybatis-plus-spring-boot3-starter`）；`spring-boot-starter-data-redis`（Lettuce，版本由 Boot BOM 管理）；`postgresql` 驱动 + `flyway-core` + `flyway-database-postgresql`（Boot BOM 管理）；`spring-boot-starter-test`
- PostgreSQL 16 本地：库 `iclothes`（应用）/ `iclothes_test`（测试），用户 `postgres`，密码 `iclothes123`
- Redis 本地 `127.0.0.1:6379` 无密码（首选 Memurai Developer，winget id `Memurai.MemuraiDeveloper`；备用 tporadowski/redis zip）
- 端口：Java `8080`、Python `8000`、PG `5432`、Redis `6379`
- 包名 `com.iclothes`；monorepo：`iclothes-server/`（Java）+ `app/`（Python 保留）
- 对外 7 端点与 spec §3.1 逐字节兼容；错误体统一 `{"detail": "<中文>"}`（400/404/502/503/429）
- 上传限制：图片 ≤3 张、JPG/PNG、≤5MB；消息空且无图 → 400；校验消息与现状逐字一致
- Redis 会话写锁：键 `conversation:{id}:lock`，`SET NX EX 5`，等待 ≤3s 后 503 `{"detail":"请求过于频繁，请稍后重试"}`；Redis 故障降级 JVM 内 `ReentrantLock`
- Redis 限流：键 `rate:{clientKey}:{yyyyMMddHHmm}`，TTL 61s，默认 60 次/分钟/IP，超限 429；Redis 故障 fail-open
- **不自动重试 LLM 请求**（已发出的请求重试会造成重复扣费）；Python 不可达/超时 → 502 `{"detail":"AI 服务暂不可用，请稍后重试"}`
- 上下文轮数：chat 最近 10 条 / recommend 最近 6 条用户消息（Python 侧消费）；Java 每次取最近 20 条历史随请求携带
- 自动标题：新会话首条用户消息前 20 字符（Java 侧）；会话历史裁剪：最多 50 条（Java 侧）
- Python 无状态：不落库、不带会话 id、可水平扩展
- Java `/api/health` 代理 Python `/api/health`（2s 超时），Python 不可达仍返回 200 `{"status":"ok","qianwen_configured":false}`
- Python 服务地址 Java 侧经 `iclothes.agent.base-url` 配置（环境变量 `AGENT_BASE_URL`）
- 本机无 Docker/WSL：compose 四件套作为交付物编写（pg+redis+python+java），运行验收降级为本地 PG/Redis + 进程（spec §9.3 第 2 条等价执行）
- Windows 网络事实：GitHub 直连被墙，下载用 `https://gh-proxy.com/https://github.com/...`；Maven Central 直连 200（无需镜像）
- 每个 Task 以可独立验证的交付物结束并提交 git

---

## 文件结构总览

```
# Python（改造为无状态 Agent 服务）
app/
  main.py                          # 只挂 agent + health 路由（移除 chat/recommend）
  config.py                        # 保留
  api/routers/
    __init__.py
    health.py                      # 保留（Java 代理它）
    agent.py                       # 新建：POST /api/agent/chat（无状态）
    chat.py                        # 删除
    recommend.py                   # 删除
  services/                        # 整个目录删除（conversation_store/chat_service/recommendation）
  graph/                           # 全部保留（intent_router/chat_reply/recommend_outfit/analyze_appearance/state/workflow）
  repositories/model_repo.py       # 保留
test/
  test_agent_contract.py           # 新建：契约测试（mock LLM）

# Java（新建 iclothes-server/）
iclothes-server/
  pom.xml
  src/main/java/com/iclothes/
    IclothesApplication.java
    config/
      AppProperties.java           # @ConfigurationProperties("iclothes")：upload/agent/rateLimit/frontend
      WebConfig.java               # /assets/** 资源映射
      RestClientConfig.java        # PythonAgentClient 的 RestClient Bean
    controller/
      HealthController.java        # GET /api/health（代理 Python）
      ChatController.java          # POST /api/chat（限流 + 校验）
      ConversationController.java  # conversations CRUD
      RecommendController.java     # POST /api/recommend（multipart → data URL）
      StaticController.java        # GET /（伺服 frontend/dist/index.html）
      GlobalExceptionHandler.java  # 400/404/502/503/429 + {"detail"}
    exception/
      ApiException.java
      AgentUnavailableException.java
      AgentValidationException.java
    service/
      ChatService.java             # 编排：锁 → 历史 → Python → 落库 → 裁剪 → 标题
      ConversationService.java     # CRUD + 追加 + 裁剪 + 标题
      SessionLock.java             # 接口：tryAcquire/release
      RedisSessionLock.java        # Redis NX EX + JVM 降级
      RateLimiter.java             # INCR + TTL + fail-open
    agent/
      PythonAgentClient.java       # RestClient 封装：health()/chat()
      AgentChatRequest.java        # record(message, images, history)
      AgentChatResponse.java       # record(reply, intent)
    repository/
      ConversationMapper.java      # BaseMapper + selectSummaries
      MessageMapper.java           # BaseMapper
    entity/
      Conversation.java
      Message.java
    dto/
      ChatRequest.java / ChatResponse.java / ConversationDto.java /
      ConversationSummaryDto.java / MessageDto.java
  src/main/resources/
    application.yml
    db/migration/V1__init.sql
  src/test/java/com/iclothes/
    config/StaticServeTest.java
    agent/PythonAgentClientTest.java
    service/RedisSessionLockTest.java
    service/RateLimiterTest.java
    service/ConversationServiceTest.java
    service/ChatServiceTest.java
    repository/RepositoryIT.java
    controller/HealthControllerTest.java
    controller/ChatControllerTest.java
    controller/ConversationControllerTest.java
    controller/RecommendControllerTest.java
  src/test/resources/application-test.yml
  Dockerfile                        # Task 9
app/Dockerfile                      # Task 9（Python 服务镜像）
docker-compose.yml                  # Task 9（四件套交付物）
```

---

### Task 0: 环境准备（JDK 21 + Maven + PostgreSQL 16 + Redis + 契约导出）

**Files:**
- Create: `docs/openapi-contract.json`（对外契约存档，来自 Python `/openapi.json` 或 spec §3.1）
- 无源码

**Interfaces:** 无（环境前置；后续所有 Task 依赖本机的 `java`、`mvn`、`psql`、Redis `6379`）

- [ ] **Step 1: 确认缺口**

Run:
```powershell
java -version; mvn -version; psql --version
Get-NetTCPConnection -LocalPort 6379 -State Listen -ErrorAction SilentlyContinue
```
Expected: `java`/`mvn`/`psql` 报"not recognized"，6379 无监听（本机均未装）。

- [ ] **Step 2: 安装 JDK 21（Temurin）与 Maven**

```powershell
winget install -e --id EclipseAdoptium.Temurin.21.JDK --silent --accept-package-agreements --accept-source-agreements
winget install -e --id Apache.Maven --silent --accept-package-agreements --accept-source-agreements
```

- [ ] **Step 3: 配置 JAVA_HOME 与 PATH（用户级环境变量）**

```powershell
$jh = (Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Directory | Where-Object Name -like 'jdk-21*' | Select-Object -First 1).FullName
[Environment]::SetEnvironmentVariable('JAVA_HOME', $jh, 'User')
$path = [Environment]::GetEnvironmentVariable('Path', 'User')
[Environment]::SetEnvironmentVariable('Path', "$path;C:\Program Files\Apache\maven\bin;$jh\bin", 'User')
```

- [ ] **Step 4: 验证工具链（新开终端）**

Run: `java -version; mvn -version`
Expected: `java 21.x` 与 `Apache Maven 3.9.x`。

- [ ] **Step 5: 安装 PostgreSQL 16（静默，超级用户密码 iclothes123）**

```powershell
winget install -e --id PostgreSQL.PostgreSQL.16 --silent --accept-package-agreements --accept-source-agreements --override "/quiet SUPERUSER_PASSWORD=iclothes123"
```
注意：若安装器交互失败，改用官方 EDB 安装器手动完成（密码 `iclothes123`）。

- [ ] **Step 6: 建库（应用库 + 测试库）并验证**

```powershell
$env:PGPASSWORD = 'iclothes123'
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U postgres -h localhost -c "CREATE DATABASE iclothes;"
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U postgres -h localhost -c "CREATE DATABASE iclothes_test;"
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U postgres -h localhost -c "SELECT version();"
```

- [ ] **Step 7: 安装 Redis——方案 A：Memurai Developer（首选，Redis 7 兼容，已验证 winget 存在）**

```powershell
winget install -e --id Memurai.MemuraiDeveloper --silent --accept-package-agreements --accept-source-agreements
# Memurai 默认作为 Windows 服务运行，端口 6379
Start-Sleep -Seconds 5
Test-NetConnection 127.0.0.1 -Port 6379 | Select-Object TcpTestSucceeded
```
Expected: `TcpTestSucceeded=True`。若 Memurai 安装失败，走方案 B。

- [ ] **Step 8: 安装 Redis——方案 B（备用，tporadowski/redis，经 gh-proxy）**

```powershell
$zip = "$env:TEMP\redis-win.zip"
$dir = 'D:\tools\redis'
curl.exe -s -L -m 120 -o $zip "https://gh-proxy.com/https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Expand-Archive $zip $dir -Force
Start-Process -FilePath "$dir\redis-server.exe" -WorkingDirectory $dir -WindowStyle Hidden
Start-Sleep -Seconds 3
& "$dir\redis-cli.exe" ping
```
Expected: 输出 `PONG`（方案 B 为 Redis 5.0.14，仅用到 SET NX EX/INCR/EXPIRE/DEL，兼容；优先使用方案 A）。

- [ ] **Step 9: 导出对外契约存档（Python 后端仍可启动时）**

```powershell
# 若 Python 后端可启动：uvicorn 起后执行
curl.exe -s http://127.0.0.1:8000/openapi.json -o docs/openapi-contract.json
# 不可用则按 spec §3.1 的 7 个接口手写 JSON 契约（字段/类型/错误码必须与 spec 一致）
```

- [ ] **Step 10: Commit**

```bash
git add docs/openapi-contract.json
git commit -m "chore: export API contract baseline"
```

---

### Task 1: Python 无状态化改造 + pytest 契约测试

**Files:**
- Create: `app/api/routers/agent.py`
- Create: `test/test_agent_contract.py`
- Modify: `app/main.py`（路由挂载改 agent + health）
- Delete: `app/api/routers/chat.py`、`app/api/routers/recommend.py`、`app/services/`（整个目录）

**Interfaces:**
- Consumes: `app.graph.workflow.run_chat(message, images, history) -> {"reply": str, "intent": str}`（已存在，勿改）
- Produces: `POST /api/agent/chat`，请求 `{"message", "images", "history": [{"role","content"}]}` → `{"reply", "intent"}`；400 `{"detail"}` / 502 `{"detail"}`；`/api/health` 保留

- [ ] **Step 1: 写契约测试（pytest，mock LLM，不触发真实 API）**

```python
# test/test_agent_contract.py
"""Agent 服务契约测试：mock 掉 LLM，验证请求/响应/错误格式。"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.api.routers import agent  # noqa: E402
from app.repositories.model_repo import ModelRepository  # noqa: E402


class FakeModel:
    """假的 ChatOpenAI 替身：ainvoke 返回固定文本。"""

    def __init__(self, text: str) -> None:
        self._text = text

    async def ainvoke(self, messages):
        return SimpleNamespace(content=self._text)


@pytest.fixture
def client(monkeypatch):
    # 意图路由为关键词规则，chat 意图走 deepseek，recommend 走 qianwen + deepseek
    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: FakeModel("助手回复")))
    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: FakeModel("体征分析")))
    app = FastAPI()
    app.include_router(agent.router)
    return TestClient(app)


def test_chat_intent(client):
    resp = client.post("/api/agent/chat", json={
        "message": "你好，介绍一下你自己",
        "images": [],
        "history": [],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "助手回复"
    assert body["intent"] == "chat"


def test_recommend_intent_without_images(client):
    resp = client.post("/api/agent/chat", json={
        "message": "帮我推荐上班通勤的穿搭",
        "images": [],
        "history": [],
    })
    assert resp.status_code == 200
    assert resp.json()["intent"] == "recommend"


def test_images_force_recommend(client):
    resp = client.post("/api/agent/chat", json={
        "message": "随便聊聊",
        "images": ["data:image/png;base64,AAAA"],
        "history": [],
    })
    assert resp.status_code == 200
    assert resp.json()["intent"] == "recommend"


def test_history_context_passed(client):
    history = [
        {"role": "user", "content": "之前的话题"},
        {"role": "assistant", "content": "好的"},
    ]
    resp = client.post("/api/agent/chat", json={
        "message": "继续",
        "images": [],
        "history": history,
    })
    assert resp.status_code == 200


def test_empty_message_rejected(client):
    resp = client.post("/api/agent/chat", json={"message": "", "images": [], "history": []})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "消息内容不能为空"


def test_bad_image_format_rejected(client):
    resp = client.post("/api/agent/chat", json={
        "message": "hi", "images": ["data:image/gif;base64,AAAA"], "history": [],
    })
    assert resp.status_code == 400
    assert resp.json()["detail"] == "不支持的图片格式，仅支持 JPG/PNG"


def test_missing_key_returns_502(client, monkeypatch):
    def raise_missing(*args, **kwargs):
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(raise_missing))
    resp = client.post("/api/agent/chat", json={"message": "你好", "images": [], "history": []})
    assert resp.status_code == 502
    assert "未配置" in resp.json()["detail"]
```

- [ ] **Step 2: 运行测试确认失败**

Run（项目根，用 conda Python）:
```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test/test_agent_contract.py -v
```
Expected: 失败——`app.api.routers.agent` 不存在（ImportError）。

- [ ] **Step 3: 实现无状态 agent 路由**

```python
# app/api/routers/agent.py
"""Agent 服务契约接口：无状态推理入口（Java 业务后端调用）。"""
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.graph.workflow import run_chat

router = APIRouter()

DATA_URL_RE = re.compile(r"^data:image/(jpeg|png);base64,")


class AgentChatRequest(BaseModel):
    """无状态请求：message/images/history 一次带全。"""

    message: str = Field(default="", max_length=2000)
    images: list[str] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    reply: str
    intent: str


def _validate_images(images: list[str]) -> list[str]:
    """图片 data URL 校验：格式/数量/大小（与旧 /api/chat 校验一致）。"""
    if len(images) > settings.MAX_UPLOAD_COUNT:
        raise HTTPException(status_code=400, detail=f"最多上传 {settings.MAX_UPLOAD_COUNT} 张照片")
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    validated: list[str] = []
    for url in images:
        m = DATA_URL_RE.match(url)
        if not m:
            raise HTTPException(status_code=400, detail="不支持的图片格式，仅支持 JPG/PNG")
        payload_len = len(url) - m.end()
        approx_bytes = int(payload_len * 3 / 4)
        if approx_bytes > max_bytes:
            raise HTTPException(status_code=400, detail=f"图片超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")
        validated.append(url)
    return validated


@router.post("/api/agent/chat", response_model=AgentChatResponse)
async def agent_chat(payload: AgentChatRequest) -> AgentChatResponse:
    """无状态推理：意图路由 → chat/recommend 分支 → 返回回复与意图。"""
    message = payload.message.strip()
    images = _validate_images(payload.images)
    if not message and not images:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    try:
        result = await run_chat(message, images, payload.history)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return AgentChatResponse(reply=result["reply"], intent=result["intent"])
```

- [ ] **Step 4: 修改 main.py 挂载并删除废弃模块**

`app/main.py` 中：
```python
from app.api.routers import agent, health  # 替换原 "chat, health, recommend"
...
app.include_router(agent.router)   # 替换 app.include_router(chat.router)
app.include_router(health.router)
# 删除 app.include_router(recommend.router)
```

删除：
```powershell
Remove-Item app\api\routers\chat.py, app\api\routers\recommend.py -Force
Remove-Item app\services -Recurse -Force
```

- [ ] **Step 5: 运行契约测试确认通过**

Run:
```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test/test_agent_contract.py -v
```
Expected: 7 个用例全绿（httpx 由 langchain-openai 传递依赖提供；如缺失先 `pip install httpx`）。

- [ ] **Step 6: 回归旧图逻辑测试**

Run:
```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test/test_workflow.py -v
```
Expected: 图编译与 `run_recommendation` 正常（不调真实 LLM 的部分通过；调用真实 API 的用例可跳过）。

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: stateless python agent service with /api/agent/chat contract"
```

---

### Task 2: Java 脚手架 + AppProperties + health 代理（TDD）

**Files:**
- Create: `iclothes-server/pom.xml`
- Create: `iclothes-server/src/main/java/com/iclothes/IclothesApplication.java`
- Create: `iclothes-server/src/main/java/com/iclothes/config/AppProperties.java`
- Create: `iclothes-server/src/main/java/com/iclothes/agent/PythonAgentClient.java`（本 Task 仅 health()，chat() 在 Task 5 扩展）
- Create: `iclothes-server/src/main/java/com/iclothes/config/RestClientConfig.java`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/HealthController.java`
- Create: `iclothes-server/src/main/resources/application.yml`
- Create: `iclothes-server/src/test/resources/application-test.yml`
- Test: `iclothes-server/src/test/java/com/iclothes/controller/HealthControllerTest.java`

**Interfaces:**
- Produces:
  - `AppProperties`：`getUpload()`（`maxCount=3`、`maxSizeMb=5`）、`getAgent()`（`baseUrl`、`connectTimeoutMs=3000`、`readTimeoutMs=60000`、`healthTimeoutMs=2000`）、`getRateLimit()`（`perMinute=60`）、`getFrontend()`（`dir="frontend/dist"`）
  - `PythonAgentClient.healthQianwenConfigured() -> boolean`（2s 超时，异常 → false）
  - `GET /api/health` → `{"status":"ok","qianwen_configured":bool}`

- [ ] **Step 1: 写失败测试**

```java
// HealthControllerTest.java
package com.iclothes.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.agent.PythonAgentClient;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(HealthController.class)
class HealthControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean
    PythonAgentClient agentClient;

    @Test
    void healthReportsQianwenConfiguredWhenPythonUp() throws Exception {
        when(agentClient.healthQianwenConfigured()).thenReturn(true);
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.qianwen_configured").value(true));
    }

    @Test
    void healthStillOkWhenPythonDown() throws Exception {
        when(agentClient.healthQianwenConfigured()).thenReturn(false);
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.qianwen_configured").value(false));
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=HealthControllerTest`
Expected: 编译失败（工程/类不存在）。

- [ ] **Step 3: 脚手架 + 最小实现**

`pom.xml`（完整，版本锁定）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.3</version>
    <relativePath/>
  </parent>
  <groupId>com.iclothes</groupId>
  <artifactId>iclothes-server</artifactId>
  <version>0.1.0</version>
  <properties>
    <java.version>21</java.version>
    <mybatis-plus.version>3.5.7</mybatis-plus.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
      <groupId>com.baomidou</groupId>
      <artifactId>mybatis-plus-spring-boot3-starter</artifactId>
      <version>${mybatis-plus.version}</version>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

`AppProperties.java`：

```java
package com.iclothes.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "iclothes")
public class AppProperties {

    private final Upload upload = new Upload();
    private final Agent agent = new Agent();
    private final RateLimit rateLimit = new RateLimit();
    private final Frontend frontend = new Frontend();

    public Upload getUpload() { return upload; }
    public Agent getAgent() { return agent; }
    public RateLimit getRateLimit() { return rateLimit; }
    public Frontend getFrontend() { return frontend; }

    public static class Upload {
        private int maxCount = 3;
        private int maxSizeMb = 5;
        public int getMaxCount() { return maxCount; }
        public void setMaxCount(int v) { maxCount = v; }
        public int getMaxSizeMb() { return maxSizeMb; }
        public void setMaxSizeMb(int v) { maxSizeMb = v; }
    }

    public static class Agent {
        private String baseUrl = "http://127.0.0.1:8000";
        private int connectTimeoutMs = 3000;
        private int readTimeoutMs = 60000;
        private int healthTimeoutMs = 2000;
        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String v) { baseUrl = v; }
        public int getConnectTimeoutMs() { return connectTimeoutMs; }
        public void setConnectTimeoutMs(int v) { connectTimeoutMs = v; }
        public int getReadTimeoutMs() { return readTimeoutMs; }
        public void setReadTimeoutMs(int v) { readTimeoutMs = v; }
        public int getHealthTimeoutMs() { return healthTimeoutMs; }
        public void setHealthTimeoutMs(int v) { healthTimeoutMs = v; }
    }

    public static class RateLimit {
        private int perMinute = 60;
        public int getPerMinute() { return perMinute; }
        public void setPerMinute(int v) { perMinute = v; }
    }

    public static class Frontend {
        private String dir = "frontend/dist";
        public String getDir() { return dir; }
        public void setDir(String v) { dir = v; }
    }
}
```

`RestClientConfig.java`（health 与 chat 两个 RestClient，超时不同）：

```java
package com.iclothes.config;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfig {

    @Bean
    public RestClient pythonChatClient(AppProperties properties) {
        return RestClient.builder()
                .baseUrl(properties.getAgent().getBaseUrl())
                .requestFactory(factory(properties.getAgent().getConnectTimeoutMs(),
                        properties.getAgent().getReadTimeoutMs()))
                .build();
    }

    @Bean
    public RestClient pythonHealthClient(AppProperties properties) {
        return RestClient.builder()
                .baseUrl(properties.getAgent().getBaseUrl())
                .requestFactory(factory(properties.getAgent().getHealthTimeoutMs(),
                        properties.getAgent().getHealthTimeoutMs()))
                .build();
    }

    private SimpleClientHttpRequestFactory factory(int connectMs, int readMs) {
        SimpleClientHttpRequestFactory f = new SimpleClientHttpRequestFactory();
        f.setConnectTimeout(Duration.ofMillis(connectMs));
        f.setReadTimeout(Duration.ofMillis(readMs));
        return f;
    }
}
```

`PythonAgentClient.java`（本 Task 仅 health；chat 在 Task 5 追加方法，不要删除 health）：

```java
package com.iclothes.agent;

import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PythonAgentClient {

    private final RestClient chatClient;
    private final RestClient healthClient;

    public PythonAgentClient(
            @org.springframework.beans.factory.annotation.Qualifier("pythonChatClient") RestClient chatClient,
            @org.springframework.beans.factory.annotation.Qualifier("pythonHealthClient") RestClient healthClient) {
        this.chatClient = chatClient;
        this.healthClient = healthClient;
    }

    /** 代理 Python /api/health（2s 超时）；不可达/异常一律返回 false。 */
    public boolean healthQianwenConfigured() {
        try {
            Map<?, ?> body = healthClient.get().uri("/api/health").retrieve().body(Map.class);
            return body != null && Boolean.TRUE.equals(body.get("qianwen_configured"));
        } catch (Exception e) {
            return false;
        }
    }
}
```

`HealthController.java`：

```java
package com.iclothes.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.agent.PythonAgentClient;

@RestController
public class HealthController {

    private final PythonAgentClient agentClient;

    public HealthController(PythonAgentClient agentClient) { this.agentClient = agentClient; }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "qianwen_configured", agentClient.healthQianwenConfigured());
    }
}
```

`IclothesApplication.java`：

```java
package com.iclothes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import com.iclothes.config.AppProperties;

@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class IclothesApplication {
    public static void main(String[] args) {
        SpringApplication.run(IclothesApplication.class, args);
    }
}
```

`application.yml`：

```yaml
spring:
  application:
    name: iclothes-server
  threads:
    virtual:
      enabled: true
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/iclothes}
    username: ${DB_USER:postgres}
    password: ${DB_PASSWORD:iclothes123}
  flyway:
    enabled: true
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 40MB
  data:
    redis:
      host: ${REDIS_HOST:127.0.0.1}
      port: ${REDIS_PORT:6379}

iclothes:
  agent:
    base-url: ${AGENT_BASE_URL:http://127.0.0.1:8000}
  upload:
    max-count: 3
    max-size-mb: 5
  rate-limit:
    per-minute: 60
  frontend:
    dir: ${FRONTEND_DIST:frontend/dist}

mybatis-plus:
  configuration:
    map-underscore-to-camel-case: true
```

`application-test.yml`：

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/iclothes_test
    username: postgres
    password: iclothes123
  flyway:
    enabled: true
  data:
    redis:
      host: 127.0.0.1
      port: 6379

iclothes:
  agent:
    base-url: http://127.0.0.1:8000
```

- [ ] **Step 4: 运行测试确认通过**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=HealthControllerTest`
Expected: BUILD SUCCESS，2 个用例通过。

- [ ] **Step 5: Commit**

```bash
git add iclothes-server/
git commit -m "feat: scaffold Spring Boot app with health proxy"
```

---

### Task 3: PG schema + 实体 + Mapper + CRUD 集成测试（TDD）

**Files:**
- Create: `iclothes-server/src/main/resources/db/migration/V1__init.sql`
- Create: `iclothes-server/src/main/java/com/iclothes/entity/Conversation.java`
- Create: `iclothes-server/src/main/java/com/iclothes/entity/Message.java`
- Create: `iclothes-server/src/main/java/com/iclothes/repository/ConversationMapper.java`
- Create: `iclothes-server/src/main/java/com/iclothes/repository/MessageMapper.java`
- Create: `iclothes-server/src/main/java/com/iclothes/dto/ConversationSummaryDto.java`
- Test: `iclothes-server/src/test/java/com/iclothes/repository/RepositoryIT.java`

**Interfaces:**
- Produces:
  - `Conversation`（`UUID id`、`String title`、`LocalDateTime createdAt/updatedAt`）
  - `Message`（`Long id`、`UUID conversationId`、`String role/content/intent`、`List<String> images`、`LocalDateTime createdAt`）
  - `ConversationMapper`：`BaseMapper<Conversation>` + `List<ConversationSummaryDto> selectSummaries()`
  - `MessageMapper`：`BaseMapper<Message>`

- [ ] **Step 1: 写 schema 与实体**

`V1__init.sql`（与 spec §6 逐字一致）：

```sql
CREATE TABLE conversations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title      VARCHAR(100) NOT NULL DEFAULT '新对话',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL,
    content         TEXT NOT NULL,
    intent          VARCHAR(16) NOT NULL DEFAULT '',
    images          JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);
CREATE INDEX idx_conversations_updated ON conversations(updated_at DESC);
```

`Conversation.java`：

```java
package com.iclothes.entity;

import java.time.LocalDateTime;
import java.util.UUID;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

@TableName("conversations")
public class Conversation {

    @TableId(type = IdType.INPUT)
    private UUID id;
    private String title;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Conversation() {}
    public Conversation(UUID id, String title, LocalDateTime createdAt, LocalDateTime updatedAt) {
        this.id = id; this.title = title; this.createdAt = createdAt; this.updatedAt = updatedAt;
    }

    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime v) { createdAt = v; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime v) { updatedAt = v; }
}
```

`Message.java`：

```java
package com.iclothes.entity;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;

@TableName(value = "messages", autoResultMap = true)
public class Message {

    @TableId(type = IdType.AUTO)
    private Long id;
    private UUID conversationId;
    private String role;
    private String content;
    private String intent;
    @TableField(typeHandler = JacksonTypeHandler.class)
    private List<String> images;
    private LocalDateTime createdAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public UUID getConversationId() { return conversationId; }
    public void setConversationId(UUID v) { conversationId = v; }
    public String getRole() { return role; }
    public void setRole(String v) { role = v; }
    public String getContent() { return content; }
    public void setContent(String v) { content = v; }
    public String getIntent() { return intent; }
    public void setIntent(String v) { intent = v; }
    public List<String> getImages() { return images; }
    public void setImages(List<String> v) { images = v; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime v) { createdAt = v; }
}
```

`ConversationSummaryDto.java`：

```java
package com.iclothes.dto;

import java.time.LocalDateTime;

public class ConversationSummaryDto {
    private String id;
    private String title;
    private String preview;
    private LocalDateTime updatedAt;

    public String getId() { return id; }
    public void setId(String v) { id = v; }
    public String getTitle() { return title; }
    public void setTitle(String v) { title = v; }
    public String getPreview() { return preview; }
    public void setPreview(String v) { preview = v; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime v) { updatedAt = v; }
}
```

`ConversationMapper.java`：

```java
package com.iclothes.repository;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.entity.Conversation;

@Mapper
public interface ConversationMapper extends BaseMapper<Conversation> {

    @Select("""
        SELECT c.id::text AS id, c.title, c.updated_at AS updatedAt,
               (SELECT m.content FROM messages m
                 WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1) AS preview
        FROM conversations c
        ORDER BY c.updated_at DESC
        """)
    List<ConversationSummaryDto> selectSummaries();
}
```

`MessageMapper.java`：

```java
package com.iclothes.repository;

import org.apache.ibatis.annotations.Mapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.iclothes.entity.Message;

@Mapper
public interface MessageMapper extends BaseMapper<Message> {
}
```

- [ ] **Step 2: 写失败集成测试（前置：Task 0 已建 iclothes_test 库）**

```java
// RepositoryIT.java
package com.iclothes.repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.entity.Conversation;
import com.iclothes.entity.Message;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class RepositoryIT {

    @Autowired ConversationMapper conversations;
    @Autowired MessageMapper messages;

    @Test
    void conversationCrudAndCascade() {
        UUID cid = UUID.randomUUID();
        conversations.insert(new Conversation(cid, "测试会话", LocalDateTime.now(), LocalDateTime.now()));

        Message m = new Message();
        m.setConversationId(cid);
        m.setRole("user");
        m.setContent("你好");
        m.setIntent("");
        m.setImages(List.of("data:image/png;base64,AAAA"));
        m.setCreatedAt(LocalDateTime.now());
        messages.insert(m);

        assertThat(messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, cid))).hasSize(1);

        conversations.deleteById(cid);
        assertThat(messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, cid))).isEmpty();
    }

    @Test
    void summariesIncludePreview() {
        UUID cid = UUID.randomUUID();
        conversations.insert(new Conversation(cid, "摘要测试", LocalDateTime.now(), LocalDateTime.now()));
        Message m = new Message();
        m.setConversationId(cid);
        m.setRole("assistant");
        m.setContent("这是最后一条消息");
        m.setIntent("chat");
        m.setImages(List.of());
        m.setCreatedAt(LocalDateTime.now());
        messages.insert(m);

        List<ConversationSummaryDto> summaries = conversations.selectSummaries();
        ConversationSummaryDto first = summaries.get(0);
        assertThat(first.getId()).isEqualTo(cid.toString());
        assertThat(first.getTitle()).isEqualTo("摘要测试");
        assertThat(first.getPreview()).isEqualTo("这是最后一条消息");
    }
}
```

- [ ] **Step 3: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=RepositoryIT`
Expected: 编译失败（实体/Mapper 尚不存在）。

- [ ] **Step 4: 运行测试确认通过**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=RepositoryIT`
Expected: BUILD SUCCESS，2 用例通过（Flyway 自动建表）。

- [ ] **Step 5: Commit**

```bash
git add iclothes-server/
git commit -m "feat: schema, entities, and mappers"
```

---

### Task 4: Redis 基础设施（SessionLock + RateLimiter）+ 测试（含故障降级）

**Files:**
- Create: `iclothes-server/src/main/java/com/iclothes/service/SessionLock.java`
- Create: `iclothes-server/src/main/java/com/iclothes/service/RedisSessionLock.java`
- Create: `iclothes-server/src/main/java/com/iclothes/service/RateLimiter.java`
- Test: `iclothes-server/src/test/java/com/iclothes/service/RedisSessionLockTest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/service/RateLimiterTest.java`

**Interfaces:**
- Consumes: `AppProperties`（Task 2）、`StringRedisTemplate`（Spring Data Redis 自动配置）
- Produces:
  - `SessionLock.tryAcquire(String key, long waitMillis) -> boolean`、`SessionLock.release(String key)`
  - `RateLimiter.allow(String clientKey) -> boolean`

- [ ] **Step 1: 写失败测试（锁：成功/竞争/降级；限流：阈值/fail-open）**

```java
// RedisSessionLockTest.java
package com.iclothes.service;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RedisSessionLockTest {

    @Mock StringRedisTemplate redis;
    @Mock ValueOperations<String, String> ops;

    @Test
    void acquireSuccessWhenRedisSetsKey() {
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.setIfAbsent(anyString(), anyString(), any(Duration.class))).thenReturn(Boolean.TRUE);

        RedisSessionLock lock = new RedisSessionLock(redis);
        assertThat(lock.tryAcquire("conversation:abc:lock", 1000)).isTrue();
    }

    @Test
    void acquireFailsWhenKeyHeld() {
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.setIfAbsent(anyString(), anyString(), any(Duration.class))).thenReturn(Boolean.FALSE);

        RedisSessionLock lock = new RedisSessionLock(redis);
        assertThat(lock.tryAcquire("conversation:abc:lock", 120)).isFalse();
    }

    @Test
    void acquireFallsBackToJvmLockWhenRedisDown() {
        when(redis.opsForValue()).thenThrow(new RuntimeException("redis down"));

        RedisSessionLock lock = new RedisSessionLock(redis);
        assertThat(lock.tryAcquire("conversation:abc:lock", 100)).isTrue();
        lock.release("conversation:abc:lock");
    }

    @Test
    void releaseDeletesKey() {
        RedisSessionLock lock = new RedisSessionLock(redis);
        lock.release("conversation:abc:lock");
        verify(redis).delete("conversation:abc:lock");
    }
}
```

```java
// RateLimiterTest.java
package com.iclothes.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import com.iclothes.config.AppProperties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RateLimiterTest {

    @Mock StringRedisTemplate redis;
    @Mock ValueOperations<String, String> ops;

    private AppProperties props() {
        AppProperties p = new AppProperties();
        p.getRateLimit().setPerMinute(60);
        return p;
    }

    @Test
    void allowWithinThreshold() {
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.increment(anyString())).thenReturn(5L);

        RateLimiter limiter = new RateLimiter(redis, props());
        assertThat(limiter.allow("127.0.0.1")).isTrue();
    }

    @Test
    void denyAboveThreshold() {
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.increment(anyString())).thenReturn(61L);

        RateLimiter limiter = new RateLimiter(redis, props());
        assertThat(limiter.allow("127.0.0.1")).isFalse();
    }

    @Test
    void failOpenWhenRedisDown() {
        when(redis.opsForValue()).thenThrow(new RuntimeException("redis down"));

        RateLimiter limiter = new RateLimiter(redis, props());
        assertThat(limiter.allow("127.0.0.1")).isTrue();
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=RedisSessionLockTest,RateLimiterTest`
Expected: 编译失败（类不存在）。

- [ ] **Step 3: 最小实现**

```java
// SessionLock.java
package com.iclothes.service;

public interface SessionLock {
    /** 尝试获取锁；waitMillis 内轮询，超时返回 false。 */
    boolean tryAcquire(String key, long waitMillis);

    /** 释放锁（必须与 tryAcquire 成对）。 */
    void release(String key);
}
```

```java
// RedisSessionLock.java
package com.iclothes.service;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisSessionLock implements SessionLock {

    private static final Logger log = LoggerFactory.getLogger(RedisSessionLock.class);
    private static final long TTL_SECONDS = 5;
    private static final long POLL_MS = 50;

    private final StringRedisTemplate redis;
    private final Map<String, ReentrantLock> fallbackLocks = new ConcurrentHashMap<>();

    public RedisSessionLock(StringRedisTemplate redis) { this.redis = redis; }

    @Override
    public boolean tryAcquire(String key, long waitMillis) {
        long deadline = System.currentTimeMillis() + waitMillis;
        try {
            do {
                Boolean ok = redis.opsForValue().setIfAbsent(key, "1", Duration.ofSeconds(TTL_SECONDS));
                if (Boolean.TRUE.equals(ok)) {
                    return true;
                }
                Thread.sleep(POLL_MS);
            } while (System.currentTimeMillis() < deadline);
            return false;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        } catch (Exception e) {
            // Redis 故障 → JVM 内锁降级（单实例有效）
            log.warn("Redis 不可用，会话锁降级为 JVM 内锁: {}", e.getMessage());
            return fallbackLocks.computeIfAbsent(key, k -> new ReentrantLock()).tryLock();
        }
    }

    @Override
    public void release(String key) {
        try {
            redis.delete(key);
        } catch (Exception e) {
            ReentrantLock lock = fallbackLocks.get(key);
            if (lock != null && lock.isHeldByCurrentThread()) {
                lock.unlock();
            }
        }
    }
}
```

```java
// RateLimiter.java
package com.iclothes.service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import com.iclothes.config.AppProperties;

@Component
public class RateLimiter {

    private static final Logger log = LoggerFactory.getLogger(RateLimiter.class);
    private static final DateTimeFormatter MINUTE = DateTimeFormatter.ofPattern("yyyyMMddHHmm");

    private final StringRedisTemplate redis;
    private final AppProperties properties;

    public RateLimiter(StringRedisTemplate redis, AppProperties properties) {
        this.redis = redis;
        this.properties = properties;
    }

    /** 按客户端标识限流；Redis 故障 fail-open（放行 + 告警）。 */
    public boolean allow(String clientKey) {
        try {
            String key = "rate:" + clientKey + ":" + MINUTE.format(LocalDateTime.now());
            Long count = redis.opsForValue().increment(key);
            if (count != null && count == 1) {
                redis.expire(key, Duration.ofSeconds(61));
            }
            return count == null || count <= properties.getRateLimit().getPerMinute();
        } catch (Exception e) {
            log.warn("Redis 不可用，限流 fail-open: {}", e.getMessage());
            return true;
        }
    }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=RedisSessionLockTest,RateLimiterTest`
Expected: BUILD SUCCESS，7 用例通过（含降级路径）。

- [ ] **Step 5: Commit**

```bash
git add iclothes-server/
git commit -m "feat: redis session lock with JVM fallback and rate limiter"
```

---

### Task 5: PythonAgentClient.chat + mock 契约测试（TDD）

**Files:**
- Create: `iclothes-server/src/main/java/com/iclothes/exception/AgentUnavailableException.java`
- Create: `iclothes-server/src/main/java/com/iclothes/exception/AgentValidationException.java`
- Create: `iclothes-server/src/main/java/com/iclothes/agent/AgentChatRequest.java`
- Create: `iclothes-server/src/main/java/com/iclothes/agent/AgentChatResponse.java`
- Modify: `iclothes-server/src/main/java/com/iclothes/agent/PythonAgentClient.java`（追加 `chat()`）
- Test: `iclothes-server/src/test/java/com/iclothes/agent/PythonAgentClientTest.java`

**Interfaces:**
- Consumes: `RestClient` Bean（Task 2）
- Produces:
  - `AgentChatRequest` record：`(String message, List<String> images, List<HistoryItem> history)`，`HistoryItem` record：`(String role, String content)`
  - `AgentChatResponse` record：`(String reply, String intent)`
  - `PythonAgentClient.chat(String message, List<String> images, List<AgentChatRequest.HistoryItem> history) -> AgentChatResponse`（400 → `AgentValidationException`；5xx/超时/连接失败 → `AgentUnavailableException`；**不重试**）

- [ ] **Step 1: 写失败测试（MockRestServiceServer 绑定 RestClient.Builder）**

```java
// PythonAgentClientTest.java
package com.iclothes.agent;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import com.iclothes.config.AppProperties;
import com.iclothes.exception.AgentUnavailableException;
import com.iclothes.exception.AgentValidationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;

class PythonAgentClientTest {

    private AppProperties props() {
        AppProperties p = new AppProperties();
        p.getAgent().setBaseUrl("http://127.0.0.1:8000");
        return p;
    }

    private PythonAgentClient client(RestClient.Builder builder, AppProperties p) {
        RestClient chat = builder.baseUrl(p.getAgent().getBaseUrl()).build();
        RestClient health = RestClient.builder().baseUrl(p.getAgent().getBaseUrl()).build();
        return new PythonAgentClient(chat, health);
    }

    @Test
    void chatSendsContractBodyAndParsesResponse() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        PythonAgentClient client = client(builder, props());

        server.expect(once(), requestTo("http://127.0.0.1:8000/api/agent/chat"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("你好"))
                .andExpect(jsonPath("$.history[0].role").value("user"))
                .andRespond(withSuccess("{\"reply\":\"你好！\",\"intent\":\"chat\"}",
                        MediaType.APPLICATION_JSON));

        AgentChatResponse resp = client.chat("你好", List.of(),
                List.of(new AgentChatRequest.HistoryItem("user", "之前的话题")));

        assertThat(resp.reply()).isEqualTo("你好！");
        assertThat(resp.intent()).isEqualTo("chat");
        server.verify();
    }

    @Test
    void chatPropagatesValidationError() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        PythonAgentClient client = client(builder, props());

        server.expect(once(), requestTo("http://127.0.0.1:8000/api/agent/chat"))
                .andRespond(withStatus(org.springframework.http.HttpStatus.BAD_REQUEST)
                        .body("{\"detail\":\"消息内容不能为空\"}").contentType(MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.chat("", List.of(), List.of()))
                .isInstanceOf(AgentValidationException.class)
                .hasMessage("消息内容不能为空");
    }

    @Test
    void chatWrapsServerErrorAsUnavailable() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        PythonAgentClient client = client(builder, props());

        server.expect(once(), requestTo("http://127.0.0.1:8000/api/agent/chat"))
                .andRespond(withServerError());

        assertThatThrownBy(() -> client.chat("你好", List.of(), List.of()))
                .isInstanceOf(AgentUnavailableException.class)
                .hasMessageContaining("AI 服务暂不可用");
    }

    @Test
    void chatWrapsConnectFailureAsUnavailable() {
        RestClient.Builder builder = RestClient.builder();
        PythonAgentClient client = client(builder, props());

        assertThatThrownBy(() -> client.chat("你好", List.of(), List.of()))
                .isInstanceOf(AgentUnavailableException.class);
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=PythonAgentClientTest`
Expected: 编译失败（record/异常/chat 方法不存在）。

- [ ] **Step 3: 实现 DTO、异常与 chat()**

```java
// AgentChatRequest.java
package com.iclothes.agent;

import java.util.List;

public record AgentChatRequest(String message, List<String> images, List<HistoryItem> history) {

    public record HistoryItem(String role, String content) {}
}
```

```java
// AgentChatResponse.java
package com.iclothes.agent;

public record AgentChatResponse(String reply, String intent) {
}
```

```java
// AgentUnavailableException.java
package com.iclothes.exception;

public class AgentUnavailableException extends RuntimeException {
    public AgentUnavailableException(String message) { super(message); }
    public AgentUnavailableException(String message, Throwable cause) { super(message, cause); }
}
```

```java
// AgentValidationException.java
package com.iclothes.exception;

public class AgentValidationException extends RuntimeException {
    public AgentValidationException(String message) { super(message); }
}
```

`PythonAgentClient.java` 追加（保留 health 方法）：

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestClientException;
import com.iclothes.exception.AgentUnavailableException;
import com.iclothes.exception.AgentValidationException;

private final ObjectMapper objectMapper = new ObjectMapper();

/** 调 Python /api/agent/chat（无状态，不重试）。 */
public AgentChatResponse chat(String message, List<String> images,
                              List<AgentChatRequest.HistoryItem> history) {
    try {
        return chatClient.post()
                .uri("/api/agent/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new AgentChatRequest(message, images, history))
                .retrieve()
                .body(AgentChatResponse.class);
    } catch (RestClientResponseException e) {
        if (e.getStatusCode().value() == 400) {
            throw new AgentValidationException(extractDetail(e.getResponseBodyAsString()));
        }
        throw new AgentUnavailableException("AI 服务暂不可用，请稍后重试", e);
    } catch (RestClientException e) {
        throw new AgentUnavailableException("AI 服务暂不可用，请稍后重试", e);
    }
}

private String extractDetail(String body) {
    try {
        return objectMapper.readTree(body).path("detail").asText("AI 服务暂不可用，请稍后重试");
    } catch (Exception e) {
        return "AI 服务暂不可用，请稍后重试";
    }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=PythonAgentClientTest`
Expected: BUILD SUCCESS，4 用例通过。

- [ ] **Step 5: Commit**

```bash
git add iclothes-server/
git commit -m "feat: python agent client with contract test"
```

---

### Task 6: ConversationService + ChatService 编排（锁路径 + 不重试）+ 单测

**Files:**
- Create: `iclothes-server/src/main/java/com/iclothes/exception/ApiException.java`
- Create: `iclothes-server/src/main/java/com/iclothes/service/ConversationService.java`
- Create: `iclothes-server/src/main/java/com/iclothes/service/ChatService.java`
- Create: `iclothes-server/src/main/java/com/iclothes/dto/ChatResponse.java`
- Create: `iclothes-server/src/main/java/com/iclothes/dto/ChatRequest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/service/ConversationServiceTest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/service/ChatServiceTest.java`

**Interfaces:**
- Consumes: `ConversationMapper/MessageMapper`（Task 3）、`SessionLock`/`RateLimiter`（Task 4）、`PythonAgentClient.chat`（Task 5）
- Produces:
  - `ApiException(int status, String detail)`
  - `ConversationService`：`create() -> ConversationDto`、`listSummaries() -> List<ConversationSummaryDto>`、`get(UUID) -> ConversationDto|null`、`delete(UUID) -> boolean`、`lastMessages(UUID, int limit) -> List<Message>`、`appendUser(UUID, String content, List<String> images)`、`appendAssistant(UUID, String content, String intent)`、`trim(UUID)`、`setTitle(UUID, String)`、`getTitle(UUID) -> String`
  - `ChatService.chat(String conversationId, String message, List<String> images) -> ChatResponse`；锁失败 → `ApiException(503, "请求过于频繁，请稍后重试")`
  - `ChatRequest`（`conversationId`/`message`/`images`）、`ChatResponse`（`conversationId`/`reply`/`intent`/`title`）

- [ ] **Step 1: 写失败测试（ChatService 编排，全部 mock）**

```java
// ChatServiceTest.java
package com.iclothes.service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import com.iclothes.agent.AgentChatRequest;
import com.iclothes.agent.AgentChatResponse;
import com.iclothes.agent.PythonAgentClient;
import com.iclothes.dto.ChatResponse;
import com.iclothes.entity.Conversation;
import com.iclothes.entity.Message;
import com.iclothes.exception.ApiException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ChatServiceTest {

    @Mock ConversationService conversations;
    @Mock PythonAgentClient agentClient;
    @Mock SessionLock sessionLock;

    ChatService service;
    UUID cid = UUID.randomUUID();
    String lockKey = "conversation:" + cid + ":lock";

    @BeforeEach
    void setUp() {
        when(sessionLock.tryAcquire(anyString(), eq(3000L))).thenReturn(true);
        when(agentClient.chat(anyString(), anyList(), anyList()))
                .thenReturn(new AgentChatResponse("回复", "chat"));
        service = new ChatService(conversations, agentClient, sessionLock);
    }

    @Test
    void chatOrchestratesLockAgentPersistAndRelease() {
        when(conversations.getTitle(cid)).thenReturn("旧标题");

        ChatResponse resp = service.chat(cid.toString(), "你好", List.of());

        assertThat(resp.getReply()).isEqualTo("回复");
        assertThat(resp.getIntent()).isEqualTo("chat");
        verify(sessionLock).tryAcquire(lockKey, 3000);
        verify(agentClient, times(1)).chat(eq("你好"), anyList(), anyList()); // 恰好一次 = 不重试
        verify(conversations).appendUser(eq(cid), eq("你好"), anyList());
        verify(conversations).appendAssistant(eq(cid), eq("回复"), eq("chat"));
        verify(conversations).trim(cid);
        verify(sessionLock).release(lockKey);
    }

    @Test
    void newConversationGetsCreatedAndTitled() {
        when(conversations.getTitle(any(UUID.class))).thenReturn("新对话");
        when(conversations.create()).thenAnswer(inv -> {
            ConversationDtoHelper.recordCreated(cid);
            return null;
        });

        service.chat(null, "帮我推荐一条裙子", List.of());
        // 无法直接断言 create 内部，改为断言标题落库路径
        verify(conversations).setTitle(any(UUID.class), eq("帮我推荐一条裙子"));
    }

    @Test
    void lockTimeoutThrows503AndSkipsAgent() {
        when(sessionLock.tryAcquire(anyString(), eq(3000L))).thenReturn(false);

        assertThatThrownBy(() -> service.chat(cid.toString(), "你好", List.of()))
                .isInstanceOf(ApiException.class)
                .satisfies(e -> assertThat(((ApiException) e).getStatus()).isEqualTo(503));
        verify(agentClient, never()).chat(anyString(), anyList(), anyList());
    }

    @Test
    void agentFailurePropagatesWithoutRetry() {
        when(agentClient.chat(anyString(), anyList(), anyList()))
                .thenThrow(new com.iclothes.exception.AgentUnavailableException("AI 服务暂不可用，请稍后重试"));

        assertThatThrownBy(() -> service.chat(cid.toString(), "你好", List.of()))
                .isInstanceOf(com.iclothes.exception.AgentUnavailableException.class);
        verify(agentClient, times(1)).chat(anyString(), anyList(), anyList()); // 不重试
        verify(sessionLock).release(lockKey); // finally 释放锁
    }

    static final class ConversationDtoHelper {
        static void recordCreated(UUID cid) {}
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=ChatServiceTest`
Expected: 编译失败（类不存在）。

- [ ] **Step 3: 实现 ApiException、DTO 与两个 Service**

```java
// ApiException.java
package com.iclothes.exception;

public class ApiException extends RuntimeException {
    private final int status;
    public ApiException(int status, String detail) {
        super(detail);
        this.status = status;
    }
    public int getStatus() { return status; }
}
```

```java
// ChatRequest.java
package com.iclothes.dto;

import java.util.List;

public class ChatRequest {
    private String conversationId;
    private String message = "";
    private List<String> images = List.of();

    public String getConversationId() { return conversationId; }
    public void setConversationId(String v) { conversationId = v; }
    public String getMessage() { return message; }
    public void setMessage(String v) { message = v; }
    public List<String> getImages() { return images; }
    public void setImages(List<String> v) { images = v; }
}
```

```java
// ChatResponse.java
package com.iclothes.dto;

public class ChatResponse {
    private String conversationId;
    private String reply;
    private String intent;
    private String title;

    public ChatResponse() {}
    public ChatResponse(String conversationId, String reply, String intent, String title) {
        this.conversationId = conversationId; this.reply = reply;
        this.intent = intent; this.title = title;
    }
    public String getConversationId() { return conversationId; }
    public void setConversationId(String v) { conversationId = v; }
    public String getReply() { return reply; }
    public void setReply(String v) { reply = v; }
    public String getIntent() { return intent; }
    public void setIntent(String v) { intent = v; }
    public String getTitle() { return title; }
    public void setTitle(String v) { title = v; }
}
```

```java
// ConversationService.java
package com.iclothes.service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.iclothes.dto.ConversationDto;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.dto.MessageDto;
import com.iclothes.entity.Conversation;
import com.iclothes.entity.Message;
import com.iclothes.repository.ConversationMapper;
import com.iclothes.repository.MessageMapper;

@Service
public class ConversationService {

    static final int MAX_HISTORY = 50;

    private final ConversationMapper conversations;
    private final MessageMapper messages;

    public ConversationService(ConversationMapper conversations, MessageMapper messages) {
        this.conversations = conversations;
        this.messages = messages;
    }

    public ConversationDto create() {
        Conversation c = new Conversation(UUID.randomUUID(), "新对话",
                LocalDateTime.now(), LocalDateTime.now());
        conversations.insert(c);
        return toDto(c, List.of());
    }

    public List<ConversationSummaryDto> listSummaries() {
        return conversations.selectSummaries();
    }

    public ConversationDto get(UUID id) {
        Conversation c = conversations.selectById(id);
        if (c == null) return null;
        List<Message> ms = messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, id)
                .orderByAsc(Message::getId));
        return toDto(c, ms.stream().map(this::toMessageDto).toList());
    }

    public boolean delete(UUID id) {
        return conversations.deleteById(id) > 0;
    }

    public List<Message> lastMessages(UUID id, int limit) {
        return messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, id)
                .orderByAsc(Message::getId)
                .last("LIMIT " + limit));
    }

    public void appendUser(UUID id, String content, List<String> images) {
        Message m = new Message();
        m.setConversationId(id);
        m.setRole("user");
        m.setContent(content == null ? "" : content);
        m.setIntent("");
        m.setImages(images == null ? List.of() : images);
        m.setCreatedAt(LocalDateTime.now());
        messages.insert(m);
    }

    public void appendAssistant(UUID id, String content, String intent) {
        Message m = new Message();
        m.setConversationId(id);
        m.setRole("assistant");
        m.setContent(content);
        m.setIntent(intent == null ? "" : intent);
        m.setImages(List.of());
        m.setCreatedAt(LocalDateTime.now());
        messages.insert(m);
    }

    public void trim(UUID id) {
        long total = messages.selectCount(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, id));
        if (total > MAX_HISTORY) {
            long excess = total - MAX_HISTORY;
            messages.delete(new LambdaQueryWrapper<Message>()
                    .eq(Message::getConversationId, id)
                    .orderByAsc(Message::getId)
                    .last("LIMIT " + excess));
        }
    }

    public void setTitle(UUID id, String title) {
        Conversation c = conversations.selectById(id);
        if (c != null) {
            c.setTitle(title);
            c.setUpdatedAt(LocalDateTime.now());
            conversations.updateById(c);
        }
    }

    public String getTitle(UUID id) {
        Conversation c = conversations.selectById(id);
        return c == null ? "新对话" : c.getTitle();
    }

    MessageDto toMessageDto(Message m) {
        MessageDto d = new MessageDto();
        d.setRole(m.getRole());
        d.setContent(m.getContent());
        d.setIntent(m.getIntent());
        d.setImages(m.getImages());
        d.setCreatedAt(m.getCreatedAt());
        return d;
    }

    private ConversationDto toDto(Conversation c, List<MessageDto> msgs) {
        ConversationDto d = new ConversationDto();
        d.setId(c.getId().toString());
        d.setTitle(c.getTitle());
        d.setCreatedAt(c.getCreatedAt());
        d.setUpdatedAt(c.getUpdatedAt());
        d.setMessages(msgs);
        return d;
    }
}
```

`MessageDto.java` 与 `ConversationDto.java`（Task 3 的 `ConversationSummaryDto` 同目录，新增两个）：

```java
// MessageDto.java
package com.iclothes.dto;

import java.time.LocalDateTime;
import java.util.List;

public class MessageDto {
    private String role;
    private String content;
    private String intent;
    private List<String> images;
    private LocalDateTime createdAt;

    public String getRole() { return role; }
    public void setRole(String v) { role = v; }
    public String getContent() { return content; }
    public void setContent(String v) { content = v; }
    public String getIntent() { return intent; }
    public void setIntent(String v) { intent = v; }
    public List<String> getImages() { return images; }
    public void setImages(List<String> v) { images = v; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime v) { createdAt = v; }
}
```

```java
// ConversationDto.java
package com.iclothes.dto;

import java.time.LocalDateTime;
import java.util.List;

public class ConversationDto {
    private String id;
    private String title;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    private List<MessageDto> messages;

    public String getId() { return id; }
    public void setId(String v) { id = v; }
    public String getTitle() { return title; }
    public void setTitle(String v) { title = v; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime v) { createdAt = v; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime v) { updatedAt = v; }
    public List<MessageDto> getMessages() { return messages; }
    public void setMessages(List<MessageDto> v) { messages = v; }
}
```

```java
// ChatService.java
package com.iclothes.service;

import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.iclothes.agent.AgentChatRequest;
import com.iclothes.agent.AgentChatResponse;
import com.iclothes.agent.PythonAgentClient;
import com.iclothes.dto.ChatResponse;
import com.iclothes.entity.Message;
import com.iclothes.exception.ApiException;

@Service
public class ChatService {

    static final int HISTORY_LIMIT = 20;
    static final int TITLE_MAX = 20;
    static final long LOCK_WAIT_MS = 3000;
    static final String LOCK_PREFIX = "conversation:";
    static final String LOCK_SUFFIX = ":lock";

    private final ConversationService conversations;
    private final PythonAgentClient agentClient;
    private final SessionLock sessionLock;

    public ChatService(ConversationService conversations, PythonAgentClient agentClient,
                       SessionLock sessionLock) {
        this.conversations = conversations;
        this.agentClient = agentClient;
        this.sessionLock = sessionLock;
    }

    public ChatResponse chat(String conversationId, String message, List<String> images) {
        // 1. 会话解析：id 无效/不存在 → 新建
        UUID cid = parseOrNull(conversationId);
        boolean isNew = false;
        if (cid == null) {
            isNew = true;
            cid = UUID.randomUUID();
            conversations.create(); // 空会话落库
        } else if (conversations.get(cid) == null) {
            isNew = true;
            conversations.create();
        }

        String lockKey = LOCK_PREFIX + cid + LOCK_SUFFIX;

        // 4. Redis 会话写锁（等待 ≤3s，失败 503）；Redis 故障时内部降级
        boolean locked = sessionLock.tryAcquire(lockKey, LOCK_WAIT_MS);
        if (!locked) {
            throw new ApiException(503, "请求过于频繁，请稍后重试");
        }

        try {
            // 3. 取历史（最近 20 条）→ 5. 调 Python（不重试）
            List<Message> history = conversations.lastMessages(cid, HISTORY_LIMIT);
            List<AgentChatRequest.HistoryItem> historyItems = history.stream()
                    .map(m -> new AgentChatRequest.HistoryItem(m.getRole(), m.getContent()))
                    .toList();
            AgentChatResponse resp = agentClient.chat(message, images, historyItems);

            // 6. 落库 → 7. 裁剪 → 8. 自动标题
            conversations.appendUser(cid, message, images);
            conversations.appendAssistant(cid, resp.reply(), resp.intent());
            conversations.trim(cid);

            String title = conversations.getTitle(cid);
            if (isNew && message != null && !message.isBlank()) {
                String clean = message.trim().replace("\n", " ");
                title = clean.substring(0, Math.min(TITLE_MAX, clean.length()));
                conversations.setTitle(cid, title);
            }

            return new ChatResponse(cid.toString(), resp.reply(), resp.intent(), title);
        } finally {
            sessionLock.release(lockKey);
        }
    }

    private UUID parseOrNull(String id) {
        if (id == null || id.isBlank()) return null;
        try {
            return UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }
}
```

- [ ] **Step 4: 实现 ConversationService 测试**

```java
// ConversationServiceTest.java
package com.iclothes.service;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import com.iclothes.dto.ConversationDto;
import com.iclothes.repository.ConversationMapper;
import com.iclothes.repository.MessageMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ConversationServiceTest {

    @Mock ConversationMapper conversations;
    @Mock MessageMapper messages;

    @Test
    void getReturnsNullForMissing() {
        UUID id = UUID.randomUUID();
        when(conversations.selectById(id)).thenReturn(null);
        ConversationService service = new ConversationService(conversations, messages);
        assertThat(service.get(id)).isNull();
    }

    @Test
    void createProducesDto() {
        ConversationService service = new ConversationService(conversations, messages);
        ConversationDto dto = service.create();
        assertThat(dto.getId()).isNotNull();
        assertThat(dto.getTitle()).isEqualTo("新对话");
        assertThat(dto.getMessages()).isEmpty();
    }

    @Test
    void trimOnlyDeletesBeyondLimit() {
        // 裁剪逻辑在 RepositoryIT 中覆盖；此处验证不会误删（total <= 50 时不调用 delete）
        ConversationService service = new ConversationService(conversations, messages);
        UUID id = UUID.randomUUID();
        when(messages.selectCount(org.mockito.ArgumentMatchers.any()))
                .thenReturn(10L);
        service.trim(id);
        org.mockito.Mockito.verify(messages, org.mockito.Mockito.never())
                .delete(org.mockito.ArgumentMatchers.any());
    }
}
```

- [ ] **Step 5: 运行全部测试**

Run: `mvn -f iclothes-server/pom.xml test`
Expected: 全部通过（含既有用例）。

- [ ] **Step 6: Commit**

```bash
git add iclothes-server/
git commit -m "feat: conversation and chat orchestration with session lock"
```

---

### Task 7: Controller 层 + 统一异常（400/404/502/503/429）+ MockMvc 测试

**Files:**
- Create: `iclothes-server/src/main/java/com/iclothes/controller/ChatController.java`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/ConversationController.java`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/RecommendController.java`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/GlobalExceptionHandler.java`
- Test: `iclothes-server/src/test/java/com/iclothes/controller/ChatControllerTest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/controller/ConversationControllerTest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/controller/RecommendControllerTest.java`

**Interfaces:**
- Consumes: `ChatService.chat`、`ConversationService`（Task 6）、`RateLimiter.allow`（Task 4）、`AppProperties`（Task 2）
- Produces: 对外 7 端点（spec §3.1）；`GlobalExceptionHandler`：`ApiException` → status+detail、`AgentUnavailableException` → 502、`AgentValidationException` → 400（透传 detail）、`Exception` → 500

- [ ] **Step 1: 写失败测试**

```java
// ChatControllerTest.java
package com.iclothes.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.config.AppProperties;
import com.iclothes.dto.ChatResponse;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ChatController.class)
@Import(AppProperties.class)
class ChatControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean
    ChatService chatService;

    @MockitoBean
    RateLimiter rateLimiter;

    @Test
    void emptyMessageAndImagesRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"\",\"images\":[]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("消息内容不能为空"));
    }

    @Test
    void invalidImageFormatRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hi\",\"images\":[\"data:image/gif;base64,AAAA\"]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("不支持的图片格式，仅支持 JPG/PNG"));
    }

    @Test
    void tooManyImagesRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        String images = "["
                + "\"data:image/png;base64,AAAA\",\"data:image/png;base64,BBBB\","
                + "\"data:image/png;base64,CCCC\",\"data:image/png;base64,DDDD\"]";
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hi\",\"images\":" + images + "}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("最多上传 3 张照片"));
    }

    @Test
    void rateLimitedReturns429() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(false);
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"images\":[]}"))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.detail").value("请求过于频繁，请稍后重试"));
    }

    @Test
    void happyPathReturnsChatResponse() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        when(chatService.chat(any(), any(), anyList()))
                .thenReturn(new ChatResponse("abc", "回复", "chat", "新对话"));
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"images\":[]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reply").value("回复"))
                .andExpect(jsonPath("$.intent").value("chat"));
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=ChatControllerTest`
Expected: 编译失败（Controller/异常处理不存在）。

- [ ] **Step 3: 实现统一异常处理**

```java
// GlobalExceptionHandler.java
package com.iclothes.controller;

import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import com.iclothes.exception.AgentUnavailableException;
import com.iclothes.exception.AgentValidationException;
import com.iclothes.exception.ApiException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, String>> apiError(ApiException e) {
        return ResponseEntity.status(e.getStatus()).body(Map.of("detail", e.getMessage()));
    }

    @ExceptionHandler(AgentUnavailableException.class)
    public ResponseEntity<Map<String, String>> agentDown(AgentUnavailableException e) {
        return ResponseEntity.status(502).body(Map.of("detail", e.getMessage()));
    }

    @ExceptionHandler(AgentValidationException.class)
    public ResponseEntity<Map<String, String>> agentValidation(AgentValidationException e) {
        return ResponseEntity.status(400).body(Map.of("detail", e.getMessage()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> internal(Exception e) {
        log.error("unhandled error", e);
        return ResponseEntity.status(500).body(Map.of("detail", "服务器内部错误"));
    }
}
```

- [ ] **Step 4: 实现 ChatController（限流 + 校验，消息与 Python 旧版逐字一致）**

```java
// ChatController.java
package com.iclothes.controller;

import java.util.List;
import java.util.regex.Pattern;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import jakarta.servlet.http.HttpServletRequest;
import com.iclothes.config.AppProperties;
import com.iclothes.dto.ChatRequest;
import com.iclothes.dto.ChatResponse;
import com.iclothes.exception.ApiException;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

@RestController
public class ChatController {

    private static final Pattern DATA_URL = Pattern.compile("^data:image/(jpeg|png);base64,");

    private final ChatService chatService;
    private final RateLimiter rateLimiter;
    private final AppProperties properties;

    public ChatController(ChatService chatService, RateLimiter rateLimiter, AppProperties properties) {
        this.chatService = chatService;
        this.rateLimiter = rateLimiter;
        this.properties = properties;
    }

    @PostMapping("/api/chat")
    public ChatResponse chat(@RequestBody ChatRequest req, HttpServletRequest http) {
        if (!rateLimiter.allow(clientIp(http))) {
            throw new ApiException(429, "请求过于频繁，请稍后重试");
        }
        List<String> images = validateImages(req.getImages());
        String message = req.getMessage() == null ? "" : req.getMessage().trim();
        if (message.isEmpty() && images.isEmpty()) {
            throw new ApiException(400, "消息内容不能为空");
        }
        return chatService.chat(req.getConversationId(), message, images);
    }

    List<String> validateImages(List<String> images) {
        List<String> list = images == null ? List.of() : images;
        if (list.size() > properties.getUpload().getMaxCount()) {
            throw new ApiException(400,
                    "最多上传 " + properties.getUpload().getMaxCount() + " 张照片");
        }
        long maxBytes = properties.getUpload().getMaxSizeMb() * 1024L * 1024L;
        for (String url : list) {
            if (!DATA_URL.matcher(url).find()) {
                throw new ApiException(400, "不支持的图片格式，仅支持 JPG/PNG");
            }
            int payloadLen = url.length() - DATA_URL.matcher(url).end();
            long approxBytes = (long) (payloadLen * 3 / 4.0);
            if (approxBytes > maxBytes) {
                throw new ApiException(400,
                        "图片超过 " + properties.getUpload().getMaxSizeMb() + "MB 限制");
            }
        }
        return list;
    }

    private String clientIp(HttpServletRequest http) {
        String fwd = http.getHeader("X-Forwarded-For");
        if (fwd != null && !fwd.isBlank()) {
            return fwd.split(",")[0].trim();
        }
        return http.getRemoteAddr();
    }
}
```

- [ ] **Step 5: 实现 ConversationController 与 RecommendController**

```java
// ConversationController.java
package com.iclothes.controller;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.dto.ConversationDto;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.exception.ApiException;
import com.iclothes.service.ConversationService;

@RestController
public class ConversationController {

    private final ConversationService service;

    public ConversationController(ConversationService service) { this.service = service; }

    @PostMapping("/api/conversations")
    public ConversationDto create() {
        return service.create();
    }

    @GetMapping("/api/conversations")
    public List<ConversationSummaryDto> list() {
        return service.listSummaries();
    }

    @GetMapping("/api/conversations/{id}")
    public ConversationDto get(@PathVariable String id) {
        ConversationDto dto = service.get(parseUuid(id));
        if (dto == null) throw new ApiException(404, "会话不存在");
        return dto;
    }

    @DeleteMapping("/api/conversations/{id}")
    public Map<String, Boolean> delete(@PathVariable String id) {
        if (!service.delete(parseUuid(id))) throw new ApiException(404, "会话不存在");
        return Map.of("ok", true);
    }

    private UUID parseUuid(String id) {
        try {
            return UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            throw new ApiException(404, "会话不存在");
        }
    }
}
```

```java
// RecommendController.java
package com.iclothes.controller;

import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import jakarta.servlet.http.HttpServletRequest;
import com.iclothes.config.AppProperties;
import com.iclothes.exception.ApiException;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

@RestController
public class RecommendController {

    private final ChatService chatService;
    private final RateLimiter rateLimiter;
    private final AppProperties properties;

    public RecommendController(ChatService chatService, RateLimiter rateLimiter, AppProperties properties) {
        this.chatService = chatService;
        this.rateLimiter = rateLimiter;
        this.properties = properties;
    }

    @PostMapping("/api/recommend")
    public Map<String, String> recommend(
            @RequestParam("images") List<MultipartFile> images,
            @RequestParam(value = "description", defaultValue = "") String description,
            HttpServletRequest http) {
        if (!rateLimiter.allow(http.getRemoteAddr())) {
            throw new ApiException(429, "请求过于频繁，请稍后重试");
        }
        if (images == null || images.isEmpty()) {
            throw new ApiException(400, "请至少上传一张照片");
        }
        if (images.size() > properties.getUpload().getMaxCount()) {
            throw new ApiException(400,
                    "最多上传 " + properties.getUpload().getMaxCount() + " 张照片");
        }
        long maxBytes = properties.getUpload().getMaxSizeMb() * 1024L * 1024L;
        List<String> urls = new ArrayList<>();
        for (MultipartFile f : images) {
            if (f.getContentType() == null
                    || !(f.getContentType().equals("image/jpeg") || f.getContentType().equals("image/png"))) {
                throw new ApiException(400,
                        "不支持的图片格式：" + f.getContentType() + "，仅支持 JPG/PNG");
            }
            if (f.getSize() > maxBytes) {
                throw new ApiException(400,
                        "图片 " + f.getOriginalFilename() + " 超过 "
                                + properties.getUpload().getMaxSizeMb() + "MB 限制");
            }
            try {
                urls.add("data:" + f.getContentType() + ";base64,"
                        + Base64.getEncoder().encodeToString(f.getBytes()));
            } catch (java.io.IOException e) {
                throw new ApiException(400, "读取图片失败：" + f.getOriginalFilename());
            }
        }
        var resp = chatService.chat(null, description, urls);
        return Map.of("suggestion", resp.getReply());
    }
}
```

- [ ] **Step 6: 写 ConversationControllerTest 与 RecommendControllerTest**

```java
// ConversationControllerTest.java
package com.iclothes.controller;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.dto.ConversationDto;
import com.iclothes.service.ConversationService;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ConversationController.class)
class ConversationControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean
    ConversationService service;

    @Test
    void missingConversationReturns404() throws Exception {
        mvc.perform(get("/api/conversations/00000000-0000-0000-0000-000000000001"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value("会话不存在"));
    }

    @Test
    void deleteMissingReturns404() throws Exception {
        mvc.perform(delete("/api/conversations/00000000-0000-0000-0000-000000000001"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value("会话不存在"));
    }

    @Test
    void createReturnsDto() throws Exception {
        ConversationDto dto = new ConversationDto();
        dto.setId(UUID.randomUUID().toString());
        dto.setTitle("新对话");
        dto.setMessages(List.of());
        when(service.create()).thenReturn(dto);
        mvc.perform(post("/api/conversations"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("新对话"));
    }
}
```

```java
// RecommendControllerTest.java
package com.iclothes.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.config.AppProperties;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RecommendController.class)
@Import(AppProperties.class)
class RecommendControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean ChatService chatService;
    @MockitoBean RateLimiter rateLimiter;

    @Test
    void noImagesRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        mvc.perform(multipart("/api/recommend"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("请至少上传一张照片"));
    }

    @Test
    void wrongContentTypeRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        MockMultipartFile file = new MockMultipartFile("images", "a.txt", "text/plain", new byte[]{1});
        mvc.perform(multipart("/api/recommend").file(file))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("不支持的图片格式：text/plain，仅支持 JPG/PNG"));
    }

    @Test
    void happyPath() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        when(chatService.chat(any(), any(), anyList()))
                .thenReturn(new com.iclothes.dto.ChatResponse("c", "建议", "recommend", "t"));
        MockMultipartFile file = new MockMultipartFile("images", "a.png", "image/png", new byte[]{1, 2, 3});
        mvc.perform(multipart("/api/recommend").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.suggestion").value("建议"));
    }
}
```

- [ ] **Step 7: 运行全部测试**

Run: `mvn -f iclothes-server/pom.xml test`
Expected: 全部通过。

- [ ] **Step 8: Commit**

```bash
git add iclothes-server/
git commit -m "feat: controllers with unified error handling and rate limiting"
```

---

### Task 8: 前端联通 + 静态伺服（验证型）

**Files:**
- Modify: `frontend/vite.config.js`（代理目标 8000 → 8080）
- Create: `iclothes-server/src/main/java/com/iclothes/controller/StaticController.java`
- Create: `iclothes-server/src/main/java/com/iclothes/config/WebConfig.java`
- Test: `iclothes-server/src/test/java/com/iclothes/config/StaticServeTest.java`

**Interfaces:**
- Consumes: `AppProperties.getFrontend().getDir()`（Task 2）
- Produces: `GET /` → `frontend/dist/index.html`；`GET /assets/**` → dist 资源

- [ ] **Step 1: 构建前端 + 写失败测试（需真实 dist 存在）**

```powershell
cd D:\code\i-clothes\frontend
npm.cmd run build   # 产出 dist/index.html 与 dist/assets/index-*.{js,css}
```

```java
// StaticServeTest.java
package com.iclothes.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "iclothes.frontend.dir=../frontend/dist")
@ActiveProfiles("test")
@AutoConfigureMockMvc
class StaticServeTest {
    @Autowired MockMvc mvc;

    @Test
    void servesIndexHtmlReferencingAssets() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("/assets/")));
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=StaticServeTest`
Expected: 失败（`/` 404，StaticController 不存在）。

- [ ] **Step 3: 实现静态伺服**

```java
// StaticController.java
package com.iclothes.controller;

import java.io.File;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.config.AppProperties;

@RestController
public class StaticController {

    private final AppProperties properties;

    public StaticController(AppProperties properties) { this.properties = properties; }

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    public Resource index() {
        return new FileSystemResource(new File(properties.getFrontend().getDir(), "index.html"));
    }
}
```

```java
// WebConfig.java
package com.iclothes.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final AppProperties properties;

    public WebConfig(AppProperties properties) { this.properties = properties; }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("file:" + properties.getFrontend().getDir() + "/assets/");
    }
}
```

- [ ] **Step 4: 修改 vite 代理并验证**

`frontend/vite.config.js` 中：

```js
proxy: {
  '/api': 'http://127.0.0.1:8080',
},
```

Run:
```powershell
mvn -f iclothes-server/pom.xml test -Dtest=StaticServeTest
mvn -f iclothes-server/pom.xml package -DskipTests
# 从仓库根启动（frontend.dir 默认 frontend/dist）
Start-Process -FilePath java -ArgumentList '-jar','iclothes-server/target/iclothes-server-0.1.0.jar' -WorkingDirectory 'D:\code\i-clothes'
Start-Sleep -Seconds 15
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/api/health
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8080/assets/index-*.js
```
Expected: 三个均 200；测试通过。

- [ ] **Step 5: Commit**

```bash
git add iclothes-server/ frontend/vite.config.js
git commit -m "feat: serve frontend dist and wire dev proxy to 8080"
```

---

### Task 9: 端到端验收 + Docker compose 交付物（四件套）

**Files:**
- Create: `iclothes-server/Dockerfile`
- Create: `app/Dockerfile`
- Create: `docker-compose.yml`（项目根）
- 无新增 Java/Python 源码（本任务发现的问题修复除外）

**Interfaces:** 无（验收任务；失败修复需回归对应 Task 的测试）

- [ ] **Step 1: 启动全栈（PG + Redis + Python + Java）**

```powershell
# 前置：PG 服务已启动、Redis 6379 已监听、iclothes 库已建
cd D:\code\i-clothes
$env:PGPASSWORD = 'iclothes123'
# Python Agent 服务（真实 key 从 .env 读取）
$env:QIANWEN_API_KEY = (Select-String -Path .env -Pattern '^QIANWEN_API_KEY=(.*)$').Matches.Groups[1].Value
$env:DEEPSEEK_API_KEY = (Select-String -Path .env -Pattern '^DEEPSEEK_API_KEY=(.*)$').Matches.Groups[1].Value
Start-Process -FilePath 'D:\code\i-clothes\.conda\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'D:\code\i-clothes' -WindowStyle Hidden
Start-Sleep -Seconds 10
curl.exe -s http://127.0.0.1:8000/api/health
# Java 业务后端
Start-Process -FilePath java -ArgumentList '-jar','iclothes-server/target/iclothes-server-0.1.0.jar' -WorkingDirectory 'D:\code\i-clothes' -WindowStyle Hidden
Start-Sleep -Seconds 15
curl.exe -s http://127.0.0.1:8080/api/health
```
Expected: Python health `{"status":"ok","qianwen_configured":true}`；Java health 代理后同样 `true`。

- [ ] **Step 2: 行为清单逐项验证（spec §3.2，JSON body 走 UTF-8 文件）**

```powershell
$utf8 = New-Object System.Text.UTF8Encoding($false)
$tmp = Join-Path $env:TEMP 'e2e'; New-Item -ItemType Directory -Force -Path $tmp | Out-Null
# a) 新建会话
$cid = (curl.exe -s -X POST http://127.0.0.1:8080/api/conversations | ConvertFrom-Json).id
# b) 闲聊（真实调用 DeepSeek）→ intent=chat
$b = @{ conversation_id = $cid; message = '你好，介绍一下你自己，尽量简短'; images = @() } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText("$tmp\b.json", $b, $utf8)
curl.exe -s -X POST http://127.0.0.1:8080/api/chat -H "Content-Type: application/json" --data-binary "@$tmp\b.json"
# c) 文字推荐（无图）→ intent=recommend，回复以「没有照片的情况下…」开头
$c = @{ conversation_id = $cid; message = '帮我推荐一套上班通勤的穿搭，简洁一点'; images = @() } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText("$tmp\c.json", $c, $utf8)
curl.exe -s -X POST http://127.0.0.1:8080/api/chat -H "Content-Type: application/json" --data-binary "@$tmp\c.json"
# d) 校验：空消息 → 400；坏图片 → 400；4 张图 → 400
# e) 会话详情：messages=4（2 user + 2 assistant），assistant 消息带 intent
curl.exe -s "http://127.0.0.1:8080/api/conversations/$cid"
# f) 自动标题 = 首条用户消息前 20 字符
# g) 删除会话 → {ok:true}；GET 不存在 → 404 会话不存在
# h) 并发验证：同一会话双开各发一条（PowerShell 两个后台任务）→ 消息不丢不乱（总数=6）
# i) 重启 Java 后 GET 会话列表仍有数据（PG 持久化）
```
Expected: 与 spec §3.2 逐项一致；并发后消息总数为 6 且两轮回复都在。

- [ ] **Step 3: 编写 Docker 交付物（本机无 Docker，仅交付 + 语法校验）**

`iclothes-server/Dockerfile`（构建上下文为仓库根）：

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY iclothes-server/target/iclothes-server-0.1.0.jar app.jar
COPY frontend/dist ./dist
ENV FRONTEND_DIST=dist
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

`app/Dockerfile`（Python Agent 服务）：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.yml`（项目根，四件套）：

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: iclothes
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-iclothes123}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-postgres}"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  iclothes-python:
    build: .
    dockerfile: app/Dockerfile
    environment:
      QIANWEN_API_KEY: ${QIANWEN_API_KEY}
      QIANWEN_BASE_URL: ${QIANWEN_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}
      QIANWEN_MODEL: ${QIANWEN_MODEL:-qwen3.7-max-2026-06-08}
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
      DEEPSEEK_BASE_URL: ${DEEPSEEK_BASE_URL:-https://api.deepseek.com}
      DEEPSEEK_MODEL: ${DEEPSEEK_MODEL:-deepseek-v4-flash}
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')\""]
      interval: 10s
      timeout: 5s
      retries: 10

  iclothes-server:
    build:
      context: .
      dockerfile: iclothes-server/Dockerfile
    environment:
      DB_URL: jdbc:postgresql://postgres:5432/iclothes
      DB_USER: ${DB_USER:-postgres}
      DB_PASSWORD: ${DB_PASSWORD:-iclothes123}
      REDIS_HOST: redis
      AGENT_BASE_URL: http://iclothes-python:8000
      FRONTEND_DIST: dist
      QIANWEN_API_KEY: ${QIANWEN_API_KEY}
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      iclothes-python:
        condition: service_healthy

volumes:
  pgdata:
```

校验（Docker 可用时）：`docker compose config`；不可用时人工核对 YAML 缩进与变量引用。

- [ ] **Step 4: Commit**

```bash
git add iclothes-server/Dockerfile app/Dockerfile docker-compose.yml
git commit -m "chore: docker compose deliverable (pg+redis+python+java)"
```

---

### Task 10: 清理与文档

**Files:**
- Modify: `常用指令`、`CHANGELOG.md`、`README.md`

**Interfaces:** 无

- [ ] **Step 1: 更新 `常用指令`**

替换为（双服务 + 中间件启动）：

```
停掉后台phoenix
Get-NetTCPConnection -LocalPort 6006,4317 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

停掉后台app（python agent / java / vite）
Get-NetTCPConnection -LocalPort 8000,8080,5173 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

启动 Python Agent 服务（:8000）
cd D:\code\i-clothes
D:\code\i-clothes\.conda\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

启动 Java 业务后端（:8080，需 PG + Redis 已运行）
cd D:\code\i-clothes
java -jar iclothes-server\target\iclothes-server-0.1.0.jar

前端开发模式（Vite，代理 /api 到 8080）
cd D:\code\i-clothes\frontend
npm.cmd run dev
```

- [ ] **Step 2: 更新 CHANGELOG.md**

按现有格式在 [Unreleased] 追加：

```
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
```

- [ ] **Step 3: 更新 README.md 为双服务简介（一句架构说明 + 启动指引链接 常用指令）**

- [ ] **Step 4: 验收复核（spec §9.3）**

```powershell
# 全新环境模拟：停掉全部服务 → 重启 PG/Redis → 起 Python + Java → 浏览器走全流程
# 并发双开同一会话发消息 → 消息不丢不乱
```
Expected: 四条验收标准全部满足（compose 项按 Global Constraints 降级为本地进程等价验证）。

- [ ] **Step 5: Commit**

```bash
git add 常用指令 CHANGELOG.md README.md
git commit -m "docs: update run instructions and changelog for dual-service architecture"
```

---

## Self-Review 记录

**1. Spec 覆盖核查：**
- §2 架构（数据归 Java / 推理归 Python / 状态收口）→ Task 6 ChatService 编排 + Task 5 无状态契约 ✓
- §3.1 对外 7 端点 → Task 2（health）+ Task 7（chat/conversations/recommend）+ Task 8（static 非 API）✓
- §3.2 行为清单：图片校验/空消息 → Task 7；意图规则（Python）→ Task 1 保留 graph；无照片开头 → Task 1（graph 不变）；chat 10/recommend 6 → Task 1（graph 消费 history）；自动标题 20 → Task 6；裁剪 50 → Task 6 ✓
- §4.1 对内契约 → Task 1（Python 侧）+ Task 5（Java 侧 MockRestServiceServer 契约测试）✓
- §4.2 改造点：删 conversation_store/chat_service/会话路由 → Task 1 Step 4 ✓；`/api/agent/chat` 无状态 → Task 1 Step 3 ✓；保留 graph/model_repo/Phoenix → Task 1 明确不删 ✓
- §5.2 编排 9 步 → Task 6 ChatService 注释逐行对应 ✓
- §5.3 并发与 Redis：锁 NX EX 5 / 等待 3s / 503 → Task 4 + Task 6；限流 60/min/429 → Task 4 + Task 7；虚拟线程 → Task 2 yml；RestClient 超时 3s/60s → Task 2 RestClientConfig；Redis 故障降级 → Task 4 测试用例；不重试 → Task 6 verify(times(1)) ✓
- §6 数据模型 → Task 3 V1__init.sql 逐字一致 ✓
- §7 health 代理（2s 超时、不可达 200+false）→ Task 2 ✓
- §8 失败模式：Python 不可达 502 → Task 5/7；Redis 不可用降级 → Task 4；锁竞争 503 → Task 6；LLM 失败透传不重试 → Task 5/6；会话不存在 404/自动新建 → Task 6/7；图片超限 400 → Task 7 ✓
- §9 测试验收：Python 契约测试 → Task 1；Java 单测 → Task 2-8；集成 → Task 3 + Task 9；验收标准 → Task 9 Step 2 + Task 10 Step 4 ✓
- §10 迁移 11 步 → Task 0-10 一一对应 ✓
- §11 假设（同仓库/端口/删除范围）→ Global Constraints ✓

**2. 占位符扫描：** 全部代码步骤含完整可编译代码；无 TBD/TODO/"类似 Task N"/"写适当校验"。Task 9 Step 2 的 e/g/h/i 子项以注释形式列出操作目标并在 Expected 给出判定标准，属于验收清单而非代码占位。

**3. 类型一致性：**
- `AppProperties`（Task 2）的 `getUpload/getAgent/getRateLimit/getFrontend` 被 Task 4（RateLimiter）、Task 5（agent baseUrl）、Task 7（上传限制）、Task 8（frontend.dir）引用，字段名一致
- `SessionLock.tryAcquire(String, long)`/`release(String)`（Task 4）在 Task 6 ChatService 中以 `LOCK_WAIT_MS=3000`、锁键 `conversation:{id}:lock` 调用，与 Global Constraints 一致
- `AgentChatRequest.HistoryItem(role, content)`（Task 5）在 Task 6 从 `Message.getRole()/getContent()` 构造，字段名一致
- `ChatResponse`（Task 6 定义）在 Task 7 Controller 中构造/返回，getter 名一致；`ChatRequest` 同
- `ApiException(int, String)`（Task 6）被 Task 7 抛 400/404/429/503、被 GlobalExceptionHandler 处理，构造签名一致
- `PythonAgentClient.chat(String, List<String>, List<HistoryItem>)`（Task 5）在 Task 6 调用，签名一致；health 方法 Task 2 定义、Task 2 测试引用
- Python 侧 `run_chat(message, images, history)` 为现有 `workflow.py` 既有函数，Task 1 直接复用未改签名

**4. 写作中内联修正（相对初稿）：**
- 限流超限状态码定为 **429**（spec §7 列了 400/404/502/503，未含限流码；HTTP 语义 429 更准确，已在 Global Constraints 补充为错误集之一）
- `ChatServiceTest.newConversationGetsCreatedAndTitled` 中 `conversations.create()` 返回 `ConversationDto`，无法直接断言其内部 id；改用 `setTitle` 调用断言标题落库路径（测试与实现同步调整，避免对 mock 返回值的空断言）
- `ConversationService.trim` 补充"total ≤ 50 时不调用 delete"的防误删用例
- Python 侧确认 `httpx`（TestClient 依赖）由 `langchain-openai` 传递提供，计划中注明缺失时的补救命令
- Redis 方案 A（Memurai）与方案 B（tporadowski zip）均已实测验证（winget id 存在、gh-proxy 下载 URL 200），写为可执行命令

---

## Execution Handoff

**"Plan complete and saved to `docs/superpowers/plans/2026-08-17-springboot-migration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?"**
