"""Aggregated usage of licensed source families (GOV-1, P6): count up, never one row per read."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import LicensedDataUseRecord

EXPORT_PREFIX = "export:"


def record_licensed_use(
    session: Session,
    *,
    principal_id: str,
    families: Iterable[str],
    surface: str,
    now_utc: datetime,
) -> int:
    """Count one read of each family by this principal through this surface today.

    An upsert on (day, principal, family, surface), so concurrent requests add up instead
    of racing. Returns the number of families counted. The caller commits.
    """

    rows = [
        {
            "usage_day": now_utc.date(),
            "principal_id": principal_id[:64],
            "source_family": family[:32],
            "surface": surface[:160],
            "reads": 1,
            "first_at_utc": now_utc,
            "last_at_utc": now_utc,
        }
        for family in sorted(set(families))
        if family
    ]
    if not rows:
        return 0
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - the product runs on PostgreSQL; tests on SQLite
        return _record_portably(session, rows)
    statement = insert(LicensedDataUseRecord).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["usage_day", "principal_id", "source_family", "surface"],
        set_={
            "reads": LicensedDataUseRecord.reads + 1,
            "last_at_utc": statement.excluded.last_at_utc,
        },
    )
    session.execute(statement)
    return len(rows)


def _record_portably(session: Session, rows: list[dict[str, Any]]) -> int:
    for values in rows:
        key = (values["usage_day"], values["principal_id"], values["source_family"],
               values["surface"])
        row = session.get(LicensedDataUseRecord, key)
        if row is None:
            session.add(LicensedDataUseRecord(**values))
        else:
            row.reads += 1
            row.last_at_utc = values["last_at_utc"]
    return len(rows)


def usage_by_family(session: Session, *, since: date) -> dict[str, dict[str, Any]]:
    """Per family since a day: distinct principals, reads, file exports and the last read."""

    is_export = LicensedDataUseRecord.surface.startswith(EXPORT_PREFIX)
    statement = (
        select(
            LicensedDataUseRecord.source_family,
            func.count(func.distinct(LicensedDataUseRecord.principal_id)),
            func.sum(LicensedDataUseRecord.reads),
            func.max(LicensedDataUseRecord.last_at_utc),
        )
        .where(LicensedDataUseRecord.usage_day >= since)
        .group_by(LicensedDataUseRecord.source_family)
    )
    usage: dict[str, dict[str, Any]] = {}
    for family, principals, reads, last in session.execute(statement):
        usage[family] = {
            "principals": int(principals or 0),
            "reads": int(reads or 0),
            "exports": 0,
            "last_read_utc": last.isoformat() if last is not None else None,
        }
    exports = (
        select(LicensedDataUseRecord.source_family, func.sum(LicensedDataUseRecord.reads))
        .where(LicensedDataUseRecord.usage_day >= since, is_export)
        .group_by(LicensedDataUseRecord.source_family)
    )
    for family, count in session.execute(exports):
        usage.setdefault(family, {"principals": 0, "reads": 0, "last_read_utc": None})
        usage[family]["exports"] = int(count or 0)
    return usage


__all__ = ["EXPORT_PREFIX", "record_licensed_use", "usage_by_family"]
