"""Deal capture: import exchange exports, enter deals by hand, the blotter, the ETRM entry
sheet, the end-of-day check and the day's close (SMALL_DESK_PLAN section 4, steps 1 and 2).

A file comes in (an upload, or a file dropped in the watched folder), its format is named or
recognised by its headers, and every row becomes a canonical deal or a listed problem
(``domain/deals``). Each deal is stored as a version keyed by venue and venue trade id: the
same trade in a repeated export of the day adds nothing, a correction or a cancellation
adds a version and supersedes the earlier one, which is kept. A deal entered by hand (a
broker or bilateral deal) is the same record with ``origin = manual`` and the fields the
person typed listed, so every result built from it can say so (AGENTS.md rule 19).

The ETRM stays the official record (decision 11): the entry sheet is what the desk keys into
the ETRM, the end-of-day check compares the ETRM's own export with what was captured, and
closing the day records who acknowledged which differences. Book isolation applies through
the ORM (every table here carries ``book_id``). Nothing places, sends or pre-fills an order,
nominates, settles or books (rule 8).

交易捕获：导入交易所导出与手工录入、交易记录簿、ETRM 录入表、日终核对与日结；ETRM 仍为正式记录。
"""

from __future__ import annotations

import calendar as _calendar
import hashlib
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.deals.formats import DealFormat, FormatError
from eurogas_nexus.domain.deals.record import FIELDS, CanonicalDeal, RowProblem

MAX_FILE_BYTES = 16 * 1024 * 1024
#: The provider id captured deals carry when laid over the book (``position_inputs``).
OVERLAY_PROVIDER = "DEAL_CAPTURE"
ESTIMATE_LABEL = "desk estimate, before ETRM close"


class DealCaptureError(ValueError):
    """A request refused as a whole, with a stable code and the reason."""

    def __init__(self, code: str, message: str, status: int = 422, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}


def dec(value: Decimal | None) -> str | None:
    """A decimal as plain text without trailing zeros (``31.25``, never ``3.125E+1``)."""

    if value is None:
        return None
    text = format(Decimal(value).normalize(), "f")
    return "0" if text in {"-0", ""} else text


def actor_of(caller) -> str:
    principal = getattr(caller, "principal", caller)
    return str(getattr(principal, "name", None) or getattr(principal, "principal_id", None)
               or "api")[:128]


# ----------------------------------------------------------------------------- formats


MANUAL_FORMAT = DealFormat(
    name="manual",
    title="Entered by hand",
    venue="OTC",
    provenance="Entered by hand",
    adapter="mapped_csv",
    columns={name: (name,) for name in FIELDS},
    values={},
    defaults={},
    lot_sizes={},
    detect=(),
    timezone="UTC",
    date_formats=("%Y-%m-%d",),
    datetime_formats=("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"),
    verified=True,
)


def formats() -> tuple[dict[str, DealFormat], list[str]]:
    from eurogas_nexus.domain.deals.formats import load_formats

    return load_formats()


def formats_catalogue() -> dict[str, Any]:
    from eurogas_nexus.domain.deals.formats import sheet_layout_path
    from eurogas_nexus.domain.deals.sheet import load_layout

    found, errors = formats()
    try:
        layout = load_layout(sheet_layout_path()).describe()
    except (OSError, FormatError) as exc:
        layout, errors = None, [*errors, str(exc)]
    return {
        "formats": [item.describe() for item in sorted(found.values(), key=lambda f: f.name)],
        "sheet_layout": layout,
        "errors": errors,
    }


def sheet_layout():
    from eurogas_nexus.domain.deals.formats import sheet_layout_path
    from eurogas_nexus.domain.deals.sheet import load_layout

    try:
        return load_layout(sheet_layout_path())
    except (OSError, FormatError) as exc:
        raise DealCaptureError("sheet_layout_invalid", str(exc), status=500) from exc


# ----------------------------------------------------------------------------- books


def _require_book(session, book_id: str | None) -> str:
    """A book that exists and the caller may see (the ORM scope hides any other)."""

    from eurogas_nexus.db.models import TradingBookRecord

    if not book_id:
        raise DealCaptureError("book_required", "choose the book the deals belong to")
    if session.get(TradingBookRecord, book_id) is None:
        raise DealCaptureError("book_not_in_scope", f"book {book_id!r} is not one of yours",
                               status=404)
    return book_id


def books_choice(session) -> list[dict[str, str]]:
    from eurogas_nexus.db.models import TradingBookRecord

    return [
        {"book_id": row.book_id, "name": row.name, "legal_entity": row.legal_entity}
        for row in session.query(TradingBookRecord).order_by(TradingBookRecord.name).all()
        if row.active
    ]


# ----------------------------------------------------------------------------- storing


@dataclass
class ImportOutcome:
    file_id: str
    format_name: str
    format_title: str
    provenance: str
    verified: bool
    counts: dict[str, int] = field(default_factory=dict)
    problems: list[dict[str, Any]] = field(default_factory=list)
    deals: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "format": self.format_name,
            "format_title": self.format_title,
            "provenance": self.provenance,
            "verified": self.verified,
            "counts": self.counts,
            "problems": self.problems,
            "deals": self.deals,
        }


def _hidden_version(session, key: str) -> int:
    """The highest version of ``key`` in any book (the caller learns only that it exists)."""

    from sqlalchemy import func

    from eurogas_nexus.db.models import CapturedDealRecord

    held = (
        session.query(func.max(CapturedDealRecord.version))
        .filter(CapturedDealRecord.deal_key == key)
        .execution_options(book_scope="system")
        .scalar()
    )
    return int(held or 0)


def store_deal(session, deal: CanonicalDeal, *, entered_by: str, now: datetime,
               file_id: str | None = None, reason: str | None = None) -> str:
    """Store one deal as a new version unless it is a repeat; returns what happened.

    ``new``, ``amended``, ``cancelled`` or ``duplicate``. A key held only in a book the
    caller cannot see is refused (``held_elsewhere``) without saying where.
    """

    from eurogas_nexus.db.models import CapturedDealRecord

    key = deal.deal_key
    digest = deal.digest()
    current = (
        session.query(CapturedDealRecord)
        .filter(CapturedDealRecord.deal_key == key,
                CapturedDealRecord.superseded_at_utc.is_(None))
        .one_or_none()
    )
    if current is not None and current.content_digest == digest:
        return "duplicate"
    top = _hidden_version(session, key)
    if current is None and top:
        visible = (
            session.query(CapturedDealRecord.version)
            .filter(CapturedDealRecord.deal_key == key)
            .first()
        )
        if visible is None:
            return "held_elsewhere"
    if current is not None:
        current.superseded_at_utc = now
        outcome = "cancelled" if deal.status == "cancelled" else "amended"
    else:
        outcome = "cancelled" if deal.status == "cancelled" else "new"
    if reason is None:
        where = (f"{deal.source_file} line {deal.source_line}" if deal.origin == "file"
                 else "entered by hand")
        reason = {"new": None, "amended": f"corrected by {where}",
                  "cancelled": f"cancelled by {where}"}[outcome]
    session.add(CapturedDealRecord(
        version_id=uuid.uuid4().hex,
        deal_key=key,
        version=top + 1,
        status=deal.status,
        venue=deal.venue,
        venue_trade_id=deal.venue_trade_id,
        leg_id=deal.leg_id or "",
        trade_date=deal.trade_date,
        trade_time_utc=deal.trade_time_utc,
        trader=deal.trader,
        counterparty=deal.counterparty or "",
        cleared=deal.cleared,
        hub=deal.hub,
        product=deal.product,
        delivery_start=deal.delivery_start,
        delivery_end=deal.delivery_end,
        side=deal.side,
        volume=deal.volume,
        volume_unit=deal.volume_unit,
        total_mwh=deal.total_mwh,
        price=deal.price,
        price_currency=deal.price_currency,
        price_unit=deal.price_unit,
        physical=deal.physical,
        instrument=deal.instrument,
        fees=deal.fees,
        fee_currency=deal.fee_currency,
        book_id=deal.book_id,
        origin=deal.origin,
        file_id=file_id,
        file_name=deal.source_file,
        line=deal.source_line,
        entered_by_hand=list(deal.entered_by_hand) or None,
        entered_by=entered_by[:128],
        recorded_at_utc=now,
        superseded_at_utc=None,
        change_reason=(reason or None) and reason[:200],
        content_digest=digest,
    ))
    session.flush()
    return outcome


def import_file(
    session,
    caller,
    content: bytes,
    *,
    file_name: str,
    book_id: str | None,
    format_name: str | None = None,
    origin: str = "upload",
    now: datetime | None = None,
) -> ImportOutcome:
    """Read an export and store its deals; every unreadable row is recorded and returned."""

    from eurogas_nexus.db.models import DealImportFileRecord, DealImportProblemRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event
    from eurogas_nexus.domain.deals.formats import detect_format
    from eurogas_nexus.domain.deals.parse import decode, parse_deal_file, read_table

    now = now or datetime.now(UTC)
    if len(content) > MAX_FILE_BYTES:
        raise DealCaptureError("file_too_large", f"at most {MAX_FILE_BYTES} bytes", status=413)
    if not content.strip():
        raise DealCaptureError("file_empty", "the file is empty")
    book = _require_book(session, book_id)
    known, _errors = formats()
    if format_name:
        fmt = known.get(format_name)
        if fmt is None:
            raise DealCaptureError("format_unknown", f"no format named {format_name!r}",
                                   status=404, formats=sorted(known))
    else:
        probe = DealFormat(**{**MANUAL_FORMAT.__dict__, "name": "probe"})
        headers: list[str] = []
        shown: list[str] | None = None
        for delimiter in (",", ";", "\t", "|"):
            try:
                headers, _rows = read_table(
                    decode(content)[:200_000],
                    DealFormat(**{**probe.__dict__, "delimiter": delimiter}),
                )
            except Exception:  # noqa: BLE001 - a probe; the chosen format reads it properly
                headers = []
            shown = headers if shown is None else shown
            fmt = detect_format(headers, known)
            if fmt is not None:
                break
        if fmt is None:
            raise DealCaptureError(
                "format_not_recognised",
                "the file's headers match no format; choose the format, or add one "
                "(a copy of desk_csv.toml with the file's headers)",
                headers=(shown or [])[:40], formats=sorted(known),
            )
    actor = actor_of(caller)
    parsed = parse_deal_file(content, fmt, file_name=file_name[:256], default_trader="",
                             book_id=book)
    file_id = uuid.uuid4().hex
    outcome = ImportOutcome(file_id=file_id, format_name=fmt.name, format_title=fmt.title,
                            provenance=fmt.provenance, verified=fmt.verified)
    counts = {"rows": parsed.rows, "new": 0, "amended": 0, "cancelled": 0, "duplicate": 0,
              "unreadable": 0}
    problems: list[RowProblem] = list(parsed.problems)
    visible_books: dict[str, bool] = {}
    for deal in parsed.deals:
        if deal.book_id and deal.book_id != book:
            if deal.book_id not in visible_books:
                try:
                    _require_book(session, deal.book_id)
                    visible_books[deal.book_id] = True
                except DealCaptureError:
                    visible_books[deal.book_id] = False
            if not visible_books[deal.book_id]:
                problems.append(RowProblem(deal.source_line or 0, "book_not_in_scope",
                                           f"book {deal.book_id!r} is not one of yours",
                                           "book", deal.book_id))
                continue
        result = store_deal(session, deal, entered_by=actor, now=now, file_id=file_id)
        if result == "held_elsewhere":
            problems.append(RowProblem(deal.source_line or 0, "held_elsewhere",
                                       "this trade id is already captured in another book",
                                       "venue_trade_id", deal.venue_trade_id))
            continue
        counts[result] += 1
        outcome.deals.append({"deal_key": deal.deal_key, "line": deal.source_line,
                              "outcome": result})
    business_day = parsed.deals[0].trade_date if parsed.deals else now.date()
    for problem in problems:
        counts["unreadable"] += 1
        existing = (
            session.query(DealImportProblemRecord)
            .filter(
                DealImportProblemRecord.business_date == business_day,
                DealImportProblemRecord.book_id == book,
                DealImportProblemRecord.raw_row == problem.raw[:2000],
                DealImportProblemRecord.reason_code == problem.code,
                DealImportProblemRecord.resolved_at_utc.is_(None),
            )
            .first()
            if problem.raw else None
        )
        if existing is None:
            session.add(DealImportProblemRecord(
                problem_id=uuid.uuid4().hex, file_id=file_id, file_name=file_name[:256],
                line=problem.line, reason_code=problem.code[:48], message=problem.message[:500],
                field_name=(problem.field or None) and problem.field[:48],
                raw_value=(problem.value or None) and str(problem.value)[:200],
                raw_row=problem.raw[:2000], book_id=book, business_date=business_day,
                recorded_at_utc=now,
            ))
        outcome.problems.append(problem.as_dict())
    session.add(DealImportFileRecord(
        file_id=file_id, file_name=file_name[:256],
        sha256=hashlib.sha256(content).hexdigest(), format_name=fmt.name, book_id=book,
        origin=origin, received_by=actor, received_at_utc=now, rows_total=counts["rows"],
        rows_new=counts["new"], rows_amended=counts["amended"],
        rows_cancelled=counts["cancelled"], rows_duplicate=counts["duplicate"],
        rows_unreadable=counts["unreadable"],
    ))
    outcome.counts = counts
    record_audit_event(
        session, event_type="desk.deal_capture", principal=actor, action="deals.import",
        resource=f"deal-file:{file_id}", outcome="recorded", now_utc=now,
        detail=(f"{file_name[:120]} ({fmt.name}) into {book}: "
                + ", ".join(f"{k}={v}" for k, v in counts.items())),
    )
    return outcome


def enter_manual_deal(session, caller, values: dict[str, Any], *, now: datetime | None = None
                      ) -> dict[str, Any]:
    """A broker or bilateral deal entered by hand: checked like a file row, marked manual.

    ``values`` uses the canonical field names. Without a ``venue_trade_id`` one is made
    (``M-...``). With the ``deal_key`` of an earlier manual deal it corrects or cancels it.
    """

    from eurogas_nexus.db.models import CapturedDealRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event
    from eurogas_nexus.domain.deals.parse import RowError, canonical_deal, hand_entry_row

    now = now or datetime.now(UTC)
    actor = actor_of(caller)
    given = {k: str(v).strip() for k, v in values.items()
             if k in FIELDS and v is not None and str(v).strip() != ""}
    correcting = str(values.get("deal_key") or "").strip()
    if correcting:
        current = (
            session.query(CapturedDealRecord)
            .filter(CapturedDealRecord.deal_key == correcting,
                    CapturedDealRecord.superseded_at_utc.is_(None))
            .one_or_none()
        )
        if current is None:
            raise DealCaptureError("deal_not_found", "no such deal in your books", status=404)
        if current.origin != "manual":
            raise DealCaptureError(
                "deal_from_file",
                "this deal came from an exchange file; a correction comes with the next export",
                status=409,
            )
        base = _record_fields(current)
        base.update(given)
        given = base
    book = _require_book(session, given.get("book"))
    given["book"] = book
    if not given.get("venue_trade_id"):
        given["venue_trade_id"] = f"M-{uuid.uuid4().hex[:10].upper()}"
    given.setdefault("venue", "OTC")
    given.setdefault("trader", actor)
    given.setdefault("trade_date", now.date().isoformat())
    typed = tuple(sorted(k for k in values if k in FIELDS and values.get(k) not in (None, "")))
    row = hand_entry_row(MANUAL_FORMAT, given)
    try:
        deal = canonical_deal(row, file_name=None, default_trader=actor, book_id=book,
                              origin="manual", entered_by_hand=typed)
    except RowError as exc:
        raise DealCaptureError(exc.code, str(exc), field=exc.field, value=exc.value) from exc
    if correcting and deal.deal_key != correcting:
        raise DealCaptureError("deal_key_changed", "the venue and trade id of a deal stay as "
                               "they are; enter a new deal instead")
    outcome = store_deal(session, deal, entered_by=actor, now=now,
                         reason=None if not correcting else
                         ("cancelled by hand" if deal.status == "cancelled" else
                          "corrected by hand"))
    if outcome == "held_elsewhere":
        raise DealCaptureError("held_elsewhere", "this trade id is already captured in another "
                               "book", status=409)
    record_audit_event(
        session, event_type="desk.deal_capture", principal=actor, action="deals.manual",
        resource=f"deal:{deal.deal_key}", outcome=outcome, now_utc=now,
        detail=f"entered by hand: {', '.join(typed)}",
    )
    return {"deal_key": deal.deal_key, "outcome": outcome, "origin": "manual",
            "entered_by_hand": list(typed)}


def _record_fields(record) -> dict[str, str]:
    """A stored version as manual-entry values (to correct it field by field)."""

    return {
        "venue": record.venue, "venue_trade_id": record.venue_trade_id,
        "leg_id": record.leg_id or "", "trade_date": record.trade_date.isoformat(),
        "trade_time": record.trade_time_utc.isoformat() if record.trade_time_utc else "",
        "trader": record.trader, "counterparty": record.counterparty,
        "cleared": "yes" if record.cleared else "no", "hub": record.hub,
        "delivery_start": record.delivery_start.isoformat(),
        "delivery_end": record.delivery_end.isoformat(), "product": record.product,
        "side": record.side, "volume": dec(record.volume) or "",
        "volume_unit": record.volume_unit, "price": dec(record.price) or "",
        "price_unit": record.price_unit, "physical": "yes" if record.physical else "no",
        "instrument": record.instrument, "fees": dec(record.fees) or "",
        "fee_currency": record.fee_currency or "", "status": record.status,
        "book": record.book_id or "",
    }  # fmt: skip


def resolve_problem(session, caller, problem_id: str, *, note: str, now: datetime | None = None
                    ) -> dict[str, Any]:
    """Mark an unreadable row as dealt with (entered by hand, or not a deal), audited."""

    from eurogas_nexus.db.models import DealImportProblemRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    now = now or datetime.now(UTC)
    row = session.get(DealImportProblemRecord, problem_id)
    if row is None:
        raise DealCaptureError("problem_not_found", "no such row in your books", status=404)
    actor = actor_of(caller)
    row.resolved_at_utc, row.resolved_by = now, actor
    record_audit_event(
        session, event_type="desk.deal_capture", principal=actor, action="deals.problem.resolve",
        resource=f"deal-problem:{problem_id}", outcome="resolved", now_utc=now,
        detail=f"{row.file_name} line {row.line}: {note[:300]}",
    )
    return {"problem_id": problem_id, "resolved_by": actor, "resolved_at_utc": now.isoformat()}


# ----------------------------------------------------------------------------- reading


def current_deals(session, *, day: date | None = None, since: date | None = None,
                  until: date | None = None) -> list:
    from eurogas_nexus.db.models import CapturedDealRecord

    query = session.query(CapturedDealRecord).filter(
        CapturedDealRecord.superseded_at_utc.is_(None))
    if day is not None:
        query = query.filter(CapturedDealRecord.trade_date == day)
    if since is not None:
        query = query.filter(CapturedDealRecord.trade_date >= since)
    if until is not None:
        query = query.filter(CapturedDealRecord.trade_date <= until)
    return query.order_by(CapturedDealRecord.trade_date, CapturedDealRecord.trade_time_utc,
                          CapturedDealRecord.deal_key).all()


def price_per_mwh(record) -> Decimal:
    from eurogas_nexus.domain.deals.parse import price_factor

    return Decimal(record.price) * price_factor(record.price_unit,
                                                f"{record.price_currency}/MWh")


def source_of(record) -> dict[str, Any]:
    if record.origin == "manual":
        return {"kind": "manual", "entered_by": record.entered_by,
                "fields": list(record.entered_by_hand or [])}
    return {"kind": "file", "file_name": record.file_name, "line": record.line}


def source_text(record) -> str:
    if record.origin == "manual":
        return f"entered by hand by {record.entered_by}"
    return f"{record.file_name} line {record.line}"


def deal_row(record, versions: int = 1) -> dict[str, Any]:
    return {
        "deal_key": record.deal_key, "version": record.version, "versions": versions,
        "status": record.status, "venue": record.venue, "venue_trade_id": record.venue_trade_id,
        "leg_id": record.leg_id or None, "trade_date": record.trade_date.isoformat(),
        "trade_time_utc": record.trade_time_utc.isoformat() if record.trade_time_utc else None,
        "trader": record.trader, "counterparty": record.counterparty or None,
        "cleared": record.cleared, "hub": record.hub, "product": record.product,
        "delivery_start": record.delivery_start.isoformat(),
        "delivery_end": record.delivery_end.isoformat(), "side": record.side,
        "volume": dec(record.volume), "volume_unit": record.volume_unit,
        "total_mwh": dec(record.total_mwh), "price": dec(record.price),
        "price_unit": record.price_unit, "price_currency": record.price_currency,
        "physical": record.physical, "instrument": record.instrument,
        "fees": dec(record.fees), "fee_currency": record.fee_currency,
        "book_id": record.book_id, "origin": record.origin, "source": source_of(record),
        "recorded_at_utc": record.recorded_at_utc.isoformat(),
        "change_reason": record.change_reason,
    }  # fmt: skip


def sheet_values(record) -> dict[str, Any]:
    """A deal's values as the ETRM entry sheet layout names them (typed, not text)."""

    return {
        "deal_key": record.deal_key, "venue": record.venue,
        "venue_trade_id": record.venue_trade_id, "leg_id": record.leg_id,
        "trade_date": record.trade_date, "trade_time": record.trade_time_utc,
        "trader": record.trader, "counterparty": record.counterparty,
        "counterparty_or_venue": record.counterparty or record.venue,
        "cleared": record.cleared, "hub": record.hub, "product": record.product,
        "delivery_start": record.delivery_start, "delivery_end": record.delivery_end,
        "side": record.side, "volume": Decimal(record.volume),
        "volume_unit": record.volume_unit, "total_mwh": Decimal(record.total_mwh),
        "price": Decimal(record.price), "price_unit": record.price_unit,
        "price_currency": record.price_currency, "price_per_mwh": price_per_mwh(record),
        "physical": record.physical, "instrument": record.instrument,
        "fees": Decimal(record.fees) if record.fees is not None else None,
        "fee_currency": record.fee_currency, "book": record.book_id or "",
        "source": source_text(record), "version": record.version, "status": record.status,
    }  # fmt: skip


def _version_counts(session, keys: list[str]) -> dict[str, int]:
    from sqlalchemy import func

    from eurogas_nexus.db.models import CapturedDealRecord

    if not keys:
        return {}
    return dict(
        session.query(CapturedDealRecord.deal_key, func.count(CapturedDealRecord.version_id))
        .filter(CapturedDealRecord.deal_key.in_(keys))
        .group_by(CapturedDealRecord.deal_key)
        .all()
    )


def totals(records) -> list[dict[str, Any]]:
    """Per hub and delivery period: buys, sells and net in MWh, volume-weighted prices."""

    groups: dict[tuple[str, str, date], dict[str, Any]] = {}
    for record in records:
        if record.status != "live":
            continue
        key = (record.hub, record.product, record.delivery_start)
        entry = groups.setdefault(key, {
            "hub": record.hub, "product": record.product,
            "delivery_start": record.delivery_start.isoformat(),
            "delivery_end": record.delivery_end.isoformat(), "deals": 0,
            "buy_mwh": Decimal(0), "sell_mwh": Decimal(0), "_buy_value": Decimal(0),
            "_sell_value": Decimal(0), "price_units": set(),
        })
        mwh = Decimal(record.total_mwh)
        entry["deals"] += 1
        entry["price_units"].add(record.price_unit)
        if record.side == "buy":
            entry["buy_mwh"] += mwh
            entry["_buy_value"] += mwh * Decimal(record.price)
        else:
            entry["sell_mwh"] += mwh
            entry["_sell_value"] += mwh * Decimal(record.price)
    out = []
    for _key, entry in sorted(groups.items(), key=lambda item: (item[0][0], item[0][2],
                                                                 item[0][1])):
        units = entry.pop("price_units")
        unit = next(iter(units)) if len(units) == 1 else None
        buy_value, sell_value = entry.pop("_buy_value"), entry.pop("_sell_value")
        def avg(value: Decimal, mwh: Decimal, unit: str | None = unit) -> str | None:
            return dec((value / mwh).quantize(Decimal("0.0001"))) if unit and mwh else None

        out.append({
            **entry,
            "buy_mwh": dec(entry["buy_mwh"]), "sell_mwh": dec(entry["sell_mwh"]),
            "net_mwh": dec(entry["buy_mwh"] - entry["sell_mwh"]),
            "avg_buy_price": avg(buy_value, entry["buy_mwh"]),
            "avg_sell_price": avg(sell_value, entry["sell_mwh"]),
            "price_unit": unit,
        })
    return out


def open_problems(session, day: date) -> list:
    from eurogas_nexus.db.models import DealImportProblemRecord

    return (
        session.query(DealImportProblemRecord)
        .filter(DealImportProblemRecord.business_date == day,
                DealImportProblemRecord.resolved_at_utc.is_(None))
        .order_by(DealImportProblemRecord.recorded_at_utc, DealImportProblemRecord.line)
        .all()
    )


def problem_row(row) -> dict[str, Any]:
    return {
        "problem_id": row.problem_id, "file_name": row.file_name, "line": row.line,
        "code": row.reason_code, "message": row.message, "field": row.field_name,
        "value": row.raw_value, "raw": row.raw_row, "book_id": row.book_id,
        "recorded_at_utc": row.recorded_at_utc.isoformat(),
    }  # fmt: skip


def day_closes(session, day: date) -> list:
    from eurogas_nexus.db.models import DealDayCloseRecord

    return (
        session.query(DealDayCloseRecord)
        .filter(DealDayCloseRecord.business_date == day,
                DealDayCloseRecord.superseded_at_utc.is_(None))
        .order_by(DealDayCloseRecord.closed_at_utc)
        .all()
    )


def day_status(session, day: date, records=None) -> dict[str, Any]:
    """Whether the day is closed for every book that has deals (and by whom)."""

    records = current_deals(session, day=day) if records is None else records
    closes = day_closes(session, day)
    closed_books = {row.book_id for row in closes}
    books = {record.book_id for record in records}
    open_books = sorted(book or "" for book in books - closed_books)
    return {
        "business_date": day.isoformat(),
        "closed": bool(closes) and not open_books,
        "open_books": open_books,
        "closes": [
            {"book_id": row.book_id, "closed_by": row.closed_by,
             "closed_at_utc": row.closed_at_utc.isoformat(),
             "differences": len(row.differences or []), "etrm_file_name": row.etrm_file_name,
             "note": row.note}
            for row in closes
        ],
        "label": None if (closes and not open_books) else ESTIMATE_LABEL,
    }


def blotter(session, *, day: date, trader: str | None = None, hub: str | None = None,
            venue: str | None = None, book_id: str | None = None) -> dict[str, Any]:
    """The day's deals with where each came from, the unread rows, and totals."""

    records = current_deals(session, day=day)
    choices = {
        "traders": sorted({r.trader for r in records}),
        "hubs": sorted({r.hub for r in records}),
        "venues": sorted({r.venue for r in records}),
        "books": sorted({r.book_id or "" for r in records}),
    }
    shown = [
        r for r in records
        if (not trader or r.trader.casefold() == trader.casefold())
        and (not hub or r.hub == hub.upper())
        and (not venue or r.venue == venue.upper())
        and (not book_id or r.book_id == book_id)
    ]
    versions = _version_counts(session, [r.deal_key for r in shown])
    problems = [row for row in open_problems(session, day)
                if not book_id or row.book_id == book_id]
    return {
        "business_date": day.isoformat(),
        "deals": [deal_row(r, versions.get(r.deal_key, 1)) for r in shown],
        "unreadable": [problem_row(row) for row in problems],
        "totals": totals(shown),
        "counts": {
            "deals": len(shown),
            "live": sum(1 for r in shown if r.status == "live"),
            "cancelled": sum(1 for r in shown if r.status == "cancelled"),
            "manual": sum(1 for r in shown if r.origin == "manual"),
            "unreadable": len(problems),
        },
        "choices": choices,
        "status": day_status(session, day, records),
    }


def deal_history(session, deal_key: str) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models import CapturedDealRecord

    rows = (
        session.query(CapturedDealRecord)
        .filter(CapturedDealRecord.deal_key == deal_key)
        .order_by(CapturedDealRecord.version)
        .all()
    )
    if not rows:
        raise DealCaptureError("deal_not_found", "no such deal in your books", status=404)
    return [
        {**deal_row(row, len(rows)),
         "superseded_at_utc": row.superseded_at_utc.isoformat() if row.superseded_at_utc
         else None, "entered_by": row.entered_by}
        for row in rows
    ]


def etrm_sheet(session, *, day: date, file_format: str) -> tuple[bytes, str, str]:
    """The day's deals in the ETRM entry layout: (content, media type, file name)."""

    from eurogas_nexus.domain.deals.sheet import sheet_csv, sheet_xlsx

    layout = sheet_layout()
    records = current_deals(session, day=day)
    values = [sheet_values(record) for record in records]
    name = f"etrm-entry-{day.isoformat()}"
    if file_format == "xlsx":
        about = [("Business date", day.isoformat()), ("Layout", layout.title),
                 ("Layout file", layout.source_path), ("Deals", str(len(values))),
                 ("Note", "Captured deals for keying into the ETRM; the ETRM is the official "
                          "record.")]
        return (sheet_xlsx(layout, values, about),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                f"{name}.xlsx")
    return sheet_csv(layout, values), "text/csv; charset=utf-8", f"{name}.csv"


# ----------------------------------------------------------------------------- the check


def read_etrm_export(text: str, layout) -> tuple[list, list[dict[str, Any]], int]:
    """The ETRM export's trades (one row at a time through ``import_etrm_trades``'s parser).

    Returns the trades, the rows that could not be read (line and reason), and the number
    of cancelled trades the export carries.
    """

    import csv
    import io

    from eurogas_nexus.domain.deals.eod import EtrmSide
    from eurogas_nexus.ingestion.etrm_trades import EtrmImportError, parse_etrm_trades

    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration:
        raise DealCaptureError("etrm_file_empty", "the ETRM export has no header row") from None
    names = [(name or "").strip().lower() for name in header]
    reference_index = (names.index(layout.etrm_reference_column.lower())
                       if layout.etrm_reference_column
                       and layout.etrm_reference_column.lower() in names else None)
    rows, unreadable, cancelled = [], [], 0
    for raw in reader:
        line = reader.line_num
        if not any((cell or "").strip() for cell in raw):
            continue
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="\n").writerows([header, raw])
        try:
            parsed = parse_etrm_trades(buffer.getvalue(), system=layout.etrm_system,
                                       source_reference=f"eod-check:{line}")
        except EtrmImportError as exc:
            unreadable.append({"line": line, "message": str(exc),
                               "code": getattr(exc, "reason_code", "etrm_row_invalid")})
            continue
        if parsed.cancelled_ids:
            cancelled += 1
            continue
        values = parsed.upserts[0]
        cells = {name: (raw[i] if i < len(raw) else "").strip() for i, name in enumerate(names)}
        rows.append(EtrmSide(
            trade_id=values["external_order_id"],
            reference=(raw[reference_index].strip() if reference_index is not None
                       and reference_index < len(raw) else ""),
            hub=values["hub"],
            side=values["side"].lower(),
            first_day=date.fromisoformat(cells["delivery_start"][:10]),
            last_day=date.fromisoformat(cells["delivery_end"][:10]),
            total_mwh=Decimal(repr(values["quantity_mwh"])),
            price_per_mwh=Decimal(repr(values["price"])),
            counterparty=cells.get("counterparty", ""),
            book_id=values.get("book_id"),
            line=line,
        ))
    return rows, unreadable, cancelled


def captured_side(record):
    from eurogas_nexus.domain.deals.eod import CapturedSide

    return CapturedSide(
        deal_key=record.deal_key, venue=record.venue, venue_trade_id=record.venue_trade_id,
        status=record.status, trader=record.trader, counterparty=record.counterparty or "",
        cleared=record.cleared, hub=record.hub, product=record.product, side=record.side,
        first_day=record.delivery_start, last_day=record.delivery_end,
        total_mwh=Decimal(record.total_mwh), price_per_mwh=price_per_mwh(record),
        currency=record.price_currency, book_id=record.book_id, source=source_text(record),
    )


def eod_check(session, *, day: date, etrm_text: str, etrm_file_name: str) -> dict[str, Any]:
    """Captured deals of the day against the ETRM export; stores nothing."""

    from eurogas_nexus.domain.deals.eod import check
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    layout = sheet_layout()
    rows, unreadable, cancelled = read_etrm_export(etrm_text, layout)
    visible = visible_book_ids(session)
    outside = 0
    if visible is not None:
        kept = [row for row in rows if row.book_id in visible]
        outside, rows = len(rows) - len(kept), kept
    records = current_deals(session, day=day)
    result = check([captured_side(record) for record in records], rows)
    result.unreadable = unreadable
    payload = result.as_dict()
    # An ETRM row that could not be read is a difference too: it cannot be matched.
    for item in unreadable:
        payload["differences"].append({
            "id": hashlib.sha256(f"etrm_unreadable|{item['line']}|{item['message']}".encode()
                                 ).hexdigest()[:16],
            "kind": "etrm_unreadable", "deal_key": None, "etrm_trade_id": None, "hub": None,
            "product": None, "matched_by": None, "captured": None, "etrm": None,
            "detail": item,
        })
    payload["counts"]["etrm_unreadable"] = len(unreadable)
    payload.update({
        "business_date": day.isoformat(),
        "etrm_file_name": etrm_file_name,
        "etrm_sha256": hashlib.sha256(etrm_text.encode("utf-8")).hexdigest(),
        "captured_deals": len(records),
        "etrm_trades": len(rows),
        "etrm_cancelled": cancelled,
        "etrm_rows_outside_your_books": outside,
        "reference_column": layout.etrm_reference_column or None,
        "status": day_status(session, day, records),
    })
    return payload


def close_day(session, caller, *, day: date, etrm_text: str, etrm_file_name: str,
              acknowledgements: dict[str, str], note: str | None = None,
              now: datetime | None = None, valuation=None) -> dict[str, Any]:
    """Close the day for the caller's books once every difference is acknowledged.

    The check is run again here (never taken from the client). Each difference needs an
    acknowledgement (a short note); one missing refuses the close and lists it. The close is
    recorded per book with the person, the time, the ETRM file's digest, every difference
    with its note, and the deal values the P&L carries to the next day. Audited.
    """

    from eurogas_nexus.db.models import DealDayCloseRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    now = now or datetime.now(UTC)
    actor = actor_of(caller)
    result = eod_check(session, day=day, etrm_text=etrm_text, etrm_file_name=etrm_file_name)
    missing = [item["id"] for item in result["differences"]
               if not str(acknowledgements.get(item["id"]) or "").strip()]
    if missing:
        raise DealCaptureError(
            "differences_not_acknowledged",
            f"{len(missing)} difference(s) are not acknowledged; each needs a note",
            status=409, missing=missing,
        )
    records = current_deals(session, day=day)
    books = sorted({record.book_id or "" for record in records}
                   | {(item.get("etrm") or {}).get("book_id") or "" for item in
                      result["differences"] if item.get("etrm")})
    if not books:
        books = [""]
    pnl = valuation if valuation is not None else day_pnl(session, caller, day=day, now=now)
    pairs = dict(result.get("pairs") or {})
    closes = []
    for book in books:
        for previous in session.query(DealDayCloseRecord).filter(
            DealDayCloseRecord.business_date == day,
            DealDayCloseRecord.book_id == (book or None),
            DealDayCloseRecord.superseded_at_utc.is_(None),
        ):
            previous.superseded_at_utc = now
        in_book = {record.deal_key for record in records if (record.book_id or "") == book}
        differences = [
            {**item, "acknowledgement": str(acknowledgements[item["id"]])[:500],
             "acknowledged_by": actor}
            for item in result["differences"]
            if (item.get("deal_key") in in_book)
            or ((item.get("etrm") or {}).get("book_id") or "") == book
            or (item["kind"] == "etrm_unreadable" and book == books[0])
        ]
        figures = {
            "values": {key: value for key, value in pnl["values"].items() if key in in_book},
            "day_pnl": [row for row in pnl["by_trader_hub"] if row.get("book_id", "") == book],
            "pairs": {key: value for key, value in pairs.items() if key in in_book},
            "etrm_system": sheet_layout().etrm_system,
            "marks_warnings": pnl["warnings"],
            "simulated_marks": pnl["simulated_marks"],
        }
        row = DealDayCloseRecord(
            close_id=uuid.uuid4().hex, business_date=day, book_id=book or None,
            closed_by=actor, closed_at_utc=now, etrm_file_name=etrm_file_name[:256],
            etrm_sha256=result["etrm_sha256"], differences=differences, figures=figures,
            note=(note or None) and note[:500],
        )
        session.add(row)
        closes.append({"book_id": book or None, "close_id": row.close_id,
                       "differences": len(differences)})
    record_audit_event(
        session, event_type="desk.deal_capture", principal=actor, action="deals.day.close",
        resource=f"deal-day:{day.isoformat()}", outcome="closed", now_utc=now,
        detail=(f"ETRM file {etrm_file_name[:100]} sha256 {result['etrm_sha256'][:16]}; "
                f"{len(result['differences'])} difference(s) acknowledged; books "
                f"{', '.join(b or '-' for b in books)}"),
    )
    session.flush()
    return {"business_date": day.isoformat(), "closed_by": actor,
            "closed_at_utc": now.isoformat(), "closes": closes,
            "differences": len(result["differences"])}


# ----------------------------------------------------------------------------- P&L


def _months(first: date, last: date) -> list[tuple[str, date, date]]:
    out = []
    day = first
    while day <= last:
        end = date(day.year, day.month, _calendar.monthrange(day.year, day.month)[1])
        stop = min(end, last)
        out.append((f"{day.year:04d}-{day.month:02d}", day, stop))
        day = stop + timedelta(days=1)
    return out


def monthly_mwh(record) -> list[tuple[str, Decimal]]:
    """The deal's signed MWh per delivery month (by gas days, by hours for a MW deal)."""

    from eurogas_nexus.domain.deals.parse import period_hours
    from eurogas_nexus.domain.ontology.boundary import check_boundary

    total = Decimal(record.total_mwh) * (1 if record.side == "buy" else -1)
    parts = _months(record.delivery_start, record.delivery_end)
    if len(parts) == 1:
        return [(parts[0][0], total)]
    if record.volume_unit in {"MW", "kWh/h"}:
        market = check_boundary(market=record.hub, gas_hub_required=True).market
        calendar = market.calendar if market else "EU-CAM-UTC-2025"
        whole = period_hours(record.delivery_start, record.delivery_end, calendar)
        weights = [period_hours(a, b, calendar) for _m, a, b in parts]
    else:
        whole = Decimal((record.delivery_end - record.delivery_start).days + 1)
        weights = [Decimal((b - a).days + 1) for _m, a, b in parts]
    return [(month, total * weight / whole) for (month, _a, _b), weight in zip(parts, weights,
                                                                             strict=True)]


def marks_for(caller, today: date, last_day: date, *, now: datetime | None = None):
    """The ladder's marks (the one price per hub and month every screen reads) and its notes.

    This is the existing marking logic (``position_inputs.ladder_inputs``); the deal values
    below only multiply its marks by each deal's volume, in exact decimals.
    """

    from eurogas_nexus.application.position_inputs import (
        is_simulated_marks_warning,
        ladder_inputs,
    )

    start = today.replace(day=1)
    end = max(last_day, today)
    end = min(end, date(today.year + 3, 12, 31))
    inputs = ladder_inputs(caller, today, start, end, now=now)
    simulated = any(is_simulated_marks_warning(text) for text in inputs.warnings)
    return inputs, simulated


def deal_value(record, marks: dict) -> tuple[Decimal | None, str | None]:
    """(mark − price) × MWh over the deal's delivery months at the ladder's marks."""

    if record.status != "live":
        return Decimal(0), None
    from eurogas_nexus.domain.ontology.markets import quote_currency

    if quote_currency(record.hub) != record.price_currency:
        return None, "currency"
    price = price_per_mwh(record)
    total = Decimal(0)
    for month, mwh in monthly_mwh(record):
        mark = marks.get((record.hub, month))
        if mark is None:
            return None, "no_mark"
        total += (Decimal(repr(float(mark))) - price) * mwh
    return total.quantize(Decimal("0.01")), None


def previous_values(session, day: date) -> dict[str, Decimal]:
    """Each deal's value at the newest close before ``day`` (per book, latest wins)."""

    from eurogas_nexus.db.models import DealDayCloseRecord

    rows = (
        session.query(DealDayCloseRecord)
        .filter(DealDayCloseRecord.business_date < day,
                DealDayCloseRecord.superseded_at_utc.is_(None))
        .order_by(DealDayCloseRecord.business_date, DealDayCloseRecord.closed_at_utc)
        .all()
    )
    out: dict[str, Decimal] = {}
    for row in rows:
        for key, value in ((row.figures or {}).get("values") or {}).items():
            out[key] = Decimal(str(value))
    return out


def closed_pnl(session, since: date, until: date) -> dict[tuple[str, str, str, str], Decimal]:
    """Day P&L stored at each close in ``[since, until)``, by (book, trader, hub, currency)."""

    from eurogas_nexus.db.models import DealDayCloseRecord

    rows = (
        session.query(DealDayCloseRecord)
        .filter(DealDayCloseRecord.business_date >= since,
                DealDayCloseRecord.business_date < until,
                DealDayCloseRecord.superseded_at_utc.is_(None))
        .all()
    )
    out: dict[tuple[str, str, str, str], Decimal] = defaultdict(Decimal)
    for row in rows:
        for item in (row.figures or {}).get("day_pnl") or []:
            key = (item.get("book_id", ""), item["trader"], item["hub"], item["currency"])
            out[key] += Decimal(str(item["day"]))
    return out


def day_pnl(session, caller, *, day: date, now: datetime | None = None) -> dict[str, Any]:
    """Day, month-to-date and year-to-date P&L of captured deals, by book, trader and hub.

    Day P&L of a deal is its value at today's marks less its value at the previous close
    (zero for a deal new since then; a cancelled deal is worth zero, so its earlier value
    reverses). A deal with no mark is listed as not valued, never counted as zero; a deal
    delivered and no longer marked keeps its last closed value (no change). Month and year to
    date add the day P&L stored at each close of the period. Amounts are in the hub's
    currency; currencies are never added together. Fees are shown apart.
    """

    records = [r for r in current_deals(session, until=day)]
    live_open = [r for r in records if r.status == "live" and r.delivery_end >= day]
    last = max([r.delivery_end for r in live_open] or [day])
    inputs, simulated = marks_for(caller, day, last, now=now)
    marks = inputs.marks
    previous = previous_values(session, day)
    values: dict[str, str] = {}
    not_valued: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str, str], dict[str, Decimal]] = {}
    for record in records:
        value, reason = deal_value(record, marks)
        prior = previous.get(record.deal_key)
        if value is None:
            if prior is not None and record.delivery_end < day.replace(day=1):
                value = prior  # delivered: its last closed value stands
            else:
                not_valued.append({"deal_key": record.deal_key, "hub": record.hub,
                                   "product": record.product, "reason": reason})
                continue
        values[record.deal_key] = dec(value) or "0"
        change = value - (prior or Decimal(0))
        key = (record.book_id or "", record.trader, record.hub, record.price_currency)
        entry = grouped.setdefault(key, {"day": Decimal(0), "fees": Decimal(0)})
        entry["day"] += change
        if record.trade_date == day and record.fees is not None and record.status == "live":
            entry["fees"] += Decimal(record.fees)
    month_start, year_start = day.replace(day=1), day.replace(month=1, day=1)
    mtd = closed_pnl(session, month_start, day)
    ytd = closed_pnl(session, year_start, day)
    keys = set(grouped) | set(mtd) | set(ytd)
    rows = []
    for key in sorted(keys):
        book, trader, hub, currency = key
        today_value = grouped.get(key, {}).get("day", Decimal(0))
        rows.append({
            "book_id": book, "trader": trader, "hub": hub, "currency": currency,
            "day": dec(today_value.quantize(Decimal("0.01"))) or "0",
            "mtd": dec((mtd.get(key, Decimal(0)) + today_value).quantize(Decimal("0.01"))),
            "ytd": dec((ytd.get(key, Decimal(0)) + today_value).quantize(Decimal("0.01"))),
            "fees": dec(grouped.get(key, {}).get("fees", Decimal(0))) or "0",
        })
    totals_by_currency: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        entry = totals_by_currency.setdefault(row["currency"], {
            "day": Decimal(0), "mtd": Decimal(0), "ytd": Decimal(0)})
        for name in ("day", "mtd", "ytd"):
            entry[name] += Decimal(row[name] or "0")
    return {
        "business_date": day.isoformat(),
        "by_trader_hub": rows,
        "totals": [{"currency": c, **{k: dec(v) for k, v in t.items()}}
                   for c, t in sorted(totals_by_currency.items())],
        "values": values,
        "not_valued": not_valued,
        "warnings": list(dict.fromkeys(inputs.warnings))[:20],
        "simulated_marks": simulated,
        "marks": inputs.marks,
        "resolved": inputs.resolved,
        "inputs": inputs,
        "method": ("Captured deals at the position ladder's marks (one price per hub and "
                   "month): (mark − price) × MWh per delivery month; day P&L is the change "
                   "since the previous close. Fees apart."),
    }


# ----------------------------------------------------------------------------- overlay


def overlay_orders(session, day: date) -> tuple[list, dict[str, str], dict[str, str], int]:
    """Captured live deals not yet in the ETRM book, shaped as screen orders for the ladder.

    A deal leaves the overlay when a close paired it with an ETRM trade that is now loaded
    in the book (``etrm-<system>-<trade id>``). Returns the orders, their books, their
    counterparties and how many deals were left out because their ETRM twin is loaded.
    """

    from eurogas_nexus.db.models import DealDayCloseRecord, ScreenOrderObservationRecord
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
    from eurogas_nexus.domain.market_positioning import ScreenOrderObservation
    from eurogas_nexus.domain.ontology.boundary import check_boundary

    pairs: dict[str, str] = {}
    system = "ETRM"
    for row in session.query(DealDayCloseRecord).filter(
            DealDayCloseRecord.superseded_at_utc.is_(None)).all():
        figures = row.figures or {}
        system = figures.get("etrm_system") or system
        for key, trade in (figures.get("pairs") or {}).items():
            system_key = "".join(ch for ch in str(figures.get("etrm_system") or "ETRM").upper()
                                 if ch.isalnum())[:16] or "ETRM"
            pairs[key] = f"etrm-{system_key.lower()}-{trade}"[:64]
    loaded = {
        oid for (oid,) in session.query(ScreenOrderObservationRecord.order_observation_id)
        .filter(ScreenOrderObservationRecord.order_observation_id.in_(list(pairs.values())))
        .all()
    } if pairs else set()
    orders, books, counterparties, left_out = [], {}, {}, 0
    for record in current_deals(session, until=day):
        if record.status != "live" or record.delivery_end < day:
            continue
        if pairs.get(record.deal_key) in loaded:
            left_out += 1
            continue
        market = check_boundary(market=record.hub, gas_hub_required=True).market
        calendar = market.calendar if market else "EU-CAM-UTC-2025"
        start = gas_day_start_for_date(record.delivery_start, calendar)
        end = gas_day_start_for_date(record.delivery_end + timedelta(days=1), calendar)
        oid = f"capture-{record.deal_key}"[:128]
        orders.append(ScreenOrderObservation(
            order_observation_id=oid, provider_id=OVERLAY_PROVIDER, venue=record.venue,
            account_label=record.trader, external_order_id=record.venue_trade_id,
            side="BUY" if record.side == "buy" else "SELL", order_type=record.instrument,
            hub=record.hub, product=record.product, contract_code=record.deal_key[:128],
            delivery_start_utc=start.isoformat(), delivery_end_utc=end.isoformat(),
            price=float(price_per_mwh(record)), currency=record.price_currency,
            unit=f"{record.price_currency}/MWh", quantity_mwh=float(record.total_mwh),
            filled_quantity_mwh=float(record.total_mwh), remaining_quantity_mwh=0.0,
            status="FILLED", observed_at_utc=(record.trade_time_utc or record.recorded_at_utc
                                              ).isoformat(),
            source_system=OVERLAY_PROVIDER, source_reference=source_text(record)[:128],
        ))
        books[oid] = record.book_id or ""
        if record.counterparty and not record.cleared:
            counterparties[oid] = record.counterparty
    return orders, books, counterparties, left_out


# ----------------------------------------------------------------------------- watched folder

DROP_DIR_ENV = "EUROGAS_NEXUS_DEAL_DROP_DIR"
DROP_SUFFIXES = (".csv", ".txt")


def import_drop_folder(session_factory, caller, folder, *, now: datetime | None = None
                       ) -> list[dict[str, Any]]:
    """Import every export dropped in ``<folder>/<book id>/``; move each to ``imported/`` or
    ``refused/`` with a ``.result.txt`` note beside it, so a file is read once.

    Each file is its own transaction: one refused file never stops the others. The format is
    recognised by the file's headers; a subfolder ``<book id>/<format name>/`` names it.
    """

    import json
    from pathlib import Path

    root = Path(folder)
    outcomes: list[dict[str, Any]] = []
    if not root.is_dir():
        return outcomes
    for book_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        candidates = [(path, None) for path in sorted(book_dir.iterdir())
                      if path.is_file() and path.suffix.lower() in DROP_SUFFIXES]
        for fmt_dir in sorted(p for p in book_dir.iterdir() if p.is_dir()
                              and p.name not in {"imported", "refused"}):
            candidates += [(path, fmt_dir.name) for path in sorted(fmt_dir.iterdir())
                           if path.is_file() and path.suffix.lower() in DROP_SUFFIXES]
        for path, format_name in candidates:
            when = now or datetime.now(UTC)
            outcome: dict[str, Any] = {"file": path.name, "book_id": book_dir.name}
            try:
                content = path.read_bytes()
                with session_factory() as session:
                    result = import_file(session, caller, content, file_name=path.name,
                                         book_id=book_dir.name, format_name=format_name,
                                         origin="folder", now=when)
                    session.commit()
                outcome.update(status="imported", **result.counts)
                target = book_dir / "imported"
                note = json.dumps(result.as_dict(), indent=2, default=str)
            except DealCaptureError as exc:
                outcome.update(status="refused", code=exc.code, message=exc.message)
                target = book_dir / "refused"
                note = json.dumps(exc.detail(), indent=2, default=str)
            except OSError as exc:
                outcome.update(status="unreadable", message=str(exc))
                outcomes.append(outcome)
                continue
            target.mkdir(exist_ok=True)
            stamp = when.strftime("%Y%m%dT%H%M%S")
            moved = target / f"{stamp}-{path.name}"
            path.replace(moved)
            moved.with_name(moved.name + ".result.txt").write_text(note, encoding="utf-8")
            outcomes.append(outcome)
    return outcomes
