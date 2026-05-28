"""CLI health helper tests."""

import pytest

from eurogas_nexus.cli.health import run_health_check
from eurogas_nexus.sdk.health_client import HealthPayload


def test_run_health_check_formats_sdk_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_fetch_health(base_url: str) -> HealthPayload:
        assert base_url == "http://localhost:8000"
        return HealthPayload(
            status="ok",
            service="eurogas-nexus",
            version="0.1.0",
            profile="development",
        )

    monkeypatch.setattr("eurogas_nexus.cli.health.fetch_health", _fake_fetch_health)

    output = run_health_check("http://localhost:8000")

    assert output == "status=ok service=eurogas-nexus version=0.1.0 profile=development"
