"""What one caller may see: visibility, lanes, ranking, groups, cursors, readiness (B.5, B.7).

Visibility (no cross-book leak, the ``alert_scope`` rule): with portfolio isolation on, an
opportunity is shown only when the caller sees *every* book behind it; one with no book is
firm-level and shown only to a caller who sees every book. It is shown only when the caller
is entitled to every source family on its value path. A person's own dismissal hides a key
until the record's version moves on (a material change).

Pagination is by cursor over the complete ranked bucket; a cursor names the evaluation it
was cut from, and a newer evaluation makes it expire (409) rather than skip or repeat rows,
so nothing is silently truncated.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.opportunities.model import (
    TYPE_CODE,
    Lane,
    OpportunityState,
    OpportunityType,
    decimal_text,
)
from eurogas_nexus.domain.opportunities.ranking import RankInput, rank
from eurogas_nexus.domain.valuation.quality import CLASS_LABEL, InputClass

BUCKETS = ("must_act", "could_act", "market", "watching", "blocked")
MAX_PAGE = 50


class CursorError(ValueError):
    """A cursor from an older evaluation or not a cursor at all."""


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _num(value) -> str | None:
    return None if value is None else decimal_text(Decimal(str(value)))


def visible_to(row, allowed_books: set[str] | None, entitled) -> bool:
    """Book scope and entitlement for one record (``entitled(family) -> bool``)."""

    books = list(row.book_ids or [])
    # A market item carries no book (it needs no position); entitlement still applies.
    market = getattr(row, "lane", None) == Lane.MARKET.value
    if (
        not market
        and allowed_books is not None
        and (not books or any(b not in allowed_books for b in books))
    ):
        return False
    return all(entitled(family) for family in row.source_families or [])


#: The claim fields that name what an opportunity is about, per type (the grouping subject).
SUBJECT_FIELDS: dict[str, tuple[str, ...]] = {
    "hedge_gap": ("contract",),
    "event_exposure": ("asset", "contract"),
    "locational": ("buy_hub", "sell_hub"),
    "unused_capacity": ("buy_hub", "sell_hub"),
    "time_spread": ("hub", "where"),
    "sell_down": ("hub", "side"),
    "reroute": ("resource", "option"),
    "prompt_arbitrage": ("hub", "sell", "buy"),
}


def subject_of(row) -> str:
    """What the record is about, in words: "Haldor supply (Easington)", "TTF → THE"."""

    fields = dict(row.claim_fields or {})
    names = SUBJECT_FIELDS.get(row.type, ())
    parts = [str(fields.get(name) or "").strip() for name in names]
    parts = [part for part in parts if part]
    if row.type in {"locational", "unused_capacity"} and len(parts) == 2:
        return f"{parts[0]} → {parts[1]}"
    return " · ".join(parts) or str(fields.get("subject") or row.type)


def grouped(items: list[dict]) -> list[dict]:
    """One item per (type, subject), in the order of its best-ranked member (design polish:
    one opportunity per subject, not per month). Each keeps its lead's fields and gains
    ``group``: the members largest first, their count and totals."""

    order: list[tuple[str, str]] = []
    members: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        key = (item["type"], item["subject"])
        if key not in members:
            order.append(key)
            members[key] = []
        members[key].append(item)

    def size(item: dict) -> Decimal:
        value = (item.get("value") or {}).get("amount")
        volume = (item.get("volume") or {}).get("value")
        headline = (item.get("headline") or {}).get("value")
        return abs(Decimal(value or volume or headline or "0"))

    out = []
    for key in order:
        rows = members[key]
        lead = rows[0]
        largest = sorted(rows, key=size, reverse=True)
        currencies = {(r.get("value") or {}).get("currency") for r in rows if r.get("value")}
        volume_units = {(r.get("volume") or {}).get("unit") for r in rows if r.get("volume")}
        total_value = (
            sum(Decimal((r.get("value") or {}).get("amount") or "0") for r in rows)
            if len(currencies) == 1
            else None
        )
        total_volume = (
            sum(Decimal((r.get("volume") or {}).get("value") or "0") for r in rows)
            if len(volume_units) == 1
            else None
        )
        out.append(
            {
                **lead,
                "group": {
                    "count": len(rows),
                    "members": [
                        {
                            "opportunity_id": r["opportunity_id"],
                            "period": r["period"],
                            "period_start": r["period_start"],
                            "headline": r["headline"],
                            "value": r["value"],
                            "volume": r["volume"],
                            "state": r["state"],
                            "deadline_utc": r["deadline_utc"],
                            "expires_at_utc": r["expires_at_utc"],
                        }
                        for r in largest
                    ],
                    "total_value": None
                    if total_value is None
                    else {"amount": decimal_text(total_value), "currency": next(iter(currencies))},
                    "total_volume": None
                    if total_volume is None
                    else {"value": decimal_text(total_volume), "unit": next(iter(volume_units))},
                },
            }
        )
    return out


def summary(row, *, user_state: dict | None = None, ranked=None) -> dict[str, Any]:
    """One record as a list row."""

    quality = InputClass(row.quality_class)
    return {
        "opportunity_id": row.opportunity_id,
        "key": row.opp_key,
        "type": row.type,
        "type_code": TYPE_CODE[OpportunityType(row.type)],
        "lane": row.lane,
        "state": row.state,
        "claim": row.claim_text,
        "headline": {"value": _num(row.headline_value), "unit": row.headline_unit},
        "value": None
        if row.value_amount is None
        else {"amount": _num(row.value_amount), "currency": row.value_currency},
        "volume": None
        if row.volume_value is None
        else {"value": _num(row.volume_value), "unit": row.volume_unit},
        "period": row.period_label,
        "quality": {"class": quality.value, "label": CLASS_LABEL[quality]},
        "simulated": row.simulated,
        "book_ids": list(row.book_ids or []),
        "expires_at_utc": _aware(row.expires_at_utc).isoformat(),
        "deadline_utc": _aware(row.deadline_utc).isoformat() if row.deadline_utc else None,
        "version": row.version,
        "first_seen_utc": _aware(row.first_seen_utc).isoformat(),
        "last_evaluated_utc": _aware(row.last_evaluated_utc).isoformat(),
        "reasons": list(row.reasons or []),
        "blocked": row.blocker_json,
        "rank": None if ranked is None else {"position": ranked.position, "reason": ranked.reason},
        "user_state": user_state,
        "subject": subject_of(row),
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if getattr(row, "period_end", None) else None,
    }


def _rank_input(row) -> RankInput:
    size = row.volume_value if row.lane == Lane.MUST_ACT.value else row.reporting_value
    return RankInput(
        opportunity_id=row.opportunity_id,
        lane=Lane(row.lane),
        quality=InputClass(row.quality_class),
        simulated=row.simulated,
        consecutive_seen=row.consecutive_seen,
        expires_at_utc=_aware(row.expires_at_utc),
        deadline_utc=_aware(row.deadline_utc),
        value_eur=None if row.reporting_value is None else Decimal(str(row.reporting_value)),
        size=abs(Decimal(str(size if size is not None else row.headline_value))),
        size_unit=row.volume_unit or row.headline_unit,
    )


def encode_cursor(bucket: str, offset: int, evaluation_id: str | None) -> str:
    """Opaque cursor text."""

    raw = json.dumps({"b": bucket, "o": offset, "e": evaluation_id}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str, evaluation_id: str | None) -> tuple[str, int]:
    """``(bucket, offset)``.

    Raises:
        CursorError: not a cursor, or cut from an older evaluation.
    """

    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        bucket, offset, cut = str(data["b"]), int(data["o"]), data.get("e")
    except Exception as exc:  # noqa: BLE001 - any malformed cursor is the same refusal
        raise CursorError("cursor_invalid") from exc
    if bucket not in BUCKETS or offset < 0:
        raise CursorError("cursor_invalid")
    if cut != evaluation_id:
        raise CursorError("cursor_expired")
    return bucket, offset


def _page(rows: list, bucket: str, offset: int, limit: int, evaluation_id: str | None):
    page = rows[offset : offset + limit]
    end = offset + len(page)
    return {
        "total": len(rows),
        "offset": offset,
        "items": page,
        "next_cursor": encode_cursor(bucket, end, evaluation_id) if end < len(rows) else None,
    }


def _next_run(session) -> dict[str, Any]:
    """When the next scheduled evaluation runs: on the next scheduler tick when inputs are
    pending (after the debounce), else when an input changes."""

    from eurogas_nexus.application.opportunities.schedule import DEBOUNCE, last_scheduled_start
    from eurogas_nexus.db.models import OpportunityPendingInputRecord

    pending = sorted(row.input_class for row in session.query(OpportunityPendingInputRecord))
    last = last_scheduled_start(session)
    return {
        "pending_inputs": pending,
        "last_scheduled_utc": None if last is None else _aware(last).isoformat(),
        "not_before_utc": None
        if not pending or last is None
        else (_aware(last) + DEBOUNCE).isoformat(),
    }


def latest_evaluation(session):
    """The most recent finished evaluation row, or ``None``."""

    from eurogas_nexus.db.models import OpportunityEvaluationRecord

    return (
        session.query(OpportunityEvaluationRecord)
        .filter(OpportunityEvaluationRecord.finished_at_utc.is_not(None))
        .order_by(OpportunityEvaluationRecord.started_at_utc.desc())
        .first()
    )


def visible_records(session, principal) -> list:
    """Every live record the caller may see (book scope, entitlement)."""

    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models import OpportunityRecord
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    allowed = visible_book_ids(session)
    rows = (
        session.query(OpportunityRecord)
        .filter(
            OpportunityRecord.state.notin_(
                [OpportunityState.EXPIRED.value, OpportunityState.CONVERTED.value]
            )
        )
        .all()
    )
    return [
        row
        for row in rows
        if visible_to(row, allowed, lambda family: row_allowed(principal, family))
    ]


def user_states(session, principal_id: str | None, keys: Iterable[str]) -> dict[str, Any]:
    """The caller's dismissals and follows by key."""

    from eurogas_nexus.db.models import OpportunityUserStateRecord

    if not principal_id:
        return {}
    keys = list(keys)
    if not keys:
        return {}
    return {
        row.opp_key: row
        for row in session.query(OpportunityUserStateRecord)
        .filter(OpportunityUserStateRecord.principal_id == principal_id)
        .filter(OpportunityUserStateRecord.opp_key.in_(keys))
        .all()
    }


def _user_view(state_row, record) -> dict | None:
    if state_row is None:
        return None
    return {
        "state": state_row.state,
        "reason": state_row.reason_code,
        "at_version": state_row.at_version,
        "changed_since": record.version != state_row.at_version,
    }


def list_opportunities(
    session,
    principal,
    *,
    lane: str | None = None,
    group: str | None = None,
    opportunity_type: str | None = None,
    book_id: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    thresholds=None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """The caller's list: two lanes, the watching and blocked groups, counts, readiness.

    Raises:
        CursorError: ``cursor_invalid`` or ``cursor_expired``.
    """

    from eurogas_nexus.application.opportunities.settings import load_thresholds

    now = now_utc or datetime.now(UTC)
    settings = thresholds or load_thresholds(session)
    evaluation = latest_evaluation(session)
    evaluation_id = evaluation.evaluation_id if evaluation else None
    rows = visible_records(session, principal)
    if opportunity_type:
        rows = [row for row in rows if row.type == opportunity_type]
    if book_id:
        rows = [row for row in rows if book_id in (row.book_ids or [])]
    mine = user_states(session, getattr(principal, "principal_id", None), [r.opp_key for r in rows])
    hidden = 0
    shown = []
    for row in rows:
        state_row = mine.get(row.opp_key)
        if (
            state_row is not None
            and state_row.state == "dismissed"
            and (state_row.at_version == row.version)
        ):
            hidden += 1
            continue
        shown.append(row)
    confirming = [row for row in shown if row.state == OpportunityState.NEW.value]
    listed = [
        row
        for row in shown
        if row.state in {OpportunityState.ACTIONABLE.value, OpportunityState.INDICATIVE.value}
        # A market item always says what the firm would need: it is listed while watched.
        or (row.lane == Lane.MARKET.value and row.state == OpportunityState.WATCH.value)
    ]
    buckets: dict[str, list[dict]] = {}
    for lane_name in (Lane.MUST_ACT.value, Lane.COULD_ACT.value, Lane.MARKET.value):
        members = [row for row in listed if row.lane == lane_name]
        ranked = {
            item.opportunity_id: item for item in rank([_rank_input(r) for r in members], now)
        }
        members.sort(key=lambda r: ranked[r.opportunity_id].position)
        buckets[lane_name] = [
            summary(
                r, user_state=_user_view(mine.get(r.opp_key), r), ranked=ranked[r.opportunity_id]
            )
            for r in members
        ]
    for group_name, state in (
        ("watching", OpportunityState.WATCH),
        ("blocked", OpportunityState.BLOCKED),
    ):
        members = sorted(
            (row for row in shown if row.state == state.value and row.lane != Lane.MARKET.value),
            key=lambda r: (_aware(r.expires_at_utc), r.opportunity_id),
        )
        buckets[group_name] = [
            summary(r, user_state=_user_view(mine.get(r.opp_key), r)) for r in members
        ]
    # One item per subject: the lane shows at most seven subjects and counts subjects.
    buckets = {name: grouped(items) for name, items in buckets.items()}
    page_size = max(1, min(limit or settings.max_per_lane, MAX_PAGE))
    if cursor:
        bucket, offset = decode_cursor(cursor, evaluation_id)
        selected = {bucket: _page(buckets[bucket], bucket, offset, page_size, evaluation_id)}
    else:
        wanted = [name for name in BUCKETS if name in {lane, group}] or list(BUCKETS)
        selected = {
            name: _page(buckets[name], name, 0, page_size, evaluation_id) for name in wanted
        }
    simulated = any(item["simulated"] for items in buckets.values() for item in items)
    return {
        "as_of_utc": None if evaluation is None else _aware(evaluation.as_of_utc).isoformat(),
        "evaluation": None
        if evaluation is None
        else {
            "evaluation_id": evaluation.evaluation_id,
            "status": evaluation.status,
            "finished_at_utc": _aware(evaluation.finished_at_utc).isoformat(),
            "demo_desk": evaluation.demo_desk,
            # What started it: "schedule" (inputs changed, CP-13) or "on_demand" (a person).
            "trigger": evaluation.trigger,
            "next": _next_run(session),
        },
        "lanes": {
            name: selected[name] for name in ("must_act", "could_act", "market") if name in selected
        },
        "groups": {name: selected[name] for name in ("watching", "blocked") if name in selected},
        "confirming": len(confirming),
        "hidden_by_you": hidden,
        "per_lane_shown": settings.max_per_lane,
        "simulated": simulated,
        "banner": "Demo desk: every figure here is computed from simulated data."
        if simulated
        else None,
        "readiness": readiness(session, principal),
    }


def readiness(session, principal) -> dict[str, Any]:
    """The day-one checklist (B.7): book, prices, published costs, assumptions."""

    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models import (
        AssumptionSetVersionRecord,
        FirmMarkRecord,
        HedgeApprovalRecord,
        LngTerminalTermsRecord,
        MarketObservationRecord,
        MarketQuoteRecord,
        TsoTariffRecord,
        UpstreamResourceContractRecord,
    )
    from eurogas_nexus.security.portfolio_scope import restrict

    contracts = (
        restrict(
            session.query(UpstreamResourceContractRecord),
            UpstreamResourceContractRecord,
            session,
        )
        .filter(UpstreamResourceContractRecord.retired_at_utc.is_(None))
        .count()
    )
    bands = session.query(HedgeApprovalRecord).count()
    quote_sources = [
        source
        for (source,) in session.query(MarketQuoteRecord.source_system)
        .filter(MarketQuoteRecord.simulated.is_(False))
        .distinct()
        .all()
        if not source.endswith("_Sim") and row_allowed(principal, source)
    ]
    # Only prices per unit of energy count (FX and other series share the table).
    from sqlalchemy import func, or_

    settlement_sources = [
        source
        for (source,) in session.query(MarketObservationRecord.source_system)
        .filter(
            or_(
                func.upper(MarketObservationRecord.unit).like("%MWH%"),
                func.upper(MarketObservationRecord.unit).like("%/TH%"),
                func.upper(MarketObservationRecord.unit).like("%THERM%"),
            )
        )
        .distinct()
        .all()
        if not source.endswith("_Sim") and source != "DEMO" and row_allowed(principal, source)
    ]
    marks = session.query(FirmMarkRecord).filter(FirmMarkRecord.superseded_at_utc.is_(None)).count()
    tariffs = (
        session.query(TsoTariffRecord)
        .filter(TsoTariffRecord.tariff_status.in_(["FINAL", "INDICATIVE"]))
        .count()
    )
    terminals = session.query(LngTerminalTermsRecord).count()
    approved = (
        session.query(AssumptionSetVersionRecord)
        .filter(AssumptionSetVersionRecord.review_state == "approved")
        .count()
    )
    prices_ready = bool(quote_sources or settlement_sources or marks)
    return {
        "book": {
            "ready": contracts > 0,
            "contracts": contracts,
            "approved_hedge_bands": bands,
            "missing": None if contracts else "no contracts in your books",
        },
        "prices": {
            "ready": prices_ready,
            "licensed_quote_sources": sorted(quote_sources),
            "settlement_sources": sorted(settlement_sources),
            "firm_marks": marks,
            "missing": None
            if prices_ready
            else "no licensed quotes or marks: needs a price entitlement or the firm's marks",
        },
        "published_costs": {
            "ready": tariffs > 0,
            "transport_tariffs": tariffs,
            "terminal_terms": terminals,
            "missing": None if tariffs else "no published transport tariffs held",
        },
        "assumptions": {
            "ready": approved > 0,
            "approved_versions": approved,
            "missing": None if approved else "no approved assumption set",
        },
        "types_now": ["hedge_gap"] if contracts and bands else [],
    }


def detail(session, principal, opportunity_id: str) -> dict[str, Any] | None:
    """The full object (legs, assumptions, falsifiers, sensitivity, checks, quality), its
    snapshot record, its versions and the caller's own state; ``None`` when not visible."""

    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models import OpportunityRecord, OpportunityVersionRecord
    from eurogas_nexus.db.repositories.commercial_assumptions import load_snapshot
    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    row = session.get(OpportunityRecord, opportunity_id)
    if row is None or not visible_to(
        row, visible_book_ids(session), lambda family: row_allowed(principal, family)
    ):
        return None
    version = session.get(OpportunityVersionRecord, (row.opportunity_id, row.version))
    versions = [
        {
            "version": item.version,
            "state": item.state,
            "snapshot_id": item.snapshot_id,
            "recorded_at_utc": _aware(item.recorded_at_utc).isoformat(),
        }
        for item in session.query(OpportunityVersionRecord)
        .filter(OpportunityVersionRecord.opportunity_id == row.opportunity_id)
        .order_by(OpportunityVersionRecord.version)
        .all()
    ]
    snapshot = load_snapshot(session, row.snapshot_id)
    mine = user_states(session, getattr(principal, "principal_id", None), [row.opp_key])
    return {
        **summary(row, user_state=_user_view(mine.get(row.opp_key), row)),
        "object": None if version is None else version.payload_json,
        "snapshot": None if snapshot is None else snapshot[0],
        "versions": versions,
        "case": None
        if row.case_id is None
        else {
            "case_id": row.case_id,
            "converted_by": row.converted_by,
            "converted_at_utc": _aware(row.converted_at_utc).isoformat(),
        },
        "ended_reason": row.ended_reason,
        "next_steps": ["open_as_case", "watch", "dismiss"]
        if row.state not in {"blocked", "converted", "expired"}
        else ["watch", "dismiss"]
        if row.state == "blocked"
        else [],
    }
