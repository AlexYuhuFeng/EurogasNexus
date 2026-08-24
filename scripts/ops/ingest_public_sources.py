"""Explicit live ingestion for public/source-keyed V1 data sources.

This script is operator-invoked only. It performs live HTTP reads, writes
normalized rows to PostgreSQL, never prints secrets, and archives the raw
provider payload for lineage (raw -> canonical audit trail).

Fail-closed gates (audit item 4): every live source passes the entitlement
check, and export-restricted sources (ENTSOG, GIE) additionally require a
certification record whose gate allows live; blocked sources are recorded as
failed runs, never silently skipped.

Ingestion is re-run safe (idempotent): observation rows upsert by natural
primary key with first-seen ``observed_at_utc``, and reference snapshots
replace only the ENTSOG scope, only when the new payload is non-empty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError

from eurogas_nexus.db.models import (
    CapacityObservationRecord,
    FlowObservationRecord,
    FxObservationRecord,
    IngestionRunRecord,
    LngObservationRecord,
    MarketObservationRecord,
    ProviderCredentialRecord,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    ReferenceTsoAccessPoint,
    StorageObservationRecord,
)
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    replace_reference_snapshot,
    upsert_observation_rows,
)
from eurogas_nexus.db.session import (
    create_session_factory,
    get_engine,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.ingestion.public_sources import (
    ecb_fx_observations_from_xml,
    ecb_market_observations_from_xml,
    entsog_capacity_observations_from_json,
    entsog_flow_observations_from_json,
    entsog_market_hubs_from_connectionpoints,
    entsog_reference_facilities_from_connectionpoints,
    entsog_reference_nodes_from_connectionpoints,
    entsog_tso_access_points_from_json,
    gie_lng_observations_from_json,
    gie_storage_observations_from_json,
)

# Sources that are export-restricted and therefore require certification
# before live ingestion (ECB public reference rates are fully public).
CERTIFICATION_REQUIRED_SOURCES = frozenset({"ENTSOG", "GIE", "GIE-AGSI", "GIE-ALSI"})
# Raw payloads larger than this are not archived (warning only).
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ENTSOG_OPERATIONAL_URL = "https://transparency.entsog.eu/api/v1/operationaldatas"
ENTSOG_CONNECTION_POINTS_URL = "https://transparency.entsog.eu/api/v1/connectionpoints"
ENTSOG_OPERATOR_POINT_DIRECTIONS_URL = (
    "https://transparency.entsog.eu/api/v1/operatorpointdirections"
)
GIE_AGSI_EU_URL = "https://agsi.gie.eu/api/data/EU"
GIE_ALSI_EU_URL = "https://alsi.gie.eu/api/data/EU"
ENTSOG_CAPACITY_INDICATORS = (
    "Firm Technical",
    "Firm Booked",
    "Interruptible Booked",
    "Nomination",
)


def main() -> int:
    """    Run public-source ingestion for registered, certified sources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=(
            "all",
            "ecb",
            "entsog",
            "entsog-capacity",
            "entsog-reference",
            "gie-agsi",
            "gie-alsi",
        ),
        action="append",
        default=[],
        help="Source to ingest. May be repeated. Default: all.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Bounded record limit per source.")
    parser.add_argument("--json", action="store_true", help="Print a JSON report.")
    args = parser.parse_args()

    database_url = resolve_database_url()
    if not database_url:
        return _emit({"ok": False, "error": "Database URL is missing."}, as_json=args.json)

    selected = set(args.source or ["all"])
    if "all" in selected:
        selected = {
            "ecb",
            "entsog",
            "entsog-capacity",
            "entsog-reference",
            "gie-agsi",
            "gie-alsi",
        }

    engine = None
    session_factory = None
    started = datetime.now(UTC)
    report: dict[str, Any] = {
        "ok": False,
        "redacted_database_url": redact_database_url(database_url),
        "sources": {},
        "warnings": [],
    }
    try:
        engine = get_engine(database_url)
        session_factory = create_session_factory(engine)
        with session_factory() as gate_session:
            gate_families = (
                ("ENTSOG", {"entsog", "entsog-capacity", "entsog-reference"}),
                ("GIE", {"gie-agsi", "gie-alsi"}),
            )
            for family, names in gate_families:
                if not selected & names:
                    continue
                blockers = _gate_blockers(gate_session, family)
                if blockers:
                    _record_run(
                        gate_session,
                        family,
                        "failed",
                        started,
                        0,
                        "gate:" + ",".join(blockers),
                    )
                    report["warnings"].append(
                        f"{family} live ingestion blocked (fail-closed): "
                        + ",".join(blockers)
                    )
                    selected -= names
            gate_session.commit()
        gie_key = _resolve_gie_key(session_factory) if selected & {"gie-agsi", "gie-alsi"} else None
        if selected & {"gie-agsi", "gie-alsi"} and not gie_key:
            report["warnings"].append("GIE key missing; skipped GIE AGSI/ALSI ingestion.")
            selected -= {"gie-agsi", "gie-alsi"}

        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "EurogasNexus/0.5 preview public-source-ingestion"},
        ) as client:
            with session_factory() as session:
                if "ecb" in selected:
                    xml_text = _fetch_text(client, ECB_DAILY_URL)
                    _archive_raw_payload(
                        session,
                        source_system="ECB",
                        dataset="fx-reference-rates",
                        source_reference="ecb-eurofxref-daily",
                        payload_text=xml_text,
                        record_count=0,
                        received_at=started,
                    )
                    rows = ecb_market_observations_from_xml(
                        xml_text,
                        currencies={"USD", "GBP", "CHF", "NOK", "DKK", "PLN"},
                    )
                    fx_rows = ecb_fx_observations_from_xml(
                        xml_text,
                        currencies={"USD", "GBP", "CHF", "NOK", "DKK", "PLN"},
                    )
                    if not rows and not fx_rows:
                        _record_run(session, "ECB", "failed", started, 0, "empty_response")
                        report["warnings"].append("ECB returned no observations.")
                    else:
                        upsert_observation_rows(session, MarketObservationRecord, rows)
                        upsert_observation_rows(session, FxObservationRecord, fx_rows)
                        _record_run(
                            session,
                            "ECB",
                            "succeeded",
                            started,
                            len(rows) + len(fx_rows),
                            "ecb-eurofxref-daily",
                        )
                        report["sources"]["ECB"] = {
                            "records": len(rows) + len(fx_rows),
                            "dataset": "fx-reference-rates",
                        }

                if "entsog-reference" in selected:
                    connection_payload = _fetch_json(
                        client,
                        ENTSOG_CONNECTION_POINTS_URL,
                        params={"limit": str(max(args.limit, 1000)), "extended": "1"},
                    )
                    direction_payload = _fetch_json(
                        client,
                        ENTSOG_OPERATOR_POINT_DIRECTIONS_URL,
                        params={"limit": str(max(args.limit, 1000)), "hasData": "1"},
                    )
                    _archive_raw_payload(
                        session,
                        source_system="ENTSOG",
                        dataset="connectionpoints",
                        source_reference="entsog-connectionpoints",
                        payload_json=connection_payload,
                        record_count=0,
                        received_at=started,
                    )
                    _archive_raw_payload(
                        session,
                        source_system="ENTSOG",
                        dataset="operatorpointdirections",
                        source_reference="entsog-operatorpointdirections",
                        payload_json=direction_payload,
                        record_count=0,
                        received_at=started,
                    )
                    node_rows = entsog_reference_nodes_from_connectionpoints(
                        connection_payload
                    )
                    facility_rows = entsog_reference_facilities_from_connectionpoints(
                        connection_payload
                    )
                    hub_rows = entsog_market_hubs_from_connectionpoints(connection_payload)
                    tso_access_rows = entsog_tso_access_points_from_json(direction_payload)
                    reference_summary = _replace_reference_network(
                        session,
                        nodes=node_rows,
                        facilities=facility_rows,
                        hubs=hub_rows,
                        tso_access_points=tso_access_rows,
                    )
                    if reference_summary["skipped_tables"]:
                        report["warnings"].append(
                            "ENTSOG reference payload empty for "
                            + ", ".join(reference_summary["skipped_tables"])
                            + "; existing rows kept."
                        )
                    _record_run(
                        session,
                        "ENTSOG",
                        "succeeded",
                        started,
                        len(node_rows)
                        + len(facility_rows)
                        + len(hub_rows)
                        + len(tso_access_rows),
                        "entsog-reference-network",
                    )
                    reference_record_count = (
                        len(node_rows)
                        + len(facility_rows)
                        + len(hub_rows)
                        + len(tso_access_rows)
                    )
                    report["sources"]["ENTSOG-reference"] = {
                        "records": reference_record_count,
                        "dataset": "connectionpoints/operatorpointdirections",
                    }

                if "entsog" in selected:
                    flow_payload = _fetch_json(
                        client,
                        ENTSOG_OPERATIONAL_URL,
                        params={"limit": str(args.limit), "indicator": "Physical Flow"},
                    )
                    _archive_raw_payload(
                        session,
                        source_system="ENTSOG",
                        dataset="operationaldatas",
                        source_reference="entsog-operationaldatas",
                        payload_json=flow_payload,
                        record_count=0,
                        received_at=started,
                    )
                    rows = entsog_flow_observations_from_json(flow_payload)
                    if not rows:
                        raise RuntimeError("ENTSOG returned no physical-flow observations.")
                    upsert_observation_rows(session, FlowObservationRecord, rows)
                    _record_run(
                        session,
                        "ENTSOG",
                        "succeeded",
                        started,
                        len(rows),
                        "entsog-operationaldatas",
                    )
                    report["sources"]["ENTSOG"] = {"records": len(rows), "dataset": "flows"}

                if "entsog-capacity" in selected:
                    capacity_rows: list[dict[str, Any]] = []
                    for indicator in ENTSOG_CAPACITY_INDICATORS:
                        capacity_rows.extend(
                            entsog_capacity_observations_from_json(
                                _fetch_json(
                                    client,
                                    ENTSOG_OPERATIONAL_URL,
                                    params={"limit": str(args.limit), "indicator": indicator},
                                )
                            )
                        )
                    upsert_observation_rows(session, CapacityObservationRecord, capacity_rows)
                    _record_run(
                        session,
                        "ENTSOG",
                        "succeeded",
                        started,
                        len(capacity_rows),
                        "entsog-operationaldatas-capacity",
                    )
                    report["sources"]["ENTSOG-capacity"] = {
                        "records": len(capacity_rows),
                        "dataset": "capacity",
                    }

                if "gie-agsi" in selected:
                    payload = _fetch_json(
                        client,
                        GIE_AGSI_EU_URL,
                        params={"limit": str(args.limit)},
                        headers={"x-key": gie_key},
                    )
                    _archive_raw_payload(
                        session,
                        source_system="GIE",
                        dataset="AGSI",
                        source_reference="gie-agsi-api",
                        payload_json=payload,
                        record_count=0,
                        received_at=started,
                    )
                    rows = gie_storage_observations_from_json(payload)
                    if not rows:
                        _record_run(session, "GIE-AGSI", "failed", started, 0, "empty_response")
                        report["warnings"].append("GIE AGSI returned no observations.")
                    else:
                        upsert_observation_rows(session, StorageObservationRecord, rows)
                        _record_run(
                            session,
                            "GIE-AGSI",
                            "succeeded",
                            started,
                            len(rows),
                            "gie-agsi-api",
                        )
                        report["sources"]["GIE-AGSI"] = {"records": len(rows), "dataset": "AGSI"}

                if "gie-alsi" in selected:
                    payload = _fetch_json(
                        client,
                        GIE_ALSI_EU_URL,
                        params={"limit": str(args.limit)},
                        headers={"x-key": gie_key},
                    )
                    _archive_raw_payload(
                        session,
                        source_system="GIE",
                        dataset="ALSI",
                        source_reference="gie-alsi-api",
                        payload_json=payload,
                        record_count=0,
                        received_at=started,
                    )
                    rows = gie_lng_observations_from_json(payload)
                    if not rows:
                        _record_run(session, "GIE-ALSI", "failed", started, 0, "empty_response")
                        report["warnings"].append("GIE ALSI returned no observations.")
                    else:
                        upsert_observation_rows(session, LngObservationRecord, rows)
                        _record_run(
                            session,
                            "GIE-ALSI",
                            "succeeded",
                            started,
                            len(rows),
                            "gie-alsi-api",
                        )
                        report["sources"]["GIE-ALSI"] = {"records": len(rows), "dataset": "ALSI"}

                session.commit()

        report["ok"] = True
        return _emit(report, as_json=args.json)
    except (httpx.HTTPError, SQLAlchemyError, ValueError, RuntimeError) as exc:
        report["error"] = exc.__class__.__name__
        if session_factory is not None:
            failed_sources = set()
            for source in selected:
                if source == "ecb":
                    failed_sources.add("ECB")
                elif source.startswith("entsog"):
                    failed_sources.add("ENTSOG")
                elif source.startswith("gie"):
                    failed_sources.add("GIE")
            try:
                with session_factory() as session:
                    for source_name in failed_sources:
                        _record_run(
                            session,
                            source_name,
                            "failed",
                            started,
                            0,
                            f"public-source-{exc.__class__.__name__}",
                        )
                    session.commit()
            except SQLAlchemyError:
                pass
        return _emit(report, as_json=args.json)
    finally:
        if engine is not None:
            engine.dispose()


def _fetch_text(client: httpx.Client, url: str) -> str:
    try:
        response = _get_with_retry(client, url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        if url != ECB_DAILY_URL or os.name != "nt":
            raise
        return _fetch_text_with_powershell(url)


def _fetch_text_with_powershell(url: str) -> str:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$ProgressPreference='SilentlyContinue'; "
                f"(Invoke-WebRequest -Uri '{url}' -UseBasicParsing -TimeoutSec 30).Content"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def _fetch_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = _get_with_retry(client, url, params=params, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Provider response was not a JSON object.")
    return payload


def _gate_blockers(session, source_system: str) -> list[str]:
    """Return fail-closed gate blockers for a live source (audit item 4).

    Entitlement is checked for every source; export-restricted sources
    (ENTSOG, GIE) additionally require a certification record whose gate
    allows live ingestion. Any blocker means the source must not be fetched.
    """

    from eurogas_nexus.governance.entitlement import (
        KNOWN_ENTITLED_SYSTEMS_V1,
        entitlement_check,
    )

    blockers: list[str] = []
    decision = entitlement_check(
        source_system,
        known_entitled_systems=KNOWN_ENTITLED_SYSTEMS_V1,
    )
    if not decision.granted:
        blockers.append(f"entitlement:{decision.scope.value}")
        return blockers

    if source_system not in CERTIFICATION_REQUIRED_SOURCES:
        return blockers

    from eurogas_nexus.db.repositories.certification import latest_certification
    from eurogas_nexus.domain.ingestion.certification import certification_gate

    certification = latest_certification(session, source_system)
    gate = certification_gate(
        source_system,
        stage=(certification or {}).get("stage", "unverified"),
        checks=(certification or {}).get("checks"),
    )
    if not gate.allows_live:
        blockers.append(f"certification:{gate.reason}")
    return blockers


def _archive_raw_payload(
    session,
    *,
    source_system: str,
    dataset: str,
    source_reference: str,
    payload_text: str | None = None,
    payload_json: dict | None = None,
    record_count: int = 0,
    received_at: datetime,
) -> None:
    """Archive one raw provider payload for raw -> canonical lineage.

    Oversized payloads are skipped with a printed warning (never truncated).
    """

    from eurogas_nexus.db.repositories.raw_archive import archive_raw_payload

    if payload_text is not None:
        serialized = payload_text.encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        size = len(serialized)
    elif payload_json is not None:
        serialized = json.dumps(payload_json, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        size = len(serialized)
    else:
        return
    if size > MAX_ARCHIVE_BYTES:
        print(
            f"raw payload archive skipped (>{MAX_ARCHIVE_BYTES} bytes): "
            f"{source_system}/{dataset}"
        )
        return
    archive_raw_payload(
        session,
        archive_id=f"raw-{uuid.uuid4().hex[:20]}",
        source_system=source_system,
        dataset=dataset,
        source_reference=source_reference,
        payload_text=payload_text,
        payload_json=payload_json,
        payload_sha256=digest,
        record_count=record_count,
        received_at_utc=received_at,
    )


def _get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
) -> httpx.Response:
    """GET with backoff retry on transport errors AND 429/5xx responses.

    ``Retry-After`` (seconds or HTTP-date) is honored when present; otherwise
    the backoff is ``1.5 * (attempt + 1)`` seconds.
    """

    last_error: httpx.HTTPError | None = None
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(1.5 * (attempt + 1))
            continue
        if response.status_code not in {429, 500, 502, 503, 504}:
            return response
        if attempt == attempts - 1:
            return response
        time.sleep(_retry_delay_seconds(response, attempt))
    assert last_error is not None
    raise last_error


def _retry_delay_seconds(response: httpx.Response, attempt: int) -> float:
    """Return the retry delay honoring ``Retry-After`` when available."""

    retry_after = response.headers.get("retry-after", "").strip()
    if retry_after.isdigit():
        return min(float(retry_after), 30.0)
    if retry_after:
        try:
            from email.utils import parsedate_to_datetime

            target = parsedate_to_datetime(retry_after)
            if target is not None:
                delay = (target - datetime.now(UTC)).total_seconds()
                if delay > 0:
                    return min(delay, 30.0)
        except (TypeError, ValueError):
            pass
    return 1.5 * (attempt + 1)


def _resolve_gie_key(session_factory) -> str | None:
    env_key = os.environ.get("GIE_API_KEY", "").strip()
    if env_key:
        return env_key

    try:
        from eurogas_nexus.security.credentials import (
            credential_store_configured,
            decrypt_credential_payload,
        )

        if not credential_store_configured():
            return None
        with session_factory() as session:
            row = session.get(ProviderCredentialRecord, "GIE")
            if row is None:
                return None
            payload = decrypt_credential_payload(row.encrypted_payload)
            key = str(payload.get("api_key") or "").strip()
            return key or None
    except Exception:
        return None


def _record_run(
    session,
    source_name: str,
    status: str,
    started: datetime,
    records: int,
    reference: str,
) -> None:
    finished_at = datetime.now(UTC)
    session.merge(
        IngestionRunRecord(
            run_id=f"run-{source_name.lower()}-{uuid.uuid4().hex[:12]}",
            source_name=source_name,
            status=status,
            started_at_utc=started,
            finished_at_utc=finished_at,
            notes=f"{records} normalized records upserted from {reference}.",
        )
    )
    record_audit_event(
        session,
        event_type="ingestion",
        principal="operator",
        action="public_source_ingest",
        resource=f"source:{source_name}",
        outcome=status,
        severity="warning" if status == "failed" else "info",
        detail=f"{records} normalized records from {reference}.",
        source_system="eurogas-nexus",
        now_utc=finished_at,
    )


def _replace_reference_network(
    session,
    *,
    nodes: list[dict[str, Any]],
    facilities: list[dict[str, Any]],
    hubs: list[dict[str, Any]],
    tso_access_points: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace the ENTSOG reference snapshot table by table.

    Each table is replaced only when its incoming payload is non-empty, so a
    partial provider response can never wipe the existing reference network.
    Operator-maintained tables (edges, node/facility mappings, topology/market
    mappings) and non-ENTSOG rows are never touched. The whole step runs inside
    the caller's transaction, so any failure (including a foreign-key conflict
    on an operator edge that references a removed node) rolls everything back.
    """

    if not any((nodes, facilities, hubs, tso_access_points)):
        raise RuntimeError(
            "ENTSOG returned no reference-network rows; existing topology was kept."
        )

    node_ids = {row["id"] for row in nodes}
    now = datetime.now(UTC)
    summary: dict[str, Any] = {"replaced": 0, "skipped_tables": []}
    for model, rows in (
        (ReferenceNode, nodes),
        (ReferenceFacility, facilities),
        (ReferenceMarketHub, hubs),
        (ReferenceTsoAccessPoint, tso_access_points),
    ):
        if not rows:
            summary["skipped_tables"].append(model.__tablename__)
            continue
        prepared: list[dict[str, Any]] = []
        for row in rows:
            prepared_row = {**row, "created_at_utc": now}
            if model is ReferenceTsoAccessPoint and prepared_row["point_id"] not in node_ids:
                prepared_row["point_id"] = None
            prepared.append(prepared_row)
        summary["replaced"] += replace_reference_snapshot(
            session,
            model,
            prepared,
            source_system="ENTSOG",
        )
    session.flush()
    return summary


def _emit(payload: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload.get("ok"):
        counts = ", ".join(
            f"{source}={detail['records']}" for source, detail in payload.get("sources", {}).items()
        )
        print(f"public source ingestion succeeded: {counts}")
    else:
        print(f"public source ingestion failed: {payload.get('error')}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
