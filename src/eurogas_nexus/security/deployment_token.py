"""What the static deployment API token may do (security review H3).

The deployment token (``EUROGAS_NEXUS_PUBLIC_API_TOKEN``) identifies a deployment, not a person.
It used to resolve to an OPERATOR with the ``*`` scope over every book and licensed dataset, and
an OPERATOR route accepted any ``X-Eurogas-Principal`` name as the actor, so a holder of a leaked
``.env`` file read everything and acted under someone else's name.

Two modes, chosen by ``EUROGAS_NEXUS_PUBLIC_API_TOKEN_MODE``:

``service`` (the default in trial and release)
    The token is a **service principal** (``service:public-api``) with a configured role
    (``EUROGAS_NEXUS_PUBLIC_API_TOKEN_ROLE``, default VIEWER, never ADMIN) and configured data
    scopes (``EUROGAS_NEXUS_PUBLIC_API_TOKEN_SCOPES``, default none: public sources only, no
    book). ``X-Eurogas-Principal`` is ignored: every act is attributed to the service principal.
    People and scripts that act as a person use personal API keys (``/api/me/api-keys``).

``legacy_operator`` (deprecated; the default in development and test only)
    The old compatibility caller: OPERATOR, ``*``. An OPERATOR route still needs
    ``X-Eurogas-Principal``, but the act is recorded as ``public-api@<claimed name>`` so the
    audit trail says the name was claimed by a token holder, not verified. In trial and release
    it must be chosen explicitly, and the start-up log warns on every start.

Rotation: set the new value in ``EUROGAS_NEXUS_PUBLIC_API_TOKEN`` and the old one in
``EUROGAS_NEXUS_PUBLIC_API_TOKEN_PREVIOUS``, restart, move every client to the new value, then
clear the previous one and restart again (docs/security/DEPLOYMENT_TOKEN.md).

The token is never accepted in a URL: query strings reach access logs.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

MODE_ENV = "EUROGAS_NEXUS_PUBLIC_API_TOKEN_MODE"
ROLE_ENV = "EUROGAS_NEXUS_PUBLIC_API_TOKEN_ROLE"
SCOPES_ENV = "EUROGAS_NEXUS_PUBLIC_API_TOKEN_SCOPES"
PREVIOUS_TOKEN_ENV = "EUROGAS_NEXUS_PUBLIC_API_TOKEN_PREVIOUS"

SERVICE = "service"
LEGACY_OPERATOR = "legacy_operator"
MODES = frozenset({SERVICE, LEGACY_OPERATOR})
PRODUCTION_ENVIRONMENTS = frozenset({"trial", "release"})
SERVICE_ROLES = frozenset({"VIEWER", "SCHEDULER", "ANALYST", "REVIEWER", "OPERATOR"})
#: The name recorded for acts of the deployment token; a claimed name is appended after ``@``.
SERVICE_ACTOR = "public-api"
INTERNAL_ACTOR = "internal-api"

_LOG = logging.getLogger(__name__)


def _environment(environ: Mapping[str, str]) -> str:
    from eurogas_nexus.core.config import runtime_environment

    return runtime_environment(environ)


def token_mode(environ: Mapping[str, str] | None = None) -> str:
    """``service`` or ``legacy_operator``; the default follows the environment."""

    env = os.environ if environ is None else environ
    raw = (env.get(MODE_ENV) or "").strip().lower()
    if raw in MODES:
        return raw
    return SERVICE if _environment(env) in PRODUCTION_ENVIRONMENTS else LEGACY_OPERATOR


def service_role(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    role = (env.get(ROLE_ENV) or "VIEWER").strip().upper()
    return role if role in SERVICE_ROLES else "VIEWER"


def service_scopes(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    env = os.environ if environ is None else environ
    raw = env.get(SCOPES_ENV) or ""
    return tuple(
        sorted({item.strip() for item in raw.split(",") if item.strip() and item.strip() != "*"})
    )


def assert_token_settings_allowed(environ: Mapping[str, str] | None = None) -> None:
    """Refuse a misconfigured token at start-up; warn while the legacy mode is in use.

    Raises:
        RuntimeError: an unknown mode, an ADMIN or unknown service role, or a ``*`` scope.
    """

    env = os.environ if environ is None else environ
    raw = (env.get(MODE_ENV) or "").strip().lower()
    if raw and raw not in MODES:
        raise RuntimeError(f"{MODE_ENV}={raw!r}: use 'service' or 'legacy_operator'")
    role = (env.get(ROLE_ENV) or "").strip().upper()
    if role and role not in SERVICE_ROLES:
        raise RuntimeError(
            f"{ROLE_ENV}={role!r}: the deployment token may hold one of "
            f"{sorted(SERVICE_ROLES)}; administration needs a person's own sign-in"
        )
    scopes = [item.strip() for item in (env.get(SCOPES_ENV) or "").split(",")]
    if "*" in scopes:
        raise RuntimeError(
            f"{SCOPES_ENV} may not contain '*': name the source families and BOOKS: scopes "
            "the integration needs"
        )
    if token_mode(env) == LEGACY_OPERATOR and (env.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN") or ""):
        _LOG.warning(
            "deployment token in deprecated legacy_operator mode: it reads every book and "
            "licensed dataset; set %s=service and move people to personal API keys",
            MODE_ENV,
        )


def claimed_actor(service: str, claimed: str) -> str:
    """``public-api@alice``: the service acted, and the name was claimed, not verified."""

    room = 64 - len(service) - 1
    return f"{service}@{claimed[:room]}"
