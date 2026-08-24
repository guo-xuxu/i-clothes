"""穿搭推荐工作流的图定义与编译。

流程：START → intent_router（意图路由）
  - recommend + 有图：analyze_appearance → recommend_outfit
  - recommend + 无图：recommend_outfit（纯文字推荐，跳过体征分析）
  - chat：chat_reply（多轮闲聊）
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    analyze_appearance,
    chat_reply,
    intent_router,
    recommend_outfit,
)
from app.graph.state import OutfitState


def _route_by_intent(state: OutfitState) -> str:
    """根据意图路由结果选择分支。"""
    if state.get("intent") == "recommend":
        return "recommend_with_images" if state.get("images") else "recommend_no_images"
    return "chat"


@lru_cache(maxsize=1)
def get_workflow():
    """构建并编译穿搭推荐工作流图。"""
    graph = StateGraph(OutfitState)

    graph.add_node("intent_router", intent_router)
    graph.add_node("analyze_appearance", analyze_appearance)
    graph.add_node("recommend_outfit", recommend_outfit)
    graph.add_node("chat_reply", chat_reply)

    graph.add_edge(START, "intent_router")
    graph.add_conditional_edges(
        "intent_router",
        _route_by_intent,
        {
            "recommend_with_images": "analyze_appearance",
            "recommend_no_images": "recommend_outfit",
            "chat": "chat_reply",
        },
    )
    graph.add_edge("analyze_appearance", "recommend_outfit")
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
