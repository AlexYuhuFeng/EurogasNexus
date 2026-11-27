"""The facts ``nexus status`` needs from inside the product (``eurogas_nexus.cli.desk_status``).

It reads only operational metadata through the product's own code: the database revision
against the one this version needs, the data scheduler's heartbeat, the freshness contract of
every connected source (``application/freshness_contract.py``, the same judgement the Sources
page shows), and the newest backup the gated upgrade would accept. It changes nothing and
returns no setting, URL or credential; each part is read on its own, so one failing read never
hides the others.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    from eurogas_nexus.domain.dataops.contracts import as_utc

    return as_utc(value).isoformat()


def _age_minutes(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return round(max(0.0, (now - moment).total_seconds()) / 60.0, 1)


def connected_rows(rows: list[dict[str, Any]], runtime_states: dict[str, dict]) -> list[dict]:
    """Rows of sources that are connected: they delivered once, or the scheduler runs them.

    A registered source the desk never switched on (no key, not approved) is not connected
    and is left out, so the status lists what the desk actually relies on. Pure.
    """

    connected: list[dict] = []
    for row in rows:
        state = runtime_states.get(row["source_id"]) or {}
        if row.get("last_received_at_utc") or state.get("enabled"):
            connected.append(row)
    return connected


def collect(now: datetime | None = None) -> dict[str, Any]:
    """Every fact, each part independently: one failing read never hides the others."""

    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    now = now or datetime.now(UTC)
    report: dict[str, Any] = {
        "generated_at_utc": now.isoformat(),
        "database": {"reachable": False, "required_revision": DB_SCHEMA_REVISION},
        "scheduler": {"last_heartbeat_at_utc": None, "age_seconds": None},
        "sources": [],
        "backup_marker": None,
        "errors": [],
    }
    from sqlalchemy import text

    from eurogas_nexus.db.session import get_session_factory

    factory = get_session_factory()
    try:
        with factory() as session:
            revision = session.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
            report["database"].update(reachable=True, revision=revision)
    except Exception as exc:  # noqa: BLE001 - reported as a fact
        report["errors"].append(f"database: {exc.__class__.__name__}")
        return report

    try:
        from eurogas_nexus.db.models import DataOperationsHeartbeatRecord

        with factory() as session:
            row = session.get(DataOperationsHeartbeatRecord, "primary")
            last = _iso(row.last_heartbeat_at_utc) if row else None
        report["scheduler"] = {
            "last_heartbeat_at_utc": last,
            "age_seconds": None
            if last is None
            else round((_age_minutes(last, now) or 0.0) * 60.0, 0),
        }
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"scheduler: {exc.__class__.__name__}")

    try:
        from eurogas_nexus.application.freshness_contract import freshness_contract
        from eurogas_nexus.db.models import SourceRuntimeStateRecord
        from eurogas_nexus.db.repositories.dataops import source_runtime_payload
        from eurogas_nexus.domain.dataops.registry import source_definitions

        providers = {item.source_id: item.provider for item in source_definitions()}

        with factory() as session:
            states = {
                row.source_id: source_runtime_payload(row)
                for row in session.query(SourceRuntimeStateRecord).all()
            }
            rows = freshness_contract(session, now=now, runtime_states=states)
        report["sources"] = [
            {
                "source_id": row["source_id"],
                "provider": providers.get(row["source_id"], row["source_id"]),
                "dataset": row["dataset"],
                "state": row["state"],
                "last_received_at_utc": row["last_received_at_utc"],
                "age_minutes": _age_minutes(row["last_received_at_utc"], now),
                "next_expected_overdue": bool(row.get("next_expected_overdue")),
            }
            for row in connected_rows(rows, states)
        ]
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"sources: {exc.__class__.__name__}")

    try:
        from eurogas_nexus.application.database_upgrade import latest_backup

        with factory() as session:
            marker = latest_backup(session)
        if marker is not None:
            report["backup_marker"] = {
                "reference": marker.reference,
                "kind": marker.kind,
                "recorded_at_utc": marker.recorded_at_utc.isoformat(),
            }
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"backup marker: {exc.__class__.__name__}")
    return report
