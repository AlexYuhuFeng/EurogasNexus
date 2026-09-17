"""PortfolioSnapshot projection (Architecture V2 Wave 5, priority 2).

One coherent read model for the portfolio workspace: the cockpit summary, the
imported screen orders, the PnL snapshots and the operator-owned contract
context, all read inside one session and all measured against one as-of instant
with per-slice freshness.

The summary is produced by ``domain.market_positioning.summarize_portfolio`` -
the same domain function ``/api/portfolio/live-summary`` calls - over the same
rows ``/api/portfolio/screen-orders`` and ``/api/portfolio/pnl-snapshots``
return, so the projection can never disagree with the endpoints it composes.

Two properties are preserved deliberately:

- **Never fabricate evidence.** A portfolio with no valuation row keeps the
  ``None`` (unknown) aggregates and the ``VALUATION_EVIDENCE_MISSING`` warning
  the domain function already produces; the projection adds no zero.
- **Never widen.** Screen orders and PnL snapshots carry a ``source_system``, so
  this projection applies the same fail-closed row filter the market reads use
  (``filter_entitled_rows``). The underlying portfolio routes apply no row
  filter, so the projection is strictly narrower than they are - never wider.
  The filter that ran is recorded per slice in ``entitlement``.
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
    WARNING_SOURCE_STALE,
    context_filter_block,
    dedupe,
    entitlement_block,
    projection_envelope,
    projection_slice,
)
from eurogas_nexus.application.projections.freshness import (
    freshness_block,
    freshness_state_summary,
    latest_iso_for_keys,
    row_source_systems,
    source_provenance_rows,
    strictest_expectation,
)
from eurogas_nexus.application.projections.market_reads import (
    ENTITLEMENT_RULE_LEGACY,
    ENTITLEMENT_RULE_SOURCE_FAMILY,
    row_allowed,
)
from eurogas_nexus.application.projections.portfolio_reads import (
    PORTFOLIO_TABLE_LINEAGE,
    pnl_snapshots,
    screen_orders,
)
from eurogas_nexus.domain.market_positioning import summarize_portfolio
from eurogas_nexus.security.identity import AuthenticatedPrincipal

PROJECTION_ID = "portfolio-snapshot"
PROJECTION_VERSION = "portfolio-snapshot.v1"

#: Canonical tables the payload is composed from (reported as meta lineage).
TABLE_LINEAGE: tuple[str, ...] = (*PORTFOLIO_TABLE_LINEAGE, "upstream_contracts")

_ORDER_TIME_KEYS = ("observed_at_utc",)
_VALUATION_TIME_KEYS = ("valuation_time_utc",)
_NO_CONTEXT_FIELD_RULE = (
    "portfolio reads carry no hub/product dimension, so the declared context is "
    "reported but not applied"
)
_DEGRADED_RULE = "not evaluated: no runtime database read was possible"

#: Why the resource-pool slice is declared but not composed here.
RESOURCE_POOL_FOLLOW_UP = (
    "Portfolio resources and executable sale options are composed by "
    "api/routes/public/route_cost.py::_compose_resource_pool_options (contracts, "
    "candidates, tariffs, market rows, FX, company TSO access). Reusing it needs "
    "that composition extracted into the application layer first; until then the "
    "projection reports the slice as unavailable instead of duplicating it. "
    "ScenarioContext delivers the cheap, DB-backed parts of the same context."
)


def build_portfolio_snapshot(
    principal: AuthenticatedPrincipal,
    *,
    session: Session | None,
    portfolio_id: str | None = None,
    gas_day: str | None = None,
    delivery_product: str | None = None,
    hub: str | None = None,
    as_of_utc: datetime | None = None,
    now_utc: datetime | None = None,
    order_limit: int = 500,
    snapshot_limit: int = 500,
    contract_limit: int = 200,
) -> dict[str, Any]:
    """Compose the PortfolioSnapshot projection for one principal.

    Args:
        principal: The authenticated principal the payload is rendered for.
        session: Open SQLAlchemy session, or ``None`` when no runtime database is
            configured.
        portfolio_id: Optional portfolio filter (same semantics as
            ``GET /api/portfolio/live-summary?portfolio_id=``).
        gas_day: ISO gas day of the declared context.
        delivery_product: Declared delivery product, or ``None``.
        hub: Declared hub, or ``None``.
        as_of_utc: The single as-of instant; defaults to ``now_utc``.
        now_utc: Injectable clock (tests).
        order_limit: Bound on the screen-order slice.
        snapshot_limit: Bound on the PnL snapshot slice.
        contract_limit: Bound on the upstream-contract slice.

    Returns:
        ``{"data": ..., "meta": ...}`` with the portfolio summary, screen
        orders, PnL snapshots, upstream contract context and per-slice
        freshness.

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
        return _unavailable_portfolio_snapshot(context, portfolio_id=portfolio_id)
    return _populated_portfolio_snapshot(
        principal,
        session=session,
        context=context,
        portfolio_id=portfolio_id,
        order_limit=order_limit,
        snapshot_limit=snapshot_limit,
        contract_limit=contract_limit,
    )


def _populated_portfolio_snapshot(
    principal: AuthenticatedPrincipal,
    *,
    session: Session,
    context: ProjectionContext,
    portfolio_id: str | None,
    order_limit: int,
    snapshot_limit: int,
    contract_limit: int,
) -> dict[str, Any]:
    """Build every slice from one session and one as-of instant."""

    orders = screen_orders(session)
    snapshots = pnl_snapshots(session)
    if portfolio_id:
        snapshots = [
            snapshot for snapshot in snapshots if snapshot.portfolio_id == portfolio_id
        ]

    entitled_orders = _filter_models(principal, orders, limit=order_limit)
    entitled_snapshots = _filter_models(principal, snapshots, limit=snapshot_limit)
    order_rows = [order.model_dump(mode="json") for order in entitled_orders]
    snapshot_rows = [snapshot.model_dump(mode="json") for snapshot in entitled_snapshots]

    summary = summarize_portfolio(entitled_orders, entitled_snapshots)
    contracts = _upstream_contracts(session)[:contract_limit]

    data_source_rows = source_provenance_rows(
        {
            "screen_orders": order_rows,
            "pnl_snapshots": snapshot_rows,
        },
        timestamp_keys={
            "screen_orders": _ORDER_TIME_KEYS,
            "pnl_snapshots": _VALUATION_TIME_KEYS,
        },
        now_utc=context.as_of_utc,
    )

    slices: dict[str, dict[str, Any]] = {
        "summary": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            payload=summary.model_dump(mode="json"),
            freshness=_freshness(
                snapshot_rows,
                context,
                keys=_VALUATION_TIME_KEYS,
                derived_from="pnl_snapshots",
            ),
            entitlement=_entitlement_record(
                principal,
                raw_count=len(snapshots) + len(orders),
                kept_count=len(entitled_snapshots) + len(entitled_orders),
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_CONTEXT_FIELD_RULE),
            limits={
                "bounds": [
                    _limit_record(order_limit, len(orders)),
                    _limit_record(snapshot_limit, len(snapshots)),
                ]
            },
            warnings=list(summary.warnings),
            notes=[
                "Aggregated by domain.market_positioning.summarize_portfolio, the same "
                "function /api/portfolio/live-summary uses.",
                "A None GBP aggregate means 'not measured'; it is never a measured zero.",
            ],
        ),
        "screen_orders": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=order_rows,
            freshness=_freshness(order_rows, context, keys=_ORDER_TIME_KEYS),
            entitlement=_entitlement_record(
                principal,
                raw_count=len(orders),
                kept_count=len(entitled_orders),
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_CONTEXT_FIELD_RULE),
            limits=_limit_record(order_limit, len(orders)),
            notes=["Rows of /api/portfolio/screen-orders."],
        ),
        "pnl_snapshots": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=snapshot_rows,
            freshness=_freshness(snapshot_rows, context, keys=_VALUATION_TIME_KEYS),
            entitlement=_entitlement_record(
                principal,
                raw_count=len(snapshots),
                kept_count=len(entitled_snapshots),
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_CONTEXT_FIELD_RULE),
            limits=_limit_record(snapshot_limit, len(snapshots)),
            notes=["Rows of /api/portfolio/pnl-snapshots."],
        ),
        "contracts": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=contracts,
            freshness=_freshness(contracts, context, keys=_VALUATION_TIME_KEYS),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=(
                    "operator-owned contract rows carry no source system, and the "
                    "underlying /api/route-cost/upstream-contracts route applies no "
                    "row filter; this slice adds none"
                ),
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_CONTEXT_FIELD_RULE),
            limits=_limit_record(contract_limit, len(contracts)),
            notes=[
                "Operator-owned upstream resource contracts (GET "
                "/api/route-cost/upstream-contracts); a gas-year contract carries no "
                "observation instant, so its freshness is reported as unmeasured.",
            ],
        ),
        "resources": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=[],
            payload={
                "available": False,
                "unavailable_reason": "RESOURCE_POOL_COMPOSITION_IS_ROUTE_LOCAL",
                "follow_up": RESOURCE_POOL_FOLLOW_UP,
                "served_by": "/api/route-cost/resource-pool/options",
            },
            freshness=freshness_block(
                row_count=0,
                last_observed_at_utc=None,
                expectation_minutes=None,
                now_utc=context.as_of_utc,
            ),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason="no rows are composed by this slice",
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_CONTEXT_FIELD_RULE),
            notes=[
                "Declared follow-up: portfolio resources/sale options stay on "
                "/api/route-cost/resource-pool/options until that composition is "
                "extracted.",
            ],
        ),
        "data_sources": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=data_source_rows,
            payload={
                **freshness_state_summary(data_source_rows),
                "row_total": sum(int(row["row_count"]) for row in data_source_rows),
                "tables": list(TABLE_LINEAGE),
                "entitlement_note": (
                    "Only source systems present in the returned, entitlement-filtered "
                    "rows are listed."
                ),
            },
            freshness=_freshness(
                order_rows + snapshot_rows,
                context,
                keys=_ORDER_TIME_KEYS,
            ),
            entitlement=_entitlement_record(
                principal,
                raw_count=len(orders) + len(snapshots),
                kept_count=len(entitled_orders) + len(entitled_snapshots),
            ),
            context_filter=context_filter_block(
                applied=[],
                rule="derived from the slices above after their own filters",
            ),
            notes=[
                "Per-source freshness/provenance summary of the portfolio slices.",
            ],
        ),
    }

    warnings = _payload_warnings(slices, summary.warnings)
    return projection_envelope(
        {
            "projection": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "as_of_utc": context.as_of_utc.isoformat(),
            "time_basis": context.time_basis_payload(),
            "active_context": context.active_context_payload(),
            "portfolio_id": summary.portfolio_id,
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


def _unavailable_portfolio_snapshot(
    context: ProjectionContext,
    *,
    portfolio_id: str | None,
) -> dict[str, Any]:
    """Build the explicit-unknown payload used when no runtime DB is configured."""

    empty_freshness = freshness_block(
        row_count=0,
        last_observed_at_utc=None,
        expectation_minutes=None,
        now_utc=context.as_of_utc,
    )
    slices: dict[str, dict[str, Any]] = {}
    for name in ("screen_orders", "pnl_snapshots", "contracts", "data_sources"):
        slices[name] = projection_slice(
            source=SOURCE_RUNTIME_DB_NOT_CONFIGURED,
            rows=[],
            freshness=empty_freshness,
            entitlement=entitlement_block(applied=False, filtered_out=0, reason=_DEGRADED_RULE),
            context_filter=context_filter_block(applied=[], rule=_DEGRADED_RULE),
            notes=["Portfolio observations require the runtime PostgreSQL database."],
        )
    summary = summarize_portfolio([], [])
    slices["summary"] = projection_slice(
        source=SOURCE_RUNTIME_DB_NOT_CONFIGURED,
        payload=summary.model_dump(mode="json"),
        freshness=empty_freshness,
        entitlement=entitlement_block(applied=False, filtered_out=0, reason=_DEGRADED_RULE),
        context_filter=context_filter_block(applied=[], rule=_DEGRADED_RULE),
        warnings=list(summary.warnings),
        notes=[
            "Summarized from zero rows: every GBP aggregate stays None (unknown) and "
            "VALUATION_EVIDENCE_MISSING is reported.",
        ],
    )
    slices["resources"] = projection_slice(
        source=SOURCE_RUNTIME_DB_NOT_CONFIGURED,
        rows=[],
        payload={
            "available": False,
            "unavailable_reason": "RESOURCE_POOL_COMPOSITION_IS_ROUTE_LOCAL",
            "follow_up": RESOURCE_POOL_FOLLOW_UP,
            "served_by": "/api/route-cost/resource-pool/options",
        },
        freshness=empty_freshness,
        entitlement=entitlement_block(applied=False, filtered_out=0, reason=_DEGRADED_RULE),
        context_filter=context_filter_block(applied=[], rule=_DEGRADED_RULE),
    )
    warnings = dedupe([WARNING_RUNTIME_DB_NOT_CONFIGURED, *summary.warnings])
    return projection_envelope(
        {
            "projection": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "as_of_utc": context.as_of_utc.isoformat(),
            "time_basis": context.time_basis_payload(),
            "active_context": context.active_context_payload(),
            "portfolio_id": portfolio_id or summary.portfolio_id,
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


def _upstream_contracts(session: Session) -> list[dict[str, Any]]:
    """Read the operator-owned upstream resource contracts."""

    from eurogas_nexus.db.repositories.route_cost import list_upstream_contracts

    return list_upstream_contracts(session)


def _filter_models(
    principal: AuthenticatedPrincipal,
    models: Sequence[Any],
    *,
    limit: int,
) -> list[Any]:
    """Apply the fail-closed row filter to observation models, then bound them.

    The rule is the same one the market reads use (:func:`row_allowed`), applied
    to the model's ``source_system``; the models are kept as models so the
    domain summary receives exactly the rows the slice reports.
    """

    kept = [model for model in models if row_allowed(principal, model.source_system)]
    return kept[:limit]


def _freshness(
    rows: Sequence[Mapping[str, Any]],
    context: ProjectionContext,
    *,
    keys: Sequence[str],
    derived_from: str | None = None,
) -> dict[str, Any]:
    """Build one slice's freshness block from its returned rows."""

    return freshness_block(
        row_count=len(rows),
        last_observed_at_utc=latest_iso_for_keys(rows, keys),
        expectation_minutes=strictest_expectation(row_source_systems(rows)),
        now_utc=context.as_of_utc,
        derived_from=derived_from,
    )


def _entitlement_record(
    principal: AuthenticatedPrincipal,
    *,
    raw_count: int,
    kept_count: int,
) -> dict[str, Any]:
    """Describe the commercial row filter actually applied to a slice."""

    if principal.auth_method == "legacy_public_token":
        return entitlement_block(applied=False, filtered_out=0, reason=ENTITLEMENT_RULE_LEGACY)
    return entitlement_block(
        applied=True,
        filtered_out=max(0, raw_count - kept_count),
        reason=f"{ENTITLEMENT_RULE_SOURCE_FAMILY} (strictly narrower than the "
        "underlying /api/portfolio route, which applies no row filter)",
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


def _payload_warnings(
    slices: Mapping[str, Mapping[str, Any]],
    summary_warnings: Sequence[str],
) -> list[str]:
    """Aggregate the payload-level warning codes from the slice results."""

    stale = any(
        isinstance(item.get("freshness"), Mapping)
        and item["freshness"].get("state") == "STALE"
        for item in slices.values()
    )
    filtered = any(
        isinstance(item.get("entitlement"), Mapping)
        and bool(item["entitlement"].get("filtered_out"))
        for item in slices.values()
    )
    return dedupe(
        [
            *summary_warnings,
            WARNING_SOURCE_STALE if stale else None,
            WARNING_ENTITLEMENT_FILTERED if filtered else None,
        ]
    )
