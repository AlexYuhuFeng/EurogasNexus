"""Shared GIE credential-status resolver tests.

The resolver is the single source of truth for both the runtime fetch and every
reported status surface, so these tests pin the precedence, the operator-disabled
guarantee and the secret-safety of the reported shape. No credential value, no
fragment of one and no filesystem path may appear in the status object.
"""

from __future__ import annotations

from eurogas_nexus.ingestion.gie_transport import (
    GIE_API_KEY_ENV,
    GIE_API_KEY_FILE_ENV,
    GieCredentialStatus,
    resolve_gie_credential_status,
)

_SECRET = "gie-owner-secret-value-1234567890"


def test_missing_credential_reports_no_secret_and_no_path() -> None:
    status = resolve_gie_credential_status(environ={})

    assert status == GieCredentialStatus(
        configured=False,
        source_kind="missing",
        blocked=False,
        diagnostics=("credential_missing",),
        support_flags=("connection_test", "agsi", "alsi"),
    )
    assert _SECRET not in repr(status)


def test_environment_key_is_reported_configured_without_the_value() -> None:
    status = resolve_gie_credential_status(environ={GIE_API_KEY_ENV: _SECRET})

    assert status.configured is True
    assert status.source_kind == "env"
    assert status.blocked is False
    assert status.diagnostics == ()
    assert _SECRET not in repr(status)


def test_external_key_file_is_reported_configured_without_its_path(tmp_path) -> None:
    key_file = tmp_path / "gie-api-key.txt"
    key_file.write_text(_SECRET + "\n", encoding="utf-8")

    status = resolve_gie_credential_status(environ={GIE_API_KEY_FILE_ENV: str(key_file)})

    assert status.configured is True
    assert status.source_kind == "file"
    assert status.blocked is False
    # The external owner path is never part of the reported status.
    assert str(key_file) not in repr(status)
    assert str(tmp_path) not in repr(status)
    assert _SECRET not in repr(status)


def test_unreadable_key_file_is_a_stable_diagnostic_code_not_a_path() -> None:
    missing = "Z:/definitely/absent/gie-key.txt"

    status = resolve_gie_credential_status(environ={GIE_API_KEY_FILE_ENV: missing})

    assert status.configured is False
    assert status.source_kind == "file_unreadable"
    assert status.blocked is True
    assert status.diagnostics == ("gie_key_file_unreadable",)
    assert missing not in repr(status)


def test_stored_credential_is_reported_configured() -> None:
    status = resolve_gie_credential_status(
        environ={},
        credential_lookup=lambda: _SECRET,
        stored_credential_status=lambda: "configured",
    )

    assert status.configured is True
    assert status.source_kind == "credential_store"
    assert status.blocked is False
    assert _SECRET not in repr(status)


def test_operator_disabled_stored_credential_is_not_reenabled_by_env_or_file(
    tmp_path,
) -> None:
    """A disabled stored credential stays blocked -- external config cannot revive it."""

    status = resolve_gie_credential_status(
        environ={},
        credential_lookup=lambda: _SECRET,
        stored_credential_status=lambda: "disabled",
    )

    assert status.configured is False
    assert status.source_kind == "operator_disabled"
    assert status.blocked is True
    assert status.operator_disabled is True
    assert status.diagnostics == ("credential_disabled",)


def test_disabled_source_operation_blocks_any_credential_source() -> None:
    status = resolve_gie_credential_status(
        environ={GIE_API_KEY_ENV: _SECRET},
        credential_lookup=lambda: _SECRET,
        stored_credential_status=lambda: "configured",
        source_operation_enabled=lambda: False,
    )

    assert status.configured is False
    assert status.blocked is True
    assert status.source_kind == "operator_disabled"
    assert status.diagnostics == ("source_operation_disabled",)


def test_external_env_takes_documented_precedence_over_a_stored_credential() -> None:
    """The env path is operator-controlled and keeps its documented precedence."""

    status = resolve_gie_credential_status(
        environ={GIE_API_KEY_ENV: _SECRET},
        credential_lookup=lambda: "stored-other-value",
        stored_credential_status=lambda: "configured",
    )

    assert status.configured is True
    assert status.source_kind == "env"
    assert status.blocked is False


def test_a_raising_credential_lookup_never_breaks_the_status_probe() -> None:
    def exploding_lookup() -> str | None:
        raise RuntimeError("store unavailable")

    status = resolve_gie_credential_status(
        environ={}, credential_lookup=exploding_lookup
    )

    assert status.configured is False
    assert status.source_kind == "missing"


def test_an_absent_stored_status_is_no_override_and_keeps_env_configured() -> None:
    """A missing state row means "no override", not "unreadable"."""

    status = resolve_gie_credential_status(
        environ={GIE_API_KEY_ENV: _SECRET},
        credential_lookup=lambda: _SECRET,
        stored_credential_status=lambda: None,
        source_operation_enabled=lambda: None,
    )

    assert status.configured is True
    assert status.source_kind == "env"
    assert status.blocked is False
    assert status.diagnostics == ()


def test_an_unreadable_stored_status_is_not_a_confirmed_permit() -> None:
    """A failed operator-state read must fail closed, never permit the credential."""

    def exploding_status() -> str | None:
        raise RuntimeError("credential store unavailable")

    status = resolve_gie_credential_status(
        environ={GIE_API_KEY_ENV: _SECRET},
        stored_credential_status=exploding_status,
    )

    assert status.configured is False
    assert status.blocked is True
    assert status.source_kind == "state_unreadable"
    assert status.diagnostics == ("credential_state_unreadable",)
    assert _SECRET not in repr(status)


def test_an_unreadable_source_operation_state_is_not_a_confirmed_permit() -> None:
    def exploding_state() -> bool | None:
        raise RuntimeError("runtime state unavailable")

    status = resolve_gie_credential_status(
        environ={GIE_API_KEY_ENV: _SECRET},
        stored_credential_status=lambda: "configured",
        source_operation_enabled=exploding_state,
    )

    assert status.configured is False
    assert status.blocked is True
    assert status.source_kind == "state_unreadable"
    assert status.diagnostics == ("source_operation_state_unreadable",)
    assert status.operator_disabled is False
