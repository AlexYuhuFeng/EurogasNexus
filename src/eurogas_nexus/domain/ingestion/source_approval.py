"""Public-source approval: which sources need an administrator's approval, and their state.

Pure and DB-free. The fail-closed ingestion gate (``scripts/ops/ingest_public_sources.py``
``_gate_blockers``) lets ENTSOG and GIE ingest only with a certification record at
``live_validated`` carrying both required checks. On the first live bring-up (2026-11-12)
nothing in the product produced that record, so every fresh installation read
``source_gate_blocked`` with its keys configured; the record was made by hand on the real
store. This module makes the way through the gate a product step: an administrator
approves a public source on behalf of the firm (who, when, why, having read the terms
summary below), and the product then runs the same bounded live validation the operator
command ran (``application.public_source_approval``). The gate itself is unchanged.

Classification of every registered source (``classify_source``):

- ``approval``: the gate requires an approval before any read (ENTSOG);
- ``approval_and_key``: approval plus the provider's registered key (GIE AGSI/ALSI);
- ``no_approval``: public data read without approval (ECB, Elexon, National Gas, BoE,
  ECB €STR, NY Fed, ENTSOG UMMs, ECMWF Open Data);
- ``key_only``: public data that needs only the provider's key (EIA, ENTSO-E, GIE IIP);
- ``licensed``: the customer's own licence and entitlement (exchanges, brokers, price
  reporters, Kpler, weather vendors, FX fix vendors, EEX NGP);
- ``register`` / ``simulated`` / ``model``: a TSO tariff register an operator keeps, the
  demo's simulated price sources, the optional model service.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

#: Source systems whose live read requires an administrator's approval (the gate's
#: ``CERTIFICATION_REQUIRED_SOURCES`` for public data; EEX is licensed and stays with the
#: licensed path). GIE products are stored under ``GIE``.
APPROVAL_REQUIRED_SYSTEMS: frozenset[str] = frozenset({"ENTSOG", "GIE"})
#: Registered source id of each approval-required system.
APPROVAL_SOURCE_IDS: dict[str, str] = {"ENTSOG": "src-entsog", "GIE": "src-gie"}
#: Public sources that need only the provider's key (the registry marks only some of them).
KEY_ONLY_SYSTEMS: frozenset[str] = frozenset({"EIA", "ENTSOE", "REMIT"})

#: Stable reason code a refused read records and every surface shows.
NOT_APPROVED_CODE = "source_not_approved"
#: The check an administrator's approval adds to the certification record.
APPROVAL_CHECK = "entitlement_confirmed"
#: Where the action lives, in the words every surface uses.
APPROVAL_ACTION = "Admin → Connectors"


@dataclass(frozen=True)
class SourceTerms:
    """The engineering summary of a provider's terms (docs/legal/DATA_SOURCE_TERMS.md).

    Shown to the administrator before approval. It is a summary, not legal advice: the
    administrator approves for the firm, and the product never accepts terms itself.
    """

    provider: str
    summary: str
    attribution: str
    terms_url: str
    reference: str = "docs/legal/DATA_SOURCE_TERMS.md"
    #: Bump when the summary changes, so an approval records which text was shown.
    version: str = "2026-11-16"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


SOURCE_TERMS: dict[str, SourceTerms] = {
    "ENTSOG": SourceTerms(
        provider="ENTSOG Transparency Platform",
        summary=(
            "Free public data. ENTSOG TP Terms of Use (Rev. 3, 10 Nov 2026) Art. 5: you may "
            "download, store and use the contents in good faith, keeping proprietary notices "
            "intact, citing the source and download date, and without implying ENTSOG "
            "endorsement. No clause excludes commercial use. Confirm the current terms "
            "before use."
        ),
        attribution='ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/',
        terms_url="https://www.entsog.eu/privacy-policy-and-terms-use",
    ),
    "GIE": SourceTerms(
        provider="GIE AGSI+ / ALSI (Gas Infrastructure Europe)",
        summary=(
            "Free with a registered API key (your firm's own key, held server-side). Reuse "
            "requires attribution to GIE as the data source. Confirm the current terms of "
            "the AGSI+/ALSI platforms before use."
        ),
        attribution="Source: GIE AGSI+ / ALSI (Gas Infrastructure Europe)",
        terms_url="https://agsi.gie.eu/",
    ),
}

#: Plain words for each state; the UI translates the code, these serve CLI and logs.
STATE_WORDS: dict[str, str] = {
    "not_required": "No approval needed",
    "not_approved": "Not approved yet",
    "approved_waiting_for_key": "Approved, waiting for key",
    "approved": "Approved, waiting for the first read",
    "running": "Running",
    "failing": "Failing",
}


def approval_required(source_system: str | None) -> bool:
    return str(source_system or "") in APPROVAL_REQUIRED_SYSTEMS


def classify_source(row: dict[str, Any]) -> str:
    """One class per registered source (see the module docstring)."""

    system = str(row.get("source_system") or "")
    integration = str(row.get("integration") or "api")
    source_id = str(row.get("source_id") or "")
    needs_key = bool(row.get("credential_requirements")) or system in KEY_ONLY_SYSTEMS
    if integration == "manual_register":
        return "register"
    if system.endswith("_Sim") or source_id.endswith("-sim"):
        return "simulated"
    if integration == "model_service":
        return "model"
    if approval_required(system):
        return "approval_and_key" if needs_key else "approval"
    if row.get("category") == "price" and system not in {"EIA"} and needs_key:
        return "licensed"
    if system in {"Platts", "ICIS", "Argus", "Kpler", "Weather", "WMR", "BFIX"}:
        return "licensed"
    return "key_only" if needs_key else "no_approval"


def is_approved(certification: dict[str, Any] | None) -> bool:
    """An administrator approved the source (or an operator certified it live before)."""

    if not certification:
        return False
    checks = {str(check).lower() for check in certification.get("checks") or ()}
    stage = str(certification.get("stage") or "").lower()
    return APPROVAL_CHECK in checks or stage in {"live_validated", "certified"}


def approval_info(certification: dict[str, Any] | None) -> dict[str, Any]:
    """Who approved, when and why, from a certification record (``None`` fields if not)."""

    evidence = (certification or {}).get("evidence") or {}
    approval = evidence.get("approval") if isinstance(evidence, dict) else None
    if isinstance(approval, dict):
        return {
            "approved_by": approval.get("approved_by"),
            "approved_at_utc": approval.get("approved_at_utc"),
            "reason": approval.get("reason"),
            "terms_version": approval.get("terms_version"),
        }
    if certification and is_approved(certification):
        # Certified by an operator before approvals existed: that operator stands in.
        return {
            "approved_by": certification.get("evaluated_by"),
            "approved_at_utc": certification.get("evaluated_at_utc"),
            "reason": certification.get("note"),
            "terms_version": None,
        }
    return {"approved_by": None, "approved_at_utc": None, "reason": None, "terms_version": None}


def approval_state(
    source_system: str,
    *,
    certification: dict[str, Any] | None,
    gate_allows_live: bool,
    credential_state: str,
    connectivity_status: str,
    last_message: str | None = None,
    last_success_at_utc: str | None = None,
) -> dict[str, Any]:
    """The approval state a person reads for one source, with the reason when it fails.

    ``credential_state`` and ``connectivity_status`` are the Source Center's own values.
    """

    if not approval_required(source_system):
        return {"required": False, "state": "not_required", "reason": None}
    terms = SOURCE_TERMS.get(source_system)
    base = {
        "required": True,
        "terms": terms.as_dict() if terms else None,
        "action": APPROVAL_ACTION,
        **approval_info(certification),
    }
    if not is_approved(certification):
        return {**base, "state": "not_approved", "reason": NOT_APPROVED_CODE}
    if credential_state in {"missing", "disabled"}:
        return {**base, "state": "approved_waiting_for_key", "reason": "credential_missing"}
    if not gate_allows_live:
        failure = ((certification or {}).get("evidence") or {}).get("validation_failure")
        return {
            **base,
            "state": "failing",
            "reason": failure or "live_validation_pending",
        }
    if connectivity_status in {"failed", "stale"}:
        return {**base, "state": "failing", "reason": last_message or connectivity_status}
    if connectivity_status == "active" and last_success_at_utc:
        # Rows alone do not make it running (the shipped reference bundle is ENTSOG rows);
        # an ingestion run must have succeeded.
        return {**base, "state": "running", "reason": None}
    return {**base, "state": "approved", "reason": None}
