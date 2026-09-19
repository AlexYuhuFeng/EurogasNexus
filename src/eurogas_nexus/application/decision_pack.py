"""The decision pack: one case's governance artefact, composed and made citable.

Why this exists: the platform records everything a decision needs - the case, its evidence, the
snapshot each reference points at, the assumptions, the alternatives, the AI findings, the warnings
and the human record with its actor - and none of it in a form a reviewer can *sign*. Assembling it
by hand from four reads is exactly the work that gets skipped under deadline, and a pack that is
assembled in a client cannot be cited by anything.

So the pack is composed **here**, by the deterministic layer, and it carries a canonical content
hash: a printed or signed copy can be matched to the platform's own record by recomputing the hash
from the JSON, and a field that changed afterwards changes it.

Three rules the composition follows, because a governance artefact that overstates itself is worse
than none:

* it **verifies what it can and reports what it cannot**. An evidence reference whose snapshot is
  not on record is listed with ``snapshot_resolvable: false`` rather than dropped, and the pack says
  so in its blockers.
* it **never invents a signature**. ``signable`` states whether the case has the two things that
  make it decidable at all (evidence and a recorded decision); the signature itself is a human act
  outside the platform, and the pack says that where a reader will look for it.
* it carries its **own basis**: which fields the hash covers, and which version of the pack shape
  produced it, so an artefact from an older deployment is recognisable as one.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

PACK_VERSION = "decision-pack-1"
#: What the content hash is computed over, stated in the payload so a verifier does not have to
#: guess the canonicalisation: every field of the pack except ``content_hash`` itself, serialised
#: as canonical JSON (sorted keys, UTF-8, no insignificant whitespace).
HASH_BASIS = (
    "sha256 over the canonical JSON of this pack without its content_hash field "
    "(sorted keys, UTF-8, no insignificant whitespace)"
)


def canonical_hash(payload: dict[str, Any]) -> str:
    """Return the canonical SHA-256 of a pack body.

    计算 pack 正文的规范化 SHA-256（键排序、UTF-8、无多余空白）。

    Args:
        payload: The pack body, without the ``content_hash`` field.

    Returns:
        The hash as ``sha256:<hex digest>``.
    """

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _evidence_entries(
    evidence: list[dict[str, Any]], resolvable_snapshots: set[str]
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in evidence:
        snapshot_id = item.get("snapshot_id") or None
        entries.append(
            {
                "kind": item.get("kind"),
                "ref": item.get("ref"),
                "label": item.get("label"),
                "as_of_utc": item.get("as_of_utc"),
                "snapshot_id": snapshot_id,
                # Measured, not assumed: a reference whose snapshot is not on record is the first
                # thing a reviewer needs to know, and dropping it would hide the hole.
                "snapshot_resolvable": (
                    snapshot_id in resolvable_snapshots if snapshot_id else None
                ),
            }
        )
    return entries


def load_decision_pack(
    session: Any, case_id: str, *, case: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Load one case and compose its decision pack.

    读取决策案并组装其决策包；案不存在时返回 None。

    Args:
        session: Open runtime-database session.
        case_id: The case to pack.
        case: The case payload when the caller has already loaded it, so one read does not load the
            same row twice.

    Returns:
        The pack body, or ``None`` when no such case exists.
    """

    from eurogas_nexus.db.repositories.audit import list_audit_events_for_resource
    from eurogas_nexus.db.repositories.data_platform import get_analysis_snapshot
    from eurogas_nexus.db.repositories.decision import get_decision_case

    resolved_case = case if case is not None else get_decision_case(session, case_id)
    if resolved_case is None:
        return None
    cited = {
        item.get("snapshot_id")
        for item in (resolved_case.get("evidence") or [])
        if item.get("snapshot_id")
    }
    resolvable = {
        snapshot_id
        for snapshot_id in cited
        if get_analysis_snapshot(session, snapshot_id) is not None
    }
    audit_events = list_audit_events_for_resource(session, f"decision_case:{case_id}")
    return build_decision_pack(
        resolved_case, resolvable_snapshots=resolvable, audit_events=audit_events
    )


def build_decision_pack(
    case: dict[str, Any],
    *,
    resolvable_snapshots: set[str],
    audit_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compose one case's decision pack.

    组装单个决策案的"决策包"（上下文、证据、假设、备选、人类记录、审计引用与内容哈希）。

    Args:
        case: The case payload ``GET /api/decision-cases/{case_id}`` serves today.
        resolvable_snapshots: Snapshot ids that are on record, so each evidence reference can be
            reported as resolvable or not.
        audit_events: The audit trail entries recorded against this case
            (``resource == "decision_case:<case_id>"``), oldest first.

    Returns:
        The pack body, including ``content_hash`` and ``content_hash_basis``.
    """

    records = list(case.get("records") or [])
    evidence = _evidence_entries(list(case.get("evidence") or []), resolvable_snapshots)
    unresolved = [entry["ref"] for entry in evidence if entry["snapshot_resolvable"] is False]
    decision = records[-1] if records else None

    blockers: list[str] = []
    if not evidence:
        blockers.append("DECISION_PACK_EVIDENCE_MISSING")
    if decision is None:
        blockers.append("DECISION_PACK_DECISION_NOT_RECORDED")
    if unresolved:
        blockers.append("DECISION_PACK_SNAPSHOT_UNRESOLVED")
    # The case's own blockers are why it cannot be decided yet; they belong in the pack too, because
    # a reviewer reading the pack should not have to open the case to learn what is missing.
    blockers.extend(str(item) for item in (case.get("blockers") or []))

    body: dict[str, Any] = {
        "pack_version": PACK_VERSION,
        "case_id": case.get("case_id"),
        "objective": case.get("objective"),
        "status": case.get("status"),
        "context": {
            "gas_day": case.get("gas_day"),
            "delivery_product": case.get("delivery_product"),
            "hub_id": case.get("hub_id"),
            "portfolio_ref": case.get("portfolio_ref"),
            "snapshot_id": case.get("snapshot_id"),
            "reproducible": case.get("reproducible"),
            "created_by": case.get("created_by"),
            "created_at_utc": case.get("created_at_utc"),
        },
        "evidence": evidence,
        "assumptions": list(case.get("assumptions") or []),
        "alternatives": list(case.get("alternatives") or []),
        "ai_findings": list(case.get("ai_findings") or []),
        "warnings": list(case.get("warnings") or []),
        "decision": decision,
        "history": records,
        "audit": {
            # The trail is part of the pack, not a pointer to it: the case's own acts are recorded
            # against ``decision_case:<case_id>``, so they can be cited here without a join guess.
            "resource": f"decision_case:{case.get('case_id')}",
            "events": audit_events,
            "read_surface": "/api/audit",
        },
        "signable": decision is not None and bool(evidence),
        "blockers": blockers,
        "signature_note": (
            "This pack is the artefact a reviewer signs; the platform records the human decision "
            "and its actor, and does not hold a signature."
        ),
    }
    # The basis is part of the artefact, so it is set before the hash: the rule a verifier applies
    # is then exactly "hash everything except content_hash", with nothing to remember.
    body["content_hash_basis"] = HASH_BASIS
    body["content_hash"] = canonical_hash(body)
    return body
