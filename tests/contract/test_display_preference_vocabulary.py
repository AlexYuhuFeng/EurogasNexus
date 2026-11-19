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
