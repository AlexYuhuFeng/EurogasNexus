"""Temporal/as-of rules for the historical backtest engine.

The rules in this module are the single backend implementation of historical
information-set selection. No strategy component, API route, or UI may
re-implement "latest price as of T" with its own ad-hoc timestamp filters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite

from eurogas_nexus.domain.backtest.contracts import (
    BacktestCostObservation,
    BacktestEconomicAssumptions,
    BacktestEvidencePool,
    BacktestFxRate,
    BacktestObservation,
)
from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_interval_utc,
    gas_day_label,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    FillPricePolicy,
    MissingDataPolicy,
    TemporalIntegrityStatus,
)

# Sources whose normalized market_observations rows have no explicit receipt
# time. The classification is a policy decision, not an invented timestamp.
_SOURCE_TEMPORAL_POLICY: dict[str, tuple[TemporalIntegrityStatus, str]] = {
    "ICE_OCM": (
        TemporalIntegrityStatus.APPROXIMATE,
        "Exchange screen mark; observed_at is contemporaneous but exact "
        "platform availability latency is not stored.",
    ),
    "TRAY": (
        TemporalIntegrityStatus.APPROXIMATE,
        "Broker screen; observed_at is contemporaneous but exact platform "
        "availability latency is not stored.",
    ),
    "EEX": (
        TemporalIntegrityStatus.APPROXIMATE,
        "Exchange reference; observed_at is the row effective time and "
        "publication latency is not stored.",
    ),
    "ICIS": (
        TemporalIntegrityStatus.APPROXIMATE,
        "Daily assessment; publication timestamp is not stored.",
    ),
    "SAP": (
        TemporalIntegrityStatus.APPROXIMATE,
        "Assessment publication timestamp is not stored.",
    ),
    "ECB": (
        TemporalIntegrityStatus.APPROXIMATE,
        "Reference rate publication timestamp is not stored.",
    ),
}

WARNING_TEMPORAL_PROVENANCE_APPROXIMATE = "TEMPORAL_PROVENANCE_APPROXIMATE"
WARNING_CARRY_FORWARD_USED = "CARRY_FORWARD_USED"
BLOCKER_FX_MISSING = "FX_EVIDENCE_MISSING"
BLOCKER_UNIT_MISMATCH = "UNIT_MISMATCH"


def classify_source_temporal_integrity(
    source_system: str,
    *,
    received_at_utc: datetime | None,
    observed_at_utc: datetime | None,
) -> tuple[TemporalIntegrityStatus, str]:
    """Classify one row without inventing availability provenance."""

    if received_at_utc is not None:
        return TemporalIntegrityStatus.VERIFIED, "received_at_utc stored"
    if observed_at_utc is None:
        return (
            TemporalIntegrityStatus.INSUFFICIENT,
            "No observed_at_utc; row cannot be placed on the information clock",
        )
    status, reason = _source_temporal_policy(source_system)
    return status, reason


def availability_time(
    observation: BacktestObservation | BacktestFxRate,
) -> tuple[datetime, TemporalIntegrityStatus]:
    """Return the allowed availability timestamp for one row."""

    status = observation.temporal_integrity
    if status == TemporalIntegrityStatus.INSUFFICIENT:
        raise ValueError("insufficient temporal provenance cannot be ordered")
    value = observation.received_at_utc or observation.observed_at_utc
    return _as_utc(value), status


def as_of_price_observations(
    pool: BacktestEvidencePool,
    decision_time_utc: datetime,
    *,
    required_price_names: set[str] | None = None,
    hubs: set[str] | None = None,
    tenors: set[str] | None = None,
    bar_minutes: int | None = None,
    fill_price_policy: FillPricePolicy = FillPricePolicy.MID,
) -> list[BacktestObservation]:
    """Return price rows allowed at T and matching component constraints."""

    decision = _as_utc(decision_time_utc)
    selected: list[BacktestObservation] = []
    for row in pool.observations:
        if row.temporal_integrity == TemporalIntegrityStatus.INSUFFICIENT:
            continue
        available, _ = availability_time(row)
        if available > decision:
            continue
        if required_price_names and row.price_name.upper() not in required_price_names:
            continue
        if hubs and row.hub.upper() not in hubs:
            continue
        if tenors and row.tenor.lower() not in tenors:
            continue
        if bar_minutes is not None and row.bar_minutes not in {None, bar_minutes}:
            continue
        if not _matches_fill_policy(row, fill_price_policy):
            continue
        selected.append(row)
    selected.sort(key=lambda row: _as_utc(row.observed_at_utc))
    return selected


def as_of_fx_rates(
    pool: BacktestEvidencePool,
    decision_time_utc: datetime,
) -> list[BacktestFxRate]:
    """Return FX rows whose availability timestamp is at or before T."""

    decision = _as_utc(decision_time_utc)
    selected: list[BacktestFxRate] = []
    for row in pool.fx_rates:
        if row.temporal_integrity == TemporalIntegrityStatus.INSUFFICIENT:
            continue
        available, _ = availability_time(row)
        if available <= decision:
            selected.append(row)
    selected.sort(key=lambda row: _as_utc(row.observed_at_utc))
    return selected


def as_of_cost_observations(
    pool: BacktestEvidencePool,
    decision_time_utc: datetime,
) -> list[BacktestCostObservation]:
    """Return cost rows effective at T; newest eligible row per key wins."""

    decision = _as_utc(decision_time_utc)
    eligible: dict[tuple[str, str, str], BacktestCostObservation] = {}
    for row in pool.cost_observations:
        if _as_utc(row.effective_from_utc) > decision:
            continue
        if row.effective_to_utc is not None and _as_utc(row.effective_to_utc) < decision:
            continue
        key = (row.scope_type, row.scope_id, row.observation_type)
        current = eligible.get(key)
        if current is None or _row_recency(row) > _row_recency(current):
            eligible[key] = row
    return sorted(eligible.values(), key=lambda row: (row.scope_type, row.scope_id))


def latest_eligible_for_series(
    rows: list[BacktestObservation],
    *,
    series_names: set[str],
) -> list[BacktestObservation]:
    """Return the latest allowed row per source series, newest first."""

    by_name: dict[str, BacktestObservation] = {}
    for row in rows:
        name = row.price_name.upper()
        if name not in series_names:
            continue
        current = by_name.get(name)
        if current is None or _as_utc(row.observed_at_utc) > _as_utc(
            current.observed_at_utc
        ):
            by_name[name] = row
    return sorted(
        by_name.values(), key=lambda row: _as_utc(row.observed_at_utc), reverse=True
    )


def apply_missing_data_policy(
    eligible: list[BacktestObservation],
    *,
    series_names: set[str],
    decision_time_utc: datetime,
    assumptions: BacktestEconomicAssumptions,
    fallback_rows: list[BacktestObservation] | None = None,
) -> tuple[list[BacktestObservation], list[str], list[str]]:
    """Apply the declared missing-data policy for one required series.

    Returns ``(selected_rows, warnings, blockers)``. Unrestricted forward
    fill is never applied; carry-forward is bounded and provenance-marked.
    Fallback source selection searches the unfiltered as-of rows so the
    approved fallback can have a different source/price-name lineage.
    """

    selected = list(eligible)
    found = {row.price_name.upper() for row in eligible}
    missing = sorted(series_names - found)
    if not missing:
        return selected, [], []

    policy = assumptions.missing_data_policy
    if policy == MissingDataPolicy.FAIL:
        return selected, [], [f"MISSING_PRICE_SERIES:{name}" for name in missing]
    if policy == MissingDataPolicy.SKIP_DECISION:
        return selected, [], ["SKIP_DECISION:MISSING_PRICE_SERIES"]
    if policy == MissingDataPolicy.USE_APPROVED_FALLBACK_SOURCE:
        for name in missing:
            fallback = assumptions.fallback_sources.get(name)
            if not fallback:
                return selected, [], [
                    f"FALLBACK_SOURCE_NOT_CONFIGURED:{name}"
                ]
            candidates = list(fallback_rows or eligible)
            fallback_selected = [
                row
                for row in candidates
                if row.source_system.upper() == fallback.upper()
                or row.price_name.upper() == fallback.upper()
            ]
            if not fallback_selected:
                return selected, [], [f"FALLBACK_SOURCE_MISSING:{name}"]
            selected.extend(
                row.model_copy(
                    update={
                        "price_name": name,
                        "source_reference": (
                            f"fallback:{fallback}->{name}:"
                            f"{row.source_reference}"
                        ),
                    }
                )
                for row in fallback_selected
            )
        return selected, [f"SOURCE_FALLBACK_USED:{','.join(missing)}"], []

    # CARRY_FORWARD_WITH_MAX_AGE: find last observation before T, bounded.
    decision = _as_utc(decision_time_utc)
    for name in missing:
        candidates = [
            row
            for row in eligible
            if row.price_name.upper() in series_names
            and _as_utc(row.observed_at_utc) <= decision
        ]
        if not candidates:
            return selected, [], [f"MISSING_PRICE_SERIES:{name}"]
        latest = max(candidates, key=lambda row: _as_utc(row.observed_at_utc))
        age = (decision - _as_utc(latest.observed_at_utc)).total_seconds()
        if age > assumptions.carry_forward_max_age_seconds:
            return selected, [], [
                f"CARRY_FORWARD_MAX_AGE_EXCEEDED:{name}:{int(age)}s"
            ]
        if latest not in selected:
            selected.append(latest)
    return selected, [f"CARRY_FORWARD_USED:{','.join(missing)}"], []


def convert_price_to_gbp_mwh(
    *,
    price: float,
    currency: str,
    unit: str,
    fx_rates: list[BacktestFxRate],
) -> tuple[float, list[str], list[str]]:
    """Convert one price to GBP/MWh using eligible historical FX only.

    Returns ``(price_gbp_mwh, warnings, blockers)``. A currency mismatch
    without conversion evidence is a blocker, never a silent passthrough.
    """

    warnings: list[str] = []
    blockers: list[str] = []
    if not _is_mwh_unit(unit):
        blockers.append(f"{BLOCKER_UNIT_MISMATCH}:{unit}")
        return 0.0, warnings, blockers
    source = currency.strip().upper()
    if source == "GBP":
        return _round4(price), warnings, blockers
    factor = _fx_factor(source, "GBP", fx_rates)
    if factor is None:
        blockers.append(f"{BLOCKER_FX_MISSING}:{source}->GBP")
        return 0.0, warnings, blockers
    return _round4(price * factor), warnings, blockers


def gas_day_window(
    decision_time_utc: datetime,
    *,
    calendar: str = DEFAULT_GAS_DAY_CALENDAR,
) -> tuple[str, datetime, datetime]:
    """Resolve the canonical gas-day window containing a decision time."""

    start, end = gas_day_interval_utc(decision_time_utc, calendar=calendar)
    return gas_day_label(decision_time_utc, calendar=calendar), start, end


def _fx_factor(
    source_currency: str,
    target_currency: str,
    rates: list[BacktestFxRate],
) -> float | None:
    """Latest eligible direct FX factor for source->target."""

    source = source_currency.upper()
    target = target_currency.upper()
    if source == target:
        return 1.0
    matching: list[BacktestFxRate] = []
    for rate in rates:
        base = rate.base_currency.upper()
        quote = rate.quote_currency.upper()
        if not _positive_finite(rate.rate):
            continue
        if base == source and quote == target:
            matching.append(rate)
        elif base == target and quote == source:
            matching.append(rate)
    if not matching:
        return None
    latest = max(matching, key=lambda row: _as_utc(row.observed_at_utc))
    if latest.base_currency.upper() == source:
        return latest.rate
    return 1.0 / latest.rate


def _matches_fill_policy(
    row: BacktestObservation,
    policy: FillPricePolicy,
) -> bool:
    if policy == FillPricePolicy.NEXT_ELIGIBLE:
        return True
    price_type = row.price_type.upper()
    if policy == FillPricePolicy.ASSESSMENT:
        return price_type in {"ASSESSMENT", "DAILY_ASSESSMENT"}
    if policy == FillPricePolicy.MID:
        return price_type in {"MID", "EXCHANGE_REFERENCE", "BROKER_SCREEN", "INSTANT"}
    if policy == FillPricePolicy.BID:
        return price_type == "BID"
    if policy == FillPricePolicy.ASK:
        return price_type == "ASK"
    if policy == FillPricePolicy.LAST:
        return price_type == "LAST"
    return True


def _source_temporal_policy(
    source_system: str,
) -> tuple[TemporalIntegrityStatus, str]:
    normalized = source_system.replace("_", " ").replace("-", " ").strip().upper()
    for prefix, policy in _SOURCE_TEMPORAL_POLICY.items():
        if normalized.startswith(prefix) or source_system.upper().startswith(prefix):
            return policy
    return TemporalIntegrityStatus.APPROXIMATE, "No declared receipt timestamp"


def _is_mwh_unit(unit: str) -> bool:
    normalized = unit.upper().replace(" ", "")
    return "MWH" in normalized


def _positive_finite(value: float) -> bool:
    return isfinite(value) and value > 0


def _round4(value: float) -> float:
    return round(value, 4)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _row_recency(row: BacktestCostObservation) -> datetime:
    return _as_utc(row.created_at_utc or row.effective_from_utc)
