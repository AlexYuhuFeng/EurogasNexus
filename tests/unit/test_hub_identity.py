"""A hub is resolved by rule or reported as unresolved; it is never guessed or defaulted."""

from __future__ import annotations

import pytest

from eurogas_nexus.application.position_inputs import hub_from_text
from eurogas_nexus.domain.ontology.identity import resolve_hub


@pytest.mark.parametrize(
    ("text", "hub", "basis"),
    [
        ("TTF", "TTF", "code"),
        ("ttf", "TTF", "code"),
        ("NBP Day-Ahead", "NBP", "code"),
        ("Kestrel supply (TTF)", "TTF", "code"),
        ("ETF", "ETF", "code"),
        ("GTF", "GTF", "code"),
        ("Gaspoint Nordic", "ETF", "alias"),
        ("THE Day-Ahead", "THE", "code"),
        ("Haldor supply (Easington)", "NBP", "delivery_point"),
        ("St Fergus", "NBP", "delivery_point"),
        ("Zeebrugge terminal", "ZTP", "delivery_point"),
    ],
)
def test_a_code_an_alias_or_a_known_delivery_point_resolves(text, hub, basis):
    resolution = resolve_hub(text)
    assert (resolution.hub, resolution.basis) == (hub, basis)


@pytest.mark.parametrize(
    "text",
    [
        "Rotterdam, Netherlands",  # contains the letters THE: once became the German hub
        "The Netherlands",
        "the hub",
        "Bethel",
        "UNKNOWN_POINT",
        "Easingtonn",  # a misspelling: once silently NBP
        "TTF/NBP spread",  # two hubs: ambiguous
        "Henry Hub Natural Gas Spot Price",  # a hub, but not one of this registry's codes
        "",
        None,
    ],
)
def test_anything_else_is_unresolved_never_a_default(text):
    resolution = resolve_hub(text)
    assert resolution.hub is None and resolution.basis == "unresolved"
    assert hub_from_text(text or "") is None


def test_a_deployments_own_mapping_is_consulted_first():
    points = {"KESTREL LANDFALL": "TTF"}
    assert resolve_hub("Kestrel landfall", points=points).basis == "mapping"
    assert resolve_hub("Kestrel landfall").hub is None


def test_an_unmapped_contract_is_left_out_and_said_so(tmp_path, monkeypatch):
    from datetime import UTC, date, datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import eurogas_nexus.db.models  # noqa: F401
    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models.route_cost import UpstreamResourceContractRecord

    url = f"sqlite+pysqlite:///{tmp_path / 'store.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    now = datetime(2026, 11, 12, tzinfo=UTC)

    def contract(contract_id: str, point: str) -> UpstreamResourceContractRecord:
        values = {
            column.name: (
                now if "DateTime" in type(column.type).__name__
                else 1.0 if type(column.type).__name__ in {"Float", "Numeric"}
                else 1 if type(column.type).__name__ == "Integer"
                else False if type(column.type).__name__ == "Boolean"
                else [] if type(column.type).__name__ == "JSON"
                else "x"
            )
            for column in UpstreamResourceContractRecord.__table__.columns
            if not column.nullable and column.default is None
        }
        values.update(contract_id=contract_id, delivery_point_name=point, gas_year="2026/27",
                      delivery_quantity_mwh_per_day=1000.0, contract_price_gbp_mwh=30.0)
        return UpstreamResourceContractRecord(**values)

    with Session(engine) as session:
        session.add(contract("good", "Easington"))
        session.add(contract("lost", "Rotterdam, Netherlands"))
        session.commit()

    inputs = ladder_inputs(firm_caller(), date(2026, 11, 12), date(2026, 11, 12),
                           date(2027, 9, 30))
    assert [leg.reference for leg in inputs.legs] == ["good"]
    assert inputs.legs[0].hub == "NBP"
    assert any("lost" in w and "does not name a hub" in w for w in inputs.warnings)


# --- ETF is the Danish exchange hub, never TTF; ETF and GTF are distinct (2026-11-15) ---


@pytest.mark.parametrize("text", ["ETF", "ETF Day-Ahead", "Danish supply (ETF)", "etf"])
def test_etf_names_the_danish_hub_not_ttf(text):
    from eurogas_nexus.domain.ontology.markets import market

    resolution = resolve_hub(text)
    assert resolution.hub == "ETF"
    assert market("ETF").country == "DK" and market("TTF").country == "NL"


def test_ttf_never_resolves_from_danish_text():
    for text in ("ETF", "Exchange Transfer Facility", "GTF", "Gaspoint Nordic"):
        assert resolve_hub(text, points={"EXCHANGE TRANSFER FACILITY": "ETF"}).hub != "TTF"


def test_etf_and_gtf_stay_distinct():
    from eurogas_nexus.domain.ontology.markets import market

    assert resolve_hub("GTF").hub == "GTF"
    assert market("ETF") is not market("GTF")
    assert resolve_hub("ETF/GTF transfer").hub is None  # two hubs named: ambiguous, not merged
    assert hub_from_text("Exchange Transfer Facility") is None  # free text: intake maps it


def test_contract_intake_names_keep_the_danish_hubs_apart():
    from eurogas_nexus.application.contract_intake import _HUBS

    points = {name.upper(): code for code, names in _HUBS.items() for name in names}
    assert resolve_hub("Exchange Transfer Facility", points=points).hub == "ETF"
    assert resolve_hub("Gas Transfer Facility", points=points).hub == "GTF"
    assert resolve_hub("Title Transfer Facility", points=points).hub == "TTF"


def test_a_danish_zone_prices_at_etf():
    from eurogas_nexus.application.desk_text import hub_for_zone

    assert hub_for_zone("DK") == "ETF"
