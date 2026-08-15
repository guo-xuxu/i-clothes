"""穿搭推荐工作流的图定义与编译。

当前 MVP 只有一个节点（analyze_scene）。后续版本可在此扩展：
identify_items（DeepSeek 识别单品）、generate_outfit（生图）等节点，
通过 add_node / add_edge 串联即可，无需改动调用方。
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import analyze_appearance, recommend_outfit
from app.graph.state import OutfitState


@lru_cache(maxsize=1)
def get_workflow():
    """构建并编译穿搭推荐工作流图。"""
    graph = StateGraph(OutfitState)

    graph.add_node("analyze_appearance", analyze_appearance)
    graph.add_node("recommend_outfit", recommend_outfit)

    graph.add_edge(START, "analyze_appearance")
    graph.add_edge("analyze_appearance", "recommend_outfit")
    graph.add_edge("recommend_outfit", END)

    return graph.compile()


async def run_recommendation(images: list[str], description: str = "") -> str:
    """执行工作流，返回穿搭建议文本。

    Args:
        images: data URL 形式的图片列表。
        description: 可选文字说明。

    Returns:
        穿搭建议文本。
    """
    workflow = get_workflow()
    result = await workflow.ainvoke(
        {"images": images, "description": description}
    )
    return result["suggestion"]
