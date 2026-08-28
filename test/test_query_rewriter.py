"""查询改写单测：LLM 改写（mock DeepSeek）+ 解析 fail-open + 节点行为。"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.graph.nodes.query_rewriter import (  # noqa: E402
    QueryRewrite,
    format_history,
    parse_rewrite,
    query_rewriter,
    rewrite_query,
)
from app.repositories.model_repo import ModelRepository  # noqa: E402


def test_parse_rewrite_valid():
    raw = '{"query": "梨形身材 显瘦 穿搭建议", "keywords": ["梨形身材", "显瘦"]}'
    rw = parse_rewrite(raw)
    assert rw.query == "梨形身材 显瘦 穿搭建议"
    assert rw.keywords == ["梨形身材", "显瘦"]


def test_parse_rewrite_fenced():
    raw = '```json\n{"query": "婚礼 正装 穿搭", "keywords": ["婚礼", "正装"]}\n```'
    rw = parse_rewrite(raw)
    assert rw.query == "婚礼 正装 穿搭"


def test_parse_rewrite_invalid_empty():
    rw = parse_rewrite("这不是 JSON")
    assert rw.query == ""
    assert rw.keywords == []


def test_format_history_limits_turns():
    history = [
        {"role": "user", "content": "第一轮"},
        {"role": "assistant", "content": "回复一"},
        {"role": "user", "content": "第二轮"},
        {"role": "assistant", "content": "回复二"},
        {"role": "user", "content": "第三轮"},
        {"role": "assistant", "content": "回复三"},
    ]
    text = format_history(history, max_turns=2)
    assert "第三轮" in text
    assert "回复三" in text
    assert "第二轮" in text
    assert "第一轮" not in text


def test_rewrite_query_parses_model_output(monkeypatch):
    class FakeDs:
        async def ainvoke(self, messages):
            return SimpleNamespace(content='{"query": "冷皮 适合 颜色 推荐", "keywords": ["冷皮", "颜色"]}')

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: FakeDs()))

    rw = asyncio.run(rewrite_query("我是冷皮适合什么颜色", [], "color", "肤色与个人色彩"))
    assert rw.query == "冷皮 适合 颜色 推荐"
    assert rw.keywords == ["冷皮", "颜色"]


def test_rewrite_query_falls_back_on_model_error(monkeypatch):
    class BoomDs:
        async def ainvoke(self, messages):
            raise RuntimeError("provider error")

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: BoomDs()))

    rw = asyncio.run(rewrite_query("我是冷皮适合什么颜色", [], "color", "肤色与个人色彩"))
    assert rw.query == "我是冷皮适合什么颜色"  # 回退原文
    assert rw.keywords == []


def test_rewrite_query_falls_back_on_bad_output(monkeypatch):
    class PlainDs:
        async def ainvoke(self, messages):
            return SimpleNamespace(content="随便聊聊")

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: PlainDs()))

    rw = asyncio.run(rewrite_query("条纹怎么搭配", [], "match", "图案与纹理"))
    assert rw.query == "条纹怎么搭配"


def test_node_skips_llm_for_chat(monkeypatch):
    called = []

    def _boom():
        called.append(1)
        raise AssertionError("chat 意图不应调用 LLM")

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(_boom))

    out = asyncio.run(query_rewriter(
        {"description": "你好呀", "intent_detail": "chat", "dimension": "general", "messages": []}))
    assert out["rewritten_query"] == "你好呀"
    assert out["rewrite_keywords"] == []
    assert called == []


def test_node_rewrites_for_recommend(monkeypatch):
    class FakeDs:
        async def ainvoke(self, messages):
            return SimpleNamespace(content='{"query": "围巾 搭配 建议", "keywords": ["围巾", "搭配"]}')

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: FakeDs()))

    out = asyncio.run(query_rewriter(
        {"description": "围巾怎么搭配", "intent_detail": "match", "dimension": "配饰与点缀",
         "messages": [{"role": "user", "content": "之前聊过围巾"}]}))
    assert out["rewritten_query"] == "围巾 搭配 建议"
    assert out["rewrite_keywords"] == ["围巾", "搭配"]
