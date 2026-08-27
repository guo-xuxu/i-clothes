"""知识库入库接口测试：mock service 层与 import_all，验证触发/状态/单飞契约。

原则：不调用真实 import_all（不调 LLM、不写 Chroma/graph.json/登记表/同义词典），
只测「路由 → service」的接口行为与 service 的状态机。
"""
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.api.routers import knowledge as knowledge_router  # noqa: E402
from app.knowledge import service as knowledge_service  # noqa: E402

FAKE_STATS = {
    "processed": 1, "skipped": 2, "failed": 0,
    "nodes": 10, "edges": 20, "entity_vectors": 10, "chunk_vectors": 3,
}


# ---------------------------------------------------------------------------
# 通用 fixture
# ---------------------------------------------------------------------------

def _fresh_app() -> TestClient:
    """独立 FastAPI 实例（不加载 main.py，避免拖入 Phoenix 等副作用）。"""
    app = FastAPI()
    app.include_router(knowledge_router.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    """每个用例前重置进程内构建状态（只动内存，不落盘）。"""
    knowledge_service._state = knowledge_service.BuildState()
    yield


def _wait_idle(timeout: float = 5.0) -> None:
    """等待后台线程把状态从 running 转出（mock 的 import_all 瞬时完成）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if knowledge_service._state.status != "running":
            return
        time.sleep(0.01)
    raise AssertionError("构建线程未在超时内结束")


# ---------------------------------------------------------------------------
# 路由契约测试（mock service 层，绝不执行真实入库）
# ---------------------------------------------------------------------------

def test_trigger_returns_started(monkeypatch):
    monkeypatch.setattr(knowledge_router, "trigger_build",
                        lambda paths=None: {"status": "started"})
    client = _fresh_app()
    resp = client.post("/api/knowledge/import", json={})
    assert resp.status_code == 200
    assert resp.json() == {"status": "started"}


def test_trigger_forwards_paths(monkeypatch):
    captured: dict = {}

    def fake(paths=None):
        captured["paths"] = paths
        return {"status": "started"}

    monkeypatch.setattr(knowledge_router, "trigger_build", fake)
    client = _fresh_app()
    paths = ["app/knowledge/docs/color/三色原则.md"]
    resp = client.post("/api/knowledge/import", json={"paths": paths})
    assert resp.status_code == 200
    assert captured["paths"] == paths


def test_trigger_conflict_409_when_running(monkeypatch):
    def fake(paths=None):
        raise knowledge_service.BuildAlreadyRunning()

    monkeypatch.setattr(knowledge_router, "trigger_build", fake)
    client = _fresh_app()
    resp = client.post("/api/knowledge/import", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "知识库构建正在进行中"


def test_trigger_invalid_paths_rejected():
    """paths 含非字符串元素 → 400（真实校验逻辑，无需 mock）。"""
    client = _fresh_app()
    resp = client.post("/api/knowledge/import", json={"paths": [123]})
    assert resp.status_code == 400
    assert "paths" in resp.json()["detail"]


def test_status_returns_snapshot(monkeypatch):
    monkeypatch.setattr(knowledge_router, "get_build_status",
                        lambda: {"status": "idle", "started_at": None,
                                 "finished_at": None, "last_stats": FAKE_STATS,
                                 "error": None})
    client = _fresh_app()
    resp = client.get("/api/knowledge/import/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "idle"
    assert body["last_stats"]["skipped"] == 2


# ---------------------------------------------------------------------------
# service 层测试（mock import_all，验证状态机与单飞）
# ---------------------------------------------------------------------------

def test_trigger_runs_import_and_marks_idle(monkeypatch):
    gate = threading.Event()

    def fake(paths=None):
        gate.wait(timeout=5)
        return FAKE_STATS

    monkeypatch.setattr(knowledge_service, "import_all", fake)

    resp = knowledge_service.trigger_build()
    assert resp == {"status": "started"}
    assert knowledge_service._state.status == "running"

    gate.set()
    _wait_idle()

    assert knowledge_service._state.status == "idle"
    assert knowledge_service._state.last_stats == FAKE_STATS
    assert knowledge_service._state.finished_at is not None


def test_trigger_forwards_paths_to_import(monkeypatch):
    captured: dict = {}

    def fake(paths=None):
        captured["paths"] = paths
        return FAKE_STATS

    monkeypatch.setattr(knowledge_service, "import_all", fake)

    paths = ["a.md", "b.md"]
    knowledge_service.trigger_build(paths)
    _wait_idle()
    assert captured["paths"] == paths


def test_single_flight_rejects_second_trigger(monkeypatch):
    gate = threading.Event()

    def slow(paths=None):
        gate.wait(timeout=5)
        return FAKE_STATS

    monkeypatch.setattr(knowledge_service, "import_all", slow)

    knowledge_service.trigger_build()
    with pytest.raises(knowledge_service.BuildAlreadyRunning):
        knowledge_service.trigger_build()

    gate.set()
    _wait_idle()
    assert knowledge_service._state.status == "idle"


def test_build_failure_marks_failed(monkeypatch):
    def boom(paths=None):
        raise RuntimeError("LLM 超时")

    monkeypatch.setattr(knowledge_service, "import_all", boom)

    knowledge_service.trigger_build()
    _wait_idle()

    assert knowledge_service._state.status == "failed"
    assert "LLM 超时" in knowledge_service._state.error
    assert knowledge_service._state.finished_at is not None


def test_status_snapshot_shape():
    knowledge_service._state.status = "running"
    knowledge_service._state.started_at = "2026-08-27T12:00:00"
    snap = knowledge_service.get_build_status()
    assert snap["status"] == "running"
    assert snap["started_at"] == "2026-08-27T12:00:00"
    assert set(snap.keys()) == {"status", "started_at", "finished_at", "last_stats", "error"}
