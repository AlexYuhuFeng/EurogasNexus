"""Read-only /api/market routes.

The loading and shaping code for every slice lives in
``eurogas_nexus.application.projections.market_reads`` so the Wave 5
MarketContext projection composes exactly these reads instead of re-implementing
them. This module keeps the HTTP concerns: the runtime-database guard, the
``503 runtime_db_unavailable`` translation and the response envelope. Every
response field of every endpoint below is unchanged.
"""

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.dependencies.row_entitlement import current_principal
from eurogas_nexus.application.projections.market_reads import (
    annotate_quotes,
    derive_intraday_spreads,
    filter_entitled_opportunities,
    filter_entitled_rows,
    fx_observation_row,
    fx_observations,
    fx_row_from_market_observation,
    intraday_opportunities,
    market_observation_row,
    market_quotes,
    normalized_market_view,
    quote_close_rows,
    source_family_filter,
)
from eurogas_nexus.application.refreshable_reads import (
    FORMAT_DESCRIPTION,
    FX_COLUMNS,
    OBSERVATION_COLUMNS,
    REFRESH_FORMAT_PATTERN,
)
from eurogas_nexus.domain.market.fx_fixings import (
    FxFixingError,
    resolve_fixing,
    select_fixing_rates,
)
from eurogas_nexus.domain.market.interest_rates import (
    BENCHMARKS,
    InterestRateError,
    resolve_financing_rate,
)
from eurogas_nexus.domain.market.interest_rates import (
    benchmark as rate_benchmark,
)
from eurogas_nexus.domain.market.products import (
    ProductCodeError,
    resolve_product,
    standard_strip,
)
from eurogas_nexus.domain.market.units import (
    ENERGY_UNITS_PER_MWH,
    PRICE_UNITS,
    UnitConversionError,
    canonical_price_unit,
    convert_price,
)

router = APIRouter(tags=["market"])


#: DATA-1: the ``as_of`` query parameter of the market reads that can answer "as known at".
_AS_OF_DESCRIPTION = (
    "ISO 8601 UTC instant (e.g. 2026-11-20T17:30:00Z). Answer with what was known then: each "
    "figure at the revision current at that instant, with its revision number, publication "
    "time and the time this store first held it. Omitted: the current read, unchanged."
)


def _flat_csv(rows: list[dict], *, columns, report: str):
    """DATA-1 refreshable read: the rows as CSV with a fixed header (export decision applied)."""

    from eurogas_nexus.api.csv_export import csv_response
    from eurogas_nexus.application.refreshable_reads import flat_rows

    return csv_response(flat_rows(rows, columns), report=report, columns=columns)


def _as_of(text: str | None) -> datetime | None:
    """The parsed ``as_of``; 422 ``as_of_invalid`` / ``as_of_in_future`` when unusable."""

    from eurogas_nexus.application.as_of_reads import AsOfError, parse_as_of

    try:
        return parse_as_of(text)
    except AsOfError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from exc


_PAGE_LIMIT = Query(
    default=1000,
    ge=1,
    le=10_000,
    description="Rows per page (1..10000); meta.continuation says whether more follow.",
)
_PAGE_CURSOR = Query(default=None, max_length=512, description="meta.continuation.cursor")
_FROM_UTC = Query(default=None, description="Oldest observed_at_utc (ISO-8601 with offset)")
_TO_UTC = Query(default=None, description="Newest observed_at_utc (ISO-8601 with offset)")


def _page_request(limit, cursor, from_utc, to_utc, filters):
    """The page asked for; 400 with the paging code on a bad bound or cursor."""

    from eurogas_nexus.application.keyset_paging import PageCursorError, page_request

    try:
        return page_request(
            limit=limit, cursor=cursor, from_utc=from_utc, to_utc=to_utc, filters=filters
        )
    except PageCursorError as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "message": str(exc)}
        ) from exc


def _paged_csv(rows, continuation: dict, *, columns, report: str):
    """A page as CSV; the continuation rides in headers (a spreadsheet reads no meta)."""

    response = _flat_csv(rows, columns=columns, report=report)
    response.headers["X-Eurogas-Page-Limit"] = str(continuation["limit"])
    response.headers["X-Eurogas-Has-More"] = "true" if continuation["has_more"] else "false"
    if continuation["cursor"]:
        response.headers["X-Eurogas-Next-Cursor"] = continuation["cursor"]
    return response


@router.get("/api/market/observations")
def list_observations(
    request: Request,
    as_of: str | None = Query(default=None, description=_AS_OF_DESCRIPTION),
    format: str = Query(
        default="json", pattern=REFRESH_FORMAT_PATTERN, description=FORMAT_DESCRIPTION
    ),
    limit: int = _PAGE_LIMIT,
    cursor: str | None = _PAGE_CURSOR,
    from_utc: str | None = _FROM_UTC,
    to_utc: str | None = _TO_UTC,
    product: str | None = Query(default=None, max_length=64, description="Product or hub code"),
    market_venue: str | None = Query(default=None, max_length=64),
    source_system: str | None = Query(default=None, max_length=64),
) -> dict:
    """List market observations from the runtime DB, newest first, one keyset page at a time.

    返回市场观测（按观测时间倒序分页）；DB 未配置时降级为空并告警（fail-closed）。

    The read used to return the whole table (20.8 MB on the demo desk). It now answers one
    page (``limit``, default 1,000) with ``meta.continuation`` (``has_more``, ``cursor``);
    a caller that needs a whole range asks for it with ``from_utc``/``to_utc`` and follows
    ``cursor`` (``application/keyset_paging``). ``product`` matches a product or every
    product of a hub (``TTF`` matches ``TTF Month-Ahead``).

    Args:
        request: Incoming FastAPI request (used for row entitlement).
        as_of: DATA-1, read as known at this instant (see ``application/as_of_reads``).
        format: DATA-1, ``csv`` for flat rows with a fixed header (Power Query); the
            continuation is in the ``X-Eurogas-Has-More``/``X-Eurogas-Next-Cursor`` headers.

    Raises:
        HTTPException: 400 ``page_cursor_invalid``/``page_cursor_filter_mismatch``/
            ``page_window_invalid``; 503 ``runtime_db_unavailable`` on DB read failure.
    """

    moment = _as_of(as_of)
    filters = {
        "as_of": as_of or "", "product": product or "", "market_venue": market_venue or "",
        "source_system": source_system or "",
    }
    page = _page_request(limit, cursor, from_utc, to_utc, filters)
    if not _db_is_configured():
        if format == "csv":
            return _flat_csv([], columns=OBSERVATION_COLUMNS, report="market-observations")
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; market observations are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.application.keyset_paging import iso_ts, page_rows
        from eurogas_nexus.application.projections.market_reads import (
            market_observation_keyset_page,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            if moment is None:
                rows, more = market_observation_keyset_page(
                    session, current_principal(request), page, product=product,
                    market_venue=market_venue, source_system=source_system,
                )
                rows = _filter_entitled_rows(request, rows, source_key="source_system")
            else:
                from eurogas_nexus.application.as_of_reads import market_observations_as_of

                known = _filter_entitled_rows(
                    request, market_observations_as_of(session, moment), source_key="source_system"
                )
                known = [
                    row for row in known
                    if (not product or row["product"] == product
                        or str(row["product"]).startswith(f"{product} "))
                    and (not market_venue or row["market_venue"] == market_venue)
                    and (not source_system or row["source_system"] == source_system)
                ]
                rows, more = page_rows(
                    known, page, ts_of=iso_ts, id_of=lambda row: str(row["observation_id"])
                )
        if format == "csv":
            return _paged_csv(
                rows, more, columns=OBSERVATION_COLUMNS, report="market-observations"
            )
        envelope = _env(rows, source="runtime-postgresql")
        envelope["meta"]["continuation"] = more
        return envelope
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/fx")
def list_fx(
    request: Request,
    as_of: str | None = Query(default=None, description=_AS_OF_DESCRIPTION),
    format: str = Query(
        default="json", pattern=REFRESH_FORMAT_PATTERN, description=FORMAT_DESCRIPTION
    ),
    limit: int = _PAGE_LIMIT,
    cursor: str | None = _PAGE_CURSOR,
    from_utc: str | None = _FROM_UTC,
    to_utc: str | None = _TO_UTC,
    pair: str | None = Query(default=None, max_length=16, description="e.g. EUR/GBP"),
) -> dict:
    """List FX observations from the runtime DB, newest first, one keyset page at a time.

    返回汇率观测（分页）；DB 未配置时降级为空并告警。

    Same paging as ``/api/market/observations`` (``meta.continuation``; CSV headers).

    Raises:
        HTTPException: 400 on a bad cursor or bound; 503 ``runtime_db_unavailable``.
    """

    moment = _as_of(as_of)
    filters = {"as_of": as_of or "", "pair": pair or ""}
    page = _page_request(limit, cursor, from_utc, to_utc, filters)
    if not _db_is_configured():
        if format == "csv":
            return _flat_csv([], columns=FX_COLUMNS, report="market-fx")
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; ECB FX observations are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.application.keyset_paging import iso_ts, page_rows
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            if moment is None:
                rows = fx_observations(session)
            else:
                from eurogas_nexus.application.as_of_reads import fx_observations_as_of

                rows = fx_observations_as_of(session, moment)
        # Licensed fixes (WMR/BFIX) share this table: filter like every other row read.
        rows = _filter_entitled_rows(request, rows, source_key="source_system")
        if pair:
            rows = [row for row in rows if str(row.get("pair") or "").upper() == pair.upper()]
        # The FX read unions two tables (fixings, and the ECB rows of the market table), so
        # the page is taken over the read rows; the answer is bounded either way.
        rows, more = page_rows(
            rows, page, ts_of=iso_ts,
            id_of=lambda row: str(row.get("observation_id") or row.get("pair") or ""),
        )
        if format == "csv":
            return _paged_csv(rows, more, columns=FX_COLUMNS, report="market-fx")
        envelope = _env(rows, source="runtime-postgresql")
        envelope["meta"]["continuation"] = more
        return envelope
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/quotes")
def list_quotes(
    request: Request,
    hub: str | None = None,
    product: str | None = None,
    source_system: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    cursor: str | None = _PAGE_CURSOR,
    from_utc: str | None = _FROM_UTC,
    to_utc: str | None = _TO_UTC,
) -> dict:
    """Return normalized L1 quotes from the runtime DB, newest first, one keyset page.

    The page used to stop at ``limit`` without saying so; it now states
    ``meta.continuation`` (``has_more``, ``cursor``) like every paged read.
    """

    page = _page_request(
        limit, cursor, from_utc, to_utc,
        {"hub": hub or "", "product": product or "", "source_system": source_system or ""},
    )

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; market quotes are unavailable."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.application.price_resolver import attach_resolved, open_price_book
        from eurogas_nexus.db.session import get_session_factory

        now = datetime.now(UTC)
        with get_session_factory()() as session:
            found, more = market_quotes(
                session, hub=hub, product=product, source_system=source_system, page=page
            )
            rows = _filter_entitled_rows(request, found, source_key="source_system")
            # P-08: the one price every screen reads for each quote's hub and window.
            book = open_price_book(
                session, request, now=now, hubs={str(row.get("hub") or "") for row in rows}
            )
        # Each quote with its as-of, age against the source's cadence and the previous close
        # (additive fields; the close is read from the desk's daily closes for this caller).
        envelope = _env(
            attach_resolved(annotate_quotes(rows, quote_close_rows(request, now), now=now), book),
            source="runtime-postgresql",
        )
        envelope["meta"]["continuation"] = more
        return envelope
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/prices")
def list_prices(
    request: Request,
    hub: list[str] = Query(default=[], description="Hub codes, repeated or comma-separated"),
    start: str | None = Query(default=None, description="First delivery month, YYYY-MM"),
    months: int = Query(default=12, ge=1, le=36),
    side: str = Query(default="mid", pattern="^(mid|bid|ask)$"),
    include_simulated: bool = Query(default=False),
    as_of: str | None = Query(default=None, description=_AS_OF_DESCRIPTION),
    format: str = Query(
        default="json", pattern=REFRESH_FORMAT_PATTERN, description=FORMAT_DESCRIPTION
    ),
) -> dict:
    """The monthly price strip (curve) of each hub: the one price per month (DATA-1, P-08).

    One flat row per hub and delivery month with the price every screen reads for it, its
    kind, source and age, and the version it was: ``revision``, ``published_at_utc``,
    ``known_from_utc``. With ``as_of`` the strip is the one known at that instant (ticks
    received by then, each settlement at its revision current then, the marks in force).
    A month with no price held is a row with empty price fields. Simulated prices are left
    out unless ``include_simulated`` is true, and are marked when included. ``format=csv``
    answers the same rows as a file with the fixed column order (Power Query, DATA-1).
    """

    from eurogas_nexus.application.price_strip import (
        PRICE_STRIP_COLUMNS,
        PriceStripError,
        price_strip_rows,
        strip_hubs,
        strip_months,
    )

    moment = _as_of(as_of)
    now = datetime.now(UTC)
    try:
        hubs = strip_hubs(hub)
        first_days = strip_months(start, months, at=moment or now)
    except PriceStripError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from exc
    if not _db_is_configured():
        if format == "csv":
            return _flat_csv([], columns=PRICE_STRIP_COLUMNS, report="price-strip")
        envelope = _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; prices are unavailable."],
        )
        envelope["meta"]["columns"] = list(PRICE_STRIP_COLUMNS)
        return envelope
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = price_strip_rows(
                session,
                request,
                hubs=hubs,
                months=first_days,
                as_of=moment,
                side=side,
                include_simulated=include_simulated,
                now=now,
            )
        if format == "csv":
            return _flat_csv(rows, columns=PRICE_STRIP_COLUMNS, report="price-strip")
        envelope = _env(rows, source="runtime-postgresql")
        envelope["meta"]["columns"] = list(PRICE_STRIP_COLUMNS)
        envelope["meta"]["as_of_utc"] = None if moment is None else moment.isoformat()
        return envelope
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/changes")
def list_market_changes(
    request: Request,
    after: str | None = Query(
        default=None,
        description="The next_cursor of the previous page; omitted: from the first event; "
        "'latest': no events, only the cursor of the newest one",
    ),
    kinds: list[str] = Query(
        default=[], description="Event types, repeated or comma-separated (price.updated...)"
    ),
    subject: str | None = Query(
        default=None, max_length=160, description="Subject key prefix, e.g. hub:TTF or cargo:"
    ),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    """What changed since a cursor: market events, oldest first, as digests (DATA-1, P2).

    Read-only and poll-safe: each page ends with ``meta.next_cursor``; asking again with it
    returns only what was recorded since, in a stable order that never skips a committed
    event. Each change names the event (key, type, subject, revision, ``insert`` or
    ``update``, times, source, the snapshot keys it touches) and never its value: read the
    value through the entitled read (for a price, ``/api/market/observations?as_of=``).
    Entitlement is per caller: a market event by its source family, a desk event only for a
    caller who may read the portfolio across every book. Retention: the outbox is
    append-only and nothing prunes it.
    """

    from eurogas_nexus.application.change_feed import (
        CHANGE_COLUMNS,
        ChangeFeedError,
        parse_cursor,
        parse_kinds,
        read_changes,
    )

    try:
        position = parse_cursor(after)
        wanted = parse_kinds(kinds)
    except ChangeFeedError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from exc
    if not _db_is_configured():
        envelope = _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; market changes are unavailable."],
        )
        envelope["meta"].update({"next_cursor": after, "has_more": False})
        return envelope
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            page = read_changes(
                session,
                current_principal(request),
                after=position,
                kinds=wanted,
                subject_prefix=subject,
                limit=limit,
            )
        envelope = _env(page.changes, source="runtime-postgresql")
        envelope["meta"].update(
            {
                "next_cursor": page.next_cursor,
                "has_more": page.has_more,
                "columns": list(CHANGE_COLUMNS),
                "retention": "full history; market events are append-only and never pruned",
            }
        )
        return envelope
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/opportunities")
def list_opportunities(
    request: Request,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Return backend-calculated intraday decision snapshots."""

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; intraday opportunities are unavailable."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = filter_entitled_opportunities(
                session,
                current_principal(request),
                intraday_opportunities(session, status=status, limit=limit),
            )
        return _env(rows, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/normalized")
def list_normalized_view(
    request: Request,
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict:
    """Return the backend-normalized market view (hub/tenor/FX->GBP per row)."""

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; normalized market view is unavailable."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        identity = current_principal(request)
        with get_session_factory()() as session:
            view = normalized_market_view(
                session,
                limit=limit,
                source_filter=source_family_filter(identity),
            )
        envelope = _env(
            view["rows"],
            source="runtime-postgresql",
            warnings=view["warnings"],
        )
        envelope["meta"]["window"] = _row_window(view["rows"], limit)
        return envelope
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _row_window(rows: list[dict], limit: int) -> dict:
    """The rows a bounded read returned, stated so nothing outside them reads as absent.

    The view is the newest ``limit`` observations with per-source coverage; ``limit_reached``
    says older rows may exist beyond it, and the observed range says which instants the rows
    span.
    """

    observed = sorted(str(row.get("observed_at_utc")) for row in rows if row.get("observed_at_utc"))
    return {
        "row_limit": limit,
        "returned": len(rows),
        "limit_reached": len(rows) >= limit,
        "observed_from_utc": observed[0] if observed else None,
        "observed_to_utc": observed[-1] if observed else None,
    }


@router.get("/api/market/spreads")
def list_spreads(request: Request) -> dict:
    """List intraday cross-hub spreads derived from runtime opportunities.

    返回由日内机会派生的跨枢纽价差（gross spread）；DB 未配置或未采集
    价格时降级为空并告警。

    Args:
        request: Incoming FastAPI request (unused except wiring).

    Returns:
        Enveloped spread rows or an empty enveloped response.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` on DB read failure.
    """

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Spread calculation requires sourced prices in runtime DB."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            opportunities = filter_entitled_opportunities(
                session, current_principal(request), intraday_opportunities(session, limit=100)
            )
        return _env(derive_intraday_spreads(opportunities), source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _filter_entitled_rows(request: Request, rows: list[dict], *, source_key: str) -> list[dict]:
    """Apply row-level commercial entitlement to DB-identity callers.

    Legacy public-token deployments retain the single-trust-domain view. A
    DB-backed identity sees only rows whose source family is in its data
    scopes (public baseline families remain visible to all).

    The rule itself lives in the application layer
    (:func:`eurogas_nexus.application.projections.market_reads.filter_entitled_rows`)
    so the MarketContext projection applies exactly the same filter.
    """

    return filter_entitled_rows(current_principal(request), rows, source_key=source_key)


def _market_row(row):
    """Shape one market observation row (compatibility alias, see market_reads)."""

    return market_observation_row(row)


def _fx_row(row):
    """Shape one FX observation row (compatibility alias, see market_reads)."""

    return fx_observation_row(row)


def _fx_row_from_market_observation(row):
    """Shape one ECB market observation as FX (compatibility alias)."""

    return fx_row_from_market_observation(row)


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for market reads.",
            "error_class": exc.__class__.__name__,
        },
    )


@router.get("/api/market/products")
def list_products(
    trade_date: date | None = None,
    code: list[str] | None = Query(default=None, max_length=32),
) -> dict:
    """Resolve gas product codes (DA, WE, BOM, M+1, Q+1, Sum-27, Cal-27...) to delivery.

    Without ``code`` the standard desk strip is returned. Pure calendar logic; no DB.
    无 code 参数时返回标准交易曲线条（WD→Cal+1）；纯日历计算，不读数据库。

    Raises:
        HTTPException: 422 ``unknown_product_code`` for an unknown/expired code.
    """

    anchor = trade_date or datetime.now(UTC).date()
    if not code:
        periods = standard_strip(anchor)
    else:
        try:
            periods = [resolve_product(item, anchor) for item in code]
        except ProductCodeError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "unknown_product_code", "message": str(exc)},
            ) from exc
    return _env(
        {"trade_date": anchor.isoformat(), "products": [p.as_dict() for p in periods]},
        source="gas-product-calendar",
        warnings=["Exchange holiday calendars are not applied to DA."],
    )


@router.get("/api/market/price-conversion")
def convert_market_price(
    request: Request,
    value: float = Query(..., allow_inf_nan=False),
    from_unit: str = Query(..., max_length=16),
    to_unit: str | None = Query(default=None, max_length=16),
    fx_source: str = Query(default="ECB", max_length=8),
    fx_fixing: str | None = Query(default=None, max_length=32),
    fx_date: date | None = None,
    fx_average_from: date | None = None,
    fx_average_to: date | None = None,
    gbp_per_eur: float | None = Query(default=None, gt=0),
    usd_per_eur: float | None = Query(default=None, gt=0),
) -> dict:
    """Convert a gas price between EUR/MWh, GBp/th, USD/MMBtu and related quotations.

    FX comes from the named benchmark fix: ``fx_source`` ECB (default), WMR
    (WM/Reuters) or BFIX (Bloomberg), optionally a specific ``fx_fixing``, on
    ``fx_date`` or averaged over ``fx_average_from``..``fx_average_to`` (LNG
    pricing-period practice); latest fix otherwise. Explicit ``*_per_eur`` values
    override per currency. Licensed fixes are entitlement-filtered per principal.
    汇率来自指定基准定盘（ECB/WMR/BFIX），可指定日期或定价期平均；显式参数优先。

    Raises:
        HTTPException: 422 ``unsupported_price_unit`` / ``fx_rate_unavailable`` /
            ``unknown_fx_fixing``.
    """

    try:
        fixing = resolve_fixing(fx_source, fx_fixing)
        selection: dict[str, object] = {"eur_rates": {}, "value_dates": [], "fixings_used": 0}
        if _db_is_configured() and (gbp_per_eur is None or usd_per_eur is None):
            selection = select_fixing_rates(
                _filter_entitled_rows(request, _fx_rows(), source_key="source_system"),
                fixing,
                on=fx_date,
                average_from=fx_average_from,
                average_to=fx_average_to,
            )
    except FxFixingError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "unknown_fx_fixing", "message": str(exc)}
        ) from exc

    rates: dict[str, dict[str, object]] = {}
    fixing_rates = selection["eur_rates"]
    for currency in ("GBP", "USD"):
        if currency in fixing_rates:
            rates[currency] = {
                "rate": fixing_rates[currency],
                "source": fixing.source_system,
                "fixing": fixing.fixing_id,
                "value_dates": selection["value_dates"],
            }
    if gbp_per_eur is not None:
        rates["GBP"] = {"rate": gbp_per_eur, "source": "request"}
    if usd_per_eur is not None:
        rates["USD"] = {"rate": usd_per_eur, "source": "request"}
    targets = [to_unit] if to_unit else list(PRICE_UNITS)
    eur_rates = {currency: float(entry["rate"]) for currency, entry in rates.items()}
    converted: dict[str, float | None] = {}
    try:
        source_unit = canonical_price_unit(from_unit)
        for target in targets:
            try:
                converted[canonical_price_unit(target)] = convert_price(
                    value, source_unit, target, eur_rates=eur_rates
                )
            except UnitConversionError:
                if to_unit:
                    raise
                converted[canonical_price_unit(target)] = None
    except UnitConversionError as exc:
        code = "fx_rate_unavailable" if "FX" in str(exc) else "unsupported_price_unit"
        raise HTTPException(status_code=422, detail={"code": code, "message": str(exc)}) from exc
    warnings = (
        []
        if len(rates) == 2
        else [f"Some {fixing.label} rates are unavailable for this request; null values."]
    )
    return _env(
        {
            "value": value,
            "from_unit": source_unit,
            "converted": converted,
            "fx": rates,
            "fx_fixing": {
                "fixing_id": fixing.fixing_id,
                "source_system": fixing.source_system,
                "label": fixing.label,
                "licensed": fixing.licensed,
                "fixings_used": selection["fixings_used"],
                "averaged": fx_average_from is not None,
            },
            "factors": {
                "therm_per_mwh": ENERGY_UNITS_PER_MWH["therm"],
                "mmbtu_per_mwh": ENERGY_UNITS_PER_MWH["MMBtu"],
            },
        },
        source="gas-unit-conversion",
        warnings=warnings,
    )


@router.get("/api/market/interest-rates")
def list_interest_rates(
    request: Request,
    benchmark: str | None = Query(default=None, max_length=8),
    limit: int = Query(default=30, ge=1, le=400),
) -> dict:
    """Overnight benchmark fixings (SONIA, €STR, SOFR), newest first per benchmark.

    返回隔夜基准利率定盘（按基准最新在前）；DB 未配置时降级为空并告警。

    Raises:
        HTTPException: 422 ``unknown_benchmark``; 503 ``runtime_db_unavailable``.
    """

    selected = None
    if benchmark:
        try:
            selected = rate_benchmark(benchmark).benchmark_id
        except InterestRateError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "unknown_benchmark", "message": str(exc)}
            ) from exc
    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; benchmark fixings are unavailable."],
        )
    rows = _filter_entitled_rows(request, _interest_rate_rows(selected), source_key="source_system")
    per_benchmark: dict[str, int] = {}
    limited = []
    for row in rows:
        count = per_benchmark.get(row["benchmark_id"], 0)
        if count < limit:
            limited.append(row)
            per_benchmark[row["benchmark_id"]] = count + 1
    benchmarks = {
        key: {
            "label": item.label,
            "currency": item.currency,
            "day_count": item.day_count,
            "administrator": item.administrator,
            "attribution": item.attribution,
        }
        for key, item in BENCHMARKS.items()
    }
    return _env({"benchmarks": benchmarks, "fixings": limited}, source="runtime-postgresql")


@router.get("/api/market/financing-rate")
def resolve_contract_financing_rate(
    request: Request,
    benchmark: str = Query(..., max_length=8),
    as_of: date | None = None,
    spread_bps: float = Query(default=0.0, ge=-1000, le=5000, allow_inf_nan=False),
    max_staleness_days: int = Query(default=7, ge=0, le=31),
) -> dict:
    """All-in contract financing rate = benchmark fixing on/before ``as_of`` + spread.

    Returns the rate on the benchmark's own day count and restated on ACT/365F (the
    basis the early-cash term accrues on), with the fixing date and source.
    合同融资利率 = 截至 as_of 的基准定盘 + 点差；同时给出 ACT/365F 等效利率。

    Raises:
        HTTPException: 422 ``financing_rate_unavailable`` (unknown benchmark, no or
            stale fixing); 503 ``runtime_db_unavailable``.
    """

    anchor = as_of or datetime.now(UTC).date()
    try:
        rate_benchmark(benchmark)
        rows = (
            _filter_entitled_rows(request, _interest_rate_rows(None), source_key="source_system")
            if _db_is_configured()
            else []
        )
        resolved = resolve_financing_rate(
            rows,
            benchmark,
            as_of=anchor,
            spread_bps=spread_bps,
            max_staleness_days=max_staleness_days,
        )
    except InterestRateError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "financing_rate_unavailable", "message": str(exc)},
        ) from exc
    return _env(resolved.as_dict(), source="runtime-postgresql")


def _interest_rate_rows(benchmark_id: str | None) -> list[dict]:
    """Stored fixings, newest first (entitlement applied by the caller)."""

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import InterestRateObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            query = session.query(InterestRateObservationRecord)
            if benchmark_id:
                query = query.filter(InterestRateObservationRecord.benchmark_id == benchmark_id)
            records = query.order_by(InterestRateObservationRecord.value_date.desc()).all()
            return [
                {
                    "benchmark_id": record.benchmark_id,
                    "currency": record.currency,
                    "value_date": record.value_date.isoformat(),
                    "rate_pct": record.rate_pct,
                    "day_count": record.day_count,
                    "source_system": record.source_system,
                    "source_reference": record.source_reference,
                    "ingested_at_utc": record.ingested_at_utc.isoformat(),
                }
                for record in records
            ]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _fx_rows() -> list[dict]:
    """All FX observation rows from the runtime DB (entitlement applied by caller)."""

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return fx_observations(session)
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _env(data: object, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings or [],
        },
    }
