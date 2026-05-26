"""Named route profiles for development and release deployments."""

from enum import StrEnum

from pydantic import BaseModel


class ApiProfileName(StrEnum):
    """Supported API exposure profiles."""

    DEVELOPMENT = "development"
    RELEASE = "release"


class ApiRouteProfile(BaseModel):
    """Route exposure switches for one deployment profile."""

    name: ApiProfileName
    expose_docs: bool
    expose_openapi: bool
    include_v1: bool = True
    include_internal: bool = False
    include_dev: bool = False


API_ROUTE_PROFILES: dict[ApiProfileName, ApiRouteProfile] = {
    ApiProfileName.DEVELOPMENT: ApiRouteProfile(
        name=ApiProfileName.DEVELOPMENT,
        expose_docs=True,
        expose_openapi=True,
        include_dev=True,
    ),
    ApiProfileName.RELEASE: ApiRouteProfile(
        name=ApiProfileName.RELEASE,
        expose_docs=False,
        expose_openapi=False,
    ),
}


def get_route_profile(name: str | ApiProfileName) -> ApiRouteProfile:
    """Return a named API route profile."""

    profile_name = ApiProfileName(name)
    return API_ROUTE_PROFILES[profile_name]

