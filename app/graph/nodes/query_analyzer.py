"""意图分析节点：对每条消息产出 intent/dimension/photo_type/必要信息。

- 无图：关键词规则（analyze_text，零成本）；
- 有图：千问多模态一次调用（analyze_with_image，结构化 JSON + Pydantic 校验，fail-open）。
对外契约不变：state["intent"] 仍是 recommend|chat（由 intent_detail 映射）。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.graph.state import OutfitState
from app.repositories.model_repo import ModelRepository

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.S)

# ---------------------------------------------------------------------------
# 意图关键词（dict 顺序即优先级；无命中 → chat）
# ---------------------------------------------------------------------------
INTENT_KEYWORDS: dict[str, list[str]] = {
    "outfit": ["推荐", "穿搭", "怎么穿", "穿什么", "穿啥", "衣服", "着装", "穿着", "look"],
    "match": ["搭配", "配什么", "怎么配", "怎么搭", "配饰", "混搭", "搭什么", "组合"],
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
    """工作流入口节点：意图（5 类）+ 维度 + 照片类型 + 必要信息 → 写入 state。

    对外契约映射（spec D5）：intent_detail ∈ {outfit, match, style, color} → intent="recommend"；
    chat → "chat"。
    """
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
