"""查询改写节点：把用户问题改写成检索友好的查询（供图/向量召回消费）。

- 输入：当前消息 + 会话历史（代词指代消解）+ intent_detail/dimension（定向增强）；
- 输出：{"query": 改写后的检索查询, "keywords": [关键检索词, ...]}；
- chat 意图不检索 → 跳过 LLM，原样透传；
- fail-open：LLM 失败/解析失败 → 回退原消息。
"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.graph.state import OutfitState
from app.repositories.model_repo import ModelRepository

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.S)
MAX_HISTORY_TURNS = 3

_RW_PROMPT = """你是穿搭领域的查询改写器。把用户问题改写成更适合「知识图谱 + 向量检索」的检索查询。

输入：
- 当前问题：{message}
- 历史对话（用于指代消解）：
{history}
- 意图：{intent}（outfit=整体穿搭 / match=单品搭配 / style=风格 / color=颜色）
- 知识维度：{dimension}

改写要求：
1. 指代消解：把代词（它/这件/这种/那个）还原为历史对话中的具体实体（如"风衣"）；
2. 规范表达：用常见规范说法（如"梨型"→"梨形"），必要时补充同义说法；
3. 突出检索词：保留核心实体词（服饰/场合/颜色/体型/风格等），去掉寒暄与冗余；
4. 输出严格 JSON，不要任何多余文字：
{{"query": "改写后的检索查询（一句话，中文）", "keywords": ["关键检索词1", "关键检索词2", ...]}}"""


class QueryRewrite(BaseModel):
    """一次查询改写的结果。"""

    query: str = ""
    keywords: list[str] = []


def format_history(messages: list[dict], max_turns: int = MAX_HISTORY_TURNS) -> str:
    """把最近 max_turns 轮历史格式化为文本（旧在前新在后）。"""
    lines = []
    for m in (messages or [])[-max_turns * 2:]:
        role = "用户" if m.get("role") == "user" else "助手"
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "（无）"


def parse_rewrite(raw: str) -> QueryRewrite:
    """解析 LLM 输出为 QueryRewrite；失败返回空结果（由调用方回退原文）。"""
    if not raw:
        return QueryRewrite()
    m = _JSON_RE.search(raw)
    if not m:
        return QueryRewrite()
    try:
        data = json.loads(m.group(0))
        return QueryRewrite(
            query=str(data.get("query", "")).strip(),
            keywords=[str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()],
        )
    except Exception as exc:  # noqa: BLE001 - 解析失败统一回退
        logger.warning("查询改写 JSON 解析失败: %.120s (%s)", raw, exc)
        return QueryRewrite()


async def rewrite_query(
    message: str,
    history: list[dict],
    intent_detail: str,
    dimension: str,
) -> QueryRewrite:
    """调用 DeepSeek 改写查询；任何失败回退原文（fail-open）。"""
    model = ModelRepository.get_deepseek()
    prompt = _RW_PROMPT.format(
        message=message,
        history=format_history(history),
        intent=intent_detail or "chat",
        dimension=dimension or "general",
    )
    try:
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        rw = parse_rewrite(resp.content)
        if not rw.query:
            return QueryRewrite(query=message)
        return rw
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.warning("查询改写失败（回退原文）: %s", exc)
        return QueryRewrite(query=message)


async def query_rewriter(state: OutfitState) -> OutfitState:
    """改写节点：chat 意图透传不调 LLM；其余意图改写并写入 state。"""
    message = (state.get("description") or "").strip()
    if state.get("intent_detail") == "chat":
        return {"rewritten_query": message, "rewrite_keywords": []}
    rw = await rewrite_query(
        message,
        state.get("messages") or [],
        state.get("intent_detail") or "",
        state.get("dimension") or "",
    )
    return {"rewritten_query": rw.query, "rewrite_keywords": rw.keywords}
