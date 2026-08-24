"""意图路由节点：判断用户是要穿搭推荐还是正常闲聊。

MVP 采用纯关键词规则（零成本零延迟）。
误判时用户换个说法即可；后续可升级为 LLM 判断 + 关键词兜底。
"""
from app.graph.state import OutfitState

# 推荐意图关键词（优先匹配）
RECOMMEND_KEYWORDS = [
    "推荐", "搭配", "穿搭", "穿什么", "怎么穿", "着装", "风格", "色系", "场合",
    "婚礼", "约会", "通勤", "面试", "聚会", "派对", "出差", "旅游", "上班",
    "出席", "外套", "裤子", "裙子", "鞋子", "上衣", "下装", "配饰", "套装",
    "单品", "衣服", "穿着", "适合", "好看", "显瘦", "look",
]

# 闲聊意图关键词
CHAT_KEYWORDS = ["闲聊", "你是谁", "你会什么", "介绍一下你", "帮助", "help"]


def _latest_user_text(state: OutfitState) -> str:
    """取本轮文字；为空时回退到历史上最近一条用户消息。"""
    text = (state.get("description") or "").strip()
    if text:
        return text
    for m in reversed(state.get("messages") or []):
        if m.get("role") == "user":
            return (m.get("content") or "").strip()
    return ""


def intent_router(state: OutfitState) -> OutfitState:
    """按关键词规则返回意图："recommend" | "chat"。"""
    # 有图片一律视为推荐意图
    if state.get("images"):
        return {"intent": "recommend"}

    text = _latest_user_text(state).lower()
    if not text:
        return {"intent": "chat"}

    for kw in RECOMMEND_KEYWORDS:
        if kw in text:
            return {"intent": "recommend"}
    for kw in CHAT_KEYWORDS:
        if kw in text:
            return {"intent": "chat"}
    return {"intent": "chat"}
