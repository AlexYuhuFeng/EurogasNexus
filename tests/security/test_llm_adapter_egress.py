"""Deployment egress policy applies even when a caller bypasses route guards."""

import httpx
import pytest

from eurogas_nexus.core.config import get_settings
from eurogas_nexus.llm.deepseek import invoke_deepseek
from eurogas_nexus.llm.deepseek import test_deepseek_connection as check_connection


@pytest.fixture(autouse=True)
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "environment,enabled", [("development", "false"), ("trial", "true"), ("release", "true")]
)
@pytest.mark.parametrize("operation", ["completion", "credential_test"])
def test_disabled_adapter_never_transmits(monkeypatch, environment, enabled, operation):
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", environment)
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", enabled)

    def forbidden(*args, **kwargs):
        pytest.fail("Disabled provider attempted an outbound HTTP request")

    monkeypatch.setattr(httpx, "post", forbidden)
    monkeypatch.setattr(httpx, "get", forbidden)
    result = (
        invoke_deepseek(
            api_key="synthetic-only", messages=[{"role": "user", "content": "private test data"}]
        )
        if operation == "completion"
        else check_connection(api_key="synthetic-only")
    )
    assert result.status == "provider_disabled"
    assert result.error_code == "LLM_PROVIDER_DISABLED_IN_PROFILE"
    assert result.content is None


def test_explicitly_enabled_development_calls_both_operations(monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", "true")
    requests = []

    def post(url, **kwargs):
        requests.append(("POST", url))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [{"message": {"content": "synthetic result"}}],
            },
        )

    def get(url, **kwargs):
        requests.append(("GET", url))
        return httpx.Response(200, request=httpx.Request("GET", url), json={"data": []})

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "get", get)
    assert invoke_deepseek(api_key="synthetic-only", messages=[]).content == "synthetic result"
    assert check_connection(api_key="synthetic-only").status == "success"
    assert requests == [
        ("POST", "https://api.deepseek.com/chat/completions"),
        ("GET", "https://api.deepseek.com/models"),
    ]
