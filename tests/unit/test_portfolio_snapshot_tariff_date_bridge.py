"""The PortfolioSnapshot projection's connected route-tariff date bridge.

The projection resolves one canonical ``ProjectionContext`` gas day and passes
that exact date into the shared resource-pool composition. These tests use a real
SQLite runtime store and the actual repository reads, so they exercise the same
path the projection serves:

- a tariff covering the context gas day prices the route and the composition's
  ``tariff_applicability_date`` is echoed unchanged;
- a tariff gap blocks the route instead of producing a zero-cost sale option;
- a context derived from the as-of instant (no explicit ``gas_day``) uses that
  calendar gas day, never the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.projections import build_portfolio_snapshot
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CompanyTsoAccessRecord,
    MarketObservationRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.domain.route_cost.tariff_selection import (
    TARIFF_NOT_EFFECTIVE_ON_DATE,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

AS_OF = datetime(2026, 1, 31, 9, 30, tzinfo=UTC)
GAS_DAY = "2026-01-31"
ROUTE_ID = "ttf-nbp-bridge"


def _legacy_principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="fixture-principal",
        name="fixture-principal",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=(),
        roles=("ANALYST",),
        auth_method="legacy_public_token",
    )


def _session(tmp_path, name: str) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_route_inputs(
    session: Session,
    *,
    effective_from: datetime,
    effective_to: datetime | None,
) -> None:
    """Seed one contract, one BBL route, its tariff and its NBP market price."""

    session.add(
        UpstreamResourceContractRecord(
            contract_id="pool-ttf-2025",
            contract_name="Resource pool TTF supply 2025",
            resource_type="PIPELINE_IMPORT",
            delivery_point_name="TTF",
            gas_year="2025+",
            delivery_quantity_mwh_per_day=100.0,
            contract_price_gbp_mwh=30.0,
            settlement_frequency="monthly",
            upstream_payment_lag_days=20,
            screen_sale_cash_lag_days=1,
            delivery_tolerance_pct=2.0,
            nomination_tolerance_pct=1.0,
            tolerance_risk_allowance_gbp_mwh=0.1,
            annual_financing_rate_pct=6.0,
            owned_entry_capacity_mwh_per_day=None,
            owned_exit_capacity_mwh_per_day=None,
            allowed_exit_points=["NBP"],
            eligible_sale_modes=["TARGET_MARKET_SALE"],
            notes="test_fixture:not_customer_data",
            created_at_utc=AS_OF,
            updated_at_utc=AS_OF,
        )
    )
    session.add(
        RouteCandidateRecord(
            route_id=ROUTE_ID,
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
                    "gas_year": "2025+",
                    "capacity_product": "ANNUAL",
                    "firmness": "FIRM",
                    "available_capacity_mwh_per_day": 5_000,
                }
            ],
            required_entry_point_name=None,
            required_exit_point_name=None,
            required_tso_access=["BBL Company"],
            source_systems=["public_route_template", "BBL"],
            active=True,
            created_at_utc=AS_OF,
        )
    )
    session.add(
        TsoTariffRecord(
            tariff_id="jan",
            document_id="doc-jan",
            country="NL",
            tso="BBL Company",
            market_area="BBL",
            gas_year="2025+",
            point_id="bbl-forward-nl-gb",
            source_point_name="BBL Forward Flow NL to GB",
            direction="EXIT",
            capacity_product="ANNUAL",
            firmness="FIRM",
            tariff_value=2.0,
            currency="GBP",
            unit="GBP/MWh",
            effective_from=effective_from,
            effective_to=effective_to,
            tariff_status="FINAL",
            source_table="synthetic portfolio bridge table",
            source_page=None,
            source_refs=["test:portfolio-bridge-tariff"],
            manual_review_required=False,
            created_at_utc=AS_OF,
        )
    )
    session.add(
        CompanyTsoAccessRecord(
            access_id="access-bbl",
            tso="BBL Company",
            market_area="BBL",
            status="ACTIVE",
            valid_from_utc=datetime(2020, 1, 1, tzinfo=UTC),
            valid_to_utc=None,
            source_reference="test:portfolio-bridge-access",
            notes=None,
            updated_at_utc=AS_OF,
        )
    )
    session.add(
        MarketObservationRecord(
            observation_id="obs-nbp-bridge",
            market_venue="ICE_OCM",
            product="NBP day-ahead",
            price=30.0,
            unit="GBP/MWh",
            currency="GBP",
            period_start_utc=AS_OF,
            period_end_utc=AS_OF + timedelta(days=1),
            observed_at_utc=AS_OF - timedelta(minutes=5),
            source_system="ICE_OCM_Sim",
            source_reference="fixture:ICE_OCM:bridge",
            source_record_id="ice-ocm-bridge-1",
            freshness="simulated_live",
            quality_score=0.9,
            research_only=True,
            metadata_json={
                "hub": "NBP",
                "tenor": "day-ahead",
                "simulated": True,
                "source_family": "ICE_OCM",
            },
        )
    )
    session.commit()


def test_projection_passes_its_context_gas_day_and_echoes_the_composition_date(
    tmp_path,
) -> None:
    """A covering tariff is selected for the context date and echoed unchanged."""

    with _session(tmp_path, "portfolio-bridge-cover.sqlite") as session:
        _seed_route_inputs(
            session,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            effective_to=datetime(2026, 1, 31, tzinfo=UTC),
        )
        payload = build_portfolio_snapshot(
            _legacy_principal(),
            session=session,
            gas_day=GAS_DAY,
            as_of_utc=AS_OF,
        )

    resources = payload["data"]["slices"]["resources"]
    assert resources["payload"]["blockers"] == []
    assert resources["payload"]["tariff_applicability_date"] == GAS_DAY
    assert resources["row_count"] == 1
    option = resources["rows"][0]
    assert option["option_id"] == ROUTE_ID
    assert option["route_cost_gbp_mwh"] == 2.0
    assert option["route_cost_currency"] == "GBP"
    assert option["route_cost_unit"] == "GBP/MWh"
    assert option["tariff_applicability_date"] == GAS_DAY
    assert "tariff:jan" in option["route_cost_source_refs"]
    assert "test:portfolio-bridge-tariff" in option["route_cost_source_refs"]
    assert option["capacity_status"] == "KNOWN"


def test_projection_blocks_a_tariff_gap_instead_of_a_zero_cost_sale_option(
    tmp_path,
) -> None:
    """A gap is a blocker; no route edge or zero-charge option is invented."""

    with _session(tmp_path, "portfolio-bridge-gap.sqlite") as session:
        _seed_route_inputs(
            session,
            effective_from=datetime(2026, 2, 1, tzinfo=UTC),
            effective_to=datetime(2026, 2, 28, tzinfo=UTC),
        )
        payload = build_portfolio_snapshot(
            _legacy_principal(),
            session=session,
            gas_day=GAS_DAY,
            as_of_utc=AS_OF,
        )

    resources = payload["data"]["slices"]["resources"]
    assert resources["rows"] == []
    assert resources["row_count"] == 0
    assert resources["payload"]["tariff_applicability_date"] == GAS_DAY
    assert resources["payload"]["counts"]["sale_options"] == 0
    assert any(
        blocker.startswith(f"ROUTE_COST_MISSING:{ROUTE_ID}:")
        and TARIFF_NOT_EFFECTIVE_ON_DATE in blocker
        for blocker in resources["payload"]["blockers"]
    )
    assert "sale_price_gbp_mwh" not in str(resources["payload"])


def test_projection_derives_the_same_gas_day_from_the_as_of_instant(tmp_path) -> None:
    """With no explicit gas_day, the context calendar label is still used."""

    with _session(tmp_path, "portfolio-bridge-derived.sqlite") as session:
        _seed_route_inputs(
            session,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            effective_to=datetime(2026, 1, 31, tzinfo=UTC),
        )
        payload = build_portfolio_snapshot(
            _legacy_principal(),
            session=session,
            as_of_utc=AS_OF,
        )

    resources = payload["data"]["slices"]["resources"]
    assert payload["data"]["active_context"]["gas_day"] == GAS_DAY
    assert resources["payload"]["tariff_applicability_date"] == GAS_DAY
    assert resources["rows"][0]["tariff_applicability_date"] == GAS_DAY
    assert resources["rows"][0]["route_cost_gbp_mwh"] == 2.0
