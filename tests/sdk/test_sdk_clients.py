"""SDK client import and model tests (no live server needed)."""


def test_sdk_all_clients_importable() -> None:
    from eurogas_nexus.sdk.reference_network import (
        NodeDTO,
        fetch_nodes,
    )
    from eurogas_nexus.sdk.research import (
        compute_route_cost,
    )
    from eurogas_nexus.sdk.sources import (
        SourceSystem,
    )
    assert callable(fetch_nodes)
    assert callable(compute_route_cost)
    assert NodeDTO.model_fields
    assert SourceSystem.model_fields


def test_health_client_imports() -> None:
    from eurogas_nexus.sdk.health_client import HealthPayload, fetch_health
    assert callable(fetch_health)
    assert HealthPayload.model_fields


def test_research_result_models() -> None:
    from eurogas_nexus.sdk.research import (
        BacktestResult,
        NetbackResult,
        RouteCostResult,
        ShadowRunResult,
    )
    assert RouteCostResult.model_fields
    assert NetbackResult.model_fields
    assert BacktestResult.model_fields
    assert ShadowRunResult.model_fields


def test_sdk_does_not_import_backend_internals() -> None:
    import sys
    before = set(sys.modules.keys())
    import eurogas_nexus.sdk.reference_network  # noqa: F401
    import eurogas_nexus.sdk.research  # noqa: F401
    import eurogas_nexus.sdk.sources  # noqa: F401
    after = set(sys.modules.keys())
    forbidden = {
        "eurogas_nexus.db", "eurogas_nexus.runtime_store",
        "eurogas_nexus.workflows", "eurogas_nexus.ingestion",
        "eurogas_nexus.observations", "eurogas_nexus.governance",
    }
    leaked = (after - before) & forbidden
    assert not leaked, f"SDK leaked backend modules: {leaked}"
