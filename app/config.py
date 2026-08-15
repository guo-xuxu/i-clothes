"""应用配置模块，从环境变量加载配置。"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """集中管理应用配置。"""

    # 通义千问
    QIANWEN_API_KEY: str = os.getenv("QIANWEN_API_KEY", "")
    QIANWEN_BASE_URL: str = os.getenv(
        "QIANWEN_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    QIANWEN_MODEL: str = os.getenv("QIANWEN_MODEL", "qwen3.7-max-2026-06-08")

    # DeepSeek（后续版本）
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    # 上传限制
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "5"))
    MAX_UPLOAD_COUNT: int = int(os.getenv("MAX_UPLOAD_COUNT", "3"))

    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


settings = Settings()