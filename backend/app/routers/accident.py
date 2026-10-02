"""事故管理接口：维护事故记录，覆盖上报事故、开展调查、结案归档等动作。"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.accident import AccidentService

router = APIRouter(prefix="/api/accident", tags=["事故管理"])

service = AccidentService()

LIST_FIELDS = ["事故编号", "事故设备", "事故类型", "伤亡情况", "直接损失", "发生时间", "调查结论", "事故状态"]
STATUSES = ["待上报", "已上报", "调查中", "已结案"]
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按事故编号或事故设备检索"),
    status: str | None = Query(default=None, description="待上报、已上报、调查中、已结案；传「待处理」等价于未结案"),
    month: str | None = Query(default=None, description="按发生月份过滤，格式 YYYY-MM"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按事故编号/设备、状态与月份过滤事故管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if month is not None and not MONTH_PATTERN.match(month):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM，例如 2026-08")
    items, total = service.list_entries(keyword=keyword, status=status, month=month, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats", response_model=dict)
def stats_entries() -> dict[str, Any]:
    """台账顶部统计：待处理、已结案、重伤以上，与概览、看板同一套结案判定。"""
    return service.get_stats()


@router.get("/board")
def board_overview() -> dict[str, Any]:
    """按期看板总览：左侧月份分段，右侧类型分布与直接损失合计。"""
    return service.board_overview()


@router.get("/board/{month}")
def board_month(month: str) -> dict[str, Any]:
    """下钻到某月：当月事故类型分布、损失合计、重伤以上清单与事故全量。"""
    if not MONTH_PATTERN.match(month):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM，例如 2026-08")
    bucket = service.board_month(month)
    if bucket is None:
        raise HTTPException(status_code=404, detail=f"{month} 没有事故记录")
    return bucket


# 固定路径要排在 /{entry_id} 前面，否则 export 会当成事故编号
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出事故管理清单：返回当前全量数据，取数口径与列表完全一致。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "accident", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条事故记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"事故记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条事故记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="事故记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条事故记录执行上报事故、开展调查、结案归档；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
