"""Approve a public source and run the live validation the ingestion gate requires.

ENTSOG and GIE ingest only with a certification record at ``live_validated`` with both
required checks (the fail-closed gate in ``scripts/ops/ingest_public_sources.py``). On the
first live bring-up nothing in the product produced that record, so a fresh installation
with its keys configured read ``source_gate_blocked`` until an engineer certified by hand.
This module is the product path through the gate:

1. an administrator approves the source for the firm (:func:`approve_public_source`): who,
   when, why and which terms summary was shown are recorded with the evidence and in the
   audit log (``source.approval``). The product never accepts terms itself;
2. the product then runs a bounded live validation for each dataset: a small live sample
   through the transport ingestion uses, a dry run of the normaliser (nothing is written),
   the field-shape check, and the evidence (counts and the sample's SHA-256, never the
   sample or a key). Only a sample that passes reaches ``live_validated``;
3. an approval given before the provider key exists is kept as "approved, waiting for
   key"; the first ingestion attempt after the key arrives runs the validation
   (:func:`ensure_approved_source_validated`) under the approver's record.

The same functions serve the Connectors screen (``POST /api/sources/{id}/approve``), the
operator command ``scripts/ops/approve_public_source.py`` and the demo start-up.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.ingestion.source_approval import (
    APPROVAL_CHECK,
    APPROVAL_REQUIRED_SYSTEMS,
    APPROVAL_SOURCE_IDS,
    SOURCE_TERMS,
    approval_info,
    is_approved,
)

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




# ------------------------------------------------------------------ approval


class ApprovalError(ValueError):
    """An approval that cannot be recorded; ``code`` is stable for API and CLI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


#: Accepted spellings of each approval-required source.
_ALIASES = {
    "entsog": "ENTSOG",
    "src-entsog": "ENTSOG",
    "gie": "GIE",
    "src-gie": "GIE",
    "gie-agsi": "GIE",
    "gie-alsi": "GIE",
}


def approval_system(source: str) -> str:
    """The source system an approval names (``entsog``, ``src-gie``, ``GIE`` ...)."""

    value = str(source or "").strip()
    system = _ALIASES.get(value.lower(), value.upper())
    if system not in APPROVAL_REQUIRED_SYSTEMS:
        raise ApprovalError(
            "approval_not_required",
            f"{source!r} is not a public source that needs approval "
            f"(those are: {', '.join(sorted(APPROVAL_SOURCE_IDS.values()))}).",
        )
    return system


def resolve_provider_key(system: str, session_factory=None) -> str | None:
    """The provider key the source reads with, or ``None`` (only GIE needs one).

    The ingestion path's own resolver: environment, key file, then the encrypted store,
    with an operator-disabled credential refused.
    """

    if system != "GIE":
        return None
    from eurogas_nexus.ingestion.gie_transport import (
        GieTransportError,
        resolve_gie_runtime_api_key,
    )

    try:
        resolved = resolve_gie_runtime_api_key(session_factory=session_factory)
    except GieTransportError:
        return None
    return resolved.value if resolved is not None else None


def live_validation(
    system: str, *, client, now: datetime, api_key: str | None
) -> tuple[str, list[str], list[DatasetCheck]]:
    """Run the bounded live validation for ``system``: (stage, checks, per-dataset checks)."""

    if system == "ENTSOG":
        checks = check_entsog(client, now)
        credential_checked = False
    else:
        checks = check_gie(client, now, api_key or "")
        credential_checked = all(not check.error for check in checks)
    stage, passed = decide(checks, credential_checked=credential_checked)
    return stage, passed, checks


def _http_client():
    import httpx

    return httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _adapter_version() -> str:
    from eurogas_nexus.version import APPLICATION_VERSION

    return str(APPLICATION_VERSION)


def _record(
    session,
    system: str,
    *,
    approval: dict[str, Any],
    stage: str,
    checks: list[str],
    datasets: list[DatasetCheck],
    evaluated_by: str,
    now: datetime,
    validation_failure: str | None,
) -> dict[str, Any]:
    from eurogas_nexus.db.repositories.certification import upsert_provider_certification

    datasets_evidence = [check.as_evidence() for check in datasets]
    evidence: dict[str, Any] = {
        "approval": approval,
        "live_test": "passed" if stage == "live_validated" else "not_run_or_failed",
        "datasets": datasets_evidence,
        "min_accepted_share": MIN_ACCEPTED_SHARE,
    }
    if validation_failure:
        evidence["validation_failure"] = validation_failure
    return upsert_provider_certification(
        session,
        source_system=system,
        stage=stage,
        checks=[APPROVAL_CHECK, *checks],
        evidence=evidence,
        evaluated_by=evaluated_by,
        note=f"approved by {approval['approved_by']}: {approval['reason']}",
        now_utc=now,
        adapter_version=_adapter_version(),
        credential_label="GIE_API_KEY" if system == "GIE" else None,
        entitlement_scope=system,
        tests_performed=(
            ["bounded live sample", "normaliser dry run", "field shape"] if datasets else []
        ),
        # The approval is the firm's decision and stays until revoked; the validation
        # evidence records when it was shown.
        expires_at_utc=None,
        evidence_ref=f"sha256:{_sha(datasets_evidence)}" if datasets else None,
    )


def _failure(stage: str, datasets: list[DatasetCheck]) -> str | None:
    if stage == "live_validated":
        return None
    errors = [f"{check.dataset}: {check.error}" for check in datasets if check.error]
    if errors:
        return "live_validation_failed: " + "; ".join(errors)[:300]
    return "live_validation_failed: the live sample did not pass the shape or sample checks"


def _validate_and_record(
    session, system: str, approval: dict[str, Any], *, now: datetime, client,
    session_factory, evaluated_by: str,
) -> tuple[str, dict[str, Any]]:
    key = resolve_provider_key(system, session_factory)
    if system == "GIE" and key is None:
        record = _record(
            session, system, approval=approval, stage="configured", checks=[], datasets=[],
            evaluated_by=evaluated_by, now=now, validation_failure=None,
        )
        return "approved_waiting_for_key", record
    owned = client is None
    client = client or _http_client()
    try:
        stage, passed, datasets = live_validation(system, client=client, now=now, api_key=key)
    finally:
        if owned:
            client.close()
    failure = _failure(stage, datasets)
    record = _record(
        session, system, approval=approval, stage=stage, checks=passed, datasets=datasets,
        evaluated_by=evaluated_by, now=now, validation_failure=failure,
    )
    return ("approved" if failure is None else "failing"), record


def approve_public_source(
    session,
    source: str,
    *,
    actor: str,
    reason: str,
    accept_terms: bool,
    now: datetime | None = None,
    client=None,
    session_factory=None,
) -> dict[str, Any]:
    """Record an administrator's approval of a public source and validate it live.

    Idempotent: a source already approved and passing the gate is left as it is
    (``changed`` false). Raises :class:`ApprovalError` with a stable code for a source
    that needs no approval, an empty reason or terms not accepted. The caller commits.
    """

    from eurogas_nexus.db.repositories.audit import record_audit_event
    from eurogas_nexus.db.repositories.certification import latest_certification
    from eurogas_nexus.domain.ingestion.certification import certification_gate

    system = approval_system(source)
    actor = str(actor or "").strip()
    reason = str(reason or "").strip()
    if not actor:
        raise ApprovalError("actor_required", "An approval names who approves.")
    if not reason:
        raise ApprovalError("reason_required", "An approval states why (for the audit log).")
    if not accept_terms:
        raise ApprovalError(
            "terms_not_accepted",
            "Read the provider's terms summary and accept them for your firm to approve.",
        )
    now = now or datetime.now(UTC)
    terms = SOURCE_TERMS[system]
    current = latest_certification(session, system)
    if current and is_approved(current):
        gate = certification_gate(system, stage=current["stage"], checks=current["checks"])
        if gate.allows_live:
            return {
                "source_id": APPROVAL_SOURCE_IDS[system],
                "source_system": system,
                "state": "approved",
                "changed": False,
                "approval": approval_info(current),
                "terms": terms.as_dict(),
                "stage": current["stage"],
            }
    approval = {
        "approved_by": actor,
        "approved_at_utc": now.isoformat(),
        "reason": reason,
        "terms_version": terms.version,
        "terms_reference": terms.reference,
        "terms_url": terms.terms_url,
        "terms_summary": terms.summary,
        "attribution": terms.attribution,
    }
    state, record = _validate_and_record(
        session, system, approval, now=now, client=client, session_factory=session_factory,
        evaluated_by=actor,
    )
    record_audit_event(
        session,
        event_type="source.approval",
        principal=actor,
        action="approve_public_source",
        resource=f"source:{APPROVAL_SOURCE_IDS[system]}",
        outcome=state,
        severity="warning" if state == "failing" else "info",
        detail=(
            f"{system} approved by {actor} for the firm; reason: {reason}; terms summary "
            f"{terms.version} ({terms.reference}); validation stage {record['stage']}"
        ),
        source_system=system,
        now_utc=now,
    )
    session.flush()
    return {
        "source_id": APPROVAL_SOURCE_IDS[system],
        "source_system": system,
        "state": state,
        "changed": True,
        "approval": approval_info(record),
        "terms": terms.as_dict(),
        "stage": record["stage"],
        "failure": (record.get("evidence") or {}).get("validation_failure"),
    }


def ensure_approved_source_validated(
    session, system: str, *, now: datetime | None = None, client=None, session_factory=None
) -> bool:
    """Run the live validation for an approved source that has not passed it yet.

    For the ingestion gate: an approval given before the provider key existed (or whose
    validation failed for an upstream reason) is validated at the next read, under the
    approver's record. Never approves anything: without an approval it returns False.
    Returns whether the gate now allows the source.
    """

    from eurogas_nexus.db.repositories.certification import latest_certification
    from eurogas_nexus.domain.ingestion.certification import certification_gate

    current = latest_certification(session, system)
    if not current or not is_approved(current):
        return False
    gate = certification_gate(system, stage=current["stage"], checks=current["checks"])
    if gate.allows_live:
        return True
    approval = (current.get("evidence") or {}).get("approval")
    if not isinstance(approval, dict):
        return False  # an operator record without an administrator's approval
    now = now or datetime.now(UTC)
    state, record = _validate_and_record(
        session, system, approval, now=now, client=client, session_factory=session_factory,
        evaluated_by=str(approval.get("approved_by") or "approval"),
    )
    return certification_gate(system, stage=record["stage"], checks=record["checks"]).allows_live


__all__ = [
    "ApprovalError",
    "DatasetCheck",
    "approval_system",
    "approve_public_source",
    "check_entsog",
    "check_gie",
    "decide",
    "ensure_approved_source_validated",
    "live_validation",
]


#: What a screen calls each held-back source's data.
_DATA_NAMES = {"ENTSOG": "ENTSOG flows", "GIE": "GIE storage and LNG"}
_STATE_REASON = {
    "not_approved": "source not approved",
    "approved_waiting_for_key": "approved, waiting for the GIE key",
    "failing": "live validation failed",
}


def held_back_sources(session, systems=("ENTSOG", "GIE")) -> list[dict[str, str]]:
    """The approval-required sources the gate holds back, in the words a screen shows.

    ``[{"source_system", "state", "text"}]``, e.g. "ENTSOG flows: source not approved -
    Admin → Connectors". Empty when every named source is approved and validated. Reads
    only the certification record and the key's presence; never calls a provider.
    """

    from eurogas_nexus.db.repositories.certification import latest_certification
    from eurogas_nexus.domain.ingestion.certification import certification_gate
    from eurogas_nexus.domain.ingestion.source_approval import APPROVAL_ACTION

    held = []
    for system in systems:
        record = latest_certification(session, system)
        if record is not None and certification_gate(
            system, stage=record["stage"], checks=record["checks"]
        ).allows_live:
            continue
        if not is_approved(record):
            state = "not_approved"
        elif system == "GIE" and resolve_provider_key(system) is None:
            state = "approved_waiting_for_key"
        else:
            state = "failing"
        held.append({
            "source_system": system,
            "state": state,
            "text": f"{_DATA_NAMES[system]}: {_STATE_REASON[state]} - {APPROVAL_ACTION}",
        })
    return held
