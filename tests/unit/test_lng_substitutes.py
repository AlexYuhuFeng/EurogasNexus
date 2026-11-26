"""LNG-4 substitute supply read from the book, and the one transport-cost function.

``_transport_cost`` answers capacity the firm holds first (sunk), then the public tariff,
else "not held"; ``load_substitutes`` turns the book's upstream swing and the hubs it prices
into substitute sources for a short obligation, leaving out (and naming) any source whose
transport or price the data does not hold. Every price and rate is test data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import contract_costs
from eurogas_nexus.application.lng_demurrage import FxBook, FxChoice
from eurogas_nexus.application.lng_substitutes import _transport_cost, load_substitutes
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import UpstreamResourceContractRecord
from eurogas_nexus.domain.lng.disruption import Obligation

DAY = date(2027, 1, 24)
NOW = datetime(2027, 1, 20, 9, tzinfo=UTC)
FX = FxBook(
    FxChoice(),
    DAY,
    [
        {
            "source_system": "ECB",
            "pair": "EURGBP",
            "rate": 0.80,
            "value_date": "2027-01-19",
            "rate_type": "reference",
        }
    ],
)
CEPSA = Obligation("cepsa", "Cepsa", "Huelva", "PVB", DAY, date(2027, 2, 12), 50_000.0)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 's.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as made:
        yield made
    engine.dispose()


def contract(contract_id: str, point: str, **values) -> UpstreamResourceContractRecord:
    base = {
        "contract_id": contract_id,
        "contract_name": contract_id.title(),
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": point,
        "gas_year": "2026",
        "delivery_quantity_mwh_per_day": 100_000.0,
        "contract_price_gbp_mwh": 24.0,
        "contract_price_currency": "GBP",
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 10.0,
        "nomination_tolerance_pct": 1.0,
        "tolerance_risk_allowance_gbp_mwh": None,
        "annual_financing_rate_pct": 5.0,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": [point],
        "eligible_sale_modes": ["LOCAL_MARKET_SALE"],
        "notes": None,
        "book_id": "lng-book",
        "created_at_utc": NOW,
        "updated_at_utc": NOW,
    }
    return UpstreamResourceContractRecord(**{**base, **values})


# ------------------------------------------------------------------------ _transport_cost


def test_no_transport_is_needed_at_the_same_point(session):
    cost = _transport_cost(session, "pvb", "PVB", DAY, FX)
    assert (cost.eur_mwh, cost.basis, cost.source) == (0.0, "same_point", "no transport needed")


def test_a_public_tariff_in_another_currency_is_converted_and_named(session, monkeypatch):
    monkeypatch.setattr(
        contract_costs,
        "transport_leg_cost",
        lambda *a, **k: {
            "value": 0.96,
            "currency": "GBP",
            "basis": "public_tariff",
            "source_ref": "tso:entry-exit",
        },
    )
    cost = _transport_cost(session, "PEG", "PVB", DAY, FX)
    assert cost.eur_mwh == pytest.approx(1.20)
    assert (cost.basis, cost.source) == ("public_tariff", "public tariff: tso:entry-exit")
    assert cost.fx["source"] == "ECB" and cost.fx["rate_date"] == "2027-01-19"
    assert cost.tried == (
        "capacity the firm holds on the leg",
        "public tariff on the cheapest proven route",
    )


def test_a_tariff_not_held_or_not_converted_is_missing_never_zero(session, monkeypatch):
    monkeypatch.setattr(
        contract_costs,
        "transport_leg_cost",
        lambda *a, **k: {"value": None, "source_ref": None, "note": "no proven route"},
    )
    cost = _transport_cost(session, "TTF", "PVB", DAY, FX)
    assert (cost.eur_mwh, cost.basis, cost.note) == (None, "missing", "no proven route")
    monkeypatch.setattr(
        contract_costs,
        "transport_leg_cost",
        lambda *a, **k: {"value": 1.0, "currency": "USD", "source_ref": "tso:x"},
    )
    unconverted = _transport_cost(session, "TTF", "PVB", DAY, FX)
    assert unconverted.eur_mwh is None and "not converted" in unconverted.note


def test_capacity_the_firm_holds_on_the_leg_is_sunk(session):
    session.add(
        contract(
            "peg-exit",
            "PEG",
            owned_exit_capacity_mwh_per_day=60_000.0,
            allowed_exit_points=["PVB"],
        )
    )
    session.flush()
    cost = _transport_cost(session, "PEG", "PVB", DAY, FX)
    assert (cost.eur_mwh, cost.basis) == (0.0, "contract_sunk")
    assert cost.source == "capacity the firm holds (sunk): upstream_resource_contract:peg-exit"


# ------------------------------------------------------------------------ load_substitutes


def test_upstream_swing_and_hub_gas_become_substitute_sources(session, monkeypatch):
    session.add(contract("medgaz", "PVB", contract_price_currency="EUR"))
    session.add(contract("no-swing", "PVB", delivery_tolerance_pct=0.0))
    session.add(contract("retired", "PVB", retired_at_utc=NOW))
    session.add(contract("other-book", "PVB", book_id="elsewhere"))
    session.add(contract("nbp", "NBP", gas_year="2026", contract_price_gbp_mwh=24.0))
    session.flush()

    def leg(_session, _caller, *, from_point, to_point, gas_day):
        if from_point.upper() == "PEG":
            return {"value": 1.20, "currency": "EUR", "basis": "public_tariff", "source_ref": "t"}
        return {"value": None, "source_ref": None, "note": f"no route from {from_point}"}

    monkeypatch.setattr(contract_costs, "transport_leg_cost", leg)
    prices = {("PVB", "2027-01"): 31.0, ("PEG", "2027-01"): 30.20, ("TTF", "2027-01"): 30.40}
    out = load_substitutes(
        session,
        "lng-book",
        [CEPSA],
        prices,
        premium_eur_mwh=0.25,
        premium_source="desk short-notice premium",
        fx=FX,
        today=NOW.date(),
    )
    by_id = {s.source_id: s for s in out.sources}
    assert set(by_id) == {"hub:PEG:cepsa", "hub:PVB:cepsa", "upstream:medgaz:cepsa"}

    peg = by_id["hub:PEG:cepsa"]
    assert (peg.kind, peg.point, peg.price_hub, peg.premium_eur_mwh, peg.transport_eur_mwh) == (
        "hub",
        "PVB",
        "PEG",
        0.25,
        1.20,
    )
    assert (peg.start, peg.end, peg.max_mwh_per_day) == (DAY, date(2027, 2, 12), 50_000.0)
    assert peg.sources["transport"] == "public tariff: t"
    assert by_id["hub:PVB:cepsa"].transport_eur_mwh == 0.0

    swing = by_id["upstream:medgaz:cepsa"]
    # 10 % tolerance on 100,000 MWh/d; the stated EUR price; delivered at PVB already.
    assert (swing.kind, swing.max_mwh_per_day, swing.price_eur_mwh) == ("upstream", 10_000, 24.0)
    assert swing.transport_eur_mwh == 0.0
    assert swing.sources["gas"].startswith("upstream_resource_contract:medgaz")
    # The gas year 2026 runs to 30 Sep 2027, so the whole obligation window is covered.
    assert swing.end == date(2027, 2, 12)

    # TTF and NBP gas have no transport cost held to PVB: left out, and said so.
    assert any(w.startswith("hub gas from TTF to Cepsa at PVB left out") for w in out.warnings)
    assert any(w.startswith("swing of Nbp to Cepsa left out") for w in out.warnings)


def test_a_contract_price_in_gbp_is_converted_at_the_fx_choice(session, monkeypatch):
    session.add(contract("peg-gbp", "PEG", allowed_exit_points=["PVB"]))
    session.flush()
    monkeypatch.setattr(
        contract_costs,
        "transport_leg_cost",
        lambda *a, **k: {
            "value": 0.0,
            "currency": "EUR",
            "basis": "public_tariff",
            "source_ref": "t",
        },
    )
    out = load_substitutes(
        session,
        "lng-book",
        [CEPSA],
        {},
        premium_eur_mwh=0.0,
        premium_source="none",
        fx=FX,
        today=NOW.date(),
    )
    (swing,) = out.sources
    assert swing.price_eur_mwh == pytest.approx(24.0 / 0.80)
    assert "ECB" in swing.sources["fx"]


def test_nothing_short_means_no_substitutes():
    assert (
        load_substitutes(
            None, "b", [], {}, premium_eur_mwh=0, premium_source="", fx=FX, today=DAY
        ).sources
        == []
    )
