"""Shared row-matching helpers for the analysis package (private).

这些是快照行匹配的通用小工具（关键词命中、时间窗过滤、宽松时间解析、
去重），供 builders / glossary_* 各模块复用；均为纯函数，不依赖模型。
"""

from __future__ import annotations

from datetime import UTC, datetime


def _contains_any(
    row: dict,
    keys: list[str],
    *,
    fields: tuple[str, ...] | None = None,
) -> bool:
    """Whether any key appears (case-insensitive) in the row's haystack.

    检查行内是否命中任一关键词：未指定 fields 时搜索全部值，
    指定时只搜索这些字段，避免误命中无关字段。

    Args:
        row: Snapshot row (dict).
        keys: Keywords to search for.
        fields: Fields to search; None = all values.

    Returns:
        True when any non-empty key is found; False for an empty key list.
    """

    normalized = [key.lower() for key in keys if key]
    if not normalized:
        return False
    values = [row.get(field, "") for field in fields] if fields else row.values()
    haystack = " ".join(str(value) for value in values).lower()
    return any(key in haystack for key in normalized)


def _row_matches_duration(
    row: dict,
    *,
    duration_start_utc: datetime | None,
    duration_end_utc: datetime | None,
    start_fields: tuple[str, ...],
    end_fields: tuple[str, ...],
) -> bool:
    """Whether the row's time window overlaps the requested duration.

    时间窗重叠判定（半开区间）：行内起止时间任取字段组中的第一个可解析值；
    请求未给边界时恒为 True；行时间缺失时按"可解析的部分"宽松处理。

    Args:
        row: Snapshot row (dict).
        duration_start_utc: Requested window start, or None.
        duration_end_utc: Requested window end, or None.
        start_fields: Candidate fields for the row start.
        end_fields: Candidate fields for the row end.

    Returns:
        True when both windows overlap (or the request is unbounded).
    """

    if duration_start_utc is None and duration_end_utc is None:
        return True
    row_start = _first_datetime(row, start_fields)
    row_end = _first_datetime(row, end_fields) or row_start
    if duration_start_utc and row_end and row_end < duration_start_utc:
        return False
    if duration_end_utc and row_start and row_start > duration_end_utc:
        return False
    return True


def _first_datetime(row: dict, fields: tuple[str, ...]) -> datetime | None:
    """Return the first parseable datetime among the candidate fields."""

    for field in fields:
        parsed = _parse_datetime(row.get(field))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: object) -> datetime | None:
    """Lenient ISO datetime parsing: aware if possible, else assumed UTC.

    宽松解析：接受 datetime 实例与 ISO 字符串（含 ``Z`` 后缀）；naive
    值按 UTC 解释（与全仓 ISO 契约一致）；解析失败返回 None 而非抛错。

    Args:
        value: Datetime, ISO string, or None.

    Returns:
        Aware UTC datetime, or None when unparseable.
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _unique(values: list[str]) -> list[str]:
    """Deduplicate preserving first-seen order."""

    return list(dict.fromkeys(values))
