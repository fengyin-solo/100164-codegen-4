"""气象观测业务规则：录入校验、同时刻合并、预警阈值与播报互证都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "weather"
ALERT_MODULE = "weather_alert"

REQUIRED_FIELDS = ["观测时间", "能见度", "风速", "风向", "跑道视程"]

# 物理量取值范围：能见度/跑道视程单位为米，风速单位为米/秒。
VISIBILITY_MIN, VISIBILITY_MAX = 0.0, 10000.0
WIND_SPEED_MIN, WIND_SPEED_MAX = 0.0, 100.0
RVR_MIN, RVR_MAX = 0.0, 2000.0

# 预警线：低于（风速为不低于）阈值即触发，红色严于橙色。
VISIBILITY_RED, VISIBILITY_ORANGE = 500.0, 1000.0
RVR_RED, RVR_ORANGE = 300.0, 550.0
WIND_RED, WIND_ORANGE = 25.0, 15.0

DEFAULT_BROADCAST_TARGETS = "塔台、机坪管制、运行指挥中心"

# 风向允许 0～360 度，或十六方位（可带“风”字），另保留“静风”。
COMPASS_POINTS = {
    "北", "东北偏北", "东北", "东北偏东", "东", "东南偏东", "东南", "东南偏南",
    "南", "西南偏南", "西南", "西南偏西", "西", "西北偏西", "西北", "西北偏北",
    "静风",
}

ALERT_TYPE_VISIBILITY = "能见度"
ALERT_TYPE_WIND = "风速"
ALERT_TYPE_RVR = "跑道视程"
ACTIVE_STATUS = "预警中"
RESOLVED_STATUS = "已解除"


class WeatherService:
    def list_observations(self) -> list[dict[str, Any]]:
        """观测记录按观测时间倒序返回，并挂上联播预警，保证两份清单可互相印证。"""
        rows = sorted(
            store.rows(MODULE),
            key=lambda row: str(row.get("观测时间", "")),
            reverse=True,
        )
        return [self._with_alerts(row) for row in rows]

    def get_observation(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._with_alerts(entry) if entry else None

    def list_alerts(self) -> dict[str, Any]:
        """预警播报清单：先播报的在前不如最新播报在前，按播报时刻倒序。"""
        rows = sorted(
            store.rows(ALERT_MODULE),
            key=lambda row: (str(row.get("播报时刻", "")), int(row.get("id", 0))),
            reverse=True,
        )
        return {"items": rows, "total": len(rows)}

    def create_observation(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, int]]:
        """录入或合并一条观测；校验不过时原样拒绝，不落库、不产生预警。"""
        errors, cleaned = self._validate(values)
        if errors:
            return None, errors, {}

        observed_at = cleaned["观测时间"]
        existing = self._find_by_time(observed_at)
        if existing is None:
            rows = store.rows(MODULE)
            entry: dict[str, Any] = {"id": max((int(r.get("id", 0)) for r in rows), default=0) + 1}
            rows.append(entry)
            merged = False
        else:
            entry = existing
            merged = True

        entry.update(cleaned)
        alert_summary = self._sync_alerts(
            entry, broadcast_targets=str(values.get("播报对象") or "").strip()
        )
        self._refresh_flags(entry)
        entry["_merged"] = merged
        return entry, [], alert_summary

    # ---- 校验 ----------------------------------------------------------

    def _validate(self, values: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        errors: list[str] = []
        cleaned: dict[str, Any] = {}

        observed_raw = values.get("观测时间")
        observed_at = self._parse_time(observed_raw)
        if observed_at is None:
            if observed_raw is None or not str(observed_raw).strip():
                errors.append("观测时间为空，无法保存")
            else:
                errors.append(f"观测时间「{observed_raw}」无法识别，应为 YYYY-MM-DD HH:MM 形式")
        else:
            cleaned["观测时间"] = observed_at

        visibility, msg = self._read_number("能见度", values.get("能见度"), VISIBILITY_MIN, VISIBILITY_MAX, "米")
        if msg:
            errors.append(msg)
        else:
            cleaned["能见度"] = visibility

        wind_speed, msg = self._read_number("风速", values.get("风速"), WIND_SPEED_MIN, WIND_SPEED_MAX, "米/秒")
        if msg:
            errors.append(msg)
        else:
            cleaned["风速"] = wind_speed

        wind_direction = self._normalize_direction(values.get("风向"))
        if wind_direction is None:
            raw = values.get("风向")
            if raw is None or not str(raw).strip():
                errors.append("风向为空，无法保存")
            else:
                errors.append(f"风向「{raw}」无法识别，请使用 0～360 度或如「西北风」的十六方位")
        else:
            cleaned["风向"] = wind_direction

        rvr, msg = self._read_number("跑道视程", values.get("跑道视程"), RVR_MIN, RVR_MAX, "米")
        if msg:
            errors.append(msg)
        else:
            cleaned["跑道视程"] = rvr

        return errors, cleaned

    @staticmethod
    def _read_number(
        label: str, raw: Any, low: float, high: float, unit: str
    ) -> tuple[float | None, str | None]:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None, f"{label}为空，无法保存"
        if isinstance(raw, bool):
            return None, f"{label}「{raw}」不是有效数值，无法保存"
        try:
            number = float(str(raw).strip())
        except (TypeError, ValueError):
            return None, f"{label}「{raw}」不是有效数值，无法保存"
        if number < low or number > high:
            return None, f"{label} {raw} 超出物理范围（{_fmt(low)}～{_fmt(high)} {unit}），拒绝保存"
        return number, None

    @staticmethod
    def _parse_time(raw: Any) -> str | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        try:
            moment = datetime.fromisoformat(text.replace("T", " "))
        except ValueError:
            return None
        return moment.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _normalize_direction(raw: Any) -> str | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        try:
            degree = float(text)
        except ValueError:
            point = text[:-1] if text.endswith("风") else text
            return text if point in COMPASS_POINTS else None
        if degree < 0 or degree > 360:
            return None
        return f"{degree:g}°"

    # ---- 预警同步 ------------------------------------------------------

    def _sync_alerts(self, entry: dict[str, Any], *, broadcast_targets: str) -> dict[str, int]:
        """以观测时刻最新实况为准同步预警：新增、更新、解除，绝不重复叠加。"""
        breaches = self._breaches(entry)
        alerts = store.rows(ALERT_MODULE)
        current = {
            str(a.get("预警类型")): a
            for a in alerts
            if int(a.get("观测记录", 0)) == int(entry["id"])
        }
        summary = {"created": 0, "updated": 0, "resolved": 0}

        for breach in breaches:
            alert = current.get(breach["预警类型"])
            if alert is None:
                alert = {"id": max((int(a.get("id", 0)) for a in alerts), default=0) + 1}
                alert.update({
                    "观测记录": entry["id"],
                    "观测时间": entry["观测时间"],
                    "预警类型": breach["预警类型"],
                    "播报对象": broadcast_targets or DEFAULT_BROADCAST_TARGETS,
                    "播报时刻": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "pending": False,
                    "abnormal": True,
                })
                alerts.append(alert)
                summary["created"] += 1
            else:
                summary["updated"] += 1
            alert["status"] = ACTIVE_STATUS
            alert["预警等级"] = breach["预警等级"]
            alert["触发实况"] = breach["触发实况"]
            alert["预警阈值"] = breach["预警阈值"]
            alert["预警内容"] = breach["预警内容"]

        active_types = {b["预警类型"] for b in breaches}
        for alert_type, alert in current.items():
            if alert_type not in active_types and alert.get("status") == ACTIVE_STATUS:
                alert["status"] = RESOLVED_STATUS
                alert["abnormal"] = False
                summary["resolved"] += 1
        return summary

    @staticmethod
    def _breaches(entry: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        visibility = float(entry["能见度"])
        if visibility < VISIBILITY_RED:
            findings.append(_breach(
                ALERT_TYPE_VISIBILITY, "红色", visibility, VISIBILITY_RED,
                f"能见度 {_fmt(visibility)} 米低于红色预警线 {_fmt(VISIBILITY_RED)} 米，低能见度运行风险高",
            ))
        elif visibility < VISIBILITY_ORANGE:
            findings.append(_breach(
                ALERT_TYPE_VISIBILITY, "橙色", visibility, VISIBILITY_ORANGE,
                f"能见度 {_fmt(visibility)} 米低于橙色预警线 {_fmt(VISIBILITY_ORANGE)} 米，请注意低能见度运行",
            ))

        rvr = float(entry["跑道视程"])
        if rvr < RVR_RED:
            findings.append(_breach(
                ALERT_TYPE_RVR, "红色", rvr, RVR_RED,
                f"跑道视程 {_fmt(rvr)} 米低于红色预警线 {_fmt(RVR_RED)} 米，跑道起降标准受限",
            ))
        elif rvr < RVR_ORANGE:
            findings.append(_breach(
                ALERT_TYPE_RVR, "橙色", rvr, RVR_ORANGE,
                f"跑道视程 {_fmt(rvr)} 米低于橙色预警线 {_fmt(RVR_ORANGE)} 米，请关注跑道视程变化",
            ))

        wind = float(entry["风速"])
        if wind >= WIND_RED:
            findings.append(_breach(
                ALERT_TYPE_WIND, "红色", wind, WIND_RED,
                f"风速 {_fmt(wind)} 米/秒达到红色预警线 {_fmt(WIND_RED)} 米/秒，大风危及地面作业",
            ))
        elif wind >= WIND_ORANGE:
            findings.append(_breach(
                ALERT_TYPE_WIND, "橙色", wind, WIND_ORANGE,
                f"风速 {_fmt(wind)} 米/秒达到橙色预警线 {_fmt(WIND_ORANGE)} 米/秒，请注意防风",
            ))
        return findings

    # ---- 辅助 ----------------------------------------------------------

    def _find_by_time(self, observed_at: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("观测时间")) == observed_at:
                return row
        return None

    @staticmethod
    def _refresh_flags(entry: dict[str, Any]) -> None:
        active = [
            a for a in store.rows(ALERT_MODULE)
            if int(a.get("观测记录", 0)) == int(entry["id"]) and a.get("status") == ACTIVE_STATUS
        ]
        entry["status"] = ACTIVE_STATUS if active else "正常"
        entry["abnormal"] = bool(active)
        entry["pending"] = False

    @staticmethod
    def _with_alerts(entry: dict[str, Any]) -> dict[str, Any]:
        detail = dict(entry)
        linked = [
            dict(a) for a in store.rows(ALERT_MODULE)
            if int(a.get("观测记录", 0)) == int(entry.get("id", 0))
        ]
        linked.sort(key=lambda a: (str(a.get("播报时刻", "")), int(a.get("id", 0))), reverse=True)
        detail["预警播报"] = linked
        detail.pop("_merged", None)
        return detail


def _breach(alert_type: str, level: str, value: float, threshold: float, content: str) -> dict[str, Any]:
    unit = "米/秒" if alert_type == ALERT_TYPE_WIND else "米"
    comparator = "不低于" if alert_type == ALERT_TYPE_WIND else "低于"
    return {
        "预警类型": alert_type,
        "预警等级": level,
        "触发实况": f"{_fmt(value)} {unit}",
        "预警阈值": f"{comparator}{_fmt(threshold)} {unit}",
        "预警内容": content,
    }


def _fmt(number: float) -> str:
    return f"{number:g}"
