"""知识库构建接口：触发增量入库 + 查询构建状态（FastAPI 对外入口）。

对外契约（snake_case，错误体恒 {"detail": "中文"}）：
- POST /api/knowledge/import
    body 可选 {"paths": ["相对路径", ...]}；缺省或空列表 = 全量扫描 docs/
    → 200 {"status": "started"}（后台线程执行，立即返回）
    → 409 {"detail": "知识库构建正在进行中"}（单飞冲突）
    → 400 {"detail": "paths 必须是字符串数组"}（校验失败）
- GET /api/knowledge/import/status
    → 200 {"status": "idle"|"running"|"failed", "started_at", "finished_at",
           "last_stats", "error"}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.knowledge.service import BuildAlreadyRunning, get_build_status, trigger_build

router = APIRouter()


class ImportRequest(BaseModel):
    """入库请求体：paths 可选（None 或缺省 = 全量扫描 docs/）。"""

    paths: list[Any] | None = None


@router.post("/api/knowledge/import")
async def knowledge_import(payload: ImportRequest | None = None) -> dict:
    """触发对所有未入库文档的增量构建（切块→抽取→归并→建图→embedding→登记）。"""
    paths = _validate_paths(payload)
    try:
        return trigger_build(paths)
    except BuildAlreadyRunning:
        raise HTTPException(status_code=409, detail="知识库构建正在进行中")


@router.get("/api/knowledge/import/status")
async def knowledge_import_status() -> dict:
    """返回构建状态：idle | running | failed + 最近一次统计。"""
    return get_build_status()


def _validate_paths(payload: ImportRequest | None) -> list[str] | None:
    """校验 paths：元素必须全是非空字符串；None/空列表按全量处理。"""
    if payload is None or payload.paths is None:
        return None
    if not payload.paths:
        return None  # 空列表 = 全量（与 import_all 语义一致）
    for p in payload.paths:
        if not isinstance(p, str) or not p.strip():
            raise HTTPException(status_code=400, detail="paths 必须是字符串数组")
    return [p.strip() for p in payload.paths]
