"""聊天业务服务：意图路由 → 工作流执行 → 会话落库。"""
from app.graph.workflow import run_chat
from app.services.conversation_store import Conversation, Message, store

# 新会话的默认标题；首条用户消息会自动作为标题
DEFAULT_TITLE = "新对话"
TITLE_MAX_LEN = 20
# 传给模型的上下文轮数
CONTEXT_TURNS = 10


async def handle_message(
    conversation_id: str | None,
    message: str,
    images: list[str],
) -> dict:
    """处理一条用户消息，返回回复与意图。

    Args:
        conversation_id: 已有会话 id；None 时自动新建会话。
        message: 用户文本（可为空，但文本与图片不能同时为空，由接口层校验）。
        images: 本轮图片 data URL 列表。

    Returns:
        {"conversation_id", "reply", "intent", "title"}
    """
    conv: Conversation | None = await store.get(conversation_id) if conversation_id else None
    if conv is None:
        conv = await store.create(DEFAULT_TITLE)

    # 构造历史上下文（不含本轮）
    history = [
        {"role": m.role, "content": m.content}
        for m in conv.messages[-CONTEXT_TURNS * 2:]
    ]

    result = await run_chat(message, images, history)

    # 落库：用户消息 + 助手回复
    await store.append_message(
        conv.id, Message(role="user", content=message, images=images)
    )
    await store.append_message(
        conv.id,
        Message(role="assistant", content=result["reply"], intent=result["intent"]),
    )

    # 自动起标题：新会话用首条用户消息
    if conv.title == DEFAULT_TITLE and message.strip():
        title = message.strip().replace("\n", " ")
        await store.set_title(conv.id, title[:TITLE_MAX_LEN])

    return {
        "conversation_id": conv.id,
        "reply": result["reply"],
        "intent": result["intent"],
        "title": conv.title,
    }
