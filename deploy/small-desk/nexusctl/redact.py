"""Remove every secret from text that leaves the PC (the diagnostics bundle).

Two layers, then a check:

1. **Known values.** Every secret the installation holds (``stack.env``) is replaced wherever
   it appears, in any form (as written, URL-encoded), so a password that turns up in an odd
   place (a log line, an error message) still goes.
2. **Shapes.** Whatever looks like a secret is replaced even when its value is unknown: a
   ``password=``/``token:``/``secret`` setting, a password inside a connection string, an
   ``Authorization`` header or bearer token, password hashes and salts, signed tokens (JWT),
   encrypted values (Fernet), private keys, one-time passwords, long random strings.
3. :meth:`Redactor.leaks` looks again at the finished text; the bundle is not written while
   anything is found (fail closed).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import quote, quote_plus

REMOVED = "<removed>"

_SECRET_WORDS = (
    r"password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|"
    r"passphrase|credential|cookie|authorization|salt|digest_b64|password_hash|session_id"
)
# NAME=value, NAME: value, "name": "value" (also JSON-escaped, \"name\": \"value\") where the
# name mentions a secret.
_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?P<name>\\?["']?[A-Za-z0-9_.\-]*(?:""" + _SECRET_WORDS + r""")[A-Za-z0-9_.\-]*\\?["']?)
    (?P<sep>\s*[=:]\s*)
    (?P<quote>\\?["']?)
    (?P<value>(?!<removed>)[^\s"',;}\]\\]+)
    """
)
# scheme://user:password@host
_URL_PASSWORD = re.compile(r"(?P<head>\b[a-z][a-z0-9+.\-]*://[^:/@\s]+:)(?P<value>[^@\s/]+)@")
_AUTH_HEADER = re.compile(r"(?i)\b(authorization\s*[:=]\s*)(?!<removed>)([^\r\n]+)")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+(?!<removed>)([A-Za-z0-9._~+/=\-]{8,})")
_PATTERNS = (
    # PEM private keys (any kind).
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    # Password hashes: modular crypt formats and the product's scrypt storage.
    re.compile(r"\$(?:scrypt|argon2(?:id|i|d)?|2[abxy]|pbkdf2[\w-]*|[156])\$[^\s\"']+"),
    re.compile(r"\b(?:scrypt|pbkdf2_sha256|argon2)[:$][A-Za-z0-9+/=$:.\-]{16,}"),
    # Signed tokens (JWT) and Fernet-encrypted values.
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"),
    re.compile(r"\bgAAAAA[A-Za-z0-9_\-]{40,}={0,2}"),
    # The product's one-time passwords (abcd-efgh-jkmn-pqrs).
    re.compile(r"\b[a-hj-km-np-z2-9]{4}(?:-[a-hj-km-np-z2-9]{4}){3}\b"),
)
# Long random-looking strings: letters and digits mixed, 32+ characters. Plain hexadecimal
# (image digests, checksums) is kept: it identifies versions and is not a secret here.
_LONG_TOKEN = re.compile(r"(?<![A-Za-z0-9_\-+/])[A-Za-z0-9_\-+/]{32,}={0,2}(?![A-Za-z0-9_\-+/])")


def _looks_random(candidate: str) -> bool:
    core = candidate.rstrip("=")
    if re.fullmatch(r"[0-9a-fA-F]+", core):
        return False
    if "/" in core and not re.search(r"[A-Z]", core):
        return False  # a path, not a key
    classes = sum(bool(re.search(pattern, core)) for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]"))
    return classes >= 3


class Redactor:
    def __init__(self, known_secrets: Iterable[str] = ()) -> None:
        values: set[str] = set()
        for secret in known_secrets:
            secret = (secret or "").strip()
            if len(secret) < 6:
                continue  # too short to replace safely; the shapes below still apply
            values.update({secret, quote(secret, safe=""), quote_plus(secret)})
        # Longest first, so a secret that contains another is removed whole.
        self.known = sorted(values, key=len, reverse=True)

    def redact(self, text: str) -> str:
        for secret in self.known:
            if secret in text:
                text = text.replace(secret, REMOVED)
        for pattern in _PATTERNS:
            text = pattern.sub(REMOVED, text)
        text = _URL_PASSWORD.sub(lambda m: m.group("head") + REMOVED + "@", text)
        text = _AUTH_HEADER.sub(lambda m: m.group(1) + REMOVED, text)
        text = _BEARER.sub(lambda m: m.group(1) + " " + REMOVED, text)
        text = _ASSIGNMENT.sub(
            lambda m: m.group("name") + m.group("sep") + m.group("quote") + REMOVED, text
        )
        text = _LONG_TOKEN.sub(
            lambda m: REMOVED if _looks_random(m.group(0)) else m.group(0), text
        )
        return text

    def leaks(self, text: str) -> list[str]:
        """What still looks secret in ``text`` (descriptions only, never the value)."""

        found: list[str] = []
        if any(secret in text for secret in self.known):
            found.append("a secret of this installation")
        checks = (
            ("a private key, hash, signed or encrypted value", _PATTERNS),
            ("a password in a connection string", (_URL_PASSWORD,)),
            ("an authorization header", (_AUTH_HEADER,)),
            ("a bearer token", (_BEARER,)),
            ("a secret setting", (_ASSIGNMENT,)),
        )
        for description, patterns in checks:
            for pattern in patterns:
                for match in pattern.finditer(text):
                    if REMOVED not in match.group(0) or pattern is _URL_PASSWORD and (
                        match.group("value") != REMOVED
                    ):
                        found.append(description)
                        break
        if any(_looks_random(m.group(0)) for m in _LONG_TOKEN.finditer(text)):
            found.append("a long random string")
        return sorted(set(found))
