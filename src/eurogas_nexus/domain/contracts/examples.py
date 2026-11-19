"""Worked examples of each typed contract kind (fictional), for the demo desk and the tests.

Every figure is an example a desk would recognise, not a market value: a UKCS field's gas
sold by tender at NBP day-ahead less 0.40 p/th with a 20 % swing, an LNG master agreement
with a fictional portfolio seller, and one DES cargo under it into a north-west European
terminal priced at 115 % Henry Hub plus 2.50 USD/MMBtu.
"""

from __future__ import annotations

from datetime import date, timedelta


def _month_start(day: date, months_ahead: int) -> date:
    index = day.year * 12 + day.month - 1 + months_ahead
    return date(index // 12, index % 12 + 1, 1)


def tender_terms(today: date) -> dict:
    """An upstream tender for the coming winter quarter at NBP."""

    start = _month_start(today, 1)
    end = _month_start(today, 4) - timedelta(days=1)
    return {
        "schema": "upstream-tender/v1",
        "counterparty_id": "DEMO-NORDVIK",
        "seller_name": "Nordvik Energy (fictional)",
        "field_name": "Skarv West (fictional field)",
        "tender_reference": "NV-T-Q1",
        "delivery_point": "NBP",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "nomination": "day_ahead",
        "allowed_exit_points": ["NBP"],
        "dcq_mwh_per_day": 5000.0,
        "min_dcq_mwh_per_day": 4000.0,
        "max_dcq_mwh_per_day": 6000.0,
        "offtake_obligation_pct": 90.0,
        "field_outage_force_majeure": True,
        "price_type": "index",
        "index": "NBP day-ahead",
        "differential": -0.4,
        "fixed_price": None,
        "price_unit": "GBp/th",
        "entry_cost_per_mwh": 0.15,
        "payment_lag_days": 20,
        "financing_rate_pct": 5.0,
    }


def mspa_terms(today: date) -> dict:
    """An LNG master agreement under which the desk buys cargoes."""

    return {
        "schema": "lng-mspa/v1",
        "counterparty_id": "DEMO-ATLANTIC-LNG",
        "counterparty_name": "Atlantic LNG Marketing (fictional)",
        "our_side": "buyer",
        "master_reference": "MSPA-2025-014",
        "signed_on": date(today.year - 1, 3, 14).isoformat(),
        "governing_law": "English law",
        "term_start": date(today.year - 1, 4, 1).isoformat(),
        "term_end": None,
        "delivery_terms": ["FOB", "DES"],
        "laytime_hours": 36.0,
        "demurrage_usd_per_day": 60000.0,
        "gcv_min_mj_m3": 37.5,
        "gcv_max_mj_m3": 44.0,
        "diversion_allowed": True,
        "credit_support": "parent_guarantee",
        "credit_support_amount": 25000000.0,
        "credit_support_currency": "USD",
        "payment_lag_days": 20,
    }


def cargo_terms(today: date) -> dict:
    """One DES cargo under the master, delivered in the month after next."""

    first = _month_start(today, 2)
    return {
        "schema": "lng-cargo/v1",
        "cargo_reference": "CN-07",
        "delivery_term": "DES",
        "load_port": "Sabine Pass",
        "discharge_terminal": "Gate terminal",
        "terminal_hub": "TTF",
        "window_start": (first + timedelta(days=9)).isoformat(),
        "window_end": (first + timedelta(days=13)).isoformat(),
        "narrowed_start": None,
        "narrowed_end": None,
        "quantity_mmbtu": 3600000.0,
        "tolerance_pct": 5.0,
        "price_formula": "hh",
        "slope": 1.15,
        "constant": 2.5,
        "hub_index": None,
        "fixed_price": None,
        "price_unit": "USD/MMBtu",
        "pricing_month": f"{_month_start(today, 1):%Y-%m}",
        "boil_off_pct_per_day": 0.1,
        "vessel_name": None,
        "lng_cargo_id": None,
    }
