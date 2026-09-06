"""Repository access for temporally safe backtest execution.

This module owns DB access only. Temporal rules, economics and metrics live
in the domain backtest package. The repository loads all eligible rows once
as a bounded batch; the engine never issues one query per decision event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    BacktestAttributionRecord,
    BacktestDecisionEventRecord,
    BacktestExperimentRecord,
    BacktestSeriesRecord,
    CostObservationRecord,
    FxObservationRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    StrategyVersionRecord,
)
from eurogas_nexus.domain.backtest.contracts import (
    BacktestCostObservation,
    BacktestEvidencePool,
    BacktestFxRate,
    BacktestObservation,
    BacktestPeriod,
    BacktestResourceEvidence,
)
from eurogas_nexus.domain.backtest.temporal import classify_source_temporal_integrity
from eurogas_nexus.domain.strategy_lab.registry import (
    canonical_content_hash,
)


class BacktestRepositoryError(ValueError):
    """Domain failure in backtest persistence."""


def load_backtest_evidence_pool(
    session: Session,
    *,
    version: StrategyVersionRecord,
    period: BacktestPeriod,
    max_lookback_seconds: int = 86_400,
) -> BacktestEvidencePool:
    """Load all potentially eligible evidence rows for one run."""

    lookback_start = _as_utc(period.start_utc) - timedelta(
        seconds=max_lookback_seconds
    )
    period_end = _as_utc(period.end_utc)
    observations: list[BacktestObservation] = []

    market_rows = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.observed_at_utc >= lookback_start)
        .filter(MarketObservationRecord.observed_at_utc <= period_end)
        .order_by(MarketObservationRecord.observed_at_utc)
        .all()
    )
    for row in market_rows:
        metadata = row.metadata_json or {}
        tenor = str(metadata.get("tenor") or _tenor_from_product(row.product))
        integrity, reason = classify_source_temporal_integrity(
            row.source_system,
            received_at_utc=None,
            observed_at_utc=row.observed_at_utc,
        )
        observations.append(
            BacktestObservation(
                observation_id=row.observation_id,
                source_system=row.source_system,
                venue=row.market_venue,
                hub=str(metadata.get("hub") or _hub_from_product(row.product, row.market_venue)),
                product=row.product,
                tenor=tenor,
                price_name=str(
                    metadata.get("price_name")
                    or _price_name(row.source_system, tenor)
                ),
                price=row.price,
                currency=row.currency,
                unit=row.unit,
                observed_at_utc=row.observed_at_utc,
                received_at_utc=None,
                delivery_start_utc=row.period_start_utc,
                delivery_end_utc=row.period_end_utc,
                bar_minutes=None,
                price_type=str(
                    metadata.get("price_type")
                    or _observation_price_type(metadata)
                ).lower(),
                source_reference=row.source_reference,
                simulated=bool(metadata.get("simulated", False)),
                temporal_integrity=integrity,
            )
        )

    quote_rows = (
        session.query(MarketQuoteRecord)
        .filter(MarketQuoteRecord.observed_at_utc >= lookback_start)
        .filter(MarketQuoteRecord.observed_at_utc <= period_end)
        .order_by(MarketQuoteRecord.observed_at_utc)
        .all()
    )
    for row in quote_rows:
        tenor = row.product
        for price_type, price in _quote_side_prices(row):
            if price is None:
                continue
            observations.append(
                BacktestObservation(
                    observation_id=f"{row.quote_id}:{price_type.lower()}",
                    source_system=row.source_system,
                    venue=row.venue,
                    hub=row.hub,
                    product=row.product,
                    tenor=tenor,
                    price_name=_price_name(row.source_system, tenor),
                    price=price,
                    currency=row.currency,
                    unit="MWh",
                    observed_at_utc=row.observed_at_utc,
                    received_at_utc=row.received_at_utc,
                    delivery_start_utc=row.delivery_start_utc,
                    delivery_end_utc=row.delivery_end_utc,
                    bar_minutes=None,
                    price_type=price_type,
                    source_reference=row.source_reference,
                    simulated=row.simulated,
                    temporal_integrity=classify_source_temporal_integrity(
                        row.source_system,
                        received_at_utc=row.received_at_utc,
                        observed_at_utc=row.observed_at_utc,
                    )[0],
                )
            )

    fx_rows = (
        session.query(FxObservationRecord)
        .filter(FxObservationRecord.observed_at_utc >= lookback_start)
        .filter(FxObservationRecord.observed_at_utc <= period_end)
        .order_by(FxObservationRecord.observed_at_utc)
        .all()
    )
    fx_rates = [
        BacktestFxRate(
            observation_id=row.observation_id,
            pair=row.pair,
            base_currency=row.base_currency,
            quote_currency=row.quote_currency,
            rate=row.rate,
            observed_at_utc=row.observed_at_utc,
            received_at_utc=None,
            source_system=row.source_system,
            source_reference=row.source_reference,
            temporal_integrity=classify_source_temporal_integrity(
                row.source_system,
                received_at_utc=None,
                observed_at_utc=row.observed_at_utc,
            )[0],
        )
        for row in fx_rows
    ]

    cost_rows = (
        session.query(CostObservationRecord)
        .filter(CostObservationRecord.effective_from_utc <= period_end)
        .filter(
            (CostObservationRecord.effective_to_utc.is_(None))
            | (CostObservationRecord.effective_to_utc >= lookback_start)
        )
        .order_by(CostObservationRecord.effective_from_utc)
        .all()
    )
    cost_observations = [
        BacktestCostObservation(
            observation_id=row.observation_id,
            scope_type=row.scope_type,
            scope_id=row.scope_id,
            observation_type=row.observation_type,
            value=row.value,
            currency=row.currency,
            unit=row.unit,
            effective_from_utc=row.effective_from_utc,
            effective_to_utc=row.effective_to_utc,
            source_system=row.source_system,
            source_reference=row.source_reference,
            created_at_utc=row.created_at_utc,
        )
        for row in cost_rows
    ]

    definition = version.definition_json or {}
    resources = [
        BacktestResourceEvidence(**row)
        for row in definition.get("resource_contexts", [])
    ]

    return BacktestEvidencePool(
        observations=observations,
        fx_rates=fx_rates,
        cost_observations=cost_observations,
        resources=resources,
    )


def create_backtest_snapshot(
    session: Session,
    *,
    pool: BacktestEvidencePool,
    period: BacktestPeriod,
    now_utc: datetime,
) -> str:
    """Create a CR-03 immutable evidence snapshot for one backtest run."""

    from eurogas_nexus.db.repositories import strategy_registry

    observation_refs = sorted(pool.observation_refs())
    fx_refs = sorted(pool.fx_refs())
    resource_refs = sorted(pool.resource_refs())
    cost_refs = sorted(pool.cost_refs())
    source_systems = sorted(
        {
            row.source_system
            for row in pool.observations
            if row.source_system
        }
        | {row.source_system for row in pool.fx_rates if row.source_system}
        | {row.source_system for row in pool.cost_observations if row.source_system}
    )
    row_counts = {
        "price_observations": len(pool.observations),
        "fx_observations": len(pool.fx_rates),
        "cost_observations": len(pool.cost_observations),
        "resource_contexts": len(pool.resources),
    }
    temporal_statuses = {
        row.temporal_integrity.value for row in pool.observations
    } | {row.temporal_integrity.value for row in pool.fx_rates}
    quality_state = (
        "VERIFIED"
        if temporal_statuses == {"VERIFIED"}
        else "APPROXIMATE"
        if temporal_statuses
        and temporal_statuses <= {"VERIFIED", "APPROXIMATE"}
        else "INSUFFICIENT"
    )
    content = {
        "schema_version": "strategy-data-snapshot/v1",
        "period_start_utc": _iso(period.start_utc),
        "period_end_utc": _iso(period.end_utc),
        "observation_refs": observation_refs,
        "fx_observation_refs": fx_refs,
        "resource_snapshot_refs": resource_refs,
        "cost_observation_refs": cost_refs,
        "source_systems": source_systems,
        "row_counts": row_counts,
        "quality_state": quality_state,
    }
    row = strategy_registry.create_data_snapshot(
        session,
        snapshot_id=f"strategy-snapshot-{uuid4().hex[:20]}",
        data_cutoff_utc=_as_utc(period.end_utc),
        observation_refs=observation_refs,
        fx_observation_refs=fx_refs,
        resource_snapshot_refs=resource_refs,
        source_systems=source_systems,
        row_counts=row_counts,
        quality_state=quality_state,
        content_hash=canonical_content_hash(content),
        now_utc=now_utc,
    )
    session.flush()
    return row.snapshot_id


def list_backtest_events(session: Session, run_id: str) -> list[dict]:
    rows = (
        session.query(BacktestDecisionEventRecord)
        .filter(BacktestDecisionEventRecord.run_id == run_id)
        .order_by(BacktestDecisionEventRecord.decision_sequence)
        .all()
    )
    return [_event_payload(row) for row in rows]


def list_backtest_series(session: Session, run_id: str) -> list[dict]:
    rows = (
        session.query(BacktestSeriesRecord)
        .filter(BacktestSeriesRecord.run_id == run_id)
        .order_by(BacktestSeriesRecord.decision_sequence)
        .all()
    )
    return [_series_payload(row) for row in rows]


def list_backtest_attribution(session: Session, run_id: str) -> list[dict]:
    rows = (
        session.query(BacktestAttributionRecord)
        .filter(BacktestAttributionRecord.run_id == run_id)
        .order_by(
            BacktestAttributionRecord.decision_time_utc,
            BacktestAttributionRecord.dimension,
            BacktestAttributionRecord.key,
        )
        .all()
    )
    return [_attribution_payload(row) for row in rows]


def create_experiment(
    session: Session,
    *,
    experiment_id: str,
    strategy_id: str,
    base_strategy_version_id: str,
    name: str,
    hypothesis: str,
    experiment_type: str,
    evaluation_period: dict,
    created_by: str,
    now_utc: datetime,
) -> BacktestExperimentRecord:
    row = BacktestExperimentRecord(
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        base_strategy_version_id=base_strategy_version_id,
        name=name,
        hypothesis=hypothesis,
        experiment_type=experiment_type,
        evaluation_period_json=evaluation_period,
        run_ids=[],
        status="ACTIVE",
        created_by=created_by,
        created_at_utc=now_utc,
        updated_at_utc=now_utc,
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def get_experiment(
    session: Session, experiment_id: str
) -> BacktestExperimentRecord | None:
    return session.get(BacktestExperimentRecord, experiment_id)


def list_experiments(session: Session, *, limit: int = 200) -> list[dict]:
    rows = (
        session.query(BacktestExperimentRecord)
        .order_by(BacktestExperimentRecord.updated_at_utc.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [_experiment_payload(row) for row in rows]


def append_run_to_experiment(
    session: Session,
    *,
    experiment_id: str,
    run_id: str,
    now_utc: datetime,
) -> None:
    row = get_experiment(session, experiment_id)
    if row is None:
        raise BacktestRepositoryError(f"Experiment does not exist: {experiment_id}")
    run_ids = list(row.run_ids or [])
    if run_id not in run_ids:
        run_ids.append(run_id)
    row.run_ids = run_ids
    row.updated_at_utc = now_utc
    session.flush()


def _quote_side_prices(row: MarketQuoteRecord) -> list[tuple[str, float | None]]:
    mid = None
    if row.bid_price is not None and row.ask_price is not None:
        mid = round((row.bid_price + row.ask_price) / 2, 4)
    elif row.last_price is not None:
        mid = row.last_price
    return [
        ("BID", row.bid_price),
        ("ASK", row.ask_price),
        ("LAST", row.last_price),
        ("MID", mid),
    ]


def _price_name(source_system: str, tenor: str) -> str:
    normalized_source = source_system.upper().replace("_SIM", "")
    normalized_tenor = tenor.replace("-", "_").replace(" ", "_").upper()
    if "ICE_OCM" in normalized_source:
        return "ICE_OCM"
    if "ICIS" in normalized_source or "HEREN" in normalized_source:
        return "ICIS_HEREN_DAY_AHEAD"
    if "SAP" in normalized_source:
        return "SAP"
    if "EEX" in normalized_source:
        return (
            "EEX_DAY_AHEAD"
            if "DAY_AHEAD" in normalized_tenor or "DAYAHEAD" in normalized_tenor
            else f"EEX_{normalized_tenor}"
        )
    return f"{normalized_source}_{normalized_tenor}"


def _tenor_from_product(product: str) -> str:
    lowered = product.lower()
    if "within-day" in lowered or "withinday" in lowered:
        return "within-day"
    if "day-ahead" in lowered or "day ahead" in lowered:
        return "day-ahead"
    if "weekend" in lowered:
        return "weekend"
    if "month" in lowered:
        return "month-ahead"
    return lowered


def _hub_from_product(product: str, venue: str) -> str:
    return product.strip().split()[0] if product.strip() else venue


def _observation_price_type(metadata: dict) -> str:
    timing = str(metadata.get("price_timing") or "").lower()
    if "assessment" in timing:
        return "assessment"
    if "broker" in timing:
        return "broker_screen"
    if "exchange" in timing:
        return "exchange_reference"
    if timing == "instant":
        return "instant"
    return "mid"


def _event_payload(row: BacktestDecisionEventRecord) -> dict:
    return {
        "event_id": row.event_id,
        "run_id": row.run_id,
        "experiment_id": row.experiment_id,
        "decision_sequence": row.decision_sequence,
        "decision_time_utc": _iso(row.decision_time_utc),
        "gas_day": row.gas_day,
        "gas_day_start_utc": _iso(row.gas_day_start_utc),
        "gas_day_end_utc": _iso(row.gas_day_end_utc),
        "outcome": row.outcome,
        "candidate_action_for_review": row.candidate_action_for_review,
        "weighted_score": row.weighted_score,
        "day_ahead_average_gbp_mwh": row.day_ahead_average_gbp_mwh,
        "intraday_average_gbp_mwh": row.intraday_average_gbp_mwh,
        "intraday_vs_day_ahead_spread_gbp_mwh": row.intraday_vs_day_ahead_spread_gbp_mwh,
        "allocation_targets": row.allocation_targets or [],
        "gross_indicative_pnl_gbp": row.gross_indicative_pnl_gbp,
        "modeled_costs_gbp": row.modeled_costs_gbp,
        "net_indicative_pnl_gbp": row.net_indicative_pnl_gbp,
        "cumulative_net_indicative_pnl_gbp": row.cumulative_net_indicative_pnl_gbp,
        "ending_exposure_mwh_per_day": row.ending_exposure_mwh_per_day,
        "missing_inputs": row.missing_inputs or [],
        "warnings": row.warnings or [],
        "price_evidence_refs": row.price_evidence_refs or [],
        "fx_evidence_refs": row.fx_evidence_refs or [],
        "cost_evidence_refs": row.cost_evidence_refs or [],
        "resource_evidence_refs": row.resource_evidence_refs or [],
        "cost_trace": row.cost_trace or [],
        "attribution": row.attribution or [],
        "research_only": row.research_only,
        "human_review_required": row.human_review_required,
    }


def _series_payload(row: BacktestSeriesRecord) -> dict:
    return {
        "series_point_id": row.series_point_id,
        "run_id": row.run_id,
        "decision_sequence": row.decision_sequence,
        "decision_time_utc": _iso(row.decision_time_utc),
        "gas_day": row.gas_day,
        "gross_indicative_pnl_gbp": row.gross_indicative_pnl_gbp,
        "modeled_costs_gbp": row.modeled_costs_gbp,
        "net_indicative_pnl_gbp": row.net_indicative_pnl_gbp,
        "cumulative_net_indicative_pnl_gbp": row.cumulative_net_indicative_pnl_gbp,
        "ending_exposure_mwh_per_day": row.ending_exposure_mwh_per_day,
        "research_only": row.research_only,
    }


def _attribution_payload(row: BacktestAttributionRecord) -> dict:
    return {
        "attribution_id": row.attribution_id,
        "run_id": row.run_id,
        "event_id": row.event_id,
        "decision_time_utc": _iso(row.decision_time_utc),
        "dimension": row.dimension,
        "key": row.key,
        "gross_indicative_pnl_gbp": row.gross_indicative_pnl_gbp,
        "modeled_costs_gbp": row.modeled_costs_gbp,
        "net_indicative_pnl_gbp": row.net_indicative_pnl_gbp,
        "quantity_mwh_per_day": row.quantity_mwh_per_day,
        "source_refs": row.source_refs or [],
        "research_only": row.research_only,
    }


def _experiment_payload(row: BacktestExperimentRecord) -> dict:
    return {
        "experiment_id": row.experiment_id,
        "strategy_id": row.strategy_id,
        "base_strategy_version_id": row.base_strategy_version_id,
        "name": row.name,
        "hypothesis": row.hypothesis,
        "experiment_type": row.experiment_type,
        "evaluation_period": row.evaluation_period_json or {},
        "run_ids": row.run_ids or [],
        "status": row.status,
        "created_by": row.created_by,
        "created_at_utc": _iso(row.created_at_utc),
        "updated_at_utc": _iso(row.updated_at_utc),
        "research_only": row.research_only,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None
