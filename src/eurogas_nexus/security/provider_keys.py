"""Runtime-only provider key retrieval (see ``provider_credentials`` for the contract)."""

from __future__ import annotations


def load_provider_api_key(provider_id: str) -> str | None:
    """Return the key a backend call should use, without logging it.

    The provider's environment variables, then its key file, then the encrypted store;
    a credential an administrator disabled is never used.
    """

    from eurogas_nexus.security.provider_credentials import (
        CredentialFileError,
        resolve_provider_credential,
    )

    try:
        resolved = resolve_provider_credential(provider_id)
    except CredentialFileError:
        return None
    return resolved.value if resolved else None
