"""API pagination and error conventions tests (P3b convergence)."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_limit_parameter_is_validated_on_list_endpoints() -> None:
    client = TestClient(create_app())

    for path in (
        "/api/glossary",
        "/api/ingestion-runs",
        "/api/reference-network/nodes",
        "/api/reference-network/edges",
        "/api/reference-network/facilities",
        "/api/reference-network/market-hubs",
        "/api/reference-network/tso-access",
    ):
        zero = client.get(path, params={"limit": 0})
        assert zero.status_code == 422, f"{path} must reject limit=0"
        huge = client.get(path, params={"limit": 100_000})
        assert huge.status_code == 422, f"{path} must reject oversized limit"
        ok = client.get(path, params={"limit": 10})
        assert ok.status_code == 200, f"{path} must accept limit=10"


def test_review_decisions_respects_limit(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from eurogas_nexus.api.routes.public import review as review_routes

    rows = [
        {
            "decision_id": f"d{i}",
            "entity_type": "strategy_run",
            "entity_id": f"run-{i}",
            "actor": "operator",
            "decision": "accepted",
            "note": None,
            "created_at_utc": "2026-07-01T12:00:00+00:00",
        }
        for i in range(20)
    ]

    class _Ctx:
        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(review_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        "eurogas_nexus.db.session.get_session_factory",
        lambda: lambda: _Ctx(),
    )
    monkeypatch.setattr(
        "eurogas_nexus.db.repositories.review.list_review_decisions",
        lambda session, limit=100, **kwargs: rows[:limit],
    )

    client = TestClient(create_app())
    response = client.get("/api/review/decisions", params={"limit": 5})

    assert response.status_code == 200
    assert len(response.json()["data"]) == 5
