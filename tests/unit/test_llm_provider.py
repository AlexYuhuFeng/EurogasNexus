"""The LLM endpoint is installation configuration, validated before any call."""

import pytest

from eurogas_nexus.llm import deepseek
from eurogas_nexus.llm.provider import (
    LlmEndpointError,
    configured_endpoint,
    validate_base_url,
)


def test_there_is_no_default_provider_and_configuration_names_it():
    # Security review M10: no prompt leaves the server until an endpoint is chosen.
    with pytest.raises(LlmEndpointError, match="no model provider"):
        configured_endpoint({})
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


class _Ok:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}]}


def _enabled(monkeypatch, base_url="http://127.0.0.1:8001/v1"):
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_BASE_URL", base_url)
    monkeypatch.setattr(
        deepseek, "get_settings", lambda: type("S", (), {"llm_external_provider_enabled": True})()
    )


def test_a_self_hosted_model_is_called_without_a_key(monkeypatch):
    """Small-desk plan 3.6: the desk may point at its own model, with or without a key."""

    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(headers=headers)
        return _Ok()

    _enabled(monkeypatch)
    monkeypatch.setattr(deepseek.httpx, "post", fake_post)
    result = deepseek.invoke_deepseek(api_key=None, messages=[{"role": "user", "content": "x"}])
    assert result.status == "success"
    assert "Authorization" not in seen["headers"]
    # An endpoint outside the firm's network still needs a key, and nothing is sent without it.
    _enabled(monkeypatch, "https://api.example.com/v1")
    monkeypatch.setattr(deepseek.httpx, "post", lambda *a, **k: pytest.fail("sent without key"))
    assert deepseek.invoke_deepseek(api_key="", messages=[]).status == "credential_missing"


def test_an_unanswered_call_is_abandoned_at_its_time_limit(monkeypatch):
    """Small-desk plan section 5: a model that has not answered in time is not waited for."""

    import threading
    import time

    release = threading.Event()

    def slow_post(url, headers, json, timeout):
        assert timeout == pytest.approx(0.6)  # each network phase is bounded by the same limit
        release.wait(5)
        return _Ok()

    _enabled(monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_AI_TIMEOUT_SECONDS", "0.6")
    monkeypatch.setattr(deepseek.httpx, "post", slow_post)
    started = time.monotonic()
    result = deepseek.invoke_deepseek(api_key="k", messages=[{"role": "user", "content": "x"}])
    elapsed = time.monotonic() - started
    release.set()
    assert result.status == "timeout" and result.content is None
    assert 0.5 <= elapsed < 1.5, elapsed


def test_time_limits_default_to_three_seconds_and_refuse_nonsense():
    from eurogas_nexus.llm.provider import call_timeout_seconds

    assert call_timeout_seconds("interactive", {}) == 3.0
    assert call_timeout_seconds("draft", {}) == 240.0
    assert call_timeout_seconds("interactive", {"EUROGAS_NEXUS_AI_TIMEOUT_SECONDS": "5"}) == 5.0
    for bad in ("0", "-1", "abc", "1e9"):
        assert call_timeout_seconds("interactive", {"EUROGAS_NEXUS_AI_TIMEOUT_SECONDS": bad}) == 3.0


def test_every_registered_use_has_a_timing_and_interactive_uses_get_three_seconds(monkeypatch):
    from eurogas_nexus.application.ai_controls import call_budget
    from eurogas_nexus.domain.ai.register import AI_USES, TIMINGS

    monkeypatch.delenv("EUROGAS_NEXUS_AI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_AI_DRAFT_TIMEOUT_SECONDS", raising=False)
    for item in AI_USES:
        assert item.timing in TIMINGS
        expected = 3.0 if item.timing == "interactive" else 240.0
        assert call_budget(item.use, {})["timeout_seconds"] == expected
    drafts = {item.use for item in AI_USES if item.timing == "draft"}
    assert drafts == {"report_editor", "enrichment"}


def test_counterparty_names_are_aliased_out_and_restored_in_the_reply():
    from eurogas_nexus.application.ai_controls import GovernedModel
    from eurogas_nexus.application.ai_payloads import CounterpartyAliases

    aliases = CounterpartyAliases(("Northwind Gas Trading", "Acme Energy"))
    sent = []

    def call(messages):
        sent.extend(messages)
        return "Counterparty A is in breach; counterparty b is on watch.", "success"

    model = GovernedModel("explain", call, aliases=aliases)
    reply = model([{"role": "user", "content": "Northwind Gas Trading credit breach; ACME ENERGY "
                    "at 85%. Acme Energyx is another word."}])
    text = sent[0]["content"]
    assert "Northwind" not in text and "Acme Energy " not in text
    assert text.startswith("Counterparty A credit breach; Counterparty B at 85%.")
    assert "Acme Energyx" in text  # only whole names are replaced
    assert reply == "Northwind Gas Trading is in breach; Acme Energy is on watch."
