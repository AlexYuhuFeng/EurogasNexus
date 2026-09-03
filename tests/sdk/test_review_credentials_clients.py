"""SDK review and credentials client tests (P1 coverage closure)."""

import httpx
from eurogas_nexus_sdk.credentials import fetch_credential_providers
from eurogas_nexus_sdk.review import (
    ReviewDecisionInput,
    fetch_review_decisions,
    record_review_decision,
)


def test_fetch_review_decisions_lists_rows(monkeypatch) -> None:
    def fake_get(url: str, *, params, timeout: float, **kwargs) -> httpx.Response:
        assert params["limit"] == "50"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "decision_id": "d1",
                        "entity_type": "strategy_run",
                        "entity_id": "run-1",
                        "actor": "operator",
                        "decision": "accepted",
                        "note": None,
                        "created_at_utc": "2026-07-01T12:00:00+00:00",
                    }
                ],
                "meta": {"source_references": ["review", "audit-events"], "warnings": []},
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_review_decisions("http://example.test", limit=50)

    assert len(result.data) == 1
    assert result.data[0].decision == "accepted"
    assert result.data[0].actor == "operator"


def test_record_review_decision_posts_and_returns_row(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url: str, *, json, timeout: float, **kwargs) -> httpx.Response:
        captured["body"] = json
        return httpx.Response(
            200,
            json={
                "data": {
                    "decision_id": "d2",
                    "entity_type": "strategy_run",
                    "entity_id": "run-2",
                    "actor": "ops-user",
                    "decision": "rejected",
                    "note": "bad output",
                    "created_at_utc": "2026-07-01T12:05:00+00:00",
                },
                "meta": {"source_references": ["review", "audit-events"], "warnings": []},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = record_review_decision(
        "http://example.test",
        ReviewDecisionInput(
            entity_type="strategy_run",
            entity_id="run-2",
            actor="ops-user",
            decision="rejected",
            note="bad output",
        ),
    )

    assert result.data is not None
    assert result.data.note == "bad output"
    assert captured["body"]["decision"] == "rejected"


def test_fetch_credential_providers_lists_posture(monkeypatch) -> None:
    def fake_get(url: str, *, timeout: float, **kwargs) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "provider_id": "GIE",
                        "display_name": "GIE AGSI/ALSI",
                        "credential_required": True,
                        "default_model": None,
                        "configured": True,
                        "status": "configured",
                        "label": "default",
                        "redacted_preview": "key***",
                        "last_tested_at_utc": None,
                        "last_test_status": None,
                    }
                ],
                "meta": {"source_references": ["credentials"], "warnings": []},
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_credential_providers("http://example.test")

    assert len(result.data) == 1
    assert result.data[0].provider_id == "GIE"
    assert result.data[0].configured is True
    assert result.data[0].redacted_preview == "key***"
