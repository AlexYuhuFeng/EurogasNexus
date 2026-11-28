"""The SDK's error type and base URL handling (documentation review, section 7)."""

from __future__ import annotations

import httpx
import pytest
from eurogas_nexus_sdk import NexusAPIError, _http


def _respond(monkeypatch, status: int, body, seen: list[str] | None = None):
    def fake_get(url, **_kwargs):
        if seen is not None:
            seen.append(url)
        return httpx.Response(status, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)


def test_a_refusal_raises_a_typed_error_with_the_servers_fields(monkeypatch):
    _respond(monkeypatch, 403, {
        "detail": {"code": "permission_denied", "message": "Needs ANALYST."},
        "recoverability": "fix_request",
        "correlation_id": "abc123",
    })
    response = _http.get("http://nexus.local/api/portfolio/positions")
    with pytest.raises(NexusAPIError) as caught:
        response.raise_for_status()
    error = caught.value
    assert isinstance(error, httpx.HTTPStatusError)  # existing handlers keep working
    assert (error.status_code, error.code, error.message) == (
        403, "permission_denied", "Needs ANALYST.",
    )
    assert error.recoverability == "fix_request" and error.correlation_id == "abc123"
    assert str(error) == "403 permission_denied: Needs ANALYST. (correlation id abc123)"


def test_a_validation_refusal_names_each_field(monkeypatch):
    _respond(monkeypatch, 422, {"detail": [
        {"loc": ["body", "laytime_hours"], "msg": "Input should be greater than or equal to 0"},
    ]})
    with pytest.raises(NexusAPIError) as caught:
        _http.get("http://nexus.local/api/x").raise_for_status()
    assert caught.value.code == "validation_failed"
    assert "body.laytime_hours" in caught.value.message


def test_success_passes_and_a_body_that_is_not_json_still_raises(monkeypatch):
    _respond(monkeypatch, 200, {"data": []})
    assert _http.get("http://nexus.local/api/x").raise_for_status().status_code == 200

    def html(url, **_kwargs):
        return httpx.Response(502, text="<html>proxy</html>", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", html)
    with pytest.raises(NexusAPIError) as caught:
        _http.get("http://nexus.local/api/x").raise_for_status()
    assert caught.value.code is None and caught.value.status_code == 502


def test_a_base_url_may_end_with_a_slash(monkeypatch):
    seen: list[str] = []
    _respond(monkeypatch, 200, {"data": []}, seen)
    _http.get("http://nexus.local:8000//api/market/quotes?next=a//b")
    assert seen == ["http://nexus.local:8000/api/market/quotes?next=a//b"]


