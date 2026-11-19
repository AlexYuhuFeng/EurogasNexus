"""Opportunities over the API (CP-08): permissions, scope, dismissal, case, cursors, settings."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    DecisionCaseRecord,
    HedgeApprovalRecord,
    TradingBookRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _contract(cid: str, book: str) -> UpstreamResourceContractRecord:
    now = datetime.now(UTC)
    return UpstreamResourceContractRecord(
        contract_id=cid,
        contract_name=cid.upper(),
        resource_type="PIPELINE_IMPORT",
        delivery_point_name="TTF",
        gas_year=f"{now.year}+",
        delivery_quantity_mwh_per_day=10_000.0,
        contract_price_gbp_mwh=30.0,
        contract_price_currency="EUR",
        settlement_frequency="monthly",
        upstream_payment_lag_days=20,
        screen_sale_cash_lag_days=1,
        delivery_tolerance_pct=5.0,
        nomination_tolerance_pct=2.0,
        annual_financing_rate_pct=5.0,
        allowed_exit_points=["TTF"],
        eligible_sale_modes=["LOCAL_MARKET_SALE"],
        book_id=book,
        created_at_utc=now,
        updated_at_utc=now,
    )


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'opps.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    who = {}
    now = datetime.now(UTC)
    with Session(engine) as session:
        for book in ("uk-nbp", "nl-ttf"):
            session.add(
                TradingBookRecord(
                    book_id=book,
                    name=book,
                    legal_entity="EGN-" + book[:2].upper(),
                    region="europe",
                    business="gas",
                    base_currency="EUR",
                    active=True,
                    updated_by="t",
                    updated_at_utc=now,
                )
            )
        session.add_all([_contract("uk-supply", "uk-nbp"), _contract("nl-supply", "nl-ttf")])
        for cid in ("uk-supply", "nl-supply"):
            session.add(
                HedgeApprovalRecord(
                    contract_id=cid,
                    min_hedge_ratio_pct=60.0,
                    max_hedge_ratio_pct=80.0,
                    approval_ref="RC-1",
                    valid_until=date(now.year + 2, 9, 30),
                    updated_by="risk",
                    updated_at_utc=now,
                )
            )
        for name, role, scopes in (
            ("viewer", "VIEWER", ["*"]),
            ("trader", "ANALYST", ["*"]),
            ("risk", "REVIEWER", ["*"]),
            ("admin", "ADMIN", ["*"]),
            ("uktrader", "ANALYST", ["BOOKS:BOOK:UK-NBP"]),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=scopes
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            who[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.commit()
    return TestClient(create_app(Settings(api_profile="release"))), engine, who


def test_the_opportunity_flow(tmp_path, monkeypatch) -> None:
    client, engine, who = _setup(tmp_path, monkeypatch)
    assert client.post("/api/opportunities/evaluations", headers=who["viewer"]).status_code == 403
    for _ in range(2):
        run = client.post("/api/opportunities/evaluations", headers=who["trader"])
        assert run.status_code == 200, run.text
        assert run.json()["data"]["evaluators"]["hedge_gap"]["status"] == "ok"
    assert client.get("/api/opportunities", headers=who["admin"]).status_code == 403

    full = client.get("/api/opportunities", headers=who["viewer"]).json()["data"]
    must = full["lanes"]["must_act"]
    # One item per subject (contract), its months inside: two contracts, many months each.
    assert must["total"] == 2 and len(must["items"]) == 2 and not must["next_cursor"]
    assert all(item["group"]["count"] > 1 for item in must["items"])
    for item in must["items"]:
        members = item["group"]["members"]
        sizes = [float(m["volume"]["value"]) for m in members]
        assert sizes == sorted(sizes, reverse=True)  # largest first
        assert float(item["group"]["total_volume"]["value"]) == sum(sizes)
        assert item["subject"] and item["period_start"]
    assert full["simulated"] is False
    assert full["evaluation"]["trigger"] == "on_demand"
    assert full["evaluation"]["next"]["pending_inputs"] == []
    books = {book for item in must["items"] for book in item["book_ids"]}
    assert books == {"uk-nbp", "nl-ttf"} or books <= {"uk-nbp", "nl-ttf"}

    # Book scope: the UK trader never sees an NL row, in the list or by id.
    uk = client.get("/api/opportunities", headers=who["uktrader"]).json()["data"]
    uk_items = uk["lanes"]["must_act"]["items"]
    assert uk_items and all(item["book_ids"] == ["uk-nbp"] for item in uk_items)
    nl_id = next(item for item in must["items"] if item["book_ids"] == ["nl-ttf"])["opportunity_id"]
    assert client.get(f"/api/opportunities/{nl_id}", headers=who["uktrader"]).status_code == 404

    # Cursors: every row exactly once; a newer evaluation expires the cursor.
    seen, cursor = [], None
    while True:
        params = {"lane": "must_act", "limit": 1, **({"cursor": cursor} if cursor else {})}
        page = client.get("/api/opportunities", headers=who["viewer"], params=params).json()
        bucket = page["data"]["lanes"]["must_act"]
        seen += [item["opportunity_id"] for item in bucket["items"]]
        cursor = bucket["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == must["total"]
    stale = client.get(
        "/api/opportunities", headers=who["viewer"], params={"lane": "must_act", "limit": 1}
    ).json()["data"]["lanes"]["must_act"]
    client.post("/api/opportunities/evaluations", headers=who["trader"])
    expired = client.get(
        "/api/opportunities", headers=who["viewer"], params={"cursor": stale["next_cursor"]}
    )
    assert expired.status_code == 409 and expired.json()["detail"]["code"] == "cursor_expired"

    # Detail: the full object with its arithmetic and snapshot record.
    target = must["items"][0]["opportunity_id"]
    detail = client.get(f"/api/opportunities/{target}", headers=who["trader"]).json()["data"]
    legs = detail["object"]["legs"]
    assert [leg["kind"] for leg in legs] == ["term", "term", "result"]
    assert detail["snapshot"]["snapshot_id"] and detail["object"]["falsifiers"]
    assert detail["next_steps"] == ["open_as_case", "watch", "dismiss"]

    # Dismissal: needs a reason; hides for that person only; restore brings it back.
    bad = client.put(
        f"/api/opportunities/{target}/state", headers=who["trader"], json={"action": "dismiss"}
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "dismiss_reason_required"
    ok = client.put(
        f"/api/opportunities/{target}/state",
        headers=who["trader"],
        json={"action": "dismiss", "reason": "already_covered"},
    )
    assert ok.status_code == 200
    mine = client.get("/api/opportunities", headers=who["trader"]).json()["data"]
    assert mine["hidden_by_you"] == 1
    others = client.get("/api/opportunities", headers=who["viewer"]).json()["data"]
    assert others["hidden_by_you"] == 0
    stats = client.get("/api/opportunities/statistics", headers=who["risk"]).json()["data"]
    assert stats["dismissals"] == [{"type": "hedge_gap", "reason": "already_covered", "count": 1}]
    client.put(
        f"/api/opportunities/{target}/state", headers=who["trader"], json={"action": "restore"}
    )
    assert (
        client.get("/api/opportunities", headers=who["trader"]).json()["data"]["hidden_by_you"] == 0
    )

    # Open as a case: the existing case flow, frozen arithmetic and the snapshot reference.
    assert (
        client.post(f"/api/opportunities/{target}/case", headers=who["viewer"]).status_code == 403
    )
    opened = client.post(f"/api/opportunities/{target}/case", headers=who["trader"])
    assert opened.status_code == 200, opened.text
    case = opened.json()["data"]["case"]
    assert case["evidence"][0]["ref"].startswith(f"opportunity:{target}@v")
    assert case["evidence"][0]["snapshot_id"] == detail["snapshot"]["snapshot_id"]
    again = client.post(f"/api/opportunities/{target}/case", headers=who["trader"])
    assert again.status_code == 409 and again.json()["detail"]["case_id"] == case["case_id"]
    with Session(engine) as session:
        stored = session.get(DecisionCaseRecord, case["case_id"])
        assert stored.alternatives_json[0]["economics_ref"].startswith("opportunity:")
        assert any(item["key"].startswith("input:book:hedge:") for item in stored.assumptions_json)
        assert (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "opportunity.open_case")
            .count()
            == 1
        )
    gone = client.get("/api/opportunities", headers=who["viewer"]).json()["data"]
    # A converted month leaves its subject's months (the subject stays while others remain).
    months = lambda data: sum(i["group"]["count"] for i in data["lanes"]["must_act"]["items"])  # noqa: E731
    assert months(gone) == months(full) - 1


def test_threshold_settings_are_the_risk_functions(tmp_path, monkeypatch) -> None:
    client, _engine, who = _setup(tmp_path, monkeypatch)
    current = client.get("/api/opportunities/settings", headers=who["viewer"]).json()["data"]
    assert current["min_margin"] == {"value": "0.1", "unit": "EUR/MWh", "currency": "EUR"}
    assert current["min_value"]["value"] == "10000" and current["max_per_lane"] == 7
    body = {"max_per_lane": 5, "marks_actionable": True}
    assert (
        client.put("/api/opportunities/settings", headers=who["trader"], json=body).status_code
        == 403
    )
    changed = client.put("/api/opportunities/settings", headers=who["risk"], json=body)
    assert changed.status_code == 200 and changed.json()["data"]["max_per_lane"] == 5
    bad = client.put("/api/opportunities/settings", headers=who["risk"], json={"persistence": 9})
    assert bad.status_code == 422
