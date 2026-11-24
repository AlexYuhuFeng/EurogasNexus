"""P-17 maker-checker: a limit or reference-data change takes effect on a second person's word.

Four eyes as an ETRM or a bank's market-risk controls apply it: one person proposes, a
different authorised person approves; the proposer never approves their own change; a pending
change shows who, what (before and after), why and since when; approval, rejection and
withdrawal are audited with the change; an approved figure keeps who proposed and who approved
it. An administrator can switch four eyes off per write (a single-person install), and that
switch is itself an audited write.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.models import (
    AuditEventRecord,
    ChangeRequestRecord,
    CreditLineRecord,
    HedgeApprovalRecord,
    LngTerminalTermsRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from tests.api.test_risk_limits_api import PUBLIC_TOKEN, _h, _setup

LINE = {
    "name": "Centrica plc",
    "aliases": ["CENTRICA"],
    "limit_amount": 1_000_000,
    "currency": "GBP",
    "collateral_amount": 0,
    "contract_ids": ["nbp-supply"],
}
LINES = "/api/portfolio/credit-lines/CNA"
CHANGES = "/api/portfolio/change-requests"


def _add_admin(engine, who):
    with Session(engine) as session:
        row = create_identity_principal(
            session, name="admin", display_name="Admin", role="ADMIN", data_scopes=["*"]
        )
        principal_id = row.principal_id
        _key, bearer = create_identity_api_key(session, principal_id, scopes=["*"])
        session.commit()
    who["admin"] = {
        "X-Eurogas-Api-Key": PUBLIC_TOKEN,
        "X-Eurogas-Identity": bearer,
        "principal": principal_id,
    }


def _decide(client, who, change_id, verb, name, note=None):
    body = None if note is None else {"note": note}
    return client.post(f"{CHANGES}/{change_id}/{verb}", json=body, headers=_h(who, name))


def _line_in_force(client, who, name="risk"):
    return client.get(LINES, headers=_h(who, name)).json()["data"]


def test_a_limit_change_waits_for_a_second_person_and_keeps_its_provenance(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    first = client.put(
        LINES, json={**LINE, "change_reason": "new counterparty"}, headers=_h(who, "risk")
    )
    assert first.status_code == 202, first.text
    assert (
        _decide(
            client, who, first.json()["data"]["change"]["change_id"], "approve", "checker"
        ).status_code
        == 200
    )

    raised = client.put(
        LINES,
        json={**LINE, "limit_amount": 2_500_000, "change_reason": "credit committee CC-77"},
        headers=_h(who, "risk"),
    )
    assert raised.status_code == 202, raised.text
    proposal = raised.json()["data"]
    assert proposal["pending_approval"] is True and proposal["changed"] == ["limit_amount"]
    change = proposal["change"]
    change_id = change["change_id"]
    # Who, what (before and after), why, since when.
    assert change["proposed_by"] == who["risk"]["principal"]
    assert change["proposed_by_name"] == "risk"
    assert change["fields"] == [
        {"name": "limit_amount", "before": 1_000_000.0, "after": 2_500_000.0}
    ]
    assert change["reason"] == "credit committee CC-77" and change["proposed_at_utc"]
    assert change["own"] is True and change["may_approve"] is False
    assert change["may_withdraw"] is True

    # Nothing changed yet: the limit in force is the approved one.
    assert _line_in_force(client, who)["limit_amount"] == 1_000_000

    # One open proposal per record.
    second = client.put(LINES, json={**LINE, "limit_amount": 9}, headers=_h(who, "risk"))
    assert second.status_code == 409 and second.json()["detail"]["code"] == "change_pending"
    assert second.json()["detail"]["change_id"] == change_id

    # The proposer cannot approve their own change; the refusal says how a one-person
    # installation proceeds.
    own = _decide(client, who, change_id, "approve", "risk")
    assert own.status_code == 403
    assert own.json()["detail"]["code"] == "four_eyes_required"
    assert "organisation settings" in own.json()["detail"]["message"]
    # A trader may neither see nor approve the risk function's change.
    assert _decide(client, who, change_id, "approve", "analyst").status_code == 403
    traders_view = client.get(CHANGES, headers=_h(who, "analyst")).json()["data"]["changes"]
    assert traders_view == []

    listed = client.get(CHANGES, headers=_h(who, "checker")).json()["data"]
    (pending,) = listed["changes"]
    assert pending["change_id"] == change_id and pending["may_approve"] is True
    assert pending["subject"] == "Centrica plc" and pending["label"] == "Credit line"
    assert {row["action"]: row["required"] for row in listed["four_eyes"]} == {
        "risk.credit_line.update": True,
        "risk.mandate.update": True,
        "risk.hedge_approval.update": True,
        "market.firm_marks.update": True,
        "lng.terminal_terms.update": True,
        "lng.freight_route": True,
    }

    approved = _decide(client, who, change_id, "approve", "checker")
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["state"] == "approved"
    assert approved.json()["data"]["decided_by"] == who["checker"]["principal"]
    again = _decide(client, who, change_id, "approve", "jdoe")
    assert again.status_code == 409 and again.json()["detail"]["code"] == "change_not_pending"

    # The figure in force, and who proposed and who approved it.
    line = _line_in_force(client, who)
    assert line["limit_amount"] == 2_500_000 and line["updated_by"] == who["risk"]["principal"]
    provenance = line["provenance"]
    assert provenance["second_approval"] is True
    assert provenance["set_by"] == who["risk"]["principal"] and provenance["set_by_name"] == "risk"
    assert provenance["approved_by"] == who["checker"]["principal"]
    assert provenance["approved_by_name"] == "checker"
    assert provenance["change_id"] == change_id and provenance["approved_at_utc"]
    assert provenance["reason"] == "credit committee CC-77"
    (row,) = client.get("/api/portfolio/credit-exposure", headers=_h(who, "analyst")).json()[
        "data"
    ]["rows"]
    assert row["provenance"]["approved_by_name"] == "checker"

    with Session(engine) as session:
        assert session.get(CreditLineRecord, "CNA").change_id == change_id
        events = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.resource == "credit_line:CNA")
            .order_by(AuditEventRecord.event_ts_utc, AuditEventRecord.event_id)
            .all()
        )
        refused = (
            session.query(AuditEventRecord)
            .filter_by(action="change_request.self_approval_refused")
            .all()
        )
    by_action: dict[str, list[AuditEventRecord]] = {}
    for event in events:
        by_action.setdefault(event.action, []).append(event)
    assert len(by_action["change_request.propose"]) == 2
    assert len(by_action["change_request.approve"]) == 2
    applied = by_action["risk.credit_line.update"][-1]
    # The write itself is audited under the approver, naming both, with the diff.
    assert applied.principal == who["checker"]["principal"]
    assert "proposed by" in applied.detail and "approved by" in applied.detail
    assert applied.before_summary == {"limit_amount": 1_000_000}
    assert applied.after_summary == {"limit_amount": 2_500_000}
    approval = by_action["change_request.approve"][-1]
    assert approval.correlation_id == change_id
    assert approval.principal == who["checker"]["principal"]
    assert len(refused) == 1 and refused[0].principal == who["risk"]["principal"]


def test_rejection_and_withdrawal_are_audited_and_change_nothing(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    path = "/api/portfolio/hedge-approvals/nbp-supply"
    proposed = client.put(path, json={"max_hedge_ratio_pct": 50}, headers=_h(who, "risk"))
    change_id = proposed.json()["data"]["change"]["change_id"]

    assert _decide(client, who, change_id, "reject", "checker", note="").status_code == 422
    own = _decide(client, who, change_id, "reject", "risk", note="no")
    assert own.status_code == 409 and own.json()["detail"]["code"] == "withdraw_own_change"
    assert _decide(client, who, change_id, "withdraw", "checker").status_code == 403
    rejected = _decide(client, who, change_id, "reject", "checker", note="no committee minute")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["state"] == "rejected"
    assert rejected.json()["data"]["decision_note"] == "no committee minute"

    again = client.put(
        path,
        json={"max_hedge_ratio_pct": 50, "approval_ref": "CC-1", "change_reason": "minute CC-1"},
        headers=_h(who, "risk"),
    )
    assert again.status_code == 202  # a rejected proposal no longer blocks the record
    second_id = again.json()["data"]["change"]["change_id"]
    withdrawn = _decide(client, who, second_id, "withdraw", "risk", note="wrong contract")
    assert withdrawn.status_code == 200 and withdrawn.json()["data"]["state"] == "withdrawn"
    assert _decide(client, who, second_id, "approve", "checker").status_code == 409

    decided = client.get(f"{CHANGES}?state=decided", headers=_h(who, "checker")).json()
    assert {row["state"] for row in decided["data"]["changes"]} == {"rejected", "withdrawn"}
    assert client.get(CHANGES, headers=_h(who, "checker")).json()["data"]["changes"] == []
    with Session(engine) as session:
        assert session.query(HedgeApprovalRecord).count() == 0
        actions = [
            event.action
            for event in session.query(AuditEventRecord)
            .filter(AuditEventRecord.action.like("change_request.%"))
            .all()
        ]
    assert sorted(actions) == [
        "change_request.propose",
        "change_request.propose",
        "change_request.reject",
        "change_request.withdraw",
    ]


def test_a_proposal_is_refused_when_the_figures_moved_since(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    _add_admin(engine, who)
    client = TestClient(create_app())
    first = client.put(LINES, json=LINE, headers=_h(who, "risk"))
    _decide(client, who, first.json()["data"]["change"]["change_id"], "approve", "checker")
    stale = client.put(LINES, json={**LINE, "limit_amount": 3_000_000}, headers=_h(who, "jdoe"))
    stale_id = stale.json()["data"]["change"]["change_id"]
    # Meanwhile four eyes is switched off and the line changed directly.
    off = client.put(
        "/api/settings/organisation",
        json={"four_eyes": {"risk.credit_line.update": False}},
        headers=_h(who, "admin"),
    )
    assert off.status_code == 200, off.text
    direct = client.put(LINES, json={**LINE, "limit_amount": 1_200_000}, headers=_h(who, "risk"))
    assert direct.status_code == 200, direct.text
    refused = _decide(client, who, stale_id, "approve", "checker")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "change_stale"
    assert refused.json()["detail"]["stored_now"] == {"limit_amount": 1_200_000.0}
    assert _line_in_force(client, who)["limit_amount"] == 1_200_000
    with Session(engine) as session:
        assert session.get(ChangeRequestRecord, stale_id).state == "pending"


def test_four_eyes_is_set_per_write_by_an_administrator_and_the_switch_is_audited(
    tmp_path, monkeypatch
):
    engine, who = _setup(tmp_path, monkeypatch)
    _add_admin(engine, who)
    client = TestClient(create_app())
    settings = "/api/settings/organisation"
    body = {"four_eyes": {"risk.credit_line.update": False}}
    assert client.put(settings, json=body, headers=_h(who, "risk")).status_code == 403
    unknown = client.put(
        settings, json={"four_eyes": {"access.user.create": False}}, headers=_h(who, "admin")
    )
    assert unknown.status_code == 422
    assert client.put(settings, json=body, headers=_h(who, "admin")).status_code == 200
    # Switches merge: one write off leaves the others on.
    other = {"four_eyes": {"lng.freight_route": True}}
    stored = client.put(settings, json=other, headers=_h(who, "admin")).json()["data"]
    assert stored["four_eyes"] == {"risk.credit_line.update": False, "lng.freight_route": True}

    # A one-person install: the line applies at once and says it had no second approval.
    direct = client.put(LINES, json=LINE, headers=_h(who, "risk"))
    assert direct.status_code == 200 and direct.json()["data"]["pending_approval"] is False
    line = _line_in_force(client, who)
    assert line["provenance"]["second_approval"] is False
    assert line["provenance"]["approved_by"] is None
    assert line["provenance"]["set_by"] == who["risk"]["principal"]
    # The other writes keep four eyes.
    band = client.put(
        "/api/portfolio/hedge-approvals/nbp-supply",
        json={"max_hedge_ratio_pct": 50},
        headers=_h(who, "risk"),
    )
    assert band.status_code == 202
    with Session(engine) as session:
        switches = (
            session.query(AuditEventRecord).filter_by(action="settings.organisation.update").all()
        )
    assert len(switches) == 2
    assert switches[0].after_summary["four_eyes"] == {"risk.credit_line.update": False}
    assert switches[0].principal == who["admin"]["principal"]


def test_a_mandate_is_never_approved_by_the_trader_it_governs(tmp_path, monkeypatch):
    _engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    mandate = {"trader": "jdoe", "display_name": "J. Doe", "hubs": ["NBP"]}
    proposed = client.put(
        "/api/portfolio/trader-mandates/M1", json=mandate, headers=_h(who, "risk")
    )
    change_id = proposed.json()["data"]["change"]["change_id"]
    refused = _decide(client, who, change_id, "approve", "jdoe")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "own_mandate"
    assert _decide(client, who, change_id, "approve", "checker").status_code == 200


def test_terminal_terms_are_approved_by_another_person_on_the_desk(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    terms = {
        "name": "Isle of Grain",
        "hub": "NBP",
        "regas_tariff_per_mwh": 1.0,
        "source_note": "2026 tariff schedule",
        "change_reason": "tariff published",
    }
    proposed = client.put(
        "/api/portfolio/lng-terminal-terms/grain", json=terms, headers=_h(who, "analyst")
    )
    assert proposed.status_code == 202, proposed.text
    change_id = proposed.json()["data"]["change"]["change_id"]
    assert (
        client.get("/api/portfolio/lng-terminal-terms", headers=_h(who, "analyst")).json()["data"][
            "rows"
        ]
        == []
    )
    # Risk does not approve desk reference data; the proposer does not approve their own.
    risk = _decide(client, who, change_id, "approve", "checker")
    assert risk.status_code == 403 and risk.json()["detail"]["code"] == "permission_denied"
    assert _decide(client, who, change_id, "approve", "analyst").status_code == 403
    desk_view = client.get(CHANGES, headers=_h(who, "desk2")).json()["data"]["changes"]
    assert [row["change_id"] for row in desk_view] == [change_id]
    assert desk_view[0]["new_record"] is True and desk_view[0]["reason"] == "tariff published"
    assert _decide(client, who, change_id, "approve", "desk2").status_code == 200
    (row,) = client.get("/api/portfolio/lng-terminal-terms", headers=_h(who, "analyst")).json()[
        "data"
    ]["rows"]
    assert row["regas_tariff_per_mwh"] == 1.0
    assert row["provenance"]["approved_by_name"] == "desk2"
    with Session(engine) as session:
        assert session.get(LngTerminalTermsRecord, "grain").change_id == change_id
