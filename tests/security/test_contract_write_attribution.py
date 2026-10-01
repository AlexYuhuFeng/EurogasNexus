"""Governed upstream-contract writes are attributable and fail closed (Architecture V2).

``POST /api/route-cost/upstream-contracts`` used to be an unattributed
overwrite: it accepted no actor, wrote no audit row and replaced the stored
economic terms in place. These tests pin the fixed posture:

* the actor is the authenticated principal resolved through
  ``require_acting_actor`` *before* any database access - a request-body field
  is never trusted, and a request with no resolved identity is refused before
  the write could be attempted;
* the GOVERNED permission and the commercial boundary are unchanged;
* the audit trail names the authenticated principal, never a caller-supplied
  name.

The revision-capture lifecycle (create, replay, economic change, metadata-only
change and rollback) is exercised in
``tests/integration/test_route_cost_contract_write_revisions.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public import route_cost as route_cost_routes
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    UpstreamContractRevisionRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.security.permissions import Permission, permission_for_path

PUBLIC_TOKEN = "test-public-api-token"
CONTRACT_PATH = "/api/route-cost/upstream-contracts"
CONTRACT_ID = "attribution-ttf-supply-2025"


def _body(**overrides: object) -> dict[str, object]:
    """A full valid upsert body; extra keys mimic a client trying to name an actor."""

    payload: dict[str, object] = {
        "contract_id": CONTRACT_ID,
        "contract_name": "Attribution TTF supply 2025",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": 125.5,
        "contract_price_gbp_mwh": 29.75,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2,
        "nomination_tolerance_pct": 1,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
        "annual_financing_rate_pct": 6,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": ["NBP", "TTF"],
        "eligible_sale_modes": ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
        "variable_cost_gbp_mwh": 0.75,
        "regas_fee_gbp_mwh": 1.25,
        "fuel_loss_allowance_pct": 1.5,
        "notes": "operator draft decision support",
    }
    payload.update(overrides)
    return payload


def _prepare_db(tmp_path, monkeypatch) -> str:
    """A throw-away SQLite runtime store, configured like a real deployment."""

    database_url = f"sqlite+pysqlite:///{(tmp_path / 'contract-write.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _bearer(
    session: Session, *, name: str, roles: list[str], scopes: list[str]
) -> tuple[str, str]:
    row = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role=roles[0],
        data_scopes=scopes,
    )
    row.roles = list(roles)
    _key, bearer = create_identity_api_key(session, row.principal_id, display_name="contract")
    return row.principal_id, bearer


def _headers(bearer: str | None = None) -> dict[str, str]:
    headers = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}
    if bearer:
        headers["X-Eurogas-Identity"] = bearer
    return headers


def _session(url: str) -> Session:
    return Session(create_engine(url, future=True))


def test_contract_write_is_still_a_governed_commercial_write() -> None:
    """The posture this slice must not change: GOVERNED inside the commercial boundary."""

    assert permission_for_path(CONTRACT_PATH) is Permission.GOVERNED


def test_identity_less_request_is_refused_before_any_store_access(
    tmp_path, monkeypatch
) -> None:
    """No principal means no write, even with a configured runtime database."""

    url = _prepare_db(tmp_path, monkeypatch)
    bare_request = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(HTTPException) as denied:
        route_cost_routes.upsert_upstream_contract(
            route_cost_routes.UpstreamContractUpsertRequest(**_body()),
            bare_request,
        )

    assert denied.value.status_code == 401
    assert denied.value.detail["error"] == "authentication_required"
    # The store was configured and reachable: a route that touched it first
    # would have written. Nothing was written.
    with _session(url) as session:
        assert session.query(UpstreamResourceContractRecord).count() == 0
        assert session.query(UpstreamContractRevisionRecord).count() == 0
        assert session.query(AuditEventRecord).count() == 0


def test_body_supplied_actor_is_ignored_and_the_principal_is_recorded(
    tmp_path, monkeypatch
) -> None:
    """A caller who types an actor name does not attribute the write to them."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        analyst_id, analyst_bearer = _bearer(
            session, name="contract-trader", roles=["ANALYST"], scopes=["TTF"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(
        CONTRACT_PATH,
        json=_body(actor="spoofed-actor", recorded_by="spoofed-actor"),
        headers=_headers(analyst_bearer),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["contract_id"] == CONTRACT_ID
    with _session(url) as session:
        upserts = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "route_cost.contract.upsert")
            .all()
        )
        assert [row.principal for row in upserts] == [analyst_id]
        revisions = session.query(UpstreamContractRevisionRecord).all()
        assert [row.recorded_by for row in revisions] == [analyst_id]
        assert (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.principal == "spoofed-actor")
            .count()
            == 0
        )


def test_write_without_read_authority_is_refused_before_any_write(
    tmp_path, monkeypatch
) -> None:
    """A VIEWER identity keeps the existing GOVERNED refusal, with no side effects."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        _viewer_id, viewer_bearer = _bearer(
            session, name="contract-viewer", roles=["VIEWER"], scopes=["TTF"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(CONTRACT_PATH, json=_body(), headers=_headers(viewer_bearer))

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "identity_role_forbidden"
    with _session(url) as session:
        assert session.query(UpstreamResourceContractRecord).count() == 0
        assert session.query(UpstreamContractRevisionRecord).count() == 0
        assert session.query(AuditEventRecord).count() == 0


def test_administration_only_identity_is_refused_by_the_commercial_boundary(
    tmp_path, monkeypatch
) -> None:
    """Rank is not commercial access: an ADMIN without a commercial role is refused."""

    url = _prepare_db(tmp_path, monkeypatch)
    with _session(url) as session:
        _admin_id, admin_bearer = _bearer(
            session, name="contract-admin", roles=["ADMIN"], scopes=[]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(CONTRACT_PATH, json=_body(), headers=_headers(admin_bearer))

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "commercial_access_not_granted"
    with _session(url) as session:
        assert session.query(UpstreamResourceContractRecord).count() == 0
        assert session.query(UpstreamContractRevisionRecord).count() == 0
        assert session.query(AuditEventRecord).count() == 0
