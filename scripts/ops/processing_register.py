"""Draft the record of processing activities (GDPR / UK GDPR Art. 30) for this installation.

    python scripts/ops/processing_register.py --controller "Example Energy Trading Ltd" \
        --contact "dpo@example.com" --output processing-register.md

The register is drafted from the installation's own configuration (region, identity
source, external AI, retention), so it states what this installation actually does rather
than what a template assumes. The data protection officer reviews it, completes the lawful
basis and transfer mechanism for each entity, and keeps it in the firm's register; PIPL
(China), PDPA (Singapore) and PIPEDA (Canada) records can be kept from the same draft.
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.application.audit_retention import DEFAULT_AUDIT_RETENTION_DAYS

_REGIONS = {
    "global": "Primary installation (UK-hosted per docs/architecture/GLOBAL_DEPLOYMENT.md)",
    "china": "Mainland China installation; personal data of China staff stays in China",
}


def _flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def facts() -> dict[str, str]:
    """What this installation's configuration says about its processing."""

    region = (os.environ.get("EUROGAS_NEXUS_DEPLOYMENT_REGION") or "global").strip().lower()
    identity = []
    if os.environ.get("EUROGAS_NEXUS_OIDC_ISSUER"):
        mode = os.environ.get("EUROGAS_NEXUS_OIDC_PROVISIONING_MODE") or "approval"
        identity.append(
            f"OIDC single sign-on ({os.environ['EUROGAS_NEXUS_OIDC_ISSUER']}; provisioning {mode})"
        )
    if _flag("EUROGAS_NEXUS_GATEWAY_AUTH_ENABLED"):
        identity.append("authenticating gateway in the firm's network (SAML/Kerberos/agent)")
    identity.append("identity keys issued by administrators")
    llm = (
        "Enabled: alert explanations are sent to the configured external model provider; "
        "payloads exclude licensed raw data and personal data beyond the requesting user id."
        if _flag("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED")
        else "Disabled: no data leaves the installation for AI processing."
    )
    return {
        "region": _REGIONS.get(region, region),
        "identity": "; ".join(identity),
        "llm": llm,
        "audit_retention": (
            f"{DEFAULT_AUDIT_RETENTION_DAYS} days by default (five years); configurable 30-3650"
        ),
    }


def render(controller: str, contact: str) -> str:
    f = facts()
    today = datetime.now(UTC).date().isoformat()
    rows = [
        ("Controller", controller),
        ("Contact (DPO or privacy lead)", contact),
        ("System", "Eurogas Nexus (gas trading decision support; no order entry or settlement)"),
        ("Installation", f["region"]),
        (
            "Purposes",
            "Access control and accountability for staff using a trading decision-support system; "
            "record-keeping of decisions under REMIT, MAR and, where applicable, MiFID II",
        ),
        ("Data subjects", "Employees and contractors of the firm with access to the system"),
        (
            "Personal data",
            "Name, work e-mail, office, job functions, roles and data scopes; sessions and API key "
            "metadata; display preferences; audit trail of actions (who, what, when)",
        ),
        ("Special categories", "None"),
        ("Source of the data", f["identity"]),
        (
            "Recipients",
            "Administrators and compliance staff of the firm; the firm's surveillance and ETRM "
            "systems "
            "through signed exports; no sale or sharing with third parties",
        ),
        ("External AI processing", f["llm"]),
        (
            "International transfers",
            "Per installation topology; transfers between installations only by approved, "
            "signed, one-way exports. DPO to state the mechanism (adequacy, standard contractual "
            "clauses, "
            "PIPL standard contract or certification)",
        ),
        (
            "Retention",
            f"Audit events {f['audit_retention']}; sessions expire; disabled accounts minimised on "
            "request except records kept by law (GDPR Art. 17(3)(b))",
        ),
        (
            "Data-subject requests",
            "Access: scripts/ops/personal_data_export.py (audited). Rectification and erasure: "
            "administrator procedure in docs/compliance/COMPLIANCE_AUDIT.md",
        ),
        (
            "Security measures",
            "Role-based access, per-route permissions, data and book scopes, four-eyes on "
            "decisions, audit trail, TLS in transit, server-side secrets, signed releases with "
            "SBOMs; encryption at "
            "rest of database and backups provided by the deployment",
        ),
        (
            "Lawful basis",
            "To be completed by the DPO (usually legitimate interests and legal obligation)",
        ),
    ]
    lines = [
        "# Record of processing activities: Eurogas Nexus",
        "",
        f"Draft generated {today} from the installation's configuration. Review, complete the open",
        "items and keep it in the firm's register. Not legal advice.",
        "",
        "| Item | Entry |",
        "|---|---|",
        *[f"| {label} | {value} |" for label, value in rows],
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--controller", required=True, help="Legal entity that is the controller")
    parser.add_argument("--contact", required=True, help="DPO or privacy contact")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    text = render(args.controller, args.contact)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Register draft written to {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
