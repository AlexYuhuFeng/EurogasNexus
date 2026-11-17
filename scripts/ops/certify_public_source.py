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
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# The live checks live in the product (application.public_source_approval), shared with the
# administrator's approval on the Connectors screen and scripts/ops/approve_public_source.py.
from eurogas_nexus.application.public_source_approval import (  # noqa: E402
    DEFAULT_VALID_DAYS,
    EXPECTED_FIELDS,
    MIN_ACCEPTED_SHARE,
    USER_AGENT,
    DatasetCheck,
    _has_value,
    _missing,
    _period,
    _sha,
    check_entsog,
    check_gie,
    decide,
)

__all__ = [
    "DEFAULT_VALID_DAYS", "EXPECTED_FIELDS", "MIN_ACCEPTED_SHARE", "USER_AGENT", "DatasetCheck",
    "_has_value", "_missing", "_period", "_sha", "check_entsog", "check_gie", "decide",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True, choices=("entsog", "gie"))
    parser.add_argument("--operator", required=True, help="Who is running the validation.")
    parser.add_argument("--valid-days", type=int, default=DEFAULT_VALID_DAYS)
    parser.add_argument("--dry-run", action="store_true", help="Probe and report; record nothing.")
    parser.add_argument(
        "--note",
        default="",
        help="Why this validation is run (recorded with the evidence, e.g. a ticket).",
    )
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
                note="scripts/ops/certify_public_source.py"
                + (f": {args.note.strip()}" if args.note.strip() else ""),
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
