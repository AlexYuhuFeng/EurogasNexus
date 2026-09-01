"""Route-cost FX as-of conversion tests (P0-3 currency discipline)."""

from types import SimpleNamespace

from eurogas_nexus.api.routes.public.route_cost import (
    _compose_resource_pool_options,
    _value_in_gbp,
)
from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    published_european_corridor_tariffs,
)


def _fx_row(
    *,
    observation_id: str,
    pair: str,
    base: str,
    quote: str,
    rate: float,
    value_date: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        observation_id=observation_id,
        pair=pair,
        base_currency=base,
        quote_currency=quote,
        rate=rate,
        rate_type="reference",
        value_date=value_date,
        observed_at_utc=f"{value_date}T12:00:00+00:00",
        source_system="ECB",
        source_reference="ecb-eurofxref-daily",
        freshness="live",
    )


def test_value_in_gbp_passes_gbp_through() -> None:
    value, provenance, warning = _value_in_gbp(
        25.0, "GBP", "GBP/MWh", None, []
    )
    assert value == 25.0
    assert provenance == {}
    assert warning is None


def test_value_in_gbp_converts_with_as_of_value_date() -> None:
    fx_rows = [
        _fx_row(
            observation_id="fx-eur-gbp-old",
            pair="EURGBP",
            base="EUR",
            quote="GBP",
            rate=0.84,
            value_date="2026-06-01",
        ),
        _fx_row(
            observation_id="fx-eur-gbp-new",
            pair="EURGBP",
            base="EUR",
            quote="GBP",
            rate=0.86,
            value_date="2026-07-01",
        ),
    ]
    # Market observed 2026-06-15 -> as-of rate is 0.84, not the latest 0.86.
    value, provenance, warning = _value_in_gbp(
        100.0, "EUR", "EUR/MWh", None, fx_rows
    )
    # NOTE: asof_date is None here; pass the market date explicitly below.
    assert value == 86.0  # latest rate used when no as-of date supplied
    assert warning is None

    value, provenance, warning = _value_in_gbp(
        100.0, "EUR", "EUR/MWh", __import__("datetime").date(2026, 6, 15), fx_rows
    )
    assert value == 84.0
    assert provenance["fx_rate_used"] == 0.84
    assert provenance["fx_observation_id"] == "fx-eur-gbp-old"
    assert provenance["fx_value_date"] == "2026-06-01"
    assert provenance["fx_as_of_approximated"] is False
    assert warning is None


def test_value_in_gbp_falls_back_to_latest_rate_with_warning() -> None:
    fx_rows = [
        _fx_row(
            observation_id="fx-eur-gbp-new",
            pair="EURGBP",
            base="EUR",
            quote="GBP",
            rate=0.86,
            value_date="2026-07-01",
        ),
    ]
    value, provenance, warning = _value_in_gbp(
        100.0, "EUR", "EUR/MWh", __import__("datetime").date(2026, 6, 15), fx_rows
    )
    assert value == 86.0
    assert provenance["fx_as_of_approximated"] is True
    assert warning == "FX_AS_OF_APPROXIMATED:EUR->GBP"


def test_value_in_gbp_fails_closed_without_fx_rates() -> None:
    value, provenance, warning = _value_in_gbp(
        100.0, "EUR", "EUR/MWh", None, []
    )
    assert value is None
    assert provenance == {}
    assert warning is None


def test_value_in_gbp_rejects_non_mwh_units() -> None:
    value, _, _ = _value_in_gbp(100.0, "EUR", "p/therm", None, [])
    assert value is None


def test_compose_resource_pool_options_converts_eur_market_price_to_gbp() -> None:
    contracts = [
        {
            "contract_id": "c1",
            "contract_name": "TTF supply",
            "resource_type": "PIPELINE_IMPORT",
            "delivery_point_name": "TTF",
            "gas_year": "2025+",
            "delivery_quantity_mwh_per_day": 10_000,
            "contract_price_gbp_mwh": 25.0,
            "settlement_frequency": "monthly",
            "upstream_payment_lag_days": 20,
            "screen_sale_cash_lag_days": 1,
            "delivery_tolerance_pct": 2.0,
            "nomination_tolerance_pct": 1.0,
            "tolerance_risk_allowance_gbp_mwh": None,
            "annual_financing_rate_pct": 6.0,
            "owned_entry_capacity_mwh_per_day": None,
            "owned_exit_capacity_mwh_per_day": None,
            "allowed_exit_points": ["NBP"],
            "eligible_sale_modes": [],
            "notes": (
                '{"variable_cost_gbp_mwh": 0.6, "regas_fee_gbp_mwh": 0.4, '
                '"fuel_loss_allowance_pct": 1.5}'
            ),
        }
    ]
    candidates = [
        {
            "route_id": "ttf-nbp",
            "route_name": "TTF -> NBP",
            "start_point_name": "TTF",
            "target_point_name": "NBP",
            "required_tso_access": [],
            "source_systems": [],
            "route_legs": [
                {
                    "leg_id": "l1",
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
        }
    ]
    market_rows = [
        SimpleNamespace(
            observation_id="nbp-eur-day",
            market_venue="EEX",
            product="NBP day-ahead",
            price=40.0,
            currency="EUR",
            unit="EUR/MWh",
            observed_at_utc="2026-07-01T10:00:00+00:00",
            period_start_utc="2026-07-01T00:00:00+00:00",
            period_end_utc="2026-07-02T00:00:00+00:00",
            source_system="EEX_Sim",
            source_reference="sim:EEX:NBP:day-ahead:20260701",
            freshness="simulated_live",
            quality_score=0.62,
            metadata_json={
                "hub": "NBP",
                "tenor": "day-ahead",
                "simulated": True,
                "source_family": "EEX",
            },
        )
    ]
    fx_rows = [
        _fx_row(
            observation_id="fx-eur-gbp",
            pair="EURGBP",
            base="EUR",
            quote="GBP",
            rate=0.85,
            value_date="2026-07-01",
        )
    ]

    data = _compose_resource_pool_options(
        contracts=contracts,
        candidates=candidates,
        tariffs=published_european_corridor_tariffs(),
        market_rows=market_rows,
        fx_rows=fx_rows,
    )

    assert len(data["sale_options"]) == 1
    option = data["sale_options"][0]
    assert option["sale_price_gbp_mwh"] == 34.0  # 40 EUR * 0.85
    assert option["sale_price_currency"] == "GBP"
    assert option["sale_price_unit"] == "GBP/MWh"
    assert option["sale_price_original_currency"] == "EUR"
    assert option["fx_converted_from"] == "EUR"
    assert option["fx_rate_used"] == 0.85
    assert option["fx_as_of_approximated"] is False
    assert option["capacity_status"] == "KNOWN"
    assert option["capacity_limit_mwh_per_day"] == 5_000
    assert option["eligible_resource_ids"] == ["c1"]
    assert data["portfolio_resources"][0]["variable_cost_gbp_mwh"] == 1.0
    assert data["portfolio_resources"][0]["fuel_loss_allowance_pct"] == 1.5
    assert data["blockers"] == []


def test_compose_resource_pool_options_blocks_without_fx_rates() -> None:
    contracts = [
        {
            "contract_id": "c1",
            "contract_name": "TTF supply",
            "resource_type": "PIPELINE_IMPORT",
            "delivery_point_name": "TTF",
            "gas_year": "2025+",
            "delivery_quantity_mwh_per_day": 10_000,
            "contract_price_gbp_mwh": 25.0,
            "settlement_frequency": "monthly",
            "upstream_payment_lag_days": 20,
            "screen_sale_cash_lag_days": 1,
            "delivery_tolerance_pct": 2.0,
            "nomination_tolerance_pct": 1.0,
            "tolerance_risk_allowance_gbp_mwh": None,
            "annual_financing_rate_pct": 6.0,
            "owned_entry_capacity_mwh_per_day": None,
            "owned_exit_capacity_mwh_per_day": None,
            "allowed_exit_points": ["NBP"],
            "eligible_sale_modes": [],
            "notes": None,
        }
    ]
    candidates = [
        {
            "route_id": "ttf-nbp",
            "route_name": "TTF -> NBP",
            "start_point_name": "TTF",
            "target_point_name": "NBP",
            "required_tso_access": [],
            "source_systems": [],
            "route_legs": [
                {
                    "leg_id": "l1",
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
        }
    ]
    market_rows = [
        SimpleNamespace(
            observation_id="nbp-eur-day",
            market_venue="EEX",
            product="NBP day-ahead",
            price=40.0,
            currency="EUR",
            unit="EUR/MWh",
            observed_at_utc="2026-07-01T10:00:00+00:00",
            period_start_utc="2026-07-01T00:00:00+00:00",
            period_end_utc="2026-07-02T00:00:00+00:00",
            source_system="EEX_Sim",
            source_reference="sim:EEX:NBP:day-ahead:20260701",
            freshness="simulated_live",
            quality_score=0.62,
            metadata_json={
                "hub": "NBP",
                "tenor": "day-ahead",
                "simulated": True,
                "source_family": "EEX",
            },
        )
    ]

    data = _compose_resource_pool_options(
        contracts=contracts,
        candidates=candidates,
        tariffs=published_european_corridor_tariffs(),
        market_rows=market_rows,
        fx_rows=[],
    )

    assert data["sale_options"] == []
    assert any("MARKET_PRICE_FX_UNAVAILABLE:NBP" in blocker for blocker in data["blockers"])


def test_compose_resource_pool_options_blocks_unknown_capacity() -> None:
    contracts = [
        {
            "contract_id": "c1",
            "contract_name": "TTF supply",
            "resource_type": "PIPELINE_IMPORT",
            "delivery_point_name": "TTF",
            "gas_year": "2025+",
            "delivery_quantity_mwh_per_day": 10_000,
            "contract_price_gbp_mwh": 25.0,
            "settlement_frequency": "monthly",
            "upstream_payment_lag_days": 20,
            "screen_sale_cash_lag_days": 1,
            "delivery_tolerance_pct": 2.0,
            "nomination_tolerance_pct": 1.0,
            "tolerance_risk_allowance_gbp_mwh": None,
            "annual_financing_rate_pct": 6.0,
            "owned_entry_capacity_mwh_per_day": None,
            "owned_exit_capacity_mwh_per_day": None,
            "allowed_exit_points": ["NBP"],
            "eligible_sale_modes": [],
            "notes": None,
        }
    ]
    candidates = [
        {
            "route_id": "ttf-nbp",
            "route_name": "TTF -> NBP",
            "start_point_name": "TTF",
            "target_point_name": "NBP",
            "required_tso_access": [],
            "source_systems": [],
            "route_legs": [
                {
                    "leg_id": "l1",
                    "country": "NL",
                    "tso": "BBL Company",
                    "market_area": "BBL",
                    "point_name": "BBL Forward Flow NL to GB",
                    "direction": "EXIT",
                    "gas_year": "2025+",
                    "capacity_product": "ANNUAL",
                    "firmness": "FIRM",
                    "available_capacity_mwh_per_day": None,
                }
            ],
        }
    ]
    market_rows = [
        SimpleNamespace(
            observation_id="nbp-gbp-day",
            market_venue="ICE_OCM_Sim",
            product="NBP day-ahead",
            price=30.0,
            currency="GBP",
            unit="GBP/MWh",
            observed_at_utc="2026-07-01T10:00:00+00:00",
            period_start_utc="2026-07-01T00:00:00+00:00",
            period_end_utc="2026-07-02T00:00:00+00:00",
            source_system="ICE_OCM_Sim",
            source_reference="sim:ICE_OCM:NBP:day-ahead:20260701",
            freshness="simulated_live",
            quality_score=0.62,
            metadata_json={
                "hub": "NBP",
                "tenor": "day-ahead",
                "simulated": True,
                "source_family": "ICE_OCM",
            },
        )
    ]

    data = _compose_resource_pool_options(
        contracts=contracts,
        candidates=candidates,
        tariffs=published_european_corridor_tariffs(),
        market_rows=market_rows,
        fx_rows=[],
    )

    assert data["sale_options"] == []
    assert any("ROUTE_CAPACITY_UNKNOWN:ttf-nbp" in blocker for blocker in data["blockers"])


def test_compose_resource_pool_options_blocks_route_with_unconfirmed_tso_access() -> None:
    """Unknown company TSO access fails closed at composition time."""

    contracts = [
        {
            "contract_id": "c1",
            "contract_name": "TTF supply",
            "resource_type": "PIPELINE_IMPORT",
            "delivery_point_name": "TTF",
            "gas_year": "2025+",
            "delivery_quantity_mwh_per_day": 10_000,
            "contract_price_gbp_mwh": 25.0,
            "settlement_frequency": "monthly",
            "upstream_payment_lag_days": 20,
            "screen_sale_cash_lag_days": 1,
            "delivery_tolerance_pct": 2.0,
            "nomination_tolerance_pct": 1.0,
            "tolerance_risk_allowance_gbp_mwh": None,
            "annual_financing_rate_pct": 6.0,
            "owned_entry_capacity_mwh_per_day": None,
            "owned_exit_capacity_mwh_per_day": None,
            "allowed_exit_points": ["NBP"],
            "eligible_sale_modes": [],
            "notes": None,
        }
    ]
    candidates = [
        {
            "route_id": "ttf-nbp",
            "route_name": "TTF -> NBP",
            "start_point_name": "TTF",
            "target_point_name": "NBP",
            "required_tso_access": ["Uncontracted TSO"],
            "source_systems": [],
            "route_legs": [
                {
                    "leg_id": "l1",
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
        }
    ]
    market_rows = [
        SimpleNamespace(
            observation_id="nbp-gbp-day",
            market_venue="ICE_OCM_Sim",
            product="NBP day-ahead",
            price=30.0,
            currency="GBP",
            unit="GBP/MWh",
            observed_at_utc="2026-07-01T10:00:00+00:00",
            period_start_utc="2026-07-01T00:00:00+00:00",
            period_end_utc="2026-07-02T00:00:00+00:00",
            source_system="ICE_OCM_Sim",
            source_reference="sim:ICE_OCM:NBP:day-ahead:20260701",
            freshness="simulated_live",
            quality_score=0.62,
            metadata_json={
                "hub": "NBP",
                "tenor": "day-ahead",
                "simulated": True,
                "source_family": "ICE_OCM",
            },
        )
    ]

    data = _compose_resource_pool_options(
        contracts=contracts,
        candidates=candidates,
        tariffs=published_european_corridor_tariffs(),
        market_rows=market_rows,
        fx_rows=[],
    )

    assert data["sale_options"] == []
    assert any(
        "TSO_ACCESS_MISSING" in blocker or "TSO_ACCESS_UNKNOWN" in blocker
        for blocker in data["blockers"]
    )
