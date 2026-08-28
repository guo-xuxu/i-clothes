"""穿搭推荐工作流的共享状态定义。"""
from typing import TypedDict


class OutfitState(TypedDict, total=False):
    """在工作流节点间传递的状态。

    Attributes:
        images: data URL 形式的图片列表，供多模态模型使用。
        description: 用户本轮的文字输入。
        messages: 会话历史 [{"role": "user"|"assistant", "content": str}, ...]，
            不含本轮，供多轮上下文使用。
        intent: 对外意图映射（"recommend" | "chat"，契约不变）。
        intent_detail: 内部意图（"outfit"|"match"|"style"|"color"|"chat"），供检索路由。
        dimension: 消息主题所在知识维度（9 大维度或 "general"，闲聊也归类）。
        photo_type: 照片类型（"full_body"|"half_body"|"head_shot"|"unknown"）。
        analysis: 形象/必要信息文本（体型/肤色/脸型/当前穿着/场合线索，供推荐节点 prompt）。
        rewritten_query: 改写后的检索查询（LLM 改写，供检索节点消费；chat 原样透传）。
        rewrite_keywords: 改写提取的关键检索词列表。
        suggestion: 最终回复文本（推荐建议或闲聊回复）。
    """

    images: list[str]
    description: str
    messages: list[dict]
    intent: str
    intent_detail: str
    dimension: str
    photo_type: str
    analysis: str
    rewritten_query: str
    rewrite_keywords: list[str]
    suggestion: str
