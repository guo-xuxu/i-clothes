# 变更日志

本文档记录 i-clothes 项目的所有代码修改和版本变更。

## 格式说明

每个版本包含：
- **版本号**：遵循语义化版本（major.minor.patch）
- **发布日期**
- **变更类型**：Added（新增）、Changed（修改）、Fixed（修复）、Removed（移除）
- **影响文件**：列出所有修改的文件
- **变更原因**：说明为什么要做这个修改

---

## [Unreleased] - 开发中

### Added
- 创建 PRD.md - 产品需求文档
- 创建 CHANGELOG.md - 版本变更记录文档
- 搭建后端框架（FastAPI）：配置模块、上传接口、健康检查、静态资源服务
- 搭建前端上传界面（原生 HTML/CSS/JS）：支持点击/拖拽上传、预览、文字说明
- 引入 LangGraph 作为 agent 工作流框架，穿搭推荐以状态图（StateGraph）组织
- 集中式模型 provider（`app/providers.py`）：所有大模型客户端在此构造
- 千问多模态接入：通过 `ChatOpenAI` 指向 DashScope OpenAI 兼容端点

### Changed
- 千问调用逻辑从直连 httpx 改造为 LangGraph 节点 + 集中 provider
- `main.py` 由直接调用服务改为调用工作流 `run_recommendation`

### Removed
- `app/services/qianwen.py`（逻辑迁移至 `app/graph/` 与 `app/providers.py`）

**变更原因**：完成 MVP 前 3 步（项目结构、后端、前端）。采用 LangGraph
便于后续扩展 DeepSeek 识别/生图、季节/主题节点；模型调用集中封装，换模型只改一处。

**影响文件**：
- `PRD.md`、`CHANGELOG.md`（更新）
- `requirements.txt`、`.env.example`、`.gitignore`（新建/更新）
- `app/config.py`、`app/main.py`、`app/providers.py`（新建）
- `app/graph/{__init__,state,nodes,workflow}.py`（新建）
- `frontend/{index.html,style.css,app.js}`（新建）
- `app/services/qianwen.py`（删除）

---

## [0.0.1] - 2026-08-11

### Added
- 初始化 Git 仓库
- 创建 README.md

**变更原因**：项目初始化

**影响文件**：
- `README.md` (新建)
- `.git/` (初始化)

---

## 版本规划

### v0.1.0 (计划中)
**目标**：实现 MVP 基础功能
- 后端框架搭建（FastAPI）
- 前端上传界面
- 千问 API 集成
- Docker 配置
- 部署脚本

### v0.2.0 (计划中)
**目标**：完整推荐功能
- DeepSeek API 集成
- 图片识别功能
- 生图功能
- 结果展示优化

### v0.3.0 (计划中)
**目标**：场景增强
- 季节判断
- 主题穿搭
- UI/UX 优化

---

**文档维护**：每次代码提交前更新此文档  
**最后更新**：2026-08-11
