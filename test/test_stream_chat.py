"""流式输出单测：stream_chat 生成器逻辑 + SSE 端点契约（mock 工作流/生成器，不触网）。"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.api.routers import agent as agent_router  # noqa: E402
from app.graph import workflow  # noqa: E402


def _chunk(text: str):
    return SimpleNamespace(content=text)


# ---------------------------------------------------------------------------
# stream_chat 生成器（mock workflow.astream 产出脚本化序列）
# ---------------------------------------------------------------------------

class FakeWF:
    """按 stream_mode=['messages','updates'] 的 (mode, payload) 形状产出。"""

    def __init__(self, sequence):
        self._seq = sequence

    async def astream(self, inputs, stream_mode=None):
        for item in self._seq:
            yield item


def _messages_sequence():
    """正常序列：query_analyzer 内部 token（应被跳过）+ chat_reply token + intent 更新。"""
    return [
        ("messages", (_chunk("（内部检索中）"), {"langgraph_node": "query_analyzer"})),
        ("messages", (_chunk("你"), {"langgraph_node": "chat_reply"})),
        ("updates", {"query_analyzer": {"intent": "recommend", "intent_detail": "outfit"}}),
        ("messages", (_chunk("好"), {"langgraph_node": "chat_reply"})),
        ("messages", (_chunk("！"), {"langgraph_node": "recommend_outfit"})),
    ]


def test_stream_chat_yields_generation_tokens_only(monkeypatch):
    monkeypatch.setattr(workflow, "get_workflow", lambda: FakeWF(_messages_sequence()))

    got = []
    async def collect():
        async for delta, intent in workflow.stream_chat("你好", [], []):
            got.append((delta, intent))

    asyncio.run(collect())
    deltas = [d for d, _ in got if d]
    assert deltas == ["你", "好", "！"]           # 只转发生成节点 token
    assert [i for _, i in got if i is not None] == ["recommend"]  # intent 只在末尾给出
    assert got[-1] == ("", "recommend")           # 结束信号


def test_stream_chat_ends_with_intent(monkeypatch):
    seq = _messages_sequence() + [("updates", {"query_analyzer": {"intent": "chat"}})]
    monkeypatch.setattr(workflow, "get_workflow", lambda: FakeWF(seq))

    got = []
    async def collect():
        async for delta, intent in workflow.stream_chat("你好", [], []):
            got.append((delta, intent))

    asyncio.run(collect())
    assert got[-1] == ("", "chat")              # 生成器末尾 yield ("", intent)


def test_stream_chat_defaults_intent_chat(monkeypatch):
    # 无 query_analyzer 更新时兜底 chat
    seq = [("messages", (_chunk("嗯"), {"langgraph_node": "chat_reply"}))]
    monkeypatch.setattr(workflow, "get_workflow", lambda: FakeWF(seq))

    got = []
    async def collect():
        async for delta, intent in workflow.stream_chat("嗯", [], []):
            got.append((delta, intent))

    asyncio.run(collect())
    assert got[-1] == ("", "chat")


# ---------------------------------------------------------------------------
# /api/agent/chat/stream SSE 端点（mock stream_chat）
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    async def _fake_stream(message, images, history):
        for d in ["你", "好"]:
            yield d, None
        yield "", "recommend"

    monkeypatch.setattr(agent_router, "stream_chat", _fake_stream)
    app = FastAPI()
    app.include_router(agent_router.router)
    return TestClient(app)


def test_stream_endpoint_sse_events(client):
    with client.stream("POST", "/api/agent/chat/stream", json={
        "message": "帮我推荐穿搭", "images": [], "history": [],
    }) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    events = [line[6:] for line in body.splitlines() if line.startswith("data: ")]
    assert json.loads(events[0]) == {"delta": "你"}
    assert json.loads(events[1]) == {"delta": "好"}
    assert json.loads(events[2]) == {"done": True, "intent": "recommend"}


def test_stream_endpoint_error_event(monkeypatch):
    async def _boom(message, images, history):
        yield "部", None
        raise RuntimeError("LLM 超时")

    monkeypatch.setattr(agent_router, "stream_chat", _boom)
    app = FastAPI()
    app.include_router(agent_router.router)
    client = TestClient(app)

    with client.stream("POST", "/api/agent/chat/stream", json={
        "message": "你好", "images": [], "history": [],
    }) as resp:
        body = "".join(resp.iter_text())
    events = [line[6:] for line in body.splitlines() if line.startswith("data: ")]
    assert json.loads(events[0]) == {"delta": "部"}
    assert "error" in json.loads(events[1])


def test_stream_endpoint_validation_400(client):
    resp = client.post("/api/agent/chat/stream", json={
        "message": "", "images": [], "history": [],
    })
    assert resp.status_code == 400
    assert resp.json()["detail"] == "消息内容不能为空"
