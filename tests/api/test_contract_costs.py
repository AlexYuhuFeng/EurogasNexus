"""Cost reads for the opportunity evaluators: contract first, public tariff, assumption, missing."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import contract_costs
from eurogas_nexus.application.caller import firm_caller
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import LngTerminalTermsRecord, UpstreamResourceContractRecord

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def _contract(contract_id, **overrides):
    values = dict(
        contract_id=contract_id,
        contract_name=contract_id,
        resource_type="PIPELINE_IMPORT",
        delivery_point_name="TTF",
        gas_year="2026/27",
        delivery_quantity_mwh_per_day=1000.0,
        contract_price_gbp_mwh=31.5,
        contract_price_currency="EUR",
        settlement_frequency="monthly",
        upstream_payment_lag_days=20,
        screen_sale_cash_lag_days=1,
        delivery_tolerance_pct=2.0,
        nomination_tolerance_pct=1.0,
        annual_financing_rate_pct=5.0,
        allowed_exit_points=["TTF"],
        eligible_sale_modes=[],
        created_at_utc=NOW,
        updated_at_utc=NOW,
    )
    values.update(overrides)
    return UpstreamResourceContractRecord(**values)


@pytest.fixture
def session(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'costs.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    with Session(engine) as session:
        session.add(_contract("gsa-fixed"))
        session.add(_contract("gsa-index", notes='{"index_basis": "TTF month-ahead"}'))
        session.add(
            _contract(
                "held-exit",
                owned_exit_capacity_mwh_per_day=5000.0,
                allowed_exit_points=["THE"],
            )
        )
        session.add(
            LngTerminalTermsRecord(
                terminal_id="gate",
                name="Gate terminal",
                hub="TTF",
                regas_tariff_per_mwh=1.20,
                source_note="the firm's TUA",
                updated_by="desk",
                updated_at_utc=NOW,
            )
        )
        session.commit()
        yield session


def test_supply_price_reads_the_contract_and_names_what_is_not_recorded(session):
    caller = firm_caller(session=session)
    fixed = contract_costs.supply_price(session, caller, contract_id="gsa-fixed", period="2027-01")
    assert fixed["value"] == 31.5 and fixed["unit"] == "EUR/MWh"
    assert (fixed["basis"], fixed["input_class"]) == ("contract_variable", "contract")
    named = contract_costs.supply_price(session, caller, contract_id="gsa-index", period="2027-01")
    assert named["basis"] == "missing" and "formula is not recorded" in named["note"]
    gone = contract_costs.supply_price(session, caller, contract_id="nope", period="2027-01")
    assert gone["basis"] == "missing"


def test_held_capacity_is_sunk_and_an_unheld_leg_without_tariffs_is_missing(session):
    caller = firm_caller(session=session)
    held = contract_costs.transport_leg_cost(
        session, caller, from_point="TTF", to_point="THE", gas_day=date(2027, 1, 5)
    )
    assert (held["value"], held["basis"]) == (0.0, "contract_sunk")
    unheld = contract_costs.transport_leg_cost(
        session, caller, from_point="TTF", to_point="NBP", gas_day=date(2027, 1, 5)
    )
    assert unheld["basis"] == "missing" and unheld["value"] is None


def test_regas_reads_the_firms_terminal_terms_and_storage_needs_an_assumption(session):
    caller = firm_caller(session=session)
    regas = contract_costs.regas_cost(
        session, caller, terminal="gate", month="2027-01", cargo_mwh=1_000_000
    )
    assert regas["basis"] == "contract_variable"
    assert regas["value"] == pytest.approx(1.20, abs=0.01)
    assert regas["currency"] == "EUR"
    storage = contract_costs.storage_cost(session, caller, facility="Bergermeer", period="2027-01")
    assert storage["basis"] == "missing" and "assumption" in storage["note"]
    for answer in (regas, storage):
        assert set(answer) == {
            "value",
            "unit",
            "currency",
            "basis",
            "source_ref",
            "as_of",
            "input_class",
            "note",
        }
