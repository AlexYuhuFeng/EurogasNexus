"""The report catalogue always answers with a code (a demo crawl saw one 502 on it).

Its availability probe reads every report section for today, as a report would; on a busy or
cold store that can take longer than a page waits, and a section can fail in ways that are not
database errors. Neither may fail the catalogue, and an AI provider that is not set up (there
is no default provider since security review M10) is "not available", never an error.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.routes.public import reports


@pytest.fixture
def client():
    from eurogas_nexus.api.app import create_app

    reports._PROBES.clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    reports._PROBES.clear()


def test_a_probe_past_its_budget_answers_pending_and_finishes_behind(client, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(reports, "CATALOGUE_PROBE_SECONDS", 0.1)

    def slow(principal, language):
        release.wait(5)
        return {"can_generate": True, "sections": {}}

    monkeypatch.setattr(reports, "_read_availability", slow)
    response = client.get("/api/reports/catalogue")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["availability"] is None
    assert data["availability_state"]["code"] == "report_availability_pending"
    assert data["sections"], "the catalogue itself is there"
    release.set()
    # The same probe, finished, answers the next open (it is not kept as the warm view).
    again = client.get("/api/reports/catalogue").json()["data"]
    assert again["availability_state"]["code"] == "report_availability_ready"
    assert again["availability"]["can_generate"] is True


def test_a_section_that_fails_answers_unavailable_not_an_error(client, monkeypatch):
    def broken(principal, language):
        raise ValueError("a section builder failed")

    monkeypatch.setattr(reports, "_read_availability", broken)
    response = client.get("/api/reports/catalogue")
    assert response.status_code == 200
    state = response.json()["data"]["availability_state"]
    assert state == {"code": "report_availability_unavailable", "error_class": "ValueError"}


def test_an_unconfigured_ai_provider_is_not_available_never_a_failure(monkeypatch):
    def no_provider(*_args, **_kwargs):
        raise RuntimeError("no model provider is configured")

    monkeypatch.setattr("eurogas_nexus.security.provider_keys.load_provider_api_key", no_provider)
    monkeypatch.setattr(
        "eurogas_nexus.api.dependencies.ai_authority.ai_authority_denial", lambda _p: None
    )

    class _On:
        llm_external_provider_enabled = True

    monkeypatch.setattr("eurogas_nexus.core.config.get_settings", lambda: _On())
    assert reports._ai_state(object()) == (False, "no_key")
