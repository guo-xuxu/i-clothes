"""穿搭推荐工作流的节点实现。"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import OutfitState
from app.providers import get_qianwen_vl

SYSTEM_PROMPT = """你是一名专业的穿搭顾问。用户会上传一些参考照片（场景、活动或风格参考），
以及可选的文字说明。请基于照片内容，给出个性化的穿搭建议。

请按以下结构输出（使用中文）：
1. 整体风格定位：一句话概括推荐的风格方向
2. 推荐色系：主色调和搭配色
3. 单品建议：上衣、下装、鞋子、配饰的具体建议
4. 搭配技巧：2-3条实用的搭配要点

回答要具体、可执行，避免空泛的描述。"""


async def analyze_scene(state: OutfitState) -> OutfitState:
    """节点：调用千问多模态模型，根据参考照片生成穿搭建议。"""
    model = get_qianwen_vl()

    # 构造多模态内容
    content: list[dict] = []

    # 添加图片
    for url in state["images"]:
        content.append({
            "type": "image_url",
            "image_url": {"url": url}
        })

    # 添加文字
    user_text = (state.get("description") or "").strip() or "请根据这些参考照片给我推荐穿搭。"
    content.append({
        "type": "text",
        "text": user_text
    })

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=content),
    ]

    response = await model.ainvoke(messages)
    return {"suggestion": response.content}
