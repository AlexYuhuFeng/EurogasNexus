"""DB composition for normalized quotes and intraday opportunity snapshots."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    CompanyTsoAccessRecord,
    FxObservationRecord,
    IntradayOpportunityRecord,
    MarketQuoteRecord,
    RouteCandidateRecord,
)
from eurogas_nexus.db.repositories.route_cost import list_tso_tariffs
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
