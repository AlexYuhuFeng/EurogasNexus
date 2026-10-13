"""Runtime credential-boundary enforcement for the GIE ingestor (REAL-SOURCES-02 review).

The reported credential status and the *actual* fetch boundary must agree. These
tests exercise ``scripts/ops/ingest_public_sources.py::_resolve_gie_api_key``
with a stub session factory (no database, no fake stored credential, no
decryption) and pin that an operator-disabled stored credential or an explicitly
disabled source runtime operation is refused **before** any key is resolved --
including when ``GIE_API_KEY``/``GIE_API_KEY_FILE`` would otherwise take
precedence. An absent state row is no override; an unreadable one fails closed
with its own code.

Failure codes are stable and secret-safe: no key value, no key-file path and no
provider payload ever appears in the raised error.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from eurogas_nexus.ingestion import gie_transport as gt

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "ingest_public_sources.py"
)
SECRET = "ingest-gate-secret-value-1234567890"


def _load_script():
    spec = importlib.util.spec_from_file_location("ingest_public_sources", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeSession:
    """Minimal session double: no database, no credential row is ever written."""

    def __init__(self, *, credential_row, runtime_row) -> None:
        self._credential_row = credential_row
        self._runtime_row = runtime_row

    def get(self, model, key):  # noqa: ANN001 - stub
        return self._credential_row

    def query(self, model):  # noqa: ANN001 - stub
        return self

    def filter(self, *args, **kwargs):  # noqa: ANN002, ANN003 - stub
        return self

    def one_or_none(self):
        return self._runtime_row

    def __enter__(self):
        return self

    def __exit__(self, *exc):  # noqa: ANN002 - stub
        return False


def _factory(*, credential_row=None, runtime_row=None):
    return lambda: _FakeSession(credential_row=credential_row, runtime_row=runtime_row)


def _raising_factory():
    def factory():
        raise RuntimeError("operator state store unavailable")

    return factory


def test_refuses_operator_disabled_stored_credential_with_env_key(monkeypatch) -> None:
    script = _load_script()
    monkeypatch.setenv(gt.GIE_API_KEY_ENV, SECRET)

    with pytest.raises(gt.GieCredentialDisabledError) as refusal:
        script._resolve_gie_api_key(
            _factory(credential_row=SimpleNamespace(status="disabled"))
        )

    assert refusal.value.code == "gie_credential_disabled"
    assert SECRET not in repr(refusal.value)
    assert SECRET not in str(refusal.value)


def test_refuses_operator_disabled_stored_credential_with_key_file(
    tmp_path, monkeypatch
) -> None:
    script = _load_script()
    key_file = tmp_path / "gie-api-key.txt"
    key_file.write_text(SECRET + "\n", encoding="utf-8")
    monkeypatch.delenv(gt.GIE_API_KEY_ENV, raising=False)
    monkeypatch.setenv(gt.GIE_API_KEY_FILE_ENV, str(key_file))

    with pytest.raises(gt.GieCredentialDisabledError) as refusal:
        script._resolve_gie_api_key(
            _factory(credential_row=SimpleNamespace(status="disabled"))
        )

    assert refusal.value.code == "gie_credential_disabled"
    assert str(key_file) not in repr(refusal.value)
    assert SECRET not in repr(refusal.value)


def test_refuses_operator_disabled_stored_credential_with_no_external_key(
    monkeypatch,
) -> None:
    script = _load_script()
    monkeypatch.delenv(gt.GIE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(gt.GIE_API_KEY_FILE_ENV, raising=False)

    with pytest.raises(gt.GieCredentialDisabledError) as refusal:
        script._resolve_gie_api_key(
            _factory(credential_row=SimpleNamespace(status="disabled"))
        )

    # A disabled credential is deliberately not reported as merely missing.
    assert refusal.value.code == "gie_credential_disabled"


def test_refuses_explicitly_disabled_source_operation_even_with_env_key(
    monkeypatch,
) -> None:
    script = _load_script()
    monkeypatch.setenv(gt.GIE_API_KEY_ENV, SECRET)

    with pytest.raises(gt.GieSourceDisabledError) as refusal:
        script._resolve_gie_api_key(
            _factory(credential_row=None, runtime_row=SimpleNamespace(enabled=False))
        )

    assert refusal.value.code == "gie_source_disabled"
    assert SECRET not in repr(refusal.value)


def test_unreadable_operator_state_fails_closed(monkeypatch) -> None:
    script = _load_script()
    monkeypatch.setenv(gt.GIE_API_KEY_ENV, SECRET)

    with pytest.raises(gt.GieCredentialStateUnreadableError) as refusal:
        script._resolve_gie_api_key(_raising_factory())

    # An unknown state is never a confirmed permit; the code stays distinct from
    # an explicit operator disable.
    assert refusal.value.code == "gie_credential_state_unreadable"


def test_ordinary_external_key_with_no_stored_override_remains_usable(
    monkeypatch,
) -> None:
    script = _load_script()
    monkeypatch.setenv(gt.GIE_API_KEY_ENV, SECRET)

    resolved = script._resolve_gie_api_key(
        _factory(credential_row=None, runtime_row=None)
    )

    assert resolved is not None
    assert resolved.source == "env"
    assert resolved.value == SECRET

    # The resolved key is what the bounded connection test consumes; prove the
    # whole path is still usable end to end through a mock transport.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "agsi.gie.eu":
            records = [
                {
                    "name": "EU",
                    "code": "EU",
                    "gasDayStart": "2026-10-09",
                    "gasDayEnd": "2026-10-10",
                    "gasInStorage": "650.25",
                    "workingGasVolume": "1100.50",
                }
            ]
        else:
            records = [
                {
                    "name": "EU LNG",
                    "code": "EU",
                    "gasDayStart": "2026-10-09",
                    "gasDayEnd": "2026-10-10",
                    "inventory": {"gwh": "42.5"},
                    "sendOut": "3.4",
                    "dtmi": {"gwh": "65.0"},
                }
            ]
        return httpx.Response(
            200,
            json={
                "data": records,
                "last_page": 1,
                "total": len(records),
                "dataset": "EU",
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    try:
        checks = gt.test_gie_connection(client, api_key=resolved.value or "")
    finally:
        client.close()

    assert [check.product for check in checks] == ["AGSI", "ALSI"]
    assert all(check.ok for check in checks)
