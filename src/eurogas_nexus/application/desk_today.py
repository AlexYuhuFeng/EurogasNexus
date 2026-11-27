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
affected instead of saying "N feeds stale". The Data feeds popover's slices are judged by the
same contract (``projections.freshness.contract_state_for_rows``: late is LATE, stale is
STALE), so the popover and this list cannot contradict each other (QA-R-07). A section with
nothing to show returns an ``empty`` state with the reason and the next action, never a
withheld marker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.application.bounded_reads import read_bounded
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.position_inputs import is_method_note, is_simulated_marks_warning
from eurogas_nexus.domain.ontology.notes import declare, split_notes

MAX_ITEMS = 6
#: The position ladder's default horizon: the day P&L change uses the same open position.
#: Today's book horizon: the ladder's default, through the one ``ladder_horizon``.
BOOK_HORIZON_MONTHS = 12


def book_horizon(today: date) -> tuple[date, date]:
    """The horizon of Today's book: the position ladder's default (``ladder_horizon``)."""

    from eurogas_nexus.domain.portfolio.position_ladder import ladder_horizon

    return ladder_horizon(today, BOOK_HORIZON_MONTHS)
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

#: A part of Today that could not be read (the other rows stand): "book: not available (X)".
DESK_READ_UNAVAILABLE = declare("DESK_READ_UNAVAILABLE", "{section}: not available ({error})")
DESK_READ_UNRESOLVED = declare("DESK_READ_UNRESOLVED", "{section}: not resolved ({error})")


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

    from eurogas_nexus.application.price_resolver import shared_price_book

    now = now or datetime.now(UTC)
    read = _Read()
    # P-08: one price per hub and month for every figure on the page, the book's marks and
    # the risk reads inside it (credit lines, mandates), loaded once.
    price_book = _price_book(session, caller, now, read)
    with shared_price_book(price_book):
        return _compose_today(session, caller, now, balance_reader, read, price_book)


def _compose_today(session, caller, now, balance_reader, read, price_book) -> dict[str, Any]:
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    today = now.date()
    book = _book(caller, today, read, now=now, price_book=price_book)
    prices = _prices(caller, now, book, read, price_book)
    focus = focus_hubs(session, caller, book, prices)
    key_figures = _key_figures(caller, now, book, prices, read)
    key_figures["market"] = _market(caller, now, focus, read, price_book)
    changes = _changes(session, caller, now, read)
    gas_day, checklist = _gas_day(session, caller, now, book, read)
    rows = [
        key_figures,
        changes,
        _book_row(today, book, prices, read),
        _fundamentals(session, caller, now, balance_reader, read, focus),
        _needs_me(session, caller, now, book, focus, changes, key_figures, read, checklist),
        # Appended (consumers index rows by position): what to clear today and tomorrow, and
        # the nominations and terminal steps that clear it.
        gas_day,
        checklist,
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
        # Every market figure on the page simulated: one quiet source line for the page and no
        # per-figure marker; mixed classes keep the marker on each figure. Positions
        # and mandate sizes are book data, never simulated, so they do not decide it.
        "all_simulated": _all_simulated(read.figures),
        "simulated_notice": "Source: simulated figures." if simulated
        else None,
        "rows": rows,
        # The hubs the page is about: the book's, then the board's (or the user's own list).
        "focus_hubs": focus,
        "stale_figures": stale,
        # The same warnings as declared notes (domain/ontology/notes.py), said by the client.
        "warnings": read.warnings,
        "notes": split_notes(read.warnings)[1],
    }


def _gas_day(
    session, caller: Caller, now: datetime, book: _Book, read: _Read
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rows 6 and 7: "My gas day" (``application/gas_day``) and its checklist
    (``application/gas_day_checklist``), from one view of the caller's lines."""

    from eurogas_nexus.application.gas_day import gas_day_view, my_gas_day
    from eurogas_nexus.application.gas_day_checklist import checklist

    def unavailable(key: str, title: str) -> dict[str, Any]:
        return {
            "key": key,
            "title": title,
            "scope": None,
            "days": [],
            "simulated": False,
            "populated": False,
            "empty": empty(f"{key}_unavailable", "The gas day could not be read",
                           "Refresh, or open Book → Delivery"),
        }

    try:
        view = gas_day_view(session, caller, now=now, inputs=book.inputs)
        row = my_gas_day(session, caller, now=now, view=view)
    except Exception as exc:  # noqa: BLE001 - the other rows stand without it
        read.warnings.append(f"gas day: not available ({exc.__class__.__name__})")
        return (unavailable("gas_day", "My gas day"),
                unavailable("checklist", "Gas day checklist"))
    try:
        steps = checklist(session, caller, now=now, view=view)
    except Exception as exc:  # noqa: BLE001
        read.warnings.append(f"gas day checklist: not available ({exc.__class__.__name__})")
        steps = unavailable("checklist", "Gas day checklist")
    return row, steps


#: Figures that are the caller's own book data (never a simulated market value).
BOOK_DATA_KEYS = ("position.", "limit.mandate.")


#: Prices and the book's marks: what "simulated" is said about (AGENTS.md rule 17). A real input
#: beside them (a published tariff, an ECB rate, a public storage figure) does not make simulated
#: prices "mixed", so it does not bring back a pill on every figure.
PRICE_KEYS = ("price.", "market.", "spread.", "mark.")


def _all_simulated(figures: list[dict[str, Any]]) -> bool:
    """Every price and mark on the page is simulated: the page says it once (no per-figure pill)."""

    prices = [item for item in figures if item["key"].startswith(PRICE_KEYS)]
    return bool(prices) and all(item["simulated"] for item in prices)


@dataclass
class _Book:
    inputs: Any = None
    positions: dict[str, dict[str, float]] = field(default_factory=dict)
    demo_marks: bool = False


def _price_book(session, caller: Caller, now: datetime, read: _Read):
    """The caller's price book at ``now`` (``application/price_resolver``), or ``None``."""

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.price_resolver import open_price_book

    try:
        return open_price_book(session, caller, now=now)
    except SQLAlchemyError as exc:
        read.warnings.append(f"prices: not resolved ({exc.__class__.__name__})")
        return None


def _book(caller: Caller, today: date, read: _Read, *, now: datetime | None = None,
          price_book=None) -> _Book:
    from eurogas_nexus.application.position_inputs import ladder_inputs

    _start, end = book_horizon(today)
    try:
        inputs = ladder_inputs(caller, today, today, end, now=now, price_book=price_book)
    except Exception as exc:  # noqa: BLE001 - the other rows stand without the book
        read.warnings.append(f"book: not available ({exc.__class__.__name__})")
        return _Book()
    # Method notes (a floating price on the ladder by volume only) belong to the position's
    # method, not to Today's warnings: Today lists only what failed or was left out.
    read.warnings += [
        w for w in inputs.warnings if not is_simulated_marks_warning(w) and not is_method_note(w)
    ]
    return _Book(
        inputs=inputs,
        positions=net_positions(inputs.legs, today),
        demo_marks=any(is_simulated_marks_warning(w) for w in inputs.warnings),
    )


# ---------------------------------------------------------------- row 1: key figures


def _prices(
    caller: Caller, now: datetime, book: _Book, read: _Read, price_book=None
) -> dict[str, dict]:
    """Per hub, the front-month price (day-ahead where no month-ahead) and its day change.

    One series per hub: a provider's closes win over simulated ones (they never compete),
    then the series with the newest close. The series names the front month (its newest
    close's delivery month); the price shown is the one price for that hub and month
    (``price_resolver``: a fresher tick, a later close, or the close itself), with
    ``resolved_price`` saying which (P-08). The change is against the previous close of the
    same month when it is at most four days earlier (a weekend and a holiday); further back,
    or for another month, it is not a day change and is left empty. Day-ahead keeps its close.
    """

    from eurogas_nexus.application.freshness_contract import close_state
    from eurogas_nexus.application.price_resolver import resolve_close_series
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
        as_of = _iso(last.get("observed_at_utc")) or days[-1].isoformat()
        state = close_state(days[-1], now.date())
        simulated = bool(last["simulated"])
        shown_source = "Simulated price" if simulated else source
        resolved = None
        if tenor == "month-ahead":
            resolved = resolve_close_series(
                price_book, hub, closes, max_gap_days=MAX_VAR_GAP_DAYS
            )
        elif _todays_day_ahead(last, now):
            # The newest close is for the day-ahead the desk trades now: show that contract's
            # one price (a live tick when a feed quotes it), as the front month does. A
            # day-ahead is a new contract every day, so its change stays against the previous
            # day's close, as the close's own change is.
            resolved = resolve_close_series(
                price_book, hub, closes, max_gap_days=MAX_VAR_GAP_DAYS
            )
            if resolved is not None:
                resolved = {**resolved, "change": None if previous is None
                            else round(resolved["value"] - previous, 4)}
        elif tenor != "month-ahead":
            # During the trading day the day-ahead on screen is tomorrow's contract and the
            # newest close is still yesterday's (for today): a live tick for the contract
            # trading now is the price, and its change is against that newest close, as a
            # screen states a day-ahead's change.
            resolved = _live_day_ahead(price_book, hub, now, against=shown, against_day=days[-1])
        if resolved is not None:
            one = resolved["resolved"]
            shown, unit = resolved["value"], resolved["unit"]
            change = resolved["change"]
            change_basis = resolved["change_vs"].isoformat() if resolved["change_vs"] else None
            as_of = _iso(one.as_of_utc) or as_of
            state, simulated = one.state, one.simulated
            shown_source = "Simulated price" if simulated else one.source_system
        out[hub] = read.add(
            figure(
                f"price.{hub}",
                f"{hub} {product}",
                round(shown, 4),
                unit,
                as_of,
                state,
                simulated=simulated,
                source=shown_source,
                hub=hub,
                product=product,
                tenor=tenor,
                close_day=days[-1].isoformat(),
                day_change=change,
                day_change_vs=change_basis,
                resolved_price=None if resolved is None else resolved["payload"],
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
        and any(is_simulated_marks_warning(w) for w in credit.warnings)
    )
    if kind == "credit":
        # The row's own marks date and state (QA-R-07): the limits page, this figure and the
        # marks_stale alert read one judgement of the same close.
        marks_day = row.get("marks_as_of") or credit.marks_as_of
        item = figure(
            f"limit.credit.{row['counterparty_id']}",
            f"{row['counterparty']} credit headroom",
            row["headroom"],
            row["currency"],
            marks_day or today.isoformat(),
            row.get("state")
            or close_state(date.fromisoformat(marks_day) if marks_day else None, today),
            simulated=simulated,
            utilisation_pct=used,
            status=row["status"],
            unvalued_legs=row["unvalued_legs"],
            name=row["counterparty"],
            kind="credit",
            why={"subject": "credit", "id": row["counterparty_id"]},
            method=method_note(
                "credit_exposure",
                inputs_as_of={"positions": today.isoformat(), "marks": marks_day},
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
    from eurogas_nexus.domain.market.returns import contract_move
    from eurogas_nexus.domain.ontology.markets import quote_currency
    from eurogas_nexus.domain.portfolio.position_ladder import (
        MAX_VAR_GAP_DAYS,
        build_ladder,
        net_position_by_hub,
    )
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
    _start, end = book_horizon(today)
    ladder = build_ladder(inputs.legs, horizon_start=today, horizon_end=end)
    # The ladder's own net position per hub (flat-price exposure), not a second sum.
    net_open = net_position_by_hub(ladder)
    long_hubs, short_hubs = set(), set()
    for row in ladder:
        exposure = row.price_exposure_mwh
        if exposure > 1e-9:
            long_hubs.add(row.hub)
        elif exposure < -1e-9:
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
        one = (price or {}).get("resolved_price")
        # A demo price marks the book only with demo marks on (rule 17), as the ladder's.
        usable = one is not None and (not one["simulated"] or book.demo_marks)
        if usable and one["unit_mwh"] == f"{currency}/MWh":
            # P-08: the book is marked at the one price the key figure shows for its month,
            # as the ladder marks that month.
            mark = read.add(
                figure(
                    f"mark.{hub}",
                    f"{hub} mark",
                    one["value"],
                    one["unit"],
                    one["as_of_utc"] or price["as_of"],
                    one["state"],
                    simulated=demo or bool(one["simulated"]),
                    same_as=f"price.{hub}",
                    value_mwh=round(one["value_mwh"], 4),
                    unit_mwh=one["unit_mwh"],
                    resolved_price=one,
                )
            )
        elif days:
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
        marked = mark is not None and mark.get("resolved_price") is not None
        if marked:
            # The P&L moves with the price the page shows: the mark against the previous close
            # of the same month (the key figure's day change), per MWh.
            method = method_note(
                "day_pnl_change",
                inputs_as_of={
                    "positions": as_of,
                    "close": mark["as_of"],
                    "previous_close": price.get("day_change_vs"),
                },
            )
        else:
            method = method_note(
                "day_pnl_change",
                inputs_as_of={
                    "positions": as_of,
                    "close": days[-1].isoformat() if days else None,
                    "previous_close": days[-2].isoformat() if len(days) > 1 else None,
                },
            )
        if marked and hub not in offsetting:
            if price.get("day_change") is None:
                pnl = {"empty": empty("no_previous_close", f"No previous {hub} close",
                                      "Import settlements")}
            else:
                from eurogas_nexus.domain.market.units import convert_price

                moved = convert_price(price["day_change"], price["unit"], mark["unit_mwh"])
                pnl = read.add(
                    figure(
                        f"pnl.day_change.{hub}",
                        f"{hub} day P&L change",
                        round(net_open.get(hub, 0.0) * moved, 2),
                        currency,
                        mark["as_of"],
                        mark["state"],
                        simulated=mark["simulated"],
                        method=method,
                    )
                )
        elif not days:
            pnl = {"empty": empty("no_mark", f"No licensed {hub} close to mark the book",
                                  "Import settlements or connect a licensed price feed")}
        elif hub in offsetting:
            pnl = {"empty": empty("offsetting_months",
                                  f"{hub} is long and short in different months: a flat "
                                  "move is not its P&L", "Open Position for tenor exposure")}
        elif len(days) < 2 or (days[-1] - days[-2]).days > MAX_VAR_GAP_DAYS:
            pnl = {"empty": empty("no_previous_close", f"No previous {hub} close",
                                  "Import settlements")}
        elif (moved := contract_move(
            closes[days[-2]], closes[days[-1]],
            *(getattr(inputs, "close_contracts", {}).get(hub, {}).get(day) for day in days[-2:]),
        )) is None:
            # The series rolled to the next contract: the difference is a spread, not a move.
            pnl = {"empty": empty("no_previous_close", f"No previous {hub} close of the same "
                                  "contract (the series rolled)", "Import settlements")}
        else:
            change = net_open.get(hub, 0.0) * moved
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
        records = read_bounded(
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
            .filter(Storage.period_start_utc <= (until.replace(tzinfo=None) if naive else until)),
            40_000,
            what="storage observation",
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
            source="Simulated" if simulated else ", ".join(sorted({r.source_system for r in rows})),
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
            source="Simulated" if simulated else "ENTSOG, GIE, National Gas",
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
            from eurogas_nexus.domain.ontology.markets import canonical_hub

            # A hub saved under its other name (GTF) is followed as the hub itself (ETF).
            own = list(dict.fromkeys(
                canonical_hub(part) or part.strip().upper()
                for part in str(effective.get("strip_focus_hubs") or "").split(",")
                if part.strip()
            ))
        except Exception:  # noqa: BLE001 - no preference store: the derived list stands
            own = []
    ordered: list[str] = []
    for hub in [*own, *sorted(book.positions), *board, *sorted(prices)]:
        hub = hub.upper()
        if hub not in ordered and (hub in board or hub in prices):
            ordered.append(hub)
    return ordered[:MARKET_HUBS]


def _live_day_ahead(price_book, hub: str, now: datetime, *, against: float, against_day: date):
    """A live tick for the day-ahead contract trading at ``now``, or ``None`` (keep the close)."""

    from eurogas_nexus.application.price_resolver import month_window, price_payload
    from eurogas_nexus.application.projections.daily_closes import in_native_unit
    from eurogas_nexus.domain.market.gas_day import gas_day_label
    from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product

    if price_book is None:
        return None
    try:
        prompt = resolve_product("DA", date.fromisoformat(gas_day_label(now)))
    except ProductCodeError:
        return None
    window = month_window(prompt.first_gas_day, prompt.last_gas_day + timedelta(days=1))
    one = price_book.resolve(hub, *window)
    if one is None or one.kind != "live_tick":
        return None
    value, unit = in_native_unit(hub, one.value, one.unit)
    return {
        "resolved": one,
        "value": value,
        "unit": unit,
        "change": round(value - against, 4),
        "change_vs": against_day,
        "payload": price_payload(one),
    }


def _todays_day_ahead(close: dict[str, Any], now: datetime) -> bool:
    """Whether a day-ahead close is for the day-ahead contract of the gas day at ``now``."""

    from eurogas_nexus.domain.market.gas_day import gas_day_label
    from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product

    start = close.get("period_start_utc")
    if not isinstance(start, datetime | date):
        return False
    try:
        prompt = resolve_product("DA", date.fromisoformat(gas_day_label(now)))
    except ProductCodeError:
        return False
    first = start.date() if isinstance(start, datetime) else start
    return first == prompt.first_gas_day


def _market(
    caller: Caller, now: datetime, focus: list[str], read: _Read, price_book=None
) -> dict[str, Any]:
    """Row 1, "My market": DA and front month per focus hub, a 30-day series, the spreads.

    Each hub's day-ahead and month-ahead closes come from its best series (a provider's closes
    win over simulated ones, then the newest), in the hub's own quotation (NBP in p/th). The
    front month shows the one price for its month (``price_resolver``, as the key figures and
    the Prices board read it) with ``resolved_price``; the series stays the closes. The
    spreads are front month against TTF in EUR/MWh, converted with the forward FX for the
    delivery month (CP-01) and compared with the transport cost of the route the tariff
    register prices (``route_tariff_cost``); a leg or a rate not held is named, never zero.
    """

    from eurogas_nexus.application.freshness_contract import close_state
    from eurogas_nexus.application.price_resolver import resolve_close_series
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
        change = previous = None
        if len(days) > 1 and (days[-1] - days[-2]).days <= MAX_VAR_GAP_DAYS:
            previous, _ = in_native_unit(hub, closes[days[-2]]["price"], closes[days[-2]]["unit"])
            change = round(shown - previous, 4)
        points = []
        for day in days[-MARKET_SERIES_DAYS:]:
            value, _ = in_native_unit(hub, closes[day]["price"], closes[day]["unit"])
            points.append({"day": day.isoformat(), "value": round(value, 4)})
        as_of = _iso(last.get("observed_at_utc")) or days[-1].isoformat()
        state = close_state(days[-1], today)
        simulated = bool(last["simulated"])
        shown_source = "Simulated price" if simulated else source
        price_mwh, unit_mwh = last.get("price_mwh"), last.get("unit_mwh")
        resolved = None
        if tenor == "month-ahead":
            resolved = resolve_close_series(
                price_book, hub, closes, max_gap_days=MAX_VAR_GAP_DAYS
            )
        elif _todays_day_ahead(last, now):
            # The newest close is for the day-ahead the desk trades now: show that contract's
            # one price (a live tick when a feed quotes it), as the front month does. A
            # day-ahead is a new contract every day, so its change stays against the previous
            # day's close, as the close's own change is.
            resolved = resolve_close_series(
                price_book, hub, closes, max_gap_days=MAX_VAR_GAP_DAYS
            )
            if resolved is not None:
                resolved = {**resolved, "change": None if previous is None
                            else round(resolved["value"] - previous, 4)}
        else:
            # During the trading day the day-ahead trading now is tomorrow's contract and the
            # newest close is still the previous one: a live tick for the contract trading
            # now is the price, and its change is against that newest close.
            resolved = _live_day_ahead(price_book, hub, now, against=shown, against_day=days[-1])
        if resolved is not None:
            one = resolved["resolved"]
            shown, unit, change = resolved["value"], resolved["unit"], resolved["change"]
            as_of = _iso(one.as_of_utc) or as_of
            state, simulated = one.state, one.simulated
            shown_source = "Simulated price" if simulated else one.source_system
            price_mwh, unit_mwh = round(one.value, 6), one.unit
        return (
            figure(
                key,
                f"{hub} {product}",
                round(shown, 4),
                unit,
                as_of,
                state,
                simulated=simulated,
                source=shown_source,
                hub=hub,
                product=product,
                tenor=tenor,
                close_day=days[-1].isoformat(),
                day_change=change,
                series=points,
                period_start_utc=_iso(last.get("period_start_utc")),
                period_end_utc=_iso(last.get("period_end_utc")),
                price_mwh=price_mwh,
                unit_mwh=unit_mwh,
                resolved_price=None if resolved is None else resolved["payload"],
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
    from eurogas_nexus.application.route_tariff_cost import (
        load_route_capacity,
        load_tariff_rows,
        marginal_route_cost,
    )
    from eurogas_nexus.application.spreads_board import spread_direction
    from eurogas_nexus.domain.market.fx_forward import Delivery

    today = now.date()
    out: list[dict[str, Any]] = []
    holdings = None
    tariffs: dict | None = None
    bookings: list = []
    orders: dict = {}
    for hub, reference in SPREAD_PAIRS:
        leg, base = fronts.get(hub), fronts.get(reference)
        label = f"{hub}–{reference}"
        if leg is None or base is None:
            missing = hub if leg is None else reference
            out.append({"pair": label, "empty": {**empty(
                "no_front_month", f"No {missing} front-month close", "Open Prices"),
                "params": {"hub": missing}}})
            continue
        if leg["product"] != base["product"]:
            out.append({"pair": label, "empty": {**empty(
                "different_months", f"{hub} and {reference} closes are for different months",
                "Open Prices"), "params": {"hub": hub, "reference": reference}}})
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
        cause: dict[str, Any] = {}
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
                # The cause as a code with what it names, so the page says it in the reader's
                # language (the sentence above is the detail).
                cause = {"cause": getattr(exc, "cause", None) or exc.code,
                         "params": {"hub": name, "unit": item["unit"],
                                    **getattr(exc, "params", {})}}
                break
        if problem:
            out.append({"pair": label, "empty": {
                **empty("not_convertible", problem, "Admin → Connectors: FX rates"), **cause}})
            continue
        spread = values[hub]["value"] - values[reference]["value"]
        fx = values[hub]["normalisation"].get("fx") if isinstance(
            values[hub].get("normalisation"), dict) else None
        if tariffs is None:
            try:
                tariffs = {"ANNUAL": load_tariff_rows()}
                # TAR-2: the firm's booked capacity prices its part of a leg first.
                bookings, orders = load_route_capacity()
            except Exception as exc:  # noqa: BLE001
                read.warnings.append(f"tariffs: not available ({exc.__class__.__name__})")
                tariffs, bookings, orders = {}, [], {}

        def rows_for(product: str, held=tariffs) -> list:
            if product not in held:
                try:
                    held[product] = load_tariff_rows(product=product)
                except Exception:  # noqa: BLE001 - not held: the route says which product
                    held[product] = []
            return held[product]

        # The route runs from the cheaper hub to the dearer one, the rule Research > Spreads
        # uses, and the spread earns its absolute value less that cost (QA-R-06). The cost is
        # the marginal one (quant review 3.7): the monthly capacity product for the front
        # month, plus commodity charges and fuel gas; yearly capacity is sunk, shown beside.
        start, end = spread_direction(spread, hub, reference)
        marginal = marginal_route_cost(
            start, end, delivery, rows_for, bookings=bookings, orders=orders,
            gas_price=values[start]["value"],
        )
        route = marginal.choice.chosen
        cost = marginal.total if route.currency == "EUR" else None
        if cost is not None:
            net = abs(spread) - cost
            verdict = "in_the_money" if net > 0 else "out_of_the_money"
            route_view = {"value": round(cost, 3), "unit": "EUR/MWh", "verdict": verdict,
                          "from": start, "to": end, "net": round(net, 3),
                          "via": list(route.via), "input_class": route.input_class,
                          "product": marginal.product, "marginal": marginal.as_dict()}
        else:
            reason = ("legs not held: " + ", ".join(route.missing_legs())) if route.legs and not \
                route.complete else ("legs in more than one currency" if route.legs else
                                     "; ".join(route.issues) or "no route priced")
            route_view = {"value": None, "unit": "EUR/MWh", "verdict": None, "reason": reason,
                          "product": marginal.product, "marginal": marginal.as_dict()}
        simulated = bool(values[hub]["simulated"] or values[reference]["simulated"])
        out.append(read.add(figure(
            f"spread.{hub}.{reference}",
            f"{label} {leg['product']}",
            round(spread, 3),
            "EUR/MWh",
            max(leg["close_day"], base["close_day"]),
            leg["state"] if leg["state"] != "current" else base["state"],
            simulated=simulated,
            source="Simulated price" if simulated else None,
            pair=label,
            product=leg["product"],
            fx=fx,
            route_cost=route_view,
        )))
    return out


def _needs_me(
    session, caller: Caller, now: datetime, book: _Book, focus: list[str],
    changes: dict, key_figures: dict, read: _Read, checklist: dict | None = None,
) -> dict[str, Any]:
    """Row 3, "What needs me": one ranked list of at most five, each linking to its object.

    Order (E.2): must-act opportunities, unplanned outages touching the book or the focus hubs,
    limit alerts with the credit and mandate findings, then the best "could act" opportunity.
    A nomination due soon and a critical cargo change for the caller's role (LNG-2) come first.
    Opportunities and credit or mandate findings come from the role-aware discovery read
    (CP-24, ``application/discovery.py``), ranked for the caller's first job function and
    phrased in English and Chinese from the same evidence; every read inside it runs under
    the caller. With nothing to show the row is one sentence, never an empty panel.
    """

    from eurogas_nexus.application.desk_text import hub_for_zone

    items: list[dict[str, Any]] = []
    urgent: list[dict] = []
    later: list[dict] = []
    could: list[dict] = []
    try:
        from eurogas_nexus.application.discovery import discoveries

        held_functions = [
            str(item).upper() for item in getattr(caller.principal, "job_functions", ()) or ()
        ]
        function = held_functions[0] if held_functions else None
        # Each item carries its own simulated mark on Today: the sentence does not repeat it.
        found = discoveries(
            session, caller, function=function, language="en", now=now, simulated_marked=True
        )
        found_zh = discoveries(
            session, caller, function=function, language="zh", now=now, simulated_marked=True
        )
        chinese = {item["finding_id"]: item["sentence"] for item in found_zh["items"]}
        read.warnings.extend(found.get("warnings") or [])
        for item in found["items"]:
            entry = _finding_item(item, chinese.get(item["finding_id"]), found.get("as_of_utc"))
            if entry is None:
                continue
            if entry["kind"] != "opportunity":
                later.append(entry)  # credit and mandate findings sit with the limit alerts
            elif entry["lane"] == "could_act":
                could.append(entry)
            else:
                urgent.append(entry)
    except Exception as exc:  # noqa: BLE001 - no opportunity store: the other kinds stand
        read.warnings.append(f"discoveries: not available ({exc.__class__.__name__})")

    # A nomination due within three hours (or overdue) is time-critical, so first; one only
    # nominated beyond its tolerance sits with the limit findings (``needs_me_items``).
    from eurogas_nexus.application.gas_day_checklist import needs_me_items

    nominations = needs_me_items(checklist or {})
    items += [item for item in nominations if item["urgency"] in {"due_soon", "overdue"}]
    later += [item for item in nominations if item["urgency"] not in {"due_soon", "overdue"}]
    # SCHED-1: a reconciliation break of today's or tomorrow's gas day near its hub's cut-off
    # (or past the last renomination) is time-critical too; only for a reader of the book.
    items += _reconciliation_items(session, caller, now, read)
    # LNG-2: a cargo change's message for the caller's own role (trader, scheduler, risk, desk
    # head); a critical one sits with the time-critical items, the rest with the limits.
    try:
        from eurogas_nexus.application import lng_cargo_alerts

        cargo = lng_cargo_alerts.needs_me_items(
            session, getattr(caller.principal, "job_functions", ()) or (), now=now
        )
    except Exception as exc:  # noqa: BLE001 - no alert store: the other kinds stand
        read.warnings.append(f"cargo changes: not available ({exc.__class__.__name__})")
        cargo = []
    items += [item for item in cargo if item["status"] == "breach"]
    later += [item for item in cargo if item["status"] != "breach"]
    items += urgent
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
            # Since when it is out (or from when it is planned): the age of the message is noise.
            "since_utc": outage.get("start_utc"),
            "why": outage.get("why"),
        })
    limit = key_figures.get("tightest_limit")
    for alert in _limit_alerts(session, now):
        items.append(alert)
    items += later
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
        items.append(could[0])
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


def _reconciliation_items(session, caller: Caller, now: datetime, read: _Read) -> list[dict]:
    """The caller's gas-day reconciliation breaks near a cut-off (SCHED-1)."""

    from eurogas_nexus.security.authorization import Permission, authorize

    principal = getattr(caller, "principal", None)
    if principal is None or not authorize(principal, Permission.PORTFOLIO_READ).allowed:
        return []
    try:
        from eurogas_nexus.application.gas_day_reconciliation import (
            needs_me_items,
            reconciliation,
        )
        from eurogas_nexus.domain.market.gas_day import gas_day_label

        today = date.fromisoformat(gas_day_label(now))
        return needs_me_items(
            reconciliation(session, caller, day, now=now, breaks_only=True)
            for day in (today, today + timedelta(days=1)))
    except Exception as exc:  # noqa: BLE001 - the other kinds stand
        read.warnings.append(f"gas-day reconciliation: not available ({exc.__class__.__name__})")
        return []


def _finding_item(
    item: dict[str, Any], sentence_zh: str | None, as_of: str | None = None
) -> dict[str, Any] | None:
    """One discovery finding as a "What needs me" item, or None when it is only watched.

    An opportunity opens on Deals → Opportunities with the opportunity selected; a credit or
    mandate finding is a limit item (Book → Limits). The sentence is the discovery's own,
    with its input class stated in it.
    """

    kind = str(item.get("kind") or "")
    evidence = (item.get("evidence") or [{}])[0] or {}
    common = {
        "title": item["sentence"],
        "title_zh": sentence_zh,
        "simulated": bool(item.get("simulated")),
        "as_of": evidence.get("as_of_utc") or as_of,
        "quality": item.get("quality"),
    }
    if kind.startswith("opportunity."):
        opportunity_id = (item.get("link") or {}).get("opportunity_id")
        if not opportunity_id or item["severity"] < 2:
            return None
        return {
            "kind": "opportunity",
            "lane": "must_act" if item["severity"] >= 3 else "could_act",
            "id": opportunity_id,
            "headline": None,
            "period": None,
            **common,
            "target": {"mode": "deals", "task": "opportunities",
                       "params": {"opportunity": opportunity_id}},
        }
    if kind.startswith(("credit.", "mandate.")):
        return {
            "kind": "limit",
            "id": item["finding_id"],
            "status": "breach" if item["severity"] >= 3 else "watch",
            "utilisation_pct": None,
            **common,
        }
    return None


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
            "since_utc": None,  # a standing limit state has no news age to show
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

