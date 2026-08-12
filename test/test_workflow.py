"""测试穿搭推荐工作流的基本功能。"""
import asyncio
import base64
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.graph.workflow import run_recommendation

test_image_path = "../test/images/sample1.png"

def image_to_data_url(image_path: str) -> str:
    """将本地图片转换为 data URL。"""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"将本地图片转换为 data URL时图片不存在: {image_path}")

    # 根据扩展名判断 MIME 类型
    suffix = path.suffix.lower()
    mime_type = "image/jpeg" if suffix in [".jpg", ".jpeg"] else "image/png"

    with open(path, "rb") as f:
        image_data = f.read()

    b64_data = base64.b64encode(image_data).decode("utf-8")
    return f"data:{mime_type};base64,{b64_data}"


async def test_single_image():
    """测试单张图片的穿搭推荐。"""
    print("=" * 60)
    print("测试 1: 单张图片推荐")
    print("=" * 60)

    # 替换为你的测试图片路径
    test_image = test_image_path

    try:
        image_url = image_to_data_url(test_image)
        result = await run_recommendation(
            images=[image_url],
            description="我要参加朋友的生日派对"
        )

        print("\n推荐结果：")
        print(result)
        print("\n✓ 测试通过")

    except FileNotFoundError as e:
        print(f"\n✗ 图片文件不存在: {e}")
        print("请将测试图片放在 test/images/ 目录下")
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        raise


async def test_multiple_images():
    """测试多张图片的穿搭推荐。"""
    print("\n" + "=" * 60)
    print("测试 2: 多张图片推荐")
    print("=" * 60)

    test_images = [
        test_image_path,
        "test/images/sample2.png",
    ]

    try:
        image_urls = [image_to_data_url(img) for img in test_images]
        result = await run_recommendation(
            images=image_urls,
            description="我想要休闲舒适的风格"
        )

        print("\n推荐结果：")
        print(result)
        print("\n✓ 测试通过")

    except FileNotFoundError as e:
        print(f"\n✗ 图片文件不存在: {e}")
        print("请将测试图片放在 test/images/ 目录下")
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        raise


async def test_no_description():
    """测试不提供描述的情况。"""
    print("\n" + "=" * 60)
    print("测试 3: 无描述文字")
    print("=" * 60)

    test_image = test_image_path

    try:
        image_url = image_to_data_url(test_image)
        result = await run_recommendation(
            images=[image_url],
            description=""
        )

        print("\n推荐结果：")
        print(result)
        print("\n✓ 测试通过")

    except FileNotFoundError as e:
        print(f"\n✗ 图片文件不存在: {e}")
        print("请将测试图片放在 test/images/ 目录下")
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        raise


async def main():
    """运行所有测试。"""
    print("开始测试穿搭推荐工作流...")
    print("请确保：")
    print("1. .env 文件中已配置 QIANWEN_API_KEY")
    print("2. test/images/ 目录下有测试图片")
    print()

    # 运行测试
    # await test_single_image()

    # 如果第一个测试通过，继续运行其他测试
    # await test_multiple_images()
    await test_no_description()

    print("\n" + "=" * 60)
    print("所有测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
