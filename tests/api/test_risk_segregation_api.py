"""Segregation of duties and audited partial updates on the risk function's reference data.

Persona review findings P-01 and P-02 (standard B7, F3, F4): a person who also trades may not
set the limits their deals are measured against, a mandate cannot be one's own under any of
one's names, and a change that leaves a field out keeps it rather than clearing it.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.models import AuditEventRecord, CreditLineRecord, IdentityPrincipalRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.security.segregation import risk_function_refusal
from tests.api.test_risk_limits_api import PUBLIC_TOKEN, _h, _setup


def _add_dual_role(engine, who):
    """A trader who was also given REVIEWER: the combination segregation refuses."""

    with Session(engine) as session:
        row = create_identity_principal(
            session, name="dual", display_name="Dual Role", role="ANALYST", data_scopes=["*"]
        )
        row.roles = ["ANALYST", "REVIEWER"]
        _key, bearer = create_identity_api_key(
            session, row.principal_id, display_name="t", scopes=["*"]
        )
        session.commit()
        who["dual"] = {
            "X-Eurogas-Api-Key": PUBLIC_TOKEN,
            "X-Eurogas-Identity": bearer,
            "principal": row.principal_id,
        }


LINE = {
    "name": "Centrica plc",
    "aliases": ["CENTRICA"],
    "limit_amount": 1_000_000,
    "currency": "GBP",
    "collateral_amount": 0,
    "contract_ids": ["nbp-supply"],
}


def test_refusal_names_the_rule():
    assert risk_function_refusal(SimpleNamespace(role="VIEWER", roles=()), what="X")["code"] == (
        "risk_function_required"
    )
    # ANALYST outranks REVIEWER, so rank is not the test: the role itself is.
    assert risk_function_refusal(SimpleNamespace(role="ANALYST", roles=()), what="X")["code"] == (
        "risk_function_required"
    )
    dual = risk_function_refusal(
        SimpleNamespace(role="ANALYST", roles=("REVIEWER", "ANALYST")), what="Credit lines"
    )
    assert dual["code"] == "segregation_of_duties" and "ANALYST" in dual["message"]
    assert risk_function_refusal(SimpleNamespace(role="REVIEWER", roles=()), what="X") is None


def test_a_trader_who_is_also_a_reviewer_cannot_set_limits(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    _add_dual_role(engine, who)
    with Session(engine) as session:
        assert session.get(IdentityPrincipalRecord, who["dual"]["principal"]).roles == [
            "ANALYST",
            "REVIEWER",
        ]
    client = TestClient(create_app())
    mandate = {
        "trader": "someone-else",
        "display_name": "Someone Else",
        "hubs": ["TTF"],
        "max_net_mwh_per_month": 10_000,
    }
    band = {"min_hedge_ratio_pct": 50, "max_hedge_ratio_pct": 90}
    attempts = (
        ("/api/portfolio/credit-lines/CNA", LINE),
        ("/api/portfolio/trader-mandates/M9", mandate),
        ("/api/portfolio/hedge-approvals/nbp-supply", band),
        ("/api/opportunities/settings", {"persistence": 2}),
    )
    for path, body in attempts:
        refused = client.put(path, json=body, headers=_h(who, "dual"))
        assert refused.status_code == 403, (path, refused.text)
        assert refused.json()["detail"]["code"] == "segregation_of_duties", path
        allowed = client.put(path, json=body, headers=_h(who, "risk"))
        assert allowed.status_code == 200, (path, allowed.text)


def test_a_mandate_cannot_be_ones_own_under_any_name(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    for trader in ("jdoe", " JDoe ", who["jdoe"]["principal"]):
        body = {
            "trader": trader,
            "display_name": "J. Doe",
            "hubs": ["NBP"],
            "max_net_mwh_per_month": 5_000,
        }
        own = client.put("/api/portfolio/trader-mandates/M1", json=body, headers=_h(who, "jdoe"))
        assert own.status_code == 403, trader
        assert own.json()["detail"]["code"] == "own_mandate", trader


def test_a_credit_line_change_keeps_what_it_leaves_out_and_audits_the_diff(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    path = "/api/portfolio/credit-lines/CNA"
    assert client.put(path, json=LINE, headers=_h(who, "risk")).status_code == 200

    # Raise the limit only: the contract links must survive (P-01: before this fix the
    # omitted list became empty and the breach measured against the contract vanished).
    raised = client.put(
        path, json={"name": "Centrica plc", "limit_amount": 2_000_000}, headers=_h(who, "risk")
    )
    assert raised.status_code == 200, raised.text
    assert raised.json()["data"]["changed"] == ["limit_amount"]
    with Session(engine) as session:
        line = session.get(CreditLineRecord, "CNA")
        assert line.contract_ids == ["nbp-supply"]
        assert line.limit_amount == 2_000_000
        assert line.aliases == ["CENTRICA"]

    # Unlinking is still possible, but only when asked for explicitly: an empty list alone
    # is what a form that never loaded the links sends (QA-R-01).
    bare = client.put(
        path,
        json={"name": "Centrica plc", "limit_amount": 2_000_000, "contract_ids": []},
        headers=_h(who, "risk"),
    )
    assert bare.status_code == 409 and bare.json()["detail"]["code"] == "unlink_not_confirmed"
    unlinked = client.put(
        path,
        json={"name": "Centrica plc", "limit_amount": 2_000_000, "contract_ids": [],
              "unlink_contracts": True},
        headers=_h(who, "risk"),
    )
    assert unlinked.json()["data"]["changed"] == ["contract_ids"]

    unchanged = client.put(
        path,
        json={"name": "Centrica plc", "limit_amount": 2_000_000, "contract_ids": []},
        headers=_h(who, "risk"),
    )
    assert unchanged.json()["data"]["changed"] == []

    with Session(engine) as session:
        rows = (
            session.query(AuditEventRecord)
            .filter_by(action="risk.credit_line.update")
            .order_by(AuditEventRecord.event_ts_utc, AuditEventRecord.event_id)
            .all()
        )
        details = [row.detail for row in rows]
        summaries = [(row.before_summary, row.after_summary) for row in rows]
    assert len(details) == 4
    assert "limit_amount: 1000000" in details[1] and "-> 2000000" in details[1]
    assert summaries[1] == ({"limit_amount": 1_000_000}, {"limit_amount": 2_000_000})
    assert "contract_ids: ['nbp-supply'] -> []" in details[2]
    assert summaries[2] == ({"contract_ids": ["nbp-supply"]}, {"contract_ids": []})
    assert details[3] == "no change"
