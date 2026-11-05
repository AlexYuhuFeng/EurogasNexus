"""One credential contract for every provider (#38)."""

import pytest

from eurogas_nexus.security.provider_credentials import (
    PROVIDER_CREDENTIAL_SPECS,
    CredentialFileError,
    effective_credential_source,
    resolve_provider_credential,
)


def _store(status=None, value=None):
    return {"stored_status": lambda: status, "stored_value": lambda: value}


def test_environment_overrides_the_store():
    env = {"EIA_API_KEY": "env-key"}
    resolved = resolve_provider_credential("EIA", env, **_store("configured", "db-key"))
    assert (resolved.value, resolved.source, resolved.variable) == ("env-key", "env", "EIA_API_KEY")


def test_blank_environment_falls_back_to_the_store():
    env = {"EIA_API_KEY": "  "}
    resolved = resolve_provider_credential("EIA", env, **_store("configured", "db-key"))
    assert (resolved.value, resolved.source) == ("db-key", "credential_store")


def test_an_administrator_disable_is_never_bypassed_by_the_environment():
    env = {"EIA_API_KEY": "env-key"}
    assert resolve_provider_credential("EIA", env, **_store("disabled", "db-key")) is None
    status = effective_credential_source("EIA", {"EIA_API_KEY": "env-key"}, **_store("disabled"))
    assert status["effective_source"] == "disabled"
    assert "disabled" in str(status["effective_source_detail"])


def test_canonical_variable_before_alias():
    env = {"EUROGAS_NEXUS_LLM_API_KEY": "canonical", "DEEPSEEK_API_KEY": "alias"}
    assert resolve_provider_credential("DEEPSEEK", env).value == "canonical"
    alias_only = resolve_provider_credential("DEEPSEEK", {"DEEPSEEK_API_KEY": "alias"})
    assert alias_only.variable == "DEEPSEEK_API_KEY"


def test_unreadable_key_file_is_an_error_not_a_fallback(tmp_path):
    missing = tmp_path / "absent.key"
    with pytest.raises(CredentialFileError):
        resolve_provider_credential(
            "GIE", {"GIE_API_KEY_FILE": str(missing)}, **_store(None, "db-key")
        )
    status = effective_credential_source("GIE", {"GIE_API_KEY_FILE": str(missing)}, **_store())
    assert status["effective_source"] == "missing"


def test_status_never_carries_the_key():
    status = effective_credential_source("EIA", {"EIA_API_KEY": "secret-value"}, **_store())
    assert status["effective_source"] == "env"
    assert "secret-value" not in repr(status)
    resolved = resolve_provider_credential("EIA", {"EIA_API_KEY": "secret-value"})
    assert "secret-value" not in repr(resolved)


def test_every_declared_variable_is_in_the_configuration_contract():
    from eurogas_nexus.core.config_contract import CONFIG_VARS

    declared = {var.name for var in CONFIG_VARS}
    for spec in PROVIDER_CREDENTIAL_SPECS:
        for variable in (*spec.env_vars, *([spec.file_env] if spec.file_env else [])):
            assert variable in declared, (spec.provider_id, variable)
