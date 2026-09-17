"""Separation-of-duties tests for entitlement grants (architecture finding C6b).

``W0-03_ARCHITECTURE_RECONCILIATION.md`` recorded that the access surface could write
``data_scopes`` for any principal, *including the administrator making the request*: the
grantee could grant itself. Architecture V2 section 7 of
``06_IDENTITY_ACCESS_CONTROL_PLANE.md`` is explicit that entitlement is granted and never
assumed, and a grant the grantee makes to itself is not a grant.

These tests pin the control that closes the self-service half of that finding, and pin that
it does not get in the way of ordinary administration: another principal's grants are still
changed by an administrator, a request that repeats the current grants still succeeds, and
lifecycle fields that are not authority (status, email) are untouched by the rule.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public.access import ENTITLEMENT_SELF_GRANT_FORBIDDEN
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
    get_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _db(tmp_path, monkeypatch) -> str:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'self-grant.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _principal(session: Session, *, name: str, role: str, scopes: list[str]) -> tuple[str, str]:
    row = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role=role,
        data_scopes=scopes,
    )
    row.roles = [role]
    _key, bearer = create_identity_api_key(session, row.principal_id, display_name="self-grant")
    return row.principal_id, bearer


def _headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


@pytest.fixture()
def access(tmp_path, monkeypatch):
    database_url = _db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        admin_id, admin_bearer = _principal(session, name="sod-admin", role="ADMIN", scopes=[])
        other_id, _other_bearer = _principal(
            session, name="sod-analyst", role="ANALYST", scopes=["ENTSOG"]
        )
        session.commit()
    client = TestClient(create_app(Settings(api_profile="release")))
    return {"client": client, "engine": engine, "admin_id": admin_id, "other_id": other_id,
            "admin_bearer": admin_bearer}


def test_an_administrator_cannot_widen_its_own_grants(access) -> None:
    client = access["client"]
    engine = access["engine"]

    response = client.patch(
        f"/api/access/users/{access['admin_id']}",
        headers=_headers(access["admin_bearer"]),
        json={"data_scopes": ["EEX", "TICE"]},
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == ENTITLEMENT_SELF_GRANT_FORBIDDEN
    assert detail["principal_id"] == access["admin_id"]

    # Nothing changed, and the attempt itself is recorded as a denial.
    with Session(engine) as session:
        row = get_identity_principal(session, access["admin_id"])
        assert list(row.data_scopes) == []
        outcome = next(
            event.outcome
            for event in session.execute(select(AuditEventRecord)).scalars().all()
            if event.action == "access.user.update"
        )
    assert outcome == "denied"


def test_an_administrator_cannot_change_its_own_roles_either(access) -> None:
    client = access["client"]

    response = client.patch(
        f"/api/access/users/{access['admin_id']}",
        headers=_headers(access["admin_bearer"]),
        json={"roles": ["ADMIN", "ANALYST"]},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == ENTITLEMENT_SELF_GRANT_FORBIDDEN


def test_repeating_the_current_grants_is_still_allowed(access) -> None:
    """An administration form that submits unchanged fields must keep working."""

    client = access["client"]

    response = client.patch(
        f"/api/access/users/{access['admin_id']}",
        headers=_headers(access["admin_bearer"]),
        json={"roles": ["ADMIN"], "data_scopes": []},
    )

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "ADMIN"


def test_lifecycle_fields_are_not_authority_and_stay_editable(access) -> None:
    """Disabling or renaming an identity is not an entitlement grant."""

    client = access["client"]

    response = client.patch(
        f"/api/access/users/{access['admin_id']}",
        headers=_headers(access["admin_bearer"]),
        json={"email": "admin@example.test"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["email"] == "admin@example.test"


def test_an_administrator_still_grants_another_principal(access) -> None:
    """The control refuses self-grants, not administration."""

    client = access["client"]

    response = client.patch(
        f"/api/access/users/{access['other_id']}",
        headers=_headers(access["admin_bearer"]),
        json={"data_scopes": ["EEX"]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["data_scopes"] == ["EEX"]
