"""API import contract tests."""


def _route_paths(app: object) -> set[str]:
    return {path for route in app.routes if (path := getattr(route, "path", None))}


def test_app_import_exposes_fastapi_app() -> None:
    from apps.api.main import app

    paths = _route_paths(app)

    assert app.title == "Eurogas Nexus"
    assert "/v1/health" in paths
    assert "/api/v1/health" in paths

