"""Unified Data Platform contract tests (Architecture V2 Wave 4).

Pins the two declarations the Wave 4 surface rests on:

1. every Data Product stays anchored in code that exists in this repository -
   declared source families are registered sources, every endpoint it names is a
   real served route, and every provenance table is a real mapped table;
2. the Analysis Snapshot descriptor keeps the ``07_DATA_PLATFORM.md`` section 6
   field list, has a forward-only migration and a registered model, and the new
   paths are declared in the permission registry.

These are static/DB-free checks so they run in every environment.
"""

from __future__ import annotations

from pathlib import Path

from apps.api.main import app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.registry import required_table_names
from eurogas_nexus.domain.data_platform.products import (
    DataProductAvailability,
    SurfaceKind,
    data_products,
    product_by_id,
)
from eurogas_nexus.domain.data_platform.snapshots import (
    ANALYSIS_SNAPSHOT_SCHEMA_VERSION,
    DESCRIPTOR_FIELDS,
)
from eurogas_nexus.domain.dataops.entitlement import COMMERCIAL_SOURCE_FAMILIES
from eurogas_nexus.ingestion.public_sources import KWH_PER_MCM  # noqa: F401  (import safety)
from eurogas_nexus.ingestion.simulated_market_prices import (
    SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS,
)
from eurogas_nexus.security.identity import PUBLIC_BASELINE_SOURCE_FAMILIES
from eurogas_nexus.security.permissions import Permission, permission_for_path

ROOT = Path(__file__).resolve().parents[2]

#: The Data Products named by ``07_DATA_PLATFORM.md`` section 2. None may be
#: dropped from the catalogue without an architecture decision.
V2_NAMED_PRODUCTS = {
    "nbp-day-ahead-market-context",
    "ttf-eu-forward-curve-context",
    "european-physical-flow",
    "capacity-availability",
    "storage-context",
    "weather-context",
    "portfolio-position",
    "route-cost-inputs",
}


def _registered_source_systems() -> set[str]:
    from eurogas_nexus.domain.ingestion.source_registry import registered_sources

    return {source["source_system"] for source in registered_sources()}


def test_catalogue_covers_every_v2_named_data_product() -> None:
    declared = {product.product_id for product in data_products()}
    assert V2_NAMED_PRODUCTS <= declared, f"missing: {V2_NAMED_PRODUCTS - declared}"


def test_catalogue_ids_are_unique_and_stable_shaped() -> None:
    ids = [product.product_id for product in data_products()]
    assert len(ids) == len(set(ids))
    for product_id in ids:
        assert product_id == product_id.lower()
        assert " " not in product_id
        assert product_by_id(product_id) is not None


def test_every_product_is_a_business_contract() -> None:
    for product in data_products():
        assert product.business_name.strip()
        assert product.description.strip()
        assert product.domain.strip()
        assert product.availability in DataProductAvailability
        assert product.availability_note.strip(), product.product_id
        assert product.source_families or product.availability in {
            DataProductAvailability.NOT_IMPLEMENTED,
            DataProductAvailability.DECLARED_ONLY,
        }, product.product_id


def test_declared_source_families_are_registered_or_simulated_sources() -> None:
    registered = _registered_source_systems()
    simulated = set(SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS)
    baseline = set(PUBLIC_BASELINE_SOURCE_FAMILIES)
    for product in data_products():
        for family in product.source_families:
            assert family in registered | simulated | baseline, (
                f"{product.product_id}: unknown source family {family}"
            )
        for family in product.simulated_families:
            assert family in simulated, (
                f"{product.product_id}: {family} is not a simulated source system"
            )
            assert family.removesuffix("_Sim") in product.source_families


def test_entitlement_families_are_known_security_families() -> None:
    known = set(COMMERCIAL_SOURCE_FAMILIES) | set(PUBLIC_BASELINE_SOURCE_FAMILIES)
    for product in data_products():
        for family in product.entitlement_families:
            assert family in known, f"{product.product_id}: unknown entitlement family {family}"
            # A public-baseline family never requires a commercial grant.
            assert family not in PUBLIC_BASELINE_SOURCE_FAMILIES, product.product_id


def test_declared_endpoints_are_really_served() -> None:
    paths = set(app.openapi()["paths"])
    for product in data_products():
        for surface in product.served_by:
            if surface.kind is not SurfaceKind.ENDPOINT:
                continue
            reference = surface.reference.split(" ", 1)[-1]
            assert reference in paths, (
                f"{product.product_id}: declared endpoint {reference} is not served"
            )


def test_declared_modules_and_commands_exist() -> None:
    for product in data_products():
        for surface in product.served_by:
            if surface.kind is SurfaceKind.MODULE:
                assert (ROOT / "src" / "eurogas_nexus" / surface.reference).is_file(), (
                    f"{product.product_id}: module {surface.reference} does not exist"
                )
            if surface.kind is SurfaceKind.COMMAND:
                script = surface.reference.split()[1]
                assert (ROOT / script).is_file(), (
                    f"{product.product_id}: command script {script} does not exist"
                )


def test_provenance_tables_are_mapped_tables() -> None:
    import eurogas_nexus.db.models  # noqa: F401  (registers the metadata)

    for product in data_products():
        for table in product.provenance_tables:
            assert table in Base.metadata.tables, (
                f"{product.product_id}: provenance table {table} is not mapped"
            )


def test_products_without_an_implementation_say_so() -> None:
    not_implemented = [
        product
        for product in data_products()
        if product.availability
        in {DataProductAvailability.NOT_IMPLEMENTED, DataProductAvailability.DECLARED_ONLY}
    ]
    assert not_implemented, "the catalogue must declare honestly unimplemented products"
    for product in not_implemented:
        assert product.availability_note.strip()
    # A product with no served surface must be NOT_IMPLEMENTED, never AVAILABLE.
    for product in data_products():
        if not product.served_by:
            assert product.availability is DataProductAvailability.NOT_IMPLEMENTED


def test_weather_is_declared_but_not_pretended() -> None:
    weather = product_by_id("weather-context")
    assert weather is not None
    assert weather.availability is DataProductAvailability.DECLARED_ONLY
    assert "WEATHER_SOURCE_NOT_CONFIGURED" in weather.availability_note


def test_descriptor_field_list_matches_section_six() -> None:
    assert DESCRIPTOR_FIELDS == (
        "market_data_versions",
        "network_capacity_version",
        "portfolio_version",
        "contract_resource_versions",
        "tariff_fx",
        "weather_demand_assumptions",
        "manual_assumptions",
        "model_calculation_versions",
        "entitlement_context",
    )
    assert ANALYSIS_SNAPSHOT_SCHEMA_VERSION == "analysis-snapshot.v1"


def test_analysis_snapshot_model_and_migration_are_registered() -> None:
    import eurogas_nexus.db.models  # noqa: F401  (registers the model)

    assert "analysis_snapshots" in Base.metadata.tables
    assert "analysis_snapshots" in required_table_names()

    migration = ROOT / "alembic" / "versions" / "0034_analysis_snapshots.py"
    text = migration.read_text(encoding="utf-8")
    assert migration.is_file()
    assert 'revision: str = "0034_analysis_snapshots"' in text
    assert 'down_revision: str | None = "0033_market_obs_order_indexes"' in text
    for token in (
        '"snapshot_id"',
        '"as_of_utc"',
        '"gas_day"',
        '"market_data_versions_json"',
        '"network_capacity_version_json"',
        '"portfolio_version_json"',
        '"contract_resource_versions_json"',
        '"tariff_fx_json"',
        '"weather_demand_assumptions_json"',
        '"manual_assumptions_json"',
        '"model_calculation_versions_json"',
        '"entitlement_context_json"',
        '"field_availability_json"',
        '"content_hash"',
    ):
        assert token in text, token


def test_analysis_snapshot_migration_states_backward_compatibility() -> None:
    text = (ROOT / "alembic" / "versions" / "0034_analysis_snapshots.py").read_text(
        encoding="utf-8"
    )
    assert "Backward compatibility" in text
    assert "Expand-only and non-destructive" in text
    # Non-destructive: no drop of a pre-existing table or column.
    assert "drop_table" not in text.split("def downgrade", 1)[0]
    assert 'op.drop_table("analysis_snapshots")' in text


def test_new_paths_have_declared_permissions() -> None:
    assert permission_for_path("/api/data-products") is Permission.READ
    assert permission_for_path("/api/analysis-snapshots") is Permission.READ
    assert permission_for_path("/api/analysis-snapshots", "GET") is Permission.READ
    assert permission_for_path("/api/analysis-snapshots", "POST") is Permission.GOVERNED
    assert (
        permission_for_path("/api/analysis-snapshots/asnap-abc") is Permission.READ
    )


def test_catalogue_and_snapshot_reads_stay_out_of_the_commercial_prefix_family() -> None:
    """The snapshot read is lineage metadata; the analysis *query* family is not it."""

    from eurogas_nexus.security.permissions import serves_commercial_data

    # /api/analysis/ (query + reports) stays commercial; the new paths are not
    # inside that family, so a caller can see its own entitlement limitation.
    assert serves_commercial_data("/api/analysis/query") is True
    assert serves_commercial_data("/api/data-products") is False
    assert serves_commercial_data("/api/analysis-snapshots") is False
