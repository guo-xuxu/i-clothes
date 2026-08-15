"""穿搭推荐工作流的共享状态定义。"""
from typing import TypedDict


class OutfitState(TypedDict, total=False):
    """在工作流节点间传递的状态。

    Attributes:
        images: (data URL, ) 形式的图片列表，供多模态模型使用。
        description: 用户可选的文字说明。
        suggestion: 最终生成的穿搭建议文本。
    """

    images: list[str]
    description: str
    appearance: str
    suggestion: str
