"""Every non-GET route declares its permission with its method or exact path (review M2).

A path family (``/api/portfolio/``) declares the floor of its reads. A write that resolved
through it was authorised at a read floor, so write safety depended on each handler
remembering a check. Now ``permission_for_path`` refuses a non-GET request that matches only a
family (deny by default), and this test fails when a new write route is added without its own
declaration.
"""

from __future__ import annotations

import pytest

from eurogas_nexus.api.route_profiles import ApiProfileName, get_route_profile
from eurogas_nexus.security import permissions


def _routes(profile: ApiProfileName):
    from fastapi import FastAPI

    from eurogas_nexus.api.route_registration import register_routes

    app = FastAPI()
    register_routes(app, get_route_profile(profile))
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            yield method.upper(), path


@pytest.mark.parametrize("profile", [ApiProfileName.DEVELOPMENT, ApiProfileName.INTERNAL])
def test_every_write_route_has_its_own_declaration(profile):
    undeclared = []
    routes = list(_routes(profile))
    assert sum(1 for method, _path in routes if method != "GET") > 50
    for method, path in routes:
        if not path.startswith("/api/") or method in {"GET", "HEAD", "OPTIONS"}:
            continue
        try:
            permissions.permission_for_path(path, method)
        except KeyError:
            undeclared.append(f"{method} {path}")
    assert undeclared == [], "declare these in security/permissions.py"


def test_a_write_through_a_read_family_is_refused():
    assert permissions.permission_for_path("/api/portfolio/anything-new", "GET")
    with pytest.raises(KeyError):
        permissions.permission_for_path("/api/portfolio/anything-new", "POST")
    with pytest.raises(KeyError):
        permissions.permission_for_path("/api/market/anything-new", "DELETE")
