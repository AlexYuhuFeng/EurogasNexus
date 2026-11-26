"""Simulated transmission tariffs for the demo desk: the one list and the one retirement rule.

A demo installation reads no published tariffs at first, so every locational spread it shows
would be "transport not priced". It holds simulated tariffs instead: one per leg of the BBL
crossing (TTF -> NBP and its reverse flow) and of one crossing of every other main hub pair the
demo market quotes (TTF-THE, TTF-ZTP, THE-PEG, THE-ZTP, PEG-ZTP, ZTP-NBP through IUK), both
directions. Magnitudes are of the order published capacity tariffs show at 100 % load factor;
invented, not market data.

- **Labelled.** ``tariff_status`` ``SIMULATOR_ONLY`` (the lowest status: a published row always
  wins a selection; the leg's class reads "simulated"), document ``demo-simulated-tariffs``,
  source "Simulated tariff (not published)".
- **Retired** (``retire_simulated_tariffs``) once a published ENTSOG row or a *reviewed*
  public tariff (``application/tso_tariff_entries``) names the same operator, point and
  direction. A candidate entry awaiting review does not retire one.

``SIMULATED_TARIFF_LEGS`` is the single list: the demo seed writes it
(``simulated_tariff_records``) and the demo market prices its hubs against the routes it gives
(``route_cost_rows``). It covers legs the published data leaves open today (National Gas at
Bacton, GTS at Balgzand, NaTran at Obergailbach: see the coverage table,
``scripts/ops/tariff_coverage.py``) and legs ENTSOG publishes, which a live read retires.

本模块是演示用模拟管输费率的唯一清单与退役规则：标记为模拟，已发布或已复核的同段费率出现后退役。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

SIMULATED_TARIFF_DOCUMENT = "demo-simulated-tariffs"
SIMULATED_TARIFF_SOURCE = "Simulated tariff (not published)"

#: (country, operator, point key, point name, direction, EUR/MWh at 100 % load factor).
SIMULATED_TARIFF_LEGS: tuple[tuple[str, str, str, str, str, float], ...] = (
    # TTF -> NBP through BBL (forward flow), and NBP -> TTF (reverse flow).
    ("NL", "GTS", "ITP-00063", "Julianadorp (GTS) /Balgzand (BBL)", "EXIT", 0.56),
    ("GB", "BBL company", "ITP-00207", "Bacton (BBL)", "EXIT", 1.20),
    ("GB", "National Gas TSO", "ITP-00207", "Bacton (BBL)", "ENTRY", 0.12),
    ("GB", "National Gas TSO", "ITP-00207", "Bacton (BBL)", "EXIT", 0.15),
    ("GB", "BBL company", "ITP-00207", "Bacton (BBL)", "ENTRY", 1.20),
    ("NL", "GTS", "ITP-00063", "Julianadorp (GTS) /Balgzand (BBL)", "ENTRY", 0.45),
    # TTF <-> THE at VIP TTF-THE-H.
    ("NL", "GTS", "ITP-10012", "VIP TTF-THE-H", "EXIT", 0.45),
    ("DE", "Gasunie Deutschland", "ITP-10012", "VIP TTF-THE-H", "ENTRY", 0.55),
    ("DE", "Gasunie Deutschland", "ITP-10012", "VIP TTF-THE-H", "EXIT", 0.55),
    ("NL", "GTS", "ITP-10012", "VIP TTF-THE-H", "ENTRY", 0.45),
    # TTF <-> ZTP at Zelzate.
    ("NL", "GTS", "ITP-00101", "Zelzate", "EXIT", 0.45),
    ("BE", "Fluxys Belgium", "ITP-00101", "Zelzate", "ENTRY", 0.40),
    ("BE", "Fluxys Belgium", "ITP-00101", "Zelzate", "EXIT", 0.80),
    ("NL", "GTS", "ITP-00101", "Zelzate", "ENTRY", 0.85),
    # THE <-> PEG at Obergailbach / Medelsheim.
    ("DE", "NaTran Deutschland", "ITP-00137", "Obergailbach (FR) / Medelsheim (DE)", "EXIT", 0.55),
    ("FR", "NaTran", "ITP-00137", "Obergailbach (FR) / Medelsheim (DE)", "ENTRY", 0.50),
    ("FR", "NaTran", "ITP-00137", "Obergailbach (FR) / Medelsheim (DE)", "EXIT", 0.55),
    ("DE", "NaTran Deutschland", "ITP-00137", "Obergailbach (FR) / Medelsheim (DE)", "ENTRY", 0.50),
    # THE <-> ZTP at VIP THE-ZTP.
    ("DE", "Open Grid Europe", "ITP-00614", "VIP THE-ZTP", "EXIT", 0.70),
    ("BE", "Fluxys Belgium", "ITP-00614", "VIP THE-ZTP", "ENTRY", 0.70),
    ("BE", "Fluxys Belgium", "ITP-00614", "VIP THE-ZTP", "EXIT", 0.70),
    ("DE", "Open Grid Europe", "ITP-00614", "VIP THE-ZTP", "ENTRY", 0.70),
    # PEG <-> ZTP at Virtualys.
    ("FR", "NaTran", "ITP-00526", "VIRTUALYS", "EXIT", 0.50),
    ("BE", "Fluxys Belgium", "ITP-00526", "VIRTUALYS", "ENTRY", 0.40),
    ("BE", "Fluxys Belgium", "ITP-00526", "VIRTUALYS", "EXIT", 0.40),
    ("FR", "NaTran", "ITP-00526", "VIRTUALYS", "ENTRY", 0.50),
    # ZTP <-> NBP through IUK (Zeebrugge IZT, Bacton IUK).
    ("BE", "Fluxys Belgium", "ITP-00061", "Zeebrugge IZT", "EXIT", 0.40),
    ("BE", "Interconnector", "ITP-00061", "Zeebrugge IZT", "ENTRY", 1.60),
    ("GB", "Interconnector", "ITP-00005", "Bacton (IUK)", "EXIT", 1.60),
    ("GB", "National Gas TSO", "ITP-00005", "Bacton (IUK)", "ENTRY", 0.12),
    ("GB", "National Gas TSO", "ITP-00005", "Bacton (IUK)", "EXIT", 0.15),
    ("GB", "Interconnector", "ITP-00005", "Bacton (IUK)", "ENTRY", 1.60),
    ("BE", "Interconnector", "ITP-00061", "Zeebrugge IZT", "EXIT", 1.60),
    ("BE", "Fluxys Belgium", "ITP-00061", "Zeebrugge IZT", "ENTRY", 0.40),
)


def _gas_year_start(today: date) -> date:
    return date(today.year if today.month >= 10 else today.year - 1, 10, 1)


def simulated_tariff_records(
    *, today: date, now: datetime, gas_year: str, source_ref: str
) -> list[dict[str, Any]]:
    """``tso_tariffs`` rows for every simulated leg, in force from this gas year's start."""

    start = datetime.combine(_gas_year_start(today), datetime.min.time(), tzinfo=UTC)
    return [
        {
            "tariff_id": f"demo-sim-{tso}-{point}-{direction}".lower().replace(" ", "-"),
            "document_id": SIMULATED_TARIFF_DOCUMENT,
            "country": country,
            "tso": tso,
            "market_area": "DEMO",
            "gas_year": gas_year,
            "point_id": point,
            "source_point_name": name,
            "direction": direction,
            "capacity_product": "ANNUAL",
            "firmness": "FIRM",
            "tariff_value": value,
            "currency": "EUR",
            "unit": "EUR/MWh",
            "effective_from": start,
            "effective_to": None,
            "tariff_status": "SIMULATOR_ONLY",
            "source_table": SIMULATED_TARIFF_SOURCE,
            "source_page": None,
            "source_refs": [source_ref],
            "manual_review_required": True,
            "created_at_utc": now,
        }
        for country, tso, point, name, direction, value in SIMULATED_TARIFF_LEGS
    ]


def route_cost_rows() -> list[dict[str, Any]]:
    """The simulated legs as pricing rows (``route_tariff_cost``), in force at any date."""

    return [
        {
            "point_id": point,
            "direction": direction,
            "tso": tso,
            "tariff_value": value,
            "currency": "EUR",
            "unit": "EUR/MWh",
            "effective_from": None,
            "effective_to": None,
            "tariff_status": "SIMULATOR_ONLY",
            "gas_year": "demo",
            "tariff_id": f"demo-sim-{point}",
            "source_table": "simulated",
        }
        for _country, tso, point, _name, direction, value in SIMULATED_TARIFF_LEGS
    ]


#: Documents whose rows replace a simulated leg: published ENTSOG rows and reviewed entries.
def _replaces(document_id: str) -> bool:
    from eurogas_nexus.application.tso_tariff_entries import DOCUMENT, REVIEWED

    return document_id.startswith("entsog-tariffsfulls-") or document_id == DOCUMENT[REVIEWED]


def retire_simulated_tariffs(session) -> int:
    """Delete simulated tariffs whose leg a published or reviewed row now names; idempotent."""

    from eurogas_nexus.db.models import TsoTariffRecord

    held = {
        (row.tso.strip().lower(), row.point_id, row.direction.upper())
        for row in session.query(TsoTariffRecord).filter(
            TsoTariffRecord.document_id != SIMULATED_TARIFF_DOCUMENT
        )
        if _replaces(row.document_id)
    }
    retired = 0
    for row in session.query(TsoTariffRecord).filter(
        TsoTariffRecord.document_id == SIMULATED_TARIFF_DOCUMENT
    ):
        if (row.tso.strip().lower(), row.point_id, row.direction.upper()) in held:
            session.delete(row)
            retired += 1
    return retired
