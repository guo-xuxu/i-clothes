# 意图分析节点 query_analyzer 设计（i-clothes 检索阶段前置）

| 项 | 值 |
|---|---|
| 日期 | 2026-08-28 |
| 状态 | 已评审（用户确认设计，2026-08-28） |
| 分支 | main |
| 范围 | **仅意图确定**：intent + dimension + photo_type + 必要信息提取；在线检索（retrieve_context）后续单独排期 |
| 关联 | `docs/RAG知识图谱规划.md`、`app/knowledge/IMPLEMENTATION.md` |

## 1. 目标与背景

在线检索（图遍历 + 向量召回）需要知道"这条消息落在哪个知识维度"，但目前 `intent_router.py`
只有粗粒度的 recommend|chat 关键词二分类，且完全不含图片信息。本设计在 LangGraph 工作流入口
新增 **query_analyzer** 节点，对每条消息做一次结构化分析，产出四个字段：

1. **intent**（用户想干嘛）：`outfit` 穿搭 / `match` 搭配 / `style` 风格 / `color` 颜色 / `chat` 闲聊
2. **dimension**（消息落在哪个知识维度）：9 大知识维度 + `general`——**闲聊也归类维度**
   （如"羊毛和棉哪个好" → intent=chat、dimension=面料与材质；纯寒暄 → general）
3. **photo_type**（照片类型）：`full_body` 全身 / `half_body` 半身 / `head_shot` 大头 / `unknown`
4. **info**（必要信息）：体型 / 肤色 / 脸型 / 当前穿着 / 场合提示（从照片与文字提取）

**本阶段不做**：检索（retrieve_context）、维度过滤召回、prompt 注入知识——后续排期，但本设计
保证后续可以直接消费 intent/dimension。

## 2. 决策（已确认）

| # | 决策 | 结论 |
|---|---|---|
| D1 | 意图粒度 | 5 类（outfit/match/style/color/chat） |
| D2 | 判定方式 | **混合**：有图 → 千问多模态**一次调用**（意图+维度+照片类型+信息）；无图 → 关键词规则（零成本） |
| D3 | 闲聊也定维度 | 所有 intent（含 chat）都输出 dimension；9 维度 + general |
| D4 | 照片类型用途 | 影响信息提取重点（prompt 内指令，模型一次判定）+ 后续检索维度倾向 |
| D5 | 对外契约不变 | `/api/agent/chat` 响应 `intent` 仍映射 `recommend|chat`（前端按 `intent==='recommend'` 显示"穿搭模式"，零改动）；新字段内部流转 |
| D6 | 结构化输出 | Agno/Pydantic 校验 + 解析失败 fail-open（降级 chat/general/unknown + 空 info） |

## 3. 输出模型（Pydantic）

```python
class AnalysisInfo(BaseModel):
    body_shape: str = ""     # 体型（仅照片可判断时）
    skin_tone: str = ""      # 肤色冷暖/明度
    face_shape: str = ""     # 脸型
    current_outfit: str = "" # 当前穿着（颜色/单品）
    occasion_hint: str = ""  # 场合线索（文字+照片）

class QueryAnalysis(BaseModel):
    intent: Literal["outfit", "match", "style", "color", "chat"] = "chat"
    dimension: Literal["廓形与版型", "身材比例与修饰", "面料与材质", "风格定位",
                       "图案与纹理", "配饰与点缀", "场合与季节", "颜色搭配",
                       "肤色与个人色彩", "general"] = "general"
    photo_type: Literal["full_body", "half_body", "head_shot", "unknown"] = "unknown"
    info: AnalysisInfo = AnalysisInfo()
```

LLM 返回 JSON 文本 → 正则提取 `{...}` → Pydantic 校验 → 失败降级默认值（log warning）。

## 4. 节点行为

### 4.1 无图路径（关键词规则，零成本）

`intent_router.py` 改造为关键词 5 类 + 维度表：

| intent | 关键词组（示例） |
|---|---|
| outfit | 穿搭、怎么穿、穿什么、衣服、着装、通勤、面试、婚礼、约会… |
| match | 搭配、配什么、怎么配、配饰、组合… |
| style | 风格、什么风、极简、复古、街头、优雅… |
| color | 颜色、色系、显白、配色、肤色… |
| chat | 兜底 |

维度判定用独立关键词表（与 docs/ 目录对齐）：场合词→场合与季节、身材词→身材比例与修饰、
面料词→面料与材质、风格词→风格定位、图案词→图案与纹理、配饰词→配饰与点缀、
颜色/肤色词→颜色搭配或肤色与个人色彩、廓形词→廓形与版型；无命中 → general。
优先级：命中多个维度取首个命中（表序即优先级）；intent 取第一个命中的意图组，chat 兜底。

### 4.2 有图路径（千问多模态一次调用）

复用 `ModelRepository.get_qianwen_vl()`（langchain ChatOpenAI + image_url 消息，与
analyze_appearance 相同模式）；prompt 一次产出完整 JSON。prompt 要点：

- 判定意图（结合图片内容与文字）；
- 判定照片类型：全身/半身/大头/无法判断；
- 按照片类型侧重提取 info：全身→体型/腿型/比例；半身→上半身单品/搭配；大头→脸型/肤色/发型；
  无法判断的字段标空串，禁止编造；
- 输出严格 JSON（示例给出），其余文字一律不要。

### 4.3 fail-open

解析失败/模型异常 → `QueryAnalysis()` 默认值（intent=chat、dimension=general、
photo_type=unknown、info 空），记日志，不中断对话（与现有抽取器同策略）。

## 5. 状态与工作流

`state.py`（OutfitState）新增：
- `intent_detail: str`（5 值内部意图）
- `dimension: str`
- `photo_type: str`
- `analysis: str`（info 格式化文本，**取代原 `appearance`**；下游 prompt 读 analysis）

`intent` 保留为映射值：intent_detail ∈ {outfit, match, style, color} → `intent="recommend"`；
chat → `"chat"`（对外契约与路由不变）。

工作流：

```
START → query_analyzer
  → 按 intent 分流（_route_by_intent 不变）：
      recommend + 有图 → recommend_outfit（无 analyze_appearance 了）
      recommend + 无图 → recommend_outfit
      chat → chat_reply
```

- `analyze_appearance.py` **删除**（功能并入 query_analyzer）；
- `recommend_outfit.py` 的【体征分析】段改读 `analysis`；
- `intent_router.py` 改造为关键词分析（产出 intent_detail/dimension，无图路径），
  对外仍是节点名 `intent_router` 或改名 `query_analyzer`（统一改名，workflow 同步）。

## 6. 测试与回归

- **关键词路由单测**：5 类意图命中、维度命中（含多关键词优先级）、闲聊→general、纯寒暄
- **多模态解析单测**：合法 JSON 解析、围栏/杂质容忍、非法 JSON → 默认值 fail-open、模型异常 → 默认值
- **契约回归**：`test_agent_contract.py` 9 用例保持全绿——fixture 更新：fake 千问返回合法分析 JSON
  （原"有图必推荐"语义改为"模型判定"）；无图路径不触发多模态
- **workflow 冒烟**：有图 outfit 意图 → recommend_outfit 收到 analysis；chat → chat_reply

## 7. 里程碑（TDD）

| M | 内容 |
|---|---|
| M1 | 意图/维度关键词表 + 无图分析函数（纯函数，可测） |
| M2 | `query_analyzer` 节点：多模态一次调用 + Pydantic 解析 + fail-open + mock 单测 |
| M3 | state 扩展 + workflow 接入 + 对外 intent 映射 + recommend_outfit 改读 analysis + 契约测试更新 |
| M4 | 全量回归（现有 Python 契约 + 新增）+ 文档（项目开发指南/CHANGELOG） |

## 8. 已知权衡

- 有图必调千问多模态（每条带图消息一次调用，成本高于纯关键词）；
- 意图/维度判定质量依赖模型，fail-open 保证不中断但可能降级（后续可用关键词校验模型输出兜底）；
- dimension 是单选（9+1），多主题消息取模型判定/首个命中——够用即可，不做多标签。
