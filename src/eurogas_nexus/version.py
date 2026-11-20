"""Canonical application version synchronized from ``pyproject.toml``.

``pyproject.toml`` is the canonical project version, in PEP 440 (``1.0.0b1``
for a beta). This module is the runtime-visible copy so backend code never
parses packaging metadata or the repository at import time:
``APPLICATION_VERSION`` is the SemVer spelling (``1.0.0-beta.1``) that release
metadata and client/server compatibility compare, ``APPLICATION_DISPLAY_VERSION``
the spelling people read (``1.0.0-beta``).
`scripts/release/check_version_consistency.py` fails the build when either
diverges from pyproject or any other version-bearing surface.
"""

APPLICATION_VERSION = "1.0.0-beta.1"
APPLICATION_DISPLAY_VERSION = "1.0.0-beta"
DEFAULT_RELEASE_CHANNEL = "preview"

__all__ = ["APPLICATION_DISPLAY_VERSION", "APPLICATION_VERSION", "DEFAULT_RELEASE_CHANNEL"]
