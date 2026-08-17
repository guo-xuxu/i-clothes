"""穿搭推荐业务服务。

当前是工作流的薄封装，后续在此扩展用例编排：
如查询向量库相似风格、经用户仓库保存历史记录等。
"""
from app.graph.workflow import run_recommendation


async def recommend(images: list[str], description: str = "") -> str:
    """执行穿搭推荐工作流，返回建议文本。

    Args:
        images: data URL 形式的图片列表。
        description: 可选文字说明。

    Returns:
        穿搭建议文本。
    """
    return await run_recommendation(images, description)
