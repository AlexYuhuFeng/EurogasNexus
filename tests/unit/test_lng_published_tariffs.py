"""Published LNG terminal tariffs: the shipped reference file, period selection and conversions."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal as D
from importlib import resources

import pytest

from eurogas_nexus.domain.lng import published_tariffs as pt

#: The terminals the desk asked to see (Isle of Grain to Mukran).
EXPECTED = {
    "grain-lng",
    "south-hook-lng",
    "dragon-lng",
    "gate-terminal",
    "eemshaven-lng",
    "zeebrugge",
    "dunkerque-lng",
    "montoir",
    "fos-cavaou",
    "fos-tonkin",
    "wilhelmshaven:fsru-1",
    "wilhelmshaven:fsru-2",
    "brunsbuttel",
    "mukran",
}
JAN_27 = date(2027, 1, 1)
CARGO_MWH = D("1055055.8526")


def _payload() -> dict:
    text = resources.files("eurogas_nexus.reference_data").joinpath(pt.RESOURCE).read_text("utf-8")
    return json.loads(text)


def test_the_reference_file_covers_every_terminal_with_a_source_for_each_figure():
    terminals = pt.published_terminals()
    assert {t.terminal_id for t in terminals} == EXPECTED
    for terminal in terminals:
        assert terminal.hub in {"NBP", "TTF", "ZTP", "PEG", "THE"}
        for charge in terminal.charges:
            assert charge.source_url.startswith("https://") and charge.terms
            assert charge.read_on <= date(2026, 11, 26)
            assert charge.status in {"FINAL", "INDICATIVE"}
        if not any(c.kind == "regas" for c in terminal.charges):
            # No price for a new booking: said, never invented.
            assert terminal.not_published or terminal.permission_operator


def test_a_gated_operator_holds_no_figure():
    zeebrugge = pt.published_terminal("zeebrugge")
    assert zeebrugge.permission_operator == "fluxys_lng" and zeebrugge.charges == ()
    payload = _payload()
    row = next(t for t in payload["terminals"] if t["terminal_id"] == "zeebrugge")
    row["charges"] = [
        next(t for t in payload["terminals"] if t["terminal_id"] == "montoir")["charges"][0]
    ]
    with pytest.raises(pt.PublishedTariffError):
        pt.parse_published(payload)


def test_a_figure_without_an_https_source_or_with_an_unknown_status_is_refused():
    payload = _payload()
    charge = next(t for t in payload["terminals"] if t["terminal_id"] == "montoir")["charges"][0]
    for broken in ({"source_url": "http://example.org"}, {"status": "DRAFT"}):
        bad = json.loads(json.dumps(payload))
        target = next(t for t in bad["terminals"] if t["terminal_id"] == "montoir")
        target["charges"][0] = {**charge, **broken}
        with pytest.raises(pt.PublishedTariffError):
            pt.parse_published(bad)


def test_montoir_spot_regas_for_a_january_cargo_from_the_cre_grid():
    montoir = pt.published_terminal("montoir")
    uses = pt.select(montoir, "regas", JAN_27, "spot")
    assert all(not use.carried_forward for use in uses)
    # 90,000 per berthing + (0.662 + 0.053) EUR/MWh unloaded.
    total = pt.regas_total(uses, CARGO_MWH)
    assert total == D(90_000) + (D("0.662") + D("0.053")) * CARGO_MWH
    assert pt.weakest_status(uses) == "FINAL"
    term = pt.regas_total(pt.select(montoir, "regas", JAN_27, "term"), CARGO_MWH)
    assert term > total  # the base (term) TQD is dearer than the spot one
    assert pt.percent(pt.select(montoir, "gas_in_kind", JAN_27)) == D("0.5")


def test_an_ended_period_is_carried_forward_and_marked_indicative():
    whv = pt.published_terminal("wilhelmshaven:fsru-1")
    uses = pt.select(whv, "regas", JAN_27, "spot")
    assert uses and all(use.carried_forward for use in uses)
    assert pt.weakest_status(uses) == "INDICATIVE"
    assert pt.regas_total(uses, D(1000)) == D("3.45") * 1000
    # Gas in kind is seasonal: closed loop in January, open loop in July.
    assert pt.percent(pt.select(whv, "gas_in_kind", JAN_27)) == D("2.5")
    assert pt.percent(pt.select(whv, "gas_in_kind", date(2027, 7, 1))) == D("0.7")


def test_a_period_that_starts_later_never_prices_an_earlier_month():
    eet = pt.published_terminal("eemshaven-lng")
    assert pt.select(eet, "regas", JAN_27) == []
    later = pt.select(eet, "regas", date(2027, 10, 1))
    assert later and pt.weakest_status(later) == "INDICATIVE"
    # 17 m EUR per bcm per year at 11.0 kWh/m3: about 1.545 EUR/MWh.
    per_mwh = pt.regas_total(later, D(1)) * 1
    assert per_mwh == pytest.approx(D(17_000_000) / pt.MWH_PER_BCM)


def test_entry_conversions():
    grain = pt.published_terminal("grain-lng")
    uses = pt.select(grain, "entry_capacity", JAN_27, "firm") + pt.select(
        grain, "entry_commodity", JAN_27, "firm"
    )
    # 0.1259 p/kWh/d at 100 % load factor + 0.0213 p/kWh = 1.472 GBP/MWh.
    assert pt.entry_per_mwh(uses) == D("1.472")
    dunkerque = pt.published_terminal("dunkerque-lng")
    uses = pt.select(dunkerque, "entry_capacity", JAN_27, "firm")
    assert pt.entry_per_mwh(uses) == D("119.51") / 365
    assert pt.select(grain, "regas", JAN_27) == []
    assert "contract" in grain.not_published


def test_a_firm_id_or_alias_names_a_published_terminal():
    gate = pt.published_terminal("gate-terminal")
    assert gate.known_as("gate") and gate.known_as("GATE") and gate.known_as("gate-terminal")
    assert not gate.known_as("zeebrugge")
