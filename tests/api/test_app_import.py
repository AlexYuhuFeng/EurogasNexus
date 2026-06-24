"""API import contract tests."""


def _route_paths(app: object) -> set[str]:
    paths: set[str] = set()
    pending = list(getattr(app, "routes", ()))
    while pending:
        route = pending.pop()
        if path := getattr(route, "path", None):
            paths.add(path)
        pending.extend(getattr(route, "routes", ()) or ())
    return paths


def test_app_import_exposes_fastapi_app() -> None:
    from apps.api.main import app

    paths = _route_paths(app)

    assert app.title == "Eurogas Nexus"
    assert "/v1/health" in paths
    assert "/api/v1/health" in paths

