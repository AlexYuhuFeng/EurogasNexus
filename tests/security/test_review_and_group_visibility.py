"""Owner visibility of review evidence and administration of identity groups.

These assertions used to live in the strategy-sharing tests
(``test_strategy_aggregate_privacy.py``, ``test_strategy_owner_sharing.py``), which the
strategy-laboratory removal deleted. The controls they covered are not part of the laboratory
and stay: review decisions and evidence are filtered by the owner of the reviewed artefact
before any limit, the review capability refuses an unnamed caller, evidence computed over a
source family the caller is not entitled to is withheld, and identity groups are managed by an
administrator only, who cannot add themselves.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AgentReviewPackRecord
from eurogas_nexus.db.repositories.agents import create_agent_run
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.db.repositories.review import list_review_decisions, record_review_decision
from eurogas_nexus.security.identity import AuthenticatedPrincipal


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'visibility.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    ids: dict[str, str] = {}
    bearers: dict[str, str] = {}
    with Session(engine) as session:
        for name, role in (
            ("owner", "ANALYST"),
            ("reader", "ANALYST"),
            ("outsider", "ANALYST"),
            ("admin", "ADMIN"),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _, bearer = create_identity_api_key(session, row.principal_id, scopes=["*"])
            ids[name], bearers[name] = row.principal_id, bearer
        create_agent_run(
            session,
            agent_run_id="owner-agent",
            principal_id=ids["owner"],
            user_objective="private research",
        )
        session.add(
            AgentReviewPackRecord(
                review_pack_id="owner-review-pack",
                agent_run_id="owner-agent",
                objective="Private owner review",
            )
        )
        session.flush()
        record_review_decision(
            session,
            entity_type="intraday_opportunity",
            entity_id="public",
            actor="owner",
            decision="accepted",
            note="public-note",
        )
        record_review_decision(
            session,
            entity_type="agent_review_pack",
            entity_id="owner-review-pack",
            actor="owner",
            decision="accepted",
            note="secret-agent-note",
        )
        session.commit()
    yield engine, ids, bearers
    engine.dispose()


def _person(principal_id: str, name: str, scopes=("*",)) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=principal_id,
        name=name,
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=scopes,
    )


def test_review_decisions_are_filtered_by_owner_before_the_limit(store) -> None:
    engine, ids, _ = store
    with Session(engine) as session:
        # The newer private decision cannot crowd the public one out of a one-row page.
        assert [
            row["entity_id"]
            for row in list_review_decisions(session, principal_id=ids["reader"], limit=1)
        ] == ["public"]
        assert {
            row["entity_id"] for row in list_review_decisions(session, principal_id=ids["owner"])
        } == {"public", "owner-review-pack"}


def test_review_evidence_of_another_owner_reads_as_not_found(store) -> None:
    from eurogas_nexus.application.projections.review_context import _resolve_evidence
    from eurogas_nexus.db.repositories.review import can_read_review_target

    engine, ids, _ = store
    now = datetime.now(UTC)
    with Session(engine) as session:
        evidence = _resolve_evidence(
            session,
            _person(ids["reader"], "reader"),
            "agent_review_pack",
            "owner-review-pack",
            now_utc=now,
        )
        assert evidence["artifact"] is None
        assert evidence["unavailable_reason"] == "EVIDENCE_NOT_FOUND"
        assert can_read_review_target(
            session, "agent_review_pack", "owner-review-pack", ids["owner"]
        )
        assert not can_read_review_target(
            session, "agent_review_pack", "owner-review-pack", ids["reader"]
        )


def test_evidence_over_an_unentitled_source_family_is_withheld(store, monkeypatch) -> None:
    from eurogas_nexus.application.projections import review_context

    engine, ids, _ = store

    def declared(_session, entity_id, _now):
        return {"id": entity_id, "source_systems": ["EEX", "ENTSOG"]}, ["RUN_WARNING"]

    monkeypatch.setitem(review_context._EVIDENCE_RESOLVERS, "intraday_opportunity", declared)
    with Session(engine) as session:
        entry = review_context._resolve_evidence(
            session,
            _person(ids["reader"], "reader", scopes=("ENTSOG",)),
            "intraday_opportunity",
            "public",
            now_utc=datetime.now(UTC),
        )
        assert entry["available"] is False
        assert entry["unavailable_reason"] == "ENTITLEMENT_DENIED"
        assert entry["artifact"] is None
        assert entry["warnings"] == ["ENTITLEMENT_DENIED"]
        entitled = review_context._resolve_evidence(
            session,
            _person(ids["reader"], "reader"),
            "intraday_opportunity",
            "public",
            now_utc=datetime.now(UTC),
        )
        assert entitled["available"] is True


def test_the_review_capability_refuses_an_unnamed_caller_and_another_owners_target(
    store,
) -> None:
    from eurogas_nexus.application.agents.review_access import guard_review_capability

    engine, ids, _ = store
    definition = SimpleNamespace(capability_id="review.get", capability_version="v1")
    target = {"entity_type": "agent_review_pack", "entity_id": "owner-review-pack"}
    with Session(engine) as session:
        for principal_id in (None, "not-a-principal"):
            refused = guard_review_capability(
                session, {}, SimpleNamespace(principal_id=principal_id), definition
            )
            assert refused is not None
            assert refused.failure.code == "ENTITY_NOT_FOUND"
        assert (
            guard_review_capability(
                session, target, SimpleNamespace(principal_id=ids["reader"]), definition
            )
            is not None
        )
        assert (
            guard_review_capability(
                session, target, SimpleNamespace(principal_id=ids["owner"]), definition
            )
            is None
        )


def test_groups_are_admin_managed_and_membership_changes_are_immediate(store) -> None:
    _engine, ids, bearers = store

    def client(name: str) -> TestClient:
        return TestClient(
            create_app(Settings(api_profile="release")),
            headers={
                "X-Eurogas-Api-Key": "test-public-api-token",
                "X-Eurogas-Identity": bearers[name],
            },
        )

    admin, owner, outsider = client("admin"), client("owner"), client("outsider")
    try:
        assert owner.post("/api/access/groups", json={"name": "x"}).status_code == 403
        created = admin.post("/api/access/groups", json={"name": "Approved team"})
        assert created.status_code == 200, created.text
        group = created.json()["data"]["group_id"]
        for name in ("owner", "reader"):
            assert admin.put(f"/api/access/groups/{group}/members/{ids[name]}").status_code == 200
        # Membership is an access grant: an administrator cannot grant it to themselves.
        assert admin.put(f"/api/access/groups/{group}/members/{ids['admin']}").status_code == 403
        assert outsider.get("/api/me/groups").json()["data"] == []
        assert owner.get("/api/me/groups").json()["data"] == [
            {"group_id": group, "name": "Approved team"}
        ]
        assert admin.delete(f"/api/access/groups/{group}/members/{ids['owner']}").status_code == 200
        assert owner.get("/api/me/groups").json()["data"] == []
        assert admin.put(f"/api/access/groups/{group}/members/{ids['owner']}").status_code == 200
        disabled = admin.patch(f"/api/access/groups/{group}", json={"status": "DISABLED"})
        assert disabled.status_code == 200, disabled.text
        assert owner.get("/api/me/groups").json()["data"] == []
    finally:
        for item in (admin, owner, outsider):
            item.close()
