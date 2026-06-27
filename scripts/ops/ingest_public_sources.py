"""Explicit live ingestion for public/source-keyed V1 data sources.

This script is operator-invoked only. It performs live HTTP reads, writes
normalized rows to PostgreSQL, never prints secrets, and never commits raw
provider payloads.
"""

from __future__ import annotations

import argparse
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
    ReferenceEdge,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    ReferenceTsoAccessPoint,
    StorageObservationRecord,
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
                    rows = ecb_market_observations_from_xml(
                        xml_text,
                        currencies={"USD", "GBP", "CHF", "NOK", "DKK", "PLN"},
                    )
                    fx_rows = ecb_fx_observations_from_xml(
                        xml_text,
                        currencies={"USD", "GBP", "CHF", "NOK", "DKK", "PLN"},
                    )
                    for row in rows:
                        session.merge(MarketObservationRecord(**row))
                    for row in fx_rows:
                        session.merge(FxObservationRecord(**row))
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
                    node_rows = entsog_reference_nodes_from_connectionpoints(
                        connection_payload
                    )
                    facility_rows = entsog_reference_facilities_from_connectionpoints(
                        connection_payload
                    )
                    hub_rows = entsog_market_hubs_from_connectionpoints(connection_payload)
                    tso_access_rows = entsog_tso_access_points_from_json(direction_payload)
                    _replace_reference_network(
                        session,
                        nodes=node_rows,
                        facilities=facility_rows,
                        hubs=hub_rows,
                        tso_access_points=tso_access_rows,
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
                    rows = entsog_flow_observations_from_json(
                        _fetch_json(
                            client,
                            ENTSOG_OPERATIONAL_URL,
                            params={"limit": str(args.limit)},
                        )
                    )
                    for row in rows:
                        session.merge(FlowObservationRecord(**row))
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
                    for row in capacity_rows:
                        session.merge(CapacityObservationRecord(**row))
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
                    rows = gie_storage_observations_from_json(
                        _fetch_json(
                            client,
                            GIE_AGSI_EU_URL,
                            params={"limit": str(args.limit)},
                            headers={"x-key": gie_key},
                        )
                    )
                    for row in rows:
                        session.merge(StorageObservationRecord(**row))
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
                    rows = gie_lng_observations_from_json(
                        _fetch_json(
                            client,
                            GIE_ALSI_EU_URL,
                            params={"limit": str(args.limit)},
                            headers={"x-key": gie_key},
                        )
                    )
                    for row in rows:
                        session.merge(LngObservationRecord(**row))
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
    except (httpx.HTTPError, SQLAlchemyError, ValueError) as exc:
        report["error"] = exc.__class__.__name__
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


def _get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
) -> httpx.Response:
    last_error: httpx.HTTPError | None = None
    for attempt in range(attempts):
        try:
            return client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


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
    session.merge(
        IngestionRunRecord(
            run_id=f"run-{source_name.lower()}-{uuid.uuid4().hex[:12]}",
            source_name=source_name,
            status=status,
            started_at_utc=started,
            finished_at_utc=datetime.now(UTC),
            notes=f"{records} normalized records from {reference}.",
        )
    )


def _replace_reference_network(
    session,
    *,
    nodes: list[dict[str, Any]],
    facilities: list[dict[str, Any]],
    hubs: list[dict[str, Any]],
    tso_access_points: list[dict[str, Any]],
) -> None:
    from eurogas_nexus.db.models.reference_network import (
        NodeFacilityMapping,
        TopologyMarketMapping,
    )

    for model in (
        TopologyMarketMapping,
        NodeFacilityMapping,
        ReferenceTsoAccessPoint,
        ReferenceEdge,
        ReferenceFacility,
        ReferenceMarketHub,
        ReferenceNode,
    ):
        session.query(model).delete()
    session.flush()

    now = datetime.now(UTC)
    node_ids = {row["id"] for row in nodes}
    for row in nodes:
        session.merge(ReferenceNode(**{**row, "created_at_utc": now}))
    session.flush()
    for row in facilities:
        session.merge(ReferenceFacility(**{**row, "created_at_utc": now}))
    session.flush()
    for row in hubs:
        session.merge(ReferenceMarketHub(**{**row, "created_at_utc": now}))
    session.flush()
    for row in tso_access_points:
        if row["point_id"] not in node_ids:
            row = {**row, "point_id": None}
        session.merge(ReferenceTsoAccessPoint(**{**row, "created_at_utc": now}))
    session.flush()


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
