"""API import contract tests."""


def test_app_import_exposes_fastapi_app() -> None:
    from apps.api.main import app

    assert app.title == "Eurogas Nexus"
    assert any(route.path == "/v1/health" for route in app.routes)

