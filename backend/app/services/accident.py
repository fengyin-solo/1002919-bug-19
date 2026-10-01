"""事故管理业务规则：状态流转、字段校验与筛选口径都收在这里。

归档判定全模块只有一条：status 走到「已结案」即视为结案归档。
台账列表、按期看板、运营概览的待办口径都从这条规则取数，避免各算各的。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "accident"
REQUIRED_FIELDS = ["事故编号", "事故设备", "事故类型"]
OPTIONAL_FIELDS = ["伤亡情况", "直接损失", "发生时间", "调查结论", "事故状态"]
STATUS_ORDER = ["待上报", "已上报", "调查中", "已结案"]
ACTION_RULES = {"上报事故": "已上报", "开展调查": "调查中", "结案归档": "已结案"}
NEGATIVE_ACTIONS: list[str] = []

CLOSED_STATUS = "已结案"
UNDATED_MONTH = "undated"
SERIOUS_KEYWORDS = ("死亡", "重伤", "死")
LOSS_PATTERN = re.compile(r"\d+(?:\.\d+)?")
MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})")


def is_archived(entry: dict[str, Any]) -> bool:
    """唯一的归档判定：结案归档后不再计入待办，所有取数都以此为准。"""
    return entry.get("status") == CLOSED_STATUS


def is_pending(entry: dict[str, Any]) -> bool:
    """待办口径：没走到结案归档的事故都算待办。"""
    return not is_archived(entry)


def month_of(entry: dict[str, Any]) -> str | None:
    """发生时间归到月份（YYYY-MM）；没填或格式不对返回 None。"""
    raw = str(entry.get("发生时间") or "").strip()
    match = MONTH_PATTERN.match(raw)
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def occurred_on(entry: dict[str, Any]) -> date | None:
    raw = str(entry.get("发生时间") or "").strip()[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_loss(value: Any) -> float | None:
    """直接损失（万元）：空着或写不出数字的一律按待补处理，不当成零。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = LOSS_PATTERN.search(str(value))
    return float(match.group()) if match else None


def is_serious(casualty: str) -> bool:
    """重伤以上：伤亡情况里出现死亡/重伤字样即单独挑出。"""
    return any(word in casualty for word in SERIOUS_KEYWORDS)


def _sort_by_occurred(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """发生时间新的在前；没填时间的排在最后，不混进有日期的记录里。"""
    dated = [row for row in rows if occurred_on(row) is not None]
    undated = [row for row in rows if occurred_on(row) is None]
    dated.sort(key=lambda row: occurred_on(row) or date.min, reverse=True)
    return dated + undated


class AccidentService:
    @staticmethod
    def _sync(row: dict[str, Any]) -> dict[str, Any]:
        """台账读出来的每一行都按归档判定刷新待办标记，保证和概览一个口径。"""
        row["pending"] = is_pending(row)
        return row

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        device: str | None = None,
        accident_type: str | None = None,
        status: str | None = None,
        month: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._sync(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("事故编号", ""))]
        if device:
            rows = [row for row in rows if device in str(row.get("事故设备", ""))]
        if accident_type:
            rows = [row for row in rows if accident_type in str(row.get("事故类型", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if month == UNDATED_MONTH:
            rows = [row for row in rows if month_of(row) is None]
        elif month:
            rows = [row for row in rows if month_of(row) == month]
        rows = _sort_by_occurred(rows)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._sync(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            if field in values:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = is_pending(entry)
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"事故记录 {entry_id} 不存在或已归档"
        if is_archived(entry):
            return None, f"事故记录 {entry_id} 已结案归档，不再接受新的动作"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于事故管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = is_pending(entry)
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"事故记录已{action}"

    def board(self) -> dict[str, Any]:
        """按期视图看板：按月分段聚合，与台账共用同一份行数据。"""
        rows = [self._sync(row) for row in store.rows(MODULE)]
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            buckets.setdefault(month_of(row) or UNDATED_MONTH, []).append(row)
        months = [
            self._month_bucket(key, buckets[key])
            for key in sorted((key for key in buckets if key != UNDATED_MONTH), reverse=True)
        ]
        if UNDATED_MONTH in buckets:
            months.append(self._month_bucket(UNDATED_MONTH, buckets[UNDATED_MONTH]))
        return {"summary": self._summary(rows), "months": months}

    def _month_bucket(self, key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        label = "时间待补" if key == UNDATED_MONTH else f"{key[:4]}年{int(key[5:7])}月"
        type_counts: dict[str, int] = {}
        loss_total = 0.0
        loss_missing = 0
        casualty_missing = 0
        serious: list[dict[str, Any]] = []
        for row in _sort_by_occurred(rows):
            accident_type = str(row.get("事故类型") or "").strip() or "类型待补"
            type_counts[accident_type] = type_counts.get(accident_type, 0) + 1
            loss = parse_loss(row.get("直接损失"))
            if loss is None:
                loss_missing += 1
            else:
                loss_total += loss
            casualty = str(row.get("伤亡情况") or "").strip()
            if not casualty:
                casualty_missing += 1
            elif is_serious(casualty):
                serious.append({
                    "id": row.get("id"),
                    "事故编号": row.get("事故编号"),
                    "事故设备": row.get("事故设备"),
                    "事故类型": row.get("事故类型"),
                    "伤亡情况": row.get("伤亡情况"),
                    "发生时间": row.get("发生时间"),
                    "status": row.get("status"),
                })
        return {
            "month": key,
            "label": label,
            "total": len(rows),
            "pending": sum(1 for row in rows if is_pending(row)),
            "closed": sum(1 for row in rows if is_archived(row)),
            "type_distribution": [
                {"type": name, "count": count}
                for name, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "loss_total": round(loss_total, 2),
            "loss_missing": loss_missing,
            "casualty_missing": casualty_missing,
            "serious": serious,
        }

    @staticmethod
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        by_status = {status: 0 for status in STATUS_ORDER}
        serious_total = 0
        for row in rows:
            status = str(row.get("status") or "")
            by_status[status] = by_status.get(status, 0) + 1
            if is_serious(str(row.get("伤亡情况") or "")):
                serious_total += 1
        return {
            "total": len(rows),
            "pending": sum(1 for row in rows if is_pending(row)),
            "closed": sum(1 for row in rows if is_archived(row)),
            "serious_total": serious_total,
            "by_status": by_status,
        }


# 待办判定登记到数据仓库：运营概览与事故台账共用同一条归档口径。
store.set_pending_rule(MODULE, is_pending)
