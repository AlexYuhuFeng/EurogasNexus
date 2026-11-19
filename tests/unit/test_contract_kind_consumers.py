"""Contract kinds in the book's consumers: the resource pool's index cost, the map's cargoes."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from eurogas_nexus.application.map_situation import _confirmed_cargoes
from eurogas_nexus.application.resource_pool import contracts_at_index_price
from eurogas_nexus.domain.contracts import kinds
from eurogas_nexus.domain.contracts.examples import cargo_terms, tender_terms

TODAY = date(2026, 11, 19)


def _tender(**overrides):
    terms = kinds.canonical_terms(
        kinds.parse_terms("UPSTREAM_TENDER", {**tender_terms(TODAY), **overrides})
    )
    return {
        "contract_id": "t",
        "contract_kind": "UPSTREAM_TENDER",
        "kind_terms": terms,
        "delivery_point_name": "NBP",
        "contract_price_gbp_mwh": -0.1365,
        "contract_price_currency": "GBP",
    }


def test_index_tender_costs_the_index_print_plus_its_differential() -> None:
    prices = {
        "NBP": {
            "price": 84.5,
            "currency": "GBP",
            "unit": "GBp/th",
            "simulated": True,
            "source_reference": "market_observation:x",
        }
    }
    out, blockers, warnings = contracts_at_index_price([_tender()], prices)
    assert blockers == []
    # 84.50 - 0.40 p/th = 84.10 p/th = 28.70 GBP/MWh.
    assert round(out[0]["contract_price_gbp_mwh"], 2) == round(84.1 * 34.1214 / 100, 2)
    assert out[0]["contract_cost_simulated"] is True
    assert warnings == ["CONTRACT_INDEX_PRICED:t:NBP"]


def test_missing_index_print_and_slope_formula_are_blockers_not_estimates() -> None:
    _out, blockers, _ = contracts_at_index_price([_tender()], {})
    assert blockers == ["CONTRACT_INDEX_PRICE_MISSING:t"]
    cargo = {
        "contract_id": "c",
        "contract_kind": "LNG_CARGO",
        "kind_terms": kinds.canonical_terms(kinds.parse_terms("LNG_CARGO", cargo_terms(TODAY))),
        "delivery_point_name": "Gate terminal",
    }
    out, blockers, _ = contracts_at_index_price([cargo], {})
    assert out == [] and blockers == ["CONTRACT_FORMULA_PRICED:c"]
    gsa = {"contract_id": "g", "contract_kind": "SUPPLY_GSA", "kind_terms": None}
    assert contracts_at_index_price([gsa], {})[0] == [gsa]


def test_des_confirmation_is_an_expected_cargo_unless_the_feed_holds_it() -> None:
    record = SimpleNamespace(
        contract_id="c1",
        contract_name="CN-07",
        contract_kind="LNG_CARGO",
        kind_terms=cargo_terms(TODAY),
        book_id="b",
    )
    locator = SimpleNamespace(find=lambda name: {"lon": 4.0, "lat": 51.9} if name else None)
    now = datetime(2026, 11, 19, tzinfo=UTC)
    [cargo] = _confirmed_cargoes([record], [], locator, now)
    assert cargo["destination_terminal"] == "Gate terminal"
    assert cargo["eta_utc"].startswith(cargo_terms(TODAY)["window_start"])
    assert cargo["own"] is True and cargo["status"] == "contracted"
    linked = SimpleNamespace(
        **{**vars(record), "kind_terms": {**cargo_terms(TODAY), "lng_cargo_id": "v1"}}
    )
    assert _confirmed_cargoes([linked], [{"cargo_id": "v1"}], locator, now) == []
    fob = SimpleNamespace(
        **{**vars(record), "kind_terms": {**cargo_terms(TODAY), "delivery_term": "FOB"}}
    )
    assert _confirmed_cargoes([fob], [], locator, now) == []
