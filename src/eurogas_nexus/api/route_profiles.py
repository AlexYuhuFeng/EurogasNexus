"""Named route profiles for development, internal, and release deployments."""

from enum import StrEnum

from pydantic import BaseModel


class ApiProfileName(StrEnum):
    """Supported API exposure profiles."""

    DEVELOPMENT = "development"
    INTERNAL = "internal"
    RELEASE = "release"
    #: A hosted test and demonstration server (docs/deployment/SELF_HOSTED_DEMO.md): the
    #: release surface plus the credential sign-in for its provisioned tester identities.
    #: Refused in trial and release environments (``assert_profile_allowed``).
    DEMO = "demo"


class ApiRouteProfile(BaseModel):
    """Route exposure switches for one deployment profile."""

    name: ApiProfileName
    expose_docs: bool
    expose_openapi: bool
    include_public: bool = True
    include_internal: bool = False
    include_dev: bool = False
    #: Whether this profile identifies its callers (finding C5 / owner decision D1).
    #:
    #: True in every profile: a *profile* does not decide whether callers are identified, because
    #: the posture a deployment wants is a deployment statement. A deployment that trusts its
    #: network says so with ``EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS``, and that choice is reported
    #: by the health payload instead of being inherited from the code.
    require_auth: bool = True


API_ROUTE_PROFILES: dict[ApiProfileName, ApiRouteProfile] = {
    ApiProfileName.DEVELOPMENT: ApiRouteProfile(
        name=ApiProfileName.DEVELOPMENT,
        expose_docs=True,
        expose_openapi=True,
        include_dev=True,
        require_auth=True,
    ),
    ApiProfileName.INTERNAL: ApiRouteProfile(
        name=ApiProfileName.INTERNAL,
        expose_docs=False,
        expose_openapi=False,
        include_internal=True,
    ),
    ApiProfileName.RELEASE: ApiRouteProfile(
        name=ApiProfileName.RELEASE,
        expose_docs=False,
        expose_openapi=False,
        require_auth=True,
    ),
    # Hosted test/demo server: no /docs or /openapi.json, every caller identified, and the
    # credential sign-in under /api/dev/auth/login so invited testers can use the product
    # without an identity provider. Its session cookies are always Secure (cookie_policy).
    ApiProfileName.DEMO: ApiRouteProfile(
        name=ApiProfileName.DEMO,
        expose_docs=False,
        expose_openapi=False,
        include_dev=True,
        require_auth=True,
    ),
}

#: Environments in which the demo profile may be served. Trial and release describe a
#: customer deployment; a credential sign-in and simulated demo data never belong there.
DEMO_PROFILE_ENVIRONMENTS = frozenset({"development", "test"})


def assert_profile_allowed(name: str | ApiProfileName, environment: str) -> None:
    """Refuse a route profile the runtime environment must never serve.

    Raises:
        RuntimeError: when the demo profile is selected in a trial or release environment.
    """

    if ApiProfileName(name) is ApiProfileName.DEMO and (
        (environment or "").strip().lower() not in DEMO_PROFILE_ENVIRONMENTS
    ):
        raise RuntimeError(
            "EUROGAS_NEXUS_API_PROFILE=demo is refused in a "
            f"{environment!r} environment; it is for a hosted test/demo server only "
            "(EUROGAS_NEXUS_ENV=development)"
        )


def get_route_profile(name: str | ApiProfileName) -> ApiRouteProfile:
    """Return a named API route profile."""

    profile_name = ApiProfileName(name)
    return API_ROUTE_PROFILES[profile_name]


def authentication_posture(
    name: str | ApiProfileName, *, allow_anonymous_callers: bool = False
) -> str:
    """Whether a deployment identifies its callers.

    认证姿态：标识调用方（enforced）还是由部署显式声明信任网络（anonymous_allowed）。

    Architecture finding C5 was published as a runtime posture because a code default that trusts
    the network is surprising. Owner decision **D1** then installed authentication in every profile,
    so the surprising default is gone and what remains is a deployment's own choice: with
    ``EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS`` set, a caller that presents nothing resolves to the
    documented compatibility principal and receives its unrestricted row filtering - which the
    payload says out loud, so an operator still cannot be surprised by it.

    Args:
        name: Route profile name.
        allow_anonymous_callers: Whether the deployment opted into trusting its network.

    Returns:
        ``"enforced"`` when a caller that presents nothing is refused, or ``"anonymous_allowed"``
        when the deployment explicitly permits it.

    Raises:
        ValueError: When ``name`` is not a registered profile.
    """

    profile = get_route_profile(name)
    if not profile.require_auth:
        # No profile does this today; a profile that installed no authentication would be reported
        # as what it is rather than silently as "enforced".
        return "not_installed"
    return "anonymous_allowed" if allow_anonymous_callers else "enforced"
