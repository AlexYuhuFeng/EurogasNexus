"""Explicit ENTSOG operational point-direction scope; no defaults or fetching.

The scope is caller-declared provider identity. Nothing here enables a source,
infers a point, or establishes coverage. An empty scope preserves the existing
unscoped query behaviour and is not evidence of complete coverage.
"""

from __future__ import annotations

ENTSOG_POINT_DIRECTION_MAX_COUNT = 64
ENTSOG_POINT_DIRECTION_MAX_CHARS = 8192
_ENTSOG_POINT_DIRECTION_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz0123456789._-"
)


def validate_entsog_point_directions(values) -> tuple[str, ...]:
    """Return the explicit, canonical ENTSOG operational point scope.

    Values are caller-declared provider identities; nothing is inferred or
    defaulted. A value may contain a comma-separated composite. Canonicalisation
    lowercases, strips, deduplicates and sorts so the same declaration always
    produces the same query. Validation happens before database/HTTP side
    effects in ``main``.
    """

    if values is None:
        return ()
    if isinstance(values, str):
        raw_values = (values,)
    else:
        raw_values = tuple(values)
    if not raw_values:
        return ()
    if not all(isinstance(value, str) for value in raw_values):
        raise ValueError("point directions must be text values")
    if sum(len(value) for value in raw_values) > ENTSOG_POINT_DIRECTION_MAX_CHARS:
        raise ValueError(
            f"point directions exceed {ENTSOG_POINT_DIRECTION_MAX_CHARS} characters"
        )
    tokens: list[str] = []
    for value in raw_values:
        if not value.isascii():
            raise ValueError("point directions must be ASCII")
        for part in value.split(","):
            token = part.strip().lower()
            if not token:
                raise ValueError("point directions must not be blank")
            if token.endswith("entry"):
                suffix = "entry"
            elif token.endswith("exit"):
                suffix = "exit"
            else:
                raise ValueError(
                    f"point direction {token!r} must end with 'entry' or 'exit'"
                )
            prefix = token[: -len(suffix)]
            if not prefix or not prefix[0].isalnum():
                raise ValueError(
                    f"point direction {token!r} has no provider identity prefix"
                )
            if "www." in token or "://" in token:
                raise ValueError(f"point direction {token!r} must not be a URL")
            if any(char not in _ENTSOG_POINT_DIRECTION_CHARS for char in token):
                raise ValueError(
                    f"point direction {token!r} contains a control or unsupported character"
                )
            tokens.append(token)
    canonical = tuple(sorted(set(tokens)))
    if len(canonical) > ENTSOG_POINT_DIRECTION_MAX_COUNT:
        raise ValueError(
            f"at most {ENTSOG_POINT_DIRECTION_MAX_COUNT} point directions are allowed"
        )
    if len(",".join(canonical)) > ENTSOG_POINT_DIRECTION_MAX_CHARS:
        raise ValueError(
            f"point directions exceed {ENTSOG_POINT_DIRECTION_MAX_CHARS} characters"
        )
    return canonical
