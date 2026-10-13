"""Target-aware evidence selection for the CR-04 backtest engine/2.

This module is the single pure implementation of *target-aware* historical
evidence selection. It resolves each declared per-leg target interval
independently of whichever quotes happen to exist, then admits only rows whose
declared name, hub, tenor, quotation basis, evidence role and exact half-open
delivery interval match, whose availability is at or before the decision time,
and which satisfy the run's declared ``fill_price_policy``.

It is deliberately browser-, SQLAlchemy- and application-free so the rules can
be asserted directly and reused by the engine only. Local timezone arithmetic is
never used: rolling gas-day targets are resolved through
``eurogas_nexus.domain.market.gas_day`` exclusively.

The engine/1 helper ``temporal.as_of_price_observations`` is *not* called here;
the target path never falls back to the legacy name-only selection. Only the
shared ``temporal.matches_fill_policy`` predicate is reused, so the declared
fill policy means exactly the same thing in both selection paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.backtest.contracts import (
    BacktestEconomicAssumptions,
    BacktestEvidencePool,
    BacktestObservation,
)
from eurogas_nexus.domain.backtest.temporal import matches_fill_policy
from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date
from eurogas_nexus.domain.ontology.vocabulary import (
    FillPricePolicy,
    MissingDataPolicy,
    StrategyEvidenceTargetBasis,
    StrategyEvidenceTargetRole,
    TemporalIntegrityStatus,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyEvidenceTarget,
    StrategyVersionDefinition,
)

#: Version of the target-aware selection rules. Persisted (and therefore hashed)
#: in the run manifest so a later rule change is visible rather than silent.
TARGET_SELECTION_RULES_VERSION = "target-evidence-selection/v1"

#: Which declared price names each known strategy component requires evidence
#: for. This is the existing evidence contract of the engine, not a new rule.
COMPONENT_REQUIRED_PRICE_NAME_KEYS: dict[str, tuple[str, ...]] = {
    "OCM_VS_DAY_AHEAD": ("day_ahead_price_names", "intraday_price_names"),
}

# Stable, machine-readable per-leg selection reason codes.
REASON_TARGET_NOT_DECLARED = "EVIDENCE_TARGET_NOT_DECLARED"
REASON_DELIVERY_TARGET_EXPIRED = "DELIVERY_TARGET_EXPIRED"
REASON_REFERENCE_VALIDITY_MISSED = "REFERENCE_VALIDITY_NOT_CONTAINING_DECISION"
REASON_INTERVAL_MISSING = "DELIVERY_INTERVAL_MISSING"
REASON_INTERVAL_MISMATCH = "DELIVERY_INTERVAL_MISMATCH"
REASON_ROLE_UNKNOWN = "EVIDENCE_ROLE_UNKNOWN"
REASON_ROLE_MISMATCH = "EVIDENCE_ROLE_MISMATCH"
REASON_BASIS_UNKNOWN = "PRICE_BASIS_UNKNOWN"
REASON_BASIS_MISMATCH = "PRICE_BASIS_MISMATCH"
REASON_HUB_MISMATCH = "HUB_MISMATCH"
REASON_TENOR_MISMATCH = "TENOR_MISMATCH"
REASON_AVAILABILITY = "AVAILABILITY_AFTER_DECISION"
REASON_PROVENANCE = "TEMPORAL_PROVENANCE_INSUFFICIENT"
REASON_MISSING_SERIES = "MISSING_PRICE_SERIES"
REASON_FILL_POLICY_MISMATCH = "FILL_PRICE_POLICY_MISMATCH"
REASON_FALLBACK_NOT_CONFIGURED = "FALLBACK_SOURCE_NOT_CONFIGURED"
REASON_FALLBACK_MISSING = "FALLBACK_SOURCE_MISSING"
REASON_CARRY_AGE = "CARRY_FORWARD_MAX_AGE_EXCEEDED"

_SKIP_DECISION = "SKIP_DECISION:MISSING_PRICE_SERIES"


@dataclass(frozen=True)
class ResolvedTargetInterval:
    """The half-open UTC interval one declared leg resolves to at decision T."""

    start_utc: datetime
    end_utc: datetime

    def contains(self, instant: datetime) -> bool:
        return self.start_utc <= instant < self.end_utc


@dataclass(frozen=True)
class LegEvidenceSelection:
    """Outcome of selecting evidence for exactly one declared price name."""

    price_name: str
    leg_id: str | None
    rows: tuple[BacktestObservation, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    trace: dict[str, Any]


@dataclass(frozen=True)
class ComponentTargetSelection:
    """Outcome of selecting evidence for one component's required price names."""

    rows: tuple[BacktestObservation, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    leg_traces: tuple[dict[str, Any], ...]


def required_price_names(component: StrategyComponentSpec) -> list[str]:
    """Return the price names this component already consumes, in order."""

    keys = COMPONENT_REQUIRED_PRICE_NAME_KEYS.get(component.component_type)
    if keys is None:
        return []
    extension = component.extension_json or {}
    names: list[str] = []
    for key in keys:
        value = extension.get(key)
        if not isinstance(value, list):
            continue
        for name in value:
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return names


def declared_leg_for_name(
    component: StrategyComponentSpec, price_name: str
) -> StrategyEvidenceTarget | None:
    """Return the declared leg that owns one price name, or ``None``."""

    wanted = price_name.upper()
    for target in component.evidence_targets or []:
        if any(name.upper() == wanted for name in target.price_names):
            return target
    return None


def component_declaration_gaps(component: StrategyComponentSpec) -> list[str]:
    """Return the required price names this component declares no target for."""

    required = required_price_names(component)
    return sorted(
        {name for name in required if declared_leg_for_name(component, name) is None}
    )


def resolve_target_interval(
    target: StrategyEvidenceTarget, decision_time_utc: datetime
) -> ResolvedTargetInterval:
    """Resolve one declared leg's half-open interval at decision time ``T``.

    ``GAS_DAY`` resolves the gas-day label at ``T`` with the declared canonical
    calendar, offsets the *calendar date*, then asks the gas-day module for that
    date's start and the following date's start. It never adds 24 hours, so the
    23/25-hour DST days are correct.
    """

    decision = _as_utc(decision_time_utc)
    if target.target_basis == StrategyEvidenceTargetBasis.GAS_DAY:
        calendar = target.calendar_id
        assert calendar is not None  # schema guarantees this for GAS_DAY
        offset = target.gas_day_offset
        assert offset in {0, 1}
        label = gas_day_label(decision, calendar=calendar)
        target_date = date.fromisoformat(label) + timedelta(days=offset)
        start = gas_day_start_for_date(target_date, calendar=calendar)
        end = gas_day_start_for_date(target_date + timedelta(days=1), calendar=calendar)
        return ResolvedTargetInterval(start_utc=start, end_utc=end)
    start = target.delivery_start_utc
    end = target.delivery_end_utc
    assert start is not None and end is not None  # schema guarantees this
    return ResolvedTargetInterval(start_utc=_as_utc(start), end_utc=_as_utc(end))


def select_component_target_evidence(
    *,
    pool: BacktestEvidencePool,
    component: StrategyComponentSpec,
    assumptions: BacktestEconomicAssumptions,
    decision_time_utc: datetime,
) -> ComponentTargetSelection:
    """Select target-admissible evidence for every required price name."""

    decision = _as_utc(decision_time_utc)
    required = required_price_names(component)
    if not required:
        return ComponentTargetSelection(
            rows=(),
            warnings=(),
            blockers=(
                f"COMPONENT_EVIDENCE_KEYS_UNMAPPED:{component.component_type}",
            ),
            leg_traces=(),
        )

    rows: list[BacktestObservation] = []
    warnings: list[str] = []
    blockers: list[str] = []
    traces: list[dict[str, Any]] = []
    for name in required:
        outcome = _select_one_leg(
            pool=pool,
            component=component,
            price_name=name,
            assumptions=assumptions,
            decision=decision,
        )
        rows.extend(outcome.rows)
        warnings.extend(outcome.warnings)
        blockers.extend(outcome.blockers)
        traces.append(outcome.trace)
    return ComponentTargetSelection(
        rows=tuple(rows),
        warnings=tuple(warnings),
        blockers=tuple(blockers),
        leg_traces=tuple(traces),
    )


def _select_one_leg(
    *,
    pool: BacktestEvidencePool,
    component: StrategyComponentSpec,
    price_name: str,
    assumptions: BacktestEconomicAssumptions,
    decision: datetime,
) -> LegEvidenceSelection:
    target = declared_leg_for_name(component, price_name)
    if target is None:
        return _rejected(
            price_name,
            leg_id=None,
            reason=REASON_TARGET_NOT_DECLARED,
            blockers=(f"{REASON_TARGET_NOT_DECLARED}:{price_name}",),
        )

    interval = resolve_target_interval(target, decision)
    base_trace = _base_trace(target, price_name, interval, decision)
    base_trace["fill_price_policy"] = assumptions.fill_price_policy.value

    role_blocker = _role_validity_blocker(target, interval, decision)
    if role_blocker is not None:
        base_trace["reason"] = role_blocker
        return LegEvidenceSelection(
            price_name=price_name,
            leg_id=target.leg_id,
            rows=(),
            warnings=(),
            blockers=(f"{role_blocker}:{price_name}",),
            trace=base_trace,
        )

    matching = [
        row
        for row in pool.observations
        if row.price_name.upper() == price_name.upper()
        and _reject_row(
            row,
            target=target,
            interval=interval,
            fill_price_policy=assumptions.fill_price_policy,
        )
        is None
    ]
    primary = [row for row in matching if _available_at(row) <= decision]

    if primary:
        chosen = _latest(primary)
        if assumptions.missing_data_policy == MissingDataPolicy.CARRY_FORWARD_WITH_MAX_AGE:
            # Exact comparison: truncating to whole seconds would admit an age
            # of max + 0.9s, and an incomplete second is still too old.
            age = decision - _as_utc(chosen.observed_at_utc)
            if age > timedelta(seconds=assumptions.carry_forward_max_age_seconds):
                displayed_age = _format_age_seconds(age)
                base_trace["reason"] = REASON_CARRY_AGE
                base_trace["carry_forward_age_seconds"] = age.total_seconds()
                base_trace["carry_forward_age_display"] = displayed_age
                return LegEvidenceSelection(
                    price_name=price_name,
                    leg_id=target.leg_id,
                    rows=(),
                    warnings=(),
                    blockers=(
                        f"{REASON_CARRY_AGE}:{price_name}:{displayed_age}s",
                    ),
                    trace=base_trace,
                )
        _mark_matched(base_trace, chosen, decision, path="PRIMARY")
        return LegEvidenceSelection(
            price_name=price_name,
            leg_id=target.leg_id,
            rows=(chosen,),
            warnings=(),
            blockers=(),
            trace=base_trace,
        )

    return _missing_leg(
        pool=pool,
        target=target,
        price_name=price_name,
        assumptions=assumptions,
        decision=decision,
        interval=interval,
        base_trace=base_trace,
    )


def _missing_leg(
    *,
    pool: BacktestEvidencePool,
    target: StrategyEvidenceTarget,
    price_name: str,
    assumptions: BacktestEconomicAssumptions,
    decision: datetime,
    interval: ResolvedTargetInterval,
    base_trace: dict[str, Any],
) -> LegEvidenceSelection:
    policy = assumptions.missing_data_policy
    base_trace["rejected_reasons"] = _reject_reason_counts(
        pool,
        target=target,
        interval=interval,
        decision=decision,
        fill_price_policy=assumptions.fill_price_policy,
    )
    if policy == MissingDataPolicy.SKIP_DECISION:
        base_trace["reason"] = "SKIP_DECISION"
        return LegEvidenceSelection(
            price_name=price_name,
            leg_id=target.leg_id,
            rows=(),
            warnings=(),
            blockers=(_SKIP_DECISION,),
            trace=base_trace,
        )
    if policy == MissingDataPolicy.USE_APPROVED_FALLBACK_SOURCE:
        return _fallback_leg(
            pool=pool,
            target=target,
            price_name=price_name,
            assumptions=assumptions,
            decision=decision,
            interval=interval,
            base_trace=base_trace,
        )
    # FAIL and CARRY_FORWARD_WITH_MAX_AGE are equally honest here: with an exact
    # resolved interval there is no admissible same-target row at all, and an
    # older row for a *different* delivery interval is a different product that
    # must never stand in for the declared target.
    base_trace["reason"] = REASON_MISSING_SERIES
    return LegEvidenceSelection(
        price_name=price_name,
        leg_id=target.leg_id,
        rows=(),
        warnings=(),
        blockers=(f"{REASON_MISSING_SERIES}:{price_name}",),
        trace=base_trace,
    )


def _fallback_leg(
    *,
    pool: BacktestEvidencePool,
    target: StrategyEvidenceTarget,
    price_name: str,
    assumptions: BacktestEconomicAssumptions,
    decision: datetime,
    interval: ResolvedTargetInterval,
    base_trace: dict[str, Any],
) -> LegEvidenceSelection:
    fallback = assumptions.fallback_sources.get(price_name)
    if not fallback:
        base_trace["reason"] = REASON_FALLBACK_NOT_CONFIGURED
        return LegEvidenceSelection(
            price_name=price_name,
            leg_id=target.leg_id,
            rows=(),
            warnings=(),
            blockers=(f"{REASON_FALLBACK_NOT_CONFIGURED}:{price_name}",),
            trace=base_trace,
        )
    wanted_source = fallback.upper()
    candidates = [
        row
        for row in pool.observations
        if (
            row.source_system.upper() == wanted_source
            or row.price_name.upper() == wanted_source
        )
        and _reject_row(
            row,
            target=target,
            interval=interval,
            fill_price_policy=assumptions.fill_price_policy,
        )
        is None
        and _available_at(row) <= decision
    ]
    if not candidates:
        base_trace["reason"] = REASON_FALLBACK_MISSING
        return LegEvidenceSelection(
            price_name=price_name,
            leg_id=target.leg_id,
            rows=(),
            warnings=(),
            blockers=(f"{REASON_FALLBACK_MISSING}:{price_name}",),
            trace=base_trace,
        )
    chosen = _latest(candidates)
    renamed = chosen.model_copy(
        update={
            "price_name": price_name,
            "source_reference": f"fallback:{fallback}->{price_name}:{chosen.source_reference}",
        }
    )
    _mark_matched(base_trace, renamed, decision, path="FALLBACK")
    base_trace["fallback_source"] = fallback
    return LegEvidenceSelection(
        price_name=price_name,
        leg_id=target.leg_id,
        rows=(renamed,),
        warnings=(f"SOURCE_FALLBACK_USED:{price_name}",),
        blockers=(),
        trace=base_trace,
    )


def _role_validity_blocker(
    target: StrategyEvidenceTarget,
    interval: ResolvedTargetInterval,
    decision: datetime,
) -> str | None:
    if target.role == StrategyEvidenceTargetRole.DELIVERY_PRICE:
        # An expired delivery target cannot stand in for a current deliverable
        # valuation. A target that starts after T is legitimate (day-ahead /
        # forward), so delivery start is deliberately not compared with T.
        if decision >= interval.end_utc:
            return REASON_DELIVERY_TARGET_EXPIRED
        return None
    # A reference level's declared validity must contain the decision instant.
    if not interval.contains(decision):
        return REASON_REFERENCE_VALIDITY_MISSED
    return None


def _reject_row(
    row: BacktestObservation,
    *,
    target: StrategyEvidenceTarget,
    interval: ResolvedTargetInterval,
    fill_price_policy: FillPricePolicy,
) -> str | None:
    """Return the first reason this row cannot serve the declared target.

    The declared product identity is checked before the run's declared fill
    policy: a conflict between the two blocks the leg rather than selecting a
    different quotation basis. ``NEXT_ELIGIBLE`` stays permissive exactly as the
    engine/1 contract defines it.
    """

    if row.temporal_integrity == TemporalIntegrityStatus.INSUFFICIENT:
        return REASON_PROVENANCE
    if row.delivery_start_utc is None or row.delivery_end_utc is None:
        return REASON_INTERVAL_MISSING
    if (
        _as_utc(row.delivery_start_utc) != interval.start_utc
        or _as_utc(row.delivery_end_utc) != interval.end_utc
    ):
        return REASON_INTERVAL_MISMATCH
    if row.evidence_role is None:
        return REASON_ROLE_UNKNOWN
    if row.evidence_role.upper() != target.role.value.upper():
        return REASON_ROLE_MISMATCH
    if row.price_basis is None:
        return REASON_BASIS_UNKNOWN
    if row.price_basis.strip().upper() != target.price_basis.strip().upper():
        return REASON_BASIS_MISMATCH
    if row.hub.strip().upper() != target.hub.strip().upper():
        return REASON_HUB_MISMATCH
    if row.tenor.strip().lower() != target.tenor.strip().lower():
        return REASON_TENOR_MISMATCH
    if not matches_fill_policy(row, fill_price_policy):
        return REASON_FILL_POLICY_MISMATCH
    return None


def _reject_reason_counts(
    pool: BacktestEvidencePool,
    *,
    target: StrategyEvidenceTarget,
    interval: ResolvedTargetInterval,
    decision: datetime,
    fill_price_policy: FillPricePolicy,
) -> dict[str, int]:
    """Diagnose why the declared leg has no admissible row.

    Only rows that could plausibly serve the leg (matching the declared price
    names) are classified, plus an availability classification for rows that
    pass every other criterion but were observed after ``T``.
    """

    names = {name.upper() for name in target.price_names}
    counts: dict[str, int] = {}
    for row in pool.observations:
        if row.price_name.upper() not in names:
            continue
        reason = _reject_row(
            row,
            target=target,
            interval=interval,
            fill_price_policy=fill_price_policy,
        )
        if reason is None and _available_at(row) > decision:
            reason = REASON_AVAILABILITY
        if reason is None:
            continue
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def target_declarations_for_manifest(
    definition: StrategyVersionDefinition,
) -> list[dict[str, Any]]:
    """Return the frozen declarations carried by a parsed definition."""

    declarations: list[dict[str, Any]] = []
    for component in definition.components:
        for target in component.evidence_targets or []:
            payload = target.model_dump(mode="json")
            payload["component_id"] = component.component_id
            declarations.append(payload)
    return declarations


def selection_rules_block(
    *,
    definition: StrategyVersionDefinition,
    assumptions: BacktestEconomicAssumptions,
) -> dict[str, Any]:
    """The deterministic evidence-selection block hashed into the manifest."""

    return {
        "rules_version": TARGET_SELECTION_RULES_VERSION,
        "target_declarations": target_declarations_for_manifest(definition),
        "carry_forward_max_age_seconds": assumptions.carry_forward_max_age_seconds,
        "missing_data_policy": assumptions.missing_data_policy.value,
        "fill_price_policy": assumptions.fill_price_policy.value,
    }


def _base_trace(
    target: StrategyEvidenceTarget,
    price_name: str,
    interval: ResolvedTargetInterval,
    decision: datetime,
) -> dict[str, Any]:
    payload = target.model_dump(mode="json")
    return {
        "leg_id": target.leg_id,
        "price_name": price_name,
        "role": target.role.value,
        "hub": target.hub,
        "tenor": target.tenor,
        "price_basis": target.price_basis,
        "target_basis": target.target_basis.value,
        "calendar_id": payload.get("calendar_id"),
        "gas_day_offset": payload.get("gas_day_offset"),
        "resolved_start_utc": _iso(interval.start_utc),
        "resolved_end_utc": _iso(interval.end_utc),
        "decision_time_utc": _iso(decision),
        "rejected_reasons": {},
    }


def _mark_matched(
    trace: dict[str, Any],
    row: BacktestObservation,
    decision: datetime,
    *,
    path: str,
) -> None:
    trace.update(
        {
            "outcome": "MATCHED",
            "selected_path": path,
            "observation_id": row.observation_id,
            "source_reference": row.source_reference,
            "observed_at_utc": _iso(_as_utc(row.observed_at_utc)),
            "availability_time_utc": _iso(_available_at(row)),
            "delivery_start_utc": (
                _iso(_as_utc(row.delivery_start_utc))
                if row.delivery_start_utc is not None
                else None
            ),
            "delivery_end_utc": (
                _iso(_as_utc(row.delivery_end_utc))
                if row.delivery_end_utc is not None
                else None
            ),
            "evidence_role": row.evidence_role,
            "price_basis": row.price_basis,
            "simulated": bool(row.simulated),
            "temporal_integrity": row.temporal_integrity.value,
            "decision_time_utc": _iso(decision),
        }
    )


def _rejected(
    price_name: str,
    *,
    leg_id: str | None,
    reason: str,
    blockers: tuple[str, ...],
) -> LegEvidenceSelection:
    return LegEvidenceSelection(
        price_name=price_name,
        leg_id=leg_id,
        rows=(),
        warnings=(),
        blockers=blockers,
        trace={"price_name": price_name, "leg_id": leg_id, "reason": reason},
    )


def _latest(rows: list[BacktestObservation]) -> BacktestObservation:
    return max(
        rows,
        key=lambda row: (_as_utc(row.observed_at_utc), row.source_reference),
    )


def _available_at(row: BacktestObservation) -> datetime:
    value = row.received_at_utc or row.observed_at_utc
    return _as_utc(value)


def _format_age_seconds(age: timedelta) -> str:
    """Render an exact age for the blocker string without losing precision.

    A whole-second age keeps its existing ``86401s`` shape; a fractional age is
    shown to microsecond precision rather than silently rounded or truncated.
    """

    total = age.total_seconds()
    if total.is_integer():
        return str(int(total))
    return f"{total:.6f}".rstrip("0").rstrip(".")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat().replace("+00:00", "Z")
