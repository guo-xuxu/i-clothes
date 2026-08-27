"""知识库构建服务：封装 import_all 增量入库，提供后台触发与状态查询（进程内单飞）。

设计（见 docs/RAG知识图谱规划.md §3.1 MVP）：后台守护线程执行 import_all，
HTTP 层立即返回，另提供状态查询；进程内单飞（同一时刻只允许一个构建），
多实例部署时需升级为 Redis 队列（基础设施已有，当前 MVP 不引入）。

职责边界：
- 只负责「触发 + 状态」，不重写 import_all 的入库逻辑（切块/抽取/归并/建图/embedding/登记）；
- 状态是进程内内存对象（不落盘），进程重启后回到 idle。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime

from app.knowledge.build.import_all import import_all

logger = logging.getLogger(__name__)


class BuildAlreadyRunning(Exception):
    """知识库构建已在进行中（单飞冲突）。"""


@dataclass
class BuildState:
    """一次后台构建的状态（进程内，不落盘）。

    Attributes:
        status: idle（空闲）| running（构建中）| failed（上次构建失败）。
        started_at / finished_at: 最近一次构建的起止时间（ISO 秒）。
        last_stats: 最近一次成功的 import_all 返回值；失败或无历史时为 None。
        error: 最近一次失败的原因；无失败时为 None。
    """

    status: str = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    last_stats: dict | None = None
    error: str | None = None


_state = BuildState()
_lock = threading.Lock()


def trigger_build(paths: list[str] | None = None) -> dict:
    """触发一次增量入库（单飞）。立即返回 {"status": "started"}。

    Args:
        paths: 待导入文档路径列表（相对/绝对皆可）；None 或空列表 = 全量扫描 docs/。

    Raises:
        BuildAlreadyRunning: 已有构建在进行中。
    """
    with _lock:
        if _state.status == "running":
            raise BuildAlreadyRunning()
        _state.status = "running"
        _state.started_at = datetime.now().isoformat(timespec="seconds")
        _state.finished_at = None
        _state.last_stats = None
        _state.error = None

    threading.Thread(target=_run_build, args=(paths,), daemon=True).start()
    return {"status": "started"}


def _run_build(paths: list[str] | None) -> None:
    """后台线程执行体：跑 import_all 并回写状态（异常记 failed，不让线程静默死掉）。"""
    try:
        stats = import_all(paths)
    except Exception as exc:  # noqa: BLE001 - 构建失败要落状态可查
        logger.exception("知识库构建失败: %s", exc)
        with _lock:
            _state.status = "failed"
            _state.error = str(exc)
            _state.finished_at = datetime.now().isoformat(timespec="seconds")
        return
    with _lock:
        _state.status = "idle"
        _state.last_stats = stats
        _state.finished_at = datetime.now().isoformat(timespec="seconds")
    logger.info("知识库构建完成: %s", stats)


def get_build_status() -> dict:
    """返回当前构建状态快照。"""
    with _lock:
        return {
            "status": _state.status,
            "started_at": _state.started_at,
            "finished_at": _state.finished_at,
            "last_stats": _state.last_stats,
            "error": _state.error,
        }
