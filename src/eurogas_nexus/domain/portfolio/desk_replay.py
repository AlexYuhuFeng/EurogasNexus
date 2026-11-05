"""Point-in-time evidence for one book, hub and gas day."""

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Annotated, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from eurogas_nexus.domain.market.gas_day import DEFAULT_GAS_DAY_CALENDAR, gas_day_start_for_date

Quantity = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Money = Annotated[Decimal, Field(allow_inf_nan=False)]
ZERO = Decimal(0)
ENGINE_VERSION = "desk-replay-v1"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    available_at: AwareDatetime
    source_ref: str = Field(min_length=1)


class Position(Evidence):
    resource_id: str = Field(min_length=1)
    kind: Literal["AVAILABLE", "COMMITMENT"]
    mwh: Quantity | None


class Outage(Evidence):
    resource_id: str = Field(min_length=1)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    unavailable_mw: Quantity


class Alternative(Evidence):
    resource_id: str = Field(min_length=1)
    kind: Literal["BUY_GAS", "CHANGE_ROUTE", "WITHDRAW_STORAGE"]
    quantity_mwh: Quantity
    cost_per_mwh: Money
    deadline: AwareDatetime
    right_confirmed: bool
    price_basis: Literal["EXECUTABLE", "CONFIRMED_COST", "INDICATIVE"]
    price_valid_until: AwareDatetime
    credit_per_mwh: Quantity | None = None


class DeskReplay(BaseModel):
    """Normalized evidence for the declared scope, supplied by the caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    book_id: str = Field(min_length=1)
    hub_id: str = Field(min_length=1)
    gas_day: date
    calendar: str = DEFAULT_GAS_DAY_CALENDAR
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: AwareDatetime
    positions: tuple[Position, ...]
    outages: tuple[Outage, ...] = ()
    alternatives: tuple[Alternative, ...] = ()


EvidenceRow = TypeVar("EvidenceRow", bound=Evidence)


def _visible(records: tuple[EvidenceRow, ...], cutoff: datetime) -> tuple[EvidenceRow, ...]:
    revisions: dict[tuple[str, int], EvidenceRow] = {}
    for record in records:
        if record.available_at > cutoff:
            continue
        key = record.record_id, record.revision
        if key in revisions and revisions[key] != record:
            raise ValueError(f"Conflicting evidence for {key}")
        revisions[key] = record
    latest = {key[0]: revisions[key] for key in sorted(revisions)}
    return tuple(latest.values())


def _outage_loss(outages: Iterable[Outage], start: datetime, end: datetime) -> Decimal:
    intervals = []
    for row in outages:
        if row.ends_at <= row.starts_at:
            raise ValueError(f"Invalid outage interval for {row.record_id}")
        left, right = max(start, row.starts_at), min(end, row.ends_at)
        if left < right:
            intervals.append((left, right, row.record_id, row.unavailable_mw))
    loss = ZERO
    previous_end = start
    for left, right, _, unavailable_mw in sorted(intervals):
        if left < previous_end:
            raise ValueError("Overlapping outage evidence requires upstream reconciliation")
        loss += unavailable_mw * Decimal(str((right - left).total_seconds())) / Decimal(3600)
        previous_end = right
    return loss


def _response(row: Alternative, gap: Decimal | None, as_of: datetime) -> dict:
    reasons = []
    if gap is None:
        reasons.append("GAP_UNKNOWN")
    if not row.right_confirmed:
        reasons.append("RIGHT_UNCONFIRMED")
    if min(row.deadline, row.price_valid_until) <= as_of:
        reasons.append("WINDOW_CLOSED")
    if row.price_basis == "INDICATIVE" or (
        row.kind == "BUY_GAS" and row.price_basis != "EXECUTABLE"
    ):
        reasons.append("PRICE_NOT_ACTIONABLE")
    if reasons:
        return {"record_id": row.record_id, "kind": row.kind, "blocked": reasons}
    assert gap is not None
    volume = min(row.quantity_mwh, gap)
    return {
        "record_id": row.record_id,
        "kind": row.kind,
        "quantity_mwh": volume,
        "remaining_gap_mwh": gap - volume,
        "incremental_cost": volume * row.cost_per_mwh,
        "incremental_credit": None if row.credit_per_mwh is None else volume * row.credit_per_mwh,
        "action_deadline": min(row.deadline, row.price_valid_until),
    }


def replay(request: DeskReplay) -> dict:
    """Freeze the visible revisions and compare independent responses to the same gap."""
    start = gas_day_start_for_date(request.gas_day, request.calendar)
    end = gas_day_start_for_date(request.gas_day + timedelta(days=1), request.calendar)
    frozen = request.model_copy(
        update={
            "positions": _visible(request.positions, request.as_of),
            "outages": _visible(request.outages, request.as_of),
            "alternatives": _visible(request.alternatives, request.as_of),
        }
    )
    resources = {row.resource_id for row in frozen.positions}
    unmatched = sorted(
        row.record_id
        for row in (*frozen.outages, *frozen.alternatives)
        if row.resource_id not in resources
    )
    results = []
    for resource in sorted(resources):
        positions = [row for row in frozen.positions if row.resource_id == resource]
        available = [row.mwh for row in positions if row.kind == "AVAILABLE"]
        committed = [row.mwh for row in positions if row.kind == "COMMITMENT"]
        if len(available) > 1:
            raise ValueError(f"Multiple availability records for {resource}")
        loss = _outage_loss(
            (row for row in frozen.outages if row.resource_id == resource), start, end
        )
        supply = available[0] if available else None
        obligation = (
            sum((value for value in committed if value is not None), ZERO)
            if committed and None not in committed
            else None
        )
        deliverable = None if supply is None else max(supply - loss, ZERO)
        remaining = gap = prior_gap = None
        if deliverable is not None and obligation is not None:
            remaining = max(deliverable - obligation, ZERO)
            gap = max(obligation - deliverable, ZERO)
            assert supply is not None
            prior_gap = max(obligation - supply, ZERO)
        results.append(
            {
                "resource_id": resource,
                "position_record_ids": [row.record_id for row in positions],
                "committed_mwh": obligation,
                "deliverable_mwh": deliverable,
                "outage_loss_mwh": loss,
                "remaining_mwh": remaining,
                "prior_gap_mwh": prior_gap,
                "keep_plan_gap_mwh": gap,
                "alternatives": [
                    _response(row, gap, frozen.as_of)
                    for row in frozen.alternatives
                    if row.resource_id == resource
                ],
            }
        )
    fingerprint = sha256(f"{ENGINE_VERSION}\n{frozen.model_dump_json()}".encode()).hexdigest()
    return {
        "engine_version": ENGINE_VERSION,
        "input_sha256": fingerprint,
        "frozen_inputs": frozen.model_dump(mode="json"),
        "delivery_start": start,
        "delivery_end": end,
        "unmatched_record_ids": unmatched,
        "resources": results,
    }
