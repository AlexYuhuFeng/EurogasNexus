"""DB composition for normalized quotes and intraday opportunity snapshots."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    CompanyTsoAccessRecord,
    FxObservationRecord,
    IntradayOpportunityRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    RouteCandidateRecord,
)
from eurogas_nexus.db.repositories.route_cost import list_tso_tariffs
from eurogas_nexus.domain.market_intelligence.normalized_view import (
    FxRateInput,
    MarketObservationInput,
    build_normalized_market_view,
)
from eurogas_nexus.domain.market_intelligence.opportunity_engine import (
    AccessStatus,
    FxRate,
    IntradayOpportunity,
    MarketQuote,
    OpportunityScanPolicy,
    RouteEconomics,
    evaluate_route_opportunity,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg


def upsert_market_quotes(session: Session, rows: list[dict]) -> int:
    """Persist normalized quote rows without committing the caller's transaction."""

    for row in rows:
        session.merge(MarketQuoteRecord(**row))
    session.flush()
    return len(rows)


def list_market_quotes(
    session: Session,
    *,
    hub: str | None = None,
    product: str | None = None,
    source_system: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """List market quotes with optional filters, newest first.

    列出规范化 L1 报价（可按 hub/product/来源过滤，按观测时间倒序）。

    Args:
        session: DB session.
        hub: Hub filter (case-insensitive), or None.
        product: Product filter (case-insensitive), or None.
        source_system: Source system filter, or None.
        limit: Max rows.

    Returns:
        List of quote payload dicts.
    """

    query = session.query(MarketQuoteRecord)
    if hub:
        query = query.filter(MarketQuoteRecord.hub == hub.strip().upper())
    if product:
        query = query.filter(MarketQuoteRecord.product == product.strip().lower())
    if source_system:
        query = query.filter(MarketQuoteRecord.source_system == source_system)
    rows = query.order_by(MarketQuoteRecord.observed_at_utc.desc()).limit(limit).all()
    return [_quote_dict(row) for row in rows]


def list_intraday_opportunities(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 100,
    now_utc: datetime | None = None,
) -> list[dict]:
    """List intraday opportunities, optionally filtered by status.

    列出日内机会（可按状态过滤，按检出时间倒序）；带状态过滤时扩大
    预取量以补偿过滤损耗。

    Args:
        session: DB session.
        status: Status filter (e.g. ``ACTIONABLE_REVIEW``), or None.
        limit: Max rows after filtering.
        now_utc: Evaluation clock for validity checks, or None.

    Returns:
        List of opportunity payload dicts.
    """

    query = session.query(IntradayOpportunityRecord)
    requested_status = status.strip().upper() if status else None
    query_limit = min(limit * 5, 1000) if requested_status else limit
    rows = (
        query.order_by(IntradayOpportunityRecord.detected_at_utc.desc())
        .limit(query_limit)
        .all()
    )
    serialized = [_opportunity_dict(row, now_utc=now_utc) for row in rows]
    if requested_status:
        serialized = [row for row in serialized if row["status"] == requested_status]
    return serialized[:limit]


def get_intraday_opportunity(
    session: Session,
    opportunity_id: str,
    *,
    now_utc: datetime | None = None,
) -> dict | None:
    """Return one intraday opportunity payload by id (None when absent).

    Reuses the same serializer as :func:`list_intraday_opportunities`, so the
    expiry rewrite (``EXPIRED`` + ``OPPORTUNITY_EXPIRED``) is identical whether a
    caller reads the list or one row - the review workflow needs one row by id
    and must not re-implement that rule.

    Args:
        session: DB session.
        opportunity_id: Opportunity id to read.
        now_utc: Evaluation clock for the validity check, or None.

    Returns:
        The opportunity payload, or None when no row carries that id.
    """

    from eurogas_nexus.db.models import IntradayOpportunityRecord

    row = session.get(IntradayOpportunityRecord, opportunity_id)
    if row is None:
        return None
    return _opportunity_dict(row, now_utc=now_utc)


#: Unit pattern for the gas rows the source-coverage read reserves. Shared by the
#: per-source pages and by the fallback's ranking window, so the row set a
#: reservation is computed over cannot drift between the two shapes.
_GAS_UNIT_PATTERN = "%MWH%"


def list_normalized_market_view(
    session: Session,
    *,
    limit: int = 500,
    source_filter: Callable[[str], bool] | None = None,
) -> dict:
    """Compose the backend-normalized market view (FX/tenor/hub owned by backend).

    Returns ``{"rows": [...], "warnings": [...]}`` where every row carries the
    original observation fields plus ``hub``, ``tenor``, ``is_gas_price``, and
    ``price_gbp_mwh`` computed by the domain normalization module.
    """

    allowed_market_sources = allowed_source_systems(
        session,
        MarketObservationRecord,
        source_filter,
    )
    allowed_fx_sources = allowed_source_systems(
        session,
        FxObservationRecord,
        source_filter,
    )
    observation_rows = list_market_observations_with_source_coverage(
        session,
        limit=limit,
        per_source_limit=40,
        source_systems=allowed_market_sources,
    )
    fx_query = session.query(FxObservationRecord)
    if allowed_fx_sources is not None:
        fx_query = fx_query.filter(FxObservationRecord.source_system.in_(allowed_fx_sources))
    fx_rows = fx_query.order_by(
        FxObservationRecord.observed_at_utc.desc(), FxObservationRecord.pair
    ).all()
    rates = [_fx_rate_input(row) for row in fx_rows]
    if not rates:
        rates = _ecb_market_fx_inputs(session, source_systems=allowed_market_sources)

    inputs = [
        MarketObservationInput(
            market_venue=row.market_venue,
            product=row.product,
            price=row.price,
            currency=row.currency,
            unit=row.unit,
            observed_at_utc=_iso(row.observed_at_utc),
            period_start_utc=_iso(row.period_start_utc),
            metadata_json=row.metadata_json or {},
        )
        for row in observation_rows
    ]
    view = build_normalized_market_view(inputs, rates)
    rows = [
        {**_observation_dict(row), **normalized}
        for row, normalized in zip(observation_rows, view["rows"], strict=True)
    ]
    return {"rows": rows, "warnings": view["warnings"]}


def list_market_observations_with_source_coverage(
    session: Session,
    *,
    limit: int,
    per_source_limit: int = 40,
    source_systems: set[str] | None = None,
) -> list:
    """Return recent observations with bounded low-frequency source coverage.

    返回近期观测并为低频来源保留有界配额：每日评估类数据不得被高频 tick 挤掉。

    The returned set is the globally newest ``limit`` rows merged with a bounded
    reservation for the gas sources, deduplicated by ``observation_id``, capped at
    ``limit`` and ordered by the market observation route's own order (observed
    instant desc, market venue, product). The reservation is now one bounded page
    per candidate source (:func:`_newest_gas_row_page`) instead of a ranking window
    over every gas row of the table; the superseded window is kept for the one case
    that read still decides, see :func:`_bounded_source_coverage_rows`. Bounds,
    entitlement, tie handling and the fallback's cost are recorded in
    ``docs/operations/SOURCE_COVERAGE_READ.md``.

    Args:
        session: DB session.
        limit: Maximum rows returned, and the global newest read's bound.
        per_source_limit: Maximum rows a single source may reserve.
        source_systems: Entitled source values, or None for every source value
            present in the table (the resource-pool composition reads that way and
            applies entitlement to the returned rows afterwards).

    Returns:
        At most ``limit`` observation rows: the per-source reservation first, then
        the globally newest rows, deduplicated and ordered as described above.
    """

    newest_query = session.query(MarketObservationRecord)
    if source_systems is not None:
        newest_query = newest_query.filter(
            MarketObservationRecord.source_system.in_(source_systems)
        )
    newest_rows = (
        newest_query
        .order_by(
            MarketObservationRecord.observed_at_utc.desc(),
            MarketObservationRecord.market_venue,
            MarketObservationRecord.product,
        )
        .limit(limit)
        .all()
    )
    if limit <= 0 or not newest_rows:
        return newest_rows
    return _merge_bounded_source_coverage(
        newest_rows,
        _bounded_source_coverage_rows(
            session,
            limit=limit,
            per_source_limit=per_source_limit,
            source_systems=source_systems,
        ),
        limit=limit,
    )


def _bounded_source_coverage_rows(
    session: Session,
    *,
    limit: int,
    per_source_limit: int,
    source_systems: set[str] | None = None,
) -> list:
    """Read the newest gas rows of every candidate source, one bounded read each.

    The reservation half of :func:`list_market_observations_with_source_coverage`:
    one ``LIMIT``-bounded page per candidate source, in the shape
    ``ix_market_observations_source_time`` (migration 0010) serves. The quota a
    source keeps is applied after the reads, because it divides ``limit`` by the
    number of gas sources and that divisor is only known once every candidate
    source has answered; a source with no gas row at all reserves nothing and
    consumes no quota.

    When the candidate sources outnumber the payload bound the reservation may not
    fit - the quota is then one row per gas source - and a page order would decide
    which rows survive, a choice this read has no mandate to make. The candidate
    count is known before any row is read, so that case takes
    :func:`_reserved_gas_rows_window`, the algorithm that decided it before, without
    reading a page first; its own quota rule leaves the selection identical wherever
    the reservation would have fit. It is rare (the source count must exceed the
    payload bound) and its cost is the superseded shape's cost.

    Args:
        session: DB session.
        limit: The payload's row bound (the merge still owns the final cap).
        per_source_limit: Maximum rows one source may reserve.
        source_systems: Entitled source values, or None for every source present.

    Returns:
        The reserved rows every source with a gas row can keep, delivered read by
        read in a deterministic source order; :func:`_merge_bounded_source_coverage`
        orders the payload.
    """

    page_bound = min(per_source_limit, limit)
    if page_bound <= 0:
        return []
    sources = _coverage_source_systems(session, source_systems)
    if not sources:
        return []
    if len(sources) > limit:
        return _reserved_gas_rows_window(
            session,
            limit=limit,
            per_source_limit=per_source_limit,
            source_systems=source_systems,
        )
    pages = [
        page
        for page in (
            _newest_gas_row_page(session, source=source, bound=page_bound)
            for source in sources
        )
        if page
    ]
    if not pages:
        return []
    source_quota = min(per_source_limit, max(1, limit // len(pages)))
    return [row for page in pages for row in page[:source_quota]]


def _reserved_gas_rows_window(
    session: Session,
    *,
    limit: int,
    per_source_limit: int,
    source_systems: set[str] | None,
) -> list:
    """The superseded reservation read, kept for the case it still decides.

    ``count(DISTINCT source_system)`` over the gas rows, then ``row_number() OVER
    (PARTITION BY source_system ORDER BY ...)`` over every gas row of the table and
    a join back to ``market_observations`` for the rows inside the quota. This is
    the read the bounded per-source pages replace; it is kept, unchanged, for
    :func:`_bounded_source_coverage_rows`' rare case - more candidate sources than
    the payload bound, so the reservation may not fit - where it is the algorithm
    that decided the selection before. Its two full-table reads are the cost of that
    fallback, measured by ``scripts/ops/measure_market_projection_latency.py`` as
    ``normalized.source_count`` and ``normalized.source_coverage_window``. The row
    order of the reservation is the join's, as it always was.
    """

    source_count_query = session.query(
        func.count(func.distinct(MarketObservationRecord.source_system))
    ).filter(MarketObservationRecord.unit.ilike(_GAS_UNIT_PATTERN))
    if source_systems is not None:
        source_count_query = source_count_query.filter(
            MarketObservationRecord.source_system.in_(source_systems)
        )
    source_count = source_count_query.scalar() or 0
    if source_count == 0:
        return []

    source_quota = min(per_source_limit, max(1, limit // source_count))
    ranked_query = session.query(
        MarketObservationRecord.observation_id.label("observation_id"),
        func.row_number()
        .over(
            partition_by=MarketObservationRecord.source_system,
            order_by=(
                MarketObservationRecord.observed_at_utc.desc(),
                MarketObservationRecord.market_venue,
                MarketObservationRecord.product,
            ),
        )
        .label("source_rank"),
    ).filter(MarketObservationRecord.unit.ilike(_GAS_UNIT_PATTERN))
    if source_systems is not None:
        ranked_query = ranked_query.filter(
            MarketObservationRecord.source_system.in_(source_systems)
        )
    ranked_rows = ranked_query.subquery()
    return (
        session.query(MarketObservationRecord)
        .join(
            ranked_rows,
            ranked_rows.c.observation_id == MarketObservationRecord.observation_id,
        )
        .filter(ranked_rows.c.source_rank <= source_quota)
        .all()
    )


def _coverage_source_systems(
    session: Session,
    source_systems: set[str] | None,
) -> list[str]:
    """The candidate sources one coverage pass reads, in a deterministic order.

    A caller that already holds the entitled source values passes them in; a caller
    that does not (the resource-pool composition applies entitlement to the
    returned rows) gets the values present in the table from one ``DISTINCT`` read,
    which is the only statement this shape adds when no source set is supplied.
    """

    if source_systems is not None:
        return sorted(source_systems)
    rows = (
        session.query(MarketObservationRecord.source_system)
        .distinct()
        .order_by(MarketObservationRecord.source_system)
        .all()
    )
    return [source for (source,) in rows if isinstance(source, str)]


def _newest_gas_row_page(session: Session, *, source: str, bound: int) -> list:
    """One source's newest ``bound`` gas rows, in the route's own read order.

    ``source_system`` equality with an observed-instant descending order is the
    shape ``ix_market_observations_source_time`` serves, so this is a bounded index
    range inside one source rather than a scan of the table. The order key is the
    route's own - instant, venue, product - so rows that tie on all three are cut by
    the database, exactly as the superseded ranking window cut them; this read does
    not define a tie-break rule of its own.
    """

    return (
        session.query(MarketObservationRecord)
        .filter(
            MarketObservationRecord.source_system == source,
            MarketObservationRecord.unit.ilike(_GAS_UNIT_PATTERN),
        )
        .order_by(
            MarketObservationRecord.observed_at_utc.desc(),
            MarketObservationRecord.market_venue,
            MarketObservationRecord.product,
        )
        .limit(bound)
        .all()
    )


def _read_order_key(row) -> tuple:
    """The market observation read order as a sort key (missing instant last).

    The route's own order of ``market_observations`` is observed instant desc, then
    venue, then product; the merge orders the payload with it, so the returned rows
    have one definition of "newest first".
    """

    return (
        _as_utc(row.observed_at_utc)
        if row.observed_at_utc is not None
        else datetime.min.replace(tzinfo=UTC),
        row.market_venue,
        row.product,
    )


def _merge_bounded_source_coverage(
    newest_rows: list,
    coverage_rows: list,
    *,
    limit: int,
) -> list:
    """Merge reserved source rows with newest rows, deduplicate, and cap output.

    The reservation is merged first - the order the superseded shape used - so a
    reserved row is never displaced by a newer global row, and rows tied on the read
    order keep the reservation ahead of the global read. The reserved rows are not
    re-ranked here: they are consumed in the order the reads delivered them, and the
    final stable sort is the only ordering rule the payload has.
    """

    selected: list = []
    known_ids: set[str] = set()
    for row in [*coverage_rows, *newest_rows]:
        if row.observation_id in known_ids:
            continue
        known_ids.add(row.observation_id)
        selected.append(row)
        if len(selected) >= limit:
            break
    selected.sort(key=_read_order_key, reverse=True)
    return selected


def _fx_rate_input(row: FxObservationRecord) -> FxRateInput:
    return FxRateInput(
        pair=row.pair,
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        rate=row.rate,
        observed_at_utc=_iso(row.observed_at_utc),
    )


def _ecb_market_fx_inputs(
    session: Session,
    *,
    source_systems: set[str] | None = None,
) -> list[FxRateInput]:
    ecb_query = session.query(MarketObservationRecord).filter(
        MarketObservationRecord.source_system == "ECB"
    )
    if source_systems is not None:
        ecb_query = ecb_query.filter(MarketObservationRecord.source_system.in_(source_systems))
    rows = (
        ecb_query
        .order_by(MarketObservationRecord.observed_at_utc.desc())
        .all()
    )
    return [
        FxRateInput(
            pair=row.product.replace("/", ""),
            base_currency="EUR",
            quote_currency=row.currency,
            rate=row.price,
            observed_at_utc=_iso(row.observed_at_utc),
        )
        for row in rows
    ]


def allowed_source_systems(
    session: Session,
    model,
    source_filter: Callable[[str], bool] | None,
) -> set[str] | None:
    """Resolve a principal filter to concrete DB source values before reads.

    The predicate is the same one the row-level entitlement filter applies
    (``principal_allows_source_family`` for a DB identity, unconditional for the
    legacy public token): evaluating it over the source values present in the
    table turns it into a fail-closed ``IN`` predicate on the row read, so a
    restricted row is never fetched. This narrows the *read* only: an aggregate
    a caller reports alongside it (the projection's ``raw_count``) is a
    ``count(*)`` over the table and keeps its existing definition, restricted
    rows included.

    Args:
        session: DB session.
        model: ORM model whose ``source_system`` column is resolved.
        source_filter: Per-row source family predicate, or ``None`` for no filter.

    Returns:
        The allowed source values, or ``None`` when no filter applies.
    """

    if source_filter is None:
        return None
    source_rows = session.query(model.source_system).distinct().all()
    return {
        source_system
        for (source_system,) in source_rows
        if isinstance(source_system, str) and source_filter(source_system)
    }


def _observation_dict(row: MarketObservationRecord) -> dict:
    return {
        "observation_id": row.observation_id,
        "market_venue": row.market_venue,
        "product": row.product,
        "price": row.price,
        "unit": row.unit,
        "currency": row.currency,
        "period_start_utc": _iso(row.period_start_utc),
        "period_end_utc": _iso(row.period_end_utc),
        "observed_at_utc": _iso(row.observed_at_utc),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "source_record_id": row.source_record_id,
        "freshness": row.freshness,
        "quality_score": row.quality_score,
        "research_only": row.research_only,
        "metadata_json": row.metadata_json or {},
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def scan_and_persist_intraday_opportunities(
    session: Session,
    *,
    detected_at_utc: datetime | None = None,
    policy: OpportunityScanPolicy | None = None,
) -> dict:
    """Compose DB-owned inputs, evaluate route spreads, and persist snapshots."""

    detected_at = _as_utc(detected_at_utc or datetime.now(UTC))
    scan_id = f"intraday-scan-{detected_at.strftime('%Y%m%dT%H%M%S%f')}"
    quote_rows = (
        session.query(MarketQuoteRecord)
        .order_by(MarketQuoteRecord.observed_at_utc.desc())
        .limit(2000)
        .all()
    )
    quotes = [MarketQuote.model_validate(_quote_dict(row)) for row in _latest_quotes(quote_rows)]
    routes = _route_economics(session, detected_at)
    fx_rates = _latest_fx_rates(session)
    opportunities: list[IntradayOpportunity] = []

    for route in routes:
        if route.from_hub.strip().upper() == route.to_hub.strip().upper():
            continue
        buy_quotes = [quote for quote in quotes if quote.hub.upper() == route.from_hub.upper()]
        sell_quotes = [quote for quote in quotes if quote.hub.upper() == route.to_hub.upper()]
        for buy_quote in buy_quotes:
            for sell_quote in sell_quotes:
                opportunity = evaluate_route_opportunity(
                    buy_quote,
                    sell_quote,
                    route,
                    scan_id=scan_id,
                    detected_at_utc=detected_at,
                    fx_rates=fx_rates,
                    policy=policy,
                )
                if opportunity is None:
                    continue
                opportunities.append(opportunity)
                session.merge(
                    IntradayOpportunityRecord(**opportunity.model_dump(mode="python"))
                )

    session.flush()
    status_counts: dict[str, int] = {}
    for opportunity in opportunities:
        status_counts[opportunity.status.value] = (
            status_counts.get(opportunity.status.value, 0) + 1
        )
    return {
        "scan_id": scan_id,
        "quotes_considered": len(quotes),
        "routes_considered": len(routes),
        "opportunities_persisted": len(opportunities),
        "status_counts": dict(sorted(status_counts.items())),
        "detected_at_utc": detected_at.isoformat(),
    }


def _latest_quotes(rows: list[MarketQuoteRecord]) -> list[MarketQuoteRecord]:
    latest: dict[tuple[str, str, str], MarketQuoteRecord] = {}
    for row in rows:
        key = (row.source_system, row.venue, row.instrument_id)
        latest.setdefault(key, row)
    return list(latest.values())


def _route_economics(session: Session, at_utc: datetime) -> list[RouteEconomics]:
    candidates = (
        session.query(RouteCandidateRecord)
        .filter(RouteCandidateRecord.active.is_(True))
        .order_by(RouteCandidateRecord.route_id)
        .all()
    )
    tariff_date = at_utc.date()
    tariffs = [
        tariff
        for tariff in list_tso_tariffs(session)
        if tariff.effective_from <= tariff_date
        and (tariff.effective_to is None or tariff.effective_to >= tariff_date)
    ]
    access_rows = session.query(CompanyTsoAccessRecord).all()
    active_access, denied_access = _access_sets(access_rows, at_utc)
    results: list[RouteEconomics] = []

    for candidate in candidates:
        required_access = candidate.required_tso_access or []
        access_status = AccessStatus.CONFIRMED
        if any(tso.strip().lower() in denied_access for tso in required_access):
            access_status = AccessStatus.DENIED
        elif any(tso.strip().lower() not in active_access for tso in required_access):
            access_status = AccessStatus.UNCONFIRMED

        missing_inputs: list[str] = []
        warnings: list[str] = []
        total_cost: float | None = 0.0
        currency = "EUR"
        unit = "MWh"
        cost_components: list[dict] = []
        source_refs = [f"route_candidate:{candidate.route_id}", *(candidate.source_systems or [])]

        try:
            legs = [RouteTariffLeg.model_validate(leg) for leg in candidate.route_legs or []]
        except ValueError:
            legs = []
            missing_inputs.append("ROUTE_LEG_INVALID")

        if candidate.route_legs and legs:
            scenario = RouteCostScenario(
                scenario_id=f"intraday:{candidate.route_id}",
                source_resource_type="PIPELINE_IMPORT",
                start_point_id=candidate.start_point_name,
                target_hub_or_point_id=candidate.target_point_name,
                business_model="CROSS_BORDER_TRANSFER",
                delivery_mode="BORDER_TRANSFER",
                gas_year=legs[0].gas_year or "2025+",
                capacity_product=legs[0].capacity_product or "ANNUAL",
                firmness=legs[0].firmness or "FIRM",
                required_tso_access=required_access,
                company_accessible_tsos=(
                    sorted(active_access) if required_access else []
                ),
                tariff_legs=legs,
            )
            result = calculate_route_cost(scenario, tariffs)
            total_cost = result.total_cost
            currency = result.currency or "EUR"
            raw_unit = result.unit or "EUR/MWh"
            unit = "MWh" if raw_unit.upper().endswith("/MWH") else raw_unit
            missing_inputs.extend(result.missing_inputs)
            warnings.extend(result.warnings)
            cost_components = [item.model_dump(mode="json") for item in result.cost_breakdown]
            source_refs.extend(
                ref
                for item in result.cost_breakdown
                for ref in item.source_refs
            )

        results.append(
            RouteEconomics(
                route_id=candidate.route_id,
                route_name=candidate.route_name,
                from_hub=candidate.start_point_name,
                to_hub=candidate.target_point_name,
                total_cost=total_cost,
                currency=currency,
                unit=unit,
                available_capacity_mwh=_route_capacity(candidate.route_legs or []),
                access_status=access_status,
                required_tso_access=required_access,
                cost_components=cost_components,
                source_refs=_unique(source_refs),
                missing_inputs=_unique(missing_inputs),
                warnings=_unique(warnings),
            )
        )
    return results


def _latest_fx_rates(session: Session) -> list[FxRate]:
    rows = session.query(FxObservationRecord).order_by(
        FxObservationRecord.observed_at_utc.desc()
    ).all()
    latest: dict[tuple[str, str], FxRate] = {}
    for row in rows:
        key = (row.base_currency.upper(), row.quote_currency.upper())
        latest.setdefault(
            key,
            FxRate(
                base_currency=row.base_currency,
                quote_currency=row.quote_currency,
                rate=row.rate,
                observed_at_utc=row.observed_at_utc,
                source_reference=row.source_reference,
            ),
        )
    return list(latest.values())


def _access_sets(
    rows: list[CompanyTsoAccessRecord],
    at_utc: datetime,
) -> tuple[set[str], set[str]]:
    active: set[str] = set()
    denied: set[str] = set()
    for row in rows:
        if _as_utc(row.valid_from_utc) > at_utc:
            continue
        if row.valid_to_utc is not None and _as_utc(row.valid_to_utc) < at_utc:
            continue
        tso = row.tso.strip().lower()
        if row.status.upper() in {"ACTIVE", "CONFIRMED"}:
            active.add(tso)
        elif row.status.upper() in {"DENIED", "INACTIVE", "SUSPENDED"}:
            denied.add(tso)
    return active, denied


def _route_capacity(route_legs: list[dict]) -> float | None:
    capacities = [
        float(leg["available_capacity_mwh_per_day"])
        for leg in route_legs
        if isinstance(leg, dict)
        and isinstance(leg.get("available_capacity_mwh_per_day"), int | float)
        and float(leg["available_capacity_mwh_per_day"]) > 0
    ]
    return min(capacities) if capacities else None


def _quote_dict(row: MarketQuoteRecord) -> dict:
    return {
        "quote_id": row.quote_id,
        "source_system": row.source_system,
        "source_record_id": row.source_record_id,
        "venue": row.venue,
        "instrument_id": row.instrument_id,
        "hub": row.hub,
        "product": row.product,
        "delivery_start_utc": row.delivery_start_utc,
        "delivery_end_utc": row.delivery_end_utc,
        "bid_price": row.bid_price,
        "ask_price": row.ask_price,
        "last_price": row.last_price,
        "bid_quantity_mwh": row.bid_quantity_mwh,
        "ask_quantity_mwh": row.ask_quantity_mwh,
        "currency": row.currency,
        "unit": row.unit,
        "observed_at_utc": row.observed_at_utc,
        "received_at_utc": row.received_at_utc,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "quality_score": row.quality_score,
        "simulated": row.simulated,
        "metadata_json": row.metadata_json or {},
    }


def _opportunity_dict(
    row: IntradayOpportunityRecord,
    *,
    now_utc: datetime | None = None,
) -> dict:
    payload = {
        column.name: getattr(row, column.name)
        for column in IntradayOpportunityRecord.__table__.columns
    }
    now = _as_utc(now_utc or datetime.now(UTC))
    if _as_utc(row.valid_until_utc) < now:
        payload["status"] = "EXPIRED"
        payload["human_review_required"] = True
        payload["warnings"] = _unique([*(row.warnings or []), "OPPORTUNITY_EXPIRED"])
    return payload


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
