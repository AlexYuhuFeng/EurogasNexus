"""Whether dual control may be switched off (security review H7), without the API layer.

The start-up refusal lives here so the deployment preflight (``core/preflight.py``) and the
API (``api/dual_control.py``, which re-exports it) apply the same rule.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

DUAL_CONTROL_ENV = "EUROGAS_NEXUS_DUAL_CONTROL"
PRODUCTION = frozenset({"trial", "release"})


def _environment(environ: Mapping[str, str] | None = None) -> str:
    from eurogas_nexus.core.config import runtime_environment

    return runtime_environment(environ)


def assert_dual_control_setting_allowed(environ: Mapping[str, str] | None = None) -> None:
    """Refuse ``EUROGAS_NEXUS_DUAL_CONTROL=off`` in trial and release."""

    env = os.environ if environ is None else environ
    raw = (env.get(DUAL_CONTROL_ENV) or "").strip().lower()
    if raw in {"off", "false", "0", "no"} and _environment(env) in PRODUCTION:
        raise RuntimeError(
            f"{DUAL_CONTROL_ENV}=off is refused in a {_environment(env)!r} environment: "
            "security-relevant changes need a second administrator; use break-glass for an "
            "emergency"
        )
