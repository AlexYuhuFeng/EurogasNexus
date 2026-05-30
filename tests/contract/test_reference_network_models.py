"""Reference network model contract tests (DB-free)."""


def test_reference_node_model_is_importable() -> None:
    from eurogas_nexus.db.models.reference_network import ReferenceNode

    assert ReferenceNode.__tablename__ == "reference_nodes"


def test_reference_edge_model_is_importable() -> None:
    from eurogas_nexus.db.models.reference_network import ReferenceEdge

    assert ReferenceEdge.__tablename__ == "reference_edges"


def test_reference_facility_model_is_importable() -> None:
    from eurogas_nexus.db.models.reference_network import ReferenceFacility

    assert ReferenceFacility.__tablename__ == "reference_facilities"


def test_reference_market_hub_model_is_importable() -> None:
    from eurogas_nexus.db.models.reference_network import ReferenceMarketHub

    assert ReferenceMarketHub.__tablename__ == "reference_market_hubs"


def test_node_facility_mapping_model_has_confidence_and_eligibility() -> None:
    from eurogas_nexus.db.models.reference_network import NodeFacilityMapping

    assert NodeFacilityMapping.__tablename__ == "node_facility_mappings"
    # Verify the model has confidence (Float) and eligibility (String) columns.
    cols = {c.name: c for c in NodeFacilityMapping.__table__.columns}
    assert "confidence" in cols
    assert "eligibility" in cols


def test_topology_market_mapping_model_has_confidence_and_eligibility() -> None:
    from eurogas_nexus.db.models.reference_network import TopologyMarketMapping

    assert TopologyMarketMapping.__tablename__ == "topology_market_mappings"
    cols = {c.name: c for c in TopologyMarketMapping.__table__.columns}
    assert "confidence" in cols
    assert "eligibility" in cols


def test_all_six_tables_in_required_registry() -> None:
    from eurogas_nexus.db.registry import list_required_tables

    required = set(list_required_tables())
    for table in (
        "reference_nodes",
        "reference_edges",
        "reference_facilities",
        "reference_market_hubs",
        "node_facility_mappings",
        "topology_market_mappings",
    ):
        assert table in required, f"'{table}' missing from required table registry"


def test_registry_includes_r3_revision() -> None:
    from eurogas_nexus.db.registry import REQUIRED_TABLES

    revisions = {t.introduced_in for t in REQUIRED_TABLES}
    assert "0003_r3_reference_network" in revisions


def test_alembic_revision_0003_exists() -> None:
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0003_r3_reference_network.py"
    )
    assert migration.is_file(), f"Migration file not found: {migration}"


def test_models_are_exported_from_package() -> None:
    from eurogas_nexus.db.models import (
        NodeFacilityMapping,
        ReferenceEdge,
        ReferenceFacility,
        ReferenceMarketHub,
        ReferenceNode,
        TopologyMarketMapping,
    )

    # All imports must succeed.
    assert ReferenceNode.__tablename__ == "reference_nodes"
    assert ReferenceEdge.__tablename__ == "reference_edges"
    assert ReferenceFacility.__tablename__ == "reference_facilities"
    assert ReferenceMarketHub.__tablename__ == "reference_market_hubs"
    assert NodeFacilityMapping.__tablename__ == "node_facility_mappings"
    assert TopologyMarketMapping.__tablename__ == "topology_market_mappings"
