"""Review-decision actor integrity (W0-03 C13).

A trader review decision is a governance act: the platform stores who made it and writes an
audit event under that name. The path used to take the actor from the request body and repeat
it as the audit event's principal, so a caller could attribute a decision - and the audit
trail - to somebody who never made it. The Decision Case path had already resolved the actor
from the authenticated identity; these tests pin that both now answer "who decided" the same
way:

- the stored decision and the audit event name the authenticated identity;
- a body that claims a different actor is recorded under the identity, and the envelope
  reports the ignored claim instead of believing it;
- a deployment without a verified identity records its own acting principal, because that is
  who acted - not a name somebody typed.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord
from eurogas_nexus.security.identity import AuthenticatedPrincipal

DECISION = {
    "entity_type": "intraday_opportunity",
    "entity_id": "opp-actor-1",
    "decision": "accepted",
    "note": "checked against the pool result",
}


def _principal(name: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=f"principal-{name}",
        name=name,
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=("ENTSOG",),
        roles=("ANALYST",),
        auth_method="identity_key",
    )


def _database(tmp_path, monkeypatch) -> str:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'review-actor.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(database_url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _client(principal: AuthenticatedPrincipal | None = None) -> TestClient:
    """The app with an optional resolved identity, installed the way the profile does.

    The development profile is used deliberately: it does not authenticate the request, so the
    injected identity is the one the route sees. Under the release profile the authentication
    dependency resolves the request's own credential and overwrites it, which is the posture
    the no-identity test below covers.
    """

    app = create_app(Settings(api_profile="development"))
    if principal is not None:

        @app.middleware("http")
        async def _inject_identity(request, call_next):  # type: ignore[no-untyped-def]
            request.state.identity = principal
            return await call_next(request)

    return TestClient(app)


def _audit_rows(database_url: str, entity_id: str) -> list[tuple[str, str]]:
    """Every audit row for one decision as ``(action, principal)``.

    A review decision is audited twice by design - the repository records the decision event
    and the route records the governance action - so the rule is asserted over all of them: no
    writer may name an actor the platform did not authenticate.
    """

    with Session(create_engine(database_url, future=True)) as session:
        rows = session.scalars(
            select(AuditEventRecord)
            .where(AuditEventRecord.resource == f"intraday_opportunity:{entity_id}")
            .order_by(AuditEventRecord.event_ts_utc)
        ).all()
    return [(row.action, row.principal) for row in rows]


def test_the_recorded_actor_is_the_authenticated_identity_not_the_body_claim(
    tmp_path, monkeypatch
) -> None:
    _database(tmp_path, monkeypatch)
    client = _client(_principal("analyst-river"))

    response = client.post(
        "/api/review/decisions",
        json={**DECISION, "actor": "somebody-else"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["actor"] == "analyst-river"
    # The claim is reported, not silently dropped: the caller learns the decision is not filed
    # under the name it typed.
    assert response.json()["meta"]["warnings"] == ["ACTOR_CLAIM_IGNORED:somebody-else"]


def test_every_audit_event_names_the_identity_and_never_the_claim(tmp_path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    client = _client(_principal("analyst-river"))

    response = client.post(
        "/api/review/decisions",
        json={**DECISION, "actor": "somebody-else"},
    )
    assert response.status_code == 200

    rows = _audit_rows(database_url, DECISION["entity_id"])
    assert rows, "the decision was not audited at all"
    assert {principal for _action, principal in rows} == {"analyst-river"}
    # Both writers are covered: the repository's decision event and the route's governance one.
    assert "review.decision.record" in {action for action, _principal in rows}


def test_a_decision_without_an_actor_field_is_still_attributed(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = _client(_principal("analyst-river"))

    response = client.post("/api/review/decisions", json=DECISION)

    assert response.status_code == 200
    # The field is optional now: not sending it costs the caller nothing, because the actor
    # was never the caller's to supply.
    assert response.json()["data"]["actor"] == "analyst-river"
    assert response.json()["meta"]["warnings"] == []


def test_a_claim_that_matches_the_identity_is_not_reported_as_ignored(
    tmp_path, monkeypatch
) -> None:
    _database(tmp_path, monkeypatch)
    client = _client(_principal("analyst-river"))

    response = client.post(
        "/api/review/decisions",
        json={**DECISION, "actor": "analyst-river"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["actor"] == "analyst-river"
    # A caller that sent the truth is not nagged about it.
    assert response.json()["meta"]["warnings"] == []


def test_a_deployment_without_an_identity_records_its_own_acting_principal(
    tmp_path, monkeypatch
) -> None:
    database_url = _database(tmp_path, monkeypatch)
    # No identity is injected: this is the private-network compatibility posture, which
    # authenticates a deployment token rather than a person.
    client = _client(None)

    response = client.post(
        "/api/review/decisions",
        json={**DECISION, "actor": "somebody-else"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["actor"] == "public-api"
    assert response.json()["meta"]["warnings"] == ["ACTOR_CLAIM_IGNORED:somebody-else"]
    rows = _audit_rows(database_url, DECISION["entity_id"])
    assert {principal for _action, principal in rows} == {"public-api"}
