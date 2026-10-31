"""LNG terminal costs from each operator's own published documents.

European terminals price capacity in different ways, and a single "regas tariff" field hides
that. Each terminal here states its regime and is read from the document the operator
publishes:

* **Zeebrugge (Fluxys LNG), regulated and indexed monthly.** The CREG-approved tariff list
  gives a slot (berthing, basic storage and basic send-out for one cargo) in "basis 2003"
  euros, indexed every month with Belgian CPI; Fluxys publishes a price simulator per month
  with the indexed values. Gas in kind is a percentage of the cargo.
* **Montoir, Fos Cavaou, Fos Tonkin (Elengy), regulated by the CRE (ATTM).** A total per
  cargo by cargo size (Med-Max, standard, Q-Flex, Q-Max) for **standard** capacity and for
  **SMART SPOT** (booked after the 20th of the month before unloading), of which an energy
  term varies with the quantity unloaded. Fuel ("gas taken off"), port fees and the
  transmission entry tariff are charged separately.
* **Brunsbüttel and Wilhelmshaven (DET), auctioned.** Short-term capacity is sold by auction
  and DET publishes the average clearing price per MMBtu for each period.
* **Gate, Dunkerque LNG, Grain, Eemshaven, private terminals: exempt or negotiated.** No
  public price list applies to a new booking; the firm enters the price from its own
  contract or the operator's offer (open season, market call, secondary market).

Every parsed value carries the document URL, its SHA-256 and the period it applies to, so a
bid priced with it can be traced back to the operator's page.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

MWH_PER_MMBTU = 0.29307107
FLUXYS_TARIFF_PAGE = (
    "https://www.fluxys.com/en/natural-gas-and-biomethane/empowering-you/tariffs/"
    "tariff_fluxyslng-lng"
)
ELENGY_TARIFF_PAGE = "https://www.elengy.com/en/our-services/pricing-conditions/our-access-tariffs"
DET_NEWS_PAGE = "https://energy-terminal.de/en/news"

#: Elengy cargo classes and the energy each tariff line assumes (from the tariff brochure).
ELENGY_CARGO_CLASSES = (
    ("med_max", 500_000.0),
    ("standard", 1_000_000.0),
    ("q_flex", 1_400_000.0),
    ("q_max", 1_700_000.0),
)


class TerminalTariffError(ValueError):
    """A document could not be read as the expected tariff."""


@dataclass(frozen=True)
class TerminalCost:
    """What one product at one terminal costs, with where the figure came from."""

    terminal_id: str  # e.g. "zeebrugge:term", "montoir:spot"
    name: str
    country: str
    hub: str
    regime: str  # regulated_indexed, regulated, auction, negotiated
    product: str  # term or spot
    currency: str
    fixed_per_cargo: float = 0.0
    per_mwh: float = 0.0
    fuel_retention_pct: float = 0.0
    effective_from: str = ""  # ISO date or month the figure applies from
    period: str = ""
    source_url: str = ""
    source_sha256: str = ""
    excludes: tuple[str, ...] = ()
    by_cargo_class: dict[str, float] = field(default_factory=dict)  # Elengy totals per class

    def cost_for(self, cargo_mwh: float) -> tuple[float, float] | None:
        """(fixed per cargo, per MWh) for a cargo of this size; None if it cannot be priced.

        With a tariff by cargo class the smallest class that holds the cargo applies; a
        class the terminal does not list (Fos Tonkin takes Med-Max ships only) means the
        cargo cannot be landed there on this tariff.
        """

        if self.by_cargo_class:
            for name, energy in ELENGY_CARGO_CLASSES:
                if cargo_mwh <= energy * 1.05:
                    total = self.by_cargo_class.get(name)
                    return None if total is None else (total, 0.0)
            return None
        return self.fixed_per_cargo, self.per_mwh

    def note(self) -> str:
        parts = [f"{self.regime}, {self.product}"]
        if self.period:
            parts.append(self.period)
        if self.excludes:
            parts.append("excludes " + ", ".join(self.excludes))
        return "; ".join(parts)[:256]


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ------------------------------------------------------------------------- Fluxys (Zeebrugge)


def fluxys_document_links(page_html: str) -> dict[str, str]:
    """The newest price simulator and tariff list linked from the Fluxys LNG tariff page."""

    links = re.findall(r'href="([^"]+\.(?:xlsx|pdf))"', page_html, flags=re.IGNORECASE)
    simulators = [link for link in links if "price-simulator" in link.lower()]
    lists = [link for link in links if "tariff-list" in link.lower()]
    if not simulators:
        raise TerminalTariffError("no price simulator linked from the Fluxys tariff page")
    absolute = lambda link: link if link.startswith("http") else "https://www.fluxys.com" + link  # noqa: E731
    result = {"simulator": absolute(sorted(simulators)[-1])}
    if lists:
        result["tariff_list"] = absolute(sorted(lists)[-1])
    return result


def _xlsx_cells(content: bytes) -> dict[str, dict[str, str]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise TerminalTariffError("the price simulator is not an xlsx file") from exc
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        for item in root.findall("m:si", ns):
            shared.append("".join(t.text or "" for t in item.iter(f"{{{ns['m']}}}t")))
    sheets: dict[str, dict[str, str]] = {}
    for name in sorted(n for n in archive.namelist() if n.startswith("xl/worksheets/sheet")):
        cells: dict[str, str] = {}
        for cell in ElementTree.fromstring(archive.read(name)).iter(f"{{{ns['m']}}}c"):
            value = cell.find("m:v", ns)
            if value is None or value.text is None:
                continue
            cells[cell.get("r", "")] = (
                shared[int(value.text)] if cell.get("t") == "s" else value.text
            )
        sheets[name] = cells
    return sheets


def parse_fluxys_simulator(content: bytes, *, source_url: str) -> TerminalCost:
    """Indexed slot price for the month the simulator applies to."""

    month = ""
    slot = None
    for cells in _xlsx_cells(content).values():
        for value in cells.values():
            found = re.search(r"Tariff applicable during the month of (\w+ \d{4})", value)
            if found:
                month = found.group(1)
        for ref, value in cells.items():
            if value.strip() == "Slot":
                row = re.sub(r"[A-Z]+", "", ref)
                indexed = cells.get(f"E{row}")
                if indexed is not None:
                    try:
                        slot = float(indexed)
                    except ValueError:
                        pass
    if slot is None or not 100_000 < slot < 5_000_000:
        raise TerminalTariffError("indexed slot price not found in the Fluxys simulator")
    return TerminalCost(
        terminal_id="zeebrugge:term",
        name="Zeebrugge LNG",
        country="BE",
        hub="ZTP",
        regime="regulated_indexed",
        product="term",
        currency="EUR",
        fixed_per_cargo=round(slot, 2),
        effective_from=month,
        period=f"Fluxys LNG tariff (CREG), indexed for {month}" if month else "Fluxys LNG tariff",
        source_url=source_url,
        source_sha256=sha256(content),
        excludes=("port dues", "transmission entry"),
    )


def parse_fluxys_gas_in_kind(text: str) -> float | None:
    found = re.search(r"Gas in Kind[^\n]*?(\d+[.,]\d+)\s*%", text)
    return float(found.group(1).replace(",", ".")) if found else None


# ----------------------------------------------------------------------- Elengy (France)

_ELENGY_TERMINALS = {
    "Fos Cavaou": ("fos-cavaou", "PEG"),
    "Fos Tonkin": ("fos-tonkin", "PEG"),
    "Montoir-de-Bretagne": ("montoir", "PEG"),
}
_ELENGY_ROWS = {
    "Unloading\n(Med-Max)": "med_max",
    "Unloading\n(standard cargo)": "standard",
    "Unloading\n(Q-Flex)": "q_flex",
    "Unloading\n(Q-Max)": "q_max",
}


def _number(text: str) -> float:
    return float(text.replace(" ", "").replace(" ", "").replace(",", "."))


def parse_elengy_brochure(text: str, *, source_url: str, digest: str) -> list[TerminalCost]:
    """Standard and SMART SPOT totals per cargo class for each Elengy terminal."""

    applicable = re.search(r"TARIFFS APPLICABLE AS OF ([A-Z]+) (\d{1,2})\w* (\d{4})", text)
    effective = ""
    if applicable:
        months = [
            "JANUARY",
            "FEBRUARY",
            "MARCH",
            "APRIL",
            "MAY",
            "JUNE",
            "JULY",
            "AUGUST",
            "SEPTEMBER",
            "OCTOBER",
            "NOVEMBER",
            "DECEMBER",
        ]
        month, day, year = applicable.groups()
        if month.upper() in months:
            effective = f"{year}-{months.index(month.upper()) + 1:02d}-{int(day):02d}"
    costs: list[TerminalCost] = []
    # The brochure lists each terminal's table after its name; split on the names.
    positions = sorted(
        (match.start(), name)
        for name in _ELENGY_TERMINALS
        for match in re.finditer(rf"\n{re.escape(name)}\n", text)
    )
    for index, (start, name) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(text)
        section = text[start:end]
        standard: dict[str, float] = {}
        spot: dict[str, float] = {}
        for label, cargo_class in _ELENGY_ROWS.items():
            pattern = (
                re.escape(label)
                + r"\nEnergy variable term \nbased on quantity \neffectively unloaded\n"
                + r"(\d[\d ]*\d)\n[\d ]+\n[\d,]+ [\d,]+\s+(\d[\d ]*\d)\n"
            )
            found = re.search(pattern, section)
            if found:
                standard[cargo_class] = _number(found.group(1))
                spot[cargo_class] = _number(found.group(2))
        if not standard:
            continue
        slug, hub = _ELENGY_TERMINALS[name]
        for product, table in (("term", standard), ("spot", spot)):
            costs.append(
                TerminalCost(
                    terminal_id=f"{slug}:{product}",
                    name=name,
                    country="FR",
                    hub=hub,
                    regime="regulated",
                    product=product,
                    currency="EUR",
                    by_cargo_class=dict(table),
                    effective_from=effective,
                    # CRE deliberation 2025-41: no annual update; next one 1 April 2028.
                    period=f"Elengy ATTM tariff (CRE) from {effective}, next update 2028-04-01"
                    + ("; SMART SPOT" if product == "spot" else ""),
                    source_url=source_url,
                    source_sha256=digest,
                    excludes=("gas taken off", "port fees", "transmission entry"),
                )
            )
    if not costs:
        raise TerminalTariffError("no Elengy terminal table recognised")
    return costs


def elengy_brochure_link(page_html: str) -> str:
    links = re.findall(r'href="([^"]+\.pdf)"', page_html, flags=re.IGNORECASE)
    tariffs = [link for link in links if "tariff" in link.lower()]
    if not tariffs:
        raise TerminalTariffError("no tariff brochure linked from the Elengy page")
    link = sorted(tariffs)[-1]
    return link if link.startswith("http") else "https://www.elengy.com" + link


# ------------------------------------------------------------------------- DET (Germany)

_DET_TERMINALS = {"Brunsbüttel": ("brunsbuttel", "THE"), "Wilhelmshaven": ("wilhelmshaven", "THE")}


def parse_det_auction_notice(text: str, *, source_url: str, digest: str) -> TerminalCost:
    """An auction notice: terminal, period and average clearing price per MMBtu."""

    terminal = next((name for name in _DET_TERMINALS if name in text), None)
    price = re.search(r"average price of EUR\s*([\d.,]+)\s*/\s*MMBtu", text)
    period = re.search(r"period from ([^*.]+?\d{4})", text)
    if terminal is None or price is None:
        raise TerminalTariffError("no terminal or average price in the DET notice")
    per_mmbtu = float(price.group(1).replace(",", "."))
    slug, hub = _DET_TERMINALS[terminal]
    return TerminalCost(
        terminal_id=f"{slug}:spot",
        name=terminal,
        country="DE",
        hub=hub,
        regime="auction",
        product="spot",
        currency="EUR",
        per_mwh=round(per_mmbtu / MWH_PER_MMBTU, 4),
        period=f"DET auction, average {per_mmbtu} EUR/MMBtu"
        + (f", {period.group(1).strip()}" if period else ""),
        source_url=source_url,
        source_sha256=digest,
        excludes=("transmission entry",),
    )
