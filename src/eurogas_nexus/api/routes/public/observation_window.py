"""The bounded window of a daily observation list (storage, LNG).

The full GIE history was 1.1-1.4 MB a read on the demo store and passed the client's 10 s
timeout while ingestion ran (2026-11-17). A list read now returns the newest ``days`` gas
days, counted back from the newest observation in the store rather than from the clock, so
a store whose feed paused still shows its last weeks instead of an empty list. The window
is stated in the response (``meta.window``); a longer series is asked for with ``days``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

#: Default and maximum window (gas days, back from the newest observation).
DEFAULT_DAYS = 45
MAX_DAYS = 800


def bound(session, query, column, days: int) -> tuple[object, dict]:
    """``query`` limited to the ``days`` gas days ending at its newest ``column`` value.

    Returns the filtered query and the window to state in ``meta.window``.
    """

    from sqlalchemy import func

    newest = query.with_entities(func.max(column)).scalar()
    if newest is None:
        return query, {"days": days, "period_start_from_utc": None, "newest_period_start_utc": None}
    if isinstance(newest, str):  # sqlite without type affinity
        newest = datetime.fromisoformat(newest)
    aware = newest if newest.tzinfo else newest.replace(tzinfo=UTC)
    start = (aware - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    bound_value = start if newest.tzinfo else start.replace(tzinfo=None)
    return query.filter(column >= bound_value), {
        "days": days,
        "period_start_from_utc": start.isoformat(),
        "newest_period_start_utc": aware.isoformat(),
    }
