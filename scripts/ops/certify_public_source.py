"""Live-validate a public source and record the evidence that lets it ingest.

ENTSOG and GIE ingestion is fail-closed: it runs only when this deployment holds a
certification record at ``live_validated`` with both required checks. This command is how
an operator earns that record honestly. For each dataset of the source it:

1. reads a small, bounded live sample through the same transport ingestion uses;
2. runs the sample through the same normaliser, without writing a single observation;
3. checks that the normaliser accepted the sample (``live_sample_validation``) and that
   every record carries the fields the normaliser was built and tested against
   (``simulated_shape_match``);
4. records the outcome as certification evidence: counts, the sample's SHA-256 (not the
   sample), the sample period, who ran it and when. No secret is stored or printed.

A source that fails any check is recorded as ``connection_verified`` or left untouched, and
the command exits 1: nothing is ever certified from a failed or empty sample. The record
expires (default 90 days), so validation is repeated rather than assumed.

    python scripts/ops/certify_public_source.py --source entsog --operator ops.name
    python scripts/ops/certify_public_source.py --source gie --operator ops.name
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

USER_AGENT = "EurogasNexus public-source-certification"
#: At least this share of a live sample must normalise for the adapter to be called valid.
MIN_ACCEPTED_SHARE = 0.9
DEFAULT_VALID_DAYS = 90

#: Fields each normaliser reads, per dataset: the shape it was built and replay-tested on.
EXPECTED_FIELDS: dict[str, tuple[str, ...]] = {
    "entsog:connectionpoints": ("pointKey", "pointLabel"),
    "entsog:operationaldatas": (
        "pointKey", "operatorKey", "directionKey", "indicator", "periodFrom", "periodTo",
        "value", "unit",
    ),
    "gie:AGSI": ("name", "code", "gasDayStart", "gasInStorage", "full"),
    "gie:ALSI": ("name", "code", "gasDayStart"),
}


@dataclass
class DatasetCheck:
    dataset: str
    records: int = 0
    normalised: int = 0
    missing_fields: list[str] = field(default_factory=list)
    sample_sha256: str = ""
    period: tuple[str | None, str | None] = (None, None)
    error: str = ""

    @property
    def shape_ok(self) -> bool:
        return self.records > 0 and not self.missing_fields

    @property
    def sample_ok(self) -> bool:
        return self.records > 0 and self.normalised >= MIN_ACCEPTED_SHARE * self.records

    def as_evidence(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "records": self.records,
            "normalised": self.normalised,
            "missing_fields": self.missing_fields,
            "sample_sha256": self.sample_sha256,
            "period_from": self.period[0],
            "period_to": self.period[1],
            "error": self.error,
        }


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def _missing(records: list[dict[str, Any]], expected: tuple[str, ...]) -> list[str]:
    """Expected fields absent from every record (a field may be null on some rows)."""

    return [name for name in expected if not any(name in record for record in records)]


def _has_value(value: object) -> bool:
    """A zero flow is a value; only a missing or blank one is a placeholder."""

    return value is not None and str(value).strip() != ""


def _period(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    def values(keys: tuple[str, ...]) -> list[str]:
        return [str(row[key]) for row in rows for key in keys if row.get(key)]

    starts, ends = values(("period_start_utc", "gas_day")), values(("period_end_utc", "gas_day"))
    return (min(starts) if starts else None, max(ends) if ends else None)


def check_entsog(client, now: datetime) -> list[DatasetCheck]:
    from eurogas_nexus.ingestion.entsog_transport import EntsogTransportError, fetch_entsog_dataset
    from eurogas_nexus.ingestion.public_sources import (
        entsog_flow_observations_from_json,
        entsog_reference_nodes_from_connectionpoints,
    )

    day = (now - timedelta(days=2)).date()
    plans = (
        ("connectionpoints", {"extended": "1"}, "connectionpoints",
         entsog_reference_nodes_from_connectionpoints),
        ("operationaldatas",
         {"from": day.isoformat(), "to": (day + timedelta(days=1)).isoformat(),
          "indicator": "Physical Flow", "periodType": "day"},
         "operationaldatas", entsog_flow_observations_from_json),
    )
    checks = []
    for dataset, filters, key, normalise in plans:
        check = DatasetCheck(f"entsog:{dataset}")
        try:
            # One whole gas day of flows (a few thousand raw rows); a bounded slice of the
            # reference points. Rows the provider publishes with no value ("not available"
            # placeholders) are not expected to normalise and are not counted against it.
            whole_day = dataset == "operationaldatas"
            result = fetch_entsog_dataset(
                client,
                dataset,
                filters=filters,
                page_size=1000 if whole_day else 200,
                max_records=10_000 if whole_day else 200,
                max_pages=10 if whole_day else 1,
            )
            if whole_day:
                result.require_complete()
            records: list[dict[str, Any]] = []
            rows: list[dict[str, Any]] = []
            for page in result.pages:
                records += [
                    r
                    for r in page.payload.get(key, [])
                    if isinstance(r, dict) and (not whole_day or _has_value(r.get("value")))
                ]
                if dataset == "operationaldatas":
                    # As ingestion does: exact numeric text and the response receipt time.
                    rows += normalise(
                        page.numeric_lexeme_payload, observed_at_utc=page.received_at_utc
                    )
                else:
                    rows += normalise(page.payload)
            check.records, check.normalised = len(records), len(rows)
            check.missing_fields = _missing(records, EXPECTED_FIELDS[check.dataset])
            check.sample_sha256 = _sha(records)
            check.period = _period(rows)
        except (EntsogTransportError, ValueError, RuntimeError) as exc:
            check.error = f"{exc.__class__.__name__}: {exc}"[:300]
        checks.append(check)
    return checks


def check_gie(client, now: datetime, api_key: str) -> list[DatasetCheck]:
    from eurogas_nexus.ingestion.gie_transport import (
        GieProduct,
        GieTransportError,
        fetch_gie_product,
    )
    from eurogas_nexus.ingestion.public_sources import (
        gie_lng_observations_from_json,
        gie_storage_observations_from_json,
    )

    plans = (
        (GieProduct.agsi("https://agsi.gie.eu/api"), gie_storage_observations_from_json),
        (GieProduct.alsi("https://alsi.gie.eu/api"), gie_lng_observations_from_json),
    )
    checks = []
    for product, normalise in plans:
        check = DatasetCheck(f"gie:{product.product}")
        try:
            result = fetch_gie_product(
                client, product=product, api_key=api_key, max_records=100, max_pages=1
            )
            records = [dict(record) for record in result.records]
            rows: list[dict[str, Any]] = []
            for page in result.pages:
                rows += normalise(page.raw_payload, observed_at_utc=page.received_at_utc)
            check.records, check.normalised = len(records), len(rows)
            check.missing_fields = _missing(records, EXPECTED_FIELDS[check.dataset])
            check.sample_sha256 = _sha(records)
            check.period = _period(rows)
        except (GieTransportError, ValueError) as exc:
            check.error = f"{exc.__class__.__name__}: {exc}"[:300]
        checks.append(check)
    return checks


def decide(checks: list[DatasetCheck], *, credential_checked: bool) -> tuple[str, list[str]]:
    """The stage and check ids the evidence supports. Never more than was shown."""

    reached = bool(checks) and all(check.records > 0 and not check.error for check in checks)
    if not reached:
        return "configured", []
    passed = ["credential_verified"] if credential_checked else []
    if all(check.shape_ok for check in checks):
        passed.append("simulated_shape_match")
    if all(check.sample_ok for check in checks):
        passed.append("live_sample_validation")
    passed.append("sample_archived")  # the sample's hash and counts are in the evidence
    complete = {"simulated_shape_match", "live_sample_validation"} <= set(passed)
    return ("live_validated" if complete else "connection_verified"), passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True, choices=("entsog", "gie"))
    parser.add_argument("--operator", required=True, help="Who is running the validation.")
    parser.add_argument("--valid-days", type=int, default=DEFAULT_VALID_DAYS)
    parser.add_argument("--dry-run", action="store_true", help="Probe and report; record nothing.")
    args = parser.parse_args(argv)

    import httpx

    from eurogas_nexus.db.repositories.certification import upsert_provider_certification
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None and not args.dry_run:
        print("RUNTIME_STORE_DATABASE_URL is not set.", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    credential_checked = False
    with httpx.Client(
        timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        if args.source == "entsog":
            system, checks = "ENTSOG", check_entsog(client, now)
        else:
            from eurogas_nexus.ingestion.gie_transport import resolve_gie_api_key

            key = resolve_gie_api_key()
            if key is None:
                print("No GIE credential (GIE_API_KEY or GIE_API_KEY_FILE).", file=sys.stderr)
                return 2
            system, checks = "GIE", check_gie(client, now, key.value)
            credential_checked = all(not check.error for check in checks)

    stage, passed = decide(checks, credential_checked=credential_checked)
    report = {
        "source": system,
        "stage": stage,
        "checks": passed,
        "datasets": [check.as_evidence() for check in checks],
        "validated_at_utc": now.isoformat(),
    }
    if not args.dry_run:
        with get_session_factory()() as session:
            upsert_provider_certification(
                session,
                source_system=system,
                stage=stage,
                checks=passed,
                evidence={
                    "live_test": "passed" if stage == "live_validated" else "failed",
                    "datasets": report["datasets"],
                    "min_accepted_share": MIN_ACCEPTED_SHARE,
                },
                evaluated_by=args.operator,
                note="scripts/ops/certify_public_source.py",
                now_utc=now,
                adapter_version=_adapter_version(),
                credential_label="GIE_API_KEY" if system == "GIE" else None,
                entitlement_scope=system,
                tests_performed=["bounded live sample", "normaliser dry run", "field shape"],
                expires_at_utc=now + timedelta(days=args.valid_days),
                evidence_ref=f"sha256:{_sha(report['datasets'])}",
            )
            session.commit()
        report["recorded"] = True
        report["expires_at_utc"] = (now + timedelta(days=args.valid_days)).isoformat()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if stage == "live_validated" else 1


def _adapter_version() -> str:
    from eurogas_nexus.version import APPLICATION_VERSION

    return str(APPLICATION_VERSION)


if __name__ == "__main__":
    raise SystemExit(main())
