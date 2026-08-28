"""意图分析单测：无图关键词路由（意图 5 类 + 维度，纯函数，不触网）。"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.graph.nodes.query_analyzer import analyze_text  # noqa: E402


def test_outfit_intent_with_occasion_dimension():
    a = analyze_text("帮我推荐上班通勤的穿搭")
    assert a.intent == "outfit"
    assert a.dimension == "场合与季节"


def test_match_intent_general_dimension():
    a = analyze_text("这条裙子配什么上衣")
    assert a.intent == "match"
    assert a.dimension == "general"


def test_style_intent():
    a = analyze_text("我适合什么风格")
    assert a.intent == "style"
    assert a.dimension == "风格定位"


def test_color_intent_skin_dimension():
    a = analyze_text("我是冷皮，什么颜色显白")
    assert a.intent == "color"
    assert a.dimension == "肤色与个人色彩"


def test_color_intent_color_dimension():
    a = analyze_text("撞色怎么搭")
    assert a.intent == "match"
    assert a.dimension == "颜色搭配"


def test_wedding_outfit():
    a = analyze_text("参加婚礼穿什么")
    assert a.intent == "outfit"
    assert a.dimension == "场合与季节"


def test_casual_chat_general():
    a = analyze_text("你好，介绍一下你自己")
    assert a.intent == "chat"
    assert a.dimension == "general"


def test_empty_message_chat_general():
    a = analyze_text("")
    assert a.intent == "chat"
    assert a.dimension == "general"


# ---------------------------------------------------------------------------
# 多模态分析：JSON 解析（合法/围栏/非法/异常 → fail-open）与节点行为
# ---------------------------------------------------------------------------
import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from app.graph.nodes import query_analyzer as qa  # noqa: E402
from app.repositories.model_repo import ModelRepository  # noqa: E402


def test_parse_valid_json():
    raw = ('{"intent": "style", "dimension": "风格定位", "photo_type": "half_body", '
           '"info": {"skin_tone": "暖皮"}}')
    a = qa.parse_analysis(raw)
    assert a.intent == "style"
    assert a.dimension == "风格定位"
    assert a.photo_type == "half_body"
    assert a.info.skin_tone == "暖皮"
    assert a.info.body_shape == ""


def test_parse_fenced_json():
    raw = ('```json\n{"intent": "outfit", "dimension": "场合与季节", '
           '"photo_type": "full_body", "info": {}}\n```')
    a = qa.parse_analysis(raw)
    assert a.intent == "outfit"
    assert a.dimension == "场合与季节"


def test_parse_invalid_returns_defaults():
    a = qa.parse_analysis("这不是 JSON")
    assert a.intent == "chat"
    assert a.dimension == "general"
    assert a.photo_type == "unknown"


def test_parse_empty_returns_defaults():
    a = qa.parse_analysis("")
    assert a.intent == "chat"
    assert a.dimension == "general"


def test_parse_bad_intent_value_falls_back():
    a = qa.parse_analysis('{"intent": "shopping", "dimension": "颜色搭配", "photo_type": "unknown", "info": {}}')
    assert a.intent == "chat"


def test_format_info_joins_nonempty():
    info = qa.AnalysisInfo(body_shape="匀称", skin_tone="暖皮")
    text = qa.format_info(info)
    assert "体型：匀称" in text
    assert "肤色：暖皮" in text
    assert "脸型" not in text


def test_format_info_empty():
    assert qa.format_info(qa.AnalysisInfo()) == ""


def test_analyze_with_image_parses_model_output(monkeypatch):
    class FakeVl:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=(
                '{"intent": "color", "dimension": "肤色与个人色彩", "photo_type": "head_shot", '
                '"info": {"skin_tone": "冷皮"}}'))

    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: FakeVl()))

    a = asyncio.run(qa.analyze_with_image(["data:image/png;base64,AAAA"], "我适合什么颜色"))
    assert a.intent == "color"
    assert a.dimension == "肤色与个人色彩"
    assert a.photo_type == "head_shot"
    assert a.info.skin_tone == "冷皮"


def test_analyze_with_image_fails_open(monkeypatch):
    class BoomVl:
        async def ainvoke(self, messages):
            raise RuntimeError("provider error")

    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: BoomVl()))

    a = asyncio.run(qa.analyze_with_image(["data:image/png;base64,AAAA"], "随便"))
    assert a.intent == "chat"
    assert a.dimension == "general"


def test_query_analyzer_node_maps_intent(monkeypatch):
    class FakeVl:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=(
                '{"intent": "outfit", "dimension": "场合与季节", "photo_type": "full_body", '
                '"info": {"body_shape": "匀称"}}'))

    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: FakeVl()))

    out = asyncio.run(qa.query_analyzer(
        {"images": ["data:image/png;base64,AAAA"], "description": "帮我看看"}))
    assert out["intent"] == "recommend"
    assert out["intent_detail"] == "outfit"
    assert out["dimension"] == "场合与季节"
    assert out["photo_type"] == "full_body"
    assert "匀称" in out["analysis"]


def test_query_analyzer_node_chat_with_image(monkeypatch):
    class FakeVl:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=(
                '{"intent": "chat", "dimension": "general", "photo_type": "unknown", "info": {}}'))

    monkeypatch.setattr(ModelRepository, "get_qianwen_vl", staticmethod(lambda: FakeVl()))

    out = asyncio.run(qa.query_analyzer(
        {"images": ["data:image/png;base64,AAAA"], "description": "这张图好看吗"}))
    assert out["intent"] == "chat"
    assert out["intent_detail"] == "chat"


def test_query_analyzer_node_no_image_uses_keywords():
    out = asyncio.run(qa.query_analyzer({"images": [], "description": "我适合什么风格"}))
    assert out["intent"] == "recommend"
    assert out["intent_detail"] == "style"
    assert out["dimension"] == "风格定位"
