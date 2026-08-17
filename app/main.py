"""FastAPI 应用入口：组装应用、挂载路由与静态资源。

分层说明：
- 接口层（controller）在 app/api/routers/，main.py 只负责挂载。
- 业务层在 app/services/，核心工作流在 app/graph/。
- 数据访问层在 app/repositories/（模型、未来的 SQL/向量/知识图谱）。
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Phoenix tracing：官方 register() 自动配置 OTLP 导出并挂载 instrumentor
from phoenix.otel import register

from app.api.routers import chat, health, recommend

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
FRONTEND_DIST = FRONTEND_DIR / "dist"
DIST_READY = (FRONTEND_DIST / "index.html").exists()


@app.get("/")
async def index() -> FileResponse:
    """返回前端首页（优先 Vue 构建产物，否则回退到旧静态页）。"""
    if DIST_READY:
        return FileResponse(FRONTEND_DIST / "index.html")
    return FileResponse(FRONTEND_DIR / "index.html")


# API 路由（接口层，见 app/api/routers/）
app.include_router(recommend.router)
app.include_router(health.router)
app.include_router(chat.router)

# 静态资源：Vue 构建产物（/assets）或旧版原生前端（/static）
if DIST_READY:
    app.mount(
        "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets"
    )
else:
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
