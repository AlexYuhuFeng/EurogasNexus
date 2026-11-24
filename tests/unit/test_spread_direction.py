"""One direction rule for a spread on every screen (hands-on review QA-R-06)."""

from __future__ import annotations

from eurogas_nexus.application.spreads_board import spread_direction


def test_gas_flows_from_the_cheaper_hub_to_the_dearer_one():
    # NBP below TTF: the NBP-TTF spread is negative, so gas would go NBP to TTF.
    assert spread_direction(-3.052, "NBP", "TTF") == ("NBP", "TTF")
    assert spread_direction(2.0, "NBP", "TTF") == ("TTF", "NBP")
    assert spread_direction(0.0, "THE", "TTF") == ("TTF", "THE")
