"""Named route profiles for development, internal, and release deployments."""

from enum import StrEnum

from pydantic import BaseModel


class ApiProfileName(StrEnum):
    """Supported API exposure profiles."""

    DEVELOPMENT = "development"
    INTERNAL = "internal"
    RELEASE = "release"


class ApiRouteProfile(BaseModel):
    """Route exposure switches for one deployment profile."""

    name: ApiProfileName
    expose_docs: bool
    expose_openapi: bool
    include_public: bool = True
    include_internal: bool = False
    include_dev: bool = False
    require_auth: bool = False


API_ROUTE_PROFILES: dict[ApiProfileName, ApiRouteProfile] = {
    ApiProfileName.DEVELOPMENT: ApiRouteProfile(
        name=ApiProfileName.DEVELOPMENT,
        expose_docs=True,
        expose_openapi=True,
        include_dev=True,
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
}


def get_route_profile(name: str | ApiProfileName) -> ApiRouteProfile:
    """Return a named API route profile."""

    profile_name = ApiProfileName(name)
    return API_ROUTE_PROFILES[profile_name]


def authentication_posture(name: str | ApiProfileName) -> str:
    """Whether a profile installs app-wide authentication.

    Architecture finding C5: the ``development`` and ``internal`` profiles deliberately
    install none, so a caller that presents no identity resolves to the documented
    single-trust-domain compatibility principal and receives its unrestricted row filtering.
    That is a posture, not an accident - and publishing it on the health payload makes it
    visible to whoever operates the deployment instead of only to whoever reads the conflict
    register.
    """

    return "enforced" if get_route_profile(name).require_auth else "not_installed"

