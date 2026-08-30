"""在线召回节点：改写查询 → 图遍历 + 向量混合召回 → state["rag_context"]（fail-open）。"""
import logging

from app.graph.state import OutfitState
from app.knowledge.retrieve import retriever

logger = logging.getLogger(__name__)


async def retrieve_context(state: OutfitState) -> OutfitState:
    """执行混合召回并写入 rag_context；任何失败返回空串（fail-open，spec R6）。

    图路：改写查询 + 关键检索词 → 节点子串匹配 → 2 跳遍历；
    向量路：改写查询 embedding → Chroma chunk top-k（距离阈值 + 维度过滤）。
    """
    if state.get("intent_detail") == "chat":
        return {"rag_context": ""}
    query = (state.get("rewritten_query") or "").strip()
    if not query:
        query = (state.get("description") or "").strip()
    if not query:
        return {"rag_context": ""}
    try:
        ctx = await retriever.retrieve(
            query,
            keywords=state.get("rewrite_keywords") or [],
            dimension=state.get("dimension") or "",
            photo_type=state.get("photo_type") or "unknown",
        )
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.warning("在线召回失败（返回空上下文）: %s", exc)
        return {"rag_context": ""}
    logger.info("在线召回: dimension=%s photo_type=%s hits=%d chars=%d",
                state.get("dimension"), state.get("photo_type"),
                ctx.count("\n- ") + (1 if ctx else 0), len(ctx))
    return {"rag_context": ctx}
