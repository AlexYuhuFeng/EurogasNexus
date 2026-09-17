"""Market read composition shared by the market routes and the projections.

This module is the single home of the market loading and shaping code that
``api/routes/public/market.py`` used to own privately. Both the existing
``/api/market/*`` handlers and the Wave 5 ``MarketContext`` projection call
these functions, so the projection is a composition over the same reads instead
of a second implementation of the same queries.

Row shapes are preserved byte-for-byte from the handlers they came from: the
``/api/market/observations``, ``/api/market/fx`` and ``/api/market/spreads``
responses must keep every field they returned before this extraction.

Every function takes an explicit ``session``: the runtime-database decision and
the ``503 runtime_db_unavailable`` translation stay in the route (HTTP
concerns), while the query, the shaping and the entitlement rule live here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    principal_allows_source_family,
)

if TYPE_CHECKING:  # pragma: no cover - import boundary: importing the API must not
    # load SQLAlchemy (tests/contract/test_db_foundation.py). Annotations are
    # strings here, so no runtime import is needed.
    from sqlalchemy.orm import Session

#: Canonical runtime tables the market reads are composed from.
MARKET_TABLE_LINEAGE: tuple[str, ...] = (
    "market_observations",
    "market_quotes",
    "intraday_opportunities",
    "fx_observations",
)

#: Entitlement rule labels used in projection entitlement records.
ENTITLEMENT_RULE_SOURCE_FAMILY = "row source family must be granted to the principal"
ENTITLEMENT_RULE_LEGACY = "legacy public token keeps the single-trust-domain view"


def runtime_db_configured() -> bool:
    """Whether a runtime database URL is configured (existing resolution order)."""

    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def source_family_filter(principal: AuthenticatedPrincipal) -> Callable[[str], bool]:
    """Return the fail-closed source-family predicate for one principal.

    This is the same predicate ``/api/market/normalized`` passes into the
    repository, so the normalized read never even fetches a restricted source.
    """

    return lambda source_system: principal_allows_source_family(principal, source_system)


def row_allowed(principal: AuthenticatedPrincipal, source_system: str | None) -> bool:
    """Decide one row's commercial entitlement, fail-closed.

    Args:
        principal: The authenticated principal.
        source_system: The row's source system (``None``/blank fails closed for
            a scoped principal).

    Returns:
        ``True`` for the legacy public token (single trust domain) and for any
        source family granted to the principal; ``False`` otherwise.
    """

    if principal.auth_method == "legacy_public_token":
        return True
    return principal_allows_source_family(principal, source_system or "")


def filter_entitled_rows(
    principal: AuthenticatedPrincipal,
    rows: Iterable[dict[str, Any]],
    *,
    source_key: str = "source_system",
) -> list[dict[str, Any]]:
    """Apply row-level commercial entitlement to DB-identity callers.

    Legacy public-token deployments retain the single-trust-domain view. A
    DB-backed or OIDC identity sees only rows whose source family is in its data
    scopes (public baseline families remain visible to all). A row without a
    usable ``source_key`` is dropped rather than kept: the check fails closed.

    Args:
        principal: The authenticated principal.
        rows: Row dicts to filter.
        source_key: Row field naming the source system.

    Returns:
        The rows the principal may see, in input order.
    """

    materialized = list(rows)
    if principal.auth_method == "legacy_public_token":
        return materialized
    return [
        row for row in materialized if row_allowed(principal, row.get(source_key))
    ]


def market_observations(session: Session) -> list[dict[str, Any]]:
    """Return every market observation row, newest first (undeduped).

    Returns:
        Market observation payloads ordered by observed instant, then venue and
        product - the ordering ``/api/market/observations`` has always used.
    """

    from eurogas_nexus.db.models import MarketObservationRecord

    rows = session.query(MarketObservationRecord).order_by(
        MarketObservationRecord.observed_at_utc.desc(),
        MarketObservationRecord.market_venue,
        MarketObservationRecord.product,
    )
    return [market_observation_row(row) for row in rows.all()]


def fx_observations(session: Session) -> list[dict[str, Any]]:
    """Return FX observations, falling back to ECB market observations.

    Returns:
        FX payloads from ``fx_observations`` when that table has rows, otherwise
        the ECB rows of ``market_observations`` reshaped as FX - exactly the
        behaviour ``/api/market/fx`` already had.
    """

    from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord

    rows = session.query(FxObservationRecord).order_by(
        FxObservationRecord.observed_at_utc.desc(),
        FxObservationRecord.pair,
    ).all()
    if rows:
        return [fx_observation_row(row) for row in rows]
    market_rows = session.query(MarketObservationRecord).filter(
        MarketObservationRecord.source_system == "ECB"
    ).order_by(MarketObservationRecord.observed_at_utc.desc())
    return [fx_row_from_market_observation(row) for row in market_rows.all()]


def market_quotes(
    session: Session,
    *,
    hub: str | None = None,
    product: str | None = None,
    source_system: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Return normalized L1 quotes newest first (repository filter semantics)."""

    from eurogas_nexus.db.repositories.market_intelligence import list_market_quotes

    return list_market_quotes(
        session,
        hub=hub,
        product=product,
        source_system=source_system,
        limit=limit,
    )


def intraday_opportunities(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 100,
    now_utc: Any = None,
) -> list[dict[str, Any]]:
    """Return backend-calculated intraday opportunity snapshots."""

    from eurogas_nexus.db.repositories.market_intelligence import (
        list_intraday_opportunities,
    )

    return list_intraday_opportunities(
        session,
        status=status,
        limit=limit,
        now_utc=now_utc,
    )


def normalized_market_view(
    session: Session,
    *,
    limit: int = 500,
    source_filter: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Return the backend-normalized market view (hub/tenor/FX->GBP per row)."""

    from eurogas_nexus.db.repositories.market_intelligence import (
        list_normalized_market_view,
    )

    return list_normalized_market_view(session, limit=limit, source_filter=source_filter)


def derive_intraday_spreads(
    opportunities: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Derive cross-hub spreads from already-read opportunity snapshots.

    Args:
        opportunities: Opportunity rows, as returned by
            :func:`intraday_opportunities`.

    Returns:
        Spread payloads with exactly the fields ``/api/market/spreads`` has
        always returned. The derivation is a pure function of the supplied
        rows: the projection therefore closes the spreads slice over the same
        opportunity read it reports, instead of querying twice and risking two
        different as-of instants.
    """

    return [
        {
            "spread_id": row["opportunity_id"],
            "name": f"{row['buy_hub']} -> {row['sell_hub']} {row['product']}",
            "from_venue": row["buy_venue"],
            "to_venue": row["sell_venue"],
            "from_hub": row["buy_hub"],
            "to_hub": row["sell_hub"],
            "spread_eur_mwh": row["gross_spread"],
            "period": row["product"],
        }
        for row in opportunities
    ]


def market_observation_row(row: Any) -> dict[str, Any]:
    """Shape one market observation ORM row into its API payload."""

    from eurogas_nexus.governance.entitlement import entitlement_scope_for_source

    return {
        "observation_id": row.observation_id,
        "market_venue": row.market_venue,
        "product": row.product,
        "price": row.price,
        "unit": row.unit,
        "currency": row.currency,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "source_record_id": row.source_record_id,
        "freshness": row.freshness,
        "quality_score": row.quality_score,
        "entitlement_scope": entitlement_scope_for_source(row.source_system),
        "research_only": row.research_only,
        "metadata_json": row.metadata_json or {},
    }


def fx_observation_row(row: Any) -> dict[str, Any]:
    """Shape one FX observation ORM row into its API payload."""

    from eurogas_nexus.governance.entitlement import entitlement_scope_for_source

    return {
        "observation_id": row.observation_id,
        "pair": row.pair,
        "base_currency": row.base_currency,
        "quote_currency": row.quote_currency,
        "rate": row.rate,
        "rate_type": row.rate_type,
        "value_date": row.value_date,
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "entitlement_scope": entitlement_scope_for_source(row.source_system),
        "research_only": row.research_only,
    }


def fx_row_from_market_observation(row: Any) -> dict[str, Any]:
    """Shape one ECB market observation into the FX payload."""

    from eurogas_nexus.governance.entitlement import entitlement_scope_for_source

    quote = row.currency
    pair = row.product.replace("/", "")
    return {
        "observation_id": row.observation_id,
        "pair": pair,
        "base_currency": "EUR",
        "quote_currency": quote,
        "rate": row.price,
        "rate_type": "reference",
        "value_date": row.period_start_utc.date().isoformat(),
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "entitlement_scope": entitlement_scope_for_source(row.source_system),
        "research_only": row.research_only,
    }
