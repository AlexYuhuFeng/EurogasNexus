"""Local-account password storage and policy (no third-party dependency).

Storage
-------
Passwords are stored as a memory-hard key derivation with the standard library's
``hashlib.scrypt`` (RFC 7914): a 16-byte random salt per user and a 32-byte derived key.
The KDF name and its parameters (``n``, ``r``, ``p``, ``dklen``) are stored beside the
digest, so stronger parameters can be introduced later and an older hash is upgraded at
the next successful sign-in (:func:`needs_rehash`). Nothing stored is reversible: the
plaintext is never written, logged or audited.

The text is normalised to Unicode NFKC before hashing, so the same password typed on two
keyboards (composed or decomposed accents, full-width digits) verifies the same way.

Policy (NIST SP 800-63B style)
------------------------------
At least 12 characters and at most 128; not the user name (or containing it); not one of
a small list of trivially common passwords and not one character repeated. No composition
rules (no "one capital, one digit"): length is what makes a password strong, and
composition rules push people towards predictable patterns.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import unicodedata
from dataclasses import dataclass

KDF_NAME = "scrypt"
#: Current parameters: n=2^15, r=8 -> 32 MiB of memory per derivation (~0.1 s on a server).
DEFAULT_KDF_PARAMS: dict[str, int] = {"n": 2**15, "r": 8, "p": 1, "dklen": 32}
SALT_BYTES = 16
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

#: Trivially common passwords long enough to pass the length rule (compared case-insensitively).
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "123456789012",
        "1234567890123",
        "12345678901234",
        "123456123456",
        "111111111111",
        "000000000000",
        "121212121212",
        "123123123123",
        "abc123456789",
        "abcdefghijkl",
        "abcd1234abcd",
        "1q2w3e4r5t6y",
        "1qaz2wsx3edc",
        "qwertyuiopas",
        "qwerty123456",
        "qwertyqwerty",
        "asdfghjkl123",
        "zxcvbnm12345",
        "password1234",
        "password123!",
        "password12345",
        "passwordpassword",
        "p@ssw0rd1234",
        "p@ssword1234",
        "letmein12345",
        "welcome12345",
        "welcome123456",
        "changeme1234",
        "changeme123!",
        "iloveyou1234",
        "administrator",
        "admin1234567",
        "adminadmin12",
        "trustno11234",
        "football1234",
        "baseball1234",
        "sunshine1234",
        "princess1234",
        "superman1234",
        "starwars1234",
        "dragon123456",
        "monkey123456",
        "master123456",
        "eurogasnexus",
        "eurogasnexus1",
        "eurogas12345",
        "nexus1234567",
    }
)


class PasswordPolicyError(ValueError):
    """A proposed password breaks the policy; ``code`` is a stable machine reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PasswordHash:
    """One stored derivation: KDF name, its parameters, salt and digest (base64)."""

    kdf: str
    params: dict[str, int]
    salt_b64: str
    digest_b64: str


def normalize_password(password: str) -> str:
    """NFKC form of the password (what is measured and hashed)."""

    return unicodedata.normalize("NFKC", password or "")


def check_password_policy(password: str, *, username: str | None = None) -> None:
    """Raise :class:`PasswordPolicyError` unless the password meets the policy."""

    text = normalize_password(password)
    if len(text) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            "password_too_short",
            f"Use at least {MIN_PASSWORD_LENGTH} characters; a short phrase works well.",
        )
    if len(text) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            "password_too_long", f"Use at most {MAX_PASSWORD_LENGTH} characters."
        )
    folded = text.casefold()
    name = (username or "").strip().casefold()
    if name and (folded == name or (len(name) >= 3 and name in folded)):
        raise PasswordPolicyError(
            "password_contains_username", "The password must not contain the user name."
        )
    if folded in COMMON_PASSWORDS or len(set(folded)) == 1:
        raise PasswordPolicyError(
            "password_too_common", "This password is too common; choose another one."
        )


def _derive(password: str, salt: bytes, params: dict[str, int]) -> bytes:
    n, r, p, dklen = int(params["n"]), int(params["r"]), int(params["p"]), int(params["dklen"])
    return hashlib.scrypt(
        normalize_password(password).encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=dklen,
        # scrypt needs 128 * n * r bytes; leave headroom so OpenSSL never refuses.
        maxmem=256 * n * r * p + 1024 * 1024,
    )


def hash_password(password: str, *, params: dict[str, int] | None = None) -> PasswordHash:
    """Derive a fresh salted hash with the current (or given) parameters."""

    chosen = dict(params or DEFAULT_KDF_PARAMS)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, chosen)
    return PasswordHash(
        kdf=KDF_NAME,
        params=chosen,
        salt_b64=base64.b64encode(salt).decode("ascii"),
        digest_b64=base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: PasswordHash) -> bool:
    """Constant-time comparison of a candidate against a stored derivation."""

    if stored.kdf != KDF_NAME:
        return False
    try:
        salt = base64.b64decode(stored.salt_b64)
        expected = base64.b64decode(stored.digest_b64)
        candidate = _derive(password, salt, stored.params)
    except (ValueError, KeyError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


_DUMMY: PasswordHash | None = None


def burn_verification_time(password: str) -> None:
    """Spend the same work as a real verification (unknown user, no credential).

    A sign-in for a name that has no local password must take as long as a wrong
    password, so the response time does not tell which user names exist.
    """

    global _DUMMY
    if _DUMMY is None or _DUMMY.params != DEFAULT_KDF_PARAMS:
        _DUMMY = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _DUMMY)


def needs_rehash(stored: PasswordHash) -> bool:
    """Whether a stored hash uses other than the current KDF parameters."""

    return stored.kdf != KDF_NAME or dict(stored.params) != DEFAULT_KDF_PARAMS


#: Letters and digits that cannot be confused when read aloud or copied (no 0/o, 1/l/i).
_SECRET_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def generate_one_time_secret() -> str:
    """A one-time temporary password: four groups of four (``abcd-efgh-...``), ~79 bits."""

    groups = ["".join(secrets.choice(_SECRET_ALPHABET) for _ in range(4)) for _ in range(4)]
    return "-".join(groups)


def generate_token() -> str:
    """An opaque single-use token (password-change step); stored only as SHA-256."""

    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
