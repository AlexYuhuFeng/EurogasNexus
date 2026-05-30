"""Explicit live ingestion for public/source-keyed V1 data sources.

This script is operator-invoked only. It performs live HTTP reads, writes
normalized rows to PostgreSQL, never prints secrets, and never commits raw
provider payloads.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError

from eurogas_nexus.db.models import (
    FlowObservationRecord,
    IngestionRunRecord,
    LngObservationRecord,
    MarketObservationRecord,
    ProviderCredentialRecord,
    StorageObservationRecord,
)
from eurogas_nexus.db.session import (
    create_session_factory,
    get_engine,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.ingestion.public_sources import (
    ecb_market_observations_from_xml,
    entsog_flow_observations_from_json,
    gie_lng_observations_from_json,
    gie_storage_observations_from_json,
)

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ENTSOG_OPERATIONAL_URL = "https://transparency.entsog.eu/api/v1/operationaldatas"
GIE_AGSI_EU_URL = "https://agsi.gie.eu/api/data/EU"
GIE_ALSI_EU_URL = "https://alsi.gie.eu/api/data/EU"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=("all", "ecb", "entsog", "gie-agsi", "gie-alsi"),
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
        selected = {"ecb", "entsog", "gie-agsi", "gie-alsi"}

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

        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            with session_factory() as session:
                if "ecb" in selected:
                    rows = ecb_market_observations_from_xml(
                        _fetch_text(client, ECB_DAILY_URL),
                        currencies={"USD", "GBP", "CHF", "NOK", "DKK", "PLN"},
                    )
                    for row in rows:
                        session.merge(MarketObservationRecord(**row))
                    _record_run(
                        session,
                        "ECB",
                        "succeeded",
                        started,
                        len(rows),
                        "ecb-eurofxref-daily",
                    )
                    report["sources"]["ECB"] = {
                        "records": len(rows),
                        "dataset": "fx-reference-rates",
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
    response = client.get(url)
    response.raise_for_status()
    return response.text


def _fetch_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = client.get(url, params=params, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Provider response was not a JSON object.")
    return payload


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
