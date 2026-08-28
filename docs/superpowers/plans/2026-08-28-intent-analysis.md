# 意图分析节点 query_analyzer 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 LangGraph 工作流入口新增 `query_analyzer` 节点，对每条消息产出 intent（5 类）+ dimension（9 维度 + general，闲聊也归类）+ photo_type（全身/半身/大头）+ 必要信息提取，为后续在线检索提供前置分析。

**Architecture:** 无图走关键词规则（零成本，纯函数 `analyze_text`）；有图走千问多模态一次调用（`analyze_with_image`，复用 `get_qianwen_vl`），输出经正则提取 + Pydantic 校验（fail-open 降级默认值）。对外 `/api/agent/chat` 契约保持 `recommend|chat` 不变（内部新增 `intent_detail`/`dimension`/`photo_type`/`analysis`），`analyze_appearance.py` 删除、功能并入新节点。

**Tech Stack:** Python 3.12 + FastAPI + LangGraph + langchain `ChatOpenAI`（千问多模态）+ Pydantic v2。

**Spec:** `docs/superpowers/specs/2026-08-28-intent-analysis-design.md`（权威；本计划是它的论证）

## Global Constraints

- 对外契约不变：`/api/agent/chat` 响应 `intent` 只允许 `"recommend"|"chat"`（前端 `intent==='recommend'` 显示"穿搭模式"，零改动）；新字段仅在内部 state 流转
- 判定方式（spec D2）：有图 → 千问多模态一次调用；无图 → 关键词规则（不触网不花钱）
- 闲聊也定维度（spec D3）：所有 intent 都输出 dimension；纯寒暄 → `general`
- fail-open（spec D6）：解析失败/模型异常 → 默认值（chat/general/unknown/空 info），记日志，不中断对话
- Python 测试一律 mock 千问（不花钱）；沿用项目 FakeModel 模式（`SimpleNamespace(content=...)`）
- 回归红线：`test/test_agent_contract.py` 9 用例全绿（fixture 需同步更新，见 Task 3）
- 提交信息风格：`feat:`/`refactor:`/`test:`/`docs:`
- git：当前分支 `main`；Python 解释器 `D:\code\i-clothes\.conda\python.exe`

## 文件结构总览

```
【新建】app/graph/nodes/query_analyzer.py   # 关键词表 + Pydantic 模型 + 无图/有图分析 + 节点
【新建】test/test_query_analyzer.py        # 关键词路由/解析/节点单测（mock 千问）
【修改】app/graph/state.py                 # 新增 intent_detail/dimension/photo_type/analysis
【修改】app/graph/workflow.py              # 用 query_analyzer 替换 intent_router+analyze_appearance
【修改】app/graph/nodes/__init__.py        # 导出调整
【修改】app/graph/nodes/recommend_outfit.py# 改读 analysis
【删除】app/graph/nodes/analyze_appearance.py、intent_router.py
【修改】test/test_agent_contract.py        # fake 千问返回分析 JSON；意图语义测试更新
【修改】docs/项目开发指南.md、CHANGELOG.md  # 文档
```

---

### Task 1: 关键词分析（无图路径：意图 + 维度，纯函数）

**Files:**
- Create: `app/graph/nodes/query_analyzer.py`（本任务：模型 + 关键词表 + `analyze_text`；Task 2 追加多模态部分）
- Create: `test/test_query_analyzer.py`（本任务：`analyze_text` 用例）

**Interfaces:**
- Produces: `INTENT_KEYWORDS: dict[str, list[str]]`、`DIMENSION_KEYWORDS: dict[str, list[str]]`、
  `QueryAnalysis(BaseModel)`（intent/dimension/photo_type/info）、`AnalysisInfo(BaseModel)`、
  `analyze_text(message: str) -> QueryAnalysis`（Task 2/3 依赖）

- [ ] **Step 1: 写失败测试 test/test_query_analyzer.py（analyze_text 部分）**

```python
"""意图分析单测：无图关键词路由（意图 5 类 + 维度，纯函数，不触网）。"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.graph.nodes.query_analyzer import analyze_text  # noqa: E402


def test_outfit_intent_with_occasion_dimension():
    a = analyze_text("帮我推荐上班通勤的穿搭")
    assert a.intent == "outfit"
    assert a.dimension == "场合与季节"


def test_match_intent_general_dimension():
    a = analyze_text("这条裙子配什么上衣")
    assert a.intent == "match"
    assert a.dimension == "general"


def test_style_intent():
    a = analyze_text("我适合什么风格")
    assert a.intent == "style"
    assert a.dimension == "风格定位"


def test_color_intent_skin_dimension():
    a = analyze_text("我是冷皮，什么颜色显白")
    assert a.intent == "color"
    assert a.dimension == "肤色与个人色彩"


def test_color_intent_color_dimension():
    a = analyze_text("撞色怎么搭")
    assert a.intent == "match"
    assert a.dimension == "颜色搭配"


def test_wedding_outfit():
    a = analyze_text("参加婚礼穿什么")
    assert a.intent == "outfit"
    assert a.dimension == "场合与季节"


def test_casual_chat_general():
    a = analyze_text("你好，介绍一下你自己")
    assert a.intent == "chat"
    assert a.dimension == "general"


def test_empty_message_chat_general():
    a = analyze_text("")
    assert a.intent == "chat"
    assert a.dimension == "general"
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test/test_query_analyzer.py -v
```

Expected: FAIL（`cannot import name 'analyze_text'`——模块不存在）。

- [ ] **Step 3: 实现 query_analyzer.py（模型 + 关键词表 + analyze_text）**

```python
"""意图分析节点：对每条消息产出 intent/dimension/photo_type/必要信息。

- 无图：关键词规则（analyze_text，零成本）；
- 有图：千问多模态一次调用（analyze_with_image，结构化 JSON + Pydantic 校验，fail-open）。
对外契约不变：state["intent"] 仍是 recommend|chat（由 intent_detail 映射）。
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 意图关键词（dict 顺序即优先级；无命中 → chat）
# ---------------------------------------------------------------------------
INTENT_KEYWORDS: dict[str, list[str]] = {
    "outfit": ["推荐", "穿搭", "怎么穿", "穿什么", "穿啥", "衣服", "着装", "穿着", "look"],
    "match": ["搭配", "配什么", "怎么配", "配饰", "混搭", "搭什么", "组合"],
    "style": ["风格", "什么风", "极简", "复古", "街头", "优雅", "法式"],
    "color": ["颜色", "色系", "显白", "配色", "色调", "冷暖色"],
}

# ---------------------------------------------------------------------------
# 知识维度关键词（dict 顺序即优先级；无命中 → general）
# ---------------------------------------------------------------------------
DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "场合与季节": ["场合", "季节", "婚礼", "面试", "通勤", "约会", "上班",
                 "聚会", "出差", "旅游", "派对", "夏天", "冬天"],
    "身材比例与修饰": ["身材", "梨形", "苹果形", "显瘦", "显高", "腰线", "腿型", "肩宽", "比例"],
    "面料与材质": ["面料", "材质", "棉", "羊毛", "真丝", "麻", "透气", "垂坠", "保暖", "化纤", "混纺"],
    "风格定位": ["风格", "极简", "复古", "街头", "优雅", "法式", "休闲", "通勤风"],
    "图案与纹理": ["图案", "条纹", "格纹", "碎花", "印花", "波点", "纯色"],
    "配饰与点缀": ["配饰", "包", "鞋", "帽", "围巾", "腰带", "首饰", "耳环", "项链"],
    "肤色与个人色彩": ["肤色", "冷皮", "暖皮", "黄皮", "白皮", "四季型"],
    "颜色搭配": ["颜色", "色系", "配色", "显白", "撞色", "同色系", "色调"],
    "廓形与版型": ["廓形", "版型", "A型", "H型", "X型", "O型", "宽松", "紧身"],
}


class AnalysisInfo(BaseModel):
    """照片/文字中提取的必要信息（无法判断的字段为空串，禁止编造）。"""

    body_shape: str = ""      # 体型
    skin_tone: str = ""       # 肤色冷暖/明度
    face_shape: str = ""      # 脸型
    current_outfit: str = ""  # 当前穿着（颜色/单品）
    occasion_hint: str = ""   # 场合线索


class QueryAnalysis(BaseModel):
    """一次分析的完整输出。"""

    intent: Literal["outfit", "match", "style", "color", "chat"] = "chat"
    dimension: Literal[
        "廓形与版型", "身材比例与修饰", "面料与材质", "风格定位", "图案与纹理",
        "配饰与点缀", "场合与季节", "颜色搭配", "肤色与个人色彩", "general",
    ] = "general"
    photo_type: Literal["full_body", "half_body", "head_shot", "unknown"] = "unknown"
    info: AnalysisInfo = AnalysisInfo()


def analyze_text(message: str) -> QueryAnalysis:
    """无图路径：关键词规则 → 意图 + 维度（纯函数，零成本）。

    Args:
        message: 用户本轮文字。

    Returns:
        QueryAnalysis；photo_type 恒 unknown，info 恒空。
    """
    text = (message or "").lower()
    intent = "chat"
    for i, kws in INTENT_KEYWORDS.items():
        if any(kw in text for kw in kws):
            intent = i
            break
    dimension = "general"
    for d, kws in DIMENSION_KEYWORDS.items():
        if any(kw in text for kw in kws):
            dimension = d
            break
    return QueryAnalysis(intent=intent, dimension=dimension)
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test/test_query_analyzer.py -v
```

Expected: 8 passed。

- [ ] **Step 5: 提交**

```bash
git add app/graph/nodes/query_analyzer.py test/test_query_analyzer.py
git commit -m "feat: intent/dimension keyword analysis (stateless, no-image path)"
```

---

### Task 2: 多模态分析（parse_analysis + analyze_with_image + query_analyzer 节点）

**Files:**
- Modify: `app/graph/nodes/query_analyzer.py`（追加 `_ANALYSIS_PROMPT`、`parse_analysis`、`format_info`、`analyze_with_image`、`query_analyzer`）
- Modify: `test/test_query_analyzer.py`（追加用例）

**Interfaces:**
- Consumes: Task 1 的 `QueryAnalysis`/`AnalysisInfo`、`ModelRepository.get_qianwen_vl()`
- Produces: `parse_analysis(raw: str) -> QueryAnalysis`、`format_info(info: AnalysisInfo) -> str`、
  `analyze_with_image(images: list[str], message: str) -> QueryAnalysis`（async）、
  `query_analyzer(state: OutfitState) -> OutfitState`（async 节点，Task 3 依赖）

- [ ] **Step 1: 写失败测试（追加到 test/test_query_analyzer.py）**

```python
"""多模态分析单测：JSON 解析（合法/围栏/非法/异常 → fail-open）。"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.graph.nodes import query_analyzer as qa  # noqa: E402
from app.repositories.model_repo import ModelRepository  # noqa: E402


def test_parse_valid_json():
    raw = '{"intent": "style", "dimension": "风格定位", "photo_type": "half_body", "info": {"skin_tone": "暖皮"}}'
    a = qa.parse_analysis(raw)
    assert a.intent == "style"
    assert a.dimension == "风格定位"
    assert a.photo_type == "half_body"
    assert a.info.skin_tone == "暖皮"
    assert a.info.body_shape == ""


def test_parse_fenced_json():
    raw = '```json\n{"intent": "outfit", "dimension": "场合与季节", "photo_type": "full_body", "info": {}}\n```'
    a = qa.parse_analysis(raw)
    assert a.intent == "outfit"
    assert a.dimension == "场合与季节"


def test_parse_invalid_returns_defaults():
    a = qa.parse_analysis("这不是 JSON")
    assert a.intent == "chat"
    assert a.dimension == "general"
    assert a.photo_type == "unknown"


def test_parse_empty_returns_defaults():
    a = qa.parse_analysis("")
    assert a.intent == "chat"
    assert a.dimension == "general"


def test_parse_bad_intent_value_falls_back():
    # intent 不在允许值内 → Pydantic ValidationError → 默认值
    a = qa.parse_analysis('{"intent": "shopping", "dimension": "颜色搭配", "photo_type": "unknown", "info": {}}')
    assert a.intent == "chat"


def test_format_info_joins_nonempty():
    info = qa.AnalysisInfo(body_shape="匀称", skin_tone="暖皮")
    text = qa.format_info(info)
    assert "体型：匀称" in text
    assert "肤色：暖皮" in text
    assert "脸型" not in text


def test_format_info_empty():
    assert qa.format_info(qa.AnalysisInfo()) == ""


def test_analyze_with_image_parses_model_output(monkeypatch):
    class FakeVl:
        async def ainvoke(self, messages):
            return SimpleNamespace(content='{"intent": "color", "dimension": "肤色与个人色彩", "photo_type": "head_shot", "info": {"skin_tone": "冷皮"}}')

    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: FakeVl()))

    import asyncio
    a = asyncio.run(qa.analyze_with_image(["data:image/png;base64,AAAA"], "我适合什么颜色"))
    assert a.intent == "color"
    assert a.dimension == "肤色与个人色彩"
    assert a.photo_type == "head_shot"
    assert a.info.skin_tone == "冷皮"


def test_analyze_with_image_fails_open(monkeypatch):
    class BoomVl:
        async def ainvoke(self, messages):
            raise RuntimeError("provider error")

    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: BoomVl()))

    import asyncio
    a = asyncio.run(qa.analyze_with_image(["data:image/png;base64,AAAA"], "随便"))
    assert a.intent == "chat"
    assert a.dimension == "general"


def test_query_analyzer_node_maps_intent(monkeypatch):
    class FakeVl:
        async def ainvoke(self, messages):
            return SimpleNamespace(content='{"intent": "outfit", "dimension": "场合与季节", "photo_type": "full_body", "info": {"body_shape": "匀称"}}')

    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: FakeVl()))

    import asyncio
    out = asyncio.run(qa.query_analyzer({"images": ["data:image/png;base64,AAAA"], "description": "帮我看看"}))
    assert out["intent"] == "recommend"
    assert out["intent_detail"] == "outfit"
    assert out["dimension"] == "场合与季节"
    assert out["photo_type"] == "full_body"
    assert "匀称" in out["analysis"]


def test_query_analyzer_node_chat_with_image(monkeypatch):
    class FakeVl:
        async def ainvoke(self, messages):
            return SimpleNamespace(content='{"intent": "chat", "dimension": "general", "photo_type": "unknown", "info": {}}')

    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: FakeVl()))

    import asyncio
    out = asyncio.run(qa.query_analyzer({"images": ["data:image/png;base64,AAAA"], "description": "这张图好看吗"}))
    assert out["intent"] == "chat"
    assert out["intent_detail"] == "chat"


def test_query_analyzer_node_no_image_uses_keywords():
    import asyncio
    out = asyncio.run(qa.query_analyzer({"images": [], "description": "我适合什么风格"}))
    assert out["intent"] == "recommend"
    assert out["intent_detail"] == "style"
    assert out["dimension"] == "风格定位"
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test/test_query_analyzer.py -v
```

Expected: 新增用例 FAIL（`parse_analysis`/`format_info`/`analyze_with_image`/`query_analyzer` 未定义）。

- [ ] **Step 3: 实现（追加到 query_analyzer.py）**

```python
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import OutfitState
from app.repositories.model_repo import ModelRepository

_JSON_RE = re.compile(r"\{.*\}", re.S)

_ANALYSIS_PROMPT = """你是一名穿搭助手的前置分析器。用户可能上传照片并附文字。请一次性判断四件事，只输出一个 JSON 对象，不要任何多余文字：

1. intent（用户想做什么）：outfit=整体穿搭建议；match=单品/搭配；style=风格定位；color=颜色/配色；chat=闲聊或其他。
2. dimension（消息主题落在哪个知识维度，闲聊也算）：取值范围：廓形与版型/身材比例与修饰/面料与材质/风格定位/图案与纹理/配饰与点缀/场合与季节/颜色搭配/肤色与个人色彩/general（无法归类时）。
3. photo_type（照片类型）：full_body=全身照；half_body=半身照；head_shot=大头照/面部特写；unknown=无法判断或没有人物。
4. info（必要信息，按照片类型侧重提取）：全身照侧重体型/腿型/整体比例；半身照侧重上半身单品与搭配细节；大头照侧重脸型/肤色/发型；同时结合文字提取场合线索。无法从照片/文字判断的字段填空字符串，禁止编造。

输出格式（严格）：
{"intent": "...", "dimension": "...", "photo_type": "...", "info": {"body_shape": "", "skin_tone": "", "face_shape": "", "current_outfit": "", "occasion_hint": ""}}"""


def parse_analysis(raw: str) -> QueryAnalysis:
    """解析 LLM 输出为 QueryAnalysis；任何失败降级默认值（fail-open，spec D6）。"""
    if not raw:
        return QueryAnalysis()
    m = _JSON_RE.search(raw)
    if not m:
        return QueryAnalysis()
    try:
        data = json.loads(m.group(0))
        info_data = data.get("info") or {}
        info = AnalysisInfo(**{k: (v or "") for k, v in info_data.items()})
        return QueryAnalysis(
            intent=data.get("intent", "chat"),
            dimension=data.get("dimension", "general"),
            photo_type=data.get("photo_type", "unknown"),
            info=info,
        )
    except Exception as exc:  # noqa: BLE001 - 校验失败统一降级
        logger.warning("意图分析 JSON 解析失败: %.120s (%s)", raw, exc)
        return QueryAnalysis()


def format_info(info: AnalysisInfo) -> str:
    """把必要信息格式化为 prompt 可读文本（只含非空字段）。"""
    labels = {
        "body_shape": "体型",
        "skin_tone": "肤色",
        "face_shape": "脸型",
        "current_outfit": "当前穿着",
        "occasion_hint": "场合线索",
    }
    parts = [f"{labels[k]}：{v}" for k, v in info.model_dump().items() if v]
    return "；".join(parts)


async def analyze_with_image(images: list[str], message: str) -> QueryAnalysis:
    """有图路径：千问多模态一次调用（意图+维度+照片类型+信息）。异常 → 默认值。"""
    model = ModelRepository.get_qianwen_vl()
    content: list[dict] = [
        {"type": "image_url", "image_url": {"url": url}} for url in images
    ]
    content.append({"type": "text", "text": message or ""})
    messages = [
        SystemMessage(content=_ANALYSIS_PROMPT),
        HumanMessage(content=content),
    ]
    try:
        resp = await model.ainvoke(messages)
        return parse_analysis(resp.content)
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.warning("多模态意图分析失败（降级默认值）: %s", exc)
        return QueryAnalysis()


async def query_analyzer(state: OutfitState) -> OutfitState:
    """工作流入口节点：意图（5 类）+ 维度 + 照片类型 + 必要信息 → 写入 state。"""
    images = state.get("images") or []
    message = (state.get("description") or "").strip()
    if images:
        analysis = await analyze_with_image(images, message)
    else:
        analysis = analyze_text(message)
    return {
        "intent": "recommend" if analysis.intent != "chat" else "chat",
        "intent_detail": analysis.intent,
        "dimension": analysis.dimension,
        "photo_type": analysis.photo_type,
        "analysis": format_info(analysis.info),
    }
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test/test_query_analyzer.py -v
```

Expected: 全绿（8 + 12 = 20）。

- [ ] **Step 5: 提交**

```bash
git add app/graph/nodes/query_analyzer.py test/test_query_analyzer.py
git commit -m "feat: multimodal intent analysis node (intent/dimension/photo_type/info, fail-open)"
```

---

### Task 3: state/workflow 接入 + 契约映射 + 老节点退役

**Files:**
- Modify: `app/graph/state.py`
- Modify: `app/graph/workflow.py`
- Modify: `app/graph/nodes/__init__.py`
- Modify: `app/graph/nodes/recommend_outfit.py`
- Delete: `app/graph/nodes/analyze_appearance.py`、`app/graph/nodes/intent_router.py`
- Modify: `test/test_agent_contract.py`

**Interfaces:**
- Consumes: Task 2 的 `query_analyzer` 节点
- Produces: 新工作流（query_analyzer → recommend_outfit / chat_reply）；`state["intent"]`（recommend|chat）+ `intent_detail`/`dimension`/`photo_type`/`analysis`；`recommend_outfit` 读 `analysis`

- [ ] **Step 1: state.py 新增字段**

在 `OutfitState` 的 `appearance` 行附近新增（`appearance` 字段一并删除，改由 `analysis` 承担）：

```python
        intent_detail: 内部意图（"outfit"|"match"|"style"|"color"|"chat"），供检索路由。
        dimension: 消息主题所在知识维度（9 大维度或 "general"）。
        photo_type: 照片类型（"full_body"|"half_body"|"head_shot"|"unknown"）。
        analysis: 形象/必要信息文本（替代原 appearance，供推荐节点 prompt 使用）。
```

字段声明区把 `appearance: str` 替换为：

```python
    intent_detail: str
    dimension: str
    photo_type: str
    analysis: str
```

- [ ] **Step 2: workflow.py 重接图**

```python
"""穿搭推荐工作流的图定义与编译。

流程：START → query_analyzer（意图/维度/照片类型/信息提取）
  - recommend（outfit/match/style/color）→ recommend_outfit
  - chat → chat_reply
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    chat_reply,
    query_analyzer,
    recommend_outfit,
)
from app.graph.state import OutfitState


def _route_by_intent(state: OutfitState) -> str:
    """根据映射后的意图选择分支（对外契约 recommend|chat）。"""
    return "recommend" if state.get("intent") == "recommend" else "chat"


@lru_cache(maxsize=1)
def get_workflow():
    """构建并编译穿搭推荐工作流图。"""
    graph = StateGraph(OutfitState)

    graph.add_node("query_analyzer", query_analyzer)
    graph.add_node("recommend_outfit", recommend_outfit)
    graph.add_node("chat_reply", chat_reply)

    graph.add_edge(START, "query_analyzer")
    graph.add_conditional_edges(
        "query_analyzer",
        _route_by_intent,
        {
            "recommend": "recommend_outfit",
            "chat": "chat_reply",
        },
    )
    graph.add_edge("recommend_outfit", END)
    graph.add_edge("chat_reply", END)

    return graph.compile()
```

`run_recommendation` / `run_chat` 保持不变（`result["suggestion"]`、`result.get("intent")` 现在读映射后的 `intent`）。

- [ ] **Step 3: nodes/__init__.py 调整导出**

```python
"""节点模块：各个工作流节点的实现。"""
from app.graph.nodes.chat_reply import chat_reply
from app.graph.nodes.query_analyzer import query_analyzer
from app.graph.nodes.recommend_outfit import recommend_outfit

__all__ = [
    "chat_reply",
    "query_analyzer",
    "recommend_outfit",
]
```

- [ ] **Step 4: 删除旧节点**

```powershell
Remove-Item app/graph/nodes/analyze_appearance.py, app/graph/nodes/intent_router.py
```

- [ ] **Step 5: recommend_outfit.py 改读 analysis**

`RECOMMEND_PROMPT` 中「【体征分析】」字样改为「【形象分析】」；节点函数内：

```python
    appearance = (state.get("appearance") or "").strip()
```
改为：
```python
    analysis = (state.get("analysis") or "").strip()
```

`user_message` 组装处：

```python
    user_message = f"【形象分析】\n{analysis or '（无，用户未上传照片或未提取到信息）'}\n\n【用户需求】\n{user_need}\n\n"
```

- [ ] **Step 6: test_agent_contract.py 更新 fixture 与意图语义**

`client` fixture 中 `get_qianwen_vl` 的 mock 返回值改为合法分析 JSON：

```python
    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(
        lambda: FakeModel('{"intent": "outfit", "dimension": "场合与季节", "photo_type": "full_body", "info": {}}')))
```

`FakeModel` 构造改为接受文本（原 `__init__(self, text)` 已支持，无需改）。

`test_images_force_recommend` 改为模型判定语义（fake 返回 outfit → recommend，断言不变）；
另新增一条：fake 返回 chat 意图时，带图消息也走 chat：

```python
def test_image_with_chat_intent_goes_chat(client, monkeypatch):
    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(
        lambda: FakeModel('{"intent": "chat", "dimension": "general", "photo_type": "unknown", "info": {}}')))
    resp = client.post("/api/agent/chat", json={
        "message": "这张图好看吗",
        "images": ["data:image/png;base64,AAAA"],
        "history": [],
    })
    assert resp.status_code == 200
    assert resp.json()["intent"] == "chat"
```

- [ ] **Step 7: 跑测试确认通过（含契约回归）**

```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test/test_query_analyzer.py test/test_agent_contract.py -v
```

Expected: 全绿（20 + 10）。

- [ ] **Step 8: 提交**

```bash
git add app/graph/state.py app/graph/workflow.py app/graph/nodes/__init__.py app/graph/nodes/recommend_outfit.py test/test_agent_contract.py
git rm app/graph/nodes/analyze_appearance.py app/graph/nodes/intent_router.py
git commit -m "refactor: wire query_analyzer into workflow, retire intent_router/analyze_appearance"
```

---

### Task 4: 全量回归 + 文档

**Files:**
- Modify: `docs/项目开发指南.md`、`CHANGELOG.md`

- [ ] **Step 1: 全量回归**

```powershell
D:\code\i-clothes\.conda\python.exe -m pytest test -v --ignore=test/test_workflow.py
```

Expected: 全部通过（test_agent_contract + test_query_analyzer + test_knowledge_import 等；`test_workflow.py` 是手动冒烟，pytest 不收集）。

- [ ] **Step 2: 项目开发指南更新**

- §2 目录结构：`app/graph/nodes/` 列表把 `intent_router.py`/`analyze_appearance.py` 换成 `query_analyzer.py`
  （标注：意图 5 类 + 知识维度 + 照片类型 + 必要信息提取；有图千问多模态、无图关键词）
- §3 一次消息旅程：第 5 步改为「query_analyzer 判定意图（穿搭/搭配/风格/颜色/闲聊）+ 维度 + 照片类型」
- §5 表格：`| 意图路由关键词 | app/graph/nodes/query_analyzer.py 的 INTENT_KEYWORDS / DIMENSION_KEYWORDS | 跑 query_analyzer 单测 |`

- [ ] **Step 3: CHANGELOG 追加（[Unreleased] 段）**

```markdown
### Added
- 意图分析节点 `app/graph/nodes/query_analyzer.py`：对每条消息输出 intent（outfit/match/style/color/chat）
  + dimension（9 大知识维度 + general，闲聊也归类）+ photo_type（全身/半身/大头/unknown）
  + 必要信息（体型/肤色/脸型/当前穿着/场合）；有图走千问多模态一次调用（Pydantic 校验、fail-open），
  无图走关键词规则（零成本）

### Changed
- `intent_router.py`（关键词 recommend|chat 二分类）与 `analyze_appearance.py` 合并进
  `query_analyzer.py`（对外契约不变：响应 intent 仍为 recommend|chat，前端零改动）
```

- [ ] **Step 4: 提交**

```bash
git add docs/项目开发指南.md CHANGELOG.md
git commit -m "docs: intent analysis node guide and changelog"
```

---

## Self-Review 记录

**Spec 覆盖核对：**
- §3 输出模型 → Task 1（QueryAnalysis/AnalysisInfo）✓
- §4.1 无图关键词 → Task 1（INTENT_KEYWORDS/DIMENSION_KEYWORDS/analyze_text）✓
- §4.2 有图多模态一次调用 → Task 2（analyze_with_image + _ANALYSIS_PROMPT）✓
- §4.3 fail-open → Task 2（parse_analysis/analyze_with_image 降级）✓
- §5 状态与工作流（intent_detail/dimension/photo_type/analysis、intent 映射、analyze_appearance 删除、recommend_outfit 改读 analysis）→ Task 3 ✓
- §6 测试（关键词路由、解析 fail-open、契约回归 fixture 更新）→ Task 1/2/3 ✓
- §7 里程碑 → Task 1-4 ✓
- D5 对外契约不变 → Task 3（state["intent"] 映射 + agent.py 零改动 + 前端零改动）✓

**占位符扫描：** 无 TBD/TODO；每步含完整代码/命令。

**类型一致性：**
- `analyze_text(message) -> QueryAnalysis` 在 Task 1 定义，Task 2 `query_analyzer` 调用 ✓
- `parse_analysis(raw) -> QueryAnalysis`、`format_info(info) -> str` 在 Task 2 定义并测试 ✓
- `query_analyzer(state) -> OutfitState` 返回键 `intent/intent_detail/dimension/photo_type/analysis` 与 Task 3 state 字段一致 ✓
- `analysis` 字段在 Task 3 替换 `appearance`，`recommend_outfit` 同步改读 ✓
- 关键词表用例与测试断言逐字对应（场合与季节/肤色与个人色彩优先级已钉死）✓

**跨任务冲突预查：**
- Task 1 创建 query_analyzer.py，Task 2 追加同文件（无冲突，追加式）✓
- Task 3 删除 intent_router.py/analyze_appearance.py——无其他文件引用（workflow/__init__ 同任务内改）✓
- `test_agent_contract.py` 的「有图必推荐」语义改为「模型判定」——fixture 与用例同任务更新 ✓
- `run_recommendation`（test_workflow.py 手动冒烟用）仍读 `result["suggestion"]`——query_analyzer 不写 suggestion，recommend_outfit 写，兼容 ✓

## Execution Handoff

计划已保存至 `docs/superpowers/plans/2026-08-28-intent-analysis.md`。执行方式：本会话内联 TDD 执行（用户已确认「开始实施」，任务 1→4 顺序推进，每任务 RED→GREEN→提交）。
