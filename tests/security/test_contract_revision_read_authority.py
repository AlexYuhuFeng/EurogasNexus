"""Captured contract revisions keep the contract family's commercial authority.

The captured economic revisions stored by the governed contract write are
reachable through two new reads on the existing route-cost contract family.
They are commercial evidence of contract terms, so they keep the *existing*
authority of the sibling ``/api/route-cost/upstream-contracts`` surface and no
new authority is invented:

* the paths declare the GOVERNED (ANALYST) floor and stay inside the
  commercial-data boundary - a VIEWER keeps the role refusal and an
  ADMIN-without-a-commercial-role keeps the ``commercial_access_not_granted``
  refusal;
* authentication is the release profile's credential gate: a caller with no
  credential is refused before any evidence is read, while the deployment's
  compatibility principal (the documented SDK/CLI caller) keeps reading -
  personas and work modes are never consulted.

The behavioural read contract lives in
``tests/integration/test_route_cost_contract_revision_reads.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    UpstreamContractRevisionRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.db.repositories.route_cost import (
    capture_upstream_contract_revision,
    upsert_upstream_contract,
)
from eurogas_nexus.security.permissions import (
    Permission,
    permission_for_path,
    serves_commercial_data,
)

PUBLIC_TOKEN = "test-public-api-token"
CONTRACT_ID = "revision-read-authority-2025"
CONTRACT_PATH = "/api/route-cost/upstream-contracts"
REVISIONS_PATH = f"{CONTRACT_PATH}/{CONTRACT_ID}/revisions"
REVISION_PATH = f"{REVISIONS_PATH}/REVISION_ID"


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_id": CONTRACT_ID,
        "contract_name": "Revision read authority 2025",
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
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'revision-read-auth.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _session(url: str) -> Session:
    return Session(create_engine(url, future=True))


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
    _key, bearer = create_identity_api_key(session, row.principal_id, display_name="revision-read")
    return row.principal_id, bearer


def _headers(bearer: str | None = None) -> dict[str, str]:
    headers = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}
    if bearer:
        headers["X-Eurogas-Identity"] = bearer
    return headers


def _seed_captured_revision(url: str, *, actor: str = "capture-actor") -> str:
    """One stored contract row and one captured revision of it."""

    with _session(url) as session:
        upsert_upstream_contract(session, _body())
        result = capture_upstream_contract_revision(
            session,
            CONTRACT_ID,
            recorded_by=actor,
            recorded_at_utc=datetime.now(UTC),
        )
        assert result.revision is not None
        session.commit()
        return result.revision.contract_revision_id


def _evidence_state(url: str) -> tuple[int, int, str]:
    with _session(url) as session:
        revisions = session.query(UpstreamContractRevisionRecord).all()
        return (
            len(revisions),
            session.query(AuditEventRecord).count(),
            revisions[0].recorded_by if revisions else "",
        )


def test_revision_reads_are_governed_commercial_reads() -> None:
    """The declared authority is the sibling contract surface's, not a new one."""

    for path in (REVISIONS_PATH, REVISION_PATH):
        assert permission_for_path(path) is Permission.GOVERNED
        assert serves_commercial_data(path) is True


def test_viewer_role_keeps_the_governed_refusal_for_capture_evidence(
    tmp_path, monkeypatch
) -> None:
    """A VIEWER may not read captured contract economics, and nothing changes."""

    url = _prepare_db(tmp_path, monkeypatch)
    revision_id = _seed_captured_revision(url)
    before = _evidence_state(url)
    with _session(url) as session:
        _viewer_id, viewer_bearer = _bearer(
            session, name="revision-viewer", roles=["VIEWER"], scopes=["TTF"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    list_response = client.get(REVISIONS_PATH, headers=_headers(viewer_bearer))
    single_response = client.get(
        f"{REVISIONS_PATH}/{revision_id}", headers=_headers(viewer_bearer)
    )

    for response in (list_response, single_response):
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "identity_role_forbidden"
    assert _evidence_state(url) == before


def test_administration_only_identity_is_refused_by_the_commercial_boundary(
    tmp_path, monkeypatch
) -> None:
    """Rank is not commercial access: ADMIN alone cannot read capture evidence."""

    url = _prepare_db(tmp_path, monkeypatch)
    revision_id = _seed_captured_revision(url)
    before = _evidence_state(url)
    with _session(url) as session:
        _admin_id, admin_bearer = _bearer(
            session, name="revision-admin", roles=["ADMIN"], scopes=[]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    list_response = client.get(REVISIONS_PATH, headers=_headers(admin_bearer))
    single_response = client.get(
        f"{REVISIONS_PATH}/{revision_id}", headers=_headers(admin_bearer)
    )

    for response in (list_response, single_response):
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "commercial_access_not_granted"
    assert _evidence_state(url) == before


def test_uncredentialed_release_caller_is_refused_before_the_read(
    tmp_path, monkeypatch
) -> None:
    """Authentication is required: no credential means no evidence read."""

    url = _prepare_db(tmp_path, monkeypatch)
    _seed_captured_revision(url)
    before = _evidence_state(url)

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.get(REVISIONS_PATH)

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "public_api_token_missing"
    assert _evidence_state(url) == before


def test_deployment_token_caller_keeps_the_compatibility_read(
    tmp_path, monkeypatch
) -> None:
    """The SDK/CLI compatibility principal reads without any persona assignment."""

    url = _prepare_db(tmp_path, monkeypatch)
    _seed_captured_revision(url, actor="compatibility-capture")

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.get(REVISIONS_PATH, headers=_headers())

    assert response.status_code == 200, response.text
    evidence = response.json()["data"]["revisions"][0]
    assert evidence["contract_id"] == CONTRACT_ID
    assert evidence["recorded_by"] == "compatibility-capture"


@pytest.mark.parametrize("path", [REVISIONS_PATH, REVISION_PATH])
def test_revision_read_paths_are_declared_with_the_contract_family(path: str) -> None:
    """Every read path resolves to a declared permission (registry gate)."""

    assert permission_for_path(path) is Permission.GOVERNED
