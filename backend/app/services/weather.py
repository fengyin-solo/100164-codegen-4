"""气象观测业务规则：录入校验、同时刻合并、预警判定与播报留痕都收在这里。

能见度/风速/跑道视程都有明确的物理量程，越过量程或没有数值的观测不允许入库；
观测时间相同视为同一次观测的重复录入，做就地合并而不是新增一条。
合并后的观测只要仍达到预警线，就重新生成预警播报，并记下播报对象与播报时刻。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "weather"

# 物理量程（单位：米 / 米每秒）。跑道视程允许空缺，给值时才校验。
VALUE_RANGES = {
    "能见度": (0, 10000),
    "风速": (0, 75),
    "跑道视程": (0, 3000),
}

# 预警线：达到任意一条即生成播报。
VISIBILITY_ALERT = 800       # 能见度低于 800 米
WIND_ALERT = 17              # 风速达到 17 米每秒（八级风）
RVR_ALERT = 550              # 跑道视程低于 550 米

# 每条预警线对应的播报对象。
ALERT_RECIPIENTS = {
    "能见度": "塔台管制席、机坪运行指挥室",
    "风速": "机坪运行指挥室、各保障作业班组",
    "跑道视程": "塔台管制席、飞行区管理部",
}

TIME_FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_observed_at(raw: Any) -> str | None:
    """把录入的观测时间归一化成 YYYY-MM-DD HH:MM；识别不了就返回 None。"""
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return None


def parse_number(raw: Any) -> tuple[float | None, bool]:
    """解析数值：返回 (数值, 是否解析成功)。空串/None 视为缺值（非解析失败）。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, True
    if isinstance(raw, bool):
        return None, False
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, False
    if value != value or value in (float("inf"), float("-inf")):
        return None, False
    return value, True


def evaluate_alerts(visibility: float, wind_speed: float, rvr: float | None) -> list[dict[str, str]]:
    """判定命中的预警线，返回触发原因清单，空清单表示未达预警线。"""
    alerts: list[dict[str, str]] = []
    if visibility < VISIBILITY_ALERT:
        alerts.append({
            "field": "能见度",
            "reason": f"能见度 {_num_text(visibility)} 米低于预警线 {VISIBILITY_ALERT} 米",
        })
    if wind_speed >= WIND_ALERT:
        alerts.append({
            "field": "风速",
            "reason": f"风速 {_num_text(wind_speed)} 米/秒达到预警线 {WIND_ALERT} 米/秒",
        })
    if rvr is not None and rvr < RVR_ALERT:
        alerts.append({
            "field": "跑道视程",
            "reason": f"跑道视程 {_num_text(rvr)} 米低于预警线 {RVR_ALERT} 米",
        })
    return alerts


def _num_text(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(round(value, 2))


class WeatherService:
    def list_entries(
        self,
        *,
        warning: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """按观测时间倒序返回观测记录；warning=1 时只看产生过预警播报的记录。"""
        rows = [dict(row) for row in store.rows(MODULE)]
        if warning:
            rows = [row for row in rows if row.get("预警播报")]
        rows.sort(key=lambda row: str(row.get("观测时间", "")), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def find_by_time(self, observed_at: str) -> dict[str, Any] | None:
        """按观测时间定位记录：同一观测时刻只允许存在一条。"""
        for row in store.rows(MODULE):
            if str(row.get("观测时间", "")) == observed_at:
                return row
        return None

    def list_broadcasts(self) -> list[dict[str, Any]]:
        """预警播报清单：从观测记录里带出播报，按播报时刻倒序，与观测侧互为印证。"""
        broadcasts = [
            dict(row["预警播报"], 观测记录=row["id"])
            for row in store.rows(MODULE)
            if row.get("预警播报")
        ]
        broadcasts.sort(key=lambda item: str(item.get("播报时刻", "")), reverse=True)
        return broadcasts

    def validate(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """校验录入值：数值空缺、非数字、越过物理量程、时间格式不对都会被拒绝并说明原因。"""
        errors: list[str] = []

        observed_at = parse_observed_at(values.get("观测时间"))
        if not observed_at:
            if not str(values.get("观测时间") or "").strip():
                errors.append("观测时间为必填项")
            else:
                errors.append("观测时间格式无法识别，请使用 YYYY-MM-DD HH:MM")

        numeric: dict[str, float | None] = {field: None for field in VALUE_RANGES}
        for field, (low, high) in VALUE_RANGES.items():
            value, ok = parse_number(values.get(field))
            if not ok:
                errors.append(f"{field}必须是数字，收到的是「{values.get(field)}」")
                continue
            if field != "跑道视程" and value is None:
                errors.append(f"{field}为必填项，不能空缺")
                continue
            if value is not None and not (low <= value <= high):
                errors.append(
                    f"{field}超出物理范围（允许 {low}~{high}），收到的是 {_num_text(value)}"
                )
                continue
            numeric[field] = value

        wind_direction = str(values.get("风向") or "").strip()
        if not wind_direction:
            errors.append("风向为必填项，不能空缺")

        if errors:
            return None, errors
        return {
            "观测时间": observed_at,
            "能见度": numeric["能见度"],
            "风速": numeric["风速"],
            "跑道视程": numeric["跑道视程"],
            "风向": wind_direction,
        }, []

    def upsert_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        """录入或合并一次观测，返回 (记录, 错误说明, 是否为合并)。校验不过时不落库。"""
        clean, errors = self.validate(values)
        if errors or clean is None:
            return None, errors, False

        rows = store.rows(MODULE)
        existing = self.find_by_time(clean["观测时间"])
        # 跑道视程允许空缺：合并时刻意保留此前已有的值，避免一次漏填把旧值抹掉。
        if existing is not None and clean["跑道视程"] is None and existing.get("跑道视程") is not None:
            clean["跑道视程"] = existing["跑道视程"]

        if existing is not None:
            entry = existing
            merged = True
        else:
            entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            entry["录入次数"] = 0
            rows.append(entry)
            merged = False

        entry.update(clean)
        entry["录入次数"] = int(entry.get("录入次数", 0)) + 1
        self._refresh_broadcast(entry)
        # 供运营概览统计使用：有预警播报即异常量，观测记录本身没有待办态。
        entry["status"] = "预警" if entry.get("预警播报") else "正常"
        entry["pending"] = False
        entry["abnormal"] = bool(entry.get("预警播报"))
        return entry, [], merged

    def _refresh_broadcast(self, entry: dict[str, Any]) -> None:
        """按最新观测值重新判定预警；解除预警时撤下此前的播报，避免清单与观测对不上。"""
        alerts = evaluate_alerts(
            float(entry["能见度"]),
            float(entry["风速"]),
            None if entry.get("跑道视程") is None else float(entry["跑道视程"]),
        )
        if not alerts:
            entry.pop("预警播报", None)
            return
        fields = [item["field"] for item in alerts]
        recipients = "、".join(dict.fromkeys(
            target
            for field in fields
            for target in ALERT_RECIPIENTS[field].split("、")
        ))
        entry["预警播报"] = {
            "播报编号": f"WB-{int(entry['id']):04d}",
            "观测时间": entry["观测时间"],
            "播报时刻": _now_text(),
            "播报对象": recipients,
            "预警内容": "；".join(item["reason"] for item in alerts),
            "触发原因": fields,
        }
