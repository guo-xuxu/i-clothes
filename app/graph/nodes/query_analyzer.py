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
