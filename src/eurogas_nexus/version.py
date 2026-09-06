"""Canonical application version synchronized from ``pyproject.toml``.

``pyproject.toml`` is the canonical project version. This module is the
runtime-visible copy so backend code never parses packaging metadata or the
repository at import time. `scripts/release/check_version_consistency.py`
fails the build when this value diverges from pyproject or any other
version-bearing surface.
"""

APPLICATION_VERSION = "0.5.0"
DEFAULT_RELEASE_CHANNEL = "preview"

__all__ = ["APPLICATION_VERSION", "DEFAULT_RELEASE_CHANNEL"]
