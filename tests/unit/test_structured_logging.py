"""JSON logs: request id and principal id on every record, nothing secret, no client address."""

from __future__ import annotations

import io
import json
import logging
from types import SimpleNamespace

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core import structured_logging
from eurogas_nexus.core.config import Settings


def _record(message: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord("eurogas_nexus.test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_record_carries_request_and_principal_ids() -> None:
    state: dict = {}
    token = structured_logging.bind_request("abc123", state)
    try:
        formatter = structured_logging.JsonFormatter("test")
        before = json.loads(formatter.format(_record("hello")))
        # The identity dependency resolves the caller later (from a worker thread).
        state["identity"] = SimpleNamespace(principal_id="user-42")
        after = json.loads(formatter.format(_record("hello")))
    finally:
        structured_logging.unbind_request(token)
    assert before["request_id"] == "abc123"
    assert "principal_id" not in before
    assert after["principal_id"] == "user-42"
    assert after["level"] == "info"


def test_secrets_are_redacted_from_message_and_fields() -> None:
    formatter = structured_logging.JsonFormatter("test")
    line = formatter.format(
        _record(
            "connect postgresql+pg8000://nexus:hunter2secret@db:5432/x with Bearer abcdefghijkl",
            api_token="tok-should-not-appear",
            database_url="postgresql://u:p@h/db",
            count=3,
        )
    )
    assert "hunter2secret" not in line
    assert "abcdefghijkl" not in line
    assert "tok-should-not-appear" not in line
    assert "u:p@h" not in line
    payload = json.loads(line)
    assert payload["count"] == 3
    assert payload["api_token"] == "[REDACTED]"


def test_format_defaults_by_environment() -> None:
    assert structured_logging.log_format({"EUROGAS_NEXUS_ENV": "release"}) == "json"
    assert structured_logging.log_format({"EUROGAS_NEXUS_ENV": "development"}) == "text"
    assert (
        structured_logging.log_format(
            {"EUROGAS_NEXUS_ENV": "development", "EUROGAS_NEXUS_LOG_FORMAT": "json"}
        )
        == "json"
    )


def test_access_record_has_route_template_and_no_client_details(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "public-token")
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(structured_logging.JsonFormatter("test"))
    access = logging.getLogger(structured_logging.ACCESS_LOGGER)
    access.addHandler(handler)
    access.setLevel(logging.INFO)
    try:
        client = TestClient(create_app(Settings(api_profile="release")))
        response = client.get(
            "/api/sources/src-ecb/health?secret=zzz",
            headers={"X-Eurogas-Api-Key": "public-token"},
        )
    finally:
        access.removeHandler(handler)
    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line]
    assert lines, "no access record"
    record = lines[-1]
    assert record["request_id"] == response.headers["x-request-id"]
    assert record["status"] == response.status_code
    assert record["http_method"] == "GET"
    text = stream.getvalue()
    assert "zzz" not in text and "src-ecb" not in text and "testclient" not in text
