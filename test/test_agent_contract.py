"""Agent 服务契约测试：mock 掉 LLM，验证请求/响应/错误格式。"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.api.routers import agent  # noqa: E402
from app.knowledge.retrieve import retriever as knowledge_retriever  # noqa: E402
from app.repositories.model_repo import ModelRepository  # noqa: E402


class FakeModel:
    """假的 ChatOpenAI 替身：ainvoke 返回固定文本。"""

    def __init__(self, text: str) -> None:
        self._text = text

    async def ainvoke(self, messages):
        return SimpleNamespace(content=self._text)


@pytest.fixture
def client(monkeypatch):
    # query_analyzer：无图走关键词规则，有图走千问多模态（fake 返回合法分析 JSON）
    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: FakeModel("助手回复")))
    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(
        lambda: FakeModel('{"intent": "outfit", "dimension": "场合与季节", "photo_type": "full_body", "info": {}}')))
    # 在线召回不触真实图谱/embedding：mock 为空上下文
    async def _no_retrieve(**kwargs):
        return ""

    monkeypatch.setattr(knowledge_retriever, "retrieve", _no_retrieve)
    app = FastAPI()
    app.include_router(agent.router)
    return TestClient(app)


def test_chat_intent(client):
    resp = client.post("/api/agent/chat", json={
        "message": "你好，介绍一下你自己",
        "images": [],
        "history": [],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "助手回复"
    assert body["intent"] == "chat"


def test_recommend_intent_without_images(client):
    resp = client.post("/api/agent/chat", json={
        "message": "帮我推荐上班通勤的穿搭",
        "images": [],
        "history": [],
    })
    assert resp.status_code == 200
    assert resp.json()["intent"] == "recommend"


def test_images_force_recommend(client):
    # 有图走多模态判定：fixture 的 fake 千问返回 outfit → recommend
    resp = client.post("/api/agent/chat", json={
        "message": "随便聊聊",
        "images": ["data:image/png;base64,AAAA"],
        "history": [],
    })
    assert resp.status_code == 200
    assert resp.json()["intent"] == "recommend"


def test_image_with_chat_intent_goes_chat(client, monkeypatch):
    # 模型判定为闲聊（即使有图）→ 对外契约 chat
    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(
        lambda: FakeModel('{"intent": "chat", "dimension": "general", "photo_type": "unknown", "info": {}}')))
    resp = client.post("/api/agent/chat", json={
        "message": "这张图好看吗",
        "images": ["data:image/png;base64,AAAA"],
        "history": [],
    })
    assert resp.status_code == 200
    assert resp.json()["intent"] == "chat"


def test_history_context_passed(client):
    history = [
        {"role": "user", "content": "之前的话题"},
        {"role": "assistant", "content": "好的"},
    ]
    resp = client.post("/api/agent/chat", json={
        "message": "继续",
        "images": [],
        "history": history,
    })
    assert resp.status_code == 200


def test_empty_message_rejected(client):
    resp = client.post("/api/agent/chat", json={"message": "", "images": [], "history": []})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "消息内容不能为空"


def test_bad_image_format_rejected(client):
    resp = client.post("/api/agent/chat", json={
        "message": "hi", "images": ["data:image/gif;base64,AAAA"], "history": [],
    })
    assert resp.status_code == 400
    assert resp.json()["detail"] == "不支持的图片格式，仅支持 JPG/PNG"


def test_missing_key_returns_502(client, monkeypatch):
    def raise_missing(*args, **kwargs):
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(raise_missing))
    resp = client.post("/api/agent/chat", json={"message": "你好", "images": [], "history": []})
    assert resp.status_code == 502
    assert "未配置" in resp.json()["detail"]


def test_provider_api_error_returns_502(client, monkeypatch):
    """LLM 提供方异常（openai APIError，非 RuntimeError）→ 502 而非 500（spec §4.1）。"""

    class FailingModel:
        async def ainvoke(self, messages):
            from openai import APIError

            raise APIError("provider upstream returned an error", request=None, body=None)

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: FailingModel()))
    resp = client.post("/api/agent/chat", json={"message": "你好", "images": [], "history": []})
    assert resp.status_code == 502
    assert "provider" in resp.json()["detail"]


def test_non_llm_error_not_masked_as_502(monkeypatch):
    """评审 I2 收窄：编码类异常（ValueError 等非 LLM 提供方）不再被 502 掩盖，
    由 FastAPI 兜底为 500（raise_server_exceptions=False 下观测 wire 行为）。"""

    class BoomModel:
        async def ainvoke(self, messages):
            raise ValueError("编码错误：结果缺键")

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: BoomModel()))
    app = FastAPI()
    app.include_router(agent.router)
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/agent/chat", json={"message": "你好", "images": [], "history": []}
    )
    assert resp.status_code == 500
    # FastAPI 兜底 500 不应泄露内部异常细节
    assert "编码错误" not in resp.text

