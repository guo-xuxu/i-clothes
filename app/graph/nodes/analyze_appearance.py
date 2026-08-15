"""体征分析节点：调用千问多模态模型分析照片中人物的客观体征。"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import OutfitState
from app.providers import get_qianwen_vl

APPEARANCE_PROMPT = """你是一名专业的形象分析师。用户会上传一张或多张人物照片。
请仔细观察照片中的人物，客观描述其可见的身体特征，供后续穿搭推荐使用。

请按以下结构输出（使用中文），只描述能从照片中客观观察到的信息，不要推测或编造：
1. 体型：整体身材比例（如高挑/娇小、纤细/匀称等），肩宽、腰身特征
2. 头型/脸型：脸型轮廓（如鹅蛋脸、圆脸、方脸等）
3. 腿型：腿部线条特征、长短比例
4. 肤色：肤色冷暖倾向（冷调/暖调/中性）和明度（白皙/小麦色等）
5. 其他：发型、发色、以及照片中已有的穿着风格

如果某项无法从照片中判断，请标注"无法判断"。保持客观、简洁。"""


async def analyze_appearance(state: OutfitState) -> OutfitState:
    """分析照片中人物的体征数据（体型、脸型、腿型、肤色等）。"""
    model = get_qianwen_vl()

    content: list[dict] = []
    for url in state["images"]:
        content.append({
            "type": "image_url",
            "image_url": {"url": url}
        })
    content.append({
        "type": "text",
        "text": "请分析这些照片中人物的客观体征。"
    })

    messages = [
        SystemMessage(content=APPEARANCE_PROMPT),
        HumanMessage(content=content),
    ]

    response = await model.ainvoke(messages)
    return {"appearance": response.content}
