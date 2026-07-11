"""Seed public references and DB-resident preview trading inputs.

This script is for the local PostgreSQL test server only. Public tariff rows are
manually transcribed source references. Public route templates are derived from
those tariff references. Preview contracts are clearly marked because customer
contracts require entitlement. Price rows are inserted through the simulated
EEX_Sim, ICE_OCM_Sim, Trayport_Sim, and ICIS_Sim feed path so the market terminal,
source health, route costing, and strategy screens exercise the same PostgreSQL
tables used by licensed market-data connectors. The script does not call external
APIs, run migrations, or print database secrets.
"""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.db.models import (
    GlossaryTermRecord,
    LiveMarketMarkRecord,
    MarketObservationRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.session import (
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.domain.glossary import baseline_glossary_terms
from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    BBL_DOCUMENT_ID,
    IUK_DOCUMENT_ID,
    published_european_corridor_tariffs,
)
from eurogas_nexus.domain.route_cost.uk_public_tariffs import (
    DOCUMENT_ID as NATIONAL_GAS_DOCUMENT_ID,
)
from eurogas_nexus.domain.route_cost.uk_public_tariffs import (
    published_uk_capacity_tariffs,
)
from eurogas_nexus.ingestion.simulated_market_prices import (
    upsert_simulated_market_observations,
)

try:
    from scripts.ops.materialize_reference_edges import materialize_route_candidate_edges
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from materialize_reference_edges import materialize_route_candidate_edges

LEGACY_DEMO_PRICE_IDS = [
    "demo-market-nbp-day-ahead",
    "demo-market-ttf-day-ahead",
    "demo-market-ztp-day-ahead",
    "demo-market-peg-day-ahead",
    "demo-market-the-day-ahead",
]
LEGACY_PRICE_SOURCE_SYSTEM = "demo" + "_market" + "_price"
SIMULATED_PRICE_SOURCE_SYSTEMS = (
    "EEX_Sim",
    "ICE_OCM_Sim",
    "Trayport_Sim",
    "ICIS_Sim",
)
PUBLIC_ROUTE_IDS = [
    "public-route-ttf-bbl-nbp",
    "public-route-nbp-iuk-ztp",
    "public-route-ttf-local",
]
PREVIEW_CONTRACT_IDS = [
    "preview-portfolio-contract-ttf-pool-2025",
]
LEGACY_FIXTURE_CONTRACT_IDS = [
    "demo-portfolio-contract-ttf-pool-2025",
    "operator-test-easington-contract",
]


def main() -> int:
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2

    print(f"Runtime DB: {redact_database_url(database_url)}")
    now = datetime.now(UTC)
    session_factory = get_session_factory(database_url=database_url)
    with session_factory() as session:
        _clear_previous_preview_rows(session)
        _seed_public_tariffs(session, now)
        _seed_simulated_prices(session, now)
        _seed_preview_contract(session, now)
        _seed_public_route_templates(session, now)
        _seed_glossary(session, now)
        session.commit()
    edge_summary = materialize_route_candidate_edges(database_url=database_url)

    print(
        "Seeded public tariff rows, DB-resident simulated price rows, "
        "preview portfolio contract, public route templates, glossary terms, "
        f"and {edge_summary['created_or_updated']} route-candidate map edges."
    )
    return 0


def _clear_previous_preview_rows(session) -> None:
    session.query(TsoTariffRecord).filter(
        TsoTariffRecord.document_id.in_(
            [NATIONAL_GAS_DOCUMENT_ID, BBL_DOCUMENT_ID, IUK_DOCUMENT_ID]
        )
    ).delete(synchronize_session=False)
    session.query(LiveMarketMarkRecord).filter(
        LiveMarketMarkRecord.mark_id.in_(
            [
                "demo-market-price-ice-ocm-nbp-within-day",
            ]
        )
    ).delete(synchronize_session=False)
    session.query(LiveMarketMarkRecord).filter(
        LiveMarketMarkRecord.source_system == LEGACY_PRICE_SOURCE_SYSTEM
    ).delete(synchronize_session=False)
    session.query(UpstreamResourceContractRecord).filter(
        UpstreamResourceContractRecord.contract_id.in_(
            [*PREVIEW_CONTRACT_IDS, *LEGACY_FIXTURE_CONTRACT_IDS]
        )
    ).delete(synchronize_session=False)
    session.query(RouteCandidateRecord).filter(
        RouteCandidateRecord.route_id.in_(PUBLIC_ROUTE_IDS)
    ).delete(synchronize_session=False)
    session.query(MarketObservationRecord).filter(
        MarketObservationRecord.observation_id.in_(LEGACY_DEMO_PRICE_IDS)
    ).delete(synchronize_session=False)
    session.query(MarketObservationRecord).filter(
        MarketObservationRecord.source_system == LEGACY_PRICE_SOURCE_SYSTEM
    ).delete(synchronize_session=False)
    session.flush()


def _seed_public_tariffs(session, now: datetime) -> None:
    for tariff in [
        *published_uk_capacity_tariffs(),
        *published_european_corridor_tariffs(),
    ]:
        session.merge(
            TsoTariffRecord(
                tariff_id=tariff.tariff_id,
                document_id=tariff.document_id,
                country=tariff.country,
                tso=tariff.tso,
                market_area=tariff.market_area,
                gas_year=tariff.gas_year,
                point_id=tariff.point_id,
                source_point_name=tariff.source_point_name,
                direction=tariff.direction.value,
                capacity_product=tariff.capacity_product.value,
                firmness=tariff.firmness.value,
                tariff_value=tariff.tariff_value,
                currency=tariff.currency,
                unit=tariff.unit,
                effective_from=datetime.combine(
                    tariff.effective_from,
                    datetime.min.time(),
                    UTC,
                ),
                effective_to=(
                    datetime.combine(tariff.effective_to, datetime.min.time(), UTC)
                    if tariff.effective_to
                    else None
                ),
                tariff_status=tariff.tariff_status.value,
                source_table=tariff.source_table,
                source_page=tariff.source_page,
                source_refs=tariff.source_refs,
                manual_review_required=tariff.manual_review_required,
                created_at_utc=now,
            )
        )


def _seed_simulated_prices(session, now: datetime) -> None:
    upsert_simulated_market_observations(
        session,
        observed_at_utc=now,
        source_systems=SIMULATED_PRICE_SOURCE_SYSTEMS,
    )


def _seed_preview_contract(session, now: datetime) -> None:
    session.merge(
        UpstreamResourceContractRecord(
            contract_id="preview-portfolio-contract-ttf-pool-2025",
            contract_name="Preview TTF portfolio supply 2025",
            resource_type="PIPELINE_IMPORT",
            delivery_point_name="TTF",
            gas_year="2025+",
            delivery_quantity_mwh_per_day=10000.0,
            contract_price_gbp_mwh=25.0,
            settlement_frequency="monthly",
            upstream_payment_lag_days=20,
            screen_sale_cash_lag_days=1,
            annual_financing_rate_pct=6.0,
            delivery_tolerance_pct=2.0,
            nomination_tolerance_pct=1.0,
            tolerance_risk_allowance_gbp_mwh=0.1,
            owned_entry_capacity_mwh_per_day=None,
            owned_exit_capacity_mwh_per_day=None,
            allowed_exit_points=["NBP", "TTF", "ZTP", "PEG", "THE"],
            eligible_sale_modes=[
                "TARGET_MARKET_SALE",
                "LOCAL_MARKET_SALE",
                "REROUTE_SALE",
            ],
            notes="preview_portfolio_contract:not_customer_data",
            created_at_utc=now,
            updated_at_utc=now,
        )
    )


def _seed_public_route_templates(session, now: datetime) -> None:
    for route in [
        RouteCandidateRecord(
            route_id="public-route-ttf-bbl-nbp",
            route_name="TTF -> BBL -> NBP",
            start_point_name="TTF",
            target_point_name="NBP",
            business_model="CROSS_BORDER_TRANSFER",
            route_legs=[
                {
                    "leg_id": "bbl-forward",
                    "country": "NL",
                    "tso": "BBL Company",
                    "market_area": "BBL",
                    "point_name": "BBL Forward Flow NL to GB",
                    "direction": "EXIT",
                    "available_capacity_mwh_per_day": 2000.0,
                }
            ],
            required_entry_point_name=None,
            required_exit_point_name=None,
            required_tso_access=["BBL Company"],
            source_systems=["public_route_template", "BBL"],
            active=True,
            created_at_utc=now,
        ),
        RouteCandidateRecord(
            route_id="public-route-nbp-iuk-ztp",
            route_name="NBP -> IUK -> ZTP",
            start_point_name="NBP",
            target_point_name="ZTP",
            business_model="CROSS_BORDER_TRANSFER",
            route_legs=[
                {
                    "leg_id": "iuk-uk-be",
                    "country": "GB",
                    "tso": "Interconnector UK",
                    "market_area": "IUK",
                    "point_name": "IUK Bacton Entry",
                    "direction": "ENTRY",
                    "available_capacity_mwh_per_day": 1500.0,
                },
                {
                    "leg_id": "iuk-be-exit",
                    "country": "BE",
                    "tso": "Interconnector UK",
                    "market_area": "IUK",
                    "point_name": "IUK Zeebrugge Exit",
                    "direction": "EXIT",
                    "available_capacity_mwh_per_day": 1500.0,
                },
            ],
            required_entry_point_name="IUK Bacton Entry",
            required_exit_point_name="IUK Zeebrugge Exit",
            required_tso_access=["Interconnector UK"],
            source_systems=["public_route_template", "IUK"],
            active=True,
            created_at_utc=now,
        ),
        RouteCandidateRecord(
            route_id="public-route-ttf-local",
            route_name="Sell locally at TTF",
            start_point_name="TTF",
            target_point_name="TTF",
            business_model="VIRTUAL_HUB_SALE",
            route_legs=[],
            required_entry_point_name=None,
            required_exit_point_name=None,
            required_tso_access=[],
            source_systems=["public_route_template", "ENTSOG"],
            active=True,
            created_at_utc=now,
        ),
    ]:
        session.merge(route)


def _seed_glossary(session, now: datetime) -> None:
    for term in baseline_glossary_terms():
        session.merge(
            GlossaryTermRecord(
                term_id=term.term_id,
                term=term.term,
                category=term.category,
                definition_en=term.definition_en,
                definition_zh_cn=term.definition_zh_cn,
                aliases=term.aliases,
                related_terms=term.related_terms,
                source_refs=term.source_refs,
                active=True,
                created_at_utc=now,
                updated_at_utc=now,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
