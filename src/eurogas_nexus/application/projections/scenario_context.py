"""ScenarioContext projection (Architecture V2 Wave 5, priority 4).

The scenario/route-economics context an operator needs *before* a scenario is
computed: the route candidates available to the principal, the European TSO
tariff rows, the operator-owned upstream contracts, and an explicit statement of
which scenario inputs are **not** part of a read model.

Why it stops where it does
--------------------------

A scenario result (optimizer allocation, route recommendation, route-cost
calculation) is produced by a POST endpoint that runs a deterministic engine.
Constitution rule 38 keeps numeric truth in those engines, and rule 34 keeps
projections to read models, so this projection deliberately does **not** re-run
or cache any of them: ``data.not_included`` names each surface and the reason.

The portfolio resource-pool composition behind
``GET /api/route-cost/resource-pool/options`` lives inside the route module
(``route_cost.py::_compose_resource_pool_options``) and is therefore declared as
a bounded follow-up rather than duplicated here (see
:data:`~eurogas_nexus.application.projections.portfolio_snapshot.RESOURCE_POOL_FOLLOW_UP`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    WARNING_ENTITLEMENT_FILTERED,
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
    row_source_systems,
    strictest_expectation,
)
from eurogas_nexus.application.projections.market_reads import (
    ENTITLEMENT_RULE_LEGACY,
    ENTITLEMENT_RULE_SOURCE_FAMILY,
)
from eurogas_nexus.domain.dataops.contracts import EntitlementOutcome
from eurogas_nexus.domain.dataops.entitlement import derived_result_access
from eurogas_nexus.security.identity import AuthenticatedPrincipal

PROJECTION_ID = "scenario-context"
PROJECTION_VERSION = "scenario-context.v1"

#: Canonical tables the payload is composed from (reported as meta lineage).
TABLE_LINEAGE: tuple[str, ...] = (
    "route_candidates",
    "tso_tariffs",
    "upstream_resource_contracts",
)

_NO_ROW_FILTER_RULE = (
    "the underlying route applies no row-level commercial filter, so this slice adds none"
)
_DEGRADED_RULE = "not evaluated: no runtime database read was possible"
_NO_CONTEXT_FIELD_RULE = (
    "route and tariff rows carry no hub dimension, so the declared context is "
    "reported but not applied"
)

#: Scenario inputs a read model must not synthesise, with the surface that owns them.
NOT_INCLUDED: tuple[dict[str, str], ...] = (
    {
        "surface": "POST /api/route-cost/resource-pool/optimize",
        "reason": "OPTIMIZER_RESULT_IS_COMPUTED_NOT_READ",
        "detail": (
            "Deterministic analytics own numeric output (constitution rule 38); a "
            "projection must not re-run or fabricate an allocation."
        ),
    },
    {
        "surface": "POST /api/route-cost/recommend",
        "reason": "RECOMMENDATION_IS_COMPUTED_NOT_READ",
        "detail": "Route recommendation runs the deterministic route optimizer on request.",
    },
    {
        "surface": "POST /api/route-cost/calculate",
        "reason": "ROUTE_COST_IS_COMPUTED_NOT_READ",
        "detail": "An explicit-leg route cost is a calculation over operator-supplied legs.",
    },
    {
        "surface": "GET /api/route-cost/resource-pool/options",
        "reason": "RESOURCE_POOL_COMPOSITION_IS_ROUTE_LOCAL",
        "detail": (
            "The portfolio resource/sale-option composition is private to the route "
            "module; extracting it into the application layer is the bounded "
            "follow-up that would let this slice be delivered."
        ),
    },
    {
        "surface": "GET /api/analysis-snapshots",
        "reason": "REPRODUCIBILITY_REFERENCE_IS_A_SEPARATE_SURFACE",
        "detail": (
            "The Wave 4 Analysis Snapshot surface already serves the reproducibility "
            "reference a scenario should cite; this projection does not duplicate it."
        ),
    },
)


def build_scenario_context(
    principal: AuthenticatedPrincipal,
    *,
    session: Session | None,
    gas_day: str | None = None,
    delivery_product: str | None = None,
    hub: str | None = None,
    as_of_utc: datetime | None = None,
    now_utc: datetime | None = None,
    country: str | None = None,
    tso: str | None = None,
    market_area: str | None = None,
    tariff_limit: int = 200,
    candidate_limit: int = 200,
    contract_limit: int = 200,
) -> dict[str, Any]:
    """Compose the ScenarioContext projection for one principal.

    Args:
        principal: The authenticated principal the payload is rendered for.
        session: Open SQLAlchemy session, or ``None`` when no runtime database is
            configured.
        gas_day: ISO gas day of the declared context.
        delivery_product: Declared delivery product, or ``None``.
        hub: Declared hub, or ``None``.
        as_of_utc: The single as-of instant; defaults to ``now_utc``.
        now_utc: Injectable clock (tests).
        country: Optional TSO tariff country filter (same matching as
            ``GET /api/route-cost/tso-tariffs``).
        tso: Optional TSO name filter.
        market_area: Optional market-area filter.
        tariff_limit: Bound on the tariff slice.
        candidate_limit: Bound on the route-candidate slice.
        contract_limit: Bound on the upstream-contract slice.

    Returns:
        ``{"data": ..., "meta": ...}`` with the entitled route candidates, the
        tariff context, the upstream contracts and the explicit list of scenario
        inputs a read model does not provide.

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
        return _unavailable_scenario_context(context)
    return _populated_scenario_context(
        principal,
        session=session,
        context=context,
        country=country,
        tso=tso,
        market_area=market_area,
        tariff_limit=tariff_limit,
        candidate_limit=candidate_limit,
        contract_limit=contract_limit,
    )


def _populated_scenario_context(
    principal: AuthenticatedPrincipal,
    *,
    session: Session,
    context: ProjectionContext,
    country: str | None,
    tso: str | None,
    market_area: str | None,
    tariff_limit: int,
    candidate_limit: int,
    contract_limit: int,
) -> dict[str, Any]:
    """Build every slice from one session and one as-of instant."""

    raw_candidates = _route_candidates(session)
    candidates = [
        candidate
        for candidate in raw_candidates
        if derived_result_access(
            principal,
            candidate.get("source_systems") or [],
        ).outcome
        is EntitlementOutcome.ALLOWED
    ][:candidate_limit]

    tariffs = _tariffs(session, country=country, tso=tso, market_area=market_area)
    contracts = _upstream_contracts(session)[:contract_limit]

    slices: dict[str, dict[str, Any]] = {
        "route_candidates": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=candidates,
            freshness=_freshness(candidates, context),
            entitlement=_entitlement_record(
                principal,
                raw_count=len(raw_candidates),
                kept_count=len(candidates),
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_CONTEXT_FIELD_RULE),
            limits=_limit_record(candidate_limit, len(raw_candidates)),
            notes=[
                "GET /api/route-cost/route-candidates rows; every contributing source "
                "family must be granted (derived_result_access), the same rule the "
                "route applies.",
            ],
        ),
        "tso_tariffs": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=tariffs,
            freshness=_freshness(tariffs, context),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=_NO_ROW_FILTER_RULE,
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_CONTEXT_FIELD_RULE),
            limits=_limit_record(tariff_limit, len(tariffs)),
            payload={
                "filters": {
                    "country": country,
                    "tso": tso,
                    "market_area": market_area,
                }
            },
            notes=["GET /api/route-cost/tso-tariffs rows (European TSO tariffs)."],
        ),
        "upstream_contracts": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=contracts,
            freshness=_freshness(contracts, context),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=(
                    "operator-owned contract rows carry no source system; the "
                    "underlying route applies no row filter and this slice adds none"
                ),
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_CONTEXT_FIELD_RULE),
            limits=_limit_record(contract_limit, len(contracts)),
            notes=["GET /api/route-cost/upstream-contracts rows."],
        ),
    }

    warnings = dedupe(
        [WARNING_ENTITLEMENT_FILTERED if len(candidates) != len(raw_candidates) else None]
    )
    return projection_envelope(
        {
            "projection": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "as_of_utc": context.as_of_utc.isoformat(),
            "time_basis": context.time_basis_payload(),
            "active_context": context.active_context_payload(),
            "slices": slices,
            "not_included": [dict(item) for item in NOT_INCLUDED],
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


def _unavailable_scenario_context(context: ProjectionContext) -> dict[str, Any]:
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
            notes=["Scenario inputs require the runtime PostgreSQL database."],
        )
        for name in ("route_candidates", "tso_tariffs", "upstream_contracts")
    }
    warnings = [WARNING_RUNTIME_DB_NOT_CONFIGURED]
    return projection_envelope(
        {
            "projection": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "as_of_utc": context.as_of_utc.isoformat(),
            "time_basis": context.time_basis_payload(),
            "active_context": context.active_context_payload(),
            "slices": slices,
            "not_included": [dict(item) for item in NOT_INCLUDED],
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


def _route_candidates(session: Session) -> list[dict[str, Any]]:
    """Read route candidates with the existing repository call."""

    from eurogas_nexus.db.repositories.route_cost import list_route_candidates

    return list_route_candidates(session)


def _tariffs(
    session: Session,
    *,
    country: str | None,
    tso: str | None,
    market_area: str | None,
) -> list[dict[str, Any]]:
    """Read TSO tariffs and apply the route's own filter semantics."""

    from eurogas_nexus.db.repositories.route_cost import list_tso_tariffs

    rows = [tariff.model_dump(mode="json") for tariff in list_tso_tariffs(session)]
    filtered = rows
    if country:
        filtered = [
            row for row in filtered if str(row.get("country") or "").lower() == country.lower()
        ]
    if tso:
        filtered = [row for row in filtered if str(row.get("tso") or "").lower() == tso.lower()]
    if market_area:
        filtered = [
            row
            for row in filtered
            if str(row.get("market_area") or "").lower() == market_area.lower()
        ]
    return filtered


def _upstream_contracts(session: Session) -> list[dict[str, Any]]:
    """Read the operator-owned upstream resource contracts."""

    from eurogas_nexus.db.repositories.route_cost import list_upstream_contracts

    return list_upstream_contracts(session)


def _freshness(
    rows: Sequence[Mapping[str, Any]],
    context: ProjectionContext,
) -> dict[str, Any]:
    """Build one slice's freshness block from its returned rows."""

    return freshness_block(
        row_count=len(rows),
        last_observed_at_utc=latest_iso_for_keys(rows, ("updated_at_utc",)),
        expectation_minutes=strictest_expectation(row_source_systems(rows)),
        now_utc=context.as_of_utc,
    )


def _entitlement_record(
    principal: AuthenticatedPrincipal,
    *,
    raw_count: int,
    kept_count: int,
) -> dict[str, Any]:
    """Describe the commercial filter actually applied to the candidate slice."""

    if principal.auth_method == "legacy_public_token":
        return entitlement_block(applied=False, filtered_out=0, reason=ENTITLEMENT_RULE_LEGACY)
    return entitlement_block(
        applied=True,
        filtered_out=max(0, raw_count - kept_count),
        reason=(
            f"{ENTITLEMENT_RULE_SOURCE_FAMILY} (derived route candidates must be fully "
            "entitled, evaluated with derived_result_access before the slice is built)"
        ),
    )


def _limit_record(row_limit: int, available_rows: int) -> dict[str, Any]:
    """Return the bound applied to a slice.

    ``truncated`` is conservative: a slice that returned exactly the bound is
    reported as possibly truncated, because a filtered read cannot prove the
    source held no further row.
    """

    return {
        "row_limit": row_limit,
        "truncated": row_limit > 0 and available_rows >= row_limit,
    }
