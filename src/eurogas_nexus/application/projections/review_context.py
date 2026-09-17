"""ReviewContext projection (Architecture V2 Wave 5, priority 3).

One coherent read model for the review workflow: the review decisions recorded
against an artifact, the evidence that artifact still resolves to, and the
warnings a reviewer must see - all on one as-of instant, with per-slice
freshness.

What it composes (existing services only, never a re-implementation):

- ``db.repositories.review.list_review_decisions`` - the same read
  ``GET /api/review/decisions`` serves;
- one evidence resolver per ``domain.ontology.vocabulary.ReviewEntityType``:
  ``db.repositories.market_intelligence.get_intraday_opportunity``,
  ``db.repositories.strategy.get_strategy_run``,
  ``GeneratedReportRecord`` (the row ``POST /api/reports/portfolio`` persists)
  and ``db.repositories.agents`` (agent run replay is the review-pack evidence,
  the same payload ``GET /api/agent/runs/{id}/replay`` returns);
- ``db.repositories.monitoring.monitoring_summary`` for the open-alert posture
  that a review decision must be able to cite.

Evidence that cannot be resolved is reported as an explicit unknown
(``available = false`` plus a stable ``unavailable_reason``), never as an empty
artifact, and the payload warns ``REVIEW_EVIDENCE_INCOMPLETE`` so a reviewer
cannot mistake "not retrieved" for "nothing to review".
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import boundary: importing the API must not
    # load SQLAlchemy (tests/contract/test_db_foundation.py).
    from sqlalchemy.orm import Session

from eurogas_nexus.application.projections.context import (
    ProjectionContext,
    resolve_projection_context,
)
from eurogas_nexus.application.projections.envelope import (
    SOURCE_RUNTIME_DB_NOT_CONFIGURED,
    SOURCE_RUNTIME_POSTGRESQL,
    WARNING_DECISION_NEEDS_ATTENTION,
    WARNING_EVIDENCE_INCOMPLETE,
    WARNING_RUNTIME_DB_NOT_CONFIGURED,
    context_filter_block,
    dedupe,
    entitlement_block,
    projection_envelope,
    projection_slice,
)
from eurogas_nexus.application.projections.freshness import (
    freshness_block,
    latest_iso_for_keys,
)
from eurogas_nexus.domain.dataops.contracts import EntitlementOutcome
from eurogas_nexus.domain.dataops.entitlement import derived_result_access
from eurogas_nexus.security.identity import AuthenticatedPrincipal

PROJECTION_ID = "review-context"
PROJECTION_VERSION = "review-context.v1"

#: Canonical tables the payload is composed from (reported as meta lineage).
TABLE_LINEAGE: tuple[str, ...] = (
    "review_decisions",
    "intraday_opportunities",
    "strategy_runs",
    "generated_reports",
    "agent_runs",
    "monitoring_alerts",
)

_DECISION_TIME_KEYS = ("created_at_utc",)
_NO_ROW_FILTER_RULE = (
    "the underlying review route applies no row-level commercial filter, so this "
    "slice adds none"
)
_DEGRADED_RULE = "not evaluated: no runtime database read was possible"

#: Resolvers this projection can address, keyed by review entity type value.
SUPPORTED_ENTITY_TYPES: tuple[str, ...] = (
    "intraday_opportunity",
    "strategy_run",
    "generated_report",
    "agent_review_pack",
)


def build_review_context(
    principal: AuthenticatedPrincipal,
    *,
    session: Session | None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    gas_day: str | None = None,
    delivery_product: str | None = None,
    hub: str | None = None,
    as_of_utc: datetime | None = None,
    now_utc: datetime | None = None,
    decision_limit: int = 100,
    evidence_limit: int = 20,
) -> dict[str, Any]:
    """Compose the ReviewContext projection for one principal.

    Args:
        principal: The authenticated principal the payload is rendered for.
        session: Open SQLAlchemy session, or ``None`` when no runtime database is
            configured.
        entity_type: Optional review entity type filter (same semantics as
            ``GET /api/review/decisions?entity_type=``).
        entity_id: Optional review entity id filter.
        gas_day: ISO gas day of the declared context.
        delivery_product: Declared delivery product, or ``None``.
        hub: Declared hub, or ``None``.
        as_of_utc: The single as-of instant; defaults to ``now_utc``.
        now_utc: Injectable clock (tests).
        decision_limit: Bound on the decision slice.
        evidence_limit: Bound on how many referenced entities are resolved.

    Returns:
        ``{"data": ..., "meta": ...}`` with the decisions, the resolved evidence,
        the monitoring posture and the review warnings.

    Raises:
        GasDayInputError: When ``gas_day`` is not an ISO calendar date.
    """

    context = resolve_projection_context(
        gas_day=gas_day,
        delivery_product=delivery_product,
        hub=hub,
        as_of_utc=as_of_utc,
        now_utc=now_utc,
    )
    if session is None:
        return _unavailable_review_context(
            context,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    return _populated_review_context(
        principal,
        session=session,
        context=context,
        entity_type=entity_type,
        entity_id=entity_id,
        decision_limit=decision_limit,
        evidence_limit=evidence_limit,
    )


def _populated_review_context(
    principal: AuthenticatedPrincipal,
    *,
    session: Session,
    context: ProjectionContext,
    entity_type: str | None,
    entity_id: str | None,
    decision_limit: int,
    evidence_limit: int,
) -> dict[str, Any]:
    """Build every slice from one session and one as-of instant."""

    decisions = _review_decisions(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=decision_limit,
    )
    requested_entities = _requested_entities(
        decisions,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    evidence = [
        _resolve_evidence(
            session,
            principal,
            item_type,
            item_id,
            now_utc=context.as_of_utc,
        )
        for item_type, item_id in requested_entities[:evidence_limit]
    ]
    monitoring = _monitoring_summary(session)

    evidence_warnings = [
        warning
        for entry in evidence
        for warning in entry.get("warnings") or []
    ]
    slices: dict[str, dict[str, Any]] = {
        "decisions": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=decisions,
            freshness=freshness_block(
                row_count=len(decisions),
                last_observed_at_utc=latest_iso_for_keys(decisions, _DECISION_TIME_KEYS),
                expectation_minutes=None,
                now_utc=context.as_of_utc,
            ),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=_NO_ROW_FILTER_RULE,
            ),
            context_filter=context_filter_block(
                applied=[],
                rule="review decisions carry no hub/product dimension",
            ),
            limits={
                "row_limit": decision_limit,
                "truncated": decision_limit > 0 and len(decisions) >= decision_limit,
            },
            payload={
                "latest_decision": decisions[0] if decisions else None,
                "needs_attention_count": sum(
                    1 for row in decisions if row.get("decision") == "needs_attention"
                ),
                "decided_entities": [
                    {"entity_type": item_type, "entity_id": item_id}
                    for item_type, item_id in requested_entities
                ],
            },
            notes=[
                "Rows of /api/review/decisions, newest first.",
                "A review decision is evidence and rationale; it is never an "
                "execution approval.",
            ],
        ),
        "evidence": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=evidence,
            freshness=freshness_block(
                row_count=len(evidence),
                last_observed_at_utc=latest_iso_for_keys(decisions, _DECISION_TIME_KEYS),
                expectation_minutes=None,
                now_utc=context.as_of_utc,
                derived_from="decisions",
            ),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=_NO_ROW_FILTER_RULE,
            ),
            context_filter=context_filter_block(
                applied=[],
                rule="evidence is addressed by entity id, not by hub/product",
            ),
            limits={
                "row_limit": evidence_limit,
                "truncated": len(requested_entities) > evidence_limit,
            },
            warnings=evidence_warnings,
            payload={
                "requested_entity_count": len(requested_entities),
                "resolved_entity_count": sum(
                    1 for entry in evidence if entry.get("available")
                ),
                "supported_entity_types": list(SUPPORTED_ENTITY_TYPES),
            },
            notes=[
                "One resolver per review entity type; an entity that cannot be "
                "retrieved is reported as unavailable with a stable reason code.",
            ],
        ),
        "monitoring": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            payload=monitoring,
            freshness=freshness_block(
                row_count=0,
                last_observed_at_utc=None,
                expectation_minutes=None,
                now_utc=context.as_of_utc,
                derived_from="decisions",
            ),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=_NO_ROW_FILTER_RULE,
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_ROW_FILTER_RULE),
            notes=[
                "Aggregate monitoring alert counts (db.repositories.monitoring).",
            ],
        ),
    }

    warnings = _review_warnings(decisions, evidence)
    return projection_envelope(
        {
            "projection": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "as_of_utc": context.as_of_utc.isoformat(),
            "time_basis": context.time_basis_payload(),
            "active_context": context.active_context_payload(),
            "review_target": {
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
            "slices": slices,
            "warnings": warnings,
            "research_only": True,
            "human_review_required": True,
        },
        projection=PROJECTION_ID,
        projection_version=PROJECTION_VERSION,
        as_of_utc=context.as_of_utc.isoformat(),
        time_basis=context.time_basis_payload(),
        source_references=[SOURCE_RUNTIME_POSTGRESQL],
        warnings=warnings,
        table_lineage=TABLE_LINEAGE,
    )


def _unavailable_review_context(
    context: ProjectionContext,
    *,
    entity_type: str | None,
    entity_id: str | None,
) -> dict[str, Any]:
    """Build the explicit-unknown payload used when no runtime DB is configured."""

    empty_freshness = freshness_block(
        row_count=0,
        last_observed_at_utc=None,
        expectation_minutes=None,
        now_utc=context.as_of_utc,
    )
    slices = {
        name: projection_slice(
            source=SOURCE_RUNTIME_DB_NOT_CONFIGURED,
            rows=[],
            freshness=empty_freshness,
            entitlement=entitlement_block(applied=False, filtered_out=0, reason=_DEGRADED_RULE),
            context_filter=context_filter_block(applied=[], rule=_DEGRADED_RULE),
            notes=["Review evidence requires the runtime PostgreSQL database."],
        )
        for name in ("decisions", "evidence")
    }
    slices["monitoring"] = projection_slice(
        source=SOURCE_RUNTIME_DB_NOT_CONFIGURED,
        payload=None,
        freshness=empty_freshness,
        entitlement=entitlement_block(applied=False, filtered_out=0, reason=_DEGRADED_RULE),
        context_filter=context_filter_block(applied=[], rule=_DEGRADED_RULE),
    )
    warnings = [WARNING_RUNTIME_DB_NOT_CONFIGURED]
    return projection_envelope(
        {
            "projection": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "as_of_utc": context.as_of_utc.isoformat(),
            "time_basis": context.time_basis_payload(),
            "active_context": context.active_context_payload(),
            "review_target": {"entity_type": entity_type, "entity_id": entity_id},
            "slices": slices,
            "warnings": warnings,
            "research_only": True,
            "human_review_required": True,
        },
        projection=PROJECTION_ID,
        projection_version=PROJECTION_VERSION,
        as_of_utc=context.as_of_utc.isoformat(),
        time_basis=context.time_basis_payload(),
        source_references=[SOURCE_RUNTIME_DB_NOT_CONFIGURED],
        warnings=warnings,
        table_lineage=TABLE_LINEAGE,
    )


def _review_decisions(
    session: Session,
    *,
    entity_type: str | None,
    entity_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Read review decisions with the same repository call the route uses."""

    from eurogas_nexus.db.repositories.review import list_review_decisions

    return list_review_decisions(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )


def _requested_entities(
    decisions: list[dict[str, Any]],
    *,
    entity_type: str | None,
    entity_id: str | None,
) -> list[tuple[str, str]]:
    """Return the deduplicated (entity_type, entity_id) pairs to resolve.

    An explicit review target is always resolved first, so a caller can ask for
    the evidence of an artifact that has no decision recorded yet.
    """

    ordered: list[tuple[str, str]] = []
    if entity_type and entity_id:
        ordered.append((str(entity_type), str(entity_id)))
    for row in decisions:
        item = (str(row.get("entity_type") or ""), str(row.get("entity_id") or ""))
        if all(item) and item not in ordered:
            ordered.append(item)
    return ordered


def _resolve_evidence(
    session: Session,
    principal: AuthenticatedPrincipal,
    entity_type: str,
    entity_id: str,
    *,
    now_utc: datetime,
) -> dict[str, Any]:
    """Resolve one review artifact into an explicit evidence entry.

    The review route applies no row-level filter, so this projection invents no
    row filter either. It does apply the existing fail-closed **derived-result**
    rule where an artifact declares the source systems it was computed from
    (:func:`eurogas_nexus.domain.dataops.entitlement.derived_result_access`, the
    same helper ``/api/route-cost/route-candidates`` uses): evidence computed
    over a source family the principal is not entitled to is withheld and
    reported as an explicit ``ENTITLEMENT_DENIED`` unknown, never rendered.
    """

    entry: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "available": False,
        "resolver": entity_type if entity_type in SUPPORTED_ENTITY_TYPES else None,
        "artifact": None,
        "unavailable_reason": None,
        "warnings": [],
    }
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        entry["unavailable_reason"] = "ENTITY_TYPE_NOT_RESOLVABLE"
        return entry

    artifact, warnings = _EVIDENCE_RESOLVERS[entity_type](session, entity_id, now_utc)
    if artifact is None:
        entry["unavailable_reason"] = "EVIDENCE_NOT_FOUND"
        entry["warnings"] = warnings
        return entry

    source_systems = _evidence_source_systems(artifact)
    if derived_result_access(principal, source_systems).outcome is not EntitlementOutcome.ALLOWED:
        entry["unavailable_reason"] = "ENTITLEMENT_DENIED"
        entry["warnings"] = ["ENTITLEMENT_DENIED"]
        return entry

    entry["available"] = True
    entry["artifact"] = artifact
    entry["warnings"] = warnings
    return entry


def _evidence_source_systems(artifact: Mapping[str, Any]) -> list[str]:
    """Return the contributing source systems an artifact declares, if any."""

    systems = artifact.get("source_systems")
    if isinstance(systems, (list, tuple)):
        return [str(item) for item in systems if item]
    return []


def _intraday_opportunity_evidence(
    session: Session,
    entity_id: str,
    now_utc: datetime,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Resolve an intraday-opportunity review artifact."""

    from eurogas_nexus.db.repositories.market_intelligence import (
        get_intraday_opportunity,
    )

    artifact = get_intraday_opportunity(session, entity_id, now_utc=now_utc)
    if artifact is None:
        return None, []
    return artifact, list(artifact.get("warnings") or [])


def _strategy_run_evidence(
    session: Session,
    entity_id: str,
    now_utc: datetime,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Resolve a strategy-run review artifact."""

    _ = now_utc
    from eurogas_nexus.db.repositories.strategy import get_strategy_run

    artifact = get_strategy_run(session, entity_id)
    if artifact is None:
        return None, []
    return artifact, list(artifact.get("warnings") or [])


def _generated_report_evidence(
    session: Session,
    entity_id: str,
    now_utc: datetime,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Resolve a generated-report review artifact.

    The report row is shaped here because no repository payload builder exists
    for ``generated_reports`` today (the write path lives inside the analysis
    route); the fields are exactly the persisted columns a reviewer needs, and
    the full section bodies stay on ``POST /api/reports/portfolio``.
    """

    _ = now_utc
    from eurogas_nexus.db.models import GeneratedReportRecord

    row = session.get(GeneratedReportRecord, entity_id)
    if row is None:
        return None, []
    artifact = {
        "report_id": row.report_id,
        "report_type": row.report_type,
        "title": row.title,
        "status": row.status,
        "duration_start_utc": _iso(row.duration_start_utc),
        "duration_end_utc": _iso(row.duration_end_utc),
        "created_at_utc": _iso(row.created_at_utc),
        "section_count": len(row.sections or []),
        "source_refs": list(row.source_refs or []),
        "warnings": list(row.warnings or []),
        "research_only": row.research_only,
        "human_review_required": row.human_review_required,
    }
    return artifact, list(row.warnings or [])


def _agent_review_pack_evidence(
    session: Session,
    entity_id: str,
    now_utc: datetime,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Resolve an agent review-pack artifact through the agent run replay payload."""

    _ = now_utc
    from eurogas_nexus.db.repositories.agents import get_agent_run, replay_payload

    row = get_agent_run(session, entity_id)
    if row is None:
        return None, []
    replay = replay_payload(session, row)
    warnings = [
        str(warning)
        for warning in (replay.get("warnings") or [])
    ]
    return replay, warnings


_EVIDENCE_RESOLVERS = {
    "intraday_opportunity": _intraday_opportunity_evidence,
    "strategy_run": _strategy_run_evidence,
    "generated_report": _generated_report_evidence,
    "agent_review_pack": _agent_review_pack_evidence,
}


def _monitoring_summary(session: Session) -> dict[str, Any]:
    """Read the aggregate monitoring posture with the existing repository call."""

    from eurogas_nexus.db.repositories.monitoring import monitoring_summary

    return monitoring_summary(session)


def _review_warnings(
    decisions: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[str]:
    """Aggregate the review warning codes from the decisions and evidence."""

    needs_attention = any(
        row.get("decision") == "needs_attention" for row in decisions
    )
    incomplete = any(not entry.get("available") for entry in evidence)
    return dedupe(
        [
            WARNING_DECISION_NEEDS_ATTENTION if needs_attention else None,
            WARNING_EVIDENCE_INCOMPLETE if incomplete else None,
        ]
    )


def _iso(value: datetime | None) -> str | None:
    """Return an ISO timestamp for an optional datetime."""

    return value.isoformat() if value is not None else None
