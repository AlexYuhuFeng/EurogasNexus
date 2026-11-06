"""One credential contract for every credential-bearing provider (#38).

Each provider names the environment variables that may carry its key and whether a
connector is implemented. Resolution is the same for every provider and for every
caller (ingestion, the LLM layer, the credentials API):

1. A stored credential an administrator **disabled** blocks the provider. An
   environment key never silently re-enables it.
2. The provider's environment variables, in the order listed (the first is canonical,
   later ones are accepted aliases). A blank value counts as unset.
3. A key file named by ``<VAR>_FILE`` where the provider supports one. A configured
   file that cannot be read is an error, never a silent fall-through.
4. The encrypted credential store.

Configuration is not activation: a resolved key does not enable a source, schedule an
ingestion, permit external LLM calls or grant a market-data licence. Values are never
logged or returned to the browser; status reports only the source kind.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from eurogas_nexus.domain.connectors.manifest import ProviderCredentialSpec

CredentialSource = Literal["env", "file", "credential_store"]
EffectiveSource = Literal["env", "file", "credential_store", "disabled", "missing"]


def _declared_specs() -> tuple[ProviderCredentialSpec, ...]:
    """Every credential the connector manifests declare (C1), implemented ones first.

    ``implemented=False`` means a key may be stored for a future connector but nothing reads
    it yet; declaring it does not make a connector work or grant an entitlement.
    """

    from eurogas_nexus.domain.connectors.registry import connector_manifests

    specs = [spec for manifest in connector_manifests() for spec in manifest.credentials]
    return tuple(
        [spec for spec in specs if spec.implemented]
        + [spec for spec in specs if not spec.implemented]
    )


#: Every provider the credential manager knows, derived from the connector manifests.
PROVIDER_CREDENTIAL_SPECS: tuple[ProviderCredentialSpec, ...] = _declared_specs()

_SPECS = {spec.provider_id: spec for spec in PROVIDER_CREDENTIAL_SPECS}

#: Every environment variable a provider credential may come from, read in one place.
PROVIDER_CREDENTIAL_ENV_VARS = (
    "GIE_API_KEY",
    "GIE_API_KEY_FILE",
    "EIA_API_KEY",
    "ENTSOE_SECURITY_TOKEN",
    "EUROGAS_NEXUS_LLM_API_KEY",
    "DEEPSEEK_API_KEY",
)


def _credential_environment(environ: Mapping[str, str] | None) -> dict[str, str]:
    """The non-blank provider credential variables, from ``os.environ`` unless given."""

    env = os.environ if environ is None else environ
    values: dict[str, str] = {}
    for name in PROVIDER_CREDENTIAL_ENV_VARS:
        value = str(env.get(name) or "").strip()
        if value:
            values[name] = value
    return values


class CredentialFileError(RuntimeError):
    """A key file is configured but cannot be read as a non-empty key."""


@dataclass(frozen=True)
class ResolvedCredential:
    value: str
    source: CredentialSource
    variable: str | None = None

    def __repr__(self) -> str:  # never print the key
        return f"ResolvedCredential(source={self.source!r}, variable={self.variable!r})"


def provider_spec(provider_id: str) -> ProviderCredentialSpec | None:
    return _SPECS.get(provider_id)


def _from_environment(
    spec: ProviderCredentialSpec, env: Mapping[str, str]
) -> ResolvedCredential | None:
    for variable in spec.env_vars:
        value = env.get(variable)
        if value:
            return ResolvedCredential(value=value, source="env", variable=variable)
    if spec.file_env:
        path = env.get(spec.file_env)
        if path:
            try:
                value = Path(path).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise CredentialFileError(f"{spec.file_env} cannot be read") from exc
            if not value:
                raise CredentialFileError(f"{spec.file_env} is empty")
            return ResolvedCredential(value=value, source="file", variable=spec.file_env)
    return None


def resolve_provider_credential(
    provider_id: str,
    environ: Mapping[str, str] | None = None,
    *,
    stored_status: Callable[[], str | None] | None = None,
    stored_value: Callable[[], str | None] | None = None,
) -> ResolvedCredential | None:
    """The key a backend call for ``provider_id`` should use, or ``None``.

    ``stored_status`` returns the stored credential's status (``disabled`` blocks) or
    ``None`` when absent; ``stored_value`` returns the decrypted stored key. Both default
    to the runtime credential store when ``environ`` is the process environment.
    """

    spec = _SPECS.get(provider_id)
    env = _credential_environment(environ)
    if environ is None:
        stored_status = stored_status or (lambda: _stored_field(provider_id, "status"))
        stored_value = stored_value or (lambda: _stored_field(provider_id, "api_key"))
    if stored_status is not None and stored_status() == "disabled":
        return None
    if spec is not None:
        resolved = _from_environment(spec, env)
        if resolved is not None:
            return resolved
    if stored_value is not None:
        value = str(stored_value() or "").strip()
        if value:
            return ResolvedCredential(value=value, source="credential_store")
    return None


def effective_credential_source(
    provider_id: str,
    environ: Mapping[str, str] | None = None,
    *,
    stored_status: Callable[[], str | None] | None = None,
    stored_value: Callable[[], str | None] | None = None,
) -> dict[str, object]:
    """Secret-free status: where the key a call would use comes from, and how to change it."""

    spec = _SPECS.get(provider_id)
    env_vars = list(spec.env_vars) if spec else []
    if spec and spec.file_env:
        env_vars.append(spec.file_env)
    status: dict[str, object] = {
        "credential_env_vars": env_vars,
        "connector_implemented": bool(spec.implemented) if spec else False,
        "credential_note": spec.note if spec else "",
    }
    try:
        resolved = resolve_provider_credential(
            provider_id, environ, stored_status=stored_status, stored_value=stored_value
        )
    except CredentialFileError as exc:
        return status | {"effective_source": "missing", "effective_source_error": str(exc)}
    if resolved is None:
        env = _credential_environment(environ)
        disabled = (stored_status or (lambda: _stored_field(provider_id, "status")))() == "disabled"
        status["effective_source"] = "disabled" if disabled else "missing"
        if disabled and spec and any(var in env for var in spec.env_vars):
            status["effective_source_detail"] = (
                "An environment key is set but the administrator disabled this provider."
            )
        return status
    return status | {"effective_source": resolved.source, "effective_variable": resolved.variable}


def _stored_field(provider_id: str, field: str) -> str | None:
    """Read one field of the stored credential; ``None`` when absent or unreadable."""

    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        return None
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.security.credentials import decrypt_credential_payload

        with get_session_factory()() as session:
            row = session.get(ProviderCredentialRecord, provider_id)
            if row is None:
                return None
            if field == "status":
                return str(row.status or "")
            payload = decrypt_credential_payload(row.encrypted_payload)
            return str(payload.get(field) or "").strip() or None
    except Exception:
        return None
