"""事故管理业务规则：状态流转、字段校验、筛选口径与看板取数都收在这里。

台账列表、运营概览、按期看板共用同一份归档判定：是否结案只看 status 是否为
「已结案」，行上的 pending 标记只作缓存、读时一律按当前状态重算，避免几处数不到一起。
"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "accident"
REQUIRED_FIELDS = ["事故编号", "事故设备", "事故类型"]
STATUS_ORDER = ["待上报", "已上报", "调查中", "已结案"]
CLOSED_STATUS = STATUS_ORDER[-1]
PENDING_STATUS_ALIAS = "待处理"
ACTION_RULES = {"上报事故": "已上报", "开展调查": "调查中", "结案归档": "已结案"}
NEGATIVE_ACTIONS = []

CODE_FIELD = "事故编号"
DEVICE_FIELD = "事故设备"
TYPE_FIELD = "事故类型"
CASUALTY_FIELD = "伤亡情况"
LOSS_FIELD = "直接损失"
TIME_FIELD = "发生时间"

# 重伤以上：出现「重伤」或「死亡」才算；空着的伤亡情况不算重伤，按待补处理
SEVERE_KEYWORDS = ("重伤", "死亡")
INCOMPLETE_TEXT = "待补"
UNKNOWN_MONTH = "未知月份"

_LOSS_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_MONTH_RE = re.compile(r"^(\d{4})[-/年.](\d{1,2})")
_DATE_RE = re.compile(r"^(\d{4})[-/年.](\d{1,2})(?:[-/月.](\d{1,2}))?")


def is_closed(row: dict[str, Any]) -> bool:
    """统一的结案（归档）判定：台账、概览、看板都从这里取口径。"""
    return str(row.get("status") or "").strip() == CLOSED_STATUS


def is_pending(row: dict[str, Any]) -> bool:
    """待办入口只收未结案事故，结案归档后立即移出。"""
    return not is_closed(row)


def is_severe(row: dict[str, Any]) -> bool:
    """重伤以上事故：伤亡情况里出现「重伤」或「死亡」；空着不算。"""
    text = str(row.get(CASUALTY_FIELD) or "").strip()
    if not text or text == INCOMPLETE_TEXT:
        return False
    return any(keyword in text for keyword in SEVERE_KEYWORDS)


def field_missing(row: dict[str, Any], field: str) -> bool:
    """伤亡、损失这类可后补字段：空着就是待补，不能当成 0。"""
    value = row.get(field)
    if value is None:
        return True
    return str(value).strip() == ""


def parse_loss(value: Any) -> float | None:
    """把「直接损失」解析成以元为单位的数值；空着或解析不出返回 None（待补）。"""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = _LOSS_NUMBER_RE.search(text)
    if match is None:
        return None
    amount = float(match.group())
    if "万元" in text or "万" in text:
        amount *= 10000
    return amount


def format_loss(amount_yuan: float) -> str:
    """损失合计的展示口径：过万按万元，不足万元按元。"""
    if amount_yuan >= 10000:
        text = f"{amount_yuan / 10000:.2f}".rstrip("0").rstrip(".")
        return f"{text} 万元"
    if float(amount_yuan).is_integer():
        return f"{int(amount_yuan)} 元"
    return f"{amount_yuan:.2f} 元"


def month_of(row: dict[str, Any]) -> str:
    """从「发生时间」取 YYYY-MM；解析不出归入「未知月份」。"""
    text = str(row.get(TIME_FIELD) or "").strip()
    match = _MONTH_RE.match(text)
    if match is None:
        return UNKNOWN_MONTH
    return f"{match.group(1)}-{int(match.group(2)):02d}"


def _time_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    """发生时间倒序：能解析的按日期排前面，没填时间的沉底。"""
    text = str(row.get(TIME_FIELD) or "").strip()
    match = _DATE_RE.match(text)
    if match is None:
        return (0, "")
    day = match.group(3) or "1"
    return (1, f"{match.group(1)}-{int(match.group(2)):02d}-{int(day):02d}")


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """按当前状态重算缓存标记，修掉历史数据里与状态对不上的 pending/abnormal。"""
    row["pending"] = is_pending(row)
    row["closed"] = is_closed(row)
    row["severe"] = is_severe(row)
    # abnormal 供运营概览「异常量」使用，口径与「重伤以上」保持一致
    row["abnormal"] = row["severe"]
    if field_missing(row, "事故状态"):
        row["事故状态"] = row.get("status")
    return row


def normalize_all() -> None:
    """批量校正全量事故行，供运营概览在不经过列表接口时也能拿到同一口径。"""
    for row in store.rows(MODULE):
        normalize_row(row)


class AccidentService:
    def _all_rows(self) -> list[dict[str, Any]]:
        rows = [normalize_row(row) for row in store.rows(MODULE)]
        rows.sort(key=_time_sort_key, reverse=True)
        return rows

    def _query_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        month: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._all_rows()
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get(CODE_FIELD, ""))
                or keyword in str(row.get(DEVICE_FIELD, ""))
            ]
        if status:
            if status == PENDING_STATUS_ALIAS:
                rows = [row for row in rows if is_pending(row)]
            else:
                rows = [row for row in rows if str(row.get("status") or "") == status]
        if month:
            rows = [row for row in rows if month_of(row) == month]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        month: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._query_rows(keyword=keyword, status=status, month=month)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_stats(self) -> dict[str, Any]:
        """台账顶部统计卡：与概览、看板同源，取数失败重试后仍是这一份。"""
        rows = self._all_rows()
        by_status = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            name = str(row.get("status") or "")
            if name in by_status:
                by_status[name] += 1
        return {
            "total": len(rows),
            "pending": sum(1 for row in rows if is_pending(row)),
            "closed": by_status[CLOSED_STATUS],
            "severe": sum(1 for row in rows if is_severe(row)),
            "by_status": by_status,
        }

    def _month_bucket(self, month: str) -> dict[str, Any]:
        rows = [row for row in self._all_rows() if month_of(row) == month]
        type_counts: dict[str, int] = {}
        loss_total = 0.0
        loss_missing = 0
        for row in rows:
            accident_type = str(row.get(TYPE_FIELD) or "").strip() or "未分类"
            type_counts[accident_type] = type_counts.get(accident_type, 0) + 1
            loss = parse_loss(row.get(LOSS_FIELD))
            if loss is None:
                loss_missing += 1
            else:
                loss_total += loss
        distribution = [
            {"type": name, "count": count}
            for name, count in sorted(
                type_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ]
        return {
            "month": month,
            "count": len(rows),
            "severe_count": sum(1 for row in rows if is_severe(row)),
            "loss_total": round(loss_total, 2),
            "loss_total_text": format_loss(round(loss_total, 2)),
            "loss_missing": loss_missing,
            "types": distribution,
            "items": rows,
        }

    def board_overview(self) -> dict[str, Any]:
        """按期看板：左侧月份分段，逐月给出去重后的汇总，不重复扫账。"""
        normalize_all()
        months = {month_of(row) for row in store.rows(MODULE)}
        # 有发生时间的月份倒序（最近在前），未知月份始终沉底
        ordered = sorted((name for name in months if name != UNKNOWN_MONTH), reverse=True)
        if UNKNOWN_MONTH in months:
            ordered.append(UNKNOWN_MONTH)
        buckets = []
        for month in ordered:
            bucket = self._month_bucket(month)
            bucket.pop("items")
            buckets.append(bucket)
        return {"months": buckets}

    def board_month(self, month: str) -> dict[str, Any] | None:
        """单月下钻：类型分布、损失合计、重伤以上清单与当月事故全量。"""
        normalize_all()
        available = {month_of(row) for row in store.rows(MODULE)}
        if month not in available:
            return None
        bucket = self._month_bucket(month)
        bucket["severe_items"] = [row for row in bucket["items"] if is_severe(row)]
        return bucket

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return normalize_row(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 伤亡、损失允许先空着：登记为待补而不是补成 0
        for field in (CASUALTY_FIELD, LOSS_FIELD, TIME_FIELD, "调查结论"):
            entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["事故状态"] = STATUS_ORDER[0]
        rows.append(entry)
        return normalize_row(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"事故记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于事故管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["事故状态"] = target
        # pending/closed/abnormal 统一按状态与伤亡重算，结案立即离开待处理
        return normalize_row(entry), f"事故记录已{action}"
