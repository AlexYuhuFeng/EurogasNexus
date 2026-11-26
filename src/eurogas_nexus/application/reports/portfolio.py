"""Portfolio and outlook: the book as a desk head or a CFO reads it, from the stored records.

Six internal sections answer "what's our portfolio like, and what are we expecting for the
rest of the year and next year": the supply portfolio by delivery type and counterparty, the
trades and sales by hub, country and counterparty, realised prices and the unrealised value,
the forward view (contracted against open volume per period, hedge ratio, approved hedge
bands, sensitivities and VaR), LNG cargoes and regas slots, and how the book is run (sale
routes, hedge programmes, linked strategies).

Every figure is read from the records the Portfolio and Risk pages read, as the caller, in
the books the caller may see: contracts and filled trades as the position ladder builds them
(``ladder_inputs``), contract allocations, the gas-day schedule, the firm's own LNG cargoes
and regas slots, credit lines and hedge approvals. Nothing is estimated here: a figure the
records do not hold (a realised P&L the ETRM has not sent, a budget) is said to be missing,
never filled in.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from eurogas_nexus.application.reports.lang import T, zh
from eurogas_nexus.application.reports.sections import (
    Ctx,
    SectionResult,
    _apply,
    _empty,
    _iso,
    _new,
    is_simulated_source,
    source,
    table,
)

#: Hub to the country its market area serves (sales by country).
HUB_COUNTRY = {"TTF": "NL", "THE": "DE", "NBP": "GB", "PEG": "FR", "ZTP": "BE", "ETF": "DK",
               "GTF": "DK", "CEGH": "AT", "PSV": "IT", "PVB": "ES", "NCG": "DE", "GPL": "DE"}
COUNTRY_NAMES = {
    "NL": ("Netherlands", "荷兰"), "DE": ("Germany", "德国"), "GB": ("Great Britain", "英国"),
    "FR": ("France", "法国"), "BE": ("Belgium", "比利时"), "DK": ("Denmark", "丹麦"),
    "AT": ("Austria", "奥地利"), "IT": ("Italy", "意大利"), "ES": ("Spain", "西班牙"),
    "PL": ("Poland", "波兰"), "NO": ("Norway", "挪威"),
}
#: Delivery types, in print order.
TYPES = ("beach", "pipeline", "hub", "lng_cargo", "lng_term", "lng_master", "other")
TYPE_WORDS = {
    "beach": ("Beach delivery (upstream field)", "岸边交付（上游气田）"),
    "pipeline": ("Pipeline supply at an entry point", "管道供应（入口点交付）"),
    "hub": ("Hub delivered", "枢纽交付"),
    "lng_cargo": ("LNG cargo", "LNG 船货"),
    "lng_term": ("LNG term supply", "LNG 长期供应"),
    "lng_master": ("LNG master agreement (frame)", "LNG 主协议（框架）"),
    "other": ("Other", "其他"),
}
SALE_MODES = {
    "LOCAL_MARKET_SALE": ("sold at its own hub", "在本地枢纽出售"),
    "TARGET_MARKET_SALE": ("sold at another hub over held transport",
                           "经持有的运输容量在其他枢纽出售"),
    "REROUTE_SALE": ("may be rerouted to another exit point", "可改道至其他出口点"),
}
MMBTU_MWH = 0.29307107


def _gwh(mwh: float | None) -> float | None:
    return None if mwh is None else round(mwh / 1000.0, 1)


def _words(pair: tuple[str, str]) -> str:
    return pair[1] if zh() else pair[0]


def _lower_words(pair: tuple[str, str]) -> str:
    """The words in running text: lower case in English except an initialism (LNG)."""

    if zh():
        return pair[1]
    head, _, rest = pair[0].partition(" ")
    head = head if head.isupper() else head.lower()
    return f"{head} {rest.lower()}".strip()


def _country(code: str | None) -> str:
    return _words(COUNTRY_NAMES.get(code or "", (code or "-", code or "-")))


def _num(value: float | None, unit: str = "", digits: int | None = None) -> str:
    from eurogas_nexus.application.reports.commentary import number

    return number(value, unit, digits)


def _money(amount: float | None, currency: str) -> str:
    from eurogas_nexus.application.desk_text import money

    return money(amount, currency)


def _sign_money(amount: float, currency: str) -> str:
    return ("+" if amount >= 0 else "") + _money(amount, currency)


def _marks_simulated(warnings: list[str]) -> bool:
    """Whether the ladder read marked the book with prices from a simulated source.

    One test, the ladder's own (``is_simulated_marks_warning``): this module first matched the
    warning's wording, which changed when the demo labels went, and then never said a mark was
    simulated (AGENTS.md rule 17)."""

    from eurogas_nexus.application.position_inputs import is_simulated_marks_warning

    return any(is_simulated_marks_warning(w) for w in warnings)


def _month_start(day: date, offset: int = 0) -> date:
    month = day.month - 1 + offset
    return date(day.year + month // 12, month % 12 + 1, 1)


def _overlap(first: date, last: date, start: date, end: date) -> int:
    lo, hi = max(first, start), min(last, end)
    return max(0, (hi - lo).days + 1)


def _label(month: str) -> str:
    first = date.fromisoformat(month + "-01")
    return f"{first:%b-%y}"


# ================================================================================= read


def _window(ctx: Ctx) -> dict[str, date]:
    today = ctx.today
    look_from = min(date(today.year, 1, 1), ctx.plan.period_start or today)
    return {"today": today, "look_from": look_from, "year_end": date(today.year, 12, 31),
            "next_start": date(today.year + 1, 1, 1), "next_end": date(today.year + 1, 12, 31)}


def read(ctx: Ctx) -> dict[str, Any]:
    """Everything the portfolio sections read, once per report (cached on the context)."""

    if "portfolio" in ctx.cache:
        return ctx.cache["portfolio"]
    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.db.models import (
        ContractDeliveryRecord,
        CreditLineRecord,
        GasDayScheduleLineRecord,
        HedgeApprovalRecord,
        LngCargoRecord,
        RegasSlotRecord,
        StrategyRecord,
    )
    from eurogas_nexus.security.portfolio_scope import restrict

    w = _window(ctx)
    inputs = ladder_inputs(ctx.caller, w["today"], w["today"], w["next_end"])
    session = ctx.session
    contract_ids = [c.contract_id for c in inputs.contracts]
    deliveries = []
    if contract_ids:
        deliveries = (
            session.query(ContractDeliveryRecord)
            .filter(ContractDeliveryRecord.contract_id.in_(contract_ids))
            .filter(ContractDeliveryRecord.gas_day >= w["look_from"])
            .filter(ContractDeliveryRecord.gas_day < w["today"])
            .all()
        )
    schedule = (restrict(session.query(GasDayScheduleLineRecord), GasDayScheduleLineRecord,
                         session)
                .filter(GasDayScheduleLineRecord.gas_day == w["today"]).all())
    cargoes = (restrict(session.query(LngCargoRecord), LngCargoRecord, session)
               .filter(LngCargoRecord.book_id.isnot(None)).filter(LngCargoRecord.book_id != "")
               .all())
    slots = (restrict(session.query(RegasSlotRecord), RegasSlotRecord, session)
             .filter(RegasSlotRecord.book_id.isnot(None))
             .filter(RegasSlotRecord.window_end_utc >= ctx.day_bound(w["today"])).all())
    credit = session.query(CreditLineRecord).all()
    approvals = session.query(HedgeApprovalRecord).all()
    linked_ids = sorted({o.linked_strategy_id for o in inputs.orders if o.linked_strategy_id})
    strategies = {}
    if linked_ids:
        strategies = {s.strategy_id: s.name for s in session.query(StrategyRecord)
                      .filter(StrategyRecord.strategy_id.in_(linked_ids)).all()}
    data = {"w": w, "inputs": inputs, "deliveries": deliveries, "schedule": schedule,
            "cargoes": cargoes, "slots": slots, "credit": credit, "approvals": approvals,
            "strategies": strategies, "simulated_marks": _marks_simulated(inputs.warnings)}
    data.update(_extra_reads(ctx, data))
    ctx.cache["portfolio"] = data
    return data


def _extra_reads(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    """Records a deployment adds beside the core book (none on this branch)."""

    return {}


def _notes(contract) -> dict[str, Any]:
    try:
        value = json.loads(contract.notes) if isinstance(contract.notes, str) else contract.notes
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _terms(contract):
    from eurogas_nexus.domain.contracts import kinds

    try:
        return kinds.terms_of(contract.contract_kind, contract.kind_terms)
    except Exception:  # noqa: BLE001 - an unreadable block is reported as untyped
        return None


def counterparty_of(contract, credit, contracts_by_id: dict) -> str:
    """The counterparty a contract faces: its credit line, else the name its terms carry."""

    for line in credit:
        if contract.contract_id in (line.contract_ids or []):
            return line.name
    terms = _terms(contract)
    for attr in ("counterparty_name", "seller_name"):
        value = getattr(terms, attr, None)
        if value:
            return str(value)
    named = _notes(contract).get("counterparty")
    if named:
        return str(named)
    master = contracts_by_id.get(contract.master_contract_id or "")
    if master is not None:
        return counterparty_of(master, credit, contracts_by_id)
    return T("not recorded", "未记录")


def trade_counterparty(order, credit) -> str:
    """A trade's counterparty: the credit line its account names, else the venue it cleared on."""

    label = (order.account_label or "").strip()
    for line in credit:
        names = {line.name, line.counterparty_id, *(line.aliases or [])}
        if label and label in names:
            return line.name
    venue = order.venue or order.provider_id or "-"
    return T(f"{venue} (cleared)", f"{venue}（清算）")


def delivery_type(contract, hub: str | None) -> str:
    from eurogas_nexus.application.reports.catalogue import resolve_hub
    from eurogas_nexus.domain.contracts import kinds

    kind = contract.contract_kind
    if kind == kinds.LNG_CARGO:
        return "lng_cargo"
    if kind == kinds.LNG_MSPA:
        return "lng_master"
    if kind == kinds.LNG_TERM_SPA:
        return "lng_term"
    if kind == kinds.UPSTREAM_TENDER or (contract.resource_type or "") == "BEACH_DELIVERY":
        return "beach"
    point = (contract.delivery_point_name or "").strip()
    if hub and resolve_hub(point) == hub:
        return "hub"
    if hub:
        return "pipeline"
    return "other"


def _price_words(contract) -> tuple[str, float | None, str | None]:
    """(how it is priced, fixed price per MWh or None, currency)."""

    from eurogas_nexus.domain.contracts import kinds

    terms = _terms(contract)
    basis = kinds.price_basis(contract.contract_kind, terms)
    currency = contract.contract_price_currency or "GBP"
    if basis["basis"] == "index":
        diff = basis.get("differential_mwh") or 0.0
        return (f"{basis.get('index')} {diff:+.2f} {basis.get('currency', currency)}/MWh",
                None, basis.get("currency", currency))
    if basis["basis"] == "formula":
        return basis.get("label") or T("formula", "公式"), None, basis.get("currency")
    if basis["basis"] == "fixed":
        return (T("fixed", "固定价") + f" {basis['price_mwh']:.2f} {basis['currency']}/MWh",
                basis["price_mwh"], basis["currency"])
    if contract.contract_kind == kinds.LNG_MSPA:
        return T("per confirmation", "按每船确认"), None, None
    notes = _notes(contract)
    if notes.get("price_basis") in {"index", "formula"}:
        return str(notes.get("index_basis") or notes["price_basis"]), None, currency
    price = float(contract.contract_price_gbp_mwh or 0.0)
    return T("fixed", "固定价") + f" {price:.2f} {currency}/MWh", price, currency


# ================================================================================= supply


def _contract_rows(ctx: Ctx, data: dict[str, Any]) -> list[dict[str, Any]]:
    w = data["w"]
    inputs = data["inputs"]
    by_id = {c.contract_id: c for c in inputs.contracts}
    legs = {leg.reference: leg for leg in inputs.legs if leg.kind == "physical"}
    delivered: dict[str, float] = defaultdict(float)
    for row in data["deliveries"]:
        delivered[row.contract_id] += float(row.allocated_mwh or 0.0)
    rows = []
    for contract in inputs.contracts:
        leg = legs.get(contract.contract_id)
        terms = _terms(contract)
        hub = leg.hub if leg is not None else getattr(terms, "terminal_hub", None)
        kind = delivery_type(contract, hub)
        rest = nxt = 0.0
        window = None
        if leg is not None:
            rest = leg.mwh_per_day * _overlap(leg.first_gas_day, leg.last_gas_day, w["today"],
                                              w["year_end"])
            nxt = leg.mwh_per_day * _overlap(leg.first_gas_day, leg.last_gas_day,
                                             w["next_start"], w["next_end"])
            window = (leg.first_gas_day, leg.last_gas_day)
        elif kind == "lng_cargo" and terms is not None:
            first, last = terms.delivery_days()
            energy = terms.energy_mwh()
            if w["today"] <= first <= w["year_end"]:
                rest = energy
            elif w["next_start"] <= first <= w["next_end"]:
                nxt = energy
            window = (first, last)
        words, fixed, currency = _price_words(contract)
        field = getattr(terms, "field_name", None)
        rows.append({
            "contract_id": contract.contract_id,
            "name": contract.contract_name,
            "type": kind,
            "type_label": _words(TYPE_WORDS[kind]),
            "counterparty": counterparty_of(contract, data["credit"], by_id),
            "point": contract.delivery_point_name,
            "hub": hub or "",
            "field": field or "",
            "price": words,
            "fixed_price": fixed,
            "currency": currency,
            "rest_gwh": _gwh(rest),
            "next_gwh": _gwh(nxt),
            "delivered_gwh": _gwh(delivered.get(contract.contract_id)) or None,
            "delivered_mwh": delivered.get(contract.contract_id, 0.0),
            "window": window,
            "open_ended": bool(leg is not None and leg.open_ended),
            "book": contract.book_id or "",
            "sale_modes": _sale_modes(contract),
        })
    return rows


def _sale_modes(contract) -> list[str]:
    value = contract.eligible_sale_modes
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = [value]
    return [str(v) for v in (value or [])]


def supply(ctx: Ctx) -> SectionResult:
    result = _new("pf_supply")
    data = read(ctx)
    w = data["w"]
    rows = _contract_rows(ctx, data)
    if not rows:
        return _empty(result, T("No supply contract is held in the books you may see",
                                "您可查看的账簿中没有供应合同"), T("Open Contracts", "打开合同"))
    year, nxt = w["today"].year, w["today"].year + 1
    rest_label, next_label = T(f"Rest of {year}", f"{year}年剩余"), T(f"{nxt}", f"{nxt}年")
    result.tables.append(table(
        T("Supply contracts by delivery type", "按交付类型的供应合同"),
        [("name", T("Contract", "合同"), "text"), ("type_label", T("Type", "类型"), "text"),
         ("counterparty", T("Counterparty", "交易对手"), "text"),
         ("point", T("Delivery point", "交付点"), "text"), ("hub", T("Hub", "枢纽"), "text"),
         ("price", T("Price basis", "定价"), "text"),
         ("delivered_gwh", T("Delivered YTD, GWh", "年初至今已交付，GWh"), "num"),
         ("rest_gwh", T(f"{rest_label}, GWh", f"{rest_label}，GWh"), "num"),
         ("next_gwh", T(f"{next_label}, GWh", f"{next_label}，GWh"), "num")],
        [{k: v for k, v in r.items() if k != "window"}
         for r in sorted(rows, key=lambda r: (TYPES.index(r["type"]), -(r["next_gwh"] or 0)))],
    ))
    by_type: dict[str, float] = defaultdict(float)
    by_cp: dict[str, dict[str, float]] = defaultdict(lambda: {"rest": 0.0, "next": 0.0, "n": 0})
    for row in rows:
        by_type[row["type"]] += (row["rest_gwh"] or 0.0) + (row["next_gwh"] or 0.0)
        cp = by_cp[row["counterparty"]]
        cp["rest"] += row["rest_gwh"] or 0.0
        cp["next"] += row["next_gwh"] or 0.0
        cp["n"] += 1
    result.tables.append(table(
        T("Contracted supply by counterparty", "按交易对手的合同供应"),
        [("counterparty", T("Counterparty", "交易对手"), "text"),
         ("contracts", T("Contracts", "合同数"), "text"),
         ("rest_gwh", T(f"{rest_label}, GWh", f"{rest_label}，GWh"), "num"),
         ("next_gwh", T(f"{next_label}, GWh", f"{next_label}，GWh"), "num")],
        [{"counterparty": k, "contracts": str(v["n"]), "rest_gwh": round(v["rest"], 1),
          "next_gwh": round(v["next"], 1)}
         for k, v in sorted(by_cp.items(), key=lambda kv: -(kv[1]["rest"] + kv[1]["next"]))],
    ))
    result.charts.append({
        "id": "fig.pf_supply", "type": "bar",
        "title": T(f"Contracted supply by delivery type, {rest_label.lower()} and {next_label}",
                   f"按交付类型的合同供应，{rest_label}及{next_label}"),
        "unit": "GWh",
        "series": [{"name": T("Contracted", "已签约"),
                    "points": [[_words(TYPE_WORDS[k]), round(by_type[k], 1)]
                               for k in TYPES if by_type.get(k)]}],
    })
    total = sum(by_type.values())
    rest_total = sum(r["rest_gwh"] or 0.0 for r in rows)
    next_total = sum(r["next_gwh"] or 0.0 for r in rows)
    shares = [f"{_lower_words(TYPE_WORDS[k])} "
              f"{100 * by_type[k] / total:.0f}%"
              for k in TYPES if total and by_type.get(k)]
    cps = len({r["counterparty"] for r in rows})
    headline = T(
        f"{_count(len(rows), 'supply contract', 'supply contracts')} with "
        f"{_count(cps, 'counterparty', 'counterparties')} hold "
        f"{_num(rest_total, 'GWh')} for the rest of {year} and {_num(next_total, 'GWh')} for "
        f"{nxt}" + (f": {', '.join(shares)}." if shares else "."),
        f"{len(rows)}份供应合同、{cps}个交易对手，{year}年剩余合同量{_num(rest_total, 'GWh')}，"
        f"{nxt}年{_num(next_total, 'GWh')}" + (f"：{'，'.join(shares)}。" if shares else "。"))
    bullets = []
    beach = [r for r in rows if r["type"] == "beach"]
    if beach:
        names = ", ".join(f"{r['field'] or r['name']} ({r['counterparty']})" for r in beach)
        bullets.append(T(f"Beach delivery comes from {names}.", f"岸边交付来自{names}。"))
    delivered = [r for r in rows if r["delivered_mwh"]]
    if delivered:
        mwh = sum(r["delivered_mwh"] for r in delivered)
        bullets.append(T(
            f"{_num(mwh / 1000, 'GWh')} was delivered under "
            f"{_count(len(delivered), 'contract', 'contracts')} from "
            f"{w['look_from']:%d %b} to {w['today'] - timedelta(days=1):%d %b} (allocations).",
            f"{w['look_from'].month}月{w['look_from'].day}日至"
            f"{(w['today'] - timedelta(days=1)).month}月{(w['today'] - timedelta(days=1)).day}日"
            f"，{len(delivered)}份合同共交付{_num(mwh / 1000, 'GWh')}（分配量）。"))
    # Floating contracts on the ladder (an FOB cargo is off it until sold or discharged).
    floating = [r for r in rows if r["fixed_price"] is None and r["hub"]
                and r["type"] != "lng_master"]
    if floating:
        bullets.append(T(
            f"{_count(len(floating), 'contract floats', 'contracts float')} with an index or "
            "formula "
            f"({', '.join(r['name'] for r in floating[:3])}): the volume is on the ladder, "
            "the price follows the index.",
            f"{len(floating)}份合同按指数或公式浮动定价"
            f"（{'、'.join(r['name'] for r in floating[:3])}）：其量计入头寸，价格随指数变动。"))
    result.sources.append(source(T("Contract register and contract allocations",
                                   "合同登记与合同分配量"), "operator-input", ctx.now, "current"))
    result.methods.append({"key": "pf_volumes", "title": T("Contracted volume", "合同量"),
                           "text": T("Daily contract quantity times the gas days of each period "
                                     "the contract delivers; an evergreen contract counts to "
                                     "the end of the horizon (it renews each gas year); an LNG "
                                     "cargo counts in the month its window opens.",
                                     "每日合同量乘以该期间内合同交付的燃气日数；常青合同计至期末"
                                     "（每个燃气年续期）；LNG 船货计入其装载窗口开始的月份。")})
    result.books = sorted({r["book"] for r in rows if r["book"]})
    return _apply(result, {"headline": headline, "bullets": bullets[:3]})


# ================================================================================= trades


def _trade_rows(ctx: Ctx, data: dict[str, Any]) -> list[dict[str, Any]]:
    w = data["w"]
    legs = {leg.reference: leg for leg in data["inputs"].legs if leg.kind == "financial"}
    contracts = {c.contract_id: c.contract_name for c in data["inputs"].contracts}
    rows = []
    for order in data["inputs"].orders:
        leg = legs.get(order.order_observation_id)
        filled = float(order.filled_quantity_mwh or 0.0)
        if leg is None or filled <= 0 or leg.last_gas_day < w["look_from"]:
            continue
        side = "sell" if leg.mwh_per_day < 0 else "buy"
        days = (leg.last_gas_day - leg.first_gas_day).days + 1
        done = _overlap(leg.first_gas_day, leg.last_gas_day, w["look_from"],
                        w["today"] - timedelta(days=1))
        rows.append({
            "trade": order.order_observation_id,
            "traded": str(order.observed_at_utc)[:10],
            "counterparty": trade_counterparty(order, data["credit"]),
            "hub": leg.hub,
            "country": HUB_COUNTRY.get(leg.hub, ""),
            "side": side,
            "side_label": T("Sell", "卖出") if side == "sell" else T("Buy", "买入"),
            "delivery": _span(leg.first_gas_day, leg.last_gas_day),
            "mwh": filled,
            "gwh": _gwh(filled),
            "price": float(order.price),
            "unit": f"{order.currency}/MWh",
            "currency": order.currency,
            "delivered_mwh": abs(leg.mwh_per_day) * done,
            "delivered_gwh": _gwh(abs(leg.mwh_per_day) * done),
            "share_done": done / days if days else 0.0,
            "linked": contracts.get(order.linked_resource_id or "", order.linked_resource_id or ""),
            "strategy": data["strategies"].get(order.linked_strategy_id or "", ""),
            "book": leg.book_id,
            "simulated": is_simulated_source(order.source_system),
        })
    return rows


def _vwap(rows: list[dict[str, Any]], weight: str = "mwh") -> float | None:
    total = sum(r[weight] for r in rows)
    return sum(r["price"] * r[weight] for r in rows) / total if total else None


def trades(ctx: Ctx) -> SectionResult:
    result = _new("pf_trades")
    data = read(ctx)
    w = data["w"]
    rows = _trade_rows(ctx, data) + _obligation_rows(ctx, data)
    offtake = [line for line in data["schedule"] if line.direction == "out"]
    if not rows and not offtake:
        return _empty(result, T("No filled trade or scheduled sale is held in the books you "
                                "may see", "您可查看的账簿中没有成交或计划销售"),
                      T("Open Trades", "打开交易"))
    sells = [r for r in rows if r["side"] == "sell"]
    buys = [r for r in rows if r["side"] == "buy"]
    if rows:
        result.tables.append(table(
            T("Filled trades and sales delivering this year or later",
              "本年及以后交付的成交与销售"),
            [("traded", T("Traded", "成交日"), "date"),
             ("counterparty", T("Counterparty", "交易对手"), "text"),
             ("hub", T("Hub", "枢纽"), "text"), ("side_label", T("Side", "方向"), "text"),
             ("delivery", T("Delivery", "交付期"), "text"), ("gwh", "GWh", "num"),
             ("price", T("Price", "价格"), "num"), ("unit", T("Unit", "单位"), "text"),
             ("delivered_gwh", T("Delivered, GWh", "已交付，GWh"), "num")],
            sorted(rows, key=lambda r: r["traded"], reverse=True),
        ))
    by_hub: dict[str, list[dict]] = defaultdict(list)
    for row in sells:
        by_hub[row["hub"]].append(row)
    if sells:
        result.tables.append(table(
            T("Sales by hub and country", "按枢纽与国家的销售"),
            [("hub", T("Hub", "枢纽"), "text"), ("country", T("Country", "国家"), "text"),
             ("gwh", T("Sold, GWh", "已售，GWh"), "num"),
             ("delivered_gwh", T("Delivered, GWh", "已交付，GWh"), "num"),
             ("price", T("Average price", "平均价格"), "num"), ("unit", T("Unit", "单位"), "text"),
             ("counterparties", T("Counterparties", "交易对手"), "text")],
            [{"hub": hub, "country": _country(HUB_COUNTRY.get(hub)),
              "gwh": round(sum(r["gwh"] for r in items), 1),
              "delivered_gwh": round(sum(r["delivered_gwh"] or 0 for r in items), 1),
              "price": None if _vwap(items) is None else round(_vwap(items), 2),
              "unit": items[0]["unit"],
              "counterparties": ", ".join(sorted({r["counterparty"] for r in items}))}
             for hub, items in sorted(by_hub.items(), key=lambda kv: -sum(r["mwh"] for r in
                                                                         kv[1]))],
        ))
        result.charts.append({
            "id": "fig.pf_trades", "type": "bar",
            "title": T("Sales by hub", "按枢纽的销售"), "unit": "GWh",
            "series": [{"name": T("Sold", "已售"),
                        "points": [[f"{hub} ({HUB_COUNTRY.get(hub, '-')})",
                                    round(sum(r["gwh"] for r in items), 1)]
                                   for hub, items in sorted(by_hub.items(), key=lambda kv: -sum(
                                       r["mwh"] for r in kv[1]))]}],
        })
    by_cp: dict[str, dict[str, float]] = defaultdict(lambda: {"sold": 0.0, "bought": 0.0, "n": 0})
    for row in rows:
        entry = by_cp[row["counterparty"]]
        entry["sold" if row["side"] == "sell" else "bought"] += row["mwh"]
        entry["n"] += 1
    if offtake:
        result.tables.append(table(
            T(f"Physical flows scheduled out of the book, gas day {w['today']:%d %b}",
              f"{w['today'].month}月{w['today'].day}日燃气日计划流出"),
            [("label", T("Line", "项目"), "text"), ("kind", T("Kind", "类型"), "text"),
             ("point", T("Point", "地点"), "text"), ("hub", T("Hub", "枢纽"), "text"),
             ("mwh", "MWh", "num")],
            [{"label": line.label, "kind": _schedule_kind(line.kind), "point": line.point or "",
              "hub": line.hub, "mwh": float(line.quantity_mwh)} for line in offtake],
        ))
    sold = sum(r["mwh"] for r in sells)
    bought = sum(r["mwh"] for r in buys)
    hubs = sorted(by_hub, key=lambda h: -sum(r["mwh"] for r in by_hub[h]))
    if rows:
        headline = T(
            f"{_count(len(rows), 'filled trade or sale', 'filled trades and sales')} with "
            f"{_count(len(by_cp), 'counterparty', 'counterparties')}: "
            f"{_num(sold / 1000, 'GWh')} sold" + (f" and {_num(bought / 1000, 'GWh')} bought"
                                                  if bought else "")
            + (f", sold at {_join(hubs)}." if hubs else "."),
            f"{len(rows)}笔成交与销售，{len(by_cp)}个交易对手：已售{_num(sold / 1000, 'GWh')}"
            + (f"，买入{_num(bought / 1000, 'GWh')}" if bought else "")
            + (f"，销售枢纽为{'、'.join(hubs)}。" if hubs else "。"))
    else:
        headline = T("No filled trade is held; the gas day schedule holds the physical sales.",
                     "没有成交记录；燃气日计划中有实物销售。")
    bullets = []
    for hub in hubs[:2]:
        items = by_hub[hub]
        price = _vwap(items)
        sold_gwh = _num(sum(r["mwh"] for r in items) / 1000, "GWh")
        done_gwh = _num(sum(r["delivered_mwh"] for r in items) / 1000, "GWh")
        where = _country(HUB_COUNTRY.get(hub))
        done = sum(r["delivered_mwh"] for r in items)
        bullets.append(T(
            f"At {hub} ({where}) {sold_gwh} is sold at an average "
            f"{_num(price, items[0]['unit'])}"
            + (f", {done_gwh} of it delivered." if done else ", none of it delivered yet."),
            f"{hub}（{where}）已售{sold_gwh}，均价{_num(price, items[0]['unit'])}，"
            + (f"其中已交付{done_gwh}。" if done else "尚未交付。")))
    if offtake:
        total = sum(float(line.quantity_mwh) for line in offtake)
        bullets.append(T(
            f"Gas day {w['today']:%d %b} schedules {_num(total, 'MWh')} out of the book "
            f"({len(offtake)} lines: customer offtake, storage and exports).",
            f"{w['today'].month}月{w['today'].day}日燃气日计划流出{_num(total, 'MWh')}"
            f"（{len(offtake)}项：客户提货、储气与出口）。"))
    result.simulated = any(r["simulated"] for r in rows)
    result.sources.append(source(T("Filled trades in the books visible to the report",
                                   "报告可见账簿中的成交"), "operator-input", ctx.now, "current"))
    if offtake:
        result.sources.append(source(T("Gas day schedule", "燃气日计划"), "operator-input",
                                     ctx.now, "current"))
    result.methods.append({"key": "pf_trades", "title": T("Trades and sales", "成交与销售"),
                           "text": T("Filled quantity of each trade; delivered is the share of "
                                     "its gas days before today. A trade's counterparty is the "
                                     "credit line its account names, else the venue it cleared "
                                     "on. Average price is weighted by volume.",
                                     "每笔交易的成交量；已交付为今日之前的燃气日部分。交易对手为"
                                     "账户所对应的信用额度，否则为清算场所。均价按量加权。")})
    result.books = sorted({r["book"] for r in rows if r.get("book")}
                          | {line.book_id for line in offtake if line.book_id})
    return _apply(result, {"headline": headline, "bullets": bullets[:3]})


def _obligation_rows(ctx: Ctx, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Delivery obligations a deployment holds beside trades (none on this branch)."""

    return []


def _schedule_kind(kind: str) -> str:
    words = {"customer_offtake": ("customer offtake", "客户提货"), "export": ("export", "出口"),
             "storage_injection": ("storage injection", "注入储气"), "sale": ("sale", "销售")}
    return _words(words.get(kind, (kind, kind)))


# ================================================================================= P&L


def _ladder(data: dict[str, Any], legs, *, start: date, end: date, fx=None, currency=None):
    from eurogas_nexus.domain.portfolio.position_ladder import ladder_report

    inputs = data["inputs"]
    return ladder_report(legs, horizon_start=start, horizon_end=end, marks=inputs.marks,
                         daily_closes_by_hub=inputs.closes, fx_by_hub=fx,
                         reporting_currency=currency)


def _mtm(data: dict[str, Any], legs, start: date, end: date) -> float | None:
    from eurogas_nexus.domain.portfolio.position_ladder import mark_to_market

    if not legs:
        return None
    value, _missing = mark_to_market(legs, data["inputs"].marks, horizon_start=start,
                                     horizon_end=end)
    return value


def pnl(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.projections.portfolio_reads import pnl_snapshots
    from eurogas_nexus.domain.ontology.markets import quote_currency

    result = _new("pf_pnl")
    data = read(ctx)
    w = data["w"]
    legs = data["inputs"].legs
    if not legs:
        return _empty(result, T("No position is held in the books you may see",
                                "您可查看的账簿中没有头寸"), T("Open Position", "打开头寸"))
    hubs = sorted({leg.hub for leg in legs})
    unreal = []
    for hub in hubs:
        mine = [leg for leg in legs if leg.hub == hub]
        phys = [leg for leg in mine if leg.kind == "physical"]
        fin = [leg for leg in mine if leg.kind == "financial"]
        total = _mtm(data, mine, w["today"], w["next_end"])
        unreal.append({
            "hub": hub, "currency": quote_currency(hub),
            "supply": _round(_mtm(data, phys, w["today"], w["next_end"])),
            "trades": _round(_mtm(data, fin, w["today"], w["next_end"])),
            "total": _round(total),
            "rest": _round(_mtm(data, mine, w["today"], w["year_end"])),
            "next": _round(_mtm(data, mine, w["next_start"], w["next_end"])),
        })
    result.tables.append(table(
        T(f"Unrealised value of the forward book against today's marks, to {w['next_end']:%b %Y}",
          f"按今日标记价计的远期账簿未实现价值，至{w['next_end'].year}年{w['next_end'].month}月"),
        [("hub", T("Hub", "枢纽"), "text"),
         ("supply", T("Supply contracts", "供应合同"), "signed"),
         ("trades", T("Trades", "交易"), "signed"),
         ("rest", T(f"Rest of {w['today'].year}", f"{w['today'].year}年剩余"), "signed"),
         ("next", f"{w['next_start'].year}", "signed"),
         ("total", T("Total", "合计"), "signed"), ("currency", T("Currency", "货币"), "text")],
        unreal,
    ))
    # Realised prices: what was delivered before today, at its contract and trade prices.
    realised = []
    contract_rows = _contract_rows(ctx, data)
    trade_rows = [r for r in _trade_rows(ctx, data) if r["side"] == "sell"]
    for hub in hubs:
        cost_rows = [r for r in contract_rows if r["hub"] == hub and r["delivered_mwh"]
                     and r["fixed_price"] is not None]
        supplied = sum(r["delivered_mwh"] for r in cost_rows)
        cost = (sum(r["fixed_price"] * r["delivered_mwh"] for r in cost_rows) / supplied
                if supplied else None)
        sales = [r for r in trade_rows if r["hub"] == hub and r["delivered_mwh"]]
        sold = sum(r["delivered_mwh"] for r in sales)
        price = _vwap(sales, "delivered_mwh")
        currency = quote_currency(hub)
        same = all(r["currency"] == currency for r in cost_rows) and all(
            r["currency"] == currency for r in sales)
        if not supplied and not sold:
            continue
        realised.append({
            "hub": hub, "supplied_gwh": _gwh(supplied) if supplied else None,
            "cost": None if cost is None else round(cost, 2),
            "sold_gwh": _gwh(sold) if sold else None,
            "price": None if price is None else round(price, 2),
            "margin": round(price - cost, 2) if same and price is not None and cost is not None
            else None,
            "unit": f"{currency}/MWh",
        })
    yesterday = w["today"] - timedelta(days=1)
    if realised:
        result.tables.append(table(
            T(f"Realised prices on gas delivered {w['look_from']:%d %b} to {yesterday:%d %b %Y}",
              f"{w['look_from'].month}月{w['look_from'].day}日至{yesterday.month}月"
              f"{yesterday.day}日已交付天然气的实现价格"),
            [("hub", T("Hub", "枢纽"), "text"),
             ("supplied_gwh", T("Supply delivered, GWh", "已交付供应，GWh"), "num"),
             ("cost", T("Average supply cost", "平均供应成本"), "num"),
             ("sold_gwh", T("Sales delivered, GWh", "已交付销售，GWh"), "num"),
             ("price", T("Average sale price", "平均销售价"), "num"),
             ("margin", T("Sale over cost", "售价高于成本"), "signed"),
             ("unit", T("Unit", "单位"), "text")],
            realised,
        ))
    latest: dict[str, Any] = {}
    for snap in pnl_snapshots(ctx.session, principal_id=ctx.caller.principal_id):
        if snap.portfolio_id not in latest:
            latest[snap.portfolio_id] = snap
    if latest:
        result.tables.append(table(
            T("Realised and unrealised P&L imported from the ETRM",
              "自 ETRM 导入的已实现与未实现损益"),
            [("portfolio", T("Portfolio", "组合"), "text"),
             ("realised", T("Realised (GBP)", "已实现（GBP）"), "signed"),
             ("unrealised", T("Unrealised (GBP)", "未实现（GBP）"), "signed"),
             ("valued", T("Valued", "估值时间"), "datetime")],
            [{"portfolio": pid, "realised": s.realized_pnl_gbp, "unrealised": s.unrealized_pnl_gbp,
              "valued": _iso(s.valuation_time_utc)} for pid, s in sorted(latest.items())],
        ))
    valued = [u for u in unreal if u["total"] is not None]
    if valued:
        headline = T(
            "Unrealised, the forward book is worth "
            + _join([f"{_sign_money(u['total'], u['currency'])} at {u['hub']}" for u in valued])
            + f" against today's marks to {w['next_end']:%b %Y}.",
            "按今日标记价，远期账簿未实现价值为"
            + "，".join(f"{u['hub']} {_sign_money(u['total'], u['currency'])}" for u in valued)
            + f"（至{w['next_end'].year}年{w['next_end'].month}月）。")
    else:
        headline = T("The forward book is not valued: no mark is held for its hubs and months.",
                     "远期账簿未估值：其枢纽与月份没有标记价。")
    bullets = []
    for row in realised[:2]:
        if row["price"] is not None and row["cost"] is not None:
            bullets.append(T(
                f"Delivered so far at {row['hub']}: sales at {_num(row['price'], row['unit'])} "
                f"against supply at {_num(row['cost'], row['unit'])} average cost"
                + (f" ({row['margin']:+.2f} {row['unit']})." if row["margin"] is not None else "."),
                f"{row['hub']}已交付：销售均价{_num(row['price'], row['unit'])}，供应平均成本"
                f"{_num(row['cost'], row['unit'])}"
                + (f"（{row['margin']:+.2f} {row['unit']}）。" if row["margin"] is not None
                   else "。")))
        elif row["cost"] is not None:
            bullets.append(T(
                f"Supply delivered so far at {row['hub']}: {_num(row['supplied_gwh'], 'GWh')} at "
                f"{_num(row['cost'], row['unit'])} average cost; no delivered sale is recorded "
                "against it.",
                f"{row['hub']}已交付供应{_num(row['supplied_gwh'], 'GWh')}，平均成本"
                f"{_num(row['cost'], row['unit'])}；无对应的已交付销售记录。"))
    if not latest:
        bullets.append(T("No realised P&L is held for these books: the ETRM's settled P&L is "
                         "not imported, so realised prices are shown instead.",
                         "这些账簿没有已实现损益：ETRM 的结算损益尚未导入，因此改为显示实现价格。"))
    result.warnings.append(T("No budget or plan figures are held in the platform, so no variance "
                             "against budget is shown.",
                             "平台中没有预算或计划数据，因此不显示与预算的差异。"))
    result.simulated = data["simulated_marks"]
    result.sources.append(source(T("Position ladder and its marks", "头寸阶梯及其标记价"),
                                 "operator-input", ctx.now, "current"))
    result.methods.append({"key": "pf_unrealised", "title": T("Unrealised value", "未实现价值"),
                           "text": T("Mark minus contract or trade price, times the MWh of each "
                                     "remaining delivery month (the position ladder's "
                                     "mark-to-market), per hub in its own currency. Floating-"
                                     "price contracts carry no fixed price and are not valued.",
                                     "标记价减合同或交易价格，乘以每个剩余交付月的 MWh（头寸阶梯的"
                                     "盯市），各枢纽以其本币计。浮动价合同没有固定价格，不估值。")})
    result.methods.append({"key": "pf_realised", "title": T("Realised prices", "实现价格"),
                           "text": T("Supply cost: allocated MWh times the fixed contract price; "
                                     "sale price: delivered MWh of each sale times its price. "
                                     "Both volume-weighted. Realised P&L in money is the ETRM's "
                                     "and is shown only when imported.",
                                     "供应成本：分配 MWh 乘以固定合同价；销售价：每笔销售已"
                                     "交付 MWh 乘以其价格。均按量加权。货币形式的已实现损益"
                                     "来自 ETRM，仅在导入后显示。")})
    result.books = sorted({leg.book_id for leg in legs if leg.book_id})
    return _apply(result, {"headline": headline, "bullets": bullets[:3]})


def _count(n: int, one: str, other: str) -> str:
    return f"{n} {one if n == 1 else other}"


def _day(day: date, *, year: bool = False) -> str:
    """A date in a table cell: 22 Oct 26 in English, 2026年10月22日 in Chinese."""

    if zh():
        return (f"{day.year}年" if year else "") + f"{day.month}月{day.day}日"
    return f"{day:%d %b %y}" if year else f"{day:%d %b}"


def _span(first: date, last: date) -> str:
    return (f"{_day(first, year=True)}至{_day(last, year=True)}" if zh()
            else f"{_day(first)} – {_day(last, year=True)}")


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 0)


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ================================================================================= outlook


def _buckets(w: dict[str, date]) -> list[tuple[str, date, date]]:
    year = w["next_start"].year
    out = [(T(f"Rest of {w['today'].year}", f"{w['today'].year}年剩余"), w["today"],
            w["year_end"])]
    for q in range(4):
        first = date(year, 3 * q + 1, 1)
        last = _month_start(first, 3) - timedelta(days=1)
        out.append((f"Q{q + 1}-{year % 100:02d}", first, last))
    out.append((T(f"Calendar {year}", f"{year}全年"), w["next_start"], w["next_end"]))
    return out


def outlook(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.application.position_inputs import fx_by_hub_for
    from eurogas_nexus.application.projections.daily_closes import in_native_unit
    from eurogas_nexus.domain.ontology.markets import quote_currency
    from eurogas_nexus.domain.portfolio.position_ladder import build_ladder

    result = _new("pf_outlook")
    data = read(ctx)
    w = data["w"]
    legs = data["inputs"].legs
    if not legs:
        return _empty(result, T("No position is held in the books you may see",
                                "您可查看的账簿中没有头寸"), T("Open Position", "打开头寸"))
    ladder = build_ladder(legs, horizon_start=w["today"], horizon_end=w["next_end"])
    hubs = sorted({row.hub for row in ladder})
    months = sorted({row.month for row in ladder})
    cell = {(row.hub, row.month): row for row in ladder}

    def totals(first: date, last: date, hub: str | None = None) -> dict[str, float]:
        out = {"supply": 0.0, "sold": 0.0, "net": 0.0}
        for row in ladder:
            if hub and row.hub != hub:
                continue
            month = date.fromisoformat(row.month + "-01")
            if not (first.replace(day=1) <= month <= last):
                continue
            out["supply"] += max(row.physical_mwh, 0.0) + max(row.financial_mwh, 0.0)
            out["sold"] += -min(row.physical_mwh, 0.0) - min(row.financial_mwh, 0.0)
            out["net"] += row.net_mwh
        return out

    bucket_rows = []
    for label, first, last in _buckets(w):
        t = totals(first, last)
        row = {"period": label, "supply": _gwh(t["supply"]), "sold": _gwh(t["sold"]),
               "open": _gwh(t["net"]),
               "hedged": round(100 * t["sold"] / t["supply"], 0) if t["supply"] else None}
        row["sold_share"] = "-" if row["hedged"] is None else f"{row['hedged']:.0f}%"
        for hub in hubs[:4]:
            row[f"open_{hub}"] = _gwh(totals(first, last, hub)["net"])
        bucket_rows.append(row)
    result.tables.append(table(
        T("Contracted against open volume by period (GWh; long positive)",
          "按期间的合同量与敞口（GWh；多头为正）"),
        [("period", T("Period", "期间"), "text"), ("supply", T("Bought", "买入"), "num"),
         ("sold", T("Sold", "卖出"), "num"), ("open", T("Open", "敞口"), "signed"),
         ("sold_share", T("Sold share", "已售比例"), "text")]
        + [(f"open_{hub}", T(f"Open {hub}", f"{hub}敞口"), "signed") for hub in hubs[:4]],
        bucket_rows,
    ))
    monthly = []
    for month in months:
        row = {"month": _label(month)}
        for hub in hubs:
            c = cell.get((hub, month))
            row[f"{hub}_phys"] = _gwh(c.physical_mwh) if c else 0.0
            row[f"{hub}_fin"] = _gwh(c.financial_mwh) if c else 0.0
            row[f"{hub}_net"] = _gwh(c.net_mwh) if c else 0.0
        monthly.append(row)
    result.annex.append(table(
        T("Position by delivery month and hub, GWh (physical, financial, net)",
          "按交付月与枢纽的头寸，GWh（实物、金融、净）"),
        [("month", T("Month", "月份"), "text")]
        + [c for hub in hubs for c in (
            (f"{hub}_phys", T(f"{hub} physical", f"{hub}实物"), "signed"),
            (f"{hub}_fin", T(f"{hub} financial", f"{hub}金融"), "signed"),
            (f"{hub}_net", T(f"{hub} net", f"{hub}净"), "signed"))],
        monthly,
    ))
    result.charts.append({
        "id": "fig.pf_outlook", "type": "stacked_bar", "months": True,
        "title": T("Open position by delivery month", "按交付月的敞口"), "unit": "GWh",
        "series": [{"name": hub, "points": [[m + "-01", _gwh(cell[(hub, m)].net_mwh)
                                             if (hub, m) in cell else 0.0] for m in months]}
                   for hub in hubs],
    })
    # Approved hedge bands (the Risk page's deal hedge usage over the report horizon).
    hedge = _hedge_bands(data)
    if hedge:
        result.tables.append(table(
            T("Hedge cover against risk's approved bands", "对照风险部门批准区间的对冲覆盖"),
            [("contract", T("Contract", "合同"), "text"),
             ("band", T("Approved band", "批准区间"), "text"),
             ("range", T("Hedged", "已对冲"), "text"),
             ("outside", T("Months outside", "区间外月份"), "text"),
             ("approval", T("Approval", "批准"), "text")],
            hedge,
        ))
    # Sensitivities and VaR on the open position.
    sens = []
    for hub in hubs:
        open_rest = totals(w["today"], w["year_end"], hub)["net"]
        open_next = totals(w["next_start"], w["next_end"], hub)["net"]
        currency = quote_currency(hub)
        step, step_unit = 1.0, f"1 {currency}/MWh"
        if hub == "NBP":
            # The desk quotes NBP in pence per therm: one p/th in GBP per MWh.
            per_th, _unit = in_native_unit("NBP", 1.0, "GBP/MWh")
            if per_th:
                step, step_unit = 1.0 / per_th, "1 p/th"
        sens.append({"hub": hub, "move": step_unit,
                     "rest": round(open_rest * step, 0), "next": round(open_next * step, 0),
                     "currency": currency})
    result.tables.append(table(
        T("Value change of the open position for a one-unit price rise",
          "价格上升一个单位时敞口价值的变化"),
        [("hub", T("Hub", "枢纽"), "text"), ("move", T("Price rise", "价格上升"), "text"),
         ("rest", T(f"Rest of {w['today'].year}", f"{w['today'].year}年剩余"), "signed"),
         ("next", f"{w['next_start'].year}", "signed"),
         ("currency", T("Currency", "货币"), "text")],
        sens,
    ))
    fx, _missing = fx_by_hub_for(set(hubs), "EUR", data["inputs"].eur_rates)
    var, var_days = None, 0
    if fx and len(fx) == len(hubs):
        report = _ladder(data, legs, start=w["today"], end=w["next_end"], fx=fx, currency="EUR")
        var, var_days = report.var_95_1d, report.var_observations
    rest = bucket_rows[0]
    year_row = bucket_rows[-1]
    headline = T(
        f"Rest of {w['today'].year}: {_num(rest['supply'], 'GWh')} bought, "
        f"{_num(rest['sold'], 'GWh')} sold, {_num(rest['open'], 'GWh')} open"
        + (f" ({rest['hedged']:.0f}% sold)" if rest["hedged"] is not None else "")
        + f"; {w['next_start'].year}: {_num(year_row['open'], 'GWh')} open of "
        f"{_num(year_row['supply'], 'GWh')} bought"
        + (f" ({year_row['hedged']:.0f}% sold)." if year_row["hedged"] is not None else "."),
        f"{w['today'].year}年剩余：买入{_num(rest['supply'], 'GWh')}，卖出"
        f"{_num(rest['sold'], 'GWh')}，敞口{_num(rest['open'], 'GWh')}"
        + (f"（已售{rest['hedged']:.0f}%）" if rest["hedged"] is not None else "")
        + f"；{w['next_start'].year}年：买入{_num(year_row['supply'], 'GWh')}中敞口"
        f"{_num(year_row['open'], 'GWh')}"
        + (f"（已售{year_row['hedged']:.0f}%）。" if year_row["hedged"] is not None else "。"))
    bullets = []
    outside = [h for h in hedge if h["status"] == "breach"]
    for item in outside[:1]:
        bullets.append(T(
            f"{item['contract']} is hedged {item['range']} against its approved {item['band']} "
            f"band, outside it in {item['outside']}; approved by {item['approval']}.",
            f"{item['contract']}的对冲比例为{item['range']}，批准区间为{item['band']}，"
            f"区间外月份：{item['outside']}；批准方：{item['approval']}。"))
    if sens:
        bullets.append(T(
            "A one-unit price rise moves the open position by "
            + _join([f"{_sign_money(s['rest'] + s['next'], s['currency'])} at {s['hub']} "
                     f"({s['move']})" for s in sens]) + " to the end of "
            f"{w['next_start'].year}.",
            "价格上升一个单位，敞口价值变化：" + "，".join(
                f"{s['hub']} {_sign_money(s['rest'] + s['next'], s['currency'])}（{s['move']}）"
                for s in sens) + f"（至{w['next_start'].year}年底）。"))
    off = _off_ladder(ctx, data)
    if off:
        names = ", ".join(r["name"] for r in off[:2])
        gwh = sum((r["rest_gwh"] or 0.0) + (r["next_gwh"] or 0.0) for r in off)
        bullets.append(T(
            f"Not in these figures: {_num(gwh, 'GWh')} of FOB LNG cargo ({names}), which stays "
            "exposure to its loading formula until it is sold or discharged at a hub.",
            f"以上数字未含{_num(gwh, 'GWh')} FOB LNG 船货（{names}）：在出售或于枢纽卸货前，"
            "其敞口跟随装货定价公式。"))
    if var is not None:
        bullets.append(T(f"One-day 95% value at risk of the open position: {_money(var, 'EUR')} "
                         f"(historical simulation over {var_days} days).",
                         f"敞口一日95%风险价值：{_money(var, 'EUR')}（{var_days}天历史模拟）。"))
    result.simulated = data["simulated_marks"] and var is not None
    result.sources.append(source(T("Position ladder, hedge approvals and daily closes",
                                   "头寸阶梯、对冲批准与每日收盘价"), "operator-input", ctx.now,
                                 "current"))
    from eurogas_nexus.domain.risk.method_notes import method_note

    result.methods.append({"key": "net_position", "title": T("Net position", "净头寸"),
                           "text": method_note("net_position")["summary"]})
    if var is not None:
        result.methods.append({"key": "var_proxy", "title": T("Value at risk", "风险价值"),
                               "text": method_note("var_proxy",
                                                   params={"observations": var_days})["summary"]})
    result.methods.append({"key": "pf_sensitivity", "title": T("Sensitivity", "敏感度"),
                           "text": T("Open MWh of the period times a one-unit rise of the hub's "
                                     "price (1 p/th at NBP, 1 EUR/MWh at continental hubs), "
                                     "the whole curve moving together.",
                                     "期间敞口 MWh 乘以该枢纽价格上升一个单位（NBP 为 1 p/th，"
                                     "欧洲大陆枢纽为 1 EUR/MWh），整条曲线同步变动。")})
    result.books = sorted({leg.book_id for leg in legs if leg.book_id})
    return _apply(result, {"headline": headline, "bullets": bullets[:4]})


def _off_ladder(ctx: Ctx, data: dict[str, Any]) -> list[dict[str, Any]]:
    """FOB cargoes inside the horizon: contracted supply that is not on a European hub yet."""

    marker = "an FOB cargo is not on a European hub"
    ids = {text.split(":", 1)[0].removeprefix("contract ").strip()
           for text in data["inputs"].warnings if marker in text}
    return [r for r in _contract_rows(ctx, data)
            if r["contract_id"] in ids and ((r["rest_gwh"] or 0.0) + (r["next_gwh"] or 0.0))]


def _hedge_bands(data: dict[str, Any]) -> list[dict[str, Any]]:
    from eurogas_nexus.domain.risk.limits import HedgeApproval, VolumeLeg, deal_hedge_usage

    w = data["w"]
    inputs = data["inputs"]
    legs = {leg.reference: leg for leg in inputs.legs}
    names = {c.contract_id: c.contract_name for c in inputs.contracts}
    linked: dict[str, list[str]] = defaultdict(list)
    for order in inputs.orders:
        if order.linked_resource_id:
            linked[str(order.linked_resource_id)].append(order.order_observation_id)
    out = []
    for approval in data["approvals"]:
        leg = legs.get(approval.contract_id)
        if leg is None or leg.kind != "physical":
            continue
        until = min(w["next_end"], approval.valid_until or w["next_end"])
        if until < w["today"]:
            continue

        def volume(item, last=until):
            return VolumeLeg(item.reference, item.first_gas_day, min(item.last_gas_day, last),
                             item.mwh_per_day)

        usage = deal_hedge_usage(
            HedgeApproval(contract_id=approval.contract_id,
                          min_hedge_ratio_pct=approval.min_hedge_ratio_pct,
                          max_hedge_ratio_pct=approval.max_hedge_ratio_pct,
                          approval_ref=approval.approval_ref, valid_until=approval.valid_until),
            [volume(leg)], [volume(legs[r]) for r in linked.get(approval.contract_id, [])
                            if r in legs], today=w["today"])
        low, high = approval.min_hedge_ratio_pct, approval.max_hedge_ratio_pct
        months_out = [m["month"] for m in usage["months"]
                      if (low is not None and m["hedge_pct"] < low - 1e-6)
                      or (high is not None and m["hedge_pct"] > high + 1e-6)]
        band = f"{low or 0:.0f}–{high:.0f}%" if high is not None else f"≥{low or 0:.0f}%"
        out.append({"contract": names.get(approval.contract_id, approval.contract_id),
                    "band": band,
                    "range": (usage.get("hedge_range") or "-").replace(" to ", "至" if zh()
                                                                       else " to "),
                    "outside": _months_text(months_out) if months_out else T("none", "无"),
                    "approval": approval.approval_ref or "", "status": usage["status"]})
    return out


def _months_text(months: list[str]) -> str:
    labels = [_label(m) for m in months]
    if len(labels) <= 3:
        return ", ".join(labels)
    return T(f"{labels[0]} to {labels[-1]} ({len(labels)} months)",
             f"{labels[0]}至{labels[-1]}（{len(labels)}个月）")


# ================================================================================= LNG


def lng(ctx: Ctx) -> SectionResult:
    from eurogas_nexus.domain.contracts import kinds

    result = _new("pf_lng")
    data = read(ctx)
    w = data["w"]
    contracts = data["inputs"].contracts
    by_id = {c.contract_id: c for c in contracts}
    cargo_rows = []
    for contract in contracts:
        if contract.contract_kind != kinds.LNG_CARGO:
            continue
        terms = _terms(contract)
        if terms is None:
            continue
        first, last = terms.delivery_days()
        status = (T("delivered", "已交付") if last < w["today"] else
                  T("loading window open", "装载窗口中") if first <= w["today"] else
                  T("in plan", "计划中"))
        words, _fixed, _cur = _price_words(contract)
        cargo_rows.append({
            "cargo": terms.cargo_reference or contract.contract_name,
            "counterparty": counterparty_of(contract, data["credit"], by_id),
            "term": terms.delivery_term, "load": terms.load_port or "-",
            "discharge": terms.discharge_terminal or T("open", "未定"),
            "window": _span(first, last),
            "gwh": _gwh(terms.energy_mwh()), "mmbtu": round(terms.quantity_mmbtu, 0),
            "price": words, "status": status, "book": contract.book_id or "",
        })
    own = []
    for cargo in data["cargoes"]:
        eta = _aware_date(cargo.eta_utc)
        own.append({
            "cargo": cargo.vessel_name, "counterparty": "-", "term": "-",
            "load": cargo.load_port or "-", "discharge": cargo.destination_terminal or "-",
            "window": T(f"ETA {eta:%d %b}", f"预计{eta.month}月{eta.day}日到港") if eta else "-",
            "gwh": round(float(cargo.energy_gwh), 1) if cargo.energy_gwh else None,
            "mmbtu": None, "price": "-",
            "status": T("in transit", "运输中") if (cargo.status or "").lower() in {
                "laden", "underway", "in_transit"} else str(cargo.status),
            "book": cargo.book_id or "",
        })
    slots = []
    for slot in data["slots"]:
        start = _aware_date(slot.window_start_utc)
        end = _aware_date(slot.window_end_utc)
        slots.append({
            "terminal": slot.terminal_name,
            "country": _country(slot.terminal_country) if slot.terminal_country else "-",
            "window": _span(start, end) if start and end else "-",
            "gwh": round(float(slot.energy_gwh), 1) if slot.energy_gwh is not None else None,
            "cargo": slot.cargo_id or T("not assigned", "未分配"),
            "book": slot.book_id or "",
        })
    masters = [c for c in contracts if c.contract_kind == kinds.LNG_MSPA]
    if not (cargo_rows or own or slots or masters):
        return _empty(result, T("No LNG cargo, regas slot or master agreement is held in the "
                                "books you may see",
                                "您可查看的账簿中没有 LNG 船货、气化窗口或主协议"),
                      T("Open LNG", "打开 LNG"))
    rows = own + cargo_rows
    if rows:
        result.tables.append(table(
            T("LNG cargoes: in transit and in plan", "LNG 船货：运输中与计划中"),
            [("cargo", T("Cargo", "船货"), "text"), ("status", T("Status", "状态"), "text"),
             ("term", T("Term", "条款"), "text"), ("load", T("Load port", "装货港"), "text"),
             ("discharge", T("Discharge", "卸货"), "text"),
             ("window", T("Window", "窗口"), "text"), ("gwh", "GWh", "num"),
             ("price", T("Price", "价格"), "text"),
             ("counterparty", T("Seller", "卖方"), "text")],
            rows,
        ))
    if slots:
        result.tables.append(table(
            T("Regasification slots held", "持有的气化窗口"),
            [("terminal", T("Terminal", "接收站"), "text"),
             ("country", T("Country", "国家"), "text"), ("window", T("Window", "窗口"), "text"),
             ("gwh", "GWh", "num"), ("cargo", T("Cargo", "船货"), "text")],
            slots,
        ))
    parts_en, parts_zh = [], []
    if own:
        parts_en.append(f"{len(own)} own cargo{'es' if len(own) != 1 else ''} in transit "
                        f"({_num(sum(r['gwh'] or 0 for r in own), 'GWh')})")
        parts_zh.append(f"{len(own)}船自有 LNG 船货运输中"
                        f"（{_num(sum(r['gwh'] or 0 for r in own), 'GWh')}）")
    if cargo_rows:
        lead = cargo_rows[0]
        parts_en.append(f"{len(cargo_rows)} cargo{'es' if len(cargo_rows) != 1 else ''} under "
                        f"confirmation ({lead['cargo']}: {lead['term']} {lead['load']}, "
                        f"{lead['window']}, {_num(lead['gwh'], 'GWh')}, {lead['price']}, "
                        f"discharge {lead['discharge']})")
        parts_zh.append(f"{len(cargo_rows)}船已确认船货（{lead['cargo']}：{lead['term']} "
                        f"{lead['load']}，{lead['window']}，{_num(lead['gwh'], 'GWh')}，"
                        f"{lead['price']}，卸货{lead['discharge']}）")
    if slots:
        free = sum(1 for s in slots if s["cargo"] in {"not assigned", "未分配"})
        parts_en.append(f"{len(slots)} regas slot{'s' if len(slots) != 1 else ''} held"
                        + (f", {free} without a cargo" if free else ""))
        parts_zh.append(f"持有{len(slots)}个气化窗口"
                        + (f"，其中{free}个未分配船货" if free else ""))
    if not own:
        parts_en.append("no own cargo in transit")
        parts_zh.append("无自有船货在途")
    headline = T("LNG: " + "; ".join(parts_en) + ".", "LNG：" + "；".join(parts_zh) + "。")
    bullets = []
    for master in masters[:2]:
        terms = _terms(master)
        bullets.append(T(
            f"Master agreement {master.contract_name} with "
            f"{counterparty_of(master, data['credit'], by_id)}"
            + (f" ({', '.join(terms.delivery_terms)})" if getattr(terms, "delivery_terms", None)
               else "") + ": cargoes are confirmed under it one by one.",
            f"主协议{master.contract_name}，"
            f"交易对手{counterparty_of(master, data['credit'], by_id)}"
            + (f"（{'、'.join(terms.delivery_terms)}）" if getattr(terms, "delivery_terms", None)
               else "") + "：船货逐船确认。"))
    bullets += _lng_extra_bullets(ctx, data)
    result.sources.append(source(T("Contract register, own cargoes and regas slots",
                                   "合同登记、自有船货与气化窗口"), "operator-input", ctx.now,
                                 "current"))
    for system in sorted({c.source_system for c in data["cargoes"]}
                         | {s.source_system for s in data["slots"]}):
        if is_simulated_source(system):
            result.simulated = True
            result.sources.append(source(T("Vessel positions and slots", "船舶位置与窗口"), system,
                                         ctx.now, "current"))
    result.books = sorted({r["book"] for r in rows + slots if r.get("book")}
                          | {m.book_id for m in masters if m.book_id})
    return _apply(result, {"headline": headline, "bullets": bullets[:3]})


def _lng_extra_bullets(ctx: Ctx, data: dict[str, Any]) -> list[str]:
    """Sentences a deployment adds on its cargoes (none on this branch)."""

    return []


def _aware_date(value) -> date | None:
    from eurogas_nexus.application.reports.sections import _aware

    moment = _aware(value)
    return moment.date() if moment else None


# ================================================================================= strategies


def strategies(ctx: Ctx) -> SectionResult:
    result = _new("pf_strategies")
    data = read(ctx)
    contracts = _contract_rows(ctx, data)
    trade_rows = _trade_rows(ctx, data)
    if not contracts and not trade_rows:
        return _empty(result, T("No contract or trade is held in the books you may see",
                                "您可查看的账簿中没有合同或交易"), T("Open Contracts", "打开合同"))
    modes: dict[str, list[str]] = defaultdict(list)
    for row in contracts:
        for mode in row["sale_modes"]:
            modes[mode].append(row["name"])
    rows = []
    for mode, names in sorted(modes.items(), key=lambda kv: -len(kv[1])):
        rows.append({"strategy": _words(SALE_MODES.get(mode, (mode, mode))),
                     "applies": ", ".join(names), "count": len(names)})
    hedges = [r for r in trade_rows if r["linked"]]
    for row in hedges:
        rows.append({"strategy": T("hedge of a named supply contract", "针对指定供应合同的对冲"),
                     "applies": f"{row['linked']}: {row['side_label']} {row['gwh']} GWh "
                                f"{row['hub']} {row['delivery']}", "count": 1})
    named = [r for r in trade_rows if r["strategy"]]
    for row in named:
        rows.append({"strategy": T("registered strategy", "已登记策略"),
                     "applies": f"{row['strategy']}: {row['trade']}", "count": 1})
    transport = [line for line in data["schedule"] if line.kind in {"import", "export"}]
    for line in transport:
        rows.append({"strategy": T("cross-border flow on held capacity", "利用持有容量的跨境流"),
                     "applies": f"{line.label} ({line.point}, {_num(line.quantity_mwh, 'MWh')})",
                     "count": 1})
    result.tables.append(table(
        T("How the book is run", "账簿运作方式"),
        [("strategy", T("Strategy", "策略"), "text"),
         ("applies", T("Applies to", "适用于"), "text")],
        rows,
    ))
    local = len(modes.get("LOCAL_MARKET_SALE", []))
    target = modes.get("TARGET_MARKET_SALE", [])
    headline = T(
        _count(local, "contract is sold at its own hub", "contracts are sold at their own hub")
        + (f", {len(target)} at another hub over held transport ({', '.join(target[:2])})"
           if target else "")
        + (f", and {_count(len(hedges), 'trade hedges', 'trades hedge')} a named supply "
           "contract." if hedges else "."),
        f"{local}份合同在本地枢纽出售"
        + (f"，{len(target)}份经持有运输容量在其他枢纽出售（{'、'.join(target[:2])}）" if target
           else "") + (f"，{len(hedges)}笔交易对冲指定供应合同。" if hedges else "。"))
    bullets = []
    reroute = modes.get("REROUTE_SALE", [])
    if reroute:
        bullets.append(T(f"{', '.join(reroute)} may be rerouted to another exit point.",
                         f"{'、'.join(reroute)}可改道至其他出口点。"))
    if not named:
        bullets.append(T("No trade is linked to a registered trading strategy.",
                         "没有交易关联到已登记的交易策略。"))
    if transport:
        bullets.append(T(f"{len(transport)} cross-border flows on held capacity are scheduled "
                         "today.", f"今日计划{len(transport)}项利用持有容量的跨境流。"))
    result.sources.append(source(T("Contract register, trades and the gas day schedule",
                                   "合同登记、交易与燃气日计划"), "operator-input", ctx.now,
                                 "current"))
    result.books = sorted({r["book"] for r in contracts if r["book"]}
                          | {r["book"] for r in trade_rows if r.get("book")})
    return _apply(result, {"headline": headline, "bullets": bullets[:3]})


BUILDERS = {"pf_supply": supply, "pf_trades": trades, "pf_pnl": pnl, "pf_outlook": outlook,
            "pf_lng": lng, "pf_strategies": strategies}

__all__ = ["BUILDERS", "read"]
