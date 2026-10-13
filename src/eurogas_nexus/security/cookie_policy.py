"""Cookie transport-security policy for browser sessions.

The session and OIDC-verifier cookies used to set ``Secure`` from the inbound
request scheme alone (``request.url.scheme == "https"``). Behind the shipped
deployment that condition is never true: Caddy terminates TLS and proxies to
``api:8000`` over the container network, and uvicorn only rewrites
``request.url.scheme`` from ``X-Forwarded-Proto`` when the immediate peer is in
``FORWARDED_ALLOW_IPS`` (default ``127.0.0.1,::1``, which excludes the sidecar
proxy). The 12-hour session cookie was therefore issued without ``Secure``.

Inferring transport security from a value the network topology can silently
change is the wrong shape for a security control, so the rule is explicit:

* an ``https`` request is always ``Secure``;
* a non-development deployment (``release``/``internal`` API profile, or a
  ``trial``/``release`` environment) is always ``Secure``, whatever the request
  scheme looks like, because such a deployment is expected to be reached over
  TLS;
* only a development or test deployment may issue a non-``Secure`` cookie, so a
  plain-HTTP localhost workflow keeps working.

An operator who terminates TLS somewhere this rule cannot see is still covered:
the production profiles are unconditional.
"""

from __future__ import annotations

from typing import Protocol

#: Profiles that serve a real deployment and must never emit a plaintext cookie.
PRODUCTION_API_PROFILES = frozenset({"internal", "release"})

#: Environments that describe a real deployment.
PRODUCTION_ENVIRONMENTS = frozenset({"trial", "release"})


class CookieRequest(Protocol):
    """The request facts the cookie policy needs."""

    @property
    def scheme(self) -> str: ...


def session_cookie_secure(
    *,
    scheme: str,
    api_profile: str | None = None,
    environment: str | None = None,
) -> bool:
    """Return whether session cookies must carry the ``Secure`` attribute.

    Args:
        scheme: The request scheme as the application observes it.
        api_profile: Resolved API route profile name, when known.
        environment: Resolved ``EUROGAS_NEXUS_ENV`` value, when known.

    Returns:
        True when the cookie must be sent only over HTTPS.
    """

    if (scheme or "").strip().lower() == "https":
        return True
    if (api_profile or "").strip().lower() in PRODUCTION_API_PROFILES:
        return True
    return (environment or "").strip().lower() in PRODUCTION_ENVIRONMENTS


def request_cookie_secure(
    request: CookieRequest,
    *,
    api_profile: str | None = None,
    environment: str | None = None,
) -> bool:
    """Return the cookie policy decision for one request."""

    return session_cookie_secure(
        scheme=getattr(request, "scheme", "") or "",
        api_profile=api_profile,
        environment=environment,
    )


def deployment_cookie_context(request: object) -> tuple[str | None, str | None]:
    """Return ``(api_profile, environment)`` resolved from the application state.

    Read defensively: an application built without the usual lifespan state still
    answers, and an unreadable value simply leaves the production check to the
    request scheme rather than raising inside a login response.
    """

    state = getattr(request, "app", None)
    state = getattr(state, "state", None)
    settings = getattr(state, "settings", None)
    profile = getattr(state, "route_profile", None)

    api_profile = getattr(settings, "api_profile", None) or getattr(profile, "name", None)
    environment = getattr(settings, "environment", None)
    return (
        str(api_profile) if api_profile else None,
        str(environment) if environment else None,
    )
