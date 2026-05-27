"""API profile behavior tests."""

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings


def test_development_profile_exposes_docs_and_openapi() -> None:
    app = create_app(Settings(api_profile="development"))

    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"


def test_release_profile_hides_docs_and_openapi() -> None:
    app = create_app(Settings(api_profile="release"))

    assert app.docs_url is None
    assert app.openapi_url is None
