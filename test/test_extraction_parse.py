"""图谱抽取解析单测：LLM JSON 解析 + 抽取器行为（mock DeepSeek，不花钱）。"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.knowledge.build.extract import graph_extractor as ge  # noqa: E402
from app.knowledge.build.text_chunk import TextChunk  # noqa: E402
from app.repositories.model_repo import ModelRepository  # noqa: E402


def _chunk(text: str = "内容") -> TextChunk:
    return TextChunk(content=text, dimension=None, dimension_name=None,
                     title="t", source="t.md", index=0)


def test_parse_extraction_valid():
    raw = ('{"entities": [{"name": "西装", "type": "服装单品", "description": "正式外套"}], '
           '"relationships": [{"source": "婚礼", "target": "西装", "description": "适合", '
           '"keywords": ["适合"], "strength": 9}], "content_keywords": ["婚礼"]}')
    result = ge.parse_extraction(raw)
    assert len(result.entities) == 1
    assert result.entities[0]["name"] == "西装"
    assert len(result.relationships) == 1
    assert result.relationships[0]["source"] == "婚礼"


def test_parse_extraction_fenced():
    raw = '```json\n{"entities": [], "relationships": [], "content_keywords": []}\n```'
    result = ge.parse_extraction(raw)
    assert result.entities == []
    assert result.relationships == []


def test_parse_extraction_invalid_empty():
    result = ge.parse_extraction("不是JSON")
    assert result.entities == []
    assert result.relationships == []


def test_parse_extraction_bad_schema_empty():
    result = ge.parse_extraction('{"entities": "oops"}')
    assert result.entities == []


def test_extract_parses_model_output(monkeypatch):
    class FakeDs:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=(
                '{"entities": [{"name": "风衣", "type": "服装单品", "description": "长外套"}], '
                '"relationships": [], "content_keywords": []}'))

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: FakeDs()))
    extractor = ge.GraphExtractor()
    result = asyncio.run(extractor.extract(_chunk()))
    assert len(result.entities) == 1
    assert result.entities[0]["name"] == "风衣"


def test_extract_fails_open(monkeypatch):
    class BoomDs:
        async def ainvoke(self, messages):
            raise RuntimeError("provider error")

    monkeypatch.setattr(ModelRepository, "get_deepseek", staticmethod(lambda: BoomDs()))
    extractor = ge.GraphExtractor()
    result = asyncio.run(extractor.extract(_chunk()))
    assert result.entities == []
    assert result.relationships == []
