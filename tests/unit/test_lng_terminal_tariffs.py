"""Terminal tariffs read from each operator's document layout (synthetic fixtures)."""

from __future__ import annotations

import io
import zipfile

import pytest

from eurogas_nexus.domain.portfolio.lng_bid import TerminalTerms, regas_charge
from eurogas_nexus.ingestion.lng_terminal_tariffs import (
    TerminalTariffError,
    fluxys_document_links,
    parse_det_auction_notice,
    parse_elengy_brochure,
    parse_fluxys_gas_in_kind,
    parse_fluxys_simulator,
)


def _xlsx(cells: dict[str, str | float]) -> bytes:
    strings = [v for v in cells.values() if isinstance(v, str)]
    sheet = []
    for ref, value in cells.items():
        if isinstance(value, str):
            sheet.append(f'<c r="{ref}" t="s"><v>{strings.index(value)}</v></c>')
        else:
            sheet.append(f'<c r="{ref}"><v>{value}</v></c>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f"<worksheet {ns}><sheetData><row>{''.join(sheet)}</row></sheetData></worksheet>",
        )
    return buffer.getvalue()


def test_fluxys_indexed_slot_and_documents():
    content = _xlsx(
        {
            "A4": "Tariff applicable during the month of March 2027, calculated with the index",
            "C10": "Slot",
            "D10": 527803.2,
            "E10": 640000.5,
        }
    )
    cost = parse_fluxys_simulator(content, source_url="https://fluxys.example/sim.xlsx")
    assert cost.fixed_per_cargo == 640000.5 and cost.effective_from == "March 2027"
    assert cost.regime == "regulated_indexed" and len(cost.source_sha256) == 64
    with pytest.raises(TerminalTariffError):
        parse_fluxys_simulator(_xlsx({"C10": "Slot"}), source_url="x")
    assert parse_fluxys_gas_in_kind("Gas in Kind (Fuel Gas Compensation Rate)  1,30 %") == 1.3
    links = fluxys_document_links(
        '<a href="/-/media/x/price-simulator/2026/09---a.xlsx"></a>'
        '<a href="/-/media/x/price-simulator/2026/10---b.xlsx"></a>'
        '<a href="/-/media/x/tariff-sheets/2610---tariff-list-en.pdf"></a>'
    )
    assert links["simulator"].endswith("10---b.xlsx") and links["simulator"].startswith("https://")


ELENGY = (
    "TARIFFS APPLICABLE AS OF APRIL 1st 2031\n"
    "\nPortA\nSMART SPOT\n"
    "Unloading\n(Med-Max)\nEnergy variable term \nbased on quantity \neffectively unloaded\n"
    "600 000\n30 000\n1,20 0,38 480 000\n30 000\n0,96 0,30\n"
    "Unloading\n(standard cargo)\nEnergy variable term \nbased on quantity \neffectively unloaded\n"
    "1 000 000\n50 000\n1,00 0,32\n \n800 000\n50 000\n0,80 0,25\n"
)


def test_elengy_standard_and_spot_by_cargo_class(monkeypatch):
    import eurogas_nexus.ingestion.lng_terminal_tariffs as module

    monkeypatch.setitem(module._ELENGY_TERMINALS, "PortA", ("porta", "PEG"))
    term, spot = parse_elengy_brochure(ELENGY, source_url="https://e.example/b.pdf", digest="d")
    assert term.terminal_id == "porta:term" and spot.terminal_id == "porta:spot"
    assert term.by_cargo_class == {"med_max": 600000.0, "standard": 1000000.0}
    assert spot.by_cargo_class == {"med_max": 480000.0, "standard": 800000.0}
    assert term.effective_from == "2031-04-01"
    assert term.cost_for(450_000) == (600000.0, 0.0)
    assert term.cost_for(1_400_000) is None  # no Q-Flex class: cannot land here
    with pytest.raises(TerminalTariffError):
        parse_elengy_brochure("nothing here", source_url="u", digest="d")


def test_det_auction_notice():
    cost = parse_det_auction_notice(
        "capacities at the Wilhelmshaven terminal for the period from 1 May to 31 July 2031* "
        "were marketed at an average price of EUR 0.30 /MMBtu.",
        source_url="https://det.example/n",
        digest="d",
    )
    assert cost.terminal_id == "wilhelmshaven:spot" and cost.regime == "auction"
    assert cost.per_mwh == pytest.approx(0.30 / 0.29307107, abs=1e-4)
    with pytest.raises(TerminalTariffError):
        parse_det_auction_notice("no price", source_url="u", digest="d")


def test_regas_charge_by_regime():
    base = dict(
        terminal_id="t", name="T", country="BE", hub="ZTP", currency="EUR", regas_tariff_per_mwh=0.0
    )
    slot = TerminalTerms(**base, fixed_per_cargo=631714.81)
    assert regas_charge(slot, 1_000_000) == pytest.approx(631714.81)
    auction = TerminalTerms(**{**base, "regas_tariff_per_mwh": 0.68})
    assert regas_charge(auction, 1_000_000) == pytest.approx(680_000)
    classes = TerminalTerms(**base, by_cargo_class={"med_max": 531000, "standard": 972000})
    assert regas_charge(classes, 980_000) == 972000
    assert regas_charge(classes, 1_600_000) is None
    held = TerminalTerms(**base, capacity_basis="long_term", variable_regas_per_mwh=0.05)
    assert regas_charge(held, 1_000_000) == pytest.approx(50_000)
