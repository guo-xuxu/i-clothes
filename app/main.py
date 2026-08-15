"""FastAPI 应用入口：提供穿搭推荐接口和前端页面。"""
import base64
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Phoenix tracing：官方 register() 自动配置 OTLP 导出并挂载 instrumentor
from phoenix.otel import register

from app.config import settings
from app.graph.workflow import run_recommendation

PHOENIX_UI_PORT = 6006
PHOENIX_OTLP_PORT = 4317


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    """检查端口是否可连接。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def ensure_phoenix_server() -> None:
    """确保 Phoenix server 已就绪后再初始化追踪。

    顺序保证：Phoenix 必须先于 register() 启动，否则该进程的 span
    将因 Collector 不可达而无法导出（表现为接口正常但 UI 无记录）。
    若 Phoenix 已在运行则直接复用；否则自动拉起并等待端口就绪。

    注意：Phoenix 保持常驻，不随 uvicorn 退出而终止，避免 --reload
    热重载时误杀 Phoenix 导致端口冲突。
    """
    if _port_open(PHOENIX_UI_PORT) and _port_open(PHOENIX_OTLP_PORT):
        print(f"[Phoenix] 已在运行: http://localhost:{PHOENIX_UI_PORT}")
        return

    print("[Phoenix] 未检测到 Phoenix server，自动启动中 ...")
    log_path = Path(__file__).resolve().parent.parent / "logs" / "phoenix.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "ab", buffering=0)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(
        [sys.executable, "-m", "phoenix.server.main", "serve"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )

    deadline = time.time() + 60
    while time.time() < deadline:
        if _port_open(PHOENIX_UI_PORT) and _port_open(PHOENIX_OTLP_PORT):
            print(f"[Phoenix] 启动完成: http://localhost:{PHOENIX_UI_PORT}")
            return
        time.sleep(0.5)
    print(f"[Phoenix] 等待就绪超时(60s)，请检查日志: {log_path}")


# 先确保 Phoenix server 就绪，再注册追踪（顺序不能反）
ensure_phoenix_server()

register(
    project_name="i-clothes",
    auto_instrument=True,
)
print("[Phoenix] Tracing enabled. Make sure Phoenix server is running at http://localhost:6006")

app = FastAPI(title="i-clothes 智能穿搭助手", version="0.1.0")



BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@app.get("/")
async def index() -> FileResponse:
    """返回前端首页。"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    """健康检查，同时返回千问是否已配置。"""
    return {"status": "ok", "qianwen_configured": bool(settings.QIANWEN_API_KEY)}


@app.post("/api/recommend")
async def recommend(
    images: list[UploadFile] = File(...),
    description: str = Form(""),
) -> dict:
    """接收参考照片和文字说明，返回穿搭建议。"""
    if not images:
        raise HTTPException(status_code=400, detail="请至少上传一张照片")

    if len(images) > settings.MAX_UPLOAD_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"最多上传 {settings.MAX_UPLOAD_COUNT} 张照片",
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    image_urls: list[str] = []

    for image in images:
        if image.content_type not in settings.ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的图片格式：{image.content_type}，仅支持 JPG/PNG",
            )
        data = await image.read()
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"图片 {image.filename} 超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制",
            )
        b64 = base64.b64encode(data).decode("utf-8")
        image_urls.append(f"data:{image.content_type};base64,{b64}")

    try:
        suggestion = await run_recommendation(image_urls, description)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"suggestion": suggestion}


# 静态资源（CSS/JS）
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
