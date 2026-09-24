"""MarketContext projection (Architecture V2 Wave 5, priority 1).

One coherent read model for the market workspace, so the React client no longer
reconstructs the trading context out of ``/api/market/observations``,
``/api/market/normalized``, ``/api/market/quotes``, ``/api/market/spreads``,
``/api/market/opportunities``, ``/api/monitoring/*`` and ``/api/sources`` -
each with its own timestamp and none of them sharing an as-of
(``W0-01_CLIENT_INVENTORY.md`` sections 6.2-6.4).

Contract
--------

- **One time basis and one as-of instant.** Every slice is read inside one
  session and measured against ``context.as_of_utc``; the payload declares the
  basis (``as_of_instant``), the gas day, the frozen gas-day calendar and the
  active context once, in ``data.time_basis`` and ``meta.time_basis``.
- **Per-slice freshness.** Every slice carries a freshness block computed with
  the repository's own read-side judgement
  (``domain.monitoring.freshness.evaluate_freshness`` against the expectation
  declared by ``domain.ingestion.source_registry``), never with a second
  vocabulary.
- **No widening.** Rows pass through the same entitlement rules the underlying
  routes apply: ``/api/market/observations`` and ``/api/market/quotes`` row
  filters are the extracted
  :func:`eurogas_nexus.application.projections.market_reads.filter_entitled_rows`,
  and the normalized view is read with the same fail-closed source-family
  predicate. Slices whose underlying route applies no row filter declare
  ``entitlement.row_filter_applied = false`` instead of inventing one.
- **Bounded observation slice.** The observations route is unbounded, so its
  ``observation_limit`` is applied by the same SQL read that applies entitlement
  and the route's order
  (:func:`eurogas_nexus.application.projections.market_reads.market_observation_page`):
  the slice holds the newest entitled rows, no restricted row is fetched to
  build it, and the pre-cap counts its entitlement block reports are SQL
  aggregates rather than rows read and then discarded. ``raw_count`` keeps its
  existing meaning - the table's total rows, before entitlement, restricted rows
  included - so the entitlement block can still state how many rows the filter
  removed.
- **Honest degradation.** Without a runtime database every slice reports
  ``available = false``, ``MISSING`` freshness and no rows - never a zero that
  reads as a measurement.
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
    DETECTED_AT_BASIS,
    OBSERVED_AT_BASIS,
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
    MARKET_TABLE_LINEAGE,
    derive_intraday_spreads,
    filter_entitled_rows,
    intraday_opportunities,
    market_observation_page,
    market_quotes,
    normalized_market_view,
    source_family_filter,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

PROJECTION_ID = "market-context"
PROJECTION_VERSION = "market-context.v1"

#: Canonical tables the payload is composed from (reported as meta lineage).
TABLE_LINEAGE: tuple[str, ...] = (*MARKET_TABLE_LINEAGE, "monitoring_alerts")

_OBSERVATION_TIME_KEYS = ("observed_at_utc",)
_OPPORTUNITY_TIME_KEYS = ("detected_at_utc", "observed_at_utc")
_ALERT_TIME_KEYS = ("updated_at_utc", "detected_at_utc")

_NO_HUB_FIELD_RULE = (
    "the underlying read exposes no backend hub or product field, so the declared "
    "context is reported but not applied to this slice"
)
_NO_ROW_FILTER_RULE = (
    "the underlying route applies no row-level commercial filter, so this slice adds none"
)
_DEGRADED_RULE = "not evaluated: no runtime database read was possible"


def build_market_context(
    principal: AuthenticatedPrincipal,
    *,
    session: Session | None,
    gas_day: str | None = None,
    delivery_product: str | None = None,
    hub: str | None = None,
    as_of_utc: datetime | None = None,
    now_utc: datetime | None = None,
    opportunity_status: str | None = None,
    alert_status: str | None = None,
    observation_limit: int = 500,
    quote_limit: int = 500,
    opportunity_limit: int = 100,
    alert_limit: int = 100,
) -> dict[str, Any]:
    """Compose the MarketContext projection for one principal.

    Args:
        principal: The authenticated principal the payload is rendered for.
        session: Open SQLAlchemy session, or ``None`` when no runtime database is
            configured (every slice then reports an explicit unknown).
        gas_day: ISO gas day to select; defaults to the gas day of the as-of
            instant.
        delivery_product: Declared delivery product, or ``None``.
        hub: Declared hub, or ``None``.
        as_of_utc: The single as-of instant; defaults to ``now_utc``.
        now_utc: Injectable clock (tests).
        opportunity_status: Optional opportunity status filter, passed straight
            to the existing repository read.
        alert_status: Optional monitoring alert status filter.
        observation_limit: Bound on the observation slice (the observations
            endpoint itself is unbounded).
        quote_limit: Bound on the quote slice.
        opportunity_limit: Bound on the opportunity slice.
        alert_limit: Bound on the monitoring alert slice.

    Returns:
        ``{"data": ..., "meta": ...}`` where ``data.slices`` holds the market
        observations, the normalized quote view, quotes, intraday opportunities,
        derived spreads, the monitoring summary/alerts and the data-source
        freshness/provenance summary.

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
        return _unavailable_market_context(context)
    return _populated_market_context(
        principal,
        session=session,
        context=context,
        opportunity_status=opportunity_status,
        alert_status=alert_status,
        observation_limit=observation_limit,
        quote_limit=quote_limit,
        opportunity_limit=opportunity_limit,
        alert_limit=alert_limit,
    )


def _populated_market_context(
    principal: AuthenticatedPrincipal,
    *,
    session: Session,
    context: ProjectionContext,
    opportunity_status: str | None,
    alert_status: str | None,
    observation_limit: int,
    quote_limit: int,
    opportunity_limit: int,
    alert_limit: int,
) -> dict[str, Any]:
    """Build every slice from one session and one as-of instant.

    The observation slice is read through
    :func:`eurogas_nexus.application.projections.market_reads.market_observation_page`:
    the same entitlement rule and the same order, applied by the database before
    the slice's own ``observation_limit``, so the slice holds exactly the rows the
    unbounded ``/api/market/observations`` read would have contributed without
    materializing ``market_observations`` to discard all but a few hundred rows.
    """

    observation_page = market_observation_page(
        session,
        principal,
        limit=observation_limit,
    )
    bounded_observations = observation_page.rows

    view = normalized_market_view(
        session,
        limit=quote_limit,
        source_filter=source_family_filter(principal),
    )
    view_rows = _context_filtered_rows(
        view["rows"],
        context,
        hub_keys=("hub",),
        product_keys=(),
    )

    raw_quotes = market_quotes(
        session,
        hub=context.hub,
        product=context.delivery_product,
        limit=quote_limit,
    )
    quotes = filter_entitled_rows(principal, raw_quotes)

    raw_opportunities = intraday_opportunities(
        session,
        status=opportunity_status,
        limit=opportunity_limit,
        now_utc=context.as_of_utc,
    )
    opportunities = _context_filtered_rows(
        raw_opportunities,
        context,
        hub_keys=("buy_hub", "sell_hub"),
        product_keys=("product",),
    )
    spreads = derive_intraday_spreads(opportunities)

    monitoring_rows, monitoring_summary_payload = _monitoring_reads(
        session,
        status=alert_status,
        limit=alert_limit,
    )

    data_source_rows = source_provenance_rows(
        {
            "market_observations": bounded_observations,
            "normalized_quotes": view_rows,
            "quotes": quotes,
            "intraday_opportunities": opportunities,
        },
        timestamp_keys={
            "market_observations": _OBSERVATION_TIME_KEYS,
            "normalized_quotes": _OBSERVATION_TIME_KEYS,
            "quotes": _OBSERVATION_TIME_KEYS,
            "intraday_opportunities": _OPPORTUNITY_TIME_KEYS,
        },
        now_utc=context.as_of_utc,
    )

    slices: dict[str, dict[str, Any]] = {
        "market_observations": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=bounded_observations,
            freshness=_slice_freshness(
                bounded_observations,
                context,
                keys=_OBSERVATION_TIME_KEYS,
            ),
            entitlement=_entitlement_record(
                principal,
                raw_count=observation_page.raw_count,
                kept_count=observation_page.entitled_count,
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_HUB_FIELD_RULE),
            limits=_limit_record(observation_limit, observation_page.entitled_count),
            notes=[
                "Source rows of /api/market/observations; the endpoint itself is "
                "unbounded and this slice is bounded by observation_limit.",
            ],
        ),
        "normalized_quotes": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=view_rows,
            freshness=_slice_freshness(view_rows, context, keys=_OBSERVATION_TIME_KEYS),
            entitlement=_entitlement_record(
                principal,
                raw_count=len(view_rows),
                kept_count=len(view_rows),
                filtered_before_read=True,
            ),
            context_filter=context_filter_block(
                applied=_applied_dimensions(context, hub=True, product=False),
                rule="exact hub match on the backend-normalized hub field",
            ),
            limits=_limit_record(quote_limit, len(view["rows"])),
            warnings=list(view.get("warnings") or []),
            notes=[
                "Rows of /api/market/normalized (hub/tenor/FX->GBP normalization).",
                "The view is delivered as its own slice because its warnings describe "
                "per-row FX conversion gaps.",
            ],
        ),
        "quotes": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=quotes,
            freshness=_slice_freshness(quotes, context, keys=_OBSERVATION_TIME_KEYS),
            entitlement=_entitlement_record(
                principal,
                raw_count=len(raw_quotes),
                kept_count=len(quotes),
            ),
            context_filter=context_filter_block(
                applied=_applied_dimensions(context, hub=True, product=True),
                rule="exact hub (upper-cased) and product (lower-cased) match applied "
                "by the quotes repository",
            ),
            limits=_limit_record(quote_limit, len(quotes)),
            notes=["Rows of /api/market/quotes."],
        ),
        "intraday_opportunities": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=opportunities,
            freshness=_slice_freshness(
                opportunities,
                context,
                keys=_OPPORTUNITY_TIME_KEYS,
                basis=DETECTED_AT_BASIS,
            ),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=_NO_ROW_FILTER_RULE,
            ),
            context_filter=context_filter_block(
                applied=_applied_dimensions(context, hub=True, product=True),
                rule="exact hub match on buy_hub/sell_hub and exact product match",
            ),
            limits=_limit_record(opportunity_limit, len(raw_opportunities)),
            notes=[
                "Expiry is evaluated at the projection as-of instant, so the payload "
                "is reproducible for a past as-of.",
            ],
        ),
        "spreads": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=spreads,
            freshness=_slice_freshness(
                opportunities,
                context,
                keys=_OPPORTUNITY_TIME_KEYS,
                basis=DETECTED_AT_BASIS,
                derived_from="intraday_opportunities",
            ),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=_NO_ROW_FILTER_RULE,
            ),
            context_filter=context_filter_block(
                applied=_applied_dimensions(context, hub=True, product=True),
                rule="inherited from the opportunity rows this slice is derived from",
            ),
            limits=_limit_record(opportunity_limit, len(opportunities)),
            notes=[
                "Same derivation as /api/market/spreads, computed over the opportunity "
                "rows reported in this same payload (no second read).",
            ],
        ),
        "monitoring": projection_slice(
            source=SOURCE_RUNTIME_POSTGRESQL,
            rows=monitoring_rows,
            payload=monitoring_summary_payload,
            freshness=_slice_freshness(
                monitoring_rows,
                context,
                keys=_ALERT_TIME_KEYS,
                expectation=None,
            ),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=_NO_ROW_FILTER_RULE,
            ),
            context_filter=context_filter_block(applied=[], rule=_NO_HUB_FIELD_RULE),
            limits=_limit_record(alert_limit, len(monitoring_rows)),
            notes=[
                "Monitoring alert summary counts are the aggregate of the same read as "
                "the alert rows in this slice.",
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
                    "rows are listed; a restricted family is never named."
                ),
            },
            freshness=_slice_freshness(
                bounded_observations + quotes + view_rows + opportunities,
                context,
                keys=_OBSERVATION_TIME_KEYS,
            ),
            entitlement=_entitlement_record(
                principal,
                raw_count=observation_page.raw_count + len(raw_quotes),
                kept_count=observation_page.entitled_count + len(quotes),
                filtered_before_read=True,
            ),
            context_filter=context_filter_block(
                applied=[],
                rule="derived from the slices above after their own filters",
            ),
            limits=None,
            notes=[
                "Per-source freshness/provenance summary measured with "
                "domain.monitoring.freshness against the source registry expectation.",
            ],
        ),
    }

    warnings = _payload_warnings(slices, data_source_rows)
    return projection_envelope(
        {
            "projection": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "as_of_utc": context.as_of_utc.isoformat(),
            "time_basis": context.time_basis_payload(),
            "active_context": context.active_context_payload(),
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


def _unavailable_market_context(context: ProjectionContext) -> dict[str, Any]:
    """Build the explicit-unknown payload used when no runtime DB is configured."""

    collection_slices = (
        "market_observations",
        "normalized_quotes",
        "quotes",
        "intraday_opportunities",
        "spreads",
        "data_sources",
    )
    slices: dict[str, dict[str, Any]] = {
        name: projection_slice(
            source=SOURCE_RUNTIME_DB_NOT_CONFIGURED,
            rows=[],
            freshness=freshness_block(
                row_count=0,
                last_observed_at_utc=None,
                expectation_minutes=None,
                now_utc=context.as_of_utc,
            ),
            entitlement=entitlement_block(
                applied=False,
                filtered_out=0,
                reason=_DEGRADED_RULE,
            ),
            context_filter=context_filter_block(applied=[], rule=_DEGRADED_RULE),
            notes=["Market intelligence requires the runtime PostgreSQL database."],
        )
        for name in collection_slices
    }
    slices["monitoring"] = projection_slice(
        source=SOURCE_RUNTIME_DB_NOT_CONFIGURED,
        rows=[],
        payload=None,
        freshness=freshness_block(
            row_count=0,
            last_observed_at_utc=None,
            expectation_minutes=None,
            now_utc=context.as_of_utc,
        ),
        entitlement=entitlement_block(applied=False, filtered_out=0, reason=_DEGRADED_RULE),
        context_filter=context_filter_block(applied=[], rule=_DEGRADED_RULE),
        notes=["Monitoring alerts require the runtime PostgreSQL database."],
    )
    warnings = [WARNING_RUNTIME_DB_NOT_CONFIGURED]
    return projection_envelope(
        {
            "projection": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "as_of_utc": context.as_of_utc.isoformat(),
            "time_basis": context.time_basis_payload(),
            "active_context": context.active_context_payload(),
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


def _monitoring_reads(
    session: Session,
    *,
    status: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the monitoring summary and its alert rows from the same session."""

    from eurogas_nexus.db.repositories.monitoring import (
        list_monitoring_alerts,
        monitoring_summary,
    )

    return (
        list_monitoring_alerts(session, status=status, limit=limit),
        monitoring_summary(session),
    )


def _slice_freshness(
    rows: Sequence[Mapping[str, Any]],
    context: ProjectionContext,
    *,
    keys: Sequence[str],
    basis: str = OBSERVED_AT_BASIS,
    expectation: int | None = None,
    derived_from: str | None = None,
) -> dict[str, Any]:
    """Build one slice's freshness block from its returned rows.

    ``expectation=None`` resolves the strictest expectation declared by the
    source registry for the source systems present in the rows; rows that carry
    no source system therefore report ``expectation_source = none``.
    """

    sources = row_source_systems(rows)
    resolved_expectation = (
        expectation if expectation is not None else strictest_expectation(sources)
    ) or None
    return freshness_block(
        row_count=len(rows),
        last_observed_at_utc=latest_iso_for_keys(rows, keys),
        expectation_minutes=resolved_expectation,
        now_utc=context.as_of_utc,
        basis=basis,
        derived_from=derived_from,
    )


def _entitlement_record(
    principal: AuthenticatedPrincipal,
    *,
    raw_count: int,
    kept_count: int,
    filtered_before_read: bool = False,
) -> dict[str, Any]:
    """Describe the commercial row filter actually applied to a slice."""

    if principal.auth_method == "legacy_public_token":
        return entitlement_block(
            applied=False,
            filtered_out=0,
            reason=ENTITLEMENT_RULE_LEGACY,
        )
    return entitlement_block(
        applied=True,
        filtered_out=None if filtered_before_read else max(0, raw_count - kept_count),
        reason=(
            f"{ENTITLEMENT_RULE_SOURCE_FAMILY} (evaluated before the read, so the "
            "exact filtered count is not measurable)"
            if filtered_before_read
            else ENTITLEMENT_RULE_SOURCE_FAMILY
        ),
    )


def _context_filtered_rows(
    rows: Sequence[Mapping[str, Any]],
    context: ProjectionContext,
    *,
    hub_keys: Sequence[str],
    product_keys: Sequence[str],
) -> list[dict[str, Any]]:
    """Apply the declared context as an exact, case-insensitive match.

    A slice keeps every row when the corresponding context dimension is not
    declared, and rows that do not carry the matched field are excluded while a
    match is active (fail-closed, never a silent partial filter).
    """

    hub_key = context.hub_key()
    product_key = context.product_key()
    if not hub_key and not product_key:
        return [dict(row) for row in rows]
    kept: list[dict[str, Any]] = []
    for row in rows:
        if hub_key and hub_keys:
            values = {str(row.get(key) or "").casefold() for key in hub_keys}
            if hub_key not in values:
                continue
        if product_key and product_keys:
            values = {str(row.get(key) or "").casefold() for key in product_keys}
            if product_key not in values:
                continue
        kept.append(dict(row))
    return kept


def _applied_dimensions(
    context: ProjectionContext,
    *,
    hub: bool,
    product: bool,
) -> list[str]:
    """Return the context dimensions that are declared and applicable."""

    applied: list[str] = []
    if hub and context.hub_key():
        applied.append("hub")
    if product and context.product_key():
        applied.append("delivery_product")
    return applied


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
    data_source_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Aggregate the payload-level warning codes from the slice results."""

    stale = any(
        isinstance(item.get("freshness"), Mapping)
        and item["freshness"].get("state") == "STALE"
        for item in slices.values()
    ) or any(
        isinstance(row.get("freshness"), Mapping)
        and row["freshness"].get("state") == "STALE"
        for row in data_source_rows
    )
    filtered = any(
        isinstance(item.get("entitlement"), Mapping)
        and bool(item["entitlement"].get("filtered_out"))
        for item in slices.values()
    )
    return dedupe(
        [
            WARNING_SOURCE_STALE if stale else None,
            WARNING_ENTITLEMENT_FILTERED if filtered else None,
        ]
    )
