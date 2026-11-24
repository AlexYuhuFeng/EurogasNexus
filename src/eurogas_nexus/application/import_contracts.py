"""Versioned file contracts for what the ETRM and the ERP send (DATA-1, ETRM integration).

A contract is a named, versioned file shape (``etrm.deals.v1``): its columns, which are
required, what each holds, the key that makes a row the same row on re-import, and where the
rows land. The six contracts:

- ``etrm.deals.v1``: gas trades by trade id, cancellations too; into the books.
- ``etrm.physical_positions.v1``: the physical schedule per gas day and hub (storage,
  offtake, imports, exports); into ``gas_day_schedule_lines``.
- ``etrm.nominations.v1``: nomination statuses the scheduler or the TSO confirmed; into
  ``gas_day_nomination_events`` (append-only).
- ``etrm.cargo_schedule.v1``: the firm's LNG cargoes and their ETAs; into ``lng_cargoes``.
- ``erp.counterparties.v1`` and ``erp.invoices.v1``: the ERP's counterparties and invoice
  references; into ``erp_references``.

Every row is checked on its own, and a refused row is reported with its line, a reason code
and a message (``RowRefusal``), so a file with one bad row tells the sender exactly what to fix.
By default one refused row refuses the file and nothing is stored (``reject_file``); with
``skip_rows`` the good rows are stored and the bad ones reported. A file with a missing
required column, or a column a contract forbids (a bank account, a tax identifier), is refused
as a whole.

Re-import is idempotent: rows are keyed by the source's own id (trade id, line id, cargo id,
ERP number) or, for an append-only nomination status, by a digest of its content; a row equal
to what is stored is counted ``unchanged`` and not written again, so sending the same file
twice changes nothing and publishes nothing.

Nothing is executed: importing a deal records a trade the ETRM already booked; importing a
nomination status records what the scheduler or the TSO confirmed; neither books, nominates,
pays or sends anything (AGENTS.md rule 8). The parsers of the existing importers are reused
(``ingestion/etrm_trades``, ``ingestion/lng_positions``), so a row means the same here as in
the scripts that came before.

Writing is the operator's: ``scripts/ops/import_contract_file.py`` (dry run unless
``--commit``). ``POST /api/imports/{contract}/validate`` checks a file and stores nothing.
The documented contract is ``docs/integration/ETRM_ERP_IMPORT_CONTRACTS.md``.

DATA-1：ETRM 与 ERP 导入文件的版本化契约；逐行校验并给出原因，重复导入幂等，不执行任何交易或提名。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

REJECT_FILE = "reject_file"
SKIP_ROWS = "skip_rows"
ON_ERROR = (REJECT_FILE, SKIP_ROWS)
MAX_ROWS = 200_000
#: Columns no contract takes: bank details and tax or government identifiers stay in the ERP.
FORBIDDEN_COLUMNS = frozenset(
    {
        "iban",
        "bic",
        "swift",
        "bank_account",
        "account_number",
        "routing_number",
        "sort_code",
        "vat_id",
        "vat_number",
        "tax_id",
        "tax_number",
        "ein",
        "national_id",
        "passport",
    }
)
_FUTURE_SKEW = timedelta(minutes=5)


class ImportContractError(ValueError):
    """A request that names no contract, or a file refused as a whole."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RowError(ValueError):
    """One row refused, with its reason code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Column:
    name: str
    required: bool
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "required": self.required, "description": self.description}


@dataclass(frozen=True)
class ImportContract:
    """One versioned file shape."""

    name: str
    version: int
    title: str
    lands_in: str
    key: str
    columns: tuple[Column, ...]
    notes: str = ""

    @property
    def contract_id(self) -> str:
        return f"{self.name}.v{self.version}"

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns if column.required)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "name": self.name,
            "version": self.version,
            "title": self.title,
            "lands_in": self.lands_in,
            "key": self.key,
            "columns": [column.as_dict() for column in self.columns],
            "notes": self.notes,
            "format": "CSV, UTF-8 (a byte-order mark is accepted), header row, comma-separated",
        }


@dataclass(frozen=True)
class RowRefusal:
    line: int
    reason_code: str
    message: str
    key: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "reason_code": self.reason_code,
            "message": self.message,
            "key": self.key,
        }


@dataclass
class ImportReport:
    """What a file holds and what storing it does (or would do, on a dry run)."""

    contract_id: str
    system: str
    file_sha256: str
    on_error: str
    rows: int = 0
    accepted: int = 0
    refused: list[RowRefusal] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    committed: bool = False
    #: Whether the file is refused as a whole (nothing stored).
    file_refused: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "system": self.system,
            "file_sha256": self.file_sha256,
            "on_error": self.on_error,
            "rows": self.rows,
            "accepted": self.accepted,
            "refused": [item.as_dict() for item in self.refused],
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "removed": self.removed,
            "file_refused": self.file_refused,
            "committed": self.committed,
            "notes": list(self.notes),
            "research_only": True,
            "executes_nothing": True,
        }


# --------------------------------------------------------------------------- contracts


def _c(name: str, required: bool, description: str) -> Column:
    return Column(name, required, description)


_DEALS = ImportContract(
    name="etrm.deals",
    version=1,
    title="Gas trades from the ETRM",
    lands_in="the books (trades the position, P&L and risk reads use)",
    key="(system, trade_id)",
    columns=(
        _c("trade_id", True, "The ETRM's deal number; with the system, the row's key"),
        _c("book_id", True, "Book (portfolio, strategy) the deal is booked in; must exist here"),
        _c("hub", True, "Delivery hub (TTF, THE, NBP, PEG, PSV, ZTP...)"),
        _c("side", True, "BUY or SELL (B or S)"),
        _c("delivery_start", True, "First gas day, YYYY-MM-DD"),
        _c("delivery_end", True, "Last gas day, YYYY-MM-DD (inclusive)"),
        _c("quantity", True, "Positive quantity; the sign is the side"),
        _c("quantity_unit", True, "MWh (total), MWh/d, MW or th/d"),
        _c("price", True, "Deal price"),
        _c("price_unit", True, "Price quote, e.g. EUR/MWh or GBp/th, in the hub's currency"),
        _c("trade_time", False, "When the deal was struck, ISO 8601 (default: delivery start)"),
        _c("status", False, "CANCELLED, CANCELED, DELETED or VOID removes the deal"),
        _c("counterparty", False, "Counterparty short name as the ETRM carries it"),
    ),
    notes="A re-sent deal replaces its earlier version; a cancelled deal is removed.",
)

_POSITIONS = ImportContract(
    name="etrm.physical_positions",
    version=1,
    title="Physical schedule per gas day from the ETRM or scheduling system",
    lands_in="gas_day_schedule_lines (Today > My gas day, the hub balance)",
    key="line_id",
    columns=(
        _c("line_id", True, "The scheduling system's line id, unique across systems"),
        _c("gas_day", True, "Gas day, YYYY-MM-DD"),
        _c("hub", True, "Hub the line balances at"),
        _c("direction", True, "in (gas the firm takes at the hub) or out (gas it delivers)"),
        _c("kind", True, "in: supply, upstream, lng_send_out, storage_withdrawal, import, "
           "purchase; out: sale, customer_offtake, storage_injection, export"),
        _c("label", True, "The facility, customer, point or capacity, as the desk names it"),
        _c("quantity_mwh", True, "MWh for the gas day, zero or more"),
        _c("book_id", False, "Book the line belongs to; must exist here when given"),
        _c("point", False, "Interconnection or facility point"),
        _c("counterparty", False, "Counterparty of the line"),
        _c("contract_id", False, "Supply or capacity contract the line runs under"),
    ),
    notes="Trades and contracts give the rest of the position; this carries what neither "
    "row holds. Financial positions are derived from the deals, not imported.",
)

_NOMINATIONS = ImportContract(
    name="etrm.nominations",
    version=1,
    title="Nomination statuses from the scheduling system or nominations agent",
    lands_in="gas_day_nomination_events (append-only; the checklist reads the newest)",
    key="digest of (system, gas_day, line_ref, step, status, recorded_at, quantity_mwh)",
    columns=(
        _c("gas_day", True, "Gas day, YYYY-MM-DD"),
        _c("line_ref", True, "contract:<id>, schedule:<line_id>, lng:<slot_id> or trade:<id>"),
        _c("hub", True, "Hub of the line"),
        _c("step", True, "nomination, renomination, lng_unloading, lng_send_out, lng_inventory"),
        _c("status", True, "to_send, sent, confirmed, renominated, mismatch_queried, done"),
        _c("recorded_at", True, "When the scheduler or TSO recorded it, ISO 8601"),
        _c("quantity_mwh", False, "Nominated or confirmed MWh for the gas day"),
        _c("book_id", False, "Book of the line"),
        _c("agent", False, "Nominations agent"),
        _c("note", False, "Free text, at most 500 characters"),
    ),
    notes="A status the platform records; nothing is nominated from here.",
)

_CARGOES = ImportContract(
    name="etrm.cargo_schedule",
    version=1,
    title="The firm's LNG cargo schedule from the ETRM",
    lands_in="lng_cargoes (the cargo plan; a change publishes cargo.changed)",
    key="cargo_id",
    columns=(
        _c("cargo_id", True, "The ETRM's cargo id"),
        _c("vessel_name", True, "Vessel"),
        _c("status", True, "loading, laden, discharging, delivered or ballast"),
        _c("load_port", True, "Load port"),
        _c("vessel_imo", False, "IMO number"),
        _c("load_country", False, "ISO country code"),
        _c("departed_at", False, "ISO 8601"),
        _c("destination_terminal", False, "Discharge terminal"),
        _c("destination_country", False, "ISO country code"),
        _c("eta", False, "ISO 8601"),
        _c("eta_basis", False, "master_notice, ais_declared, feed_estimate, schedule, manual"),
        _c("eta_confidence", False, "high, medium or low"),
        _c("volume_m3", False, "Cargo volume, m3"),
        _c("energy_gwh", False, "Cargo energy, GWh"),
        _c("book_id", False, "Book of the cargo; must exist here when given"),
    ),
    notes="A blank cell keeps the stored value: a vessel feed never takes a cargo out of its "
    "book. Positions and tracks come from the vessel feed, not from this contract.",
)

_COUNTERPARTIES = ImportContract(
    name="erp.counterparties",
    version=1,
    title="Counterparties as the ERP holds them",
    lands_in="erp_references (kind counterparty)",
    key="(system, erp_id)",
    columns=(
        _c("erp_id", True, "The ERP's business partner, customer or vendor number"),
        _c("name", True, "Legal name"),
        _c("counterparty_id", False, "This platform's counterparty id (credit lines), if mapped"),
        _c("legal_entity", False, "The firm's company code or legal entity facing it"),
        _c("country", False, "ISO country code"),
        _c("currency", False, "Default invoicing currency, ISO 4217"),
        _c("payment_terms_days", False, "Days from invoice to payment"),
        _c("blocked", False, "true when the ERP blocks postings or payments to it"),
    ),
    notes="Bank details and tax identifiers are not taken; a file that carries them is refused.",
)

_INVOICES = ImportContract(
    name="erp.invoices",
    version=1,
    title="Invoice references from the ERP",
    lands_in="erp_references (kind invoice)",
    key="(system, invoice_id)",
    columns=(
        _c("invoice_id", True, "The ERP's document or invoice number"),
        _c("counterparty_erp_id", True, "The counterparty's erp_id (known, or in the same "
           "system's counterparty file)"),
        _c("direction", True, "receivable or payable"),
        _c("issue_date", True, "YYYY-MM-DD"),
        _c("due_date", True, "YYYY-MM-DD, on or after the issue date"),
        _c("amount", True, "Gross amount, positive"),
        _c("currency", True, "ISO 4217"),
        _c("trade_ref", False, "The deal, contract or cargo invoiced, as the ETRM names it"),
        _c("status", False, "open, partially_paid, paid or cancelled (default open)"),
        _c("paid_amount", False, "Amount settled so far"),
        _c("period_start", False, "First delivery day invoiced, YYYY-MM-DD"),
        _c("period_end", False, "Last delivery day invoiced, YYYY-MM-DD"),
        _c("legal_entity", False, "The firm's company code"),
    ),
    notes="A reference for reconciliation; nothing is posted or paid from here.",
)

CONTRACTS: dict[str, ImportContract] = {
    contract.contract_id: contract
    for contract in (_DEALS, _POSITIONS, _NOMINATIONS, _CARGOES, _COUNTERPARTIES, _INVOICES)
}


def contract_for(contract_id: str) -> ImportContract:
    contract = CONTRACTS.get(str(contract_id).strip())
    if contract is None:
        raise ImportContractError(
            "contract_unknown",
            f"unknown contract {contract_id!r}; known: {', '.join(sorted(CONTRACTS))}",
        )
    return contract


# --------------------------------------------------------------------------- helpers

_LINE_PREFIX = re.compile(r"^line \d+:\s*")
_CODE_SUFFIX = re.compile(r"\s*\[([a-z_]+)\]$")
_MESSAGE_CODES = (
    ("is not YYYY-MM-DD", "date_invalid"),
    ("is not a number", "number_invalid"),
    ("is not ISO 8601", "time_invalid"),
    ("side must be", "side_invalid"),
    ("is required", "value_required"),
    ("are required", "value_required"),
    ("must be positive", "quantity_not_positive"),
    ("status", "status_invalid"),
    ("window_end must follow", "period_reversed"),
    ("eta_basis", "eta_basis_unknown"),
    ("eta_confidence", "eta_confidence_unknown"),
    ("lat", "coordinate_invalid"),
    ("lon", "coordinate_invalid"),
    ("track", "track_invalid"),
)


def _row_error(exc: Exception) -> RowError:
    """An existing parser's refusal of one row, as a reason code and a message."""

    message = _LINE_PREFIX.sub("", str(exc)).strip()
    code = getattr(exc, "reason_code", None)
    suffix = _CODE_SUFFIX.search(message)
    if suffix:
        code = code or suffix.group(1)
        message = _CODE_SUFFIX.sub("", message)
    if not code:
        code = next((c for needle, c in _MESSAGE_CODES if needle in message), "row_invalid")
    return RowError(str(code), message)


def _system_key(system: str) -> str:
    key = "".join(ch for ch in str(system).upper() if ch.isalnum())[:16]
    if not key:
        raise ImportContractError("system_required", "name the sending system, e.g. Endur")
    return key


def _date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        raise RowError("date_invalid", f"{name} {value!r} is not YYYY-MM-DD") from None


def _instant(value: str, name: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise RowError("time_invalid", f"{name} {value!r} is not ISO 8601") from None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _number(value: str, name: str) -> float:
    try:
        return float(value.replace(",", "").strip())
    except ValueError:
        raise RowError("number_invalid", f"{name} {value!r} is not a number") from None


def _hub(text: str) -> str:
    from eurogas_nexus.domain.ontology.boundary import check_boundary

    checked = check_boundary(market=text, gas_hub_required=True)
    if checked.first is not None or checked.market is None:
        code = checked.first.code.value if checked.first is not None else "market_unknown"
        raise RowError(code, f"{text!r} is not a gas hub")
    return checked.market.code


def _choice(value: str, name: str, allowed: Iterable[str], code: str) -> str:
    allowed = tuple(allowed)
    folded = value.strip().lower()
    if folded not in allowed:
        raise RowError(code, f"{name} {value!r} is not one of {', '.join(allowed)}")
    return folded


def _digest(values: dict[str, Any]) -> str:
    text = json.dumps(values, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _one_row_csv(header: list[str], raw: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerow(raw)
    return buffer.getvalue()


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _same(record: Any, values: dict[str, Any], ignore: Iterable[str] = ()) -> bool:
    """Whether a stored record already holds every supplied (non-``None``) value."""

    skip = set(ignore)
    for name, value in values.items():
        if name in skip or value is None:
            continue
        held = getattr(record, name, None)
        if isinstance(value, datetime) or isinstance(held, datetime):
            if _aware(held) != _aware(value):
                return False
        elif isinstance(value, float) or isinstance(held, float):
            if held is None or abs(float(held) - float(value)) > 1e-9:
                return False
        elif held != value:
            return False
    return True


# --------------------------------------------------------------------------- parsing


@dataclass
class _Row:
    line: int
    key: str
    values: dict[str, Any]
    action: str = "upsert"  # or "remove"


@dataclass
class _Context:
    contract: ImportContract
    system: str
    system_key: str
    source_reference: str
    now: datetime
    session: Any
    books: set[str] | None = None
    counterparties: set[str] = field(default_factory=set)
    erp_loaded: bool = False


def _known_books(context: _Context) -> set[str] | None:
    if context.session is None:
        return None
    if context.books is None:
        from eurogas_nexus.db.models import TradingBookRecord

        context.books = {
            row.book_id for row in context.session.query(TradingBookRecord.book_id).all()
        }
    return context.books


def _check_book(context: _Context, book_id: str | None) -> None:
    if not book_id:
        return
    books = _known_books(context)
    if books is not None and book_id not in books:
        raise RowError("book_unknown", f"book {book_id!r} is not defined here")


def _parse_deal(context: _Context, header, raw, cells) -> _Row:
    from eurogas_nexus.ingestion.etrm_trades import EtrmImportError, parse_etrm_trades

    try:
        parsed = parse_etrm_trades(
            _one_row_csv(header, raw),
            system=context.system,
            source_reference=context.source_reference,
        )
    except EtrmImportError as exc:
        raise _row_error(exc) from None
    if parsed.cancelled_ids:
        return _Row(0, parsed.cancelled_ids[0], {}, action="remove")
    values = parsed.upserts[0]
    _check_book(context, values.get("book_id"))
    return _Row(0, values["order_observation_id"], values)


def _parse_position(context: _Context, header, raw, cells) -> _Row:
    from eurogas_nexus.application.gas_day import IN_KINDS, OUT_KINDS

    line_id = cells["line_id"]
    if not line_id or len(line_id) > 128:
        raise RowError("value_required", "line_id is required (at most 128 characters)")
    direction = _choice(cells["direction"], "direction", ("in", "out"), "direction_invalid")
    kinds = IN_KINDS if direction == "in" else OUT_KINDS
    kind = cells["kind"].strip().lower()
    if kind not in (*IN_KINDS, *OUT_KINDS):
        raise RowError("kind_unknown", f"kind {cells['kind']!r} is not a schedule line kind")
    if kind not in kinds:
        raise RowError("kind_direction_mismatch", f"kind {kind} is not an {direction} line")
    if not cells["label"]:
        raise RowError("value_required", "label is required")
    quantity = _number(cells["quantity_mwh"], "quantity_mwh")
    if quantity < 0:
        raise RowError("quantity_negative", "quantity_mwh must be zero or more (direction is "
                       "the sign)")
    book_id = cells.get("book_id") or None
    _check_book(context, book_id)
    values = {
        "line_id": line_id,
        "gas_day": _date(cells["gas_day"], "gas_day"),
        "hub": _hub(cells["hub"]),
        "book_id": book_id,
        "direction": direction,
        "kind": kind,
        "label": cells["label"][:160],
        "point": (cells.get("point") or None),
        "counterparty": (cells.get("counterparty") or None),
        "contract_id": (cells.get("contract_id") or None),
        "quantity_mwh": quantity,
        "source_system": context.system[:64],
        "source_reference": context.source_reference[:256],
        "simulated": False,
        "updated_at_utc": context.now,
    }
    return _Row(0, line_id, values)


_LINE_REF = re.compile(r"^(contract|schedule|lng|trade):\S{1,150}$")


def _parse_nomination(context: _Context, header, raw, cells) -> _Row:
    from eurogas_nexus.application.gas_day_checklist import STATUSES, STEPS

    gas_day = _date(cells["gas_day"], "gas_day")
    line_ref = cells["line_ref"]
    if not _LINE_REF.match(line_ref):
        raise RowError(
            "line_ref_invalid", "line_ref must be contract:<id>, schedule:<id>, lng:<id> or "
            "trade:<id>"
        )
    step = _choice(cells["step"], "step", STEPS, "step_unknown")
    status = _choice(cells["status"], "status", STATUSES, "status_unknown")
    recorded = _instant(cells["recorded_at"], "recorded_at")
    if recorded > context.now + _FUTURE_SKEW:
        raise RowError("time_in_future", "recorded_at is later than now")
    quantity = (
        _number(cells["quantity_mwh"], "quantity_mwh") if cells.get("quantity_mwh") else None
    )
    note = cells.get("note") or None
    if note is not None and len(note) > 500:
        raise RowError("value_too_long", "note is longer than 500 characters")
    book_id = cells.get("book_id") or None
    _check_book(context, book_id)
    hub = _hub(cells["hub"])
    identity = {
        "system": context.system_key,
        "gas_day": gas_day.isoformat(),
        "line_ref": line_ref,
        "step": step,
        "status": status,
        "recorded_at": recorded.isoformat(),
        "quantity_mwh": quantity,
    }
    event_id = f"imp-{_digest(identity)[:60]}"
    values = {
        "event_id": event_id,
        "gas_day": gas_day,
        "line_ref": line_ref,
        "hub": hub,
        "book_id": book_id,
        "step": step,
        "status": status,
        "quantity_mwh": quantity,
        "agent": (cells.get("agent") or None),
        "origin": "import",
        "recorded_by": f"import:{context.system}"[:128],
        "recorded_at_utc": recorded,
        "note": note,
        "source_system": context.system[:64],
    }
    return _Row(0, event_id, values)


def _parse_cargo(context: _Context, header, raw, cells) -> _Row:
    from eurogas_nexus.ingestion.lng_positions import LngImportError, parse_lng_cargoes

    try:
        (values,) = parse_lng_cargoes(
            _one_row_csv(header, raw),
            source_system=context.system,
            source_reference=context.source_reference,
            now_utc=context.now,
        )
    except LngImportError as exc:
        raise _row_error(exc) from None
    _check_book(context, values.get("book_id"))
    return _Row(0, values["cargo_id"], values)


_ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _currency(text: str, name: str = "currency") -> str:
    code = text.strip().upper()
    if not _ISO_CURRENCY.match(code):
        raise RowError("currency_invalid", f"{name} {text!r} is not an ISO 4217 code")
    return code


def _reference(context: _Context, kind: str, external_id: str, fields_: dict[str, Any],
               **links: Any) -> _Row:
    reference_id = f"{context.system_key.lower()}:{kind}:{external_id}"
    values = {
        "reference_id": reference_id,
        "system": context.system_key,
        "kind": kind,
        "external_id": external_id,
        "counterparty_id": links.get("counterparty_id"),
        "counterparty_external_id": links.get("counterparty_external_id"),
        "trade_ref": links.get("trade_ref"),
        "fields": fields_,
        "content_hash": _digest({**fields_, **links}),
        "source_reference": context.source_reference[:256],
    }
    return _Row(0, reference_id, values)


def _parse_counterparty(context: _Context, header, raw, cells) -> _Row:
    erp_id = cells["erp_id"]
    if not erp_id or len(erp_id) > 96:
        raise RowError("value_required", "erp_id is required (at most 96 characters)")
    if not cells["name"]:
        raise RowError("value_required", "name is required")
    fields_: dict[str, Any] = {"name": cells["name"][:160]}
    if cells.get("legal_entity"):
        fields_["legal_entity"] = cells["legal_entity"][:64]
    if cells.get("country"):
        country = cells["country"].strip().upper()
        if not re.match(r"^[A-Z]{2}$", country):
            raise RowError("country_invalid", f"country {cells['country']!r} is not ISO 3166")
        fields_["country"] = country
    if cells.get("currency"):
        fields_["currency"] = _currency(cells["currency"])
    if cells.get("payment_terms_days"):
        days = _number(cells["payment_terms_days"], "payment_terms_days")
        if days < 0 or days != int(days):
            raise RowError("number_invalid", "payment_terms_days must be a whole number >= 0")
        fields_["payment_terms_days"] = int(days)
    if cells.get("blocked"):
        flag = cells["blocked"].strip().lower()
        if flag not in {"true", "false", "1", "0", "yes", "no", "x", ""}:
            raise RowError("flag_invalid", "blocked must be true or false")
        fields_["blocked"] = flag in {"true", "1", "yes", "x"}
    context.counterparties.add(erp_id)
    return _reference(
        context, "counterparty", erp_id, fields_,
        counterparty_id=(cells.get("counterparty_id") or None),
    )


_INVOICE_STATUSES = ("open", "partially_paid", "paid", "cancelled")


def _known_counterparties(context: _Context) -> set[str]:
    if context.session is not None and not context.erp_loaded:
        from eurogas_nexus.db.models import ErpReferenceRecord

        rows = context.session.query(ErpReferenceRecord.external_id).filter(
            ErpReferenceRecord.system == context.system_key,
            ErpReferenceRecord.kind == "counterparty",
        )
        context.counterparties |= {row.external_id for row in rows}
        context.erp_loaded = True
    return context.counterparties


def _parse_invoice(context: _Context, header, raw, cells) -> _Row:
    invoice_id = cells["invoice_id"]
    if not invoice_id or len(invoice_id) > 96:
        raise RowError("value_required", "invoice_id is required (at most 96 characters)")
    counterparty = cells["counterparty_erp_id"]
    if not counterparty:
        raise RowError("value_required", "counterparty_erp_id is required")
    if context.session is not None and counterparty not in _known_counterparties(context):
        raise RowError(
            "counterparty_unknown",
            f"counterparty {counterparty!r} is not among this system's ERP counterparties",
        )
    direction = _choice(
        cells["direction"], "direction", ("receivable", "payable"), "direction_invalid"
    )
    issued = _date(cells["issue_date"], "issue_date")
    due = _date(cells["due_date"], "due_date")
    if due < issued:
        raise RowError("period_reversed", "due_date is before issue_date")
    amount = _number(cells["amount"], "amount")
    if amount <= 0:
        raise RowError("amount_not_positive", "amount must be positive (direction is the sign)")
    fields_: dict[str, Any] = {
        "direction": direction,
        "issue_date": issued.isoformat(),
        "due_date": due.isoformat(),
        "amount": amount,
        "currency": _currency(cells["currency"]),
        "status": _choice(cells.get("status") or "open", "status", _INVOICE_STATUSES,
                          "status_unknown"),
    }
    if cells.get("paid_amount"):
        paid = _number(cells["paid_amount"], "paid_amount")
        if paid < 0 or paid > amount + 1e-9:
            raise RowError("amount_invalid", "paid_amount must be between 0 and amount")
        fields_["paid_amount"] = paid
    if cells.get("period_start") or cells.get("period_end"):
        start = _date(cells.get("period_start") or "", "period_start")
        end = _date(cells.get("period_end") or "", "period_end")
        if end < start:
            raise RowError("period_reversed", "period_end is before period_start")
        fields_["period_start"], fields_["period_end"] = start.isoformat(), end.isoformat()
    if cells.get("legal_entity"):
        fields_["legal_entity"] = cells["legal_entity"][:64]
    return _reference(
        context, "invoice", invoice_id, fields_,
        counterparty_external_id=counterparty,
        trade_ref=(cells.get("trade_ref") or None),
    )


_PARSERS: dict[str, Callable[..., _Row]] = {
    "etrm.deals": _parse_deal,
    "etrm.physical_positions": _parse_position,
    "etrm.nominations": _parse_nomination,
    "etrm.cargo_schedule": _parse_cargo,
    "erp.counterparties": _parse_counterparty,
    "erp.invoices": _parse_invoice,
}


def _read(contract: ImportContract, text: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportContractError("file_empty", "the file has no header row") from None
    names = [(name or "").strip().lower() for name in header]
    forbidden = sorted(set(names) & FORBIDDEN_COLUMNS)
    if forbidden:
        raise ImportContractError(
            "column_forbidden",
            f"the file carries {', '.join(forbidden)}; bank details and tax or government "
            "identifiers are not taken, remove the column(s)",
        )
    missing = [name for name in contract.required if name not in names]
    if missing:
        raise ImportContractError("column_missing", f"missing column(s): {', '.join(missing)}")
    rows: list[tuple[int, list[str]]] = []
    for line, raw in enumerate(reader, start=2):
        if not any((cell or "").strip() for cell in raw):
            continue  # a blank line is not a row
        if len(rows) >= MAX_ROWS:
            raise ImportContractError("file_too_large", f"more than {MAX_ROWS} rows")
        rows.append((line, raw))
    return names, rows


def _parse(context: _Context, text: str, report: ImportReport) -> list[_Row]:
    names, rows = _read(context.contract, text)
    parser = _PARSERS[context.contract.name]
    accepted: list[_Row] = []
    seen: dict[str, int] = {}
    for line, raw in rows:
        report.rows += 1
        if len(raw) != len(names):
            report.refused.append(
                RowRefusal(line, "column_count", f"{len(raw)} cells for {len(names)} columns")
            )
            continue
        cells = {name: (value or "").strip() for name, value in zip(names, raw, strict=True)}
        try:
            row = parser(context, names, [cells[name] for name in names], cells)
        except RowError as exc:
            report.refused.append(RowRefusal(line, exc.code, exc.message))
            continue
        row.line = line
        if row.key in seen:
            report.refused.append(
                RowRefusal(
                    line, "duplicate_key",
                    f"the same key as line {seen[row.key]}; send one row per key", row.key,
                )
            )
            continue
        seen[row.key] = line
        accepted.append(row)
    report.accepted = len(accepted)
    return accepted


# --------------------------------------------------------------------------- storing


def _plan_and_store(context: _Context, rows: list[_Row], report: ImportReport, *,
                    write: bool) -> None:
    store = _STORES[context.contract.name]
    store(context, rows, report, write)


def _store_deals(context: _Context, rows: list[_Row], report: ImportReport, write: bool):
    from eurogas_nexus.db.models import ScreenOrderObservationRecord as Model

    session = context.session
    for row in rows:
        held = session.get(Model, row.key)
        if row.action == "remove":
            if held is None:
                report.unchanged += 1
            else:
                report.removed += 1
                if write:
                    session.delete(held)
            continue
        if held is None:
            report.created += 1
            if write:
                session.add(Model(**row.values))
        elif _same(held, row.values, ignore=("source_reference",)):
            report.unchanged += 1
        else:
            report.updated += 1
            if write:
                session.merge(Model(**row.values))


def _store_by_key(model_name: str, ignore: tuple[str, ...]):
    def store(context: _Context, rows: list[_Row], report: ImportReport, write: bool):
        from eurogas_nexus.db import models

        model = getattr(models, model_name)
        session = context.session
        for row in rows:
            held = session.get(model, row.key)
            if held is None:
                report.created += 1
                if write:
                    session.add(model(**row.values))
            elif _same(held, row.values, ignore=ignore):
                report.unchanged += 1
            else:
                report.updated += 1
                if write:
                    for name, value in row.values.items():
                        setattr(held, name, value)

    return store


def _store_nominations(context: _Context, rows: list[_Row], report: ImportReport, write: bool):
    from eurogas_nexus.db.models import GasDayNominationEventRecord as Model

    session = context.session
    for row in rows:
        if session.get(Model, row.key) is not None:
            report.unchanged += 1  # append-only: the same status recorded once
            continue
        report.created += 1
        if write:
            session.add(Model(**row.values))


def _store_cargoes(context: _Context, rows: list[_Row], report: ImportReport, write: bool):
    from eurogas_nexus.application.lng_positions_import import store_lng_rows
    from eurogas_nexus.db.models import LngCargoRecord

    session = context.session
    changed: list[dict[str, Any]] = []
    for row in rows:
        held = session.get(LngCargoRecord, row.key)
        if held is None:
            report.created += 1
        elif _same(held, row.values, ignore=("source_reference", "updated_at_utc",
                                              "source_system")):
            report.unchanged += 1
            continue
        else:
            report.updated += 1
        changed.append(row.values)
    if write and changed:
        result = store_lng_rows(session, "cargo", changed, now_utc=context.now)
        if result.get("eta_disagreements"):
            report.notes.append(
                f"{len(result['eta_disagreements'])} ETA(s) differ from another source's"
            )


def _store_references(context: _Context, rows: list[_Row], report: ImportReport, write: bool):
    from eurogas_nexus.db.models import ErpReferenceRecord as Model

    session = context.session
    for row in rows:
        held = session.get(Model, row.key)
        if held is None:
            report.created += 1
            if write:
                session.add(
                    Model(**row.values, first_imported_at_utc=context.now,
                          last_changed_at_utc=context.now)
                )
        elif held.content_hash == row.values["content_hash"]:
            report.unchanged += 1
        else:
            report.updated += 1
            if write:
                for name, value in row.values.items():
                    setattr(held, name, value)
                held.last_changed_at_utc = context.now


_STORES: dict[str, Callable[..., None]] = {
    "etrm.deals": _store_deals,
    "etrm.physical_positions": _store_by_key(
        "GasDayScheduleLineRecord", ("source_reference", "updated_at_utc")
    ),
    "etrm.nominations": _store_nominations,
    "etrm.cargo_schedule": _store_cargoes,
    "erp.counterparties": _store_references,
    "erp.invoices": _store_references,
}


# --------------------------------------------------------------------------- entry points


def run_import(
    contract_id: str,
    text: str,
    *,
    system: str,
    file_name: str = "upload.csv",
    session: Any = None,
    on_error: str = REJECT_FILE,
    commit: bool = False,
    now: datetime | None = None,
) -> ImportReport:
    """Check a file against its contract and, with ``commit``, store its accepted rows.

    Without a ``session`` the rows are checked on their own (no book or counterparty lookup,
    no counts of what would change). With one and without ``commit`` it is a dry run: the
    counts say what storing would do and nothing is written. With ``commit`` the rows are
    written in the session (the caller commits) unless the file is refused.
    """

    contract = contract_for(contract_id)
    if on_error not in ON_ERROR:
        raise ImportContractError("on_error_invalid", f"on_error must be one of {ON_ERROR}")
    moment = _aware(now) or datetime.now(UTC)
    system_key = _system_key(system)
    report = ImportReport(
        contract_id=contract.contract_id,
        system=system_key,
        file_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        on_error=on_error,
    )
    context = _Context(
        contract=contract,
        system=str(system).strip()[:32],
        system_key=system_key,
        source_reference=f"import:{contract.contract_id}:{system_key.lower()}:{file_name}"[:256],
        now=moment,
        session=session,
    )
    rows = _parse(context, text, report)
    if report.rows == 0:
        report.file_refused = True
        report.notes.append("the file holds no rows")
        return report
    if report.refused and on_error == REJECT_FILE:
        report.file_refused = True
        report.notes.append(
            f"{len(report.refused)} row(s) refused, so nothing is stored; fix them, or send "
            "with skip_rows to store the others"
        )
        return report
    if session is None:
        report.notes.append("checked without the store: books, counterparties and changes "
                            "are not looked up")
        return report
    _plan_and_store(context, rows, report, write=commit)
    report.committed = bool(commit)
    if commit:
        from eurogas_nexus.db.repositories.audit import record_audit_event

        record_audit_event(
            session,
            event_type="data.import",
            principal=f"import:{context.system}"[:128],
            action=f"import.{contract.contract_id}",
            resource=report.file_sha256,
            outcome="stored",
            severity="info",
            detail=(
                f"rows={report.rows} accepted={report.accepted} refused={len(report.refused)} "
                f"created={report.created} updated={report.updated} "
                f"unchanged={report.unchanged} removed={report.removed}"
            ),
        )
    return report


def contracts_catalogue() -> list[dict[str, Any]]:
    """Every contract, for ``GET /api/imports/contracts`` and the docs."""

    return [CONTRACTS[key].as_dict() for key in sorted(CONTRACTS)]


__all__ = [
    "CONTRACTS",
    "FORBIDDEN_COLUMNS",
    "ON_ERROR",
    "REJECT_FILE",
    "SKIP_ROWS",
    "ImportContract",
    "ImportContractError",
    "ImportReport",
    "RowRefusal",
    "contract_for",
    "contracts_catalogue",
    "run_import",
]
