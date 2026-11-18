"""One evaluation run, from snapshot to store (design J.2).

:func:`run_evaluation` opens one valuation snapshot for the firm (book scope set aside: every
book is evaluated, and each reader is filtered when reading), runs every registered
evaluator, applies the contract check and the false-positive controls, and merges the result
into the store:

- **dedupe**: one record per key (type, legs, delivery period, books); re-evaluation updates
  it, never duplicates it;
- **persistence and hysteresis** (:mod:`~eurogas_nexus.domain.opportunities.lifecycle`);
- **versions**: a material change (value moved 20 % from the version's basis, or a state
  change) cuts a new version; the version row holds the object as last valued at it;
- **expiry** at the end of the validity window; ended records are kept 90 days (longer
  when linked to a case) and then removed.

An evaluator that raises, or returns a candidate that breaks the contract, produces nothing
in that run; its records are left as they were (a failure is not an absence) and the run
records it for the administrator alert. The desk never sees an error, only the time of the
last evaluation.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from eurogas_nexus.application.caller import Caller, firm_caller
from eurogas_nexus.application.opportunities.settings import load_thresholds
from eurogas_nexus.application.valuation_snapshot import freeze_snapshot, open_valuation_snapshot
from eurogas_nexus.domain.opportunities.controls import Assessment, Thresholds, assess
from eurogas_nexus.domain.opportunities.evaluator import (
    EvaluationContext,
    Evaluator,
    registered,
    validate_candidate,
)
from eurogas_nexus.domain.opportunities.lifecycle import Tracked, expire_if_due, missed, seen
from eurogas_nexus.domain.opportunities.model import (
    ENDED_STATES,
    Candidate,
    LegKind,
    OpportunityState,
)
from eurogas_nexus.domain.opportunities.serialise import freeze

#: Ended records are kept this long, unless a decision case points at them (J.2).
RETENTION = timedelta(days=90)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _basis(candidate: Candidate) -> Decimal:
    """The figure a material change is measured on: value in EUR, else value, else headline."""

    for measure in (candidate.value_eur, candidate.value, candidate.headline):
        if measure is not None:
            return measure.value
    return Decimal(0)


def _tracked(row) -> Tracked:
    return Tracked(
        state=OpportunityState(row.state),
        assessed_state=OpportunityState(row.assessed_state),
        version=row.version,
        consecutive_seen=row.consecutive_seen,
        consecutive_missed=row.consecutive_missed,
        surfaced=row.surfaced,
        value=None if row.version_basis is None else Decimal(str(row.version_basis)),
        ended_reason=row.ended_reason,
    )


def _apply_tracked(row, tracked: Tracked, now: datetime) -> None:
    if row.state != tracked.state.value:
        row.last_changed_utc = now
    row.state = tracked.state.value
    row.assessed_state = tracked.assessed_state.value
    row.version = tracked.version
    row.version_basis = tracked.value
    row.consecutive_seen = tracked.consecutive_seen
    row.consecutive_missed = tracked.consecutive_missed
    row.surfaced = tracked.surfaced
    row.ended_reason = tracked.ended_reason


def _write_content(session, row, candidate: Candidate, assessment: Assessment) -> dict[str, Any]:
    """Copy the candidate's figures onto the record and replace its legs, checks, keys."""

    from eurogas_nexus.db.models import (
        OpportunityCheckRecord,
        OpportunityDependencyRecord,
        OpportunityLegRecord,
    )

    payload = freeze(candidate, assessment)
    row.type = candidate.type.value
    row.lane = candidate.lane.value
    row.claim_key = assessment.blocker.code if assessment.blocker else candidate.claim_key
    row.claim_fields = dict(candidate.claim_fields)
    row.claim_text = assessment.claim_text
    row.headline_value = candidate.headline.value
    row.headline_unit = candidate.headline.unit
    row.value_amount = None if candidate.value is None else candidate.value.value
    row.value_currency = None if candidate.value is None else candidate.value.unit
    row.reporting_value = None if candidate.value_eur is None else candidate.value_eur.value
    row.reporting_currency = None if candidate.value_eur is None else candidate.value_eur.unit
    row.volume_value = None if candidate.volume is None else candidate.volume.value
    row.volume_unit = None if candidate.volume is None else candidate.volume.unit
    row.period_label = candidate.period.label
    row.period_start = candidate.period.start
    row.period_end = candidate.period.end
    row.quality_class = candidate.quality.value
    row.simulated = candidate.simulated
    row.book_ids = list(candidate.book_ids)
    row.source_families = list(candidate.source_families)
    row.reasons = list(assessment.reasons)
    row.blocker_json = None if assessment.blocker is None else assessment.blocker.to_json()
    row.expires_at_utc = candidate.expires_at_utc
    row.deadline_utc = candidate.deadline_utc
    row.evaluator = candidate.evaluator
    row.evaluator_version = candidate.evaluator_version
    session.flush()
    for model in (OpportunityLegRecord, OpportunityCheckRecord, OpportunityDependencyRecord):
        session.query(model).filter(model.opportunity_id == row.opportunity_id).delete(
            synchronize_session=False
        )
    unit = candidate.headline.unit
    for seq, leg in enumerate(candidate.legs):
        session.add(
            OpportunityLegRecord(
                opportunity_id=row.opportunity_id,
                seq=seq,
                kind=leg.kind.value,
                label_key=leg.label_key,
                label=leg.label,
                quantity_value=None if leg.quantity is None else leg.quantity.value,
                quantity_unit=None if leg.quantity is None else leg.quantity.unit,
                rate_value=None if leg.rate is None else leg.rate.value,
                rate_unit=None if leg.rate is None else leg.rate.unit,
                fx_value=None if leg.fx is None else leg.fx.value,
                fx_unit=None if leg.fx is None else leg.fx.unit,
                contribution_value=None if leg.contribution is None else leg.contribution.value,
                subtotal_value=None if leg.subtotal is None else leg.subtotal.value,
                unit=unit if leg.kind in {LegKind.TERM, LegKind.SUBTOTAL, LegKind.RESULT} else None,
                input_class=None if leg.input_class is None else leg.input_class.value,
                source_family=leg.source_family,
                source_ref=leg.source_ref[:200],
                as_of_utc=leg.as_of_utc,
            )
        )
    for seq, check in enumerate(candidate.checks):
        session.add(
            OpportunityCheckRecord(
                opportunity_id=row.opportunity_id,
                seq=seq,
                kind=check.kind.value,
                result=check.result.value,
                figure=check.figure,
                reference=check.reference[:200],
            )
        )
    for key in candidate.dependency_keys:
        session.add(OpportunityDependencyRecord(opportunity_id=row.opportunity_id, input_key=key))
    return payload


def _write_version(session, row, payload: dict[str, Any], snapshot_id: str, now: datetime):
    from eurogas_nexus.db.models import OpportunityVersionRecord

    version = session.get(OpportunityVersionRecord, (row.opportunity_id, row.version))
    if version is None:
        session.add(
            OpportunityVersionRecord(
                opportunity_id=row.opportunity_id,
                version=row.version,
                state=row.state,
                snapshot_id=snapshot_id,
                recorded_at_utc=now,
                payload_json=payload,
            )
        )
    else:
        version.state = row.state
        version.snapshot_id = snapshot_id
        version.recorded_at_utc = now
        version.payload_json = payload


def merge(
    session,
    produced: dict[str, list[tuple[Candidate, Assessment]]],
    *,
    evaluation_id: str,
    snapshot_id: str,
    thresholds: Thresholds,
    now: datetime,
) -> dict[str, int]:
    """Merge one run's results into the store; returns counts by outcome."""

    from eurogas_nexus.db.models import OpportunityRecord

    counts = {
        "created": 0,
        "updated": 0,
        "new_versions": 0,
        "missed": 0,
        "expired": 0,
        "duplicates": 0,
        "purged": 0,
    }
    names = sorted(produced)
    existing = {
        row.opp_key: row
        for row in session.query(OpportunityRecord)
        .filter(OpportunityRecord.evaluator.in_(names) if names else False)
        .all()
    }
    seen_keys: set[str] = set()
    for name in names:
        for candidate, assessment in produced[name]:
            key = candidate.key
            if key in seen_keys:
                counts["duplicates"] += 1
                continue
            seen_keys.add(key)
            row = existing.get(key)
            previous = None if row is None else _tracked(row)
            tracked, changed = seen(previous, assessment.state, _basis(candidate), thresholds)
            if previous is not None and previous.state is OpportunityState.CONVERTED:
                row.last_evaluated_utc = now
                continue
            if row is None:
                row = OpportunityRecord(
                    opportunity_id=f"opp-{uuid4().hex[:20]}",
                    opp_key=key,
                    first_seen_utc=now,
                    last_changed_utc=now,
                    snapshot_id=snapshot_id,
                    evaluation_id=evaluation_id,
                )
                session.add(row)
                counts["created"] += 1
            else:
                counts["updated"] += 1
            if changed:
                counts["new_versions"] += 1
                row.last_changed_utc = now
            _apply_tracked(row, tracked, now)
            row.last_evaluated_utc = now
            row.snapshot_id = snapshot_id
            row.evaluation_id = evaluation_id
            payload = _write_content(session, row, candidate, assessment)
            _write_version(session, row, payload, snapshot_id, now)
    for key, row in existing.items():
        if key in seen_keys or OpportunityState(row.state) in ENDED_STATES:
            continue
        tracked = missed(_tracked(row), thresholds)
        counts["missed"] += 1
        if tracked.state is OpportunityState.EXPIRED:
            counts["expired"] += 1
        _apply_tracked(row, tracked, now)
        row.last_evaluated_utc = now
    for row in (
        session.query(OpportunityRecord)
        .filter(OpportunityRecord.state.notin_([state.value for state in ENDED_STATES]))
        .all()
    ):
        tracked = expire_if_due(_tracked(row), _aware(row.expires_at_utc), now)
        if tracked.state is OpportunityState.EXPIRED and row.state != tracked.state.value:
            counts["expired"] += 1
            _apply_tracked(row, tracked, now)
    cutoff = now - RETENTION
    for row in (
        session.query(OpportunityRecord)
        .filter(OpportunityRecord.state == OpportunityState.EXPIRED.value)
        .filter(OpportunityRecord.case_id.is_(None))
        .all()
    ):
        if _aware(row.last_changed_utc) < cutoff:
            session.delete(row)
            counts["purged"] += 1
    session.flush()
    return counts


def run_evaluation(
    session,
    *,
    trigger: str,
    triggered_by: str,
    now_utc: datetime | None = None,
    caller: Caller | None = None,
    evaluators: Iterable[Evaluator] | None = None,
    demo_desk: bool | None = None,
) -> dict[str, Any]:
    """Evaluate every registered evaluator firm-wide and merge the result; commit is the caller's.

    Args:
        session: Runtime-store session.
        trigger: ``on_demand``, ``schedule`` or ``outbox``.
        triggered_by: Principal id or job name recorded on the run and the snapshot.
        now_utc: The evaluation instant (default now).
        caller: Whose entitlement the snapshot reads under (default the firm's service
            caller: every book, the families held under a non-display licence).
        evaluators: Override the registry (tests).
        demo_desk: Override the deployment's demo-marks setting (tests).

    Returns:
        The run summary (evaluation id, snapshot id, status, per-evaluator status, counts).
    """

    from eurogas_nexus.db.models import OpportunityEvaluationRecord
    from eurogas_nexus.security.portfolio_scope import firm_wide_scope

    now = _aware(now_utc) or datetime.now(UTC)
    thresholds = load_thresholds(session)
    run = OpportunityEvaluationRecord(
        evaluation_id=f"oeval-{uuid4().hex[:20]}",
        trigger=trigger,
        triggered_by=triggered_by[:64],
        as_of_utc=now,
        started_at_utc=datetime.now(UTC),
        status="running",
        demo_desk=False,
        evaluators_json={},
        counts_json={},
    )
    session.add(run)
    session.flush()
    statuses: dict[str, dict[str, Any]] = {}
    produced: dict[str, list[tuple[Candidate, Assessment]]] = {}
    with firm_wide_scope():
        reader = open_valuation_snapshot(
            session,
            caller=caller or firm_caller(session=session),
            as_of_utc=now,
            assumption_set_id=thresholds.assumption_set_id,
            demo_desk=demo_desk,
        )
        context = EvaluationContext(now, thresholds, reader.demo_desk)
        for evaluator in evaluators if evaluators is not None else registered():
            try:
                candidates = list(evaluator.evaluate(reader, context))
                for candidate in candidates:
                    validate_candidate(candidate, context)
            except Exception as exc:  # noqa: BLE001 - any evaluator failure is contained
                statuses[evaluator.name] = {
                    "status": "failed",
                    "version": evaluator.version,
                    "error": type(exc).__name__,
                    "message": str(exc)[:300],
                }
                continue
            assessed = [
                (
                    candidate,
                    assess(candidate, thresholds, as_of_utc=now, demo_desk=reader.demo_desk),
                )
                for candidate in candidates
            ]
            kept = [(c, a) for c, a in assessed if a.state is not None]
            statuses[evaluator.name] = {
                "status": "ok",
                "version": evaluator.version,
                "candidates": len(candidates),
                "refused": len(assessed) - len(kept),
            }
            produced[evaluator.name] = kept
    manifest = freeze_snapshot(
        session, reader, purpose="opportunity_evaluation", created_by=triggered_by[:64]
    )
    counts = merge(
        session,
        produced,
        evaluation_id=run.evaluation_id,
        snapshot_id=manifest.snapshot_id,
        thresholds=thresholds,
        now=now,
    )
    failed = [name for name, status in statuses.items() if status["status"] == "failed"]
    run.status = "ok" if not failed else ("partial" if produced else "failed")
    run.finished_at_utc = datetime.now(UTC)
    run.snapshot_id = manifest.snapshot_id
    run.demo_desk = reader.demo_desk
    run.evaluators_json = statuses
    run.counts_json = counts
    session.flush()
    return evaluation_summary(run)


def evaluation_summary(run) -> dict[str, Any]:
    """A run as the API returns it."""

    return {
        "evaluation_id": run.evaluation_id,
        "trigger": run.trigger,
        "triggered_by": run.triggered_by,
        "as_of_utc": _aware(run.as_of_utc).isoformat(),
        "started_at_utc": _aware(run.started_at_utc).isoformat(),
        "finished_at_utc": (
            _aware(run.finished_at_utc).isoformat() if run.finished_at_utc else None
        ),
        "status": run.status,
        "snapshot_id": run.snapshot_id,
        "demo_desk": run.demo_desk,
        "evaluators": run.evaluators_json,
        "counts": run.counts_json,
    }
