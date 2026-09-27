"""气象观测接口：录入实况、查看倒序观测与明细、读取预警播报清单。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.weather import WeatherService

router = APIRouter(prefix="/api/weather", tags=["气象观测"])

service = WeatherService()

LIST_FIELDS = ["观测时间", "能见度", "风速", "风向", "跑道视程"]


@router.get("/export")
def export_observations() -> dict[str, Any]:
    """导出气象观测清单：含每条观测联带的预警播报，方便两份清单对账。"""
    items = service.list_observations()
    return {"module": "weather", "total": len(items), "items": items}


@router.get("/alerts", response_model=PageResult[dict])
def list_alerts() -> PageResult[dict]:
    """预警播报清单，按播报时刻倒序；无预警时返回空页，不报错。"""
    payload = service.list_alerts()
    items = payload["items"]
    return PageResult(items=items, total=payload["total"], page=1, size=payload["total"] or 1)


@router.get("", response_model=PageResult[dict])
def list_observations() -> PageResult[dict]:
    """气象观测记录按观测时间倒序返回；每条记录附联带预警用于互相印证。"""
    items = service.list_observations()
    return PageResult(items=items, total=len(items), page=1, size=max(len(items), 1))


@router.get("/{entry_id}", response_model=dict)
def get_observation(entry_id: int) -> dict:
    """读取单条气象观测明细；不存在时给出可读的错误说明。"""
    entry = service.get_observation(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"气象观测记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_observation(payload: EntryPayload) -> ActionResult:
    """录入气象实况：同一观测时刻合并覆盖；缺值或超物理范围时拒绝并逐条说明原因。"""
    entry, errors, summary = service.create_observation(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    if summary.get("created"):
        message = f"气象实况已录入，并生成 {summary['created']} 条预警播报"
    else:
        message = "同一观测时刻已合并更新，未重复叠加观测记录"
        if summary.get("updated"):
            message += f"，已刷新 {summary['updated']} 条在播预警"
        if summary.get("resolved"):
            message += f"，{summary['resolved']} 条预警随实况解除"
    return ActionResult(ok=True, message=message, entry=entry)
