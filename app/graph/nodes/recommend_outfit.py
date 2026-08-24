"""穿搭推荐节点：调用 DeepSeek 基于体征分析和用户需求生成推荐。"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import OutfitState
from app.repositories.model_repo import ModelRepository

RECOMMEND_PROMPT = """你是一名专业的穿搭顾问。你会收到一份对用户体型、脸型、腿型、肤色等特征的客观分析，
以及用户的穿搭需求。请基于这些信息，给出个性化、扬长避短的100字以内穿搭建议。

请按以下结构输出（使用中文）：
1. 整体风格定位：一句话概括推荐的风格方向
2. 推荐色系：结合肤色，给出显气色的主色调和搭配色
3. 单品建议：上衣、下装、鞋子、配饰的具体建议，说明如何扬长避短
4. 搭配技巧：2-3 条结合其体型特征的实用要点

注意：如果【体征分析】部分为空（用户未上传照片），请完全基于【用户需求】和
【历史对话】中的信息给出建议，并在开头加一句"没有照片的情况下，我先按文字描述
给你参考建议"。

回答要具体、可执行，紧扣前面的信息，避免空泛的描述。"""

# 最多携带的历史用户消息条数作为上下文
MAX_CONTEXT = 6


async def recommend_outfit(state: OutfitState) -> OutfitState:
    """基于体征分析（如有）和用户需求生成穿搭建议。"""
    model = ModelRepository.get_deepseek()

    appearance = (state.get("appearance") or "").strip()
    user_need = (state.get("description") or "").strip() or "日常穿搭，无特殊场合要求。"

    # 历史上下文：最近几条用户消息
    history = state.get("messages") or []
    history_lines = []
    for m in history[-MAX_CONTEXT:]:
        if m.get("role") == "user" and (m.get("content") or "").strip():
            history_lines.append(f"- {m['content'].strip()}")
    history_text = "\n".join(history_lines)

    user_message = f"【体征分析】\n{appearance or '（无，用户未上传照片）'}\n\n【用户需求】\n{user_need}\n\n"
    if history_text:
        user_message += f"【历史对话】\n{history_text}\n\n"
    user_message += "请基于以上信息给出穿搭建议。"

    messages = [
        SystemMessage(content=RECOMMEND_PROMPT),
        HumanMessage(content=user_message),
    ]

    response = await model.ainvoke(messages)
    return {"suggestion": response.content}
