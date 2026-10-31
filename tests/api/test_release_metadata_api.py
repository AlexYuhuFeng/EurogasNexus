"""Release metadata API contract."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.release.constants import DB_SCHEMA_REVISION
from eurogas_nexus.version import APPLICATION_VERSION
from scripts.release.release_metadata import latest_alembic_revision

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
    # The reported schema revision is the release compatibility contract, so it
    # must be the constant the release manifest uses AND the real migration head:
    # a stale constant may not claim a schema the deployment has moved past.
    assert data["database_schema_revision"] == DB_SCHEMA_REVISION
    assert DB_SCHEMA_REVISION == latest_alembic_revision()
    assert data["minimum_supported_client"] == APPLICATION_VERSION
    assert data["minimum_supported_server"] == APPLICATION_VERSION
    # The public application historical run executes engine/2; the legacy
    # engine/1 helper identity is reported under its own name so stored engine/1
    # results are never relabelled.
    assert data["backtest_engine_version"] == "backtest-engine/2"
    assert data["legacy_backtest_engine_version"] == "backtest-engine/1"
    assert data["strategy_schema_version"] == "strategy-definition/v1"
    assert data["solver_version"] == "min-cost-flow/v1"


def test_release_profile_requires_public_token_for_release_metadata() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    assert client.get("/api/runtime/release").status_code == 401


def test_deployment_profile_picks_region_appropriate_basemaps():
    from eurogas_nexus.api.routes.public.runtime import deployment_profile

    assert deployment_profile({}) == {"region": "global", "map_default_provider": "openfreemap"}
    china = deployment_profile({"EUROGAS_NEXUS_DEPLOYMENT_REGION": "china"})
    assert china["map_default_provider"] == "outline"
    chosen = deployment_profile(
        {
            "EUROGAS_NEXUS_DEPLOYMENT_REGION": "china",
            "EUROGAS_NEXUS_MAP_DEFAULT_PROVIDER": "tianditu",
        }
    )
    assert chosen["map_default_provider"] == "tianditu"
    assert (
        deployment_profile({"EUROGAS_NEXUS_MAP_DEFAULT_PROVIDER": "osm"})["map_default_provider"]
        == "openfreemap"
    )  # a non-commercial endpoint is never a deployment default
