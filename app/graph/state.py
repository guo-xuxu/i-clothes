"""穿搭推荐工作流的共享状态定义。"""
from typing import TypedDict


class OutfitState(TypedDict, total=False):
    """在工作流节点间传递的状态。

    Attributes:
        images: data URL 形式的图片列表，供多模态模型使用。
        description: 用户本轮的文字输入。
        messages: 会话历史 [{"role": "user"|"assistant", "content": str}, ...]，
            不含本轮，供多轮上下文使用。
        intent: 意图路由结果（"recommend" | "chat"）。
        appearance: 体征分析结果。
        suggestion: 最终回复文本（推荐建议或闲聊回复）。
    """

    images: list[str]
    description: str
    messages: list[dict]
    intent: str
    appearance: str
    suggestion: str
