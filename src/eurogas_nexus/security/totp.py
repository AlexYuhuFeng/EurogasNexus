"""Time-based one-time passwords (RFC 6238, HMAC-SHA1, 30 s, 6 digits) with the standard library.

Security review H6: local accounts get a second factor without a new dependency
(docs/legal dependency rules): RFC 4226 HOTP and RFC 6238 TOTP are a few lines of ``hmac``.
Any authenticator app (Microsoft or Google Authenticator, FreeOTP, 1Password) reads the
``otpauth://`` URI.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
#: Accept the previous and next step too (clock drift of up to 30 s either way).
WINDOW = 1
RECOVERY_CODE_COUNT = 10


def new_secret() -> str:
    """A 160-bit secret, base32 without padding (what authenticator apps expect)."""

    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def hotp(secret: str, counter: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def verify(secret: str, code: str, *, last_step: int | None = None,
           now: float | None = None) -> int | None:
    """The time step ``code`` matches, or ``None``; a step at or before ``last_step`` is
    refused, so a code is used once."""

    candidate = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(candidate) != DIGITS:
        return None
    step = current_step(now)
    for offset in range(-WINDOW, WINDOW + 1):
        counter = step + offset
        if last_step is not None and counter <= last_step:
            continue
        if hmac.compare_digest(hotp(secret, counter), candidate):
            return counter
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "Eurogas Nexus") -> str:
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


def new_recovery_codes() -> list[str]:
    """Ten single-use codes of 10 base32 characters (50 bits), shown once."""

    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return [
        "".join(secrets.choice(alphabet) for _ in range(10)) for _ in range(RECOVERY_CODE_COUNT)
    ]


def hash_recovery_code(code: str) -> str:
    normalized = "".join(ch for ch in str(code or "").upper() if ch.isalnum())
    return hashlib.sha256(f"eurogas-nexus-recovery|{normalized}".encode()).hexdigest()
