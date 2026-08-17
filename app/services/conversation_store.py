"""进程内会话存储（MVP 方案：服务重启后丢失）。

后续接入正式数据库（用户体系 P2）时，将本模块替换为 repository 实现，
接口层与前端无需改动。
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

# 单会话保留的最大消息条数（超出丢弃最早的）
MAX_HISTORY = 50
# 会话列表里显示的预览长度
PREVIEW_LEN = 30


@dataclass
class Message:
    """一条对话消息。"""

    role: str  # "user" | "assistant"
    content: str
    intent: str = ""  # assistant 消息专用：本次回复的路由意图（recommend/chat）
    images: list[str] = field(default_factory=list)  # user 消息专用：本轮图片 data URL
    created_at: float = field(default_factory=time.time)


@dataclass
class Conversation:
    """一个多轮会话。"""

    id: str
    title: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: list[Message] = field(default_factory=list)


class ConversationStore:
    """进程内会话表，线程安全。"""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._lock = asyncio.Lock()

    async def create(self, title: str = "新对话") -> Conversation:
        conv = Conversation(id=uuid.uuid4().hex, title=title)
        async with self._lock:
            self._conversations[conv.id] = conv
        return conv

    async def get(self, conversation_id: str) -> Optional[Conversation]:
        async with self._lock:
            return self._conversations.get(conversation_id)

    async def delete(self, conversation_id: str) -> bool:
        async with self._lock:
            return self._conversations.pop(conversation_id, None) is not None

    async def list_summaries(self) -> list[dict]:
        """按更新时间倒序返回会话摘要（供侧边栏）。"""
        async with self._lock:
            convs = sorted(
                self._conversations.values(),
                key=lambda c: c.updated_at,
                reverse=True,
            )
        result = []
        for c in convs:
            preview = ""
            if c.messages:
                last = c.messages[-1]
                preview = last.content.strip().replace("\n", " ")
                if len(preview) > PREVIEW_LEN:
                    preview = preview[:PREVIEW_LEN] + "…"
            result.append({
                "id": c.id,
                "title": c.title,
                "preview": preview,
                "updated_at": c.updated_at,
            })
        return result

    async def append_message(
        self, conversation_id: str, message: Message
    ) -> Optional[Conversation]:
        """追加一条消息，更新时间戳并裁剪历史。"""
        async with self._lock:
            conv = self._conversations.get(conversation_id)
            if conv is None:
                return None
            conv.messages.append(message)
            if len(conv.messages) > MAX_HISTORY:
                conv.messages = conv.messages[-MAX_HISTORY:]
            conv.updated_at = time.time()
            return conv

    async def set_title(self, conversation_id: str, title: str) -> None:
        async with self._lock:
            conv = self._conversations.get(conversation_id)
            if conv is not None:
                conv.title = title


store = ConversationStore()
