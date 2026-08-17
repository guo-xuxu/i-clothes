"""闲聊节点：调用 DeepSeek 进行多轮对话。"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph.state import OutfitState
from app.repositories.model_repo import ModelRepository

CHAT_SYSTEM_PROMPT = """你是 i-clothes 智能穿搭助手，一个友好、专业的时尚顾问。
你可以和用户轻松闲聊，也可以回答穿搭相关问题。
当用户明确想要穿搭建议时（如提到"推荐""搭配"等），建议引导用户：
- 可以上传照片获得更精准的个性化建议；
- 或直接给出基于文字描述的穿搭建议。

回答用中文，简洁自然，不要过于冗长。"""

# 最多携带的上下文消息条数（不含本轮）
MAX_CONTEXT = 10


async def chat_reply(state: OutfitState) -> OutfitState:
    """基于会话历史生成闲聊回复。"""
    history = state.get("messages") or []

    messages: list = [SystemMessage(content=CHAT_SYSTEM_PROMPT)]
    for m in history[-MAX_CONTEXT:]:
        if m.get("role") == "user":
            messages.append(HumanMessage(content=m.get("content") or ""))
        elif m.get("role") == "assistant":
            messages.append(AIMessage(content=m.get("content") or ""))
    messages.append(HumanMessage(content=state.get("description") or ""))

    model = ModelRepository.get_deepseek()
    response = await model.ainvoke(messages)
    return {"suggestion": response.content}
