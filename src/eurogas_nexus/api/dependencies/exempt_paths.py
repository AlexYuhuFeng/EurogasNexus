"""Paths that must answer without a credential, declared once.

Owner decision **D1** installs authentication in every route profile, and the first attempt at it
found the defect this module exists to prevent: the public-token gate had its own exemption list
(``/api/auth/``) while the identity dependency had none, so a login could not be reached and the
health probes - which an orchestrator, a load balancer or a CI readiness loop reads without any
credential - answered 401. Two lists would drift the same way again, so there is one.

Each prefix carries the reason it is exempt, because "exempt from authentication" is the kind of
declaration that should never be made quietly:

* ``/api/auth/`` and ``/api/dev/auth/`` - the routes that *issue* a credential. A login that
  required a login could never be used by anyone; the credential store gates what they do inside
  the handler, and the development login is mounted only by the development profile.
* ``/api/health`` - the probes (``live`` and ``ready`` by prefix). They report process liveness and
  mandatory-dependency readiness and carry no commercial material, and the tooling that reads them
  has no principal to present.
* ``/api/dev/health`` and ``/api/internal/health`` - the profile-specific health aliases, for the
  same reason.

What exemption means, precisely: the request is not refused for presenting nothing. If a caller
*does* present a credential on an exempt path, it is still resolved and validated - the exemption
is about the absence of a credential, not about skipping verification of one.
"""

from __future__ import annotations

CREDENTIAL_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/auth/",
    "/api/dev/auth/",
    "/api/health",
    "/api/dev/health",
    "/api/internal/health",
)


def is_credential_exempt(path: str) -> bool:
    """Whether ``path`` may be served to a caller that presented no credential.

    Args:
        path: The request path.

    Returns:
        True when the path is exempt, False when it requires a credential.
    """

    return path.startswith(CREDENTIAL_EXEMPT_PREFIXES)
