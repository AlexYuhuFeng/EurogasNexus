"""Placing an outage on the map: EIC, then a unique name, never a guess."""

from __future__ import annotations

from types import SimpleNamespace

from eurogas_nexus.application.map_situation import _facility_keys, _Locator


def ref(ref_id, name, lat, lon, eic=None, country="DE"):
    return SimpleNamespace(
        id=ref_id, name=name, lat=lat, lon=lon, country=country, data_quality="approx",
        source_record_id=None, metadata_json={"point_eic_code": eic} if eic else {},
    )


FACILITIES = [
    ref("fac-1", "UGS Bierwang", 48.0, 12.2, country="EU"),
    ref("fac-2", "Bergermeer", 52.6, 4.7),
    ref("fac-3", "Nord-B / SEDIANE B", 49.5, 2.7),
    ref("fac-4", "Etzel (DE) (EKB) / Oude Statenzijl Etzel (NL)", 53.5, 7.8),
    ref("fac-5", "Etzel (DE) (Crystal) / Oude Statenzijl (NL)", 53.5, 7.8),
    ref("fac-6", "Epe (DE) / Enschede (NL)", 52.2, 7.0),
    ref("fac-7", "Epe (DE) (Trianel)", 52.1, 7.1),
    ref("fac-8", "VGS Storage Hub", 51.8, 11.7, eic="21W0000000000427"),
]
NODES = [ref("node-2", "Bergermeer", 52.6, 4.7)]  # the same point as a node


def locator():
    return _Locator(NODES, FACILITIES)


def test_eic_first():
    hit, how = locator().explain(eic="21w0000000000427", name="something else")
    assert (hit["ref_id"], how) == ("fac-8", "eic")


def test_site_name_without_generic_words_places_when_unique():
    assert locator().explain(name="Bierwang")[1] == "facility_name"
    assert locator().explain(name="VGS SEDIANE B")[0]["ref_id"] == "fac-3"


def test_node_and_facility_at_one_place_are_one_match():
    hit, how = locator().explain(name="UGS Bergermeer")
    assert how == "facility_name"
    assert hit["points_at_place"] == 2


def test_several_points_at_one_site_are_one_place():
    hit, _ = locator().explain(name="Etzel")
    assert hit is not None and hit["points_at_place"] == 2


def test_a_name_for_two_places_stays_unlocated_with_the_reason():
    hit, how = locator().explain(eic="21W000000000066U", name="EPE-H")
    assert hit is None
    assert how.startswith("ambiguous_facility_name:2_places:")


def test_no_fuzzy_guess():
    assert locator().explain(name="Nüttermoor 4 H-Gas") == (None, "no_reference_match")
    assert locator().explain(name="Bierwan") == (None, "no_reference_match")


def test_facility_keys_drop_accents_brackets_and_generic_words():
    assert _facility_keys("GSF GIM Sanok - UGS PMG Brzeźnica") == {"gsf gim sanok pmg brzeznica"}
    assert "sediane b" in _facility_keys("Nord-B / SEDIANE B")
