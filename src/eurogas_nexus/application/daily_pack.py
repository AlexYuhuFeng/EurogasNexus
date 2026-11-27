"""The daily pack for managers and for the remote risk function: PDF and XLSX, English and
Chinese, by e-mail or downloaded (SMALL_DESK_PLAN section 3 item 1, section 4 steps 1-2).

Two packs from the same figures:

- **management summary**: P&L for the day, month and year to date; volume traded by hub and
  delivery period; open position by hub and month; limit usage; a short market section when
  prices are held;
- **risk pack**: P&L by trader and hub; exposure per counterparty against its limit and its
  guarantee with the guarantee's expiry; mandate checks (no options, tenor, volume); the
  end-of-day check result.

Every figure is labelled ``desk estimate, before ETRM close`` until the day is closed. A pack
that fails a sanity check (no deals on a trading day, unread rows, the day not closed, prices
simulated, deals not valued) says so in a band at the top instead of looking clean.

Sending goes through the notification outbox (``notifications.py``) to the recipient lists an
administrator keeps under Settings -> Notifications (categories ``pack_management`` and
``pack_risk``; the recipients must be registered people who may read every book's limits).
The same files download for sending by hand where the office does not let the server send
mail. The remote office has no access to the product: nothing here is a remote page.

每日报告（管理摘要与风险报告）：PDF 与 XLSX，中英文；日结前标注“交易台估算”；未通过检查时顶部提示。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from eurogas_nexus.application.deal_capture import (
    DealCaptureError,
    actor_of,
    current_deals,
    day_pnl,
    day_status,
    dec,
    open_problems,
    overlay_orders,
    totals,
)

KINDS = ("management", "risk")
LANGUAGES = ("en", "zh-CN")
CATEGORY = {"management": "pack_management", "risk": "pack_risk"}
SCHEDULE_KEY = "daily_pack_schedule"
#: A guarantee expiring within this many days is flagged in the risk pack.
GUARANTEE_WARNING_DAYS = 30
#: A scheduled slot missed by more than this (the worker was down) is skipped, not sent late.
CATCH_UP = timedelta(hours=6)

_TEXT: dict[str, tuple[str, str]] = {
    "management.title": ("Daily management summary", "每日管理摘要"),
    "risk.title": ("Daily risk pack", "每日风险报告"),
    "estimate": ("Desk estimate, before ETRM close", "交易台估算，ETRM 日结前"),
    "closed": ("Day closed against the ETRM entry by {who} at {when}",
               "已由 {who} 于 {when} 对照 ETRM 录入完成日结"),
    "scope": ("Books: {books}", "账簿：{books}"),
    "all_books": ("all books", "全部账簿"),
    "check.title": ("CHECK BEFORE USE:", "使用前请核对："),
    "check.no_deals": ("no deals were captured on this trading day",
                       "本交易日未捕获任何交易"),
    "check.unreadable": ("{n} row(s) of the exchange files could not be read",
                         "交易所文件中有 {n} 行无法读取"),
    "check.not_closed": ("the day is not closed against the ETRM entry",
                         "当日尚未对照 ETRM 录入完成日结"),
    "check.simulated": ("prices are simulated, not market prices", "价格为模拟价格，并非市场价格"),
    "check.not_valued": ("{n} deal(s) could not be valued (no price held)",
                         "{n} 笔交易无法估值（无可用价格）"),
    "section.pnl": ("Profit and loss", "损益"),
    "section.pnl_trader": ("Profit and loss by trader and hub", "按交易员与枢纽的损益"),
    "section.volume": ("Volume traded today by hub and period", "今日按枢纽与交割期的成交量"),
    "section.position": ("Open position by hub and month (MWh)", "按枢纽与月份的未平仓头寸（MWh）"),
    "section.limits": ("Limit usage", "限额使用"),
    "section.market": ("Market", "市场"),
    "section.credit": ("Counterparty exposure against limit and guarantee",
                       "交易对手敞口与限额及担保"),
    "section.mandate": ("Mandate checks", "授权检查"),
    "section.eod": ("End-of-day check", "日终核对"),
    "section.unreadable": ("Rows that could not be read", "无法读取的行"),
    "section.not_valued": ("Deals not valued", "未估值交易"),
    "col.currency": ("Currency", "币种"),
    "col.day": ("Day", "当日"),
    "col.mtd": ("Month to date", "月初至今"),
    "col.ytd": ("Year to date", "年初至今"),
    "col.fees": ("Fees today", "今日费用"),
    "col.trader": ("Trader", "交易员"),
    "col.hub": ("Hub", "枢纽"),
    "col.period": ("Period", "交割期"),
    "col.month": ("Month", "月份"),
    "col.deals": ("Deals", "笔数"),
    "col.buy": ("Bought MWh", "买入 MWh"),
    "col.sell": ("Sold MWh", "卖出 MWh"),
    "col.net": ("Net MWh", "净额 MWh"),
    "col.avg_buy": ("Avg buy", "平均买价"),
    "col.avg_sell": ("Avg sell", "平均卖价"),
    "col.unit": ("Unit", "单位"),
    "col.counterparty": ("Counterparty", "交易对手"),
    "col.limit": ("Limit", "限额"),
    "col.exposure": ("Exposure", "敞口"),
    "col.used": ("Used %", "使用率 %"),
    "col.guarantee": ("Guarantee", "担保金额"),
    "col.guarantee_expiry": ("Guarantee expiry", "担保到期日"),
    "col.status": ("Status", "状态"),
    "col.check": ("Check", "检查"),
    "col.deal": ("Deal", "交易"),
    "col.detail": ("Detail", "说明"),
    "col.kind": ("Difference", "差异"),
    "col.acknowledged": ("Acknowledged", "确认说明"),
    "col.by": ("By", "确认人"),
    "col.price": ("Price", "价格"),
    "col.as_of": ("As of", "截至"),
    "col.source": ("Source", "来源"),
    "col.file": ("File", "文件"),
    "col.line": ("Line", "行"),
    "col.reason": ("Reason", "原因"),
    "col.mandate": ("Mandate", "授权"),
    "col.largest": ("Largest net MWh", "最大净额 MWh"),
    "empty": ("None.", "无。"),
    "eod.not_closed": ("The day is not closed: {n} captured deal(s) have not been checked "
                       "against the ETRM entry.",
                       "当日尚未日结：{n} 笔捕获交易尚未与 ETRM 录入核对。"),
    "eod.closed": ("Closed by {who} at {when}; {n} difference(s) listed and acknowledged.",
                   "由 {who} 于 {when} 日结；列出并确认 {n} 项差异。"),
    "overlay": ("Positions are the book plus {n} captured deal(s) not yet in the ETRM book.",
                "头寸为账簿加上尚未进入 ETRM 账簿的 {n} 笔捕获交易。"),
    "pnl.method": ("P&L of captured deals at the position ladder's prices: (price - deal "
                   "price) x MWh per delivery month; the day is the change since the previous "
                   "close. Currencies are not added together.",
                   "捕获交易按头寸阶梯价格估值：（价格 - 成交价）× 每交割月 MWh；"
                   "当日损益为与上一次日结相比的变动。不同币种不相加。"),
    "manual_note": ("{n} deal(s) were entered by hand.", "{n} 笔交易为手工录入。"),
    "flag.option": ("option: the mandate allows no options", "期权：授权不允许期权"),
    "flag.tenor": ("tenor {months} months exceeds {limit}", "期限 {months} 个月超过 {limit}"),
    "flag.volume": ("{mwh} MWh in a month exceeds {limit}", "单月 {mwh} MWh 超过 {limit}"),
    "flag.no_mandate": ("no mandate recorded for this trader", "该交易员无授权记录"),
    "guarantee.expired": ("guarantee expired", "担保已过期"),
    "guarantee.expiring": ("guarantee expires in {days} days", "担保将在 {days} 天后到期"),
    "kind.missing_in_etrm": ("captured, not in the ETRM", "已捕获，ETRM 中没有"),
    "kind.missing_in_capture": ("in the ETRM, not captured", "ETRM 中有，未捕获"),
    "kind.side": ("buy/sell differs", "买卖方向不同"),
    "kind.hub": ("hub differs", "枢纽不同"),
    "kind.period": ("delivery period differs", "交割期不同"),
    "kind.volume": ("volume differs", "数量不同"),
    "kind.price": ("price differs", "价格不同"),
    "kind.counterparty": ("counterparty differs", "交易对手不同"),
    "kind.cancelled_in_capture": ("cancelled, still in the ETRM", "已取消，ETRM 中仍有"),
    "kind.etrm_unreadable": ("ETRM row not readable", "ETRM 行无法读取"),
    "no_limits": ("Limits are not shown: the person or service generating the pack may not "
                  "read them.", "未显示限额：生成本报告的人员或服务无权读取限额。"),
    "simulated": ("simulated", "模拟"),
}


def t(lang: str, key: str, **params: Any) -> str:
    en, zh = _TEXT[key]
    text = zh if lang == "zh-CN" else en
    return text.format(**params) if params else text


def is_trading_day(day: date) -> bool:
    """Monday to Friday (exchange holidays are not modelled; a holiday says no deals)."""

    return day.weekday() < 5


def _d(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                "Dec")


def _month_label(month: str) -> str:
    year, number = int(month[:4]), int(month[5:7])
    return f"{_MONTH_NAMES[number - 1]}-{year % 100:02d}"


# ----------------------------------------------------------------------------- figures


def pack_data(session, caller, *, day: date, now: datetime | None = None) -> dict[str, Any]:
    """Every figure both packs read, computed once (no rendering)."""

    from eurogas_nexus.application.limits_service import (
        credit_exposure_rows,
        mandate_usage_rows,
    )
    from eurogas_nexus.application.position_inputs import captured_overlay, ladder_inputs
    from eurogas_nexus.db.models import CreditLineRecord, TraderMandateRecord
    from eurogas_nexus.domain.portfolio.position_ladder import build_ladder, ladder_horizon
    from eurogas_nexus.security.authorization import Permission, authorize
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    now = now or datetime.now(UTC)
    records = current_deals(session, day=day)
    status = day_status(session, day, records)
    problems = open_problems(session, day)
    pnl = day_pnl(session, caller, day=day, now=now)
    orders, books, counterparties, left_out = overlay_orders(session, day)
    start, end = ladder_horizon(day, 12)
    limits_allowed = authorize(caller.principal, Permission.RISK_LIMITS_READ).allowed
    with captured_overlay(orders, books, counterparties):
        inputs = ladder_inputs(caller, day, start, end, now=now)
        ladder = build_ladder(inputs.legs, horizon_start=start, horizon_end=end)
        credit = credit_exposure_rows(caller, day) if limits_allowed else None
        mandates = mandate_usage_rows(caller, day) if limits_allowed else None
    position = [
        {"hub": row.hub, "month": _month_label(row.month),
         "net_mwh": dec(Decimal(repr(row.net_mwh)).quantize(Decimal(1)))}
        for row in ladder if abs(row.net_mwh) >= 0.5
    ]
    guarantees = {
        row.counterparty_id: (row.guarantee_amount, row.guarantee_expiry)
        for row in session.query(CreditLineRecord).all()
    }
    credit_rows = []
    for row in (credit.rows if credit else []):
        amount, expiry = guarantees.get(row["counterparty_id"], (None, None))
        days_left = (expiry - day).days if expiry else None
        credit_rows.append({
            "counterparty": row["counterparty"], "currency": row["currency"],
            "limit": dec(_d(row["limit"])), "exposure": dec(_d(row["net_exposure"])),
            "used_pct": row["utilisation_pct"], "status": row["status"],
            "guarantee": dec(_d(amount)), "guarantee_expiry": expiry.isoformat() if expiry
            else None, "guarantee_days_left": days_left,
        })
    mandate_rows = list(mandates.rows) if mandates else []
    by_trader = {
        record.trader.casefold(): record
        for record in session.query(TraderMandateRecord).all()
    }
    flags = []
    for record in records:
        if record.status != "live":
            continue
        mandate = by_trader.get(record.trader.casefold())
        instruments = [str(i).casefold() for i in (mandate.instruments or [])] if mandate else []
        if record.instrument == "option" and "option" not in instruments:
            flags.append({"deal_key": record.deal_key, "trader": record.trader,
                          "flag": "option", "params": {}})
        if mandate is None:
            flags.append({"deal_key": record.deal_key, "trader": record.trader,
                          "flag": "no_mandate", "params": {}})
            continue
        months = ((record.delivery_end.year - day.year) * 12
                  + record.delivery_end.month - day.month)
        if mandate.max_tenor_months is not None and months > mandate.max_tenor_months:
            flags.append({"deal_key": record.deal_key, "trader": record.trader, "flag": "tenor",
                          "params": {"months": months, "limit": mandate.max_tenor_months}})
        if mandate.max_net_mwh_per_month:
            from eurogas_nexus.application.deal_capture import monthly_mwh

            largest = max((abs(mwh) for _m, mwh in monthly_mwh(record)), default=Decimal(0))
            limit = Decimal(repr(float(mandate.max_net_mwh_per_month)))
            if largest > limit:
                flags.append({"deal_key": record.deal_key, "trader": record.trader,
                              "flag": "volume",
                              "params": {"mwh": dec(largest.quantize(Decimal(1))),
                                         "limit": dec(limit)}})
    market = []
    next_month = (day.replace(day=1) + timedelta(days=32)).replace(day=1)
    month_key = f"{next_month.year:04d}-{next_month.month:02d}"
    hubs = sorted({r.hub for r in records} | {row["hub"] for row in position})
    for hub in hubs:
        resolved = (pnl.get("resolved") or {}).get((hub, month_key))
        mark = (pnl.get("marks") or {}).get((hub, month_key))
        if mark is None:
            continue
        from eurogas_nexus.domain.ontology.markets import quote_currency

        # The hub's own quotation where the resolver gave it (NBP in p/th), else per MWh.
        native = resolved and resolved.get("value") is not None and resolved.get("unit")
        market.append({
            "hub": hub, "product": _month_label(month_key),
            "price": dec(Decimal(repr(float(resolved["value"] if native else mark)))
                         .quantize(Decimal("0.001"))),
            "unit": resolved["unit"] if native else f"{quote_currency(hub)}/MWh",
            "as_of": (resolved or {}).get("as_of_utc") or (resolved or {}).get("as_of"),
            "source": (resolved or {}).get("source_system") or (resolved or {}).get("kind"),
            "simulated": bool((resolved or {}).get("simulated")),
        })
    sanity = []
    if is_trading_day(day) and not records:
        sanity.append(("check.no_deals", {}))
    if problems:
        sanity.append(("check.unreadable", {"n": len(problems)}))
    if not status["closed"]:
        sanity.append(("check.not_closed", {}))
    if pnl["simulated_marks"]:
        sanity.append(("check.simulated", {}))
    if pnl["not_valued"]:
        sanity.append(("check.not_valued", {"n": len(pnl["not_valued"])}))
    from eurogas_nexus.application.deal_capture import day_closes

    closes = day_closes(session, day)
    differences = [item for row in closes for item in (row.differences or [])]
    visible = visible_book_ids(session)
    return {
        "business_date": day,
        "generated_at": now,
        "generated_by": actor_of(caller),
        "books": sorted(visible) if visible is not None else None,
        "status": status,
        "sanity": sanity,
        "pnl": {key: pnl[key] for key in ("by_trader_hub", "totals", "not_valued", "warnings",
                                          "simulated_marks", "method")},
        "volume": totals(records),
        "deals": len(records),
        "manual_deals": sum(1 for r in records if r.origin == "manual"),
        "position": position,
        "overlay_deals": len(orders),
        "overlay_left_out": left_out,
        "limits_allowed": limits_allowed,
        "credit": credit_rows,
        "mandates": mandate_rows,
        "mandate_flags": flags,
        "market": market,
        "problems": [{"file_name": p.file_name, "line": p.line, "code": p.reason_code,
                      "message": p.message} for p in problems],
        "eod": {"closed": status["closed"], "closes": status["closes"],
                "differences": differences, "captured": len(records)},
    }


# ----------------------------------------------------------------------------- render


def _sections(data: dict[str, Any], kind: str, lang: str) -> list[dict[str, Any]]:
    """The pack's sections as heading, lines and a table (the PDF and XLSX both read them)."""

    def num(value: Any) -> Decimal | None:
        return _d(value)

    sections: list[dict[str, Any]] = []
    pnl = data["pnl"]
    if kind == "management":
        sections.append({
            "key": "pnl", "heading": t(lang, "section.pnl"),
            "lines": [t(lang, "pnl.method")],
            "columns": [t(lang, "col.currency"), t(lang, "col.day"), t(lang, "col.mtd"),
                        t(lang, "col.ytd")],
            "rows": [[row["currency"], num(row["day"]), num(row["mtd"]), num(row["ytd"])]
                     for row in pnl["totals"]],
            "numeric": [False, True, True, True],
        })
        sections.append({
            "key": "volume", "heading": t(lang, "section.volume"),
            "lines": [t(lang, "manual_note", n=data["manual_deals"])] if data["manual_deals"]
            else [],
            "columns": [t(lang, "col.hub"), t(lang, "col.period"), t(lang, "col.deals"),
                        t(lang, "col.buy"), t(lang, "col.sell"), t(lang, "col.net"),
                        t(lang, "col.avg_buy"), t(lang, "col.avg_sell"), t(lang, "col.unit")],
            "rows": [[row["hub"], row["product"], row["deals"], num(row["buy_mwh"]),
                      num(row["sell_mwh"]), num(row["net_mwh"]), num(row["avg_buy_price"]),
                      num(row["avg_sell_price"]), row["price_unit"] or ""]
                     for row in data["volume"]],
            "numeric": [False, False, True, True, True, True, True, True, False],
        })
        sections.append({
            "key": "position", "heading": t(lang, "section.position"),
            "lines": [t(lang, "overlay", n=data["overlay_deals"])],
            "columns": [t(lang, "col.hub"), t(lang, "col.month"), t(lang, "col.net")],
            "rows": [[row["hub"], row["month"], num(row["net_mwh"])]
                     for row in data["position"]],
            "numeric": [False, False, True],
        })
        limit_rows = [[row["counterparty"], f"{row['used_pct']}" if row["used_pct"] is not None
                       else "", row["status"]] for row in data["credit"]]
        limit_rows += [[row["name"], f"{row['utilisation_pct']}"
                        if row.get("utilisation_pct") is not None else "", row["status"]]
                       for row in data["mandates"]]
        sections.append({
            "key": "limits", "heading": t(lang, "section.limits"),
            "lines": [] if data["limits_allowed"] else [t(lang, "no_limits")],
            "columns": [t(lang, "col.counterparty") + " / " + t(lang, "col.mandate"),
                        t(lang, "col.used"), t(lang, "col.status")],
            "rows": limit_rows, "numeric": [False, True, False],
        })
        if data["market"]:
            sections.append({
                "key": "market", "heading": t(lang, "section.market"),
                "columns": [t(lang, "col.hub"), t(lang, "col.period"), t(lang, "col.price"),
                            t(lang, "col.unit"), t(lang, "col.as_of"), t(lang, "col.source")],
                "rows": [[row["hub"], row["product"], num(row["price"]), row["unit"],
                          str(row["as_of"] or "")[:16],
                          (row["source"] or "") + (f" ({t(lang, 'simulated')})"
                                                   if row["simulated"] else "")]
                         for row in data["market"]],
                "numeric": [False, False, True, False, False, False],
            })
        return sections
    sections.append({
        "key": "pnl_trader", "heading": t(lang, "section.pnl_trader"),
        "lines": [t(lang, "pnl.method")],
        "columns": [t(lang, "col.trader"), t(lang, "col.hub"), t(lang, "col.currency"),
                    t(lang, "col.day"), t(lang, "col.mtd"), t(lang, "col.ytd"),
                    t(lang, "col.fees")],
        "rows": [[row["trader"], row["hub"], row["currency"], num(row["day"]), num(row["mtd"]),
                  num(row["ytd"]), num(row["fees"])] for row in pnl["by_trader_hub"]],
        "numeric": [False, False, False, True, True, True, True],
    })
    credit_rows = []
    for row in data["credit"]:
        note = row["status"]
        days_left = row["guarantee_days_left"]
        if days_left is not None and days_left < 0:
            note += "; " + t(lang, "guarantee.expired")
        elif days_left is not None and days_left <= GUARANTEE_WARNING_DAYS:
            note += "; " + t(lang, "guarantee.expiring", days=days_left)
        credit_rows.append([row["counterparty"], row["currency"], num(row["limit"]),
                            num(row["exposure"]), row["used_pct"], num(row["guarantee"]),
                            row["guarantee_expiry"] or "", note])
    sections.append({
        "key": "credit", "heading": t(lang, "section.credit"),
        "lines": [] if data["limits_allowed"] else [t(lang, "no_limits")],
        "columns": [t(lang, "col.counterparty"), t(lang, "col.currency"), t(lang, "col.limit"),
                    t(lang, "col.exposure"), t(lang, "col.used"), t(lang, "col.guarantee"),
                    t(lang, "col.guarantee_expiry"), t(lang, "col.status")],
        "rows": credit_rows,
        "numeric": [False, False, True, True, True, True, False, False],
    })
    mandate_rows = [[item["trader"], item["deal_key"], t(lang, f"flag.{item['flag']}",
                                                         **item["params"])]
                    for item in data["mandate_flags"]]
    mandate_rows += [[row["trader"], row["name"], row.get("breaches") or row["status"]]
                     for row in data["mandates"] if row["status"] not in {"ok"}]
    sections.append({
        "key": "mandate", "heading": t(lang, "section.mandate"),
        "columns": [t(lang, "col.trader"), t(lang, "col.deal") + " / " + t(lang, "col.mandate"),
                    t(lang, "col.check")],
        "rows": mandate_rows, "numeric": [False, False, False], "empty": t(lang, "empty"),
    })
    eod = data["eod"]
    if eod["closed"]:
        last = eod["closes"][-1]
        line = t(lang, "eod.closed", who=last["closed_by"], when=last["closed_at_utc"][:16],
                 n=len(eod["differences"]))
    else:
        line = t(lang, "eod.not_closed", n=eod["captured"])
    sections.append({
        "key": "eod", "heading": t(lang, "section.eod"), "lines": [line],
        "columns": [t(lang, "col.kind"), t(lang, "col.hub"), t(lang, "col.deal"),
                    t(lang, "col.detail"), t(lang, "col.acknowledged"), t(lang, "col.by")],
        "rows": [[t(lang, f"kind.{item['kind']}"), item.get("hub") or "",
                  item.get("deal_key") or item.get("etrm_trade_id") or "",
                  "; ".join(f"{k}: {v}" for k, v in (item.get("detail") or {}).items()),
                  item.get("acknowledgement") or "", item.get("acknowledged_by") or ""]
                 for item in eod["differences"]],
        "numeric": [False] * 6, "empty": t(lang, "empty"),
    })
    sections.append({
        "key": "unreadable", "heading": t(lang, "section.unreadable"),
        "columns": [t(lang, "col.file"), t(lang, "col.line"), t(lang, "col.reason")],
        "rows": [[p["file_name"], p["line"], p["message"]] for p in data["problems"]],
        "numeric": [False, True, False], "empty": t(lang, "empty"),
    })
    sections.append({
        "key": "not_valued", "heading": t(lang, "section.not_valued"),
        "columns": [t(lang, "col.deal"), t(lang, "col.hub"), t(lang, "col.period"),
                    t(lang, "col.reason")],
        "rows": [[item["deal_key"], item["hub"], item["product"], item["reason"] or ""]
                 for item in pnl["not_valued"]],
        "numeric": [False, False, False, False], "empty": t(lang, "empty"),
    })
    return sections


def header(data: dict[str, Any], lang: str) -> tuple[str, str, str]:
    """(status line, scope line, banner) of a pack."""

    status = data["status"]
    if status["closed"]:
        last = status["closes"][-1]
        state = t(lang, "closed", who=last["closed_by"], when=last["closed_at_utc"][:16])
    else:
        state = t(lang, "estimate")
    books = ", ".join(data["books"]) if data["books"] is not None else t(lang, "all_books")
    banner = ""
    if data["sanity"]:
        banner = t(lang, "check.title") + " " + "; ".join(
            t(lang, key, **params) for key, params in data["sanity"])
    return state, t(lang, "scope", books=books), banner


def render(data: dict[str, Any], kind: str, lang: str) -> tuple[bytes, bytes, str]:
    """The pack as (PDF, XLSX, base file name)."""

    from eurogas_nexus.core.report_files import pdf_document, xlsx_workbook

    if kind not in KINDS:
        raise DealCaptureError("pack_kind_unknown", f"a pack is one of {', '.join(KINDS)}")
    lang = "zh-CN" if str(lang).lower().startswith("zh") else "en"
    day = data["business_date"]
    title = f"{t(lang, f'{kind}.title')} {day.isoformat()}"
    state, scope, banner = header(data, lang)
    sections = _sections(data, kind, lang)
    generated = data["generated_at"].strftime("%Y-%m-%d %H:%M UTC")
    pdf = pdf_document(
        title=title, subtitle=f"{state} · {scope} · {generated}", sections=sections,
        footer=state, banner=banner, cjk=lang == "zh-CN",
    )
    sheets = []
    for section in sections:
        rows = [list(row) for row in section.get("rows") or []]
        notes = [[line] for line in section.get("lines") or []]
        header_row = list(section.get("columns") or [])
        if notes and not rows:
            sheets.append((section["heading"], [section["heading"]], notes))
        else:
            sheets.append((section["heading"], header_row, rows + ([[]] + notes if notes else [])))
    about = [("Pack", title), ("Status", state), ("Scope", scope),
             ("Generated", generated), ("Generated by", data["generated_by"])]
    if banner:
        about.insert(1, ("Check", banner))
    if banner:
        sheets.insert(0, (t(lang, "check.title").rstrip(":："), [t(lang, "check.title")],
                          [[t(lang, key, **params)] for key, params in data["sanity"]]))
    xlsx = xlsx_workbook(sheets, about=about,
                         caveat=t(lang, "estimate") if not data["status"]["closed"] else None)
    name = f"{kind}-pack-{day.isoformat()}-{'zh' if lang == 'zh-CN' else 'en'}"
    return pdf, xlsx, name


def plain_summary(data: dict[str, Any], kind: str, lang: str) -> str:
    """The e-mail body: the status, the sanity band and the P&L totals (files attached)."""

    state, scope, banner = header(data, lang)
    lines = [f"{t(lang, f'{kind}.title')} {data['business_date'].isoformat()}", state, scope]
    if banner:
        lines += ["", banner]
    lines.append("")
    for row in data["pnl"]["totals"]:
        lines.append(f"{t(lang, 'section.pnl')} {row['currency']}: {t(lang, 'col.day')} "
                     f"{row['day']} · {t(lang, 'col.mtd')} {row['mtd']} · "
                     f"{t(lang, 'col.ytd')} {row['ytd']}")
    lines += ["", "PDF + XLSX attached." if lang == "en" else "附 PDF 与 XLSX 文件。"]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- sending


def recipient_channels(session, kind: str) -> list:
    """The enabled notification channels that receive this pack's category."""

    from eurogas_nexus.db.models import NotificationChannelRecord

    category = CATEGORY[kind]
    return [
        channel for channel in session.query(NotificationChannelRecord).all()
        if channel.enabled and category in (channel.categories or [])
    ]


def queue_packs(session, caller, *, day: date, kinds: list[str], languages: list[str],
                trigger: str, now: datetime | None = None) -> list[dict[str, Any]]:
    """Render and queue each pack for e-mail; refused when a pack has no recipient list."""

    from eurogas_nexus.application.notifications import queue_notification
    from eurogas_nexus.db.models import DailyPackRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    now = now or datetime.now(UTC)
    kinds = [k for k in dict.fromkeys(kinds) if k in KINDS]
    languages = ["zh-CN" if str(lang).lower().startswith("zh") else "en"
                 for lang in dict.fromkeys(languages)] or ["en"]
    if not kinds:
        raise DealCaptureError("pack_kind_unknown", f"choose among {', '.join(KINDS)}")
    missing = [kind for kind in kinds if not recipient_channels(session, kind)]
    if missing:
        raise DealCaptureError(
            "no_recipients",
            "no recipient list receives " + ", ".join(missing) + " packs; an administrator "
            "adds one under Settings -> Notifications (category "
            + ", ".join(CATEGORY[k] for k in missing) + ")",
            status=409, kinds=missing,
        )
    data = pack_data(session, caller, day=day, now=now)
    actor = actor_of(caller)
    queued = []
    for kind in kinds:
        for lang in languages:
            pdf, xlsx, name = render(data, kind, lang)
            _state, scope, banner = header(data, lang)
            pack_id = uuid.uuid4().hex
            record = DailyPackRecord(
                pack_id=pack_id, business_date=day, kind=kind, language=lang, trigger=trigger,
                created_by=actor, created_at_utc=now, scope_note=scope[:500],
                warnings=[key for key, _params in data["sanity"]], pdf=pdf, xlsx=xlsx,
            )
            session.add(record)
            session.flush()
            title = f"{t(lang, f'{kind}.title')} {day.isoformat()}"
            if banner:
                title = f"{title} - {t(lang, 'check.title').rstrip(':：')}"
            dedupe = f"pack:{kind}:{lang}:{day.isoformat()}:{pack_id}"
            queue_notification(
                session, category=CATEGORY[kind],
                severity="warning" if data["sanity"] else "info", title=title,
                body=plain_summary(data, kind, lang), dedupe_key=dedupe, now=now,
            )
            from eurogas_nexus.db.models import NotificationOutboxRecord

            outbox = (session.query(NotificationOutboxRecord)
                      .filter(NotificationOutboxRecord.dedupe_key == dedupe[:200]).one())
            record.notification_id = outbox.notification_id
            queued.append({"pack_id": pack_id, "kind": kind, "language": lang,
                           "file_name": name, "warnings": record.warnings})
    record_audit_event(
        session, event_type="desk.daily_pack", principal=actor, action="pack.queue",
        resource=f"daily-pack:{day.isoformat()}", outcome=trigger, now_utc=now,
        detail=", ".join(f"{q['kind']}/{q['language']}" for q in queued)
        + (f"; checks: {', '.join(k for k, _p in data['sanity'])}" if data["sanity"] else ""),
    )
    return queued


def attachments_for(session, notification_id: str) -> list[tuple[str, str, bytes]]:
    """The files of the pack an outbox row carries: (file name, media type, bytes)."""

    from eurogas_nexus.db.models import DailyPackRecord

    record = (session.query(DailyPackRecord)
              .filter(DailyPackRecord.notification_id == notification_id).one_or_none())
    if record is None:
        return []
    name = (f"{record.kind}-pack-{record.business_date.isoformat()}-"
            f"{'zh' if record.language == 'zh-CN' else 'en'}")
    return [
        (f"{name}.pdf", "application/pdf", bytes(record.pdf)),
        (f"{name}.xlsx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", bytes(record.xlsx)),
    ]


# ----------------------------------------------------------------------------- schedule


def load_schedule(session) -> dict[str, Any]:
    from eurogas_nexus.db.models.settings import OrganisationSettingRecord

    row = session.get(OrganisationSettingRecord, SCHEDULE_KEY)
    value = row.value_json if row is not None and isinstance(row.value_json, dict) else {}
    return {
        "enabled": bool(value.get("enabled", False)),
        "at_local": str(value.get("at_local") or "18:30"),
        "timezone": str(value.get("timezone") or "Europe/London"),
        "weekdays": list(value.get("weekdays") or [0, 1, 2, 3, 4]),
        "kinds": list(value.get("kinds") or list(KINDS)),
        "languages": list(value.get("languages") or list(LANGUAGES)),
        "last_slot": value.get("last_slot"),
        "updated_by": row.updated_by if row is not None else None,
    }


def save_schedule(session, raw: dict[str, Any], *, actor: str, now: datetime) -> dict[str, Any]:
    import re

    from eurogas_nexus.db.models.settings import OrganisationSettingRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    at = str(raw.get("at_local") or "18:30")
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", at):
        raise DealCaptureError("bad_time", f"time {at!r} is not HH:MM")
    zone = str(raw.get("timezone") or "Europe/London")
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise DealCaptureError("bad_timezone", f"time zone {zone!r} is not known") from None
    weekdays = sorted({int(d) for d in raw.get("weekdays") or [0, 1, 2, 3, 4] if 0 <= int(d) <= 6})
    kinds = [k for k in raw.get("kinds") or KINDS if k in KINDS]
    languages = [lang for lang in raw.get("languages") or LANGUAGES if lang in LANGUAGES]
    if not kinds or not languages or not weekdays:
        raise DealCaptureError("bad_schedule", "choose at least one pack, language and weekday")
    current = load_schedule(session)
    value = {"enabled": bool(raw.get("enabled")), "at_local": at, "timezone": zone,
             "weekdays": weekdays, "kinds": kinds, "languages": languages,
             # Saving never makes a passed slot due again.
             "last_slot": current.get("last_slot") or latest_slot(
                 {"at_local": at, "timezone": zone, "weekdays": weekdays}, now)[0].isoformat()}
    row = session.get(OrganisationSettingRecord, SCHEDULE_KEY)
    if row is None:
        session.add(OrganisationSettingRecord(setting_key=SCHEDULE_KEY, value_json=value,
                                              updated_by=actor[:64], updated_at_utc=now))
    else:
        row.value_json, row.updated_by, row.updated_at_utc = value, actor[:64], now
    record_audit_event(session, event_type="desk.daily_pack", principal=actor,
                       action="pack.schedule", resource=f"setting:{SCHEDULE_KEY}",
                       outcome="enabled" if value["enabled"] else "disabled", now_utc=now,
                       detail=f"{at} {zone} days {weekdays} {kinds} {languages}")
    return {**value, "updated_by": actor}


def latest_slot(schedule: dict[str, Any], now: datetime) -> tuple[datetime, date]:
    """The newest scheduled instant at or before ``now`` on a scheduled weekday, and its day."""

    zone = ZoneInfo(schedule.get("timezone") or "Europe/London")
    hour, minute = (int(x) for x in str(schedule.get("at_local") or "18:30").split(":"))
    local = now.astimezone(zone)
    day = local.date()
    for _ in range(8):
        slot = datetime.combine(day, time(hour, minute), tzinfo=zone)
        if slot <= local and day.weekday() in (schedule.get("weekdays") or [0, 1, 2, 3, 4]):
            return slot.astimezone(UTC), day
        day -= timedelta(days=1)
    return datetime.combine(day, time(hour, minute), tzinfo=zone).astimezone(UTC), day


def run_due(session, *, now: datetime, caller) -> dict[str, Any] | None:
    """Send the scheduled packs when their slot has passed and not run (the worker calls this).

    Generated as the configured service principal (never an administrator); a slot older
    than :data:`CATCH_UP` is skipped. Returns what happened, or ``None`` when nothing was due.
    """

    from eurogas_nexus.db.models.settings import OrganisationSettingRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    schedule = load_schedule(session)
    if not schedule["enabled"]:
        return None
    slot, day = latest_slot(schedule, now)
    last = schedule.get("last_slot")
    if last and datetime.fromisoformat(last) >= slot:
        return None
    outcome: dict[str, Any] = {"slot": slot.isoformat(), "business_date": day.isoformat()}
    if now - slot > CATCH_UP:
        outcome["status"] = "skipped_late"
    elif caller is None:
        outcome["status"] = "refused_no_service_principal"
    else:
        from eurogas_nexus.application.caller import Caller

        try:
            outcome["queued"] = queue_packs(
                session, caller if isinstance(caller, Caller) else Caller(caller), day=day,
                kinds=schedule["kinds"], languages=schedule["languages"], trigger="schedule",
                now=now)
            outcome["status"] = "queued"
        except DealCaptureError as exc:
            outcome["status"] = f"refused: {exc.code}"
    row = session.get(OrganisationSettingRecord, SCHEDULE_KEY)
    if row is not None:
        row.value_json = {**(row.value_json or {}), "last_slot": slot.isoformat()}
    record_audit_event(session, event_type="desk.daily_pack", principal="service",
                       action="pack.schedule.run", resource=f"daily-pack:{day.isoformat()}",
                       outcome=outcome["status"].split(":")[0], now_utc=now,
                       detail=f"slot {outcome['slot']}")
    return outcome
