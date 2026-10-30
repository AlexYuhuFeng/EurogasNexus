"""The LLM endpoint is installation configuration, validated before any call."""

import pytest

from eurogas_nexus.llm import deepseek
from eurogas_nexus.llm.provider import (
    LlmEndpointError,
    configured_endpoint,
    validate_base_url,
)


def test_default_is_deepseek_and_configuration_overrides_it():
    assert configured_endpoint({}).base_url == "https://api.deepseek.com"
    endpoint = configured_endpoint(
        {
            "EUROGAS_NEXUS_LLM_BASE_URL": "https://eu.models.example.com/v1/",
            "EUROGAS_NEXUS_LLM_MODEL": "mistral-large",
            "EUROGAS_NEXUS_LLM_PROVIDER_NAME": "mistral",
        }
    )
    assert (endpoint.base_url, endpoint.model, endpoint.provider_name) == (
        "https://eu.models.example.com/v1",
        "mistral-large",
        "MISTRAL",
    )


@pytest.mark.parametrize(
    "url",
    ["http://api.example.com", "ftp://x", "https://user:pw@api.example.com", "not a url"],
)
def test_unsafe_endpoints_are_refused(url):
    with pytest.raises(LlmEndpointError):
        validate_base_url(url)


def test_plain_http_is_allowed_for_an_on_premises_model():
    assert validate_base_url("http://10.1.2.3:8000/v1") == "http://10.1.2.3:8000/v1"
    assert validate_base_url("http://localhost:11434/v1") == "http://localhost:11434/v1"


def test_calls_go_to_the_configured_endpoint_with_its_model(monkeypatch):
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, model=json["model"])
        return _Response()

    monkeypatch.setenv("EUROGAS_NEXUS_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_MODEL", "qwen2.5-72b-instruct")
    monkeypatch.setattr(deepseek.httpx, "post", fake_post)
    monkeypatch.setattr(
        deepseek, "get_settings", lambda: type("S", (), {"llm_external_provider_enabled": True})()
    )
    result = deepseek.invoke_deepseek(api_key="k", messages=[{"role": "user", "content": "hi"}])
    assert result.status == "success"
    assert captured == {
        "url": "http://127.0.0.1:8001/v1/chat/completions",
        "model": "qwen2.5-72b-instruct",
    }
