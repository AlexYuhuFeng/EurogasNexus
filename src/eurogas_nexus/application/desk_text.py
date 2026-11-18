"""Desk wording for figures: one place, so alerts, "Why?" and briefs read the same."""

from __future__ import annotations

import re

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

#: A mandate's breach texts (``domain/risk/limits.py``) as the Chinese desk reads them.
_BREACH_ZH = (
    (re.compile(r"^(\S+) is outside the mandate \((.+)\)$"), "{0}不在授权范围内（{1}）"),
    (re.compile(r"^physical supply is not allowed \((.+)\)$"), "不允许实物供应（{0}）"),
    (re.compile(r"^financial trades are not allowed \((.+)\)$"), "不允许金融交易（{0}）"),
    (re.compile(r"^(\S+) is not an allowed instrument \((.+)\)$"), "{0}不是允许的工具（{1}）"),
    (re.compile(r"^delivery to (.+) is beyond (\d+) months \((.+)\)$"),
     "交付至{0}超出{1}个月期限（{2}）"),
    (re.compile(r"^net ([\d,]+) MWh in (.+) is over ([\d,]+) MWh$"),
     "{1}净头寸{0} MWh，超过{2} MWh"),
    (re.compile(r"^(.+) hedged (\d+)%, above (\d+)%$"), "{0}套保比例{1}%，高于{2}%"),
    (re.compile(r"^(.+) hedged (\d+)%, below (\d+)%$"), "{0}套保比例{1}%，低于{2}%"),
)


def breaches_text(breaches: str, zh: bool) -> str:
    """A mandate's "; "-joined breach texts in the reader's language."""

    if not zh or not breaches:
        return breaches
    out = []
    for part in breaches.split("; "):
        for pattern, template in _BREACH_ZH:
            match = pattern.match(part)
            if match:
                out.append(template.format(*match.groups()))
                break
        else:
            out.append(part)
    return "；".join(out)



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

    from eurogas_nexus.domain.ontology.identity import resolve_hub

    upper = (zone or "").upper()
    # ONT-02: a hub named as a word, by the ontology; "NETHERLANDS" no longer contains THE.
    named = resolve_hub(zone).hub
    if named is not None:
        from eurogas_nexus.domain.ontology.markets import market

        # A superseded hub (GASPOOL, NCG) trades as its successor (THE).
        return market(named).superseded_by or named
    for key, hub in ZONE_HUB.items():
        if upper == key or upper.startswith(f"{key}-") or upper.endswith(f"-{key}"):
            return hub
    return None


def _zh() -> bool:
    from eurogas_nexus.application.reports.lang import zh

    return zh()


def credit_lines(row: dict) -> list[str]:
    """Two or three lines: the figures, then what would clear or explain the status (in the
    interface's language, ``reports.lang``)."""

    currency = row["currency"]
    zh = _zh()
    lines = [
        (f"净敞口{money(row['net_exposure'], currency)}，限额{money(row['limit'], currency)}"
         f"（{pct(row['utilisation_pct'])}）。") if zh else
        (f"Net exposure {money(row['net_exposure'], currency)} against a "
         f"{money(row['limit'], currency)} limit ({pct(row['utilisation_pct'])})."),
        _breakdown(row),
    ]
    status = row["status"]
    if status == "breach":
        need = row["net_exposure"] - row["limit"]
        lines.append(
            f"需要{money(need, currency)}的额度空间：增加抵押、提高核准限额或减少敞口。" if zh else
            f"Needs {money(need, currency)} of headroom: more collateral, a higher approved "
            "limit or less exposure."
        )
    elif status == "watch":
        lines.append(f"距限额尚有{money(row['headroom'], currency)}。" if zh else
                     f"Headroom {money(row['headroom'], currency)} before the limit.")
    elif status == "expired":
        lines.append(f"该额度已于{row['valid_until']}到期；需由风控续期。" if zh else
                     f"The line expired on {row['valid_until']}; risk must renew it.")
    elif status == "incomplete":
        lines.append(
            f"{row['unvalued_legs']}笔交易缺少对应枢纽与月份的估值，敞口被低估。" if zh else
            f"{row['unvalued_legs']} legs have no mark for their hub and month, so the "
            "exposure is understated."
        )
    evergreen = int(row.get("open_ended_legs") or 0)
    if evergreen:
        lines.append(
            f"{evergreen}份长期合同计至气年末。" if zh else
            "1 evergreen contract counts to the end of the gas year."
            if evergreen == 1
            else f"{evergreen} evergreen contracts count to the end of the gas year."
        )
    return lines


def _breakdown(row: dict) -> str:
    currency = row["currency"]
    legs = int(row.get("legs") or 0)
    if _zh():
        parts = [f"重置敞口{money(row['replacement_exposure'], currency)}"]
        if row.get("receivable_exposure"):
            parts.append(f"加应收款{money(row['receivable_exposure'], currency)}")
        if row.get("collateral"):
            parts.append(f"减抵押{money(row['collateral'], currency)}")
        return f"{'，'.join(parts)}（{legs}笔）。"
    parts = [f"Replacement {money(row['replacement_exposure'], currency)}"]
    if row.get("receivable_exposure"):
        parts.append(f"plus receivables {money(row['receivable_exposure'], currency)}")
    if row.get("collateral"):
        parts.append(f"less collateral {money(row['collateral'], currency)}")
    return f"{', '.join(parts)} ({legs} leg{'' if legs == 1 else 's'})."


def mandate_lines(row: dict) -> list[str]:
    zh = _zh()
    lines = []
    if row.get("max_net_mwh_per_month"):
        lines.append(
            (f"最大净头寸{row['largest_net_mwh']:,.0f} MWh（{row['largest_at']}），每月上限"
             f"{row['max_net_mwh_per_month']:,.0f} MWh（{pct(row['utilisation_pct'])}）"
             f"。") if zh else
            (f"Largest net position {row['largest_net_mwh']:,.0f} MWh in {row['largest_at']} "
             f"against {row['max_net_mwh_per_month']:,.0f} MWh a month "
             f"({pct(row['utilisation_pct'])}).")
        )
    if row.get("breaches"):
        lines.append(f"超限：{breaches_text(row['breaches'], True)}。" if zh else
                     f"Breaches: {row['breaches']}.")
    if row.get("max_tenor_months") is not None and row.get("furthest_month"):
        lines.append(
            f"最远月份{row['furthest_month']}；期限上限{row['max_tenor_months']}个月。" if zh else
            f"Furthest month {row['furthest_month']}; tenor limit {row['max_tenor_months']} "
            "months."
        )
    if row["status"] == "expired":
        lines.append(f"该授权已于{row['valid_until']}到期；需由风控续期。" if zh else
                     f"The mandate expired on {row['valid_until']}; risk must renew it.")
    lines.append(f"账簿{row['books']}；枢纽{row['hubs']}。" if zh else
                 f"Books {row['books']}; hubs {row['hubs']}.")
    return lines[:4]
