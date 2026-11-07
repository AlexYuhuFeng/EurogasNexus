"""Desk wording for figures: one place, so alerts, "Why?" and briefs read the same."""

from __future__ import annotations

CURRENCY_SIGN = {"EUR": "€", "GBP": "£", "USD": "$"}

#: REMIT balancing-zone names and country codes to the hub that prices them.
ZONE_HUB = {
    "UK": "NBP",
    "GB": "NBP",
    "NL": "TTF",
    "DE": "THE",
    "GASPOOL": "THE",
    "NCG": "THE",
    "FR": "PEG",
    "TRF": "PEG",
    "BE": "ZTP",
    "IT": "PSV",
    "AT": "CEGH",
    "ES": "PVB",
    "DK": "ETF",
}


def money(amount: float | None, currency: str) -> str:
    """``€2.30m``, ``£450k``: the figure a risk desk reads at a glance."""

    if amount is None:
        return "n/a"
    sign = CURRENCY_SIGN.get((currency or "").upper())
    prefix = "-" if amount < 0 else ""
    value = abs(float(amount))
    if value >= 1e6:
        text = f"{value / 1e6:.2f}m"
    elif value >= 1e3:
        text = f"{value / 1e3:.0f}k"
    else:
        text = f"{value:.0f}"
    return f"{prefix}{sign}{text}" if sign else f"{prefix}{text} {currency}"


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f}%"


def hub_for_zone(zone: str) -> str | None:
    """The hub a balancing zone trades as, if it names one."""

    from eurogas_nexus.application.position_inputs import HUB_CODES

    upper = (zone or "").upper()
    for hub in HUB_CODES:
        if hub in upper:
            return hub
    for key, hub in ZONE_HUB.items():
        if upper == key or upper.startswith(f"{key}-") or upper.endswith(f"-{key}"):
            return hub
    return None


def credit_lines(row: dict) -> list[str]:
    """Two or three lines: the figures, then what would clear or explain the status."""

    currency = row["currency"]
    lines = [
        f"Net exposure {money(row['net_exposure'], currency)} against a "
        f"{money(row['limit'], currency)} limit ({pct(row['utilisation_pct'])}).",
        _breakdown(row),
    ]
    status = row["status"]
    if status == "breach":
        need = row["net_exposure"] - row["limit"]
        lines.append(
            f"Needs {money(need, currency)} of headroom: more collateral, a higher approved "
            "limit or less exposure."
        )
    elif status == "watch":
        lines.append(f"Headroom {money(row['headroom'], currency)} before the limit.")
    elif status == "expired":
        lines.append(f"The line expired on {row['valid_until']}; risk must renew it.")
    elif status == "incomplete":
        lines.append(
            f"{row['unvalued_legs']} legs have no mark for their hub and month, so the "
            "exposure is understated."
        )
    evergreen = int(row.get("open_ended_legs") or 0)
    if evergreen:
        lines.append(
            "1 evergreen contract counts to the end of the gas year."
            if evergreen == 1
            else f"{evergreen} evergreen contracts count to the end of the gas year."
        )
    return lines


def _breakdown(row: dict) -> str:
    currency = row["currency"]
    parts = [f"Replacement {money(row['replacement_exposure'], currency)}"]
    if row.get("receivable_exposure"):
        parts.append(f"plus receivables {money(row['receivable_exposure'], currency)}")
    if row.get("collateral"):
        parts.append(f"less collateral {money(row['collateral'], currency)}")
    legs = int(row.get("legs") or 0)
    return f"{', '.join(parts)} ({legs} leg{'' if legs == 1 else 's'})."


def mandate_lines(row: dict) -> list[str]:
    lines = []
    if row.get("max_net_mwh_per_month"):
        lines.append(
            f"Largest net position {row['largest_net_mwh']:,.0f} MWh in {row['largest_at']} "
            f"against {row['max_net_mwh_per_month']:,.0f} MWh a month "
            f"({pct(row['utilisation_pct'])})."
        )
    if row.get("breaches"):
        lines.append(f"Breaches: {row['breaches']}.")
    if row.get("max_tenor_months") is not None and row.get("furthest_month"):
        lines.append(
            f"Furthest month {row['furthest_month']}; tenor limit {row['max_tenor_months']} "
            "months."
        )
    if row["status"] == "expired":
        lines.append(f"The mandate expired on {row['valid_until']}; risk must renew it.")
    lines.append(f"Books {row['books']}; hubs {row['hubs']}.")
    return lines[:4]
