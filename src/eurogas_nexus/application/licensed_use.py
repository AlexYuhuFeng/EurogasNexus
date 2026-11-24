"""Licensed-data usage and the export decision for files (GOV-1, lesson P6).

* **Usage.** Each request's meter (``governance/usage.py``) holds the licensed source
  families its entitlement checks let it read. When the request ends, one aggregated row per
  family is counted up in ``licensed_data_use`` (day, principal, family, surface). This is a
  read-side record, so it is best-effort: a read never fails because its usage row could not
  be written (the governed writes of P5 are the ones that fail closed).
* **Files.** A CSV, XLSX or PDF report applies the existing ``ExportDecision`` to the
  licensed families its rows were read from (``governance/entitlement.file_export_decision``):
  no licensed data, or only families whose current licence allows redistribution, is
  allowed; a known licensed family restricts the file to internal use and the file says so;
  a family the governance register does not know denies the file (fail closed).

许可数据：按日聚合记录使用量；导出文件（CSV/XLSX/PDF）按其数据来源的许可应用导出决策。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.governance.entitlement import FileExportDecision, file_export_decision
from eurogas_nexus.governance.usage import LicensedUseMeter

logger = logging.getLogger(__name__)

#: Days of usage shown beside each licence in the licence register.
USAGE_WINDOW_DAYS = 30


def usage_surface(route: str, meter: LicensedUseMeter) -> str:
    """The surface a request's reads are counted under: its route, marked when it was a file."""

    if meter.export_format:
        return f"export:{meter.export_format} {route}"
    return route


def licensed_families(families: Iterable[str]) -> set[str]:
    """The commercially licensed families among those a request read.

    The meter notes every family that needs a grant; the firm's own data (an ETRM import,
    the demo desk) needs one too but is not a vendor's licensed data.
    """

    from eurogas_nexus.domain.dataops.entitlement import COMMERCIAL_SOURCE_FAMILIES

    known = {family.upper(): family for family in COMMERCIAL_SOURCE_FAMILIES}
    return {known[f.upper()] for f in families if f and f.upper() in known}


def record_request_use(
    meter: LicensedUseMeter, *, principal_id: str | None, route: str, now: datetime | None = None
) -> int:
    """Count the licensed families one request read (best-effort; returns families counted)."""

    families = licensed_families(meter.families)
    if not families or not principal_id:
        return 0
    try:
        from eurogas_nexus.db.repositories.licensed_use import record_licensed_use
        from eurogas_nexus.db.session import get_session_factory, resolve_database_url

        if resolve_database_url() is None:
            return 0
        with get_session_factory()() as session:
            counted = record_licensed_use(
                session,
                principal_id=principal_id,
                families=families,
                surface=usage_surface(route, meter),
                now_utc=now or datetime.now(UTC),
            )
            session.commit()
            return counted
    except Exception as exc:  # noqa: BLE001 - usage of a read is best-effort, never the read
        logger.warning("licensed data use not recorded: %s", exc.__class__.__name__)
        return 0


def file_decision(families: Iterable[str], *, today: date | None = None) -> FileExportDecision:
    """The export decision for a file whose rows were read from these licensed families.

    A licence's redistribution flag is read from the licence register; when the register
    cannot be read no family counts as redistributable (the stricter answer).
    """

    families = licensed_families(families)
    registered: set[str] = set()
    redistributable: set[str] = set()
    if families:
        try:
            registered, redistributable = _current_licences(
                families, today or datetime.now(UTC).date()
            )
        except Exception as exc:  # noqa: BLE001 - unreadable register: nothing registered
            logger.warning("licence register not read for export: %s", exc.__class__.__name__)
    return file_export_decision(
        families, redistributable=redistributable, registered=registered
    )


def _current_licences(families: set[str], today: date) -> tuple[set[str], set[str]]:
    """Of these families: those with a current licence, and those it lets be redistributed."""

    from eurogas_nexus.db.models import MarketDataLicenceRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return set(), set()
    by_upper = {family.upper(): family for family in families}
    registered: set[str] = set()
    redistributable: set[str] = set()
    with get_session_factory()() as session:
        for row in session.query(MarketDataLicenceRecord):
            family = by_upper.get(str(row.source_family).upper())
            if family is None:
                continue
            if row.valid_from <= today and (row.valid_to is None or row.valid_to >= today):
                registered.add(family)
                if bool(row.redistribution_allowed):
                    redistributable.add(family)
    return registered, redistributable


def licence_usage(session: Any, *, today: date | None = None) -> dict[str, dict[str, Any]]:
    """Usage per licensed family over the last ``USAGE_WINDOW_DAYS`` days (for the register)."""

    from eurogas_nexus.db.repositories.licensed_use import usage_by_family

    since = (today or datetime.now(UTC).date()) - timedelta(days=USAGE_WINDOW_DAYS - 1)
    return usage_by_family(session, since=since)


__all__ = [
    "USAGE_WINDOW_DAYS",
    "file_decision",
    "licence_usage",
    "licensed_families",
    "record_request_use",
    "usage_surface",
]
