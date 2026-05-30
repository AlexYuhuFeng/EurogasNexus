"""Credential encryption and redaction helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet

SECRET_KEY_ENV = "EUROGAS_NEXUS_SECRET_KEY"


@dataclass(frozen=True)
class CredentialEnvelope:
    encrypted_payload: str
    redacted_preview: str
    credential_fingerprint: str


def credential_store_configured() -> bool:
    """Return true when backend credential encryption is configured."""

    return bool(os.environ.get(SECRET_KEY_ENV, "").strip())


def encrypt_credential_payload(payload: dict[str, str]) -> CredentialEnvelope:
    """Encrypt a provider credential payload for DB storage."""

    secret = _secret_key()
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    api_key = payload.get("api_key") or payload.get("token") or ""
    return CredentialEnvelope(
        encrypted_payload=Fernet(secret).encrypt(plaintext).decode("ascii"),
        redacted_preview=redact_secret_value(api_key),
        credential_fingerprint=fingerprint_secret_value(api_key),
    )


def decrypt_credential_payload(encrypted_payload: str) -> dict[str, Any]:
    """Decrypt a provider credential payload for live connector use."""

    plaintext = Fernet(_secret_key()).decrypt(encrypted_payload.encode("ascii"))
    value = json.loads(plaintext.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Credential payload is not an object.")
    return value


def redact_secret_value(value: str) -> str:
    """Return a stable preview without exposing the full secret."""

    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def fingerprint_secret_value(value: str) -> str:
    """Return a non-reversible credential fingerprint."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def _secret_key() -> bytes:
    raw = os.environ.get(SECRET_KEY_ENV, "").strip()
    if not raw:
        raise ValueError("Credential encryption key is not configured.")
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
        if len(decoded) == 32:
            return raw.encode("ascii")
    except Exception:
        pass
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)
