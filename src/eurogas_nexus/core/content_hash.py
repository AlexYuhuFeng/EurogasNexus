"""Deterministic content hashes for research and audit records.

A hash here is an audit and reproducibility identifier, not a security
signature. Canonical JSON (sorted keys, no whitespace, UTF-8) makes the same
semantic value hash the same way across processes and releases.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_content_hash(value: Any) -> str:
    """Return a deterministic SHA-256 hash over canonical semantic JSON.

    Args:
        value: Any JSON-serializable value; non-JSON scalars use ``str``.

    Returns:
        ``sha256:<hex digest>``.
    """

    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
