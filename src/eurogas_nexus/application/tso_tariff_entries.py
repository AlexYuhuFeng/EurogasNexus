"""Reviewed public transmission tariffs: what an administrator enters where ENTSOG has none.

ENTSOG's tariff dataset leaves legs route pricing needs uncovered (``application/
tariff_coverage.py``): National Gas's charges (its ENTSOG figures are refused), GTS's exit to
BBL at Balgzand, the French side at Obergailbach, LNG and Norwegian landing entries. The
operators publish them on their own sites, whose terms the product has not reviewed for
automated reading (docs/legal/DATA_SOURCE_TERMS.md), so a person reads the published charge
and enters it, on the pattern of the LNG terminal tariff register:

- **Recorded** by an operator or administrator: operator, point and direction chosen from the
  reference network (never typed), product, firmness, the value in the unit and currency the
  operator published it (any unit ``domain/route_cost/tariff_units`` reads), validity, the
  operator's own status (final or indicative), the source URL, its publication date and where
  in the document the figure is. A leg ENTSOG already publishes for the period is refused
  (``published_row_held``): the published row prices it.
- **Candidate** until a second person reviews it (four eyes, ``four_eyes``): it prices the leg
  as indicative meanwhile.
- **Reviewed**: it prices the leg as a reviewed public tariff, with the operator's status.
- **Retired** automatically when an ingested ENTSOG row for the same operator, point,
  direction, product and firmness covers part of its period (``retire_superseded_entries``,
  called by the ENTSOG tariff ingestion); **withdrawn** by a person. Neither prices anything.

Each entry is mirrored into the tariff register (``tso_tariffs``, ``tariff_id``
``entry-<entry_id>``), so every reader (route pricing, the route engine, the valuation
snapshot, the coverage table) reads it like any other row. Every step is audited.

本模块供管理员录入 ENTSOG 未发布的运营商公开费率（四眼复核）；复核前按指示性计价，
有已发布行覆盖同一段时自动退役。
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.domain.route_cost.tariff_units import parse_unit

CANDIDATE = "CANDIDATE"
REVIEWED = "REVIEWED"
RETIRED = "RETIRED"
WITHDRAWN = "WITHDRAWN"
ACTIVE = (CANDIDATE, REVIEWED)
#: ``tso_tariffs.document_id`` of a mirrored entry, by state.
DOCUMENT = {CANDIDATE: "tariff-entry-candidate", REVIEWED: "tariff-entry-reviewed"}
PRODUCTS = ("ANNUAL", "QUARTERLY", "MONTHLY", "DAILY", "WITHIN_DAY")
FIRMNESS = ("FIRM", "INTERRUPTIBLE")
#: The market-area label a mirrored row is filed under, by operator country (ENTSOG's).
_MARKET_AREA = {
    "NL": "Netherlands",
    "DE": "DE THE BZ",
    "BE": "BeLux",
    "LU": "BeLux",
    "FR": "TRF",
    "UK": "UK",
    "GB": "UK",
    "DK": "Joint Bal Zone DK/SE",
    "IE": "Ireland",
    "AT": "Austria",
    "CZ": "Czech",
    "IT": "Italy",
    "ES": "Spain",
    "CH": "Switzerland",
}


class TariffEntryError(ValueError):
    """A refused entry action; ``code`` is stable for the API."""

    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _now(now_utc: datetime | None) -> datetime:
    return now_utc or datetime.now(UTC)


def _audit(session, *, actor, action, resource, outcome, detail, now) -> None:
    from eurogas_nexus.db.repositories.audit import record_audit_event

    record_audit_event(
        session,
        event_type="governance.data",
        principal=actor[:128],
        action=action,
        resource=resource,
        outcome=outcome,
        severity="info",
        detail=detail[:900],
        source_system="tso-tariff-entries",
        now_utc=now,
    )


def _note_tariffs_changed(session, reason: str, now: datetime) -> None:
    try:
        from eurogas_nexus.application.opportunities.schedule import note_input_changed
    except ImportError:  # pragma: no cover - the opportunity schedule is optional here
        return
    note_input_changed(session, "tariffs", reason=reason, at_utc=now)


def _label(start: date, last: date) -> str:
    if start.month == 10 and start.day == 1 and last == date(start.year + 1, 9, 30):
        return f"{start.year}/{(start.year + 1) % 100:02d}"
    if start.month == 1 and start.day == 1 and last == date(start.year, 12, 31):
        return str(start.year)
    return f"{start:%Y-%m}..{last:%y-%m}"


# --- what can be chosen ----------------------------------------------------------------------


def reference_choices(bundle: dict | None = None) -> dict[str, Any]:
    """Operators and points from the reference network, for the entry form's pickers.

    Points: every adjacency point of the market-area graph and every corridor, LNG and
    landing point of the tariff read, with the operators ENTSOG lists there (the access rows,
    else the node's operators) and the directions each operator books.
    """

    from eurogas_nexus.ingestion.entsog_tariffs import read_points
    from eurogas_nexus.reference_data.network_bundle import load_bundle
    from eurogas_nexus.reference_data.tariff_scope import scope_points

    bundle = bundle if bundle is not None else load_bundle()
    operators = bundle.get("operators") or {}
    nodes = {str(node["point_key"]): node for node in bundle.get("nodes") or []}
    # Operators at a point: the operator point directions ENTSOG lists (access rows), the
    # node's operators and the operators the market-area links name on each side. ENTSOG's
    # direction list is incomplete (National Gas lists only its exit at Bacton IUK while the
    # graph prices its entry there too), so either direction can be entered.
    at: dict[str, set[str]] = {}
    for row in bundle.get("access") or []:
        point, operator = str(row.get("point_key") or ""), str(row.get("operator_key") or "")
        if point and operator:
            at.setdefault(point, set()).add(operator)
    for edge in bundle.get("edges") or []:
        if edge.get("type") == "market_area_link":
            at.setdefault(str(edge["point_key"]), set()).update(edge.get("operators") or [])
    scope = scope_points()
    points = []
    for key in read_points(bundle):
        node = nodes.get(key)
        at_point = at.get(key, set()) | set((node or {}).get("operators") or [])
        points.append(
            {
                "point_key": key,
                "name": str((node or {}).get("name") or scope.get(key, ("", key, ()))[1] or key),
                "country": str((node or {}).get("country") or ""),
                "kind": scope.get(key, ("crossing",))[0],
                "operators": [
                    {"operator_key": op, "directions": ["ENTRY", "EXIT"]}
                    for op in sorted(at_point)
                    if "-TSO-" in op
                ],
            }
        )
    return {
        "operators": [
            {
                "operator_key": key,
                "name": str(value.get("name") or key),
                "country": str(value.get("country") or ""),
            }
            for key, value in sorted(operators.items())
            if "-TSO-" in key
        ],
        "points": points,
        "products": list(PRODUCTS),
        "firmness": list(FIRMNESS),
    }


# --- record, review, withdraw ----------------------------------------------------------------


def _overlaps(start_a: date, last_a: date, start_b: date | None, last_b: date | None) -> bool:
    return (last_b is None or start_a <= last_b) and (start_b is None or start_b <= last_a)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _published_rows(session, *, tso, point_id, direction, product, firmness):
    from eurogas_nexus.db.models import TsoTariffRecord

    return [
        row
        for row in session.query(TsoTariffRecord).filter(
            TsoTariffRecord.point_id == point_id,
            TsoTariffRecord.direction == direction,
            TsoTariffRecord.capacity_product == product,
            TsoTariffRecord.firmness == firmness,
            TsoTariffRecord.document_id.like("entsog-tariffsfulls-%"),
        )
        if row.tso.strip().lower() == tso.strip().lower()
    ]


def record_entry(
    session,
    body: dict[str, Any],
    *,
    actor: str,
    bundle: dict | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Record one operator-published charge as a candidate (validated, audited, mirrored)."""

    from eurogas_nexus.db.models import TsoTariffEntryRecord

    choices = reference_choices(bundle)
    operators = {item["operator_key"]: item for item in choices["operators"]}
    points = {item["point_key"]: item for item in choices["points"]}
    operator_key = str(body.get("operator_key") or "")
    point_key = str(body.get("point_key") or "")
    direction = str(body.get("direction") or "").upper()
    if operator_key not in operators:
        raise TariffEntryError("operator_unknown", "Choose the operator from the list.", 422)
    if point_key not in points:
        raise TariffEntryError("point_unknown", "Choose the point from the list.", 422)
    if direction not in {"ENTRY", "EXIT"}:
        raise TariffEntryError("direction_invalid", "Direction is entry or exit.", 422)
    if operator_key not in {item["operator_key"] for item in points[point_key]["operators"]}:
        raise TariffEntryError(
            "operator_not_at_point",
            f"{operators[operator_key]['name']} is not an operator at "
            f"{points[point_key]['name']} in the reference network.",
            422,
        )
    product = str(body.get("capacity_product") or "ANNUAL").upper()
    firmness = str(body.get("firmness") or "FIRM").upper()
    if product not in PRODUCTS or firmness not in FIRMNESS:
        raise TariffEntryError("product_invalid", "Choose a standard capacity product.", 422)
    try:
        value = float(body.get("tariff_value"))
    except (TypeError, ValueError):
        raise TariffEntryError("value_invalid", "Enter the published value.", 422) from None
    if not math.isfinite(value) or value < 0:
        raise TariffEntryError("value_invalid", "Enter the published value.", 422)
    unit = str(body.get("unit") or "").strip()
    currency = str(body.get("currency") or "").strip().upper()
    parsed = parse_unit(unit)
    if parsed is None:
        raise TariffEntryError(
            "unit_not_understood",
            f"Unit {unit!r} is not one the pricing reads (for example EUR/(kWh/h)/y, "
            "GBP/(kWh/d)/y, p/kWh/d, EUR/MWh).",
            422,
        )
    if parsed.currency != currency:
        raise TariffEntryError(
            "currency_mismatch", f"The unit is in {parsed.currency}, not {currency}.", 422
        )
    try:
        valid_from = date.fromisoformat(str(body.get("valid_from")))
        valid_to = date.fromisoformat(str(body.get("valid_to")))
        published_on = date.fromisoformat(str(body.get("published_on")))
    except ValueError:
        raise TariffEntryError("date_invalid", "Dates are YYYY-MM-DD.", 422) from None
    if valid_to < valid_from:
        raise TariffEntryError("period_invalid", "The validity ends before it starts.", 422)
    now = _now(now_utc)
    if published_on > now.date():
        raise TariffEntryError("published_on_future", "The publication date is in the future.", 422)
    status = str(body.get("published_status") or "").upper()
    if status not in {"FINAL", "INDICATIVE"}:
        raise TariffEntryError(
            "status_invalid", "Say whether the operator published it final.", 422
        )
    source_url = str(body.get("source_url") or "").strip()
    if not source_url.startswith("https://") or len(source_url) > 500:
        raise TariffEntryError("source_url_invalid", "The source is an https:// address.", 422)
    location = str(body.get("source_location") or "").strip()
    if not location or len(location) > 256:
        raise TariffEntryError(
            "source_location_required", "Say where in the document the figure is.", 422
        )
    tso = operators[operator_key]["name"]
    for row in _published_rows(
        session,
        tso=tso,
        point_id=point_key,
        direction=direction,
        product=product,
        firmness=firmness,
    ):
        if _overlaps(
            valid_from, valid_to, _as_date(row.effective_from), _as_date(row.effective_to)
        ):
            raise TariffEntryError(
                "published_row_held",
                "ENTSOG publishes this leg for the period; the published row prices it.",
            )
    for other in session.query(TsoTariffEntryRecord).filter(
        TsoTariffEntryRecord.point_id == point_key,
        TsoTariffEntryRecord.direction == direction,
        TsoTariffEntryRecord.capacity_product == product,
        TsoTariffEntryRecord.firmness == firmness,
        TsoTariffEntryRecord.state.in_(ACTIVE),
    ):
        if other.tso == tso and _overlaps(valid_from, valid_to, other.valid_from, other.valid_to):
            raise TariffEntryError(
                "entry_exists",
                "An entry for this leg and period is already held; withdraw it first.",
            )
    country = operators[operator_key]["country"] or points[point_key]["country"]
    row = TsoTariffEntryRecord(
        entry_id=f"tte-{uuid.uuid4().hex[:20]}",
        state=CANDIDATE,
        operator_key=operator_key,
        tso=tso,
        point_id=point_key,
        point_name=points[point_key]["name"][:256],
        country=country[:8],
        market_area=_MARKET_AREA.get(country, country or "ENTRY")[:64],
        direction=direction,
        capacity_product=product,
        firmness=firmness,
        tariff_value=value,
        unit=unit,
        currency=currency,
        valid_from=valid_from,
        valid_to=valid_to,
        gas_year=_label(valid_from, valid_to)[:16],
        published_status=status,
        source_url=source_url,
        published_on=published_on,
        source_location=location,
        note=(str(body.get("note") or "").strip()[:1000] or None),
        recorded_by=actor[:128],
        recorded_at_utc=now,
    )
    session.add(row)
    _mirror(session, row, now)
    session.flush()
    _audit(
        session,
        actor=actor,
        action="tso_tariff_entry.record",
        resource=f"tso_tariff_entry:{row.entry_id}",
        outcome=CANDIDATE,
        detail=(
            f"{tso} {point_key} {direction} {product} {firmness} {value:g} {unit} "
            f"{valid_from}..{valid_to}; source={source_url}"
        ),
        now=now,
    )
    _note_tariffs_changed(session, f"tariff entry {row.entry_id} recorded", now)
    return entry_payload(row)


def review_entry(session, entry_id: str, *, reviewer: str, now_utc: datetime | None = None):
    """Mark a candidate reviewed; four eyes: never by whoever recorded it."""

    from eurogas_nexus.db.models import TsoTariffEntryRecord

    row = session.get(TsoTariffEntryRecord, entry_id)
    if row is None:
        raise TariffEntryError("entry_not_found", "No such tariff entry.", 404)
    if row.state == REVIEWED:
        return entry_payload(row)
    if row.state != CANDIDATE:
        raise TariffEntryError("entry_closed", "This entry is retired or withdrawn.")
    if reviewer == row.recorded_by:
        raise TariffEntryError(
            "four_eyes", "A second person reviews an entry: you recorded this one.", 403
        )
    now = _now(now_utc)
    row.state = REVIEWED
    row.reviewed_by = reviewer[:128]
    row.reviewed_at_utc = now
    _mirror(session, row, now)
    session.flush()
    _audit(
        session,
        actor=reviewer,
        action="tso_tariff_entry.review",
        resource=f"tso_tariff_entry:{entry_id}",
        outcome=REVIEWED,
        detail=f"{row.tso} {row.point_id} {row.direction} {row.tariff_value:g} {row.unit}",
        now=now,
    )
    _note_tariffs_changed(session, f"tariff entry {entry_id} reviewed", now)
    return entry_payload(row)


def withdraw_entry(
    session, entry_id: str, *, actor: str, reason: str, now_utc: datetime | None = None
):
    """Withdraw an active entry (it stops pricing at once)."""

    from eurogas_nexus.db.models import TsoTariffEntryRecord

    row = session.get(TsoTariffEntryRecord, entry_id)
    if row is None:
        raise TariffEntryError("entry_not_found", "No such tariff entry.", 404)
    if row.state not in ACTIVE:
        return entry_payload(row)
    if not reason.strip():
        raise TariffEntryError("reason_required", "Say why the entry is withdrawn.", 422)
    now = _now(now_utc)
    _close(session, row, WITHDRAWN, actor=actor, reason=reason.strip()[:256], now=now)
    _audit(
        session,
        actor=actor,
        action="tso_tariff_entry.withdraw",
        resource=f"tso_tariff_entry:{entry_id}",
        outcome=WITHDRAWN,
        detail=reason[:500],
        now=now,
    )
    _note_tariffs_changed(session, f"tariff entry {entry_id} withdrawn", now)
    return entry_payload(row)


def _close(session, row, state: str, *, actor: str, reason: str, now: datetime) -> None:
    from eurogas_nexus.db.models import TsoTariffRecord

    row.state = state
    row.closed_by = actor[:128]
    row.closed_at_utc = now
    row.closed_reason = reason[:256]
    mirrored = session.get(TsoTariffRecord, mirror_id(row.entry_id))
    if mirrored is not None:
        session.delete(mirrored)
    session.flush()


def retire_superseded_entries(session, *, now_utc: datetime | None = None) -> int:
    """Retire active entries an ingested ENTSOG row now covers (same operator, point,
    direction, product and firmness, overlapping period); returns how many. Idempotent."""

    from eurogas_nexus.db.models import TsoTariffEntryRecord

    now = _now(now_utc)
    retired = 0
    for row in session.query(TsoTariffEntryRecord).filter(TsoTariffEntryRecord.state.in_(ACTIVE)):
        for published in _published_rows(
            session,
            tso=row.tso,
            point_id=row.point_id,
            direction=row.direction,
            product=row.capacity_product,
            firmness=row.firmness,
        ):
            if _overlaps(
                row.valid_from,
                row.valid_to,
                _as_date(published.effective_from),
                _as_date(published.effective_to),
            ):
                reason = f"published row {published.tariff_id} ({published.document_id})"
                _close(session, row, RETIRED, actor="entsog-tariffs", reason=reason, now=now)
                _audit(
                    session,
                    actor="entsog-tariffs",
                    action="tso_tariff_entry.retire",
                    resource=f"tso_tariff_entry:{row.entry_id}",
                    outcome=RETIRED,
                    detail=reason,
                    now=now,
                )
                retired += 1
                break
    return retired


# --- the mirror in the tariff register -------------------------------------------------------


def mirror_id(entry_id: str) -> str:
    return f"entry-{entry_id}"


def _mirror(session, row, now: datetime) -> None:
    from eurogas_nexus.db.models import TsoTariffRecord

    reviewed = row.state == REVIEWED
    refs = [
        f"source: {row.source_url}",
        f"published on {row.published_on.isoformat()}, {row.source_location}",
        f"published as {row.published_status.lower()}",
        f"entered by {row.recorded_by} on {row.recorded_at_utc.date().isoformat()}",
    ]
    if reviewed:
        refs.append(f"reviewed by {row.reviewed_by} on {now.date().isoformat()}")
    session.merge(
        TsoTariffRecord(
            tariff_id=mirror_id(row.entry_id),
            document_id=DOCUMENT[REVIEWED if reviewed else CANDIDATE],
            country=row.country,
            tso=row.tso,
            market_area=row.market_area,
            gas_year=row.gas_year,
            point_id=row.point_id,
            source_point_name=row.point_name,
            direction=row.direction,
            capacity_product=row.capacity_product,
            firmness=row.firmness,
            tariff_value=row.tariff_value,
            currency=row.currency,
            unit=row.unit,
            effective_from=datetime.combine(row.valid_from, datetime.min.time(), tzinfo=UTC),
            effective_to=datetime.combine(row.valid_to, datetime.min.time(), tzinfo=UTC),
            # A candidate prices as indicative; a reviewed entry with the operator's status.
            tariff_status=row.published_status if reviewed else "INDICATIVE",
            source_table=(
                "Reviewed public tariff, entered by an administrator"
                if reviewed
                else "Public tariff entered by an administrator, awaiting review"
            ),
            source_page=None,
            source_refs=refs,
            manual_review_required=not reviewed,
            created_at_utc=row.recorded_at_utc,
        )
    )


# --- reads -----------------------------------------------------------------------------------


def entry_payload(row) -> dict[str, Any]:
    stamp = lambda value: value.isoformat() if value else None  # noqa: E731
    return {
        "entry_id": row.entry_id,
        "state": row.state,
        "operator_key": row.operator_key,
        "tso": row.tso,
        "point_id": row.point_id,
        "point_name": row.point_name,
        "direction": row.direction,
        "capacity_product": row.capacity_product,
        "firmness": row.firmness,
        "tariff_value": row.tariff_value,
        "unit": row.unit,
        "currency": row.currency,
        "valid_from": stamp(row.valid_from),
        "valid_to": stamp(row.valid_to),
        "gas_year": row.gas_year,
        "published_status": row.published_status,
        "source_url": row.source_url,
        "published_on": stamp(row.published_on),
        "source_location": row.source_location,
        "note": row.note,
        "recorded_by": row.recorded_by,
        "recorded_at_utc": stamp(row.recorded_at_utc),
        "reviewed_by": row.reviewed_by,
        "reviewed_at_utc": stamp(row.reviewed_at_utc),
        "closed_by": row.closed_by,
        "closed_at_utc": stamp(row.closed_at_utc),
        "closed_reason": row.closed_reason,
    }


def missing_legs(rows: list[dict], *, today: date, graph=None) -> list[dict[str, Any]]:
    """The legs the register cannot price this gas year, those blocking drawn routes first.

    One item per leg (operator, point, direction): which crossings it blocks, whether one of
    them is a drawn (representative) crossing, and whether it can be entered (an operator is
    named for it; "unknown TSO" cannot).
    """

    from eurogas_nexus.application.tariff_coverage import coverage_report, gas_year_start

    if graph is None:
        from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

        graph = shipped_market_area_graph()
    report = coverage_report(graph, rows, today=today)
    current = report["years"]["current"]
    legs: dict[tuple[str, str, str], dict[str, Any]] = {}
    for crossing in current["graph"]:
        if crossing["status"] == "priced":
            continue
        for leg in crossing["legs"]:
            if leg["held"]:
                continue
            key = (leg["point"], leg["tso"], leg["direction"])
            item = legs.setdefault(
                key,
                {
                    "kind": "crossing",
                    "point_key": leg["point"],
                    "point_name": leg["point_name"],
                    "tso": leg["tso"],
                    "direction": leg["direction"],
                    "role": leg["role"],
                    "can_be_entered": leg["can_be_entered"],
                    "why_not": None if leg["can_be_entered"] else "no operator named",
                    "blocks": [],
                    "drawn": False,
                },
            )
            item["blocks"].append(f"{crossing['from']} → {crossing['to']}")
            item["drawn"] = item["drawn"] or bool(crossing["representative"])
    for supply in current["supply"]:
        if supply["status"] == "held":
            continue
        legs[(supply["point"], "", "ENTRY")] = {
            "kind": supply["kind"],
            "point_key": supply["point"],
            "point_name": supply["via"],
            "tso": None,
            "direction": "ENTRY",
            "role": "supply_entry",
            "can_be_entered": bool(supply["can_be_entered"]),
            "why_not": None if supply["can_be_entered"] else "point not in the reference network",
            "blocks": [f"{supply['kind']} entry into {', '.join(supply['into'])}"],
            "drawn": False,
        }
    ordered = sorted(
        legs.values(),
        key=lambda item: (
            not item["can_be_entered"],
            not item["drawn"],
            item["kind"] != "crossing",
            -len(item["blocks"]),
            item["point_name"],
        ),
    )
    start = gas_year_start(max(today, gas_year_start(today)))
    for item in ordered:
        item["gas_year"] = f"{start.year}/{(start.year + 1) % 100:02d}"
    return ordered


def entries_view(session, *, today: date | None = None) -> dict[str, Any]:
    """The Admin view: legs that block routes first, then the entries and the pickers."""

    from eurogas_nexus.db.models import TsoTariffEntryRecord, TsoTariffRecord

    today = today or datetime.now(UTC).date()
    register = [
        {
            column: getattr(row, column)
            for column in (
                "tariff_id",
                "tso",
                "point_id",
                "direction",
                "gas_year",
                "tariff_value",
                "currency",
                "unit",
                "effective_from",
                "effective_to",
                "tariff_status",
                "source_table",
                "capacity_product",
                "firmness",
                "market_area",
            )
        }
        for row in session.query(TsoTariffRecord).all()
    ]
    entries = (
        session.query(TsoTariffEntryRecord)
        .order_by(TsoTariffEntryRecord.recorded_at_utc.desc())
        .all()
    )
    return {
        "missing": missing_legs(register, today=today),
        "entries": [entry_payload(row) for row in entries],
        "counts": {
            "candidate": sum(row.state == CANDIDATE for row in entries),
            "reviewed": sum(row.state == REVIEWED for row in entries),
            "retired": sum(row.state == RETIRED for row in entries),
        },
        "choices": reference_choices(),
    }
