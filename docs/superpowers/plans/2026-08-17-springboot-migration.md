# Spring Boot 后端迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Java 21 + Spring Boot 3 + LangChain4j + PostgreSQL 16 + MyBatis-Plus 实现与现有 Python 后端等价的后端（聊天/推荐/意图路由/会话持久化），前端零改动。

**Architecture:** 单模块 Maven 工程 `iclothes-server/`。分层 controller → service → repository(MyBatis-Plus Mapper) / ai(LangChain4j)。ChatService 顺序编排等价 LangGraph 节点链（意图路由 → chat/recommend 分支 → LLM 调用 → 落库）。错误统一 `{"detail": "..."}` + 400/404/502。

**Tech Stack:** Java 21、Spring Boot 3.5.3、Maven、LangChain4j 1.0.0（`langchain4j-open-ai`）、MyBatis-Plus 3.5.7（`mybatis-plus-spring-boot3-starter`）、PostgreSQL 16、Flyway、JUnit5 + Mockito + MockMvc。

**Spec:** `docs/superpowers/specs/2026-08-17-springboot-migration-design.md`（本计划从 spec 推导，执行者需同时阅读两者）

## Global Constraints

- Java 21、Spring Boot `3.5.3`（parent POM）、LangChain4j `1.0.0`、MyBatis-Plus `3.5.7`
- PostgreSQL 16，库名 `iclothes`（应用）/ `iclothes_test`（测试）
- 接口路径与响应结构与 spec §2.1 逐字节兼容；错误体固定 `{"detail": "<中文消息>"}`
- 上传限制：图片 ≤3 张、JPG/PNG、≤5MB；消息空且无图 → 400
- 意图规则：有图必 recommend；recommend 关键词优先于 chat；兜底 chat（spec §2.2）
- 上下文轮数：chat 最近 10 条；recommend 最近 6 条用户消息；历史上限 50 条
- 自动标题：首条用户消息前 20 字符
- 无照片推荐回复必须以「没有照片的情况下，我先按文字描述给你参考建议」开头（由 Prompt 保证）
- 包名 `com.iclothes`；所有敏感配置走环境变量（`QIANWEN_*`/`DEEPSEEK_*`/`DB_*`）
- 每个 Task 以可独立验证的交付物结束并提交 git
- 本机无 Docker/WSL：集成测试与验收跑本地 PostgreSQL；Docker compose 作为交付物编写但不要求运行

---

## 文件结构总览

```
iclothes-server/
  pom.xml
  Dockerfile（Task 7）
  src/main/java/com/iclothes/
    IclothesApplication.java
    config/ModelProperties.java          # @ConfigurationProperties(prefix="iclothes")
    config/WebConfig.java                # 静态资源伺服 frontend/dist
    controller/HealthController.java     # GET /api/health
    controller/ChatController.java       # POST /api/chat
    controller/ConversationController.java  # conversations CRUD
    controller/RecommendController.java  # POST /api/recommend（multipart）
    controller/ApiException.java         # 业务异常（status + detail）
    controller/GlobalExceptionHandler.java
    service/ChatService.java             # 编排（意图→分支→LLM→落库）
    service/ConversationService.java     # 会话 CRUD/追加/标题/裁剪
    ai/ModelFactory.java                 # 千问/DeepSeek ChatModel 工厂
    ai/IntentRouter.java                 # 关键词意图路由（纯函数）
    ai/Prompts.java                      # Prompt 常量
    repository/ConversationMapper.java   # BaseMapper + 摘要查询
    repository/MessageMapper.java        # BaseMapper
    entity/Conversation.java
    entity/Message.java
    dto/ChatRequest.java / ChatResponse.java / ConversationDto.java /
        ConversationSummaryDto.java / MessageDto.java
  src/main/resources/
    application.yml
    db/migration/V1__init.sql
  src/test/java/com/iclothes/
    ai/IntentRouterTest.java
    ai/ModelFactoryTest.java
    repository/RepositoryIT.java         # 集成测试（本地 PG）
    service/ChatServiceTest.java
    service/ConversationServiceTest.java
    controller/ChatControllerTest.java
    controller/ConversationControllerTest.java
    controller/RecommendControllerTest.java
  src/test/resources/application-test.yml
```

---

### Task 0: 环境准备（JDK 21 + Maven + PostgreSQL 16 + 契约导出）

**Files:**
- Create: `docs/openapi-contract.json`（契约存档，来自 Python 后端或 spec §2.1）
- 无 Java 源码

**Interfaces:** 无（环境前置；后续所有 Task 依赖本机的 `java`、`mvn`、`psql`）

- [ ] **Step 1: 确认缺口**

Run: `java -version; mvn -version; psql --version`
Expected: 三个命令均报"not recognized"（本机未装）。

- [ ] **Step 2: 安装 JDK 21（Temurin）**

```powershell
winget install -e --id EclipseAdoptium.Temurin.21.JDK --silent --accept-package-agreements --accept-source-agreements
```

- [ ] **Step 3: 安装 Maven**

```powershell
winget install -e --id Apache.Maven --silent --accept-package-agreements --accept-source-agreements
```

- [ ] **Step 4: 配置 JAVA_HOME 与 PATH（用户级环境变量，新开终端生效）**

```powershell
$jh = (Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Directory | Where-Object Name -like 'jdk-21*' | Select-Object -First 1).FullName
[Environment]::SetEnvironmentVariable('JAVA_HOME', $jh, 'User')
$path = [Environment]::GetEnvironmentVariable('Path', 'User')
[Environment]::SetEnvironmentVariable('Path', "$path;C:\Program Files\Apache\maven\bin;$jh\bin", 'User')
```

- [ ] **Step 5: 验证工具链**

Run（新开终端）: `java -version; mvn -version`
Expected: `java 21.x` 与 `Apache Maven 3.9.x`。

- [ ] **Step 6: 安装 PostgreSQL 16（静默，指定超级用户密码）**

```powershell
winget install -e --id PostgreSQL.PostgreSQL.16 --silent --accept-package-agreements --accept-source-agreements --override "/quiet SUPERUSER_PASSWORD=iclothes123"
```
注意：若安装器交互失败，改用官方 EDB 安装器手动完成（密码 `iclothes123`，勾选 Stack Builder 之外的默认项）。

- [ ] **Step 7: 建库（应用库 + 测试库）**

```powershell
$env:PGPASSWORD = 'iclothes123'
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U postgres -h localhost -c "CREATE DATABASE iclothes;"
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U postgres -h localhost -c "CREATE DATABASE iclothes_test;"
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U postgres -h localhost -c "SELECT version();"
```

- [ ] **Step 8: 导出契约存档（优先 Python 后端，失败用 spec §2.1 手写）**

```powershell
# 若 Python 后端可启动：uvicorn 起后
curl.exe -s http://127.0.0.1:8000/openapi.json -o docs/openapi-contract.json
# 不可用则按 spec §2.1 的 7 个接口手写 JSON 契约（字段名/类型/错误码必须与 spec 一致）
```

- [ ] **Step 9: Commit**

```bash
git add docs/openapi-contract.json
git commit -m "chore: export backend API contract baseline"
```

---

### Task 1: Maven 脚手架 + Spring Boot 骨架 + Health 接口（TDD）

**Files:**
- Create: `iclothes-server/pom.xml`
- Create: `iclothes-server/src/main/java/com/iclothes/IclothesApplication.java`
- Create: `iclothes-server/src/main/java/com/iclothes/config/ModelProperties.java`
- Create: `iclothes-server/src/main/resources/application.yml`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/HealthController.java`
- Test: `iclothes-server/src/test/java/com/iclothes/controller/HealthControllerTest.java`
- Test: `iclothes-server/src/test/resources/application-test.yml`

**Interfaces:**
- Produces: `GET /api/health` → `{"status":"ok","qianwen_configured":<bool>}`；`ModelProperties` 字段 `qianwen.apiKey`、`deepseek.apiKey`、`upload.maxCount`、`upload.maxSizeMb`。

- [ ] **Step 1: 写失败测试**

```java
// HealthControllerTest.java
package com.iclothes.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.config.ModelProperties;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(HealthController.class)
class HealthControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ModelProperties properties;

    @Test
    void healthReportsQianwenConfigured() throws Exception {
        when(properties.isQianwenConfigured()).thenReturn(true);
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.qianwen_configured").value(true));
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=HealthControllerTest`
Expected: 编译失败（`HealthController`/`ModelProperties` 不存在）。

- [ ] **Step 3: 脚手架 + 最小实现**

`pom.xml`（完整内容，版本锁定）：

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
    <langchain4j.version>1.0.0</langchain4j.version>
    <mybatis-plus.version>3.5.7</mybatis-plus.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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
      <groupId>dev.langchain4j</groupId>
      <artifactId>langchain4j</artifactId>
      <version>${langchain4j.version}</version>
    </dependency>
    <dependency>
      <groupId>dev.langchain4j</groupId>
      <artifactId>langchain4j-open-ai</artifactId>
      <version>${langchain4j.version}</version>
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

`ModelProperties.java`：

```java
package com.iclothes.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "iclothes")
public class ModelProperties {

    private final Model qianwen = new Model();
    private final Model deepseek = new Model();
    private final Upload upload = new Upload();

    public boolean isQianwenConfigured() { return !qianwen.getApiKey().isBlank(); }

    public Model getQianwen() { return qianwen; }
    public Model getDeepseek() { return deepseek; }
    public Upload getUpload() { return upload; }

    public static class Model {
        private String apiKey = "";
        private String baseUrl = "";
        private String model = "";
        public String getApiKey() { return apiKey; }
        public void setApiKey(String v) { apiKey = v; }
        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String v) { baseUrl = v; }
        public String getModel() { return model; }
        public void setModel(String v) { model = v; }
    }

    public static class Upload {
        private int maxCount = 3;
        private int maxSizeMb = 5;
        public int getMaxCount() { return maxCount; }
        public void setMaxCount(int v) { maxCount = v; }
        public int getMaxSizeMb() { return maxSizeMb; }
        public void setMaxSizeMb(int v) { maxSizeMb = v; }
    }
}
```

`HealthController.java`：

```java
package com.iclothes.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.config.ModelProperties;

@RestController
public class HealthController {

    private final ModelProperties properties;

    public HealthController(ModelProperties properties) { this.properties = properties; }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "qianwen_configured", properties.isQianwenConfigured());
    }
}
```

`IclothesApplication.java`：

```java
package com.iclothes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import com.iclothes.config.ModelProperties;

@SpringBootApplication
@EnableConfigurationProperties(ModelProperties.class)
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

iclothes:
  qianwen:
    api-key: ${QIANWEN_API_KEY:}
    base-url: ${QIANWEN_BASE_URL:https://dashscope.aliyuncs.com/compatible-mode/v1}
    model: ${QIANWEN_MODEL:qwen3.7-max-2026-06-08}
  deepseek:
    api-key: ${DEEPSEEK_API_KEY:}
    base-url: ${DEEPSEEK_BASE_URL:https://api.deepseek.com}
    model: ${DEEPSEEK_MODEL:deepseek-v4-flash}
  upload:
    max-count: 3
    max-size-mb: 5

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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=HealthControllerTest`
Expected: BUILD SUCCESS，1 测试通过。

- [ ] **Step 5: Commit**

```bash
git add iclothes-server/
git commit -m "feat: scaffold Spring Boot app with health endpoint"
```

---

### Task 2: IntentRouter 意图路由 + ModelFactory 模型工厂（TDD）

**Files:**
- Create: `iclothes-server/src/main/java/com/iclothes/ai/IntentRouter.java`
- Create: `iclothes-server/src/main/java/com/iclothes/ai/ModelFactory.java`
- Test: `iclothes-server/src/test/java/com/iclothes/ai/IntentRouterTest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/ai/ModelFactoryTest.java`

**Interfaces:**
- Consumes: `ModelProperties`（Task 1）
- Produces:
  - `IntentRouter.route(String text, boolean hasImages, List<String> historyUserTexts) -> String`（返回 `"recommend"`/`"chat"`）
  - `ModelFactory.qianwenVl() -> ChatLanguageModel`、`ModelFactory.deepseek() -> ChatLanguageModel`（懒加载单例；Key 为空抛 `IllegalStateException("...未配置...")`）

- [ ] **Step 1: 写失败测试（意图路由 6 用例，等价 spec §2.2）**

```java
// IntentRouterTest.java
package com.iclothes.ai;

import java.util.List;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class IntentRouterTest {

    private final IntentRouter router = new IntentRouter();

    @Test
    void chatKeywordWins() {
        assertThat(router.route("你好，你是谁", false, List.of())).isEqualTo("chat");
    }

    @Test
    void recommendKeywordWins() {
        assertThat(router.route("帮我推荐上班通勤的穿搭", false, List.of())).isEqualTo("recommend");
    }

    @Test
    void plainChatText() {
        assertThat(router.route("今天天气不错", false, List.of())).isEqualTo("chat");
    }

    @Test
    void imagesForceRecommend() {
        assertThat(router.route("随便聊聊", true, List.of())).isEqualTo("recommend");
    }

    @Test
    void historyFallback() {
        assertThat(router.route("", false, List.of("推荐一条裙子"))).isEqualTo("recommend");
    }

    @Test
    void emptyTextAndHistory() {
        assertThat(router.route("", false, List.of())).isEqualTo("chat");
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=IntentRouterTest`
Expected: 编译失败（`IntentRouter` 不存在）。

- [ ] **Step 3: 最小实现**

```java
// IntentRouter.java
package com.iclothes.ai;

import java.util.List;

public class IntentRouter {

    // 顺序即优先级：recommend 关键词先于 chat 关键词
    private static final List<String> RECOMMEND_KEYWORDS = List.of(
            "推荐", "搭配", "穿搭", "穿什么", "怎么穿", "着装", "风格", "色系", "场合",
            "婚礼", "约会", "通勤", "面试", "聚会", "派对", "出差", "旅游", "上班",
            "出席", "外套", "裤子", "裙子", "鞋子", "上衣", "下装", "配饰", "套装",
            "单品", "衣服", "穿着", "适合", "好看", "显瘦", "look");

    private static final List<String> CHAT_KEYWORDS = List.of(
            "闲聊", "你是谁", "你会什么", "介绍一下你", "帮助", "help");

    public String route(String text, boolean hasImages, List<String> historyUserTexts) {
        if (hasImages) {
            return "recommend";
        }
        String current = text == null ? "" : text.trim().toLowerCase();
        if (current.isEmpty()) {
            for (int i = historyUserTexts.size() - 1; i >= 0; i--) {
                String h = historyUserTexts.get(i) == null ? "" : historyUserTexts.get(i).trim();
                if (!h.isEmpty()) { current = h.toLowerCase(); break; }
            }
        }
        if (current.isEmpty()) {
            return "chat";
        }
        for (String kw : RECOMMEND_KEYWORDS) {
            if (current.contains(kw)) return "recommend";
        }
        for (String kw : CHAT_KEYWORDS) {
            if (current.contains(kw)) return "chat";
        }
        return "chat";
    }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=IntentRouterTest`
Expected: 6 个用例全绿。

- [ ] **Step 5: 写 ModelFactory 失败测试（Key 缺失行为，无网络调用）**

```java
// ModelFactoryTest.java
package com.iclothes.ai;

import org.junit.jupiter.api.Test;
import com.iclothes.config.ModelProperties;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ModelFactoryTest {

    @Test
    void missingKeyThrows() {
        ModelProperties props = new ModelProperties(); // 默认 apiKey 为空
        ModelFactory factory = new ModelFactory(props);
        assertThatThrownBy(factory::qianwenVl)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("QIANWEN_API_KEY");
        assertThatThrownBy(factory::deepseek)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("DEEPSEEK_API_KEY");
    }
}
```

- [ ] **Step 6: 实现 ModelFactory**

```java
// ModelFactory.java
package com.iclothes.ai;

import java.time.Duration;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import com.iclothes.config.ModelProperties;

public class ModelFactory {

    private final ModelProperties properties;
    private ChatLanguageModel qianwenVl;
    private ChatLanguageModel deepseek;

    public ModelFactory(ModelProperties properties) { this.properties = properties; }

    public synchronized ChatLanguageModel qianwenVl() {
        if (qianwenVl == null) {
            ModelProperties.Model m = properties.getQianwen();
            if (m.getApiKey().isBlank()) {
                throw new IllegalStateException("QIANWEN_API_KEY 未配置，请在环境变量中设置");
            }
            qianwenVl = build(m);
        }
        return qianwenVl;
    }

    public synchronized ChatLanguageModel deepseek() {
        if (deepseek == null) {
            ModelProperties.Model m = properties.getDeepseek();
            if (m.getApiKey().isBlank()) {
                throw new IllegalStateException("DEEPSEEK_API_KEY 未配置");
            }
            deepseek = build(m);
        }
        return deepseek;
    }

    private ChatLanguageModel build(ModelProperties.Model m) {
        return OpenAiChatModel.builder()
                .apiKey(m.getApiKey())
                .baseUrl(m.getBaseUrl())
                .modelName(m.getModel())
                .temperature(0.7)
                .timeout(Duration.ofSeconds(60))
                .build();
    }
}
```

- [ ] **Step 7: 运行全部测试**

Run: `mvn -f iclothes-server/pom.xml test`
Expected: 全部通过（IntentRouterTest 6 + ModelFactoryTest 1 + HealthControllerTest 1）。

- [ ] **Step 8: Commit**

```bash
git add iclothes-server/
git commit -m "feat: intent router and model factory"
```

---

### Task 3: Flyway schema + 实体 + Mapper（TDD，集成测试跑本地 PG）

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
  - `Conversation`（`id:UUID`、`title:String`、`createdAt/updatedAt:LocalDateTime`）
  - `Message`（`id:Long`、`conversationId:UUID`、`role/content/intent:String`、`images:List<String>`、`createdAt:LocalDateTime`）
  - `ConversationMapper`：`BaseMapper<Conversation>` + `List<ConversationSummaryDto> selectSummaries()`
  - `MessageMapper`：`BaseMapper<Message>`

- [ ] **Step 1: 写 schema 与实体（先建交付物，再写测试）**

`V1__init.sql`（与 spec §5 一致）：

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

`Message.java`（images 用 JacksonTypeHandler 映射 JSONB）：

```java
package com.iclothes.entity;

import java.time.LocalDateTime;
import java.util.List;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;

@TableName(value = "messages", autoResultMap = true)
public class Message {

    @TableId(type = IdType.AUTO)
    private Long id;
    private java.util.UUID conversationId;
    private String role;
    private String content;
    private String intent;
    @TableField(typeHandler = JacksonTypeHandler.class)
    private List<String> images;
    private LocalDateTime createdAt;

    // 全字段 getter/setter（与 Conversation 同风格，逐字段补全）
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public java.util.UUID getConversationId() { return conversationId; }
    public void setConversationId(java.util.UUID v) { conversationId = v; }
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

`ConversationSummaryDto.java`（列表摘要，含预览）：

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

- [ ] **Step 2: 写失败集成测试（前置：Task 0 的 `iclothes_test` 库存在）**

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
Expected: 编译失败（实体/Mapper 尚不存在）或连接失败。

- [ ] **Step 4: 运行测试确认通过**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=RepositoryIT`
Expected: BUILD SUCCESS，2 测试通过（Flyway 自动建表）。

- [ ] **Step 5: Commit**

```bash
git add iclothes-server/
git commit -m "feat: schema, entities, and mappers"
```

---

### Task 4: DTO + ChatService 编排（TDD，mock LLM 与 Mapper）

**Files:**
- Create: `iclothes-server/src/main/java/com/iclothes/dto/ChatRequest.java`
- Create: `iclothes-server/src/main/java/com/iclothes/dto/ChatResponse.java`
- Create: `iclothes-server/src/main/java/com/iclothes/dto/ConversationDto.java`
- Create: `iclothes-server/src/main/java/com/iclothes/dto/MessageDto.java`
- Create: `iclothes-server/src/main/java/com/iclothes/ai/Prompts.java`
- Create: `iclothes-server/src/main/java/com/iclothes/service/ConversationService.java`
- Create: `iclothes-server/src/main/java/com/iclothes/service/ChatService.java`
- Test: `iclothes-server/src/test/java/com/iclothes/service/ConversationServiceTest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/service/ChatServiceTest.java`

**Interfaces:**
- Consumes: `IntentRouter.route`、`ModelFactory`（Task 2）；`ConversationMapper/MessageMapper`（Task 3）
- Produces:
  - `ConversationService.create() -> ConversationDto`、`listSummaries() -> List<ConversationSummaryDto>`、`get(UUID) -> ConversationDto|null`、`delete(UUID) -> boolean`
  - `ChatService.chat(String conversationId, String message, List<String> images) -> ChatResponse`（自动新建会话、意图路由、分支调用、落库、自动标题、裁剪 50 条）
  - `ChatResponse`：`conversationId:String`、`reply:String`、`intent:String`、`title:String`

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
import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.output.Response;
import com.iclothes.ai.IntentRouter;
import com.iclothes.entity.Conversation;
import com.iclothes.repository.ConversationMapper;
import com.iclothes.repository.MessageMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ChatServiceTest {

    @Mock ConversationMapper conversations;
    @Mock MessageMapper messages;
    @Mock ChatLanguageModel deepseek;
    @Mock ChatLanguageModel qianwen;

    ChatService service;
    UUID cid = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        when(deepseek.generate(anyList())).thenReturn(Response.from(AiMessage.from("你好！")));
        when(qianwen.generate(anyList())).thenReturn(Response.from(AiMessage.from("体征分析结果")));
        when(conversations.selectById(any(UUID.class)))
                .thenReturn(new Conversation(cid, "新对话", LocalDateTime.now(), LocalDateTime.now()));
        service = new ChatService(new IntentRouter(), deepseek, qianwen,
                conversations, messages);
    }

    @Test
    void chatIntentCallsDeepseekWithHistory() {
        ChatResponse resp = service.chat(cid.toString(), "你好，介绍一下你自己", List.of());
        assertThat(resp.getIntent()).isEqualTo("chat");
        assertThat(resp.getReply()).isEqualTo("你好！");
        verify(deepseek).generate(argThat(list -> list.size() >= 1));
    }

    @Test
    void recommendWithoutImagesUsesDescriptionOnly() {
        ChatResponse resp = service.chat(cid.toString(), "帮我推荐上班通勤的穿搭", List.of());
        assertThat(resp.getIntent()).isEqualTo("recommend");
        verify(qianwen, never()).generate(anyList());
        verify(deepseek).generate(argThat(list -> {
            String joined = list.toString();
            return joined.contains("没有照片") || joined.contains("未上传");
        }));
    }

    @Test
    void recommendWithImagesCallsQianwenThenDeepseek() {
        ChatResponse resp = service.chat(cid.toString(), "帮我看看", List.of("data:image/png;base64,AAAA"));
        assertThat(resp.getIntent()).isEqualTo("recommend");
        verify(qianwen).generate(anyList());
        verify(deepseek).generate(anyList());
    }

    @Test
    void unknownConversationCreatesNew() {
        when(conversations.selectById(any(UUID.class))).thenReturn(null);
        when(conversations.insert(any(Conversation.class))).thenReturn(1);
        ChatResponse resp = service.chat(null, "你好", List.of());
        assertThat(resp.getConversationId()).isNotNull();
    }

    @Test
    void firstMessageSetsTitle() {
        when(conversations.selectById(any(UUID.class))).thenReturn(null);
        when(conversations.insert(any(Conversation.class))).thenReturn(1);
        ChatResponse resp = service.chat(null, "帮我推荐一条裙子", List.of());
        assertThat(resp.getTitle()).isEqualTo("帮我推荐一条裙子");
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f iclothes-server/pom.xml test -Dtest=ChatServiceTest`
Expected: 编译失败（`ChatService`/DTO 不存在）。

- [ ] **Step 3: 实现 DTO**

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

- [ ] **Step 4: 实现 Prompts + ConversationService + ChatService**

```java
// Prompts.java
package com.iclothes.ai;

public final class Prompts {
    private Prompts() {}

    public static final String CHAT_SYSTEM =
            "你是 i-clothes 智能穿搭助手，一个友好、专业的时尚顾问。\n" +
            "你可以和用户轻松闲聊，也可以回答穿搭相关问题。\n" +
            "当用户明确想要穿搭建议时（如提到\"推荐\"\"搭配\"等），建议引导用户：\n" +
            "- 可以上传照片获得更精准的个性化建议；\n" +
            "- 或直接给出基于文字描述的穿搭建议。\n" +
            "回答用中文，简洁自然，不要过于冗长。";

    public static final String RECOMMEND_SYSTEM =
            "你是一名专业的穿搭顾问。你会收到一份对用户体型、脸型、腿型、肤色等特征的客观分析，\n" +
            "以及用户的穿搭需求。请基于这些信息，给出个性化、扬长避短的100字以内穿搭建议。\n" +
            "请按以下结构输出（使用中文）：\n" +
            "1. 整体风格定位：一句话概括推荐的风格方向\n" +
            "2. 推荐色系：结合肤色，给出显气色的主色调和搭配色\n" +
            "3. 单品建议：上衣、下装、鞋子、配饰的具体建议，说明如何扬长避短\n" +
            "4. 搭配技巧：2-3 条结合其体型特征的实用要点\n" +
            "注意：如果【体征分析】部分为空（用户未上传照片），请完全基于【用户需求】和\n" +
            "【历史对话】中的信息给出建议，并在开头加一句\"没有照片的情况下，我先按文字描述\n" +
            "给你参考建议\"。\n" +
            "回答要具体、可执行，紧扣前面的信息，避免空泛的描述。";

    public static final String APPEARANCE_SYSTEM =
            "你是一名专业的形象分析师。用户会上传一张或多张人物照片。\n" +
            "请仔细观察照片中的人物，客观描述其可见的身体特征，供后续穿搭推荐使用。\n" +
            "请按以下结构输出（使用中文），只描述能从照片中客观观察到的信息，不要推测或编造：\n" +
            "1. 体型：整体身材比例（如高挑/娇小、纤细/匀称等），肩宽、腰身特征\n" +
            "2. 头型/脸型：脸型轮廓（如鹅蛋脸、圆脸、方脸等）\n" +
            "3. 腿型：腿部线条特征、长短比例\n" +
            "4. 肤色：肤色冷暖倾向（冷调/暖调/中性）和明度（白皙/小麦色等）\n" +
            "5. 其他：发型、发色、以及照片中已有的穿着风格\n" +
            "如果某项无法从照片中判断，请标注\"无法判断\"。保持客观、简洁。";
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

```java
// ChatService.java
package com.iclothes.service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.data.message.ImageContent;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.TextContent;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatLanguageModel;
import com.iclothes.ai.IntentRouter;
import com.iclothes.ai.Prompts;
import com.iclothes.dto.ChatResponse;
import com.iclothes.entity.Conversation;
import com.iclothes.entity.Message;
import com.iclothes.repository.ConversationMapper;
import com.iclothes.repository.MessageMapper;

@Service
public class ChatService {

    private static final String DEFAULT_TITLE = "新对话";
    private static final int TITLE_MAX = 20;
    private static final int CHAT_CONTEXT = 10;
    private static final int RECOMMEND_CONTEXT = 6;

    private final IntentRouter intentRouter;
    private final ChatLanguageModel deepseek;
    private final ChatLanguageModel qianwenVl;
    private final ConversationMapper conversations;
    private final MessageMapper messages;

    public ChatService(IntentRouter intentRouter, ChatLanguageModel deepseek,
                       ChatLanguageModel qianwenVl, ConversationMapper conversations,
                       MessageMapper messages) {
        this.intentRouter = intentRouter;
        this.deepseek = deepseek;
        this.qianwenVl = qianwenVl;
        this.conversations = conversations;
        this.messages = messages;
    }

    public ChatResponse chat(String conversationId, String message, List<String> images) {
        UUID cid = null;
        if (conversationId != null && !conversationId.isBlank()) {
            try { cid = UUID.fromString(conversationId); } catch (IllegalArgumentException ignored) { cid = null; }
        }
        Conversation conv = cid == null ? null : conversations.selectById(cid);
        boolean isNew = conv == null;
        if (isNew) {
            conv = new Conversation(UUID.randomUUID(), DEFAULT_TITLE,
                    LocalDateTime.now(), LocalDateTime.now());
            conversations.insert(conv);
        }
        cid = conv.getId();

        List<Message> history = messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, cid)
                .orderByAsc(Message::getId));

        // 意图路由（有图必推荐；文本为空回退到最近用户消息）
        boolean hasImages = images != null && !images.isEmpty();
        List<String> historyUserTexts = history.stream()
                .filter(m -> "user".equals(m.getRole()))
                .map(Message::getContent).toList();
        String intent = intentRouter.route(message, hasImages, historyUserTexts);

        String reply;
        if ("recommend".equals(intent)) {
            reply = recommend(history, message, images, hasImages);
        } else {
            reply = chatReply(history, message);
        }

        // 落库
        Message userMsg = new Message();
        userMsg.setConversationId(cid);
        userMsg.setRole("user");
        userMsg.setContent(message == null ? "" : message);
        userMsg.setIntent("");
        userMsg.setImages(hasImages ? images : List.of());
        userMsg.setCreatedAt(LocalDateTime.now());
        messages.insert(userMsg);

        Message aiMsg = new Message();
        aiMsg.setConversationId(cid);
        aiMsg.setRole("assistant");
        aiMsg.setContent(reply);
        aiMsg.setIntent(intent);
        aiMsg.setImages(List.of());
        aiMsg.setCreatedAt(LocalDateTime.now());
        messages.insert(aiMsg);

        trimHistory(cid);

        // 自动标题
        String title = conv.getTitle();
        if (isNew && message != null && !message.isBlank()) {
            title = message.trim().replace("\n", " ").substring(0,
                    Math.min(TITLE_MAX, message.trim().length()));
            Conversation upd = new Conversation(cid, title, conv.getCreatedAt(), LocalDateTime.now());
            conversations.updateById(upd);
        }

        return new ChatResponse(cid.toString(), reply, intent, title);
    }

    private String chatReply(List<Message> history, String message) {
        List<ChatMessage> msgs = new ArrayList<>();
        msgs.add(SystemMessage.from(Prompts.CHAT_SYSTEM));
        int start = Math.max(0, history.size() - CHAT_CONTEXT);
        for (int i = start; i < history.size(); i++) {
            Message m = history.get(i);
            if ("user".equals(m.getRole())) msgs.add(UserMessage.from(m.getContent()));
            else msgs.add(AiMessage.from(m.getContent()));
        }
        msgs.add(UserMessage.from(message == null ? "" : message));
        return deepseek.generate(msgs).content().text();
    }

    private String recommend(List<Message> history, String message, List<String> images,
                             boolean hasImages) {
        List<ChatMessage> msgs = new ArrayList<>();
        msgs.add(SystemMessage.from(Prompts.RECOMMEND_SYSTEM));

        String appearance = "";
        if (hasImages) {
            // 千问多模态体征分析
            List<dev.langchain4j.data.message.Content> contents = new ArrayList<>();
            for (String url : images) contents.add(ImageContent.from(url));
            contents.add(TextContent.from("请分析这些照片中人物的客观体征。"));
            String appearanceText = qianwenVl.generate(List.of(
                    SystemMessage.from(Prompts.APPEARANCE_SYSTEM),
                    UserMessage.from(contents))).content().text();
            appearance = appearanceText;
        }

        String need = (message == null || message.isBlank()) ? "日常穿搭，无特殊场合要求。" : message;
        StringBuilder user = new StringBuilder();
        user.append("【体征分析】\n").append(appearance.isBlank() ? "（无，用户未上传照片）" : appearance)
            .append("\n\n【用户需求】\n").append(need).append("\n\n");
        List<String> historyUserTexts = history.stream()
                .filter(m -> "user".equals(m.getRole()) && m.getContent() != null && !m.getContent().isBlank())
                .map(Message::getContent).toList();
        int start = Math.max(0, historyUserTexts.size() - RECOMMEND_CONTEXT);
        if (!historyUserTexts.isEmpty()) {
            user.append("【历史对话】\n");
            for (int i = start; i < historyUserTexts.size(); i++) {
                user.append("- ").append(historyUserTexts.get(i)).append("\n");
            }
            user.append("\n");
        }
        user.append("请基于以上信息给出穿搭建议。");
        msgs.add(UserMessage.from(user.toString()));
        return deepseek.generate(msgs).content().text();
    }

    private void trimHistory(UUID cid) {
        long total = messages.selectCount(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, cid));
        if (total > ConversationService.MAX_HISTORY) {
            long excess = total - ConversationService.MAX_HISTORY;
            messages.delete(new LambdaQueryWrapper<Message>()
                    .eq(Message::getConversationId, cid)
                    .orderByAsc(Message::getId)
                    .last("LIMIT " + excess));
        }
    }
}
```

- [ ] **Step 5: 实现 ConversationService 测试**

```java
// ConversationServiceTest.java
package com.iclothes.service;

import java.time.LocalDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import com.iclothes.dto.ConversationDto;
import com.iclothes.entity.Conversation;
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
}
```

- [ ] **Step 6: 运行全部测试**

Run: `mvn -f iclothes-server/pom.xml test`
Expected: 全部通过（含既有测试）。

- [ ] **Step 7: Commit**

```bash
git add iclothes-server/
git commit -m "feat: chat orchestration service"
```

---

### Task 5: Controller 层 + 统一异常处理（TDD，MockMvc）

**Files:**
- Create: `iclothes-server/src/main/java/com/iclothes/controller/ChatController.java`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/ConversationController.java`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/RecommendController.java`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/ApiException.java`
- Create: `iclothes-server/src/main/java/com/iclothes/controller/GlobalExceptionHandler.java`
- Test: `iclothes-server/src/test/java/com/iclothes/controller/ChatControllerTest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/controller/ConversationControllerTest.java`
- Test: `iclothes-server/src/test/java/com/iclothes/controller/RecommendControllerTest.java`

**Interfaces:**
- Consumes: `ChatService.chat`、`ConversationService`（Task 4）
- Produces: `ApiException(int status, String detail)`；`GlobalExceptionHandler` 把 `ApiException` → `{status, {"detail"}}`；`IllegalStateException`（模型未配置）→ 502；`Exception` → 500

- [ ] **Step 1: 写失败测试**

```java
// ChatControllerTest.java
package com.iclothes.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.config.ModelProperties;
import com.iclothes.service.ChatService;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(ChatController.class)
@Import(ModelProperties.class)
class ChatControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean
    ChatService chatService;

    @Test
    void emptyMessageAndImagesRejected() throws Exception {
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"\",\"images\":[]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("消息内容不能为空"));
    }

    @Test
    void invalidImageFormatRejected() throws Exception {
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hi\",\"images\":[\"data:image/gif;base64,AAAA\"]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("不支持的图片格式，仅支持 JPG/PNG"));
    }

    @Test
    void tooManyImagesRejected() throws Exception {
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
    void happyPathReturnsChatResponse() throws Exception {
        when(chatService.chat(any(), any(), anyList()))
                .thenReturn(new com.iclothes.dto.ChatResponse("abc", "回复", "chat", "新对话"));
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
Expected: 编译失败（Controller/异常类不存在）。

- [ ] **Step 3: 写 ConversationControllerTest 与 RecommendControllerTest（失败测试）**

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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

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
import com.iclothes.config.ModelProperties;
import com.iclothes.service.ChatService;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(RecommendController.class)
@Import(ModelProperties.class)
class RecommendControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean
    ChatService chatService;

    @Test
    void noImagesRejected() throws Exception {
        mvc.perform(multipart("/api/recommend"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("请至少上传一张照片"));
    }

    @Test
    void wrongContentTypeRejected() throws Exception {
        MockMultipartFile file = new MockMultipartFile("images", "a.txt", "text/plain", new byte[]{1});
        mvc.perform(multipart("/api/recommend").file(file))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("不支持的图片格式：text/plain，仅支持 JPG/PNG"));
    }

    @Test
    void happyPath() throws Exception {
        when(chatService.chat(any(), any(), anyList()))
                .thenReturn(new com.iclothes.dto.ChatResponse("c", "建议", "recommend", "t"));
        MockMultipartFile file = new MockMultipartFile("images", "a.png", "image/png", new byte[]{1, 2, 3});
        mvc.perform(multipart("/api/recommend").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.suggestion").value("建议"));
    }
}
```

- [ ] **Step 4: 实现异常体系**

```java
// ApiException.java
package com.iclothes.controller;

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
// GlobalExceptionHandler.java
package com.iclothes.controller;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, String>> apiError(ApiException e) {
        return ResponseEntity.status(e.getStatus())
                .body(Map.of("detail", e.getMessage()));
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> modelNotConfigured(IllegalStateException e) {
        return ResponseEntity.status(502).body(Map.of("detail", e.getMessage()));
    }
}
```

- [ ] **Step 5: 实现 ChatController（含校验，与 Python 校验消息逐字一致）**

```java
// ChatController.java
package com.iclothes.controller;

import java.util.Base64;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.config.ModelProperties;
import com.iclothes.dto.ChatRequest;
import com.iclothes.dto.ChatResponse;
import com.iclothes.service.ChatService;

@RestController
public class ChatController {

    private static final Pattern DATA_URL = Pattern.compile("^data:image/(jpeg|png);base64,");

    private final ChatService chatService;
    private final ModelProperties properties;

    public ChatController(ChatService chatService, ModelProperties properties) {
        this.chatService = chatService;
        this.properties = properties;
    }

    @PostMapping("/api/chat")
    public ChatResponse chat(@RequestBody ChatRequest req) {
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
}
```

- [ ] **Step 6: 实现 ConversationController**

```java
// ConversationController.java
package com.iclothes.controller;

import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.dto.ConversationDto;
import com.iclothes.dto.ConversationSummaryDto;
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
    public java.util.Map<String, Boolean> delete(@PathVariable String id) {
        if (!service.delete(parseUuid(id))) throw new ApiException(404, "会话不存在");
        return java.util.Map.of("ok", true);
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

- [ ] **Step 7: 实现 RecommendController（multipart，复用 ChatController.validateImages 的语义：类型/数量/大小）**

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
import com.iclothes.config.ModelProperties;
import com.iclothes.service.ChatService;

@RestController
public class RecommendController {

    private final ChatService chatService;
    private final ModelProperties properties;

    public RecommendController(ChatService chatService, ModelProperties properties) {
        this.chatService = chatService;
        this.properties = properties;
    }

    @PostMapping("/api/recommend")
    public Map<String, String> recommend(
            @RequestParam("images") List<MultipartFile> images,
            @RequestParam(value = "description", defaultValue = "") String description) {
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
            urls.add("data:" + f.getContentType() + ";base64,"
                    + Base64.getEncoder().encodeToString(f.getBytes()));
        }
        var resp = chatService.chat(null, description, urls);
        return Map.of("suggestion", resp.getReply());
    }
}
```

- [ ] **Step 8: 运行全部测试**

Run: `mvn -f iclothes-server/pom.xml test`
Expected: 全部通过。若 `ChatControllerTest` 中 `chatService` 为 `@MockitoBean` 时校验在 Controller 内执行，校验用例不依赖 mock 返回值——通过即证明校验路径正确。

- [ ] **Step 9: Commit**

```bash
git add iclothes-server/
git commit -m "feat: controllers with unified error handling"
```

---

### Task 6: 前端联通 + 静态伺服（验证型）

**Files:**
- Modify: `frontend/vite.config.js`（代理目标 8000 → 8080）
- Modify: `iclothes-server/src/main/java/com/iclothes/config/ModelProperties.java`、`application.yml`（新增 `iclothes.frontend.dir`）
- Create: `iclothes-server/src/main/java/com/iclothes/controller/StaticController.java`
- Create: `iclothes-server/src/main/java/com/iclothes/config/WebConfig.java`
- Create: `iclothes-server/src/main/java/com/iclothes/config/ModelFactoryConfig.java`（把 ModelFactory 注册为 Spring Bean，供 ChatService 注入）
- Test: `iclothes-server/src/test/java/com/iclothes/config/StaticServeTest.java`

**Interfaces:**
- Produces: `ChatService` 构造改为注入 `ModelFactory`（替代直接注入两个 ChatLanguageModel）——本 Task 先行调整 Task 4 的构造签名：`ChatService(IntentRouter, ModelFactory, ConversationMapper, MessageMapper)`，内部 `factory.deepseek()/qianwenVl()` 懒取；`ChatServiceTest` 同步改为 mock `ModelFactory`。
- `WebConfig`：资源映射 `/` 与 `/assets/**` → `file:frontend/dist/`（相对启动工作目录）

- [ ] **Step 1: 调整依赖注入（ModelFactory 成为 Bean）**

```java
// ModelFactoryConfig.java
package com.iclothes.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import com.iclothes.ai.ModelFactory;

@Configuration
public class ModelFactoryConfig {
    @Bean
    public ModelFactory modelFactory(ModelProperties properties) {
        return new ModelFactory(properties);
    }
}
```

修改 `ChatService` 构造函数为：

```java
public ChatService(IntentRouter intentRouter, ModelFactory modelFactory,
                   ConversationMapper conversations, MessageMapper messages) {
    this.intentRouter = intentRouter;
    this.modelFactory = modelFactory;
    this.conversations = conversations;
    this.messages = messages;
}
```

`chatReply`/`recommend` 中 `deepseek` → `modelFactory.deepseek()`、`qianwenVl` → `modelFactory.qianwenVl()`；`ChatServiceTest` 中 `when(modelFactory.deepseek()).thenReturn(deepseekMock)`、`when(modelFactory.qianwenVl()).thenReturn(qianwenMock)`。

- [ ] **Step 2: 更新测试并跑绿**

Run: `mvn -f iclothes-server/pom.xml test`
Expected: 全部通过。

- [ ] **Step 3: 构建前端 + 写失败测试（需真实 dist 存在）**

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

- [ ] **Step 4: 实现前端目录配置 + 静态控制器 + 资源映射**

`ModelProperties` 增加：

```java
private final Frontend frontend = new Frontend();

public Frontend getFrontend() { return frontend; }

public static class Frontend {
    private String dir = "frontend/dist";
    public String getDir() { return dir; }
    public void setDir(String v) { dir = v; }
}
```

`application.yml` 增加：

```yaml
  frontend:
    dir: ${FRONTEND_DIST:frontend/dist}
```

`StaticController.java`：

```java
package com.iclothes.controller;

import java.io.File;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.config.ModelProperties;

@RestController
public class StaticController {

    private final ModelProperties properties;

    public StaticController(ModelProperties properties) { this.properties = properties; }

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    public Resource index() {
        return new FileSystemResource(new File(properties.getFrontend().getDir(), "index.html"));
    }
}
```

`WebConfig.java`（只映射 `/assets/**`，`file:` 位置以 `/` 结尾）：

```java
package com.iclothes.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final ModelProperties properties;

    public WebConfig(ModelProperties properties) { this.properties = properties; }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("file:" + properties.getFrontend().getDir() + "/assets/");
    }
}
```

- [ ] **Step 5: 修改 vite 代理**

`frontend/vite.config.js` 中：

```js
proxy: {
  '/api': 'http://127.0.0.1:8080',
},
```

- [ ] **Step 6: 验证**

Run:
```powershell
mvn -f iclothes-server/pom.xml package -DskipTests
# 启动：java -jar iclothes-server/target/iclothes-server-0.1.0.jar（工作目录=仓库根）
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8080/api/health   # 200
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8080/            # 200（dist index.html）
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8080/assets/index-*.js  # 200
```
Expected: 三个均 200。`WebConfigTest` 通过。

- [ ] **Step 7: Commit**

```bash
git add iclothes-server/ frontend/vite.config.js
git commit -m "feat: serve frontend dist and wire dev proxy to 8080"
```

---

### Task 7: 端到端验收 + Docker compose 交付物

**Files:**
- Create: `iclothes-server/Dockerfile`
- Create: `docker-compose.yml`（项目根）
- 无新增 Java 源码（修复本任务发现的问题除外）

**Interfaces:** 无（验收任务；失败修复需回归 Task 1-6 的测试）

- [ ] **Step 1: 启动应用与 PG，跑 spec §2.2 行为清单冒烟**

```powershell
# 前置：PG 服务已启动；iclothes 库存在
mvn -f iclothes-server/pom.xml package -DskipTests
Start-Process -FilePath java -ArgumentList '-jar','iclothes-server/target/iclothes-server-0.1.0.jar' -WorkingDirectory 'D:\code\i-clothes'
Start-Sleep -Seconds 15
curl.exe -s http://127.0.0.1:8080/api/health
```
Expected: `{"status":"ok","qianwen_configured":true}`（若 .env 的 key 未导出到环境变量则为 false，功能不受影响）。

- [ ] **Step 2: 行为清单逐项验证（curl，JSON body 走 UTF-8 文件，参照 spec §2.2）**

```powershell
# a) 新建会话
$cid = (curl.exe -s -X POST http://127.0.0.1:8080/api/conversations | ConvertFrom-Json).id
# b) 闲聊：你好 → intent=chat
# c) 推荐（无图）→ intent=recommend，回复以「没有照片的情况下…」开头
# d) 有图推荐（可选，真图 data URL）→ intent=recommend
# e) 校验：空消息→400 消息内容不能为空；坏图片→400 不支持的图片格式；4 张图→400 最多上传 3 张照片
# f) 会话详情：messages=4（2 user + 2 assistant），assistant 消息带 intent
# g) 自动标题 = 首条用户消息前 20 字符
# h) 删除会话→{ok:true}；GET 不存在→404 会话不存在
# i) 重启应用后 GET 会话列表仍有数据（PG 持久化）
```
Expected: 与 Python 版行为清单逐项一致。

- [ ] **Step 3: 前端联通走查（浏览器或 curl 等价）**

```powershell
# dev 模式：vite dev (5173) 代理到 8080，页面可新建会话并发消息
# 生产模式：http://127.0.0.1:8080/ 直接可用
```
Expected: 前端全流程可用（新建会话 → 闲聊 → 文字推荐 → 传图推荐 → 切换/删除会话 → 刷新后历史仍在）。

- [ ] **Step 4: 编写 Docker 交付物（本机无 Docker，仅交付+语法校验）**

`iclothes-server/Dockerfile`（构建上下文为仓库根目录）：

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY iclothes-server/target/iclothes-server-0.1.0.jar app.jar
COPY frontend/dist ./dist
ENV FRONTEND_DIST=dist
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

`docker-compose.yml`（项目根）：

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

  iclothes-server:
    build:
      context: .
      dockerfile: iclothes-server/Dockerfile
    environment:
      DB_URL: jdbc:postgresql://postgres:5432/iclothes
      DB_USER: ${DB_USER:-postgres}
      DB_PASSWORD: ${DB_PASSWORD:-iclothes123}
      FRONTEND_DIST: dist
      QIANWEN_API_KEY: ${QIANWEN_API_KEY}
      QIANWEN_BASE_URL: ${QIANWEN_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}
      QIANWEN_MODEL: ${QIANWEN_MODEL:-qwen3.7-max-2026-06-08}
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
      DEEPSEEK_BASE_URL: ${DEEPSEEK_BASE_URL:-https://api.deepseek.com}
      DEEPSEEK_MODEL: ${DEEPSEEK_MODEL:-deepseek-v4-flash}
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
```

校验：`docker compose config`（Docker 可用时）；不可用则人工核对 YAML 缩进与变量引用。

- [ ] **Step 5: Commit**

```bash
git add iclothes-server/Dockerfile docker-compose.yml
git commit -m "chore: docker compose deliverable"
```

---

### Task 8: 切换与清理

**Files:**
- Modify: `常用指令`、`CHANGELOG.md`、`README.md`
- Delete: `app/`、`requirements.txt`、`frontend/package-lock.json`（保留）、`.conda/`（由用户决定，默认保留到确认后）

**Interfaces:** 无

- [ ] **Step 1: 更新 `常用指令`**

替换 Python 启动指令为：

```
启动后端（Java，需先启动 PostgreSQL 服务）
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
- 后端由 Python（FastAPI + LangGraph）迁移为 Java 21 + Spring Boot 3
  （LangChain4j + MyBatis-Plus + PostgreSQL 16），接口契约与行为等价
- 会话持久化：内存存储 → PostgreSQL（重启不丢）

### Removed
- `app/`（Python 后端）、`requirements.txt`
```

- [ ] **Step 3: 删除 Python 后端代码并提交**

```powershell
Remove-Item app -Recurse -Force
Remove-Item requirements.txt -Force
```

```bash
git add -A
git commit -m "chore: switch default backend to Spring Boot, remove Python app"
```

- [ ] **Step 4: 验收复核（spec §10.3）**

```powershell
# 全新环境模拟：停 PG 服务→重启→起 jar→浏览器走全流程
```
Expected: 四条验收标准全部满足（Docker compose 验收项按 Global Constraints 降级为本地 PG + jar 等价验证）。

---

## Self-Review 记录

- **Spec 覆盖**：§2.1 接口 7 项 → Task 1（health）+ Task 5（chat/conversations/recommend）✓；§2.2 行为清单 → Task 2（意图 6 用例）+ Task 5（校验消息）+ Task 7（冒烟逐项）✓；§5 数据模型 → Task 3 ✓；§6 AI 层 → Task 2/4 ✓；§7 契约/静态伺服 → Task 5/6 ✓；§8 配置部署 → Task 1 yml + Task 7 compose ✓；§9 边界失败模式 → Task 5 异常处理 + Task 4 无效会话自动新建 ✓；§10 测试验收 → 各 Task + Task 7 ✓；§11 迁移步骤 → Task 0-8 一一对应 ✓；§12 假设 → Global Constraints 已注明。
- **占位符扫描**：所有代码步骤均含真实代码；无 TBD/TODO。
- **类型一致性**：`ChatService.chat(String, String, List<String>) -> ChatResponse` 在 Task 4 定义、Task 5/6 引用一致；`ConversationSummaryDto`（Task 3）在 Task 4 `listSummaries` 复用一致；`ModelFactory` 在 Task 2 定义、Task 6 改为 Bean 注入并同步更新测试——Task 6 步骤 1 明确标注了构造签名变更。
- **已知偏差**：Task 0 引入 PG 安装（spec 未含，因本机无任何 DB）；Task 7 compose 验收降级（本机无 Docker/WSL，Global Constraints 已声明）。
- **自审修正**：① 静态伺服由"资源映射 `/`"改为 `StaticController` + 仅映射 `/assets/**`，前端目录走 `iclothes.frontend.dir` 配置（规避 welcome-page 行为不确定与测试工作目录相对路径问题，测试用 `../frontend/dist` 显式覆盖）；② `ChatControllerTest` 补 `@Import(ModelProperties.class)`（`@WebMvcTest` 不加载 `@EnableConfigurationProperties`）；③ 补齐 ConversationControllerTest / RecommendControllerTest 完整代码（原稿缺失，违反 no-placeholder）；④ compose 构建上下文改仓库根、Dockerfile 携带 dist 并设 `FRONTEND_DIST=dist`。
