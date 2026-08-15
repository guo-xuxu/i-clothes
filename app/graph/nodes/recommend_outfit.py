"""穿搭推荐节点：调用 DeepSeek 基于体征分析和用户需求生成推荐。"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import OutfitState
from app.providers import get_deepseek

RECOMMEND_PROMPT = """你是一名专业的穿搭顾问。你会收到一份对用户体型、脸型、腿型、肤色等特征的客观分析，
以及用户的穿搭需求。请基于这些信息，给出个性化、扬长避短的100字以内穿搭建议。

请按以下结构输出（使用中文）：
1. 整体风格定位：一句话概括推荐的风格方向
2. 推荐色系：结合肤色，给出显气色的主色调和搭配色
3. 单品建议：上衣、下装、鞋子、配饰的具体建议，说明如何扬长避短
4. 搭配技巧：2-3 条结合其体型特征的实用要点

回答要具体、可执行，紧扣前面的体征分析，避免空泛的描述。"""


async def recommend_outfit(state: OutfitState) -> OutfitState:
    """基于体征分析和用户需求生成穿搭建议。"""
    model = get_deepseek()

    appearance = state.get("appearance", "")
    user_need = (state.get("description") or "").strip() or "日常穿搭，无特殊场合要求。"

    user_message = (
        f"【体征分析】\n{appearance}\n\n"
        f"【用户需求】\n{user_need}\n\n"
        f"请基于以上信息给出穿搭建议。"
    )

    messages = [
        SystemMessage(content=RECOMMEND_PROMPT),
        HumanMessage(content=user_message),
    ]

    response = await model.ainvoke(messages)
    return {"suggestion": response.content}
