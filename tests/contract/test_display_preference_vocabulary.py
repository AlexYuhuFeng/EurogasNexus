"""The client's currency and energy-unit lists are the server's vocabulary (CP-05)."""

from __future__ import annotations

import re
from pathlib import Path

from eurogas_nexus.domain.settings.preferences import ENERGY_UNITS, REPORTING_CURRENCIES

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "clients" / "web" / "src" / "app" / "time" / "valueFormat.ts"


def _client_list(name: str) -> list[str]:
    text = CLIENT.read_text(encoding="utf-8")
    block = re.search(rf"{name}\s*=\s*\[([^\]]*)\]", text)
    assert block, f"{name} not found in {CLIENT.name}"
    return re.findall(r'"([^"]+)"', block.group(1))


def test_the_client_offers_exactly_the_servers_reporting_currencies() -> None:
    assert _client_list("REPORTING_CURRENCIES") == list(REPORTING_CURRENCIES)


def test_the_client_offers_exactly_the_servers_energy_units() -> None:
    assert _client_list("ENERGY_UNITS") == list(ENERGY_UNITS)


def test_the_client_offers_exactly_the_servers_pnl_colour_conventions() -> None:
    """The colour-vision friendly scheme (UX R1) is stored like the regional conventions."""

    from eurogas_nexus.domain.settings.preferences import PREFERENCE_VOCABULARY

    pnl = ROOT / "clients" / "web" / "src" / "app" / "model" / "pnlColor.ts"
    source = pnl.read_text(encoding="utf-8")
    block = re.search(r"PNL_COLOR_CONVENTIONS[^=]*=\s*\[([^\]]*)\]", source)
    assert block, "PNL_COLOR_CONVENTIONS not found in pnlColor.ts"
    assert re.findall(r'"([^"]+)"', block.group(1)) == list(PREFERENCE_VOCABULARY["pnl_colors"])


def test_the_client_offers_exactly_the_servers_row_densities() -> None:
    """The row density (UX R11) is a closed vocabulary on both sides."""

    from eurogas_nexus.domain.settings.preferences import BUILT_IN_DEFAULTS, PREFERENCE_VOCABULARY

    density = ROOT / "clients" / "web" / "src" / "app" / "model" / "density.ts"
    block = re.search(r"DENSITIES[^=]*=\s*\[([^\]]*)\]", density.read_text(encoding="utf-8"))
    assert block, "DENSITIES not found in density.ts"
    assert re.findall(r'"([^"]+)"', block.group(1)) == list(PREFERENCE_VOCABULARY["density"])
    assert BUILT_IN_DEFAULTS["density"] == "comfortable"
