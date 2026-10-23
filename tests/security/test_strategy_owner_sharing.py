"""Owner-controlled strategy sharing over authenticated HTTP boundaries."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import StrategyRecord, StrategyRunRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)


@pytest.fixture
def actors(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'sharing.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    clients, ids = {}, {}
    with Session(engine) as session:
        for name, role in [
            ("owner", "ANALYST"),
            ("reader", "ANALYST"),
            ("outsider", "ANALYST"),
            ("admin", "ADMIN"),
            ("viewer", "VIEWER"),
        ]:
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _, bearer = create_identity_api_key(session, row.principal_id, scopes=["*"])
            ids[name] = row.principal_id
            clients[name] = TestClient(
                create_app(Settings(api_profile="release")),
                headers={
                    "X-Eurogas-Api-Key": "test-public-api-token",
                    "X-Eurogas-Identity": bearer,
                },
            )
        session.commit()
    yield clients, ids, engine
    for client in clients.values():
        client.close()
    engine.dispose()


def create(client, strategy_id="private-strategy"):
    response = client.post(
        "/api/strategies",
        json={"strategy_id": strategy_id, "name": "Private 参数", "owner_principal_id": "spoofed"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def share(client, visibility, group_ids=None):
    return client.patch(
        "/api/strategies/private-strategy/sharing",
        json={"visibility": visibility, "group_ids": group_ids or []},
    )


def test_default_private_owner_and_shared_read_never_writes(actors):
    clients, ids, _ = actors
    dto = create(clients["owner"])
    assert dto["owner_principal_id"] == ids["owner"]
    assert dto["visibility"] == "PRIVATE" and dto["can_manage"]
    for role in ("reader", "outsider", "viewer"):
        assert clients[role].get("/api/strategies").json()["data"] == []
        assert clients[role].get("/api/strategies/private-strategy").status_code == 404
        assert share(clients[role], "PUBLIC").status_code in (403, 404)
    assert clients["admin"].get("/api/strategies/private-strategy").status_code == 403
    assert share(clients["owner"], "PUBLIC").status_code == 200
    for role in ("reader", "outsider", "viewer"):
        dto = clients[role].get("/api/strategies/private-strategy").json()["data"]
        assert not dto["can_manage"] and dto["shared_group_ids"] == []
        assert clients[role].patch(
            "/api/strategies/private-strategy/metadata", json={"name": "stolen"}
        ).status_code in (403, 404)
        assert share(clients[role], "PRIVATE").status_code in (403, 404)
    assert share(clients["owner"], "PRIVATE").status_code == 200
    assert clients["reader"].get("/api/strategies/private-strategy").status_code == 404


def test_groups_are_admin_managed_and_membership_revocation_is_immediate(actors):
    clients, ids, _ = actors
    create(clients["owner"])
    admin = clients["admin"]
    assert clients["owner"].post("/api/access/groups", json={"name": "x"}).status_code == 403
    group = admin.post("/api/access/groups", json={"name": "Approved team"}).json()["data"][
        "group_id"
    ]
    assert share(clients["owner"], "GROUPS", [group]).status_code == 422
    for role in ("owner", "reader"):
        assert admin.put(f"/api/access/groups/{group}/members/{ids[role]}").status_code == 200
    assert admin.put(f"/api/access/groups/{group}/members/{ids['admin']}").status_code == 403
    assert clients["outsider"].get("/api/me/groups").json()["data"] == []
    assert clients["owner"].get("/api/me/groups").json()["data"] == [
        {"group_id": group, "name": "Approved team"}
    ]
    assert share(clients["owner"], "GROUPS", [group]).status_code == 200
    assert clients["reader"].get("/api/strategies/private-strategy").status_code == 200
    assert clients["outsider"].get("/api/strategies/private-strategy").status_code == 404
    assert admin.delete(f"/api/access/groups/{group}/members/{ids['reader']}").status_code == 200
    assert clients["reader"].get("/api/strategies/private-strategy").status_code == 404
    assert admin.put(f"/api/access/groups/{group}/members/{ids['reader']}").status_code == 200
    assert (
        admin.patch(f"/api/access/groups/{group}", json={"status": "DISABLED"}).status_code == 200
    )
    assert clients["reader"].get("/api/strategies/private-strategy").status_code == 404
    assert clients["owner"].get("/api/strategies/private-strategy").status_code == 200


def test_version_and_run_ids_cannot_bypass_strategy_acl(actors):
    clients, _, engine = actors
    create(clients["owner"])
    response = clients["owner"].post(
        "/api/strategies/private-strategy/versions",
        json={"definition": {}, "hypothesis": "private hypothesis"},
    )
    assert response.status_code == 200, response.text
    version_id = response.json()["data"]["strategy_version_id"]
    for path in (
        "/api/strategies/private-strategy/versions",
        f"/api/strategy-versions/{version_id}",
    ):
        assert clients["reader"].get(path).status_code == 404
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(
            StrategyRunRecord(
                run_id="owned-run",
                strategy_id="private-strategy",
                strategy_version_id=version_id,
                run_mode="SHADOW_RUN",
                status="COMPLETED",
                started_at_utc=now,
                input_snapshot={},
                result_snapshot={},
                source_refs=[],
                missing_inputs=[],
                warnings=[],
                research_only=True,
                human_review_required=True,
            )
        )
        session.commit()
    for path in (
        "/api/strategy-runs/owned-run",
        "/api/strategy-runs/owned-run/events",
        "/api/strategy-lab/runs/owned-run",
    ):
        assert clients["reader"].get(path).status_code == 404
    assert clients["reader"].get("/api/strategy-runs").json()["data"] == []
    assert clients["reader"].get("/api/strategy-lab/runs").json()["data"] == []
    assert share(clients["owner"], "PUBLIC").status_code == 200
    assert clients["reader"].get(f"/api/strategy-versions/{version_id}").status_code == 200
    for path in (
        f"/api/strategy-versions/{version_id}/freeze",
        f"/api/strategy-versions/{version_id}/fork",
    ):
        assert clients["reader"].post(path, json={}).status_code == 404


def test_collection_filter_precedes_limit_and_legacy_is_quarantined(actors):
    clients, _, engine = actors
    create(clients["owner"], "visible")
    create(clients["reader"], "newer-invisible")
    with Session(engine) as session:
        now = datetime.now(UTC) + timedelta(days=1)
        session.add(
            StrategyRecord(
                strategy_id="legacy",
                name="unclaimed",
                description="",
                created_by="owner",
                created_at_utc=now,
                updated_at_utc=now,
                visibility="PUBLIC",
            )
        )
        session.commit()
    rows = clients["owner"].get("/api/strategies?limit=1").json()["data"]
    assert [row["strategy_id"] for row in rows] == ["visible"]
    assert clients["owner"].get("/api/strategies/legacy").status_code == 404


def test_invalid_audiences_and_legacy_token_do_not_acquire_ownership(actors):
    clients, _, _ = actors
    create(clients["owner"])
    assert share(clients["owner"], "PUBLIC", ["arbitrary"]).status_code == 422
    assert share(clients["owner"], "GROUPS").status_code == 422
    assert share(clients["owner"], "GROUPS", ["arbitrary"]).status_code == 422
    with TestClient(
        create_app(Settings(api_profile="release")),
        headers={"X-Eurogas-Api-Key": "test-public-api-token"},
    ) as legacy:
        assert legacy.post("/api/strategies", json={"name": "cannot own"}).status_code == 403
        assert legacy.get("/api/strategies").json()["data"] == []


def test_strategy_list_batches_owner_audiences_for_the_visible_page(actors):
    """Actual HTTP/SQL path issues one audience query regardless of page size."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from eurogas_nexus.db.models import IdentityGroupRecord, StrategyGroupShareRecord

    clients, _, engine = actors
    for index in range(4):
        create(clients["owner"], f"batch-{index}")
    create(clients["outsider"], "hidden-strategy")
    with Session(engine) as session:
        session.add_all(
            [
                IdentityGroupRecord(group_id="z-desk", name="Z desk"),
                IdentityGroupRecord(group_id="a-desk", name="A desk"),
            ]
        )
        session.flush()
        for index in range(4):
            session.get(StrategyRecord, f"batch-{index}").visibility = "GROUPS"
            for group_id in ("z-desk", "a-desk"):
                session.add(
                    StrategyGroupShareRecord(strategy_id=f"batch-{index}", group_id=group_id)
                )
        session.commit()

    statements = []

    def record(_conn, _cursor, statement, parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(Engine, "before_cursor_execute", record)
    try:
        counts = []
        for limit in (1, 3):
            statements.clear()
            response = clients["owner"].get(f"/api/strategies?limit={limit}")
            assert response.status_code == 200, response.text
            rows = response.json()["data"]
            assert len(rows) == limit
            assert all(row["shared_group_ids"] == ["a-desk", "z-desk"] for row in rows)
            assert all(row["can_manage"] for row in rows)
            counts.append(len(statements))
            audience_queries = [
                (sql, params)
                for sql, params in statements
                if sql.startswith("SELECT strategy_group_shares.strategy_id,")
            ]
            assert len(audience_queries) == 1
            assert set(audience_queries[0][1]) == {row["strategy_id"] for row in rows}
        assert counts[0] == counts[1]
    finally:
        event.remove(Engine, "before_cursor_execute", record)
    detail = clients["owner"].get("/api/strategies/batch-0").json()["data"]
    assert detail["shared_group_ids"] == ["a-desk", "z-desk"]
