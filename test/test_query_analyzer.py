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
