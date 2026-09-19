"""The decision pack: composition, verification and the canonical hash."""

from __future__ import annotations

import json

from eurogas_nexus.application.decision_pack import (
    HASH_BASIS,
    PACK_VERSION,
    build_decision_pack,
    canonical_hash,
)


def _case(**overrides) -> dict:
    case = {
        "case_id": "case-1",
        "objective": "Cover the TTF balance for the gas day",
        "status": "OPEN",
        "gas_day": "2026-09-19",
        "delivery_product": "within-day",
        "hub_id": "TTF",
        "portfolio_ref": "book-a",
        "snapshot_id": "snap-1",
        "reproducible": True,
        "created_by": "analyst-1",
        "created_at_utc": "2026-09-19T08:00:00+00:00",
        "assumptions": [{"key": "fx", "value": "0.86", "source": "ecb", "note": ""}],
        "alternatives": [
            {
                "alternative_id": "alt-1",
                "label": "Buy the balance",
                "description": "",
                "economics_ref": "econ-1",
                "warnings": [],
            }
        ],
        "evidence": [
            {
                "kind": "MARKET_CONTEXT",
                "ref": "market-context:2026-09-19",
                "label": "Market context",
                "as_of_utc": "2026-09-19T08:00:00+00:00",
                "snapshot_id": "snap-1",
            }
        ],
        "ai_findings": ["the spread narrowed"],
        "warnings": ["SCENARIO_STALE"],
        "records": [],
        "decidable": False,
        "blockers": ["EVIDENCE_INSUFFICIENT"],
    }
    case.update(overrides)
    return case


def _decision() -> dict:
    return {
        "outcome": "accepted",
        "actor": "reviewer-1",
        "note": "cover it",
        "evidence_refs": ["market-context:2026-09-19"],
        "recorded_at_utc": "2026-09-19T09:00:00+00:00",
    }


def _audit() -> list[dict]:
    return [
        {
            "event_id": "audit-1",
            "action": "decision_case_create",
            "principal": "analyst-1",
            "outcome": "recorded",
            "severity": "info",
            "event_ts_utc": "2026-09-19T08:00:00+00:00",
            "detail": "",
        }
    ]


def test_a_pack_states_its_version_and_hash_basis() -> None:
    pack = build_decision_pack(_case(), resolvable_snapshots={"snap-1"}, audit_events=_audit())

    assert pack["pack_version"] == PACK_VERSION
    assert pack["content_hash"].startswith("sha256:")
    assert pack["content_hash_basis"] == HASH_BASIS
    # The hash covers the body, and the basis explains how to recompute it.
    body = {key: value for key, value in pack.items() if key != "content_hash"}
    assert canonical_hash(body) == pack["content_hash"]


def test_the_hash_changes_when_any_packed_field_changes() -> None:
    base = build_decision_pack(
        _case(records=[_decision()]), resolvable_snapshots={"snap-1"}, audit_events=_audit()
    )

    for mutation in (
        _case(records=[_decision()], objective="Something else"),
        _case(records=[{**_decision(), "note": "cover it differently"}]),
        _case(records=[_decision()], warnings=["SCENARIO_STALE", "FX_STALE"]),
        _case(records=[_decision()], status="DECIDED"),
    ):
        changed = build_decision_pack(
            mutation, resolvable_snapshots={"snap-1"}, audit_events=_audit()
        )
        assert changed["content_hash"] != base["content_hash"]


def test_the_hash_ignores_key_order_only() -> None:
    """Canonicalisation is by sorted keys, so a re-serialised body hashes the same."""

    pack = build_decision_pack(_case(), resolvable_snapshots=set(), audit_events=[])
    body = {key: value for key, value in pack.items() if key != "content_hash"}

    reordered = json.loads(json.dumps(body, sort_keys=False))

    assert canonical_hash(reordered) == pack["content_hash"]


def test_an_evidence_reference_whose_snapshot_is_absent_is_reported_not_dropped() -> None:
    pack = build_decision_pack(
        _case(records=[_decision()]), resolvable_snapshots=set(), audit_events=[]
    )

    entry = pack["evidence"][0]
    assert entry["snapshot_id"] == "snap-1"
    assert entry["snapshot_resolvable"] is False
    assert "DECISION_PACK_SNAPSHOT_UNRESOLVED" in pack["blockers"]


def test_evidence_without_a_snapshot_reference_is_not_claimed_either_way() -> None:
    pack = build_decision_pack(
        _case(evidence=[{"kind": "MANUAL", "ref": "note", "snapshot_id": None}]),
        resolvable_snapshots=set(),
        audit_events=[],
    )

    assert pack["evidence"][0]["snapshot_resolvable"] is None
    assert "DECISION_PACK_SNAPSHOT_UNRESOLVED" not in pack["blockers"]


def test_signability_is_evidence_and_a_recorded_decision() -> None:
    undecided = build_decision_pack(_case(), resolvable_snapshots={"snap-1"}, audit_events=[])
    assert undecided["signable"] is False
    assert "DECISION_PACK_DECISION_NOT_RECORDED" in undecided["blockers"]
    assert undecided["decision"] is None

    decided = build_decision_pack(
        _case(records=[_decision()]), resolvable_snapshots={"snap-1"}, audit_events=_audit()
    )
    assert decided["signable"] is True
    assert decided["decision"]["actor"] == "reviewer-1"
    assert decided["history"] == [_decision()]


def test_a_case_with_no_evidence_cannot_be_signed_even_with_a_record() -> None:
    pack = build_decision_pack(
        _case(evidence=[], records=[_decision()]), resolvable_snapshots=set(), audit_events=[]
    )

    assert pack["signable"] is False
    assert "DECISION_PACK_EVIDENCE_MISSING" in pack["blockers"]


def test_the_case_own_blockers_travel_with_the_pack() -> None:
    pack = build_decision_pack(
        _case(blockers=["CASE_EVIDENCE_REQUIRED"]),
        resolvable_snapshots={"snap-1"},
        audit_events=[],
    )

    assert "CASE_EVIDENCE_REQUIRED" in pack["blockers"]


def test_the_pack_carries_the_audit_trail_of_the_case_itself() -> None:
    pack = build_decision_pack(_case(), resolvable_snapshots=set(), audit_events=_audit())

    assert pack["audit"]["resource"] == "decision_case:case-1"
    assert pack["audit"]["events"][0]["action"] == "decision_case_create"
    assert pack["audit"]["read_surface"] == "/api/audit"


def test_the_pack_never_claims_to_hold_a_signature() -> None:
    pack = build_decision_pack(
        _case(records=[_decision()]), resolvable_snapshots={"snap-1"}, audit_events=[]
    )

    assert "signature" not in pack
    assert "does not hold a signature" in pack["signature_note"]
