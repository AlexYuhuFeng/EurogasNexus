"""SDK health client tests."""

import httpx
import pytest

from eurogas_nexus.sdk.health_client import fetch_health


def test_fetch_health_calls_backend_health_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def _fake_get(url: str, timeout: float) -> httpx.Response:
        captured["url"] = url
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "service": "eurogas-nexus",
                "version": "0.1.0",
                "profile": "development",
            },
            request=request,
        )

    monkeypatch.setattr(httpx, "get", _fake_get)

    payload = fetch_health("http://localhost:8000")

    assert captured["url"] == "http://localhost:8000/api/health"
    assert payload.status == "ok"
