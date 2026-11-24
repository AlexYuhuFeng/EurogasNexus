"""GOV-1 (P5): a governed write and its audit row commit together, or neither does.

The audit store is made to refuse rows at flush time (as a full disk, a revoked grant or a
dropped table would), and each governed write is then attempted. The write must answer 503
``audit_unavailable`` and leave nothing behind; with the store healthy again the same write
succeeds and its audit row is there.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    ChangeRequestRecord,
    CreditLineRecord,
    HedgeApprovalRecord,
    LngCargoHedgeRecord,
    LngCargoRecord,
    OpportunitySettingRecord,
    TraderMandateRecord,
    TradingBookRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.models.strategy_access import IdentityGroupRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.governance.four_eyes import FOUR_EYES_BY_ACTION

PUBLIC_TOKEN = "test-public-api-token"


@contextmanager
def _audit_store_refuses():
    """Every flush that carries an audit row fails, as a broken audit store would."""

    def refuse(session, _context, _instances):
        if any(isinstance(item, AuditEventRecord) for item in session.new):
            raise OperationalError("INSERT INTO audit_events", {}, Exception("disk full"))

    event.listen(Session, "before_flush", refuse)
    try:
        yield
    finally:
        event.remove(Session, "before_flush", refuse)


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'gov.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC).replace(microsecond=0)
    who: dict[str, dict[str, str]] = {}
    with Session(engine) as session:
        for name, role in (
            ("analyst", "ANALYST"),
            ("risk", "REVIEWER"),
            ("checker", "REVIEWER"),
            ("admin", "ADMIN"),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            who[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.add(
            UpstreamResourceContractRecord(
                contract_id="nbp-supply",
                contract_name="NBP supply",
                resource_type="PIPELINE_IMPORT",
                delivery_point_name="NBP",
                gas_year=f"{now.year - 1}+",
                delivery_quantity_mwh_per_day=1_000.0,
                contract_price_gbp_mwh=30.0,
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=2.0,
                nomination_tolerance_pct=1.0,
                tolerance_risk_allowance_gbp_mwh=None,
                annual_financing_rate_pct=5.0,
                owned_entry_capacity_mwh_per_day=None,
                owned_exit_capacity_mwh_per_day=None,
                allowed_exit_points=["NBP"],
                eligible_sale_modes=["LOCAL_MARKET_SALE"],
                notes=None,
                book_id=None,
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        session.add(
            TradingBookRecord(
                book_id="lng-nwe",
                name="LNG NWE",
                legal_entity="Demo Energy BV",
                region="NWE",
                business="LNG",
                base_currency="EUR",
                active=True,
                updated_by="test",
                updated_at_utc=now,
            )
        )
        session.add(
            LngCargoRecord(
                cargo_id="own-1",
                vessel_name="Vessel own-1",
                status="laden",
                load_port="Sabine Pass",
                departed_at_utc=now - timedelta(days=5),
                destination_terminal="Gate Terminal",
                eta_utc=now + timedelta(days=12),
                position_lat=46.9,
                position_lon=-14.2,
                position_at_utc=now - timedelta(hours=2),
                energy_gwh=1_000.0,
                book_id="lng-nwe",
                source_system="ETRM_CSV",
                source_reference="etrm:own-1",
                updated_at_utc=now,
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return engine, who


def _month(offset: int) -> str:
    today = datetime.now(UTC).date().replace(day=1)
    year, month = divmod(today.month - 1 + offset, 12)
    return f"{today.year + year:04d}-{month + 1:02d}"


def _writes():
    """Each governed write: who makes it, the request, and the record it would leave."""

    return [
        (
            "risk",
            "PUT",
            "/api/portfolio/credit-lines/CNA",
            {"name": "Centrica plc", "limit_amount": 1_000_000, "currency": "GBP"},
            CreditLineRecord,
            "risk.credit_line.update",
        ),
        (
            "risk",
            "PUT",
            "/api/portfolio/trader-mandates/M1",
            {
                "trader": "jdoe",
                "display_name": "J. Doe",
                "hubs": ["NBP"],
                "max_net_mwh_per_month": 10_000,
                "max_tenor_months": 12,
            },
            TraderMandateRecord,
            "risk.mandate.update",
        ),
        (
            "risk",
            "PUT",
            "/api/portfolio/hedge-approvals/nbp-supply",
            {"max_hedge_ratio_pct": 50, "approval_ref": "CC-1"},
            HedgeApprovalRecord,
            "risk.hedge_approval.update",
        ),
        (
            "risk",
            "PUT",
            "/api/opportunities/settings",
            {"max_per_lane": 5},
            OpportunitySettingRecord,
            "opportunities.thresholds.update",
        ),
        (
            "analyst",
            "PUT",
            "/api/lng/cargoes/own-1/hedges",
            {"legs": [{"hub": "TTF", "month": _month(1), "mwh": -100_000}]},
            LngCargoHedgeRecord,
            "lng.cargo_hedges",
        ),
        (
            "admin",
            "POST",
            "/api/access/groups",
            {"name": "LNG desk"},
            IdentityGroupRecord,
            "access.group.create",
        ),
    ]


def test_a_governed_write_fails_and_leaves_nothing_when_its_audit_row_cannot_be_written(
    tmp_path, monkeypatch
):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    for actor, method, path, body, record, action in _writes():
        with _audit_store_refuses():
            refused = client.request(method, path, json=body, headers=who[actor])
        assert refused.status_code == 503, (path, refused.text)
        payload = refused.json()
        assert payload["error"] == "audit_unavailable", path
        # P-17: a write under four eyes is first a proposal, refused the same way.
        proposed = "change_request.propose" if action in FOUR_EYES_BY_ACTION else action
        assert payload["detail"]["action"] == proposed
        assert payload["recoverability"] == "retry"
        with Session(engine) as session:
            assert session.query(record).count() == 0, path
            assert session.query(AuditEventRecord).filter_by(action=action).count() == 0
            assert session.query(ChangeRequestRecord).filter_by(state="pending").count() == 0

        done = client.request(method, path, json=body, headers=who[actor])
        if action in FOUR_EYES_BY_ACTION:
            # P-17: the write was proposed (its own audit row, nothing applied); the approval
            # is the same write and fails the same way when its audit row cannot be written.
            assert done.status_code == 202, (path, done.text)
            change_id = done.json()["data"]["change"]["change_id"]
            approve = f"/api/portfolio/change-requests/{change_id}/approve"
            with _audit_store_refuses():
                refused = client.post(approve, headers=who["checker"])
            assert refused.status_code == 503, (path, refused.text)
            assert refused.json()["detail"]["action"] == action
            with Session(engine) as session:
                assert session.query(record).count() == 0, path
                assert session.get(ChangeRequestRecord, change_id).state == "pending"
            done = client.post(approve, headers=who["checker"])
        assert done.status_code == 200, (path, done.text)
        with Session(engine) as session:
            assert session.query(record).count() >= 1, path
            assert session.query(AuditEventRecord).filter_by(action=action).count() == 1, path


def test_a_read_still_answers_when_its_audit_row_cannot_be_written(tmp_path, monkeypatch):
    _engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    with _audit_store_refuses():
        listed = client.get("/api/access/groups", headers=who["admin"])
        users = client.get("/api/access/users", headers=who["admin"])
    assert listed.status_code == 200, listed.text
    assert users.status_code == 200, users.text
