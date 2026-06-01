"""SDK client import and model tests (no live server needed)."""


def test_sdk_all_clients_importable() -> None:
    from eurogas_nexus.sdk.analysis import (
        ask_analysis,
        fetch_business_ontology,
        generate_portfolio_report,
    )
    from eurogas_nexus.sdk.glossary import (
        GlossaryTerm,
        fetch_glossary,
    )
    from eurogas_nexus.sdk.portfolio import (
        fetch_live_summary,
        fetch_pnl_snapshots,
        fetch_screen_orders,
    )
    from eurogas_nexus.sdk.reference_network import (
        NodeDTO,
        fetch_nodes,
    )
    from eurogas_nexus.sdk.research import (
        compute_route_cost,
    )
    from eurogas_nexus.sdk.route_cost import (
        compare_easington_contract_options,
    )
    from eurogas_nexus.sdk.sources import (
        SourceSystem,
    )
    from eurogas_nexus.sdk.strategy_lab import (
        evaluate_strategy_lab,
    )
    assert callable(fetch_nodes)
    assert callable(compute_route_cost)
    assert callable(compare_easington_contract_options)
    assert callable(ask_analysis)
    assert callable(fetch_business_ontology)
    assert callable(generate_portfolio_report)
    assert callable(evaluate_strategy_lab)
    assert callable(fetch_screen_orders)
    assert callable(fetch_pnl_snapshots)
    assert callable(fetch_live_summary)
    assert callable(fetch_glossary)
    assert NodeDTO.model_fields
    assert SourceSystem.model_fields
    assert GlossaryTerm.model_fields


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
    import eurogas_nexus.sdk.portfolio  # noqa: F401
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
