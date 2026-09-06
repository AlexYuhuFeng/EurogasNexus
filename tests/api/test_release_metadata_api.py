"""Release metadata API contract."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.version import APPLICATION_VERSION

AUTH_HEADERS = {"X-Eurogas-Api-Key": "test-public-api-token"}


def test_release_metadata_separates_version_channel_and_commit() -> None:
    settings = Settings(
        release_channel="preview",
        build_git_sha="033df92a856e8820dd0f4d2a02367b21a285664d",
        build_git_ref="refs/tags/v0.5.0-preview.1.033df92a856e",
    )
    response = TestClient(create_app(settings=settings)).get(
        "/api/runtime/release", headers=AUTH_HEADERS
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["application_version"] == APPLICATION_VERSION
    assert data["release_channel"] == "preview"
    assert data["git_sha"] == "033df92a856e8820dd0f4d2a02367b21a285664d"
    assert data["api_contract_version"] == "api-contract/v1"
    assert data["database_schema_revision"] == "0030_reliability_indexes"
    assert data["minimum_supported_client"] == APPLICATION_VERSION
    assert data["minimum_supported_server"] == APPLICATION_VERSION
    assert data["backtest_engine_version"] == "backtest-engine/1"
    assert data["strategy_schema_version"] == "strategy-definition/v1"
    assert data["solver_version"] == "min-cost-flow/v1"


def test_release_profile_requires_public_token_for_release_metadata() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    assert client.get("/api/runtime/release").status_code == 401
