"""TAR-2 domain: tariff years per publisher, the NC TAR status rule, the general
source-precedence resolver and the capacity-cost split built on it.

Every figure here is made up.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from eurogas_nexus.domain.pricing import financial_institutions as fi
from eurogas_nexus.domain.pricing import source_precedence as sp
from eurogas_nexus.domain.tariffs import precedence as p
from eurogas_nexus.domain.tariffs import tariff_year as ty
from eurogas_nexus.domain.tariffs.model import status_as_of
from eurogas_nexus.domain.tariffs.publishers import PUBLISHERS, publication_window_open, publisher

# ----------------------------------------------------------------------- tariff years


def test_each_convention_labels_its_own_year():
    assert ty.year_containing(date(2027, 11, 3), ty.GAS_YEAR).label == "GY 2027/28"
    assert ty.year_containing(date(2028, 9, 30), ty.GAS_YEAR).label == "GY 2027/28"
    assert ty.year_containing(date(2027, 11, 3), ty.CALENDAR_YEAR).label == "CY 2027"
    april = ty.year_containing(date(2028, 2, 1), ty.APRIL_YEAR)
    assert (april.label, april.first, april.last) == (
        "TY 2027/28 Apr-Mar", date(2027, 4, 1), date(2028, 3, 31)
    )
    assert ty.year_containing(date(2027, 1, 1), ty.NO_TARIFF_YEAR) is None


def test_national_gas_publishes_by_gas_year_and_unknown_cadences_say_so():
    assert publisher("national-gas").tariff_year == ty.GAS_YEAR
    assert publisher("entsog-tp").tariff_year == ty.PER_ROW
    for item in PUBLISHERS:
        assert item.tariff_year in ty.CONVENTIONS, item.publisher_id
        if item.tariff_year == ty.UNKNOWN:
            assert not item.cadence_confirmed
    assert any(not item.cadence_confirmed for item in PUBLISHERS)


def test_a_stated_period_gives_its_year_and_labels_round_trip():
    assert ty.tariff_year_for(date(2027, 10, 1), date(2028, 9, 30)).label == "GY 2027/28"
    assert ty.tariff_year_for(date(2027, 1, 1), date(2027, 12, 31)).label == "CY 2027"
    odd = ty.tariff_year_for(date(2027, 2, 1), date(2027, 2, 28))
    assert odd.convention == ty.UNKNOWN and odd.label.startswith("period ")
    for label in ("GY 2027/28", "CY 2027", "TY 2027/28 Apr-Mar", odd.label):
        assert ty.parse_tariff_year(label).label == label
    assert ty.parse_tariff_year("2026/27").label == "GY 2026/27"  # ENTSOG's register column
    assert ty.parse_tariff_year("2026").label == "CY 2026"
    assert ty.parse_tariff_year("nonsense") is None


def test_a_period_across_two_tariff_years_splits_at_the_boundary():
    parts = ty.split_by_tariff_year(date(2027, 9, 25), date(2027, 10, 5), ty.GAS_YEAR)
    assert [(x.label, x.first, x.last) for x in parts] == [
        ("GY 2026/27", date(2027, 9, 25), date(2027, 9, 30)),
        ("GY 2027/28", date(2027, 10, 1), date(2027, 10, 5)),
    ]
    assert len(ty.split_by_tariff_year(date(2027, 9, 25), date(2027, 10, 5), ty.PER_ROW)) == 1


# --------------------------------------------------------------------- NC TAR rule


def test_nc_tar_rule_final_once_in_force_or_auctioned_else_indicative():
    # The yearly auction of 2027 is on Monday 5 July 2027.
    assert ty.annual_yearly_auction(2027) == date(2027, 7, 5)
    gy_27_28 = date(2027, 10, 1)
    assert ty.nc_tar_status(gy_27_28, date(2027, 7, 4)) == ("INDICATIVE", ty.BASIS_BEFORE_AUCTION)
    assert ty.nc_tar_status(gy_27_28, date(2027, 7, 5)) == ("FINAL", ty.BASIS_AUCTION_HELD)
    # A calendar-year tariff for January, read in November: the auction sold from October.
    assert ty.nc_tar_status(date(2027, 1, 1), date(2026, 11, 25))[0] == "INDICATIVE"
    assert ty.nc_tar_status(date(2027, 1, 1), date(2027, 1, 1)) == ("FINAL", ty.BASIS_IN_FORCE)


def test_a_rule_status_is_re_evaluated_as_of_the_instant_and_a_stated_one_is_not():
    june, august = date(2027, 6, 1), date(2027, 8, 1)
    rule = ("INDICATIVE", ty.BASIS_BEFORE_AUCTION)
    assert status_as_of(*rule, date(2027, 10, 1), june)[0] == "INDICATIVE"
    assert status_as_of(*rule, date(2027, 10, 1), august)[0] == "FINAL"
    # TAR-1's recorded bases are read under the same rule.
    assert status_as_of("FINAL", "period_started", date(2027, 10, 1), june)[0] == "INDICATIVE"
    stated = ("INDICATIVE", "operator_stated")
    assert status_as_of(*stated, date(2027, 10, 1), august) == stated


def test_publication_windows_tighten_polling():
    poll = publisher("entsog-tp").poll
    assert publication_window_open(date(2027, 6, 1)) and poll.interval_minutes(
        date(2027, 6, 1)
    ) == 60
    assert not publication_window_open(date(2027, 8, 20))
    assert poll.interval_minutes(date(2027, 8, 20)) == 360


# ------------------------------------------------------------- the source resolver


def _found(value, source="s"):
    return lambda: sp.Found(value, source)


def test_the_resolver_takes_the_first_tier_that_holds_a_value_and_lists_every_tier():
    found = sp.resolve(
        sp.FX_RATE,
        {
            "contracted_bank": lambda: sp.Skipped(sp.STALE, "newest rate 2026-11-01"),
            "published_reference": lambda: sp.Skipped(sp.NOT_HELD),
            "ecb_reference": _found(1.08, "ECB"),
        },
    )
    assert found.value == 1.08 and found.used.tier == "ecb_reference"
    assert [(t.tier, t.reason) for t in found.tiers] == [
        ("contracted_bank", "stale"),
        ("published_reference", "not_held"),
        ("ecb_reference", "used"),
    ]
    view = found.as_dict()
    assert view["order_source"] == "default"
    assert [s["used"] for s in view["sources"]] == [False, False, True]


def test_the_contracted_bank_wins_and_later_tiers_are_listed_as_not_tried():
    found = sp.resolve(
        sp.FX_RATE,
        {"contracted_bank": _found(1.07, "BANK:ABC"), "ecb_reference": _found(1.08, "ECB")},
    )
    assert found.value == 1.07
    assert [t.reason for t in found.tiers] == ["used", "not_tried", "not_tried"]


def test_a_configured_order_per_context_comes_before_the_kind_order():
    configured = {"fx_rate": ["ecb_reference"], "fx_rate@lng_demurrage": ["contracted_bank"]}
    assert sp.order_for(sp.FX_RATE, "lng_demurrage", configured) == (
        ("contracted_bank",), "setting:fx_rate@lng_demurrage"
    )
    assert sp.order_for(sp.FX_RATE, "route_cost", configured) == (
        ("ecb_reference",), "setting:fx_rate"
    )
    # A stored order that no longer validates is ignored: the default holds.
    assert sp.order_for(sp.FX_RATE, "", {"fx_rate": ["telex"]})[1] == "default"
    found = sp.resolve(sp.FX_RATE, {"contracted_bank": _found(1.07)}, context="route_cost",
                       configured=configured)
    assert found.value is None and found.tiers[0].reason == "not_configured"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"fx": ["ecb_reference"]}, "not a quantity kind"),
        ({"fx_rate": ["public_final"]}, "not a tier of fx_rate"),
        ({"fx_rate": ["ecb_reference", "ecb_reference"]}, "listed twice"),
        ({"fx_rate": []}, "non-empty"),
        ({"fx_rate@bad context": ["ecb_reference"]}, "a context is"),
    ],
)
def test_an_order_naming_an_unknown_kind_or_tier_is_refused(value, message):
    with pytest.raises(sp.PrecedenceError, match=message):
        sp.validate_orders(value)


def test_a_bank_entry_holds_no_credential_and_a_live_feed_needs_the_firms_agreement():
    good = fi.validate_institutions(
        {"ABCBANK": {"name": "ABC Bank", "contracted": True, "provides": ["fx"]}}
    )
    assert good["ABCBANK"]["access"] == "file" and good["ABCBANK"]["max_age_days"] == 5
    with pytest.raises(fi.InstitutionError, match="no credential"):
        fi.validate_institutions({"ABCBANK": {"name": "A", "provides": ["fx"], "api_key": "x"}})
    with pytest.raises(fi.InstitutionError, match="agreement"):
        fi.validate_institutions({"ABCBANK": {"name": "A", "provides": ["fx"], "access": "api"}})
    held = fi.institutions(
        {"ABCBANK": {"name": "A", "provides": ["fx"], "access": "api", "agreement_recorded": True,
                     "contracted": True, "contexts": ["lng_demurrage"]}}
    )
    assert held[0].source_system == "BANK:ABCBANK"
    assert held[0].applies("fx", "lng_demurrage") and not held[0].applies("fx", "route_cost")
    assert "not connected" in held[0].as_dict()["live_feed"]


# --------------------------------------------------- capacity cost split (TAR-2 (a)-(c))

JAN = (date(2027, 1, 1), date(2027, 1, 31))


def _rate(status="FINAL", cost=0.5, year="GY 2026/27", version="v1"):
    return p.PublicRate(cost, "EUR", status, year, version,
                        how_bought="day-ahead auction reserve price")


def test_contracted_covers_its_quantity_and_the_rest_takes_the_public_rate():
    held = [p.Held("LT-1", *JAN, 60.0, 0.4, "EUR", acquired_via="long_term")]
    out = p.split(p.Requirement(*JAN, 100.0), held, _rate(cost=0.5))
    view = out.as_dict()
    assert view["covered"] == {"contracted": 1860.0, "public": 1240.0, "not_held": 0}
    assert view["total_cost"] == pytest.approx(1860 * 0.4 + 1240 * 0.5)
    assert [layer["layer"] for layer in view["layers"]] == ["contracted", "public"]
    assert view["layers"][1]["how_bought"] == "day-ahead auction reserve price"
    assert [(s["tier"], s["used"]) for s in view["sources"]] == [
        ("contracted", True), ("public_final", True), ("public_indicative", False)
    ]


def test_a_booking_covering_part_of_the_period_leaves_the_other_days_to_the_public_rate():
    held = [p.Held("M-1", date(2027, 1, 1), date(2027, 1, 10), 100.0, 0.4, "EUR")]
    out = p.split(p.Requirement(*JAN, 100.0), held, _rate())
    assert out.quantity(p.CONTRACTED) == 1000.0 and out.quantity(p.PUBLIC) == 2100.0


def test_nothing_held_is_not_priced_and_never_zero():
    out = p.split(p.Requirement(*JAN, 100.0), [], None)
    assert out.total_cost is None and not out.complete
    assert out.quantity(p.NOT_HELD) == 3100.0
    assert any("not priced" in issue for issue in out.issues)
    unpriced = p.split(p.Requirement(*JAN, 10.0), [p.Held("B", *JAN, 10.0, None, None)], None)
    assert unpriced.total_cost is None
    assert any("contracted cost is not recorded" in issue for issue in unpriced.issues)


def test_final_is_used_where_held_else_indicative_is_used_and_flagged():
    final, indicative = _rate("FINAL", 0.5), _rate("INDICATIVE", 0.45, version="v0")
    out = p.split(p.Requirement(*JAN, 10.0), [], [indicative, final])
    assert out.layers[0].detail["status"] == "FINAL" and not out.indicative
    only = p.split(p.Requirement(*JAN, 10.0), [], [indicative])
    assert only.indicative and only.layers[0].detail["version_id"] == "v0"
    assert any("INDICATIVE" in issue for issue in only.issues)
    tiers = {s["tier"]: s for s in only.sources()}
    assert tiers["public_final"]["reason"] == "not_held"
    assert "no final version held for GY 2026/27" in tiers["public_final"]["note"]


def test_a_period_across_two_tariff_years_takes_each_days_own_years_rate():
    def rate_for(day):
        if day < date(2027, 10, 1):
            return _rate("FINAL", 0.5, "GY 2026/27", "v-2627")
        return _rate("INDICATIVE", 0.6, "GY 2027/28", "v-2728")

    out = p.split(p.Requirement(date(2027, 9, 28), date(2027, 10, 2), 10.0), [], rate_for)
    years = [(layer.detail["tariff_year"], layer.quantity) for layer in out.layers]
    assert years == [("GY 2026/27", 30.0), ("GY 2027/28", 20.0)]
    assert out.total_cost == pytest.approx(30 * 0.5 + 20 * 0.6) and out.indicative


def test_slots_are_drawn_from_a_pool_and_the_next_cargo_falls_to_the_public_rate():
    pool = [p.Held("SLOT-A", date(2027, 3, 1), date(2027, 3, 31), 1.0, 450000.0, "EUR",
                   basis=p.POOL, acquired_via="auction")]
    fcfs = p.PublicRate(520000.0, "EUR", "FINAL", "CY 2027", "lng-v1",
                        how_bought=p.HOW_BOUGHT["spot"])
    first = p.split(p.Requirement(date(2027, 3, 5), date(2027, 3, 5), 1.0, "slot"), pool, fcfs)
    assert first.total_cost == 450000.0 and first.layers[0].layer == p.CONTRACTED
    both = p.split(p.Requirement(date(2027, 3, 5), date(2027, 3, 6), 1.0, "slot"), pool, fcfs)
    assert [(x.layer, x.quantity) for x in both.layers] == [("contracted", 1.0), ("public", 1.0)]
    assert both.total_cost == 970000.0


def test_the_firms_order_can_leave_the_contracted_tier_out_or_put_it_second():
    held = [p.Held("LT-1", *JAN, 60.0, 0.4, "EUR")]
    public_only = p.split(p.Requirement(*JAN, 100.0), held, _rate(),
                          configured={"capacity_cost": ["public_final"]})
    assert public_only.quantity(p.CONTRACTED) == 0 and public_only.order_source.startswith(
        "setting:"
    )
    assert public_only.sources()[-1] | {"label": None} == {
        "tier": "contracted", "label": None, "used": False, "quantity": 0.0,
        "reason": "not_configured", "note": "left out of the order in force",
    }
    second = p.split(p.Requirement(*JAN, 100.0), held, _rate("INDICATIVE"),
                     order=["public_final", "contracted", "public_indicative"])
    assert second.quantity(p.CONTRACTED) == 1860.0 and second.quantity(p.PUBLIC) == 1240.0


def test_contracted_offers_rank_first_in_lng_3():
    ranks = sorted(["indicative", "tariff", "contracted", "quoted"], key=p.offer_rank)
    assert ranks[0] == "contracted" and ranks[-1] == "indicative"


def test_resolution_dates_are_reported():
    moment = datetime(2026, 11, 25, 9)
    found = sp.resolve(sp.TARIFF, {"public_final": _found(1.0)}, as_of=moment)
    assert found.as_dict()["as_of"] == moment.isoformat()
