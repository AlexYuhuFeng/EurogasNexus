"""Deterministic runtime monitoring and optional DeepSeek enrichment."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.application.ai_style import DESK_NOTE_RULES, ENRICHMENT_CALL
from eurogas_nexus.application.desk_text import credit_lines, mandate_lines, money
from eurogas_nexus.application.service_identity import (
    ServiceAuthority,
    bind_service_actor,
    configured_service_principal_name,
    resolve_service_authority,
)
from eurogas_nexus.db.models import (
    IngestionRunRecord,
    MonitoringAlertRecord,
    StrategyAlertRecord,
)
from eurogas_nexus.db.repositories.monitoring import (
    resolve_absent_monitoring_alerts,
    upsert_monitoring_alert,
)
from eurogas_nexus.domain.dataops.run_status import is_failed_run_status
from eurogas_nexus.domain.monitoring import MonitoringCandidate
from eurogas_nexus.llm import DEEPSEEK_DEFAULT_MODEL, DeepSeekCallResult, invoke_deepseek
from eurogas_nexus.security.identity import AuthenticatedPrincipal
from eurogas_nexus.security.provider_keys import load_provider_api_key

ProviderCall = Callable[..., DeepSeekCallResult]
ApiKeyLoader = Callable[[str], str | None]

#: Declared :class:`DeepSeekCallResult` status for a call refused at the authority boundary
#: (owner decision D7). ``error_code`` carries a declared ``service_identity`` refusal code.
ENRICHMENT_AUTHORITY_REFUSED = "authority_refused"


def scan_monitoring_conditions(
    session: Session,
    *,
    now_utc: datetime | None = None,
    enrich_with_llm: bool = True,
    max_llm_enrichments: int = 3,
    api_key_loader: ApiKeyLoader | None = None,
    provider_call: ProviderCall | None = None,
    service_authority: ServiceAuthority | None = None,
) -> dict[str, object]:
    """Persist current conditions and enrich only new or escalated alerts.

    Owner decision D7: enrichment runs **under a named service identity**. ``service_authority`` is
    resolved by the headless caller (see ``application/service_identity.py``); when it is absent or
    not granted, no provider is called and the refusal travels in the result, because a worker that
    spends a provider credential with nobody's authority behind the call is the one control gap the
    register refused to leave implicit.
    """

    now = _as_utc(now_utc or datetime.now(UTC))
    candidates = [
        *_opportunity_candidates(session, now),
        *_strategy_candidates(session),
        *_source_failure_candidates(session),
        *_outage_candidates(session, now),
        *_opportunity_evaluator_candidates(session),
        *_stale_source_candidates(session, now),
        *_market_event_candidates(session, now),
    ]
    candidates += _price_move_candidates(session, now)
    candidates += _shortfall_candidates(session, now)
    candidates += _fundamentals_candidates(session, now)
    limit_candidates, limits_failed = _limit_candidates(session, now)
    candidates += limit_candidates
    active_fingerprints = {candidate.fingerprint for candidate in candidates}
    if limits_failed:
        # A calculation that could not run is not an all-clear: keep open limit alerts open.
        active_fingerprints |= {
            fingerprint
            for (fingerprint,) in session.query(MonitoringAlertRecord.fingerprint)
            .filter(MonitoringAlertRecord.category == "limits")
            .filter(MonitoringAlertRecord.resolved_at_utc.is_(None))
            .all()
        }
    # Alerts raised by an event consumer (LNG-2 cargo changes) are opened, updated and
    # withdrawn by that consumer; a scan that does not compute them must not resolve them.
    from eurogas_nexus.application.alert_routing import SELF_NOTIFYING

    active_fingerprints |= {
        fingerprint
        for (fingerprint,) in session.query(MonitoringAlertRecord.fingerprint)
        .filter(MonitoringAlertRecord.category.in_(sorted(SELF_NOTIFYING)))
        .filter(MonitoringAlertRecord.resolved_at_utc.is_(None))
        .all()
    }
    rows = [
        upsert_monitoring_alert(session, candidate, now_utc=now)
        for candidate in candidates
    ]
    resolved_count = resolve_absent_monitoring_alerts(
        session,
        active_fingerprints,
        now_utc=now,
    )
    session.commit()

    enriched_count = 0
    enrichment_refusal = ""
    enrichment_refusal_detail = ""
    if enrich_with_llm and max_llm_enrichments > 0:
        authority = service_authority or resolve_service_authority(session)
        if authority.granted:
            # The gate above decides whether to *try*; enrich_monitoring_alert re-checks the
            # authority at the provider boundary, so a stale or forged gate cannot spend a
            # credential and a boundary refusal is reported here rather than swallowed.
            (
                enriched_count,
                enrichment_refusal,
                enrichment_refusal_detail,
            ) = _enrich_pending_alerts(
                session,
                rows,
                now_utc=now,
                limit=max_llm_enrichments,
                api_key_loader=api_key_loader or load_provider_api_key,
                provider_call=provider_call or invoke_deepseek,
                actor=authority.principal,
            )
        else:
            # Reported, not swallowed: the worker's own log is where an operator learns that no
            # provider call happened and which configuration would allow one.
            enrichment_refusal = authority.refusal
            enrichment_refusal_detail = authority.detail
            _record_enrichment_refusal(session, authority, now_utc=now)

    return {
        "active_count": len(candidates),
        "resolved_count": resolved_count,
        "llm_enriched_count": enriched_count,
        "llm_enrichment_refused": enrichment_refusal,
        "llm_enrichment_refusal_detail": enrichment_refusal_detail,
    }


#: Returned when the organisation switched the enrichment AI use off (GOV-1).
AI_USE_SWITCHED_OFF = "ai_use_switched_off"


def enrich_monitoring_alert(
    session: Session,
    alert: MonitoringAlertRecord,
    *,
    now_utc: datetime | None = None,
    api_key_loader: ApiKeyLoader | None = None,
    provider_call: ProviderCall | None = None,
    actor: AuthenticatedPrincipal | None = None,
) -> DeepSeekCallResult:
    """Request a live DeepSeek explanation for one persisted alert.

    Owner decision D7 is enforced here, at the provider boundary where a credential is loaded and
    a provider is called - not only in the scan that scheduled the attempt. ``actor`` is the
    identity the caller resolved earlier; it must be the deployment's persisted service principal,
    which is re-read on every attempt, so a revocation, deactivation or downgrade between
    scheduling and invocation refuses the call even though the scheduling scan saw a granted
    authority. Nothing from ``actor`` is trusted for the grant itself: the role, status and scopes
    that authorise the call come from the persisted row, which is also the identity attributed.

    A refusal returns ``DeepSeekCallResult(status=ENRICHMENT_AUTHORITY_REFUSED,
    error_code=<declared service_identity code>)`` before any credential is loaded or any alert
    field is changed, and records the refusal in the audit trail.
    """

    now = _as_utc(now_utc or datetime.now(UTC))
    authority = bind_service_actor(session, actor)
    if not authority.granted or authority.principal is None:
        _record_enrichment_refusal(
            session,
            authority,
            now_utc=now,
            resource=f"monitoring_alert:{alert.alert_id}",
            actor=actor,
        )
        return DeepSeekCallResult(
            status=ENRICHMENT_AUTHORITY_REFUSED,
            error_code=authority.refusal,
        )

    principal = authority.principal
    from eurogas_nexus.application.ai_controls import ai_use_enabled, provenance

    if not ai_use_enabled("enrichment", session):
        # GOV-1: switched off in organisation settings. No credential is loaded, no provider
        # is called and the alert is left as it is: its own rule text stands.
        return DeepSeekCallResult(status="switched_off", error_code=AI_USE_SWITCHED_OFF)
    key_loader = api_key_loader or load_provider_api_key
    call = provider_call or invoke_deepseek
    api_key = key_loader("DEEPSEEK") or key_loader("LLM")
    alert.llm_provider_id = "DEEPSEEK"
    alert.llm_last_attempt_at_utc = now
    if not api_key:
        result = DeepSeekCallResult(
            status="missing_credential",
            error_code="credential_missing",
        )
        alert.llm_status = result.status
        session.commit()
        return result

    messages = _alert_enrichment_messages(alert)
    result = call(
        api_key=api_key,
        messages=messages,
        model=DEEPSEEK_DEFAULT_MODEL,
        **ENRICHMENT_CALL,
    )
    call_record = provenance(
        "enrichment",
        messages=messages,
        output=result.content if result.status == "success" else None,
        status=result.status,
    )
    alert.llm_status = result.status
    refusal = (
        _enrichment_refusal(alert, result.content)
        if result.status == "success" and result.content
        else None
    )
    if result.status == "success" and result.content and refusal is None:
        summary_en, summary_zh_cn = _parse_bilingual_summary(result.content)
        alert.llm_summary_en = summary_en
        alert.llm_summary_zh_cn = summary_zh_cn
    elif refusal is not None:
        # The model's text did not pass the checks every model text passes (ai_style); the
        # alert's own rule text stands and the summary stays empty.
        alert.llm_status = "checks_refused"
        alert.llm_summary_en = None
        alert.llm_summary_zh_cn = None
        warning = f"deepseek_enrichment:checks_refused:{refusal}"
        alert.warnings = list(dict.fromkeys([*(alert.warnings or []), warning]))
    else:
        warning = f"deepseek_enrichment:{result.error_code or result.status}"
        alert.warnings = list(dict.fromkeys([*(alert.warnings or []), warning]))
    _record_enrichment_use(session, principal, alert, result, now_utc=now, call=call_record)
    session.commit()
    return result


#: Words for each opportunity state that raises an alert (M7): what a trader reads in a list.
_OPPORTUNITY_STATE_WORDS = {
    "actionable": ("Opportunity open", "机会开启", "warning"),
    "indicative": ("Indicative opportunity", "指示性机会", "info"),
}


def _opportunity_candidates(
    session: Session,
    now_utc: datetime,
) -> list[MonitoringCandidate]:
    """One alert per opportunity the engine lists (M7): open while it is listed, resolved
    (withdrawn) the scan after it stops being viable.

    "Listed" is the engine's own threshold: surfaced after the persistence count, and in state
    ``actionable`` (warning) or ``indicative`` (info, standing on marks or settlements). An
    opportunity that expires, is converted to a case, goes blocked or falls to watch is no
    longer a candidate, so its alert resolves; that is the withdrawal. The fingerprint is the
    record id, which the engine keeps for one opportunity key, so a re-evaluation updates the
    alert and the notification outbox writes it once. The evidence names the books and source
    families behind it; ``alert_scope`` shows it only to callers who may read the opportunity.
    """

    from decimal import Decimal

    from eurogas_nexus.application.opportunities.listing import subject_of
    from eurogas_nexus.db.models import OpportunityRecord
    from eurogas_nexus.domain.opportunities.model import decimal_text

    rows = (
        session.query(OpportunityRecord)
        .filter(OpportunityRecord.surfaced.is_(True))
        .filter(OpportunityRecord.state.in_(tuple(_OPPORTUNITY_STATE_WORDS)))
        .order_by(OpportunityRecord.last_changed_utc.desc())
        .limit(500)
        .all()
    )
    candidates: list[MonitoringCandidate] = []
    for row in rows:
        expires = _as_utc(row.expires_at_utc)
        if expires <= now_utc:
            continue  # past its validity: withdrawn even before the engine's next run
        title_en, title_zh_cn, severity = _OPPORTUNITY_STATE_WORDS[row.state]
        subject = subject_of(row)
        figure = (
            f"{decimal_text(Decimal(str(row.value_amount)))} {row.value_currency}"
            if row.value_amount is not None
            else f"{decimal_text(Decimal(str(row.headline_value)))} {row.headline_unit}"
        )
        until = expires.strftime("%Y-%m-%d %H:%M UTC")
        candidates.append(
            MonitoringCandidate(
                fingerprint=f"opportunity:{row.opportunity_id}",
                category="opportunity",
                alert_type=row.type,
                severity=severity,
                title_en=f"{title_en}: {subject}",
                title_zh_cn=f"{title_zh_cn}：{subject}",
                message_en=(
                    f"{row.claim_text} {row.period_label}, {figure}. Valid until {until}; "
                    "for review, nothing is traded."
                ),
                message_zh_cn=(
                    f"{row.claim_text} {row.period_label}，{figure}。有效至 {until}；"
                    "仅供复核，不会下单。"
                ),
                entity_type="opportunity",
                entity_id=row.opportunity_id,
                event_time_utc=row.last_changed_utc,
                evidence_snapshot={
                    "opportunity_id": row.opportunity_id,
                    "type": row.type,
                    "lane": row.lane,
                    "state": row.state,
                    "version": row.version,
                    "period": row.period_label,
                    "book_ids": list(row.book_ids or []),
                    "source_families": list(row.source_families or []),
                    "expires_at_utc": expires.isoformat(),
                    "deadline_utc": (
                        _as_utc(row.deadline_utc).isoformat() if row.deadline_utc else None
                    ),
                    "evaluation_id": row.evaluation_id,
                },
                source_refs=[f"opportunity:{row.opportunity_id}", f"snapshot:{row.snapshot_id}"],
                warnings=[],
                simulated=bool(row.simulated),
                human_review_required=True,
            )
        )
    return candidates


def _strategy_candidates(session: Session) -> list[MonitoringCandidate]:
    rows = (
        session.query(StrategyAlertRecord)
        .filter(StrategyAlertRecord.acknowledged.is_(False))
        .order_by(StrategyAlertRecord.created_at_utc.desc())
        .limit(200)
        .all()
    )
    return [
        MonitoringCandidate(
            fingerprint=f"strategy:{row.alert_id}",
            category="strategy",
            alert_type=row.alert_type,
            severity=_normalize_severity(row.severity),
            title_en="Strategy monitor alert",
            title_zh_cn="策略监控告警",
            message_en=row.message_en,
            message_zh_cn=row.message_zh_cn,
            entity_type="strategy_run",
            entity_id=row.run_id,
            event_time_utc=row.created_at_utc,
            evidence_snapshot={
                "strategy_alert_id": row.alert_id,
                "run_id": row.run_id,
                "alert_type": row.alert_type,
                "severity": row.severity,
            },
            source_refs=[f"strategy-run:{row.run_id}"],
            human_review_required=True,
        )
        for row in rows
    ]


def _source_failure_candidates(session: Session) -> list[MonitoringCandidate]:
    """One alert candidate per source whose newest requested run failed.

    "Newest" stays the newest requested run (``started_at_utc`` desc), while the
    consecutive-failure count is the unbroken streak of runs that classify as
    failed through the shared ``domain/dataops/run_status.py`` vocabulary, so
    ``FAILED`` and the legacy ``failed`` spelling count identically. A run that
    is not classified as a failure - including success, pending, cancelled and
    unknown stored values - interrupts the streak, and the raw stored status
    stays visible in the evidence snapshot. The read is bounded to the newest
    500 persisted runs globally, so the streak is a lower bound whenever the
    history exceeds that window (documented limitation, not an all-history
    count).
    """

    rows = (
        session.query(IngestionRunRecord)
        .order_by(IngestionRunRecord.started_at_utc.desc())
        .limit(500)
        .all()
    )
    runs_by_source: dict[str, list[IngestionRunRecord]] = defaultdict(list)
    for row in rows:
        runs_by_source[row.source_name].append(row)

    candidates: list[MonitoringCandidate] = []
    for source_name, source_rows in runs_by_source.items():
        latest = source_rows[0]
        if not is_failed_run_status(latest.status):
            continue
        consecutive_failures = 0
        for row in source_rows:
            if not is_failed_run_status(row.status):
                break
            consecutive_failures += 1
        severity = "critical" if consecutive_failures >= 3 else "warning"
        candidates.append(
            MonitoringCandidate(
                fingerprint=f"source_failure:{source_name.lower()}",
                category="data_source",
                alert_type="ingestion_failed",
                severity=severity,
                title_en=f"{source_name} ingestion failed",
                title_zh_cn=f"{source_name} 数据更新失败",
                message_en=(
                    f"The latest {source_name} ingestion failed; "
                    f"{consecutive_failures} consecutive failure(s)."
                ),
                message_zh_cn=(
                    f"最近一次 {source_name} 数据更新失败；"
                    f"已连续失败 {consecutive_failures} 次。"
                ),
                entity_type="data_source",
                entity_id=source_name,
                event_time_utc=latest.started_at_utc,
                evidence_snapshot={
                    "run_id": latest.run_id,
                    "source_name": source_name,
                    "status": latest.status,
                    "started_at_utc": _as_utc(latest.started_at_utc).isoformat(),
                    "finished_at_utc": (
                        _as_utc(latest.finished_at_utc).isoformat()
                        if latest.finished_at_utc
                        else None
                    ),
                    "consecutive_failures": consecutive_failures,
                    "notes": latest.notes,
                },
                source_refs=[f"ingestion-run:{latest.run_id}"],
                warnings=[latest.notes] if latest.notes else [],
                human_review_required=True,
            )
        )
    return candidates


def _opportunity_evaluator_candidates(session: Session) -> list[MonitoringCandidate]:
    """One administrator alert per evaluator that failed in the latest opportunity run.

    Design J.2: an evaluator that fails produces no opportunity and one admin alert; the desk
    sees only the time of the last evaluation. The alert resolves when a later run succeeds.
    """

    from eurogas_nexus.db.models import OpportunityEvaluationRecord

    run = (
        session.query(OpportunityEvaluationRecord)
        .filter(OpportunityEvaluationRecord.finished_at_utc.is_not(None))
        .order_by(OpportunityEvaluationRecord.started_at_utc.desc())
        .first()
    )
    if run is None:
        return []
    out = []
    for name, status in sorted((run.evaluators_json or {}).items()):
        if status.get("status") != "failed":
            continue
        out.append(
            MonitoringCandidate(
                fingerprint=f"opportunity_evaluator:{name}",
                category="data_source",
                alert_type="opportunity_evaluator_failed",
                severity="warning",
                title_en=f"Opportunity evaluator {name} failed",
                title_zh_cn=f"机会评估器 {name} 运行失败",
                message_en=(
                    f"The {name} evaluator produced nothing in evaluation {run.evaluation_id} "
                    f"({status.get('error')}); its earlier records are unchanged."
                ),
                message_zh_cn=(
                    f"评估 {run.evaluation_id} 中 {name} 评估器未产生结果"
                    f"（{status.get('error')}）；其既有记录保持不变。"
                ),
                entity_type="opportunity_evaluator",
                entity_id=name,
                event_time_utc=run.started_at_utc,
                evidence_snapshot={
                    "evaluation_id": run.evaluation_id,
                    "evaluator": name,
                    "version": status.get("version"),
                    "error": status.get("error"),
                    "message": status.get("message"),
                },
                source_refs=[f"opportunity-evaluation:{run.evaluation_id}"],
                human_review_required=True,
            )
        )
    return out


#: A delivery of a market event waiting longer than this means the outbox is not being
#: drained (the scheduler or its worker is down, or a consumer keeps failing).
MARKET_EVENT_LAG_WARNING = timedelta(minutes=15)
MARKET_EVENT_LAG_CRITICAL = timedelta(hours=1)


def _stale_source_candidates(session: Session, now: datetime) -> list[MonitoringCandidate]:
    """One alert per enabled scheduled source past its stale threshold (M6).

    The source's freshness is evaluated now, from its last success, with the source's own
    policy and calendar (``domain/dataops/freshness.py``): a source that silently stopped
    succeeding goes stale even when no run fails, which ``_source_failure_candidates``
    cannot see. A closed calendar (weekends for exchange settlements) expects nothing. A
    source that has never succeeded alerts only once it has been enabled for longer than its
    stale threshold. The alert is one per source (by fingerprint) and resolves when the
    source is fresh again.
    """

    from eurogas_nexus.db.models import SourceRuntimeStateRecord
    from eurogas_nexus.domain.dataops.contracts import FreshnessState
    from eurogas_nexus.domain.dataops.freshness import (
        FreshnessEvidence,
        evaluate_source_freshness,
    )
    from eurogas_nexus.domain.dataops.registry import source_definitions

    definitions = {definition.source_id: definition for definition in source_definitions()}
    out = []
    for state in (
        session.query(SourceRuntimeStateRecord)
        .filter(SourceRuntimeStateRecord.enabled.is_(True))
        .order_by(SourceRuntimeStateRecord.source_id)
        .all()
    ):
        definition = definitions.get(state.source_id)
        if definition is None:
            continue
        last_success = _as_utc(state.last_success_at_utc) if state.last_success_at_utc else None
        evaluation = evaluate_source_freshness(
            definition,
            FreshnessEvidence(last_success_at_utc=last_success, access_granted=True),
            now_utc=now,
        )
        threshold = int(definition.freshness_policy.stale_after_minutes)
        if evaluation.state is FreshnessState.MISSING:
            since = state.activated_at_utc
            if since is None or now - _as_utc(since) <= timedelta(minutes=threshold):
                continue
        elif evaluation.state is not FreshnessState.STALE:
            continue
        age = (
            "it has never succeeded"
            if last_success is None
            else f"its last success was {_age_text(now - last_success)} ago"
        )
        age_zh = (
            "尚无成功记录"
            if last_success is None
            else f"最近一次成功在 {_age_text(now - last_success)} 前"
        )
        out.append(
            MonitoringCandidate(
                fingerprint=f"source_stale:{state.source_id.lower()}",
                category="data_source",
                alert_type="source_stale",
                severity="warning",
                title_en=f"{state.source_id} is stale",
                title_zh_cn=f"{state.source_id} 数据已过期",
                message_en=(
                    f"{state.source_id} should update at least every {threshold} minutes; "
                    f"{age}. Figures read from it may be out of date."
                ),
                message_zh_cn=(
                    f"{state.source_id} 应至少每 {threshold} 分钟更新一次；{age_zh}。"
                    "依赖它的数据可能已过时。"
                ),
                entity_type="data_source",
                entity_id=state.source_id,
                event_time_utc=last_success or now,
                evidence_snapshot={
                    "source_id": state.source_id,
                    "freshness_state": evaluation.state.value,
                    "reason": evaluation.reason,
                    "stale_after_minutes": threshold,
                    "last_success_at_utc": last_success.isoformat() if last_success else None,
                    "last_attempt_at_utc": (
                        _as_utc(state.last_attempt_at_utc).isoformat()
                        if state.last_attempt_at_utc
                        else None
                    ),
                    "circuit_state": state.circuit_state,
                },
                source_refs=[f"source:{state.source_id}"],
                human_review_required=True,
            )
        )
    return out


def _market_event_candidates(session: Session, now: datetime) -> list[MonitoringCandidate]:
    """Market event outbox health (M6): dead letters and deliveries left waiting.

    One alert per consumer with dead letters, naming the consumer and its oldest dead
    event; it resolves once the dead letters are replayed (``market_events.py replay``). One
    alert per consumer whose oldest due delivery has waited past
    :data:`MARKET_EVENT_LAG_WARNING` (critical past :data:`MARKET_EVENT_LAG_CRITICAL`).
    """

    from eurogas_nexus.application import market_events

    report = market_events.status(session, now_utc=now, dead_limit=3)
    out = []
    for consumer, item in sorted(report["consumers"].items()):
        dead = item["dead_letters"]
        dead_count = item["counts"].get(market_events.DEAD, 0)
        if dead_count:
            first = dead[0] if dead else {}
            out.append(
                MonitoringCandidate(
                    fingerprint=f"market_events:dead:{consumer}",
                    category="data_source",
                    alert_type="market_event_dead_letter",
                    severity="critical",
                    title_en=f"Market events failed for {consumer}",
                    title_zh_cn=f"{consumer} 的市场事件处理失败",
                    message_en=(
                        f"{dead_count} market event(s) could not be delivered to {consumer} "
                        f"after every retry; the first is {first.get('event_id')} "
                        f"({first.get('subject_key')}): {first.get('last_error')}. Fix the "
                        "cause, then replay them."
                    ),
                    message_zh_cn=(
                        f"{dead_count} 个市场事件重试后仍无法交付给 {consumer}；"
                        f"首个为 {first.get('event_id')}（{first.get('subject_key')}）："
                        f"{first.get('last_error')}。修复原因后请重放。"
                    ),
                    entity_type="market_event_consumer",
                    entity_id=consumer,
                    event_time_utc=now,
                    evidence_snapshot={
                        "consumer": consumer,
                        "dead_letters": dead_count,
                        "first": dead[:3],
                    },
                    source_refs=[f"market-event:{row.get('event_id')}" for row in dead[:3]],
                    human_review_required=True,
                )
            )
        lag = item.get("oldest_due_lag_seconds")
        if lag is not None and lag > MARKET_EVENT_LAG_WARNING.total_seconds():
            waited = timedelta(seconds=lag)
            out.append(
                MonitoringCandidate(
                    fingerprint=f"market_events:lag:{consumer}",
                    category="data_source",
                    alert_type="market_event_lag",
                    severity=(
                        "critical" if waited > MARKET_EVENT_LAG_CRITICAL else "warning"
                    ),
                    title_en=f"Market events are waiting for {consumer}",
                    title_zh_cn=f"{consumer} 的市场事件积压",
                    message_en=(
                        f"The oldest market event due to {consumer} has waited "
                        f"{_age_text(waited)}; opportunities that depend on it are not being "
                        "refreshed. Check that the data-operations scheduler is running."
                    ),
                    message_zh_cn=(
                        f"交付给 {consumer} 的最早市场事件已等待 {_age_text(waited)}；"
                        "依赖它的机会未被刷新。请检查数据运维调度器是否在运行。"
                    ),
                    entity_type="market_event_consumer",
                    entity_id=consumer,
                    event_time_utc=now,
                    evidence_snapshot={
                        "consumer": consumer,
                        "oldest_due_lag_seconds": round(lag, 1),
                        "counts": item["counts"],
                    },
                    source_refs=[f"market-event-consumer:{consumer}"],
                    human_review_required=True,
                )
            )
    return out


def _age_text(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 120:
        return f"{minutes} min"
    hours = minutes // 60
    return f"{hours} h" if hours < 48 else f"{hours // 24} days"


# An outage worth a trader's attention: most of the asset out, or a large volume either way.
OUTAGE_CRITICAL_SHARE = 0.5
OUTAGE_WARNING_SHARE = 0.25
OUTAGE_WARNING_GWH_D = 100.0
OUTAGE_LOOKAHEAD = timedelta(hours=24)


def _outage_candidates(session: Session, now: datetime) -> list[MonitoringCandidate]:
    """REMIT outages active now or starting within 24 hours that move supply.

    Deterministic: the share of technical capacity out and the GWh/d decide. The alert's
    fingerprint is the message id, so it resolves by itself when the outage ends or is
    dismissed, and a revision updates it in place.
    """

    from eurogas_nexus.application.remit_outages import load_outage_rows

    candidates: list[MonitoringCandidate] = []
    for row in load_outage_rows(session, now=now, horizon_days=2):
        start = datetime.fromisoformat(str(row["start_utc"]))
        if start > now + OUTAGE_LOOKAHEAD:
            continue
        technical = row.get("technical_capacity")
        unavailable = row.get("unavailable_capacity")
        share = (
            float(unavailable) / float(technical)
            if technical and unavailable is not None
            else None
        )
        gwh = row.get("unavailable_gwh_d")
        gwh = float(gwh) if gwh is not None else None
        if share is not None and share >= OUTAGE_CRITICAL_SHARE:
            severity = "critical"
        elif (share is not None and share >= OUTAGE_WARNING_SHARE) or (
            gwh is not None and gwh >= OUTAGE_WARNING_GWH_D
        ):
            severity = "warning"
        else:
            continue
        asset = str(row["facility_name"])
        zone = str(row.get("balancing_zone") or "")
        active = row.get("status") == "active"
        volume = f"{gwh:,.0f} GWh/d" if gwh is not None else f"{unavailable} {row.get('unit')}"
        share_text = f" ({share:.0%} of capacity)" if share is not None else ""
        when_en = "out now" if active else f"from {start:%d %b %H:%M} UTC"
        when_zh = "目前停运" if active else f"自 {start:%m-%d %H:%M} UTC 起"
        candidates.append(
            MonitoringCandidate(
                fingerprint=f"outage:{row['event_id']}",
                category="physical",
                alert_type="outage",
                severity=severity,
                title_en=f"{asset} ({zone}) {volume} {when_en}",
                title_zh_cn=f"{asset}（{zone}）{volume} {when_zh}",
                message_en=(
                    f"{row.get('event_type', 'unspecified').capitalize()} outage at {asset}: "
                    f"{volume}{share_text} unavailable, {when_en}. "
                    f"Reason: {row.get('description') or 'not stated'}."
                ),
                message_zh_cn=(
                    f"{asset} 停运：不可用 {volume}{share_text}，{when_zh}。"
                    f"原因：{row.get('description') or '未说明'}。"
                ),
                entity_type="outage",
                entity_id=str(row["event_id"]),
                event_time_utc=start,
                evidence_snapshot={
                    key: row.get(key)
                    for key in (
                        "event_id", "version", "facility_name", "balancing_zone", "status",
                        "event_type", "start_utc", "end_utc", "published_at_utc",
                        "technical_capacity", "unavailable_capacity", "unavailable_gwh_d",
                        "unit", "description", "market_participant",
                    )
                },
                source_refs=[f"remit:{row['event_id']}:v{row.get('version')}"],
                # A fictional demo message is marked like the Network list marks it.
                simulated=str(row.get("source_reference") or "").lower().startswith("demo"),
                human_review_required=True,
            )
        )
    return candidates



# ------------------------------------------------------------------ price moves (G3)

#: The smallest move a person can choose for the situational strip; the strip applies each
#: person's own threshold (2, 3, 5 or 10 %) on top of this.
PRICE_MOVE_MIN_PCT = 2.0
PRICE_MOVE_CRITICAL_PCT = 10.0


def _price_move_candidates(session: Session, now: datetime) -> list[MonitoringCandidate]:
    """Day-ahead and front-month closes that moved at least 2 % against the prior close.

    The closes are the Today board's own (``daily_closes.daily_rows``), read firm-wide as
    non-display use; one series per hub and tenor, a provider's closes winning over simulated
    ones. A close older than four days, or one whose prior close is more than four days
    earlier, is not a day move. Each alert names its source system, and a reader sees it only
    when entitled to that family (``alert_scope``); simulated closes are marked simulated.
    """

    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.application.projections.daily_closes import daily_rows, in_native_unit
    from eurogas_nexus.domain.portfolio.position_ladder import MAX_VAR_GAP_DAYS

    today = now.date()
    try:
        rows = daily_rows(firm_caller(None, session), today - timedelta(days=10), today)
    except Exception:  # noqa: BLE001 - no price read, no price alert; the others stand
        return []
    series: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        if row["tenor"] not in {"day-ahead", "month-ahead"} or not row.get("hub_resolved", True):
            continue
        if not row.get("source_system"):
            continue  # only a named source raises an alert
        series.setdefault((row["hub"], row["tenor"], row["source_system"]), {})[row["day"]] = row
    best: dict[tuple[str, str], tuple] = {}
    for (hub, tenor, source), closes in series.items():
        rank = (not closes[max(closes)]["simulated"], max(closes))
        if (hub, tenor) not in best or rank > best[(hub, tenor)][0]:
            best[(hub, tenor)] = (rank, source, closes)
    candidates: list[MonitoringCandidate] = []
    for (hub, tenor), (_, source, closes) in sorted(best.items()):
        days = sorted(closes)
        if len(days) < 2 or (today - days[-1]).days > MAX_VAR_GAP_DAYS:
            continue
        if (days[-1] - days[-2]).days > MAX_VAR_GAP_DAYS:
            continue
        last, prior = closes[days[-1]], closes[days[-2]]
        price, unit = in_native_unit(hub, last["price"], last["unit"])
        previous, _ = in_native_unit(hub, prior["price"], last["unit"])
        if not previous:
            continue
        move = 100.0 * (price - previous) / abs(previous)
        if abs(move) < PRICE_MOVE_MIN_PCT:
            continue
        product = "DA" if tenor == "day-ahead" else "FM"
        simulated = bool(last["simulated"])
        candidates.append(
            MonitoringCandidate(
                fingerprint=f"price_move:{hub}:{product}:{days[-1].isoformat()}",
                category="market",
                alert_type="price_move",
                severity="critical" if abs(move) >= PRICE_MOVE_CRITICAL_PCT else "warning",
                title_en=f"{hub} {product} {move:+.1f}% vs prior close ({price:,.2f} {unit})",
                title_zh_cn=f"{hub} {product} 较前收盘 {move:+.1f}%（{price:,.2f} {unit}）",
                message_en=(
                    f"{hub} {product} closed at {price:,.3f} {unit} on {days[-1]:%d %b}, "
                    f"{move:+.1f}% against {previous:,.3f} on {days[-2]:%d %b}."
                ),
                message_zh_cn=(
                    f"{hub} {product} 于 {days[-1]:%m-%d} 收于 {price:,.3f} {unit}，"
                    f"较 {days[-2]:%m-%d} 的 {previous:,.3f} 变动 {move:+.1f}%。"
                ),
                entity_type="market_close",
                entity_id=f"{hub}:{product}",
                event_time_utc=now,
                evidence_snapshot={
                    "hub": hub,
                    "product": product,
                    "tenor": tenor,
                    "move_pct": round(move, 2),
                    "price": round(price, 4),
                    "previous_price": round(previous, 4),
                    "unit": unit,
                    "close_day": days[-1].isoformat(),
                    "previous_day": days[-2].isoformat(),
                    "source_system": source,
                    "simulated": simulated,
                },
                source_refs=[f"market-close:{source}:{hub}:{tenor}:{days[-1].isoformat()}"],
                simulated=simulated,
                human_review_required=True,
            )
        )
    return candidates


# ------------------------------------------------------------------ delivery shortfalls (G5)

#: Gas days a shortfall stays an alert after it was allocated.
SHORTFALL_LOOKBACK_DAYS = 3


def _shortfall_candidates(session: Session, now: datetime) -> list[MonitoringCandidate]:
    """Contracts that delivered short of their nomination by more than their tolerance.

    Per contract and gas day of the last three: allocated against nominated, against the
    contract's own delivery tolerance. A day not yet allocated is not a shortfall. The alert
    carries the contract's book, so book isolation applies (``alert_scope``).
    """

    from eurogas_nexus.db.models import ContractDeliveryRecord, UpstreamResourceContractRecord

    first = now.date() - timedelta(days=SHORTFALL_LOOKBACK_DAYS)
    rows = (
        session.query(ContractDeliveryRecord)
        .filter(ContractDeliveryRecord.gas_day >= first)
        .filter(ContractDeliveryRecord.allocated_mwh.isnot(None))
        .filter(ContractDeliveryRecord.nominated_mwh > 0)
        .all()
    )
    contracts = {
        row.contract_id: row
        for row in session.query(UpstreamResourceContractRecord).filter(
            UpstreamResourceContractRecord.contract_id.in_({row.contract_id for row in rows})
        )
    } if rows else {}
    candidates: list[MonitoringCandidate] = []
    for row in rows:
        contract = contracts.get(row.contract_id)
        if contract is None:
            continue
        nominated = float(row.nominated_mwh)
        shortfall = nominated - float(row.allocated_mwh)
        pct = 100.0 * shortfall / nominated
        tolerance = float(contract.delivery_tolerance_pct or 0.0)
        if shortfall <= 0 or pct <= tolerance:
            continue
        name = contract.contract_name
        candidates.append(
            MonitoringCandidate(
                fingerprint=f"shortfall:{row.contract_id}:{row.gas_day.isoformat()}",
                category="delivery",
                alert_type="shortfall",
                severity="critical" if pct > 2 * tolerance else "warning",
                title_en=f"{name} delivered {shortfall:,.0f} MWh short on {row.gas_day:%d %b}",
                title_zh_cn=f"{name} 于 {row.gas_day:%m-%d} 交付短缺 {shortfall:,.0f} MWh",
                message_en=(
                    f"Allocated {float(row.allocated_mwh):,.0f} MWh against {nominated:,.0f} MWh "
                    f"nominated: {pct:.1f}% short, beyond the {tolerance:.1f}% tolerance."
                ),
                message_zh_cn=(
                    f"分配 {float(row.allocated_mwh):,.0f} MWh，提名 {nominated:,.0f} MWh："
                    f"短缺 {pct:.1f}%，超出 {tolerance:.1f}% 容差。"
                ),
                entity_type="contract_delivery",
                entity_id=f"{row.contract_id}:{row.gas_day.isoformat()}",
                event_time_utc=now,
                evidence_snapshot={
                    "contract_id": row.contract_id,
                    "contract_name": name,
                    "gas_day": row.gas_day.isoformat(),
                    "nominated_mwh": nominated,
                    "allocated_mwh": float(row.allocated_mwh),
                    "shortfall_mwh": round(shortfall, 1),
                    "shortfall_pct": round(pct, 2),
                    "tolerance_pct": tolerance,
                    "point": row.point,
                    "tso": row.tso,
                    "source_system": row.source_system,
                    "book_ids": [contract.book_id] if contract.book_id else [],
                },
                source_refs=[f"contract-delivery:{row.contract_id}:{row.gas_day.isoformat()}"],
                simulated=row.source_system == "DEMO",
                human_review_required=True,
            )
        )
    return candidates


# ------------------------------------------------------------------ fundamentals surprises

#: A daily figure is a surprise when it is this far from its 7-day average...
FUNDAMENTALS_BAND_PCT = 30.0
#: ...and at least this far in its own unit, so a near-zero average does not alarm.
FUNDAMENTALS_FLOOR = {"storage_change": 0.3, "lng_sendout": 0.1}


def _fundamentals_candidates(session: Session, now: datetime) -> list[MonitoringCandidate]:
    """NW Europe storage daily change and LNG send-out outside their band vs the 7-day average.

    Summed over the north-west European countries (the balance's scope), on days every
    reporting country covers. The comparison is the mean of the seven days before the latest.
    """

    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.db.models.observation import LngObservationRecord as Lng
    from eurogas_nexus.db.models.observation import StorageObservationRecord as Storage
    from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES

    first = now - timedelta(days=12)
    naive = session.get_bind().dialect.name == "sqlite"
    bound = first.replace(tzinfo=None) if naive else first

    def daily(model, column) -> tuple[dict, set[str]]:
        by_day: dict = {}
        sources: set[str] = set()
        for record in (
            session.query(model.period_start_utc, model.country, model.source_system, column)
            .filter(model.country.in_(NWE_COUNTRIES), model.period_start_utc >= bound)
            .filter(column.isnot(None))
            # A row whose provider identifiers do not resolve is withheld (WITHHOLDING_RULE).
            .filter(identity_clause(session, model))
        ):
            day = _as_utc(record[0]).date()
            by_day.setdefault(day, {}).setdefault(record[1], 0.0)
            by_day[day][record[1]] += float(record[3])
            sources.add(str(record[2]))
        if not by_day:
            return {}, sources
        countries = set.intersection(*(set(values) for values in by_day.values()))
        return (
            {day: sum(values[c] for c in countries) for day, values in by_day.items()},
            sources,
        )

    inventory, storage_sources = daily(Storage, Storage.inventory_twh)
    days = sorted(inventory)
    change = {b: inventory[b] - inventory[a] for a, b in zip(days, days[1:], strict=False)}
    sendout, lng_sources = daily(Lng, Lng.send_out_twh_d)
    candidates: list[MonitoringCandidate] = []
    for series, values, unit, sources, label_en, label_zh in (
        ("storage_change", change, "TWh", storage_sources, "storage change", "储气日变化"),
        ("lng_sendout", sendout, "TWh/d", lng_sources, "LNG send-out", "LNG 外输"),
    ):
        ordered = sorted(values)
        if len(ordered) < 8:
            continue
        latest_day = ordered[-1]
        latest = values[latest_day]
        average = sum(values[d] for d in ordered[-8:-1]) / 7
        gap = latest - average
        if abs(gap) < FUNDAMENTALS_FLOOR[series]:
            continue
        deviation = 100.0 * gap / abs(average) if average else 100.0
        if abs(deviation) < FUNDAMENTALS_BAND_PCT:
            continue
        source = sorted(sources)[0] if sources else ""
        simulated = any(item.endswith("_Sim") for item in sources)
        candidates.append(
            MonitoringCandidate(
                fingerprint=f"fundamentals:{series}:{latest_day.isoformat()}",
                category="fundamentals",
                alert_type=series,
                severity="warning",
                title_en=(
                    f"NW Europe {label_en} {latest:+,.2f} {unit} on {latest_day:%d %b} "
                    f"against a 7-day average of {average:+,.2f} {unit}"
                ),
                title_zh_cn=(
                    f"西北欧{label_zh} {latest_day:%m-%d} 为 {latest:+,.2f} {unit}，"
                    f"7 日均值 {average:+,.2f} {unit}"
                ),
                message_en=(
                    f"{label_en.capitalize()} {latest:,.2f} {unit} against a 7-day average of "
                    f"{average:,.2f} {unit} ({', '.join(sorted(sources))})."
                ),
                message_zh_cn=f"{label_zh} {latest:,.2f} {unit}，7 日均值 {average:,.2f} {unit}。",
                entity_type="fundamentals_series",
                entity_id=series,
                event_time_utc=now,
                evidence_snapshot={
                    "series": series,
                    "value": round(latest, 3),
                    "average_7d": round(average, 3),
                    "difference": round(gap, 3),
                    "deviation_pct": round(deviation, 1),
                    "unit": unit,
                    "day": latest_day.isoformat(),
                    "source_system": source,
                    "simulated": simulated,
                },
                source_refs=[f"fundamentals:{series}:{source}:{latest_day.isoformat()}"],
                simulated=simulated,
                human_review_required=True,
            )
        )
    return candidates


def _limit_candidates(
    session: Session, now: datetime
) -> tuple[list[MonitoringCandidate], bool]:
    """Credit lines and trader mandates in breach, on watch, expired or incomplete.

    The figures are the risk pages' own (``application/limits_service``), computed firm-wide
    (``firm_caller``: every book, the non-display-licensed families). The second value is True
    when the calculation could not run, so open alerts are kept.
    """

    from eurogas_nexus.application.caller import firm_caller
    from eurogas_nexus.application.limits_service import (
        credit_exposure_rows,
        mandate_usage_rows,
    )
    from eurogas_nexus.db.models import CreditLineRecord, TraderMandateRecord

    if (
        session.query(CreditLineRecord.counterparty_id).first() is None
        and session.query(TraderMandateRecord.mandate_id).first() is None
    ):
        return [], False
    # The firm-wide calculation, never the enrichment service principal's own scopes: that
    # identity exists to authorise the model call (owner decision D7) and typically holds no
    # book and no market-data family, so computing under it left every leg unvalued and turned
    # each breach into "incomplete" while the risk page showed the breach. Automated risk
    # calculation is non-display use: every book plus the families with a current non-display
    # licence (``firm_caller``). Who may *see* each alert is still decided per reader
    # (``application/alert_scope.py``).
    caller = firm_caller(None, session)
    today = now.date()
    try:
        credit = credit_exposure_rows(caller, today)
        mandates = mandate_usage_rows(caller, today)
    except Exception:  # noqa: BLE001 - a failed calculation must not clear standing alerts
        return [], True
    candidates = [
        candidate
        for row, books in zip(credit.rows, credit.books, strict=True)
        if (candidate := _credit_candidate(row, books, now)) is not None
    ]
    candidates += [
        candidate
        for row, books in zip(mandates.rows, mandates.books, strict=True)
        if (candidate := _mandate_candidate(row, books, now)) is not None
    ]
    stale_marks = _marks_stale_candidate(credit.rows, credit.books, now)
    if stale_marks is not None:
        candidates.append(stale_marks)
    demo = [w for w in [*credit.warnings, *mandates.warnings] if w.startswith("DEMO")]
    if demo:
        # Figures on demo marks say so wherever the alert is shown (AGENTS.md rule 17).
        candidates = [
            replace(candidate, simulated=True, warnings=demo[:1]) for candidate in candidates
        ]
    return candidates, False


def _marks_stale_candidate(rows: list[dict], books: list[tuple[str, ...]], now: datetime):
    """One alert when the marks behind the credit limits are older than one business day.

    QA-R-07: a breach or watch raised from six-day-old marks reads like a fresh one. The age is
    the risk rows' own (``marks_as_of`` and ``state`` from ``limits_service``, judged by the
    one business-day rule in ``domain.monitoring.freshness.close_state``), so the alert, the
    Limits page and Today agree. It is a warning, late or stale (the evidence says which):
    stale marks make a figure unreliable, not a breach, and a critical limits alert reads as a
    breach on Today and waits for acknowledgement. Lines with no leg to mark, or no close at all
    (``never``: the line is already ``incomplete``), raise nothing here.
    The alert resolves when the marks are current.
    """

    affected = [
        (row, row_books)
        for row, row_books in zip(rows, books, strict=True)
        if row.get("state") in {"late", "stale"} and row.get("legs")
    ]
    if not affected:
        return None
    stale = any(row["state"] == "stale" for row, _ in affected)
    oldest = min(str(row["marks_as_of"]) for row, _ in affected if row.get("marks_as_of"))
    names = ", ".join(sorted(str(row["counterparty"]) for row, _ in affected)[:5])
    more = len(affected) - min(len(affected), 5)
    listed = names + (f" and {more} more" if more else "")
    count = len(affected)
    lines = "credit line" if count == 1 else "credit lines"
    return MonitoringCandidate(
        fingerprint="marks_stale:credit",
        category="limits",
        alert_type="marks_stale",
        severity="warning",
        title_en=f"Marks behind {count} {lines} date from {oldest}",
        title_zh_cn=f"{count} 条授信额度所用估值价格日期为 {oldest}",
        message_en=(
            f"The exposure of {listed} is valued at closes older than one business day "
            f"(oldest {oldest}). Breach and watch figures on these lines are not current; "
            "check the price feeds before acting on them."
        ),
        message_zh_cn=(
            f"{listed} 的敞口使用超过一个工作日的收盘价估值（最早 {oldest}）。"
            "这些额度的超限与关注数字并非最新，请先检查价格数据源。"
        ),
        entity_type="marks",
        entity_id="credit",
        event_time_utc=now,
        evidence_snapshot={
            "marks_as_of": oldest,
            "state": "stale" if stale else "late",
            "rule": "close_state: previous weekday's close is current",
            "lines": [
                {
                    "counterparty_id": row["counterparty_id"],
                    "counterparty": row["counterparty"],
                    "marks_as_of": row.get("marks_as_of"),
                    "state": row["state"],
                }
                for row, _ in affected
            ],
            # Book-scoped like the credit alerts: shown only to who can see every book behind.
            "book_ids": sorted({book for _, row_books in affected for book in row_books}),
        },
        source_refs=[f"credit-line:{row['counterparty_id']}" for row, _ in affected][:20],
        human_review_required=True,
    )


def _credit_candidate(row: dict, books: tuple[str, ...], now: datetime):
    status = row["status"]
    name, currency = row["counterparty"], row["currency"]
    net, limit = row["net_exposure"], row["limit"]
    used = row["utilisation_pct"]
    used_text = f"{used:.0f}%" if used is not None else "n/a"
    figures = " ".join(credit_lines(row))
    figures_zh = (
        f"净敞口 {money(net, currency)}，额度 {money(limit, currency)}（{used_text}），"
        f"余量 {money(row['headroom'], currency)}。"
    )
    if status == "breach":
        severity = "critical"
        title_en = f"{name} credit breach: {used_text} of {money(limit, currency)} limit"
        title_zh = f"{name} 信用超限：占用 {used_text}"
    elif status == "expired" and (net or 0) > 0:
        severity = "critical"
        exposure = money(net, currency)
        title_en = f"{name} credit line expired {row['valid_until']}, exposure {exposure}"
        title_zh = f"{name} 授信已于 {row['valid_until']} 到期，敞口 {exposure}"
    elif status == "watch":
        severity = "warning"
        title_en = f"{name} credit at {used_text} of limit"
        title_zh = f"{name} 信用占用 {used_text}"
    elif status == "incomplete":
        severity = "warning"
        title_en = f"{name} credit exposure incomplete: {row['unvalued_legs']} legs without a mark"
        title_zh = f"{name} 信用敞口不完整：{row['unvalued_legs']} 笔无估值"
    else:
        return None
    return MonitoringCandidate(
        fingerprint=f"credit:{row['counterparty_id']}",
        category="limits",
        alert_type="credit",
        severity=severity,
        title_en=title_en,
        title_zh_cn=title_zh,
        message_en=figures,
        message_zh_cn=figures_zh,
        entity_type="credit_line",
        entity_id=str(row["counterparty_id"]),
        event_time_utc=now,
        evidence_snapshot={**row, "book_ids": list(books)},
        source_refs=[f"credit-line:{row['counterparty_id']}"],
        human_review_required=True,
    )


def _mandate_candidate(row: dict, books: tuple[str, ...], now: datetime):
    status = row["status"]
    name = row["name"] or row["trader"]
    used = row["utilisation_pct"]
    used_text = f"{used:.0f}%" if used is not None else "n/a"
    if status == "breach":
        severity = "critical"
        title_en = f"{name} mandate breach: {row['breaches'] or used_text}"
        title_zh = f"{name} 授权超限：{row['breaches'] or used_text}"
    elif status == "expired":
        severity = "warning"
        title_en = f"{name} mandate expired {row['valid_until']}"
        title_zh = f"{name} 授权已于 {row['valid_until']} 到期"
    elif status == "watch":
        severity = "warning"
        title_en = f"{name} mandate at {used_text} of size limit"
        title_zh = f"{name} 授权规模占用 {used_text}"
    else:
        return None
    message = " ".join(mandate_lines(row))
    return MonitoringCandidate(
        fingerprint=f"mandate:{row['mandate_id']}",
        category="limits",
        alert_type="mandate",
        severity=severity,
        title_en=title_en,
        title_zh_cn=title_zh,
        message_en=message,
        message_zh_cn=f"规模占用 {used_text}；账簿：{row['books']}。",
        entity_type="trader_mandate",
        entity_id=str(row["mandate_id"]),
        event_time_utc=now,
        evidence_snapshot={**row, "book_ids": list(books)},
        source_refs=[f"mandate:{row['mandate_id']}"],
        human_review_required=True,
    )


def _enrich_pending_alerts(
    session: Session,
    rows: list[MonitoringAlertRecord],
    *,
    now_utc: datetime,
    limit: int,
    api_key_loader: ApiKeyLoader,
    provider_call: ProviderCall,
    actor: AuthenticatedPrincipal | None = None,
) -> tuple[int, str, str]:
    """Enrich eligible alerts under the acting service identity (owner decision D7).

    ``actor`` is the principal the enrichment runs as; the provider boundary re-checks it against
    the persisted identity before every call. Returns the enriched count and, when the boundary
    refused, the declared refusal code plus a detail sentence for the caller's report. The loop
    stops at the first refusal: the authority condition applies to every remaining alert, and one
    refusal is one auditable event rather than a burst of duplicate ones.
    """
    from eurogas_nexus.application.ai_controls import ai_use_enabled

    if not ai_use_enabled("enrichment", session):
        return 0, AI_USE_SWITCHED_OFF, "enrichment is switched off in organisation settings"
    retry_before = now_utc - timedelta(minutes=5)
    eligible = [
        row
        for row in rows
        if row.status == "open"
        and row.llm_status != "success"
        and (
            row.llm_last_attempt_at_utc is None
            or _as_utc(row.llm_last_attempt_at_utc) <= retry_before
        )
    ]
    enriched = 0
    for row in sorted(
        eligible,
        key=lambda item: (item.severity != "critical", item.detected_at_utc),
    )[:limit]:
        result = enrich_monitoring_alert(
            session,
            row,
            now_utc=now_utc,
            api_key_loader=api_key_loader,
            provider_call=provider_call,
            actor=actor,
        )
        if result.status == "success":
            enriched += 1
        elif result.status == ENRICHMENT_AUTHORITY_REFUSED:
            code = result.error_code or "service_authority_refused"
            return enriched, code, (
                f"refused at the provider boundary (reason={code}); see the "
                "governance.ai_authority audit record for the identity and configuration detail"
            )
    return enriched, "", ""


def _record_enrichment_refusal(
    session: Session,
    authority: ServiceAuthority,
    *,
    now_utc: datetime,
    resource: str = "monitoring_alerts",
    actor: AuthenticatedPrincipal | None = None,
) -> None:
    """Record that enrichment was refused, and why.

    A refusal is an operational event: the deployment is running a monitoring pipeline whose
    analysis stage is disabled by configuration. Recording it is what stops that from looking like
    "nothing to report". ``resource`` names the alert when the refusal came from the provider
    boundary. ``actor``, when present, is the principal that *claimed* the call, so a mismatch is
    attributed to the claimant rather than to a configured identity that never acted, and the
    detail carries no credential, prompt or evidence content.
    """

    from eurogas_nexus.db.repositories.audit import record_audit_event

    claimed_name = (getattr(actor, "name", "") or "").strip() if actor is not None else ""
    record_audit_event(
        session,
        event_type="governance.ai_authority",
        action="monitoring.enrichment.refused",
        resource=resource[:128],
        principal=(
            claimed_name or configured_service_principal_name() or "unconfigured"
        )[:64],
        outcome="denied",
        severity="warning",
        detail=f"reason={authority.refusal}; {authority.detail}",
        source_system="monitoring-worker",
        now_utc=now_utc,
    )
    session.commit()


def _record_enrichment_use(
    session: Session,
    principal: AuthenticatedPrincipal,
    alert: MonitoringAlertRecord,
    result: DeepSeekCallResult,
    *,
    now_utc: datetime,
    call: dict | None = None,
) -> None:
    """Record one provider call against the service identity it actually ran as.

    Called only after the authority boundary passed and the provider was invoked, so the row is
    evidence about a call rather than a declaration that one was intended. It carries the
    persisted principal's name, id and role - never the caller-supplied dataclass - and no
    credential, prompt or evidence content.
    """

    from eurogas_nexus.application.ai_controls import provenance_summary
    from eurogas_nexus.db.repositories.audit import record_audit_event

    record_audit_event(
        session,
        event_type="governance.ai_authority",
        action="monitoring.enrichment.provider_call",
        resource=f"monitoring_alert:{alert.alert_id}"[:128],
        principal=principal.name[:64],
        outcome="success" if result.status == "success" else "failed",
        severity="info",
        detail=(
            f"actor_id={principal.principal_id}; role={principal.role}; "
            f"provider={alert.llm_provider_id}; status={result.status}"
            + (f"; error={result.error_code}" if result.error_code else "")
        ),
        source_system="monitoring-worker",
        now_utc=now_utc,
        # GOV-1: prompt version, model id and input/output hashes (never the text).
        after_summary=provenance_summary([call]) if call else None,
    )


def _alert_enrichment_messages(alert: MonitoringAlertRecord) -> list[dict[str, str]]:
    # Minimised (application/ai_payloads.py): no ids, references or earlier warnings.
    from eurogas_nexus.application.ai_payloads import alert_for_enrichment

    snapshot = alert_for_enrichment(alert)
    return [
        {
            "role": "system",
            "content": (
                f"{DESK_NOTE_RULES} The input is a deterministic monitoring alert; say why "
                "it matters to a gas desk. If inputs are simulated, say so. Return JSON "
                "only with string fields summary_en and summary_zh_cn, the same note in "
                "English and Simplified Chinese."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(snapshot, ensure_ascii=False, default=str),
        },
    ]


def _enrichment_refusal(alert: MonitoringAlertRecord, content: str) -> str | None:
    """The check that refused either summary, or ``None`` when both pass."""

    from eurogas_nexus.application.ai_style import text_verdict

    summary_en, summary_zh_cn = _parse_bilingual_summary(content)
    if summary_en == summary_zh_cn == content.strip():
        return "format"
    evidence_text = _alert_enrichment_messages(alert)[1]["content"]
    for text, language in ((summary_en, "en"), (summary_zh_cn, "zh-CN")):
        # Each half of the bilingual summary must be in its own language.
        verdict = text_verdict(
            text, evidence_text=evidence_text, simulated=bool(alert.simulated),
            language=language,
        )
        if not verdict.ok:
            return verdict.check
    return None


def _parse_bilingual_summary(content: str) -> tuple[str, str]:
    candidate = content.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].lstrip()
    try:
        payload: dict[str, Any] = json.loads(candidate)
        summary_en = str(payload.get("summary_en") or "").strip()
        summary_zh_cn = str(payload.get("summary_zh_cn") or "").strip()
        if summary_en and summary_zh_cn:
            return summary_en, summary_zh_cn
    except (TypeError, ValueError):
        pass
    return content.strip(), content.strip()


def _normalize_severity(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"critical", "error", "high"}:
        return "critical"
    if normalized in {"warning", "warn", "medium"}:
        return "warning"
    return "info"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
