"""The Today read: what changed and does it touch us, computed once on the server (UX-05).

One deterministic read (no model) in the four rows of the product's Today screen:

1. **Key figures**: front-month close and day change per hub (hubs the visible book holds
   first), the net position today and front month, and the tightest limit's headroom.
2. **What changed**: open alerts and outages, each with the object a "Why?" explains.
3. **Our book against the market**: per hub, the position, the mark and the day P&L change.
4. **Fundamentals**: north-west Europe storage fill and the balance, as short series.

The sections come from the reads the desk brief uses (``desk_brief``): the same entitlement
(licensed prices by data scope through ``daily_rows``), the same book scope (``ladder_inputs``
restricts legs to the caller's books) and the same alert visibility. A limits row is shown
only to a caller who can see every book behind it, as limits alerts are (``alert_scope``).
Outage counts come from the service the ticker and the map read (``remit_outages``), with
the outages that cannot be placed on the map included.

Every figure carries its unit, its as-of time, its state in the freshness contract's words
(``current``, ``late``, ``stale``, ``never``, ``manual``) and ``simulated`` when its source
is simulated; ``stale_figures`` names each late or stale figure, so a page names what is
affected instead of saying "N feeds stale". A section with nothing to show returns an
``empty`` state with the reason and the next action, never a withheld marker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.application.caller import Caller

MAX_ITEMS = 6
#: The position ladder's default horizon: the day P&L change uses the same open position.
BOOK_HORIZON_MONTHS = 12
#: The ticker's and the map's outage horizon (``ShellTicker``: ``api.outages(14)``).
OUTAGE_HORIZON_DAYS = 14
STORAGE_DAYS = 30
BALANCE_DAYS = 14
#: Today's market row (design basis 2, E.2): up to four focus hubs, DA and front month each,
#: with a 30-day series for the sparkline.
MARKET_HUBS = 4
MARKET_SERIES_DAYS = 30
#: The spreads that matter to a north-west European book, quoted against TTF in EUR/MWh.
SPREAD_PAIRS: tuple[tuple[str, str], ...] = (("NBP", "TTF"), ("THE", "TTF"))
#: "What needs me" holds at most five items (E.2 row 3).
NEEDS_ME_ITEMS = 5
#: Countries shown as small multiples under the Europe storage chart (E.2 row 4).
STORAGE_COUNTRIES = 8
LATE_STATES = frozenset({"late", "stale"})


def _held_back(session, systems) -> list[dict[str, str]]:
    """Approval-required sources the ingestion gate holds back (never raises)."""

    try:
        from eurogas_nexus.application.public_source_approval import held_back_sources

        return held_back_sources(session, systems)
    except Exception:  # noqa: BLE001 - an empty state must not fail the read
        return []


def empty(code: str, reason: str, action: str) -> dict[str, str]:
    """An explicit empty state: why there is nothing, and what would fill it."""

    return {"code": code, "reason": reason, "action": action}


def figure(
    key: str,
    label: str,
    value: float | None,
    unit: str,
    as_of: str | None,
    state: str,
    *,
    simulated: bool = False,
    source: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """One figure with its unit, as-of time, freshness state and simulated flag."""

    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "as_of": as_of,
        "state": state,
        "simulated": simulated,
        "source": source,
        **extra,
    }


@dataclass
class _Read:
    """What the read collects besides the rows."""

    figures: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add(self, item: dict[str, Any]) -> dict[str, Any]:
        self.figures.append(item)
        return item


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return moment.isoformat()
    return value.isoformat()


def _month_start(day: date, offset: int = 0) -> date:
    month = day.month - 1 + offset
    return date(day.year + month // 12, month % 12 + 1, 1)


def _month_days(first: date) -> int:
    return (_month_start(first, 1) - first).days


# ---------------------------------------------------------------- positions (shared)


def net_positions(legs, today: date) -> dict[str, dict[str, float]]:
    """Per hub, net MWh/d today and the front month's average MWh/d (long positive).

    The front month is the calendar month after today's, as a month-ahead close prices it;
    its figure is the month's MWh over its days, so a leg that starts mid-month counts for
    the days it delivers. Hubs with no position in either are left out.
    """

    front = _month_start(today, 1)
    front_last = _month_start(today, 2) - timedelta(days=1)
    days = _month_days(front)
    out: dict[str, dict[str, float]] = {}
    for leg in legs:
        hub = leg.hub.upper()
        entry = out.setdefault(hub, {"today": 0.0, "front_month": 0.0})
        if leg.first_gas_day <= today <= leg.last_gas_day:
            entry["today"] += leg.mwh_per_day
        first, last = max(leg.first_gas_day, front), min(leg.last_gas_day, front_last)
        if first <= last:
            entry["front_month"] += leg.mwh_per_day * ((last - first).days + 1) / days
    return {
        hub: values
        for hub, values in out.items()
        if abs(values["today"]) > 1e-9 or abs(values["front_month"]) > 1e-9
    }


def front_month_label(today: date) -> str:
    return f"{_month_start(today, 1):%b-%y}"


# ---------------------------------------------------------------- the read


def build_today(
    session,
    caller: Caller,
    *,
    now: datetime | None = None,
    balance_reader: Callable[[], dict | None] | None = None,
) -> dict[str, Any]:
    """The Today read for this caller. ``balance_reader`` returns the NW Europe balance."""

    from eurogas_nexus.domain.market.gas_day import gas_day_label

    now = now or datetime.now(UTC)
    today = now.date()
    read = _Read()
    book = _book(caller, today, read)
    prices = _prices(caller, now, book, read)
    focus = focus_hubs(session, caller, book, prices)
    key_figures = _key_figures(caller, now, book, prices, read)
    key_figures["market"] = _market(caller, now, focus, read)
    changes = _changes(session, caller, now, read)
    rows = [
        key_figures,
        changes,
        _book_row(today, book, prices, read),
        _fundamentals(session, caller, now, balance_reader, read, focus),
        _needs_me(session, caller, now, book, focus, changes, key_figures, read),
    ]
    simulated = any(item["simulated"] for item in read.figures)
    stale = [
        {
            "key": item["key"],
            "label": item["label"],
            "state": item["state"],
            "as_of": item["as_of"],
        }
        for item in read.figures
        if item["state"] in LATE_STATES
    ]
    return {
        "as_of": now.isoformat(),
        "gas_day": gas_day_label(now),
        "front_month": front_month_label(today),
        "simulated": simulated,
        "simulated_notice": "Demo data: simulated figures, not market data." if simulated
        else None,
        "rows": rows,
        # The hubs the page is about: the book's, then the board's (or the user's own list).
        "focus_hubs": focus,
        "stale_figures": stale,
        "warnings": read.warnings,
    }


@dataclass
class _Book:
    inputs: Any = None
    positions: dict[str, dict[str, float]] = field(default_factory=dict)
    demo_marks: bool = False


def _book(caller: Caller, today: date, read: _Read) -> _Book:
    from eurogas_nexus.application.position_inputs import ladder_inputs

    end = _month_start(today, BOOK_HORIZON_MONTHS + 1) - timedelta(days=1)
    try:
        inputs = ladder_inputs(caller, today, today, end)
    except Exception as exc:  # noqa: BLE001 - the other rows stand without the book
        read.warnings.append(f"book: not available ({exc.__class__.__name__})")
        return _Book()
    read.warnings += [w for w in inputs.warnings if not w.startswith("DEMO")]
    return _Book(
        inputs=inputs,
        positions=net_positions(inputs.legs, today),
        demo_marks=any(w.startswith("DEMO") for w in inputs.warnings),
    )


# ---------------------------------------------------------------- row 1: key figures


def _prices(caller: Caller, now: datetime, book: _Book, read: _Read) -> dict[str, dict]:
    """Per hub, the front-month close (day-ahead where no month-ahead) and its day change.

    One series per hub: a provider's closes win over simulated ones (they never compete),
    then the series with the newest close. The change is against the series' previous close
    when it is at most four days earlier (a weekend and a holiday); further back it is not a
    day change and is left empty.
    """

    from eurogas_nexus.application.freshness_contract import close_state
    from eurogas_nexus.application.projections.daily_closes import daily_rows, in_native_unit
    from eurogas_nexus.domain.portfolio.position_ladder import MAX_VAR_GAP_DAYS

    series: dict[tuple[str, str, str], dict[date, dict]] = {}
    for row in daily_rows(caller, now.date() - timedelta(days=10), now.date()):
        if row["tenor"] not in {"month-ahead", "day-ahead"} or not row.get("hub_resolved", True):
            continue
        series.setdefault((row["hub"], row["tenor"], row["source_system"]), {})[row["day"]] = row
    best: dict[str, tuple] = {}
    for (hub, tenor, source), closes in series.items():
        last = closes[max(closes)]
        rank = (not last["simulated"], tenor == "month-ahead", max(closes))
        if hub not in best or rank > best[hub][0]:
            best[hub] = (rank, tenor, source, closes)
    out: dict[str, dict] = {}
    for hub, (_, tenor, source, closes) in best.items():
        days = sorted(closes)
        last = closes[days[-1]]
        if tenor == "month-ahead":
            start = last.get("period_start_utc")
            product = f"{start:%b-%y}" if start else "MA"
        else:
            product = "DA"
        # The desk's own quotation: NBP in p/th, through the unit authority (rule 17).
        shown, unit = in_native_unit(hub, last["price"], last["unit"])
        change = None
        change_basis = None
        if len(days) > 1 and (days[-1] - days[-2]).days <= MAX_VAR_GAP_DAYS:
            previous, _ = in_native_unit(hub, closes[days[-2]]["price"], last["unit"])
            change = round(shown - previous, 4)
            change_basis = days[-2].isoformat()
        state = close_state(days[-1], now.date())
        out[hub] = read.add(
            figure(
                f"price.{hub}",
                f"{hub} {product}",
                round(shown, 4),
                unit,
                _iso(last.get("observed_at_utc")) or days[-1].isoformat(),
                state,
                simulated=bool(last["simulated"]),
                source="Demo price" if last["simulated"] else source,
                hub=hub,
                product=product,
                tenor=tenor,
                close_day=days[-1].isoformat(),
                day_change=change,
                day_change_vs=change_basis,
            )
        )
    return out


def _key_figures(caller, now, book: _Book, prices: dict, read: _Read) -> dict[str, Any]:
    from eurogas_nexus.domain.risk.method_notes import method_note

    today = now.date()
    from eurogas_nexus.domain.ontology.markets import european_gas_hubs

    held = sorted(book.positions)
    # The other priced hubs in the board's order (TTF, NBP, THE, ...), not alphabetical: with
    # no book the first items are the reference hubs, never CEGH and ETF.
    board = {hub: index for index, hub in enumerate(european_gas_hubs())}
    hubs = held + sorted(
        (hub for hub in prices if hub not in held), key=lambda hub: (board.get(hub, 99), hub)
    )
    price_items: list[dict[str, Any]] = []
    for hub in hubs[:MAX_ITEMS]:
        if hub in prices:
            price_items.append(prices[hub])
        else:
            price_items.append(
                {
                    "key": f"price.{hub}",
                    "hub": hub,
                    "empty": empty(
                        "no_licensed_close",
                        f"No licensed {hub} close",
                        "Import settlements or connect a licensed price feed",
                    ),
                }
            )
    as_of = now.isoformat()
    position = None
    if book.positions:
        method = method_note("net_position", inputs_as_of={"positions": as_of})
        position = {
            "today": read.add(
                figure(
                    "position.net.today",
                    "Net position today",
                    round(sum(v["today"] for v in book.positions.values()), 1),
                    "MWh/d",
                    as_of,
                    "current",
                    method=method,
                )
            ),
            "front_month": read.add(
                figure(
                    "position.net.front_month",
                    f"Net position {front_month_label(today)}",
                    round(sum(v["front_month"] for v in book.positions.values()), 1),
                    "MWh/d",
                    as_of,
                    "current",
                    method=method,
                )
            ),
        }
    limit = _tightest_limit(caller, now, read)
    out: dict[str, Any] = {
        "key": "key_figures",
        "title": "Key figures",
        "prices": price_items,
        "prices_empty": None
        if price_items
        else empty(
            "no_prices",
            "No licensed hub closes",
            "Import settlements or connect a licensed price feed",
        ),
        "position": position,
        "position_empty": None
        if position
        else empty("no_position", "No positions in the books you can see", "Open Position"),
        "tightest_limit": limit if limit and "empty" not in limit else None,
        "limit_empty": limit.get("empty") if limit and "empty" in limit else None,
    }
    out["populated"] = bool(price_items or position or out["tightest_limit"])
    return out


def _tightest_limit(caller: Caller, now: datetime, read: _Read) -> dict[str, Any] | None:
    """The highest utilisation among the credit lines and mandates the caller may see."""

    from eurogas_nexus.application.freshness_contract import close_state
    from eurogas_nexus.application.limits_service import credit_exposure_rows, mandate_usage_rows
    from eurogas_nexus.domain.risk.method_notes import method_note

    today = now.date()
    try:
        credit = credit_exposure_rows(caller, today)
        mandates = mandate_usage_rows(caller, today)
    except Exception as exc:  # noqa: BLE001 - one missing section must not lose the read
        read.warnings.append(f"limits: not available ({exc.__class__.__name__})")
        return None
    visible = _limits_visibility()
    candidates: list[tuple[float, str, dict]] = []
    counts = {"breach": 0, "watch": 0, "expired": 0, "shown": 0}
    for kind, result in (("credit", credit), ("mandate", mandates)):
        for row, books in zip(result.rows, result.books, strict=True):
            if not visible(books):
                continue
            counts["shown"] += 1
            if row["status"] in counts:
                counts[row["status"]] += 1
            if row.get("utilisation_pct") is not None:
                candidates.append((float(row["utilisation_pct"]), kind, row))
    if not candidates:
        if counts["shown"]:
            return {"empty": empty("no_limit_usage", "No limit has a measured usage",
                                   "Open Limits")}
        return {"empty": empty("no_limits", "No credit lines or mandates you can see",
                               "Risk adds them under Limits")}
    used, kind, row = max(candidates, key=lambda item: item[0])
    # Demo marks value the line only when some close was used (the caller may hold none).
    simulated = (
        kind == "credit"
        and credit.marks_as_of is not None
        and any(w.startswith("DEMO") for w in credit.warnings)
    )
    if kind == "credit":
        marks_day = date.fromisoformat(credit.marks_as_of) if credit.marks_as_of else None
        item = figure(
            f"limit.credit.{row['counterparty_id']}",
            f"{row['counterparty']} credit headroom",
            row["headroom"],
            row["currency"],
            credit.marks_as_of or today.isoformat(),
            close_state(marks_day, today),
            simulated=simulated,
            utilisation_pct=used,
            status=row["status"],
            unvalued_legs=row["unvalued_legs"],
            name=row["counterparty"],
            kind="credit",
            why={"subject": "credit", "id": row["counterparty_id"]},
            method=method_note(
                "credit_exposure",
                inputs_as_of={"positions": today.isoformat(), "marks": credit.marks_as_of},
            ),
        )
    else:
        cap = row.get("max_net_mwh_per_month")
        item = figure(
            f"limit.mandate.{row['mandate_id']}",
            f"{row['name']} mandate headroom",
            None if cap is None else round(float(cap) - float(row["largest_net_mwh"]), 1),
            "MWh",
            now.isoformat(),
            "current",
            utilisation_pct=used,
            status=row["status"],
            name=row["name"],
            kind="mandate",
            why={"subject": "mandate", "id": row["mandate_id"]},
            method=method_note("mandate_usage", inputs_as_of={"positions": today.isoformat()}),
        )
    read.add(item)
    item["counts"] = counts
    return item


def _limits_visibility() -> Callable[[tuple[str, ...]], bool]:
    """A limits row is visible only to a caller who sees every book behind it (alert_scope)."""

    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    with get_session_factory()() as session:
        allowed = visible_book_ids(session)
    if allowed is None:
        return lambda _books: True
    return lambda books: bool(books) and all(book and book in allowed for book in books)


# ---------------------------------------------------------------- row 2: what changed


def _changes(session, caller: Caller, now: datetime, read: _Read) -> dict[str, Any]:
    alerts = _alerts(session, now)
    outages = _outages(session, caller, now, read)
    return {
        "key": "changes",
        "title": "What changed",
        "alerts": alerts,
        "outages": outages,
        "populated": bool(alerts["items"] or outages["items"]),
        "empty": None
        if alerts["items"] or outages["items"]
        else empty("nothing_changed", "No open alerts or outages", "Open Events"),
    }


def _alerts(session, now: datetime) -> dict[str, Any]:
    """Open alerts the caller may see: counts as the alert centre and ticker count them."""

    from eurogas_nexus.application.alert_scope import alert_visibility
    from eurogas_nexus.db.models import MonitoringAlertRecord
    from eurogas_nexus.db.repositories.monitoring import monitoring_summary

    visible = alert_visibility(session)
    summary = monitoring_summary(session, visible)
    open_rows = [
        row
        for row in session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.status == "open")
        .filter(MonitoringAlertRecord.severity.in_(("critical", "warning")))
        .all()
        if visible(row)
    ]
    # Limits and outages have their own places on the page (key figures, outages), so they
    # are counted here but listed once, there (one number, one place).
    rows = [
        row for row in open_rows if row.category != "limits" and row.alert_type != "outage"
    ]
    rows.sort(
        key=lambda row: (
            row.severity != "critical",
            -(row.updated_at_utc or row.detected_at_utc or now).timestamp(),
        )
    )
    return {
        "counts": {
            "open": summary["open_count"],
            "critical": summary["critical_count"],
            "warning": summary["warning_count"],
        },
        "items": [
            {
                "alert_id": row.alert_id,
                "severity": row.severity,
                "category": row.category,
                "title": row.title_en,
                "title_zh": row.title_zh_cn,
                "as_of": _iso(row.updated_at_utc or row.detected_at_utc),
                "simulated": bool(row.simulated),
                "why": {"subject": "alert", "id": row.alert_id},
            }
            for row in rows[:MAX_ITEMS]
        ],
        "more": max(0, len(rows) - MAX_ITEMS),
        "listed_elsewhere": len(open_rows) - len(rows),
    }


def _outages(session, caller: Caller, now: datetime, read: _Read) -> dict[str, Any]:
    """Outages from the ticker's and the map's service; counts include unplaced assets."""

    from sqlalchemy import func

    from eurogas_nexus.application.freshness_contract import definition_by_id, receipt_state
    from eurogas_nexus.application.remit_outages import load_outage_rows
    from eurogas_nexus.db.models import RemitUmmRecord
    from eurogas_nexus.domain.dataops.entitlement import filter_rows_for_principal
    from eurogas_nexus.domain.observations.remit_umm import outage_events

    # One row per event (the outage list's rule): messages naming the same asset, period and
    # size are one outage, counted and listed once with every operator named.
    rows = outage_events(
        filter_rows_for_principal(
            caller.principal,
            load_outage_rows(session, now=now, horizon_days=OUTAGE_HORIZON_DAYS),
        )
    )
    received = session.query(func.max(RemitUmmRecord.ingested_at_utc)).scalar()
    definition = definition_by_id("src-remit-umm")
    state = receipt_state(definition, received, now) if definition else "never"
    as_of = _iso(received)
    active = [row for row in rows if row["status"] == "active"]
    counts = {"active": len(active), "scheduled": len(rows) - len(active), "total": len(rows)}
    demo = any(str(row.get("source_reference") or "").lower().startswith("demo") for row in rows)
    read.add(
        figure(
            "outages.active",
            "Outages active now",
            float(len(active)),
            "outages",
            as_of,
            state,
            simulated=demo,
            source="REMIT",
        )
    )
    horizon = now + timedelta(hours=36)

    def size(row) -> float:
        return float(row.get("unavailable_gwh_d") or 0.0)

    soon = [
        row
        for row in rows
        if row["status"] == "active" or datetime.fromisoformat(str(row["start_utc"])) <= horizon
    ]
    soon.sort(key=lambda row: (row["status"] != "active", -size(row)))
    items = []
    for row in soon[:MAX_ITEMS]:
        gwh = row.get("unavailable_gwh_d")
        items.append(
            {
                "event_id": row["event_id"],
                "facility": row["facility_name"],
                "zone": row.get("balancing_zone"),
                "event_type": row.get("event_type"),
                "status": row["status"],
                "start_utc": row["start_utc"],
                "end_utc": row.get("end_utc"),
                # GWh/d where the message converts, else the message's own unit.
                "unavailable": round(float(gwh), 1)
                if gwh is not None
                else row.get("unavailable_capacity"),
                "unit": "GWh/d" if gwh is not None else row.get("unit"),
                "as_of": row.get("published_at_utc"),
                "simulated": str(row.get("source_reference") or "").lower().startswith("demo"),
                "operators": row.get("operators") or [],
                "message_count": row.get("message_count") or 1,
                "why": {"subject": "outage", "id": str(row["event_id"])},
            }
        )
    return {
        "counts": counts,
        "horizon_days": OUTAGE_HORIZON_DAYS,
        "as_of": as_of,
        "state": state,
        "items": items,
        "more": max(0, len(soon) - MAX_ITEMS),
    }


# ---------------------------------------------------------------- row 3: book v market


def _same_price(price: dict, mark_mwh: float, mark_unit: str) -> bool:
    """Whether the shown price (native unit, e.g. p/th) is the mark (per MWh)."""

    from eurogas_nexus.domain.market.units import UnitConversionError, convert_price

    try:
        native = convert_price(mark_mwh, mark_unit, price["unit"])
    except UnitConversionError:
        return False
    return abs(round(native, 4) - price["value"]) < 1e-9


def _book_row(today: date, book: _Book, prices: dict, read: _Read) -> dict[str, Any]:
    from eurogas_nexus.application.freshness_contract import close_state
    from eurogas_nexus.application.projections.daily_closes import in_native_unit
    from eurogas_nexus.domain.ontology.markets import quote_currency
    from eurogas_nexus.domain.portfolio.position_ladder import MAX_VAR_GAP_DAYS, build_ladder
    from eurogas_nexus.domain.risk.method_notes import method_note

    if not book.positions:
        return {
            "key": "book",
            "title": "Our book against the market",
            "hubs": [],
            "populated": False,
            "empty": empty("no_position", "No positions in the books you can see",
                           "Open Position"),
        }
    inputs = book.inputs
    end = _month_start(today, BOOK_HORIZON_MONTHS + 1) - timedelta(days=1)
    ladder = build_ladder(inputs.legs, horizon_start=today, horizon_end=end)
    net_open: dict[str, float] = {}
    long_hubs, short_hubs = set(), set()
    for row in ladder:
        net_open[row.hub] = net_open.get(row.hub, 0.0) + row.net_mwh
        if row.net_mwh > 1e-9:
            long_hubs.add(row.hub)
        elif row.net_mwh < -1e-9:
            short_hubs.add(row.hub)
    offsetting = long_hubs & short_hubs
    as_of = datetime.combine(today, datetime.min.time(), tzinfo=UTC).isoformat()
    hubs = []
    for hub in sorted(book.positions):
        position = book.positions[hub]
        currency = quote_currency(hub)
        closes = inputs.closes.get(hub, {})
        days = sorted(closes)
        mark = None
        pnl: dict[str, Any]
        price = prices.get(hub)
        # With demo marks on, a mark is simulated unless the hub's close is a provider's.
        demo = book.demo_marks and (price is None or price["simulated"])
        if days:
            same = (
                price is not None
                and price["close_day"] == days[-1].isoformat()
                and _same_price(price, closes[days[-1]], f"{currency}/MWh")
            )
            # The mark is quoted as the desk quotes the hub (NBP in p/th, rule 17); the
            # book values it per MWh, which travels with it for the Method note.
            per_mwh = closes[days[-1]]
            shown, shown_unit = in_native_unit(hub, per_mwh, f"{currency}/MWh")
            mark = read.add(
                figure(
                    f"mark.{hub}",
                    f"{hub} mark",
                    round(shown, 4),
                    shown_unit,
                    days[-1].isoformat(),
                    close_state(days[-1], today),
                    simulated=demo,
                    same_as=f"price.{hub}" if same else None,
                    value_mwh=round(per_mwh, 4),
                    unit_mwh=f"{currency}/MWh",
                )
            )
        method = method_note(
            "day_pnl_change",
            inputs_as_of={
                "positions": as_of,
                "close": days[-1].isoformat() if days else None,
                "previous_close": days[-2].isoformat() if len(days) > 1 else None,
            },
        )
        if not days:
            pnl = {"empty": empty("no_mark", f"No licensed {hub} close to mark the book",
                                  "Import settlements or connect a licensed price feed")}
        elif hub in offsetting:
            pnl = {"empty": empty("offsetting_months",
                                  f"{hub} is long and short in different months: a flat "
                                  "move is not its P&L", "Open Position for tenor exposure")}
        elif len(days) < 2 or (days[-1] - days[-2]).days > MAX_VAR_GAP_DAYS:
            pnl = {"empty": empty("no_previous_close", f"No previous {hub} close",
                                  "Import settlements")}
        else:
            change = net_open.get(hub, 0.0) * (closes[days[-1]] - closes[days[-2]])
            pnl = read.add(
                figure(
                    f"pnl.day_change.{hub}",
                    f"{hub} day P&L change",
                    round(change, 2),
                    currency,
                    days[-1].isoformat(),
                    close_state(days[-1], today),
                    simulated=demo,
                    method=method,
                )
            )
        hubs.append(
            {
                "hub": hub,
                "position_today": read.add(
                    figure(f"position.{hub}.today", f"{hub} today",
                           round(position["today"], 1), "MWh/d", as_of, "current")
                ),
                "position_front_month": read.add(
                    figure(f"position.{hub}.front_month",
                           f"{hub} {front_month_label(today)}",
                           round(position["front_month"], 1), "MWh/d", as_of, "current")
                ),
                "net_open_mwh": round(net_open.get(hub, 0.0), 1),
                "mark": mark,
                "day_pnl_change": pnl,
            }
        )
    return {
        "key": "book",
        "title": "Our book against the market",
        "hubs": hubs,
        "horizon_months": BOOK_HORIZON_MONTHS,
        "populated": True,
        "empty": None,
    }


# ---------------------------------------------------------------- row 4: fundamentals


def _fundamentals(
    session, caller, now, balance_reader, read: _Read, focus: list[str] | None = None
) -> dict[str, Any]:
    storage = _storage(session, caller, now, read)
    balance = _balance(session, caller, now, balance_reader, read)
    europe = _storage_europe(session, caller, now, focus or [], read)
    shown = "empty" not in storage or "empty" not in balance or "empty" not in europe
    return {
        "key": "fundamentals",
        "title": "Fundamentals",
        "storage": storage,
        "storage_europe": europe,
        "balance": balance,
        "populated": shown,
        "empty": None
        if shown
        else empty("fundamentals_not_connected", "Storage data not connected",
                   "Connect GIE AGSI in Sources"),
    }


def _storage(session, caller: Caller, now: datetime, read: _Read) -> dict[str, Any]:
    """NW Europe storage fill: facilities that publish a working capacity, complete days.

    The scope is the balance's inventory scope (GB publishes no working capacity). A day
    counts only when as many countries reported as on the best-covered day of the window,
    so a day half-published is not read as a draw. Provider rows win over simulated ones.
    """


    from eurogas_nexus.application.freshness_contract import period_state
    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models.observation import StorageObservationRecord as Storage
    from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES
    from eurogas_nexus.domain.market.storage_targets import (
        DEFAULT_DEADLINE,
        DEFAULT_TARGET_PCT,
        DEFAULT_WINDOW_OPEN,
    )

    naive = session.get_bind().dialect.name == "sqlite"

    def window(until: datetime, days: int):
        """Storage rows of the NW Europe countries for ``days`` gas days up to ``until``."""

        first = until - timedelta(days=days + 5)
        records = (
            session.query(
                Storage.period_start_utc,
                Storage.country,
                Storage.source_system,
                Storage.inventory_twh,
                Storage.working_capacity_twh,
            )
            .filter(identity_clause(session, Storage))
            .filter(Storage.country.in_(NWE_COUNTRIES))
            .filter(Storage.inventory_twh.isnot(None), Storage.working_capacity_twh.isnot(None))
            .filter(Storage.period_start_utc >= (first.replace(tzinfo=None) if naive else first))
            .filter(Storage.period_start_utc <= (until.replace(tzinfo=None) if naive else until))
            .limit(40_000)
            .all()
        )
        allowed = [r for r in records if row_allowed(caller.principal, r.source_system)]
        real = [r for r in allowed if not str(r.source_system).endswith("_Sim")]
        return real or allowed, bool(allowed) and not real

    def complete_days(rows) -> tuple[dict, dict, list[date]]:
        """Inventory and capacity by day and country; only days as covered as the best one."""

        by_day: dict[date, dict[str, list[float]]] = {}
        starts: dict[date, datetime] = {}
        for record in rows:
            start = record.period_start_utc
            start = start.replace(tzinfo=UTC) if start.tzinfo is None else start.astimezone(UTC)
            day = start.date()
            entry = by_day.setdefault(day, {}).setdefault(record.country, [0.0, 0.0])
            entry[0] += float(record.inventory_twh)
            entry[1] += float(record.working_capacity_twh)
            starts[day] = max(starts.get(day, start), start)
        if not by_day:
            return by_day, starts, []
        coverage = max(len(countries) for countries in by_day.values())
        full = sorted(d for d, countries in by_day.items() if len(countries) == coverage)
        return by_day, starts, full

    def fill(by_day: dict, day: date) -> tuple[float, float | None]:
        inventory = sum(v[0] for v in by_day[day].values())
        capacity = sum(v[1] for v in by_day[day].values())
        return inventory, (round(100 * inventory / capacity, 2) if capacity else None)

    rows, simulated = window(now, STORAGE_DAYS)
    by_day, starts, all_days = complete_days(rows)
    if not all_days:
        held = _held_back(session, ("GIE",))
        if held:
            # Not a silent gap: the gate holds GIE back until an administrator approves it.
            return {"empty": empty("source_not_approved", held[0]["text"],
                                   "Admin → Connectors")}
        return {"empty": empty("storage_not_connected", "Storage data not connected",
                               "Connect GIE AGSI in Sources")}
    days = all_days[-STORAGE_DAYS:]
    series = []
    for day in days:
        inventory, fill_pct = fill(by_day, day)
        series.append(
            {"day": day.isoformat(), "inventory_twh": round(inventory, 2), "fill_pct": fill_pct}
        )
    last = days[-1]
    latest = series[-1]
    dataset = "GIE storage (AGSI)"
    item = read.add(
        figure(
            "storage.nwe.fill",
            "NW Europe storage fill",
            latest["fill_pct"],
            "%",
            last.isoformat(),
            period_state(dataset, starts[last], now),
            simulated=simulated,
            source="Demo" if simulated else ", ".join(sorted({r.source_system for r in rows})),
            countries=sorted(by_day[last]),
        )
    )
    week_before = next((d for d in reversed(days) if d <= last - timedelta(days=7)), None)
    return {
        "latest": item,
        "inventory_twh": latest["inventory_twh"],
        # Inventory and working capacity (TWh) by country, on the newest complete day and a
        # week before it: the reports' storage-by-country join reads these.
        "by_country": {c: tuple(v) for c, v in by_day[last].items()},
        "by_country_week": ({c: tuple(v) for c, v in by_day[week_before].items()}
                            if week_before else {}),
        "series": series,
        # The EU filling target (Regulation (EU) 2022/1032 as amended): met at any point in
        # the window; the desk's own version is an input of the storage trajectory.
        "target": {
            "pct": DEFAULT_TARGET_PCT,
            "window_open": f"{DEFAULT_WINDOW_OPEN[0]:02d}-{DEFAULT_WINDOW_OPEN[1]:02d}",
            "deadline": f"{DEFAULT_DEADLINE[0]:02d}-{DEFAULT_DEADLINE[1]:02d}",
        },
        "unit": "%",
    }


def _balance(session, caller: Caller, now, balance_reader, read: _Read) -> dict[str, Any]:
    """The NW Europe balance's measured days, as ``/api/market/nwe-balance`` returns them.

    Shown only when the caller may read every source behind it (a derived result is as
    licensed as its least licensed input).
    """

    from eurogas_nexus.application.freshness_contract import period_state
    from eurogas_nexus.application.pipeline_supply import LANDING_POINTS
    from eurogas_nexus.db.models import FlowObservationRecord as Flow
    from eurogas_nexus.db.models.observation import (
        LngObservationRecord as Lng,
    )
    from eurogas_nexus.db.models.observation import (
        StorageObservationRecord as Storage,
    )
    from eurogas_nexus.domain.dataops.entitlement import derived_result_access
    from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES

    if balance_reader is None:
        return {"empty": empty("balance_unavailable", "Balance not available here",
                               "Open Balance and weather")}
    naive = session.get_bind().dialect.name == "sqlite"
    first = now - timedelta(days=60)
    bound = first.replace(tzinfo=None) if naive else first
    sources: set[str] = set()
    for model, scope in (
        (Storage, Storage.country.in_(NWE_COUNTRIES)),
        (Lng, Lng.country.in_(NWE_COUNTRIES)),
        (Flow, Flow.point_id.in_(sorted({p.point_id for p in LANDING_POINTS}))),
    ):
        sources |= {
            value
            for (value,) in session.query(model.source_system)
            .filter(scope, model.period_start_utc >= bound)
            .distinct()
            .all()
            if value
        }
    if sources and derived_result_access(caller.principal, sources).outcome.value != "ALLOWED":
        return {"empty": empty("balance_not_licensed",
                               "The balance uses data outside your licences",
                               "Ask your administrator for the data scope")}
    try:
        data = balance_reader() or {}
    except Exception as exc:  # noqa: BLE001 - one missing section must not lose the read
        read.warnings.append(f"balance: not available ({exc.__class__.__name__})")
        data = {}
    history = list(data.get("history") or [])[-BALANCE_DAYS:]
    if not history:
        held = _held_back(session, ("ENTSOG", "GIE"))
        if held:
            return {"empty": empty("source_not_approved",
                                   "; ".join(item["text"] for item in held),
                                   "Admin → Connectors")}
        return {"empty": empty("balance_not_connected",
                               "Balance needs ENTSOG flows, GIE storage and LNG",
                               "Connect ENTSOG and GIE in Sources")}
    simulated = any(str(source).endswith("_Sim") for source in sources)
    last_day = date.fromisoformat(history[-1]["day"])
    from eurogas_nexus.domain.market.gas_day import gas_day_start_utc

    # The gas day's start, as the storage figure's period start: one clock for both.
    start = gas_day_start_utc(datetime.combine(last_day, datetime.min.time(), tzinfo=UTC)
                              + timedelta(hours=12))
    item = read.add(
        figure(
            "balance.nwe.supply_call",
            "NW Europe supply call",
            history[-1]["call_gwh"],
            "GWh/d",
            last_day.isoformat(),
            period_state("GIE storage (AGSI)", start, now),
            simulated=simulated,
            source="Demo" if simulated else "ENTSOG, GIE, National Gas",
        )
    )
    # E.2 row 4: the call today against its 7-day average, and LNG send-out against yesterday.
    calls = [float(day["call_gwh"]) for day in history[-7:] if day.get("call_gwh") is not None]
    lng = [day.get("lng_gwh") for day in history[-2:]]
    return {
        "latest": item,
        "series": history,
        "unit": "GWh/d",
        "call_7d_avg_gwh": round(sum(calls) / len(calls), 1) if len(calls) == 7 else None,
        "lng_gwh": lng[-1],
        "lng_vs_yesterday_gwh": round(lng[-1] - lng[0], 1)
        if len(lng) == 2 and None not in lng else None,
    }


# ---------------------------------------------------------------- design basis 2, section E


def focus_hubs(session, caller: Caller, book: _Book, prices: dict) -> list[str]:
    """My hubs: the user's own list (Settings), else the book's hubs, then the board's order.

    At most :data:`MARKET_HUBS`. The list is the page's scope for prices, outages and storage
    countries; it is derived, never a filter the user has to set (E.1).
    """

    from eurogas_nexus.domain.ontology.markets import european_gas_hubs

    board = [hub.upper() for hub in european_gas_hubs()]
    own: list[str] = []
    principal_id = getattr(caller.principal, "principal_id", None)
    if principal_id:
        try:
            from eurogas_nexus.db.models import OrganisationSettingRecord, PrincipalPreferenceRecord
            from eurogas_nexus.domain.settings.preferences import effective_preferences

            organisation = {
                row.setting_key: row.value_json for row in session.query(OrganisationSettingRecord)
            }
            row = session.get(PrincipalPreferenceRecord, str(principal_id))
            personal = dict(row.preferences_json) if row else {}
            effective = effective_preferences(organisation, personal)
            own = [
                part.strip().upper()
                for part in str(effective.get("strip_focus_hubs") or "").split(",")
                if part.strip()
            ]
        except Exception:  # noqa: BLE001 - no preference store: the derived list stands
            own = []
    ordered: list[str] = []
    for hub in [*own, *sorted(book.positions), *board, *sorted(prices)]:
        hub = hub.upper()
        if hub not in ordered and (hub in board or hub in prices):
            ordered.append(hub)
    return ordered[:MARKET_HUBS]


def _market(caller: Caller, now: datetime, focus: list[str], read: _Read) -> dict[str, Any]:
    """Row 1, "My market": DA and front month per focus hub, a 30-day series, the spreads.

    Each hub's day-ahead and month-ahead closes come from its best series (a provider's closes
    win over simulated ones, then the newest), in the hub's own quotation (NBP in p/th). The
    spreads are front month against TTF in EUR/MWh, converted with the forward FX for the
    delivery month (CP-01) and compared with the transport cost of the route the tariff
    register prices (``route_tariff_cost``); a leg or a rate not held is named, never zero.
    """

    from eurogas_nexus.application.freshness_contract import close_state
    from eurogas_nexus.application.projections.daily_closes import daily_rows, in_native_unit
    from eurogas_nexus.domain.portfolio.position_ladder import MAX_VAR_GAP_DAYS

    today = now.date()
    series: dict[tuple[str, str, str], dict[date, dict]] = {}
    start = today - timedelta(days=MARKET_SERIES_DAYS + 15)
    for row in daily_rows(caller, start, today):
        if row["tenor"] not in {"month-ahead", "day-ahead"} or not row.get("hub_resolved", True):
            continue
        series.setdefault((row["hub"].upper(), row["tenor"], row["source_system"]), {})[
            row["day"]
        ] = row
    best: dict[tuple[str, str], tuple] = {}
    for (hub, tenor, source), closes in series.items():
        last = closes[max(closes)]
        rank = (not last["simulated"], max(closes), len(closes))
        if (hub, tenor) not in best or rank > best[(hub, tenor)][0]:
            best[(hub, tenor)] = (rank, source, closes)

    built: dict[tuple[str, str], dict[str, Any] | None] = {}

    def tenor_figure(hub: str, tenor: str) -> dict[str, Any] | None:
        if (hub, tenor) not in built:
            built[(hub, tenor)] = _tenor_figure(hub, tenor)
        return built[(hub, tenor)]

    def _tenor_figure(hub: str, tenor: str) -> dict[str, Any] | None:
        if (hub, tenor) not in best:
            return None
        _, source, closes = best[(hub, tenor)]
        days = sorted(closes)
        last = closes[days[-1]]
        if tenor == "month-ahead":
            period = last.get("period_start_utc")
            product = f"{period:%b-%y}" if period else "MA"
            key = f"market.{hub}.front_month"
        else:
            product = "DA"
            key = f"market.{hub}.day_ahead"
        shown, unit = in_native_unit(hub, last["price"], last["unit"])
        change = None
        if len(days) > 1 and (days[-1] - days[-2]).days <= MAX_VAR_GAP_DAYS:
            previous, _ = in_native_unit(hub, closes[days[-2]]["price"], closes[days[-2]]["unit"])
            change = round(shown - previous, 4)
        points = []
        for day in days[-MARKET_SERIES_DAYS:]:
            value, _ = in_native_unit(hub, closes[day]["price"], closes[day]["unit"])
            points.append({"day": day.isoformat(), "value": round(value, 4)})
        return (
            figure(
                key,
                f"{hub} {product}",
                round(shown, 4),
                unit,
                _iso(last.get("observed_at_utc")) or days[-1].isoformat(),
                close_state(days[-1], today),
                simulated=bool(last["simulated"]),
                source="Demo price" if last["simulated"] else source,
                hub=hub,
                product=product,
                tenor=tenor,
                close_day=days[-1].isoformat(),
                day_change=change,
                series=points,
                period_start_utc=_iso(last.get("period_start_utc")),
                period_end_utc=_iso(last.get("period_end_utc")),
                price_mwh=last.get("price_mwh"),
                unit_mwh=last.get("unit_mwh"),
            )
        )

    hubs = []
    for hub in focus:
        day_ahead = tenor_figure(hub, "day-ahead")
        front = tenor_figure(hub, "month-ahead")
        hubs.append(
            {
                "hub": hub,
                "day_ahead": day_ahead,
                "front_month": front,
                "empty": None
                if day_ahead or front
                else empty("no_licensed_close", f"No licensed {hub} close",
                           "Import settlements or connect a licensed price feed"),
            }
        )
    # Only the figures on the page enter the freshness list; a spread's legs are its own.
    for hub in hubs:
        for item in (hub["day_ahead"], hub["front_month"]):
            if item is not None:
                read.add(item)
    fronts = {
        hub: fig for hub in sorted({h for pair in SPREAD_PAIRS for h in pair})
        if (fig := tenor_figure(hub, "month-ahead")) is not None
    }
    return {
        "hubs": hubs,
        "spreads": _spreads(caller, now, fronts, read),
        "series_days": MARKET_SERIES_DAYS,
    }


def _spreads(caller: Caller, now: datetime, fronts: dict, read: _Read) -> list[dict[str, Any]]:
    """Front-month spreads against TTF in EUR/MWh, with the route cost beside them."""

    from eurogas_nexus.application.market_normalisation import (
        NormalisationError,
        load_holdings,
        normalise_value,
    )
    from eurogas_nexus.application.route_tariff_cost import load_tariff_rows, route_cost
    from eurogas_nexus.domain.market.fx_forward import Delivery

    today = now.date()
    out: list[dict[str, Any]] = []
    holdings = None
    tariffs: list | None = None
    for hub, reference in SPREAD_PAIRS:
        leg, base = fronts.get(hub), fronts.get(reference)
        label = f"{hub}–{reference}"
        if leg is None or base is None:
            missing = hub if leg is None else reference
            out.append({"pair": label, "empty": empty(
                "no_front_month", f"No {missing} front-month close", "Open Prices")})
            continue
        if leg["product"] != base["product"]:
            out.append({"pair": label, "empty": empty(
                "different_months", f"{hub} and {reference} closes are for different months",
                "Open Prices")})
            continue
        first = date.fromisoformat(str(leg["period_start_utc"])[:10]) if leg.get(
            "period_start_utc") else _month_start(today, 1)
        last = _month_start(first, 1) - timedelta(days=1)
        delivery = Delivery(first, last, "month", leg["product"])
        if holdings is None:
            try:
                holdings = load_holdings(caller)
            except Exception as exc:  # noqa: BLE001 - the spread says why it is missing
                read.warnings.append(f"fx: not available ({exc.__class__.__name__})")
                holdings = False
        values = {}
        problem = None
        for name, item in ((hub, leg), (reference, base)):
            try:
                if not holdings:
                    raise NormalisationError("not_convertible", "no FX held")
                values[name] = normalise_value(
                    float(item["value"]), item["unit"], "EUR/MWh", holdings=holdings,
                    as_of=date.fromisoformat(item["close_day"]), delivery=delivery,
                    simulated=bool(item["simulated"]),
                )
            except NormalisationError as exc:
                problem = f"{name} in {item['unit']} cannot be put in EUR/MWh: {exc}"
                break
        if problem:
            out.append({"pair": label, "empty": empty("not_convertible", problem,
                                                      "Admin → Connectors: FX rates")})
            continue
        spread = values[hub]["value"] - values[reference]["value"]
        fx = values[hub]["normalisation"].get("fx") if isinstance(
            values[hub].get("normalisation"), dict) else None
        if tariffs is None:
            try:
                tariffs = load_tariff_rows()
            except Exception as exc:  # noqa: BLE001
                read.warnings.append(f"tariffs: not available ({exc.__class__.__name__})")
                tariffs = []
        route = route_cost(reference, hub, delivery, tariffs)
        cost = route.total if route.currency == "EUR" else None
        if cost is not None:
            verdict = "in_the_money" if spread > cost else "out_of_the_money"
            route_view = {"value": round(cost, 3), "unit": "EUR/MWh", "verdict": verdict,
                          "via": list(route.via), "input_class": route.input_class}
        else:
            reason = ("legs not held: " + ", ".join(route.missing_legs())) if route.legs and not \
                route.complete else ("legs in more than one currency" if route.legs else
                                     "; ".join(route.issues) or "no route priced")
            route_view = {"value": None, "unit": "EUR/MWh", "verdict": None, "reason": reason}
        simulated = bool(values[hub]["simulated"] or values[reference]["simulated"])
        out.append(read.add(figure(
            f"spread.{hub}.{reference}",
            f"{label} {leg['product']}",
            round(spread, 3),
            "EUR/MWh",
            max(leg["close_day"], base["close_day"]),
            leg["state"] if leg["state"] != "current" else base["state"],
            simulated=simulated,
            source="Demo price" if simulated else None,
            pair=label,
            product=leg["product"],
            fx=fx,
            route_cost=route_view,
        )))
    return out


def _needs_me(
    session, caller: Caller, now: datetime, book: _Book, focus: list[str],
    changes: dict, key_figures: dict, read: _Read,
) -> dict[str, Any]:
    """Row 3, "What needs me": one ranked list of at most five, each linking to its object.

    Order (E.2): must-act opportunities, unplanned outages touching the book or the focus hubs,
    limit alerts, then the best "could act" opportunity. With nothing to show the row is one
    sentence, never an empty panel.
    """

    from eurogas_nexus.application.desk_text import hub_for_zone

    items: list[dict[str, Any]] = []
    must: list[dict] = []
    could: list[dict] = []
    try:
        from eurogas_nexus.application.opportunities.listing import list_opportunities

        listing = list_opportunities(session, caller.principal, limit=NEEDS_ME_ITEMS, now_utc=now)
        lanes = listing.get("lanes") or {}
        must = list((lanes.get("must_act") or {}).get("items") or [])
        could = list((lanes.get("could_act") or {}).get("items") or [])
    except Exception as exc:  # noqa: BLE001 - no opportunity store: the other kinds stand
        read.warnings.append(f"opportunities: not available ({exc.__class__.__name__})")

    def opportunity(row: dict, lane: str) -> dict[str, Any]:
        return {
            "kind": "opportunity",
            "lane": lane,
            "id": row["opportunity_id"],
            "title": row.get("claim") or row.get("type"),
            "headline": row.get("headline"),
            "period": row.get("period"),
            "simulated": bool(row.get("simulated")),
            "as_of": row.get("last_evaluated_utc"),
            # Deals → Opportunities (CP-14); until it exists the mode link lands on Deals.
            "target": {"mode": "deals", "task": "opportunities",
                       "params": {"opportunity": row["opportunity_id"]}},
        }

    items += [opportunity(row, "must_act") for row in must]
    held = {hub.upper() for hub in book.positions}
    scope = held | {hub.upper() for hub in focus}
    for outage in (changes.get("outages") or {}).get("items") or []:
        if outage.get("event_type", "unplanned") == "planned":
            continue
        hub = hub_for_zone(str(outage.get("zone") or ""))
        if hub is None or hub.upper() not in scope:
            continue
        items.append({
            "kind": "outage",
            "id": outage["event_id"],
            "title": outage["facility"],
            "hub": hub,
            "touches_book": hub.upper() in held,
            "size": {"value": outage.get("unavailable"), "unit": outage.get("unit")},
            "status": outage.get("status"),
            "simulated": bool(outage.get("simulated")),
            "as_of": outage.get("as_of"),
            "why": outage.get("why"),
        })
    limit = key_figures.get("tightest_limit")
    for alert in _limit_alerts(session, now):
        items.append(alert)
    if not any(item["kind"] == "limit" for item in items) and limit and limit.get(
            "status") in {"breach", "watch"}:
        items.append({
            "kind": "limit",
            "id": limit["key"],
            "title": limit["label"],
            "status": limit.get("status"),
            "utilisation_pct": limit.get("utilisation_pct"),
            "simulated": bool(limit.get("simulated")),
            "as_of": limit.get("as_of"),
            "why": limit.get("why"),
        })
    if could:
        items.append(opportunity(could[0], "could_act"))
    shown = items[:NEEDS_ME_ITEMS]
    quiet = None
    if not shown:
        quiet = ("Nothing new since the last close: no unplanned outages at your hubs, "
                 "no alerts, no opportunity to act on.")
    return {
        "key": "needs_me",
        "title": "What needs me",
        "items": shown,
        "more": max(0, len(items) - NEEDS_ME_ITEMS),
        "quiet": quiet,
        "populated": bool(shown),
        "empty": None,
    }


def _limit_alerts(session, now: datetime) -> list[dict[str, Any]]:
    """Open limit alerts the caller may see, most severe first."""

    from eurogas_nexus.application.alert_scope import alert_visibility
    from eurogas_nexus.db.models import MonitoringAlertRecord

    visible = alert_visibility(session)
    rows = [
        row
        for row in session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.status == "open")
        .filter(MonitoringAlertRecord.category == "limits")
        .all()
        if visible(row)
    ]
    rows.sort(key=lambda row: (row.severity != "critical",
                               -(row.updated_at_utc or row.detected_at_utc or now).timestamp()))
    return [
        {
            "kind": "limit",
            "id": row.alert_id,
            "title": row.title_en,
            "title_zh": row.title_zh_cn,
            "status": "breach" if row.severity == "critical" else "watch",
            "simulated": bool(row.simulated),
            "as_of": _iso(row.updated_at_utc or row.detected_at_utc),
            "why": {"subject": "alert", "id": row.alert_id},
        }
        for row in rows[:NEEDS_ME_ITEMS]
    ]


def _storage_europe(
    session, caller: Caller, now: datetime, focus: list[str], read: _Read
) -> dict[str, Any]:
    """Row 4: Europe's storage season (band, mean, last year, target) and the country headlines.

    The storage fundamentals read (CP-04) for the EU region, with the season for the region
    only; the countries of the focus hubs come first, then the largest, up to
    :data:`STORAGE_COUNTRIES`.
    """

    from eurogas_nexus.application.fundamentals_storage import storage_read

    hub_country = {"TTF": "NL", "THE": "DE", "PEG": "FR", "ZTP": "BE", "PSV": "IT",
                   "CEGH": "AT", "PVB": "ES", "ETF": "DK"}
    focus_countries = [hub_country[hub] for hub in focus if hub in hub_country]
    try:
        data = storage_read(session, caller.principal, region="eu", season=["EU"],
                            focus=focus_countries, now=now)
    except Exception as exc:  # noqa: BLE001 - one missing section must not lose the read
        read.warnings.append(f"storage: not available ({exc.__class__.__name__})")
        return {"empty": empty("storage_not_connected", "Storage data not connected",
                               "Connect GIE AGSI in Sources")}
    region = data.get("region")
    if not region:
        return {"empty": empty("storage_not_connected", "Storage data not connected",
                               "Connect GIE AGSI in Sources")}
    countries = [
        {key: country.get(key) for key in (
            "code", "name", "simulated", "as_of", "fill_pct", "day_change_pts",
            "vs_average", "net_withdrawal_7d_twh_d", "spark")}
        for country in data.get("countries", [])[:STORAGE_COUNTRIES]
    ]
    return {
        "region": region,
        "countries": countries,
        "focus_countries": focus_countries,
        "missing": data.get("missing", []),
        "simulated": bool(data.get("simulated")),
        "unit": "%",
    }

