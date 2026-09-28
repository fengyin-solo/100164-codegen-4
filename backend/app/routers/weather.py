"""气象观测接口：录入实况、倒序查询、明细视图、预警播报清单。

固定路径（/broadcasts、/export）必须排在 /{entry_id} 之前注册，
否则 FastAPI 会把 broadcasts 当成记录 id 解析。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.weather import WeatherService

router = APIRouter(prefix="/api/weather", tags=["气象观测"])

service = WeatherService()

LIST_FIELDS = ["观测时间", "能见度", "风速", "风向", "跑道视程"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    warning: str | None = Query(default=None, description="传 1 只看产生过预警播报的观测"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按观测时间倒序返回观测记录；每条记录带出最新一次预警播报以便互相印证。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(warning=warning, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/broadcasts")
def list_broadcasts() -> dict[str, Any]:
    """预警播报清单：按播报时刻倒序，每条都能回溯到对应观测记录。"""
    items = service.list_broadcasts()
    return {"module": "weather", "total": len(items), "items": items}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出气象观测全量清单（倒序），供留档核对。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "weather", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """单条观测的明细视图：完整字段加预警播报（播报对象、播报时刻）。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"观测记录 {entry_id} 不存在")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """录入一次气象实况：同一观测时刻做合并；校验不过时拒绝保存并逐条说明原因。"""
    entry, errors, merged = service.upsert_entry(payload.values)
    if errors:
        return ActionResult(ok=False, message="保存被拒绝：" + "；".join(errors))
    if merged:
        return ActionResult(ok=True, message=f"观测时间 {entry['观测时间']} 已有记录，已合并更新", entry=entry)
    return ActionResult(ok=True, message="气象观测已录入", entry=entry)
