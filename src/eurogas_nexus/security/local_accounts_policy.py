"""Deployment settings for local accounts and demo test accounts (no database import).

Read by the application factory at start-up, so it must stay importable without SQLAlchemy:
the API import is database-free (``tests/contract/test_db_foundation.py``).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

LOCAL_ACCOUNTS_ENV = "EUROGAS_NEXUS_LOCAL_ACCOUNTS"
DEMO_TEST_ACCOUNTS_ENV = "EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS"
DEMO_ENVIRONMENTS = frozenset({"development", "test"})


def local_accounts_setting(environ: Mapping[str, str] | None = None) -> str:
    """``auto`` (default), ``on`` or ``off``; anything else reads as ``auto``."""

    value = ((environ or os.environ).get(LOCAL_ACCOUNTS_ENV) or "auto").strip().lower()
    if value in {"on", "true", "1", "yes"}:
        return "on"
    if value in {"off", "false", "0", "no"}:
        return "off"
    return "auto"


def local_accounts_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Whether local sign-in and local-account creation are offered.

    ``auto`` turns them on only when no company SSO is configured, so a small firm can run
    the product, while a firm with SSO keeps one way in unless it opts in with ``on``.
    """

    setting = local_accounts_setting(environ)
    if setting != "auto":
        return setting == "on"
    from eurogas_nexus.core.config import runtime_environment

    if runtime_environment(environ) in {"trial", "release"}:
        # Security review H6: a production installation never falls back to passwords
        # because SSO is missing; local accounts are a deliberate choice ("on").
        return False
    from eurogas_nexus.security.oidc import oidc_configured

    return not oidc_configured()


def assert_sign_in_configured(environment: str, environ: Mapping[str, str] | None = None) -> None:
    """Refuse to start a trial or release server that offers no way to sign in.

    Raises:
        RuntimeError: neither company SSO (OIDC or the authenticating gateway) nor local
            accounts (``EUROGAS_NEXUS_LOCAL_ACCOUNTS=on``) is configured.
    """

    if str(environment or "").strip().lower() not in {"trial", "release"}:
        return
    source = os.environ if environ is None else environ
    if local_accounts_setting(source) == "on":
        return
    from eurogas_nexus.security.oidc import oidc_configured

    if oidc_configured(source):
        return
    from eurogas_nexus.security.gateway_auth import GatewayConfig

    if GatewayConfig.from_env(source).enabled:
        return
    raise RuntimeError(
        "No sign-in is configured for this release server: set up company SSO "
        "(EUROGAS_NEXUS_OIDC_ISSUER and EUROGAS_NEXUS_OIDC_CLIENT_ID, or the authenticating "
        "gateway), or enable local accounts deliberately with EUROGAS_NEXUS_LOCAL_ACCOUNTS=on "
        "(then require a second factor: EUROGAS_NEXUS_MFA_REQUIRED). Local accounts are no "
        "longer switched on automatically when SSO is missing."
    )


def demo_profile_active(environ: Mapping[str, str] | None = None) -> bool:
    """The demo route profile in a development/test environment (the only demo server)."""

    source = environ or os.environ
    profile = (source.get("EUROGAS_NEXUS_API_PROFILE") or "development").strip().lower()
    from eurogas_nexus.core.config import runtime_environment

    environment = runtime_environment(source)
    return profile == "demo" and environment in DEMO_ENVIRONMENTS


def assert_demo_accounts_allowed(
    api_profile: str, environment: str, environ: Mapping[str, str] | None = None
) -> None:
    """Refuse to start when demo test accounts are configured outside the demo server.

    Raises:
        RuntimeError: ``EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS`` is set and the server is not the
            demo profile in a development/test environment (a customer runtime).
    """

    source = environ or os.environ
    if not (source.get(DEMO_TEST_ACCOUNTS_ENV) or "").strip():
        return
    profile = str(api_profile or "").strip().lower()
    env = str(environment or "").strip().lower()
    if profile != "demo" or env not in DEMO_ENVIRONMENTS:
        raise RuntimeError(
            f"{DEMO_TEST_ACCOUNTS_ENV} is refused for API profile {profile!r} in a {env!r} "
            "environment: demo test accounts with a shared weak password exist only on the "
            "hosted demo server (EUROGAS_NEXUS_API_PROFILE=demo, EUROGAS_NEXUS_ENV=development)"
        )


