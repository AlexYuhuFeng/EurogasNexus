"""A market-area side ENTSOG's interconnections leave blank is named from the access rows."""

from __future__ import annotations

from eurogas_nexus.reference_data.network_adjacency import fill_blank_sides
from eurogas_nexus.reference_data.network_bundle import load_bundle


def _edge(point, hub, operators):
    return {
        "id": f"adj-{point}-{hub}",
        "type": "market_area_link",
        "point_key": point,
        "hub_point_key": hub,
        "operators": operators,
    }


def test_a_blank_side_takes_the_operators_entsog_lists_at_the_point_in_that_country():
    bundle = {
        "operators": {
            "DE-TSO-0009": {"country": "DE"},
            "NL-TSO-0001": {"country": "NL"},
            "DE-TSO-0004": {"country": "DE"},
        },
        "access": [
            {"access_id": "a1", "point_key": "P1", "operator_key": "DE-TSO-0009"},
            {"access_id": "a2", "point_key": "P1", "operator_key": "NL-TSO-0001"},
            {"access_id": "a3", "point_key": "P2", "operator_key": "DE-TSO-0004"},
        ],
    }
    edges = [
        _edge("P1", "VTP-00045", []),  # THE side blank: OGE listed at P1 -> filled
        _edge("P1", "VTP-00002", ["NL-TSO-0001"]),  # already named: unchanged
        _edge("P2", "VTP-00039", []),  # PEG side, no French operator listed: stays blank
    ]
    filled = {edge["id"]: edge for edge in fill_blank_sides(bundle, edges)}
    assert filled["adj-P1-VTP-00045"]["operators"] == ["DE-TSO-0009"]
    assert filled["adj-P1-VTP-00045"]["operators_basis"] == "entsog_operator_point_directions"
    assert filled["adj-P1-VTP-00045"]["operators_evidence"] == ["a1"]
    assert "operators_basis" not in filled["adj-P1-VTP-00002"]
    assert filled["adj-P2-VTP-00039"]["operators"] == []


def test_the_shipped_bundle_names_the_the_side_at_bunde_oge_and_not_at_vip_france_germany():
    edges = {edge["id"]: edge for edge in load_bundle()["edges"]}
    assert edges["adj-itp-00103-vtp-00045"]["operators"] == ["DE-TSO-0009"]
    # ENTSOG names no French operator at VIP France - Germany (read 19-11-2026).
    assert edges["adj-itp-00540-vtp-00039"]["operators"] == []
    # Re-applying the rule to the shipped bundle changes nothing more.
    bundle = load_bundle()
    assert fill_blank_sides(bundle, bundle["edges"]) == bundle["edges"]
