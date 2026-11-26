"""A price shock is entered as the desk quotes the hub (AGENTS rule 17): NBP in p/th.

The position-ladder endpoint converts it with the unit authority to the per-MWh figure the
ladder values with; a shock without a unit is per MWh in the hub's currency (the earlier form).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from eurogas_nexus.api.routes.public.portfolio import _parse_tenor_shocks
from eurogas_nexus.domain.market.units import convert_price


def test_a_shock_in_pence_per_therm_is_converted_by_the_unit_authority() -> None:
    shocks = _parse_tenor_shocks(
        ["NBP:2026-12:-2:p/th", "TTF:2026-12:-2:EUR/MWh", "TTF:2027-01:1.5"]
    )
    assert shocks[("NBP", "2026-12")] == pytest.approx(convert_price(-2, "GBp/th", "GBP/MWh"))
    assert shocks[("NBP", "2026-12")] == pytest.approx(-0.682428, rel=1e-5)
    assert shocks[("TTF", "2026-12")] == -2.0
    assert shocks[("TTF", "2027-01")] == 1.5


@pytest.mark.parametrize("item", ["NBP:2026-12:-2:EUR/MWh", "NBP:2026-12:-2:furlong", "NBP:12:-2"])
def test_a_unit_in_another_currency_an_unknown_unit_or_a_bad_item_is_refused(item: str) -> None:
    with pytest.raises(HTTPException) as caught:
        _parse_tenor_shocks([item])
    assert caught.value.status_code == 422
