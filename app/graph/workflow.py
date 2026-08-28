"""穿搭推荐工作流的图定义与编译。

流程：START → query_analyzer（意图/维度/照片类型/信息提取）
  → query_rewriter（查询改写，chat 透传）
  - recommend（outfit/match/style/color）→ recommend_outfit
  - chat → chat_reply
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    chat_reply,
    query_analyzer,
    query_rewriter,
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
    graph.add_node("query_rewriter", query_rewriter)
    graph.add_node("recommend_outfit", recommend_outfit)
    graph.add_node("chat_reply", chat_reply)

    graph.add_edge(START, "query_analyzer")
    graph.add_edge("query_analyzer", "query_rewriter")
    graph.add_conditional_edges(
        "query_rewriter",
        _route_by_intent,
        {
            "recommend": "recommend_outfit",
            "chat": "chat_reply",
        },
    )
    graph.add_edge("recommend_outfit", END)
    graph.add_edge("chat_reply", END)

    return graph.compile()


async def run_recommendation(images: list[str], description: str = "") -> str:
    """执行工作流，返回回复文本（兼容测试与旧接口）。

    Args:
        images: data URL 形式的图片列表。
        description: 可选文字说明。

    Returns:
        回复文本（穿搭建议或闲聊回复）。
    """
    workflow = get_workflow()
    result = await workflow.ainvoke(
        {"images": images, "description": description, "messages": []}
    )
    return result["suggestion"]


async def run_chat(
    message: str, images: list[str], history: list[dict]
) -> dict:
    """执行工作流，返回回复与意图。

    Args:
        message: 用户本轮文字。
        images: 本轮图片 data URL 列表。
        history: 会话历史 [{"role", "content"}, ...]，不含本轮。

    Returns:
        {"reply": str, "intent": "recommend" | "chat"}
    """
    workflow = get_workflow()
    result = await workflow.ainvoke(
        {"images": images, "description": message, "messages": history}
    )
    return {
        "reply": result["suggestion"],
        "intent": result.get("intent", "chat"),
    }
