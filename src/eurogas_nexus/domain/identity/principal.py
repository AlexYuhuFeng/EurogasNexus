"""Minimal actor identity model.

Eurogas Nexus is a single-trust-domain decision-support product in preview:
there is no user directory, no company SSO/OIDC, and no per-user authorization
(those remain explicitly out of scope until R32). What exists today is an
*actor principal*: a stable operator identifier recorded on review decisions,
audit events, and internal operator writes so the trust chain can answer
"who did this" per row.

This module is the single validator for that identifier so every surface
(review API, internal API, ingestion scripts, audit records) applies the same
rules. Rules:

- required, trimmed, 1-64 characters;
- starts with a letter or digit;
- contains only letters, digits, and ``. _ @ -``;
- control characters, whitespace inside, and empty values are rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PRINCIPAL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}")
MAX_LENGTH = 64


@dataclass(frozen=True)
class PrincipalValidationError(ValueError):
    """Raised when an actor principal does not satisfy the identity rules."""

    reason: str

    def __str__(self) -> str:
        return f"invalid principal: {self.reason}"


def normalize_principal(value: str | None) -> str:
    """Validate and return the canonical (trimmed) actor principal.

    校验并规范化操作者主体标识（review 决策、审计事件、内部写入共用）。

    Args:
        value: Raw principal value; None and whitespace-only are rejected.

    Returns:
        The trimmed canonical principal.

    Raises:
        PrincipalValidationError: When the value is empty, too long, or
            contains characters outside ``[A-Za-z0-9._@-]`` (with a
            letter/digit first character).
    """

    candidate = (value or "").strip()
    if not candidate:
        raise PrincipalValidationError("principal is required")
    if len(candidate) > MAX_LENGTH:
        raise PrincipalValidationError(f"principal longer than {MAX_LENGTH} characters")
    if not PRINCIPAL_PATTERN.fullmatch(candidate):
        # 规则与模块 docstring 同步：首字符字母/数字，仅允许白名单符号。
        raise PrincipalValidationError(
            "principal must start with a letter/digit and contain only "
            "letters, digits, '.', '_', '@', '-'"
        )
    return candidate
