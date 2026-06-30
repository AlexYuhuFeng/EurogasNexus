"""Repository helpers for DB-first route-cost decision support."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.route_cost import (
    CapacityProfileRecord,
    LiveMarketMarkRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.live_markets import LiveMarketMark
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff


def list_tso_tariffs(session: Session) -> list[CapacityTariff]:
    rows = session.query(TsoTariffRecord).order_by(
        TsoTariffRecord.country,
        TsoTariffRecord.source_point_name,
        TsoTariffRecord.direction,
        TsoTariffRecord.gas_year,
    )
    return [_tariff_from_record(row) for row in rows.all()]


def list_upstream_contracts(session: Session) -> list[dict]:
    rows = session.query(UpstreamResourceContractRecord).order_by(
        UpstreamResourceContractRecord.updated_at_utc.desc()
    )
    return [_contract_payload(row) for row in rows.all()]


def upsert_upstream_contract(session: Session, data: Mapping[str, object]) -> dict:
    now = datetime.now(UTC)
    contract_id = str(data["contract_id"])
    row = session.get(UpstreamResourceContractRecord, contract_id)
    if row is None:
        row = UpstreamResourceContractRecord(
            contract_id=contract_id,
            contract_name=str(data["contract_name"]),
            resource_type=str(data["resource_type"]),
            delivery_point_name=str(data["delivery_point_name"]),
            gas_year=str(data["gas_year"]),
            delivery_quantity_mwh_per_day=float(data["delivery_quantity_mwh_per_day"]),
            contract_price_gbp_mwh=float(data["contract_price_gbp_mwh"]),
            settlement_frequency=str(data["settlement_frequency"]),
            upstream_payment_lag_days=int(data["upstream_payment_lag_days"]),
            screen_sale_cash_lag_days=int(data["screen_sale_cash_lag_days"]),
            delivery_tolerance_pct=float(data["delivery_tolerance_pct"]),
            nomination_tolerance_pct=float(data["nomination_tolerance_pct"]),
            tolerance_risk_allowance_gbp_mwh=_optional_float(
                data.get("tolerance_risk_allowance_gbp_mwh")
            ),
            annual_financing_rate_pct=float(data["annual_financing_rate_pct"]),
            owned_entry_capacity_mwh_per_day=_optional_float(
                data.get("owned_entry_capacity_mwh_per_day")
            ),
            owned_exit_capacity_mwh_per_day=_optional_float(
                data.get("owned_exit_capacity_mwh_per_day")
            ),
            allowed_exit_points=_string_list(data.get("allowed_exit_points")),
            eligible_sale_modes=_string_list(data.get("eligible_sale_modes")),
            notes=_optional_string(data.get("notes")),
            created_at_utc=now,
            updated_at_utc=now,
        )
        session.add(row)
    else:
        row.contract_name = str(data["contract_name"])
        row.resource_type = str(data["resource_type"])
        row.delivery_point_name = str(data["delivery_point_name"])
        row.gas_year = str(data["gas_year"])
        row.delivery_quantity_mwh_per_day = float(data["delivery_quantity_mwh_per_day"])
        row.contract_price_gbp_mwh = float(data["contract_price_gbp_mwh"])
        row.settlement_frequency = str(data["settlement_frequency"])
        row.upstream_payment_lag_days = int(data["upstream_payment_lag_days"])
        row.screen_sale_cash_lag_days = int(data["screen_sale_cash_lag_days"])
        row.delivery_tolerance_pct = float(data["delivery_tolerance_pct"])
        row.nomination_tolerance_pct = float(data["nomination_tolerance_pct"])
        row.tolerance_risk_allowance_gbp_mwh = _optional_float(
            data.get("tolerance_risk_allowance_gbp_mwh")
        )
        row.annual_financing_rate_pct = float(data["annual_financing_rate_pct"])
        row.owned_entry_capacity_mwh_per_day = _optional_float(
            data.get("owned_entry_capacity_mwh_per_day")
        )
        row.owned_exit_capacity_mwh_per_day = _optional_float(
            data.get("owned_exit_capacity_mwh_per_day")
        )
        row.allowed_exit_points = _string_list(data.get("allowed_exit_points"))
        row.eligible_sale_modes = _string_list(data.get("eligible_sale_modes"))
        row.notes = _optional_string(data.get("notes"))
        row.updated_at_utc = now

    session.flush()
    return _contract_payload(row)


def latest_market_marks(session: Session) -> list[LiveMarketMark]:
    rows = session.query(LiveMarketMarkRecord).order_by(
        LiveMarketMarkRecord.mark_time_utc.desc()
    )
    return [_mark_from_record(row) for row in rows.all()]


def list_route_candidates(session: Session) -> list[dict]:
    rows = session.query(RouteCandidateRecord).filter(
        RouteCandidateRecord.active.is_(True)
    ).order_by(RouteCandidateRecord.route_name)
    return [_route_candidate_payload(row) for row in rows.all()]


def list_capacity_profiles(session: Session, contract_id: str) -> list[dict]:
    rows = session.query(CapacityProfileRecord).filter(
        CapacityProfileRecord.contract_id == contract_id
    )
    return [
        {
            "capacity_profile_id": row.capacity_profile_id,
            "contract_id": row.contract_id,
            "point_name": row.point_name,
            "direction": row.direction,
            "capacity_mwh_per_day": row.capacity_mwh_per_day,
            "firmness": row.firmness,
            "valid_from_utc": row.valid_from_utc.isoformat(),
            "valid_to_utc": row.valid_to_utc.isoformat(),
            "source_reference": row.source_reference,
        }
        for row in rows.all()
    ]


def _tariff_from_record(row: TsoTariffRecord) -> CapacityTariff:
    return CapacityTariff(
        tariff_id=row.tariff_id,
        document_id=row.document_id,
        country=row.country,
        tso=row.tso,
        market_area=row.market_area,
        gas_year=row.gas_year,
        point_id=row.point_id,
        source_point_name=row.source_point_name,
        direction=TariffDirection(row.direction),
        capacity_product=CapacityProduct(row.capacity_product),
        firmness=Firmness(row.firmness),
        tariff_value=row.tariff_value,
        currency=row.currency,
        unit=row.unit,
        effective_from=row.effective_from.date(),
        effective_to=row.effective_to.date() if row.effective_to else None,
        tariff_status=TariffStatus(row.tariff_status),
        source_table=row.source_table,
        source_page=row.source_page,
        source_refs=row.source_refs,
        manual_review_required=row.manual_review_required,
    )


def _mark_from_record(row: LiveMarketMarkRecord) -> LiveMarketMark:
    return LiveMarketMark(
        venue=row.venue,
        hub=row.hub,
        product=row.product,
        bid_gbp_mwh=row.bid_gbp_mwh,
        ask_gbp_mwh=row.ask_gbp_mwh,
        last_gbp_mwh=row.last_gbp_mwh,
        mark_time_utc=row.mark_time_utc.isoformat(),
        source_system=row.source_system,
    )


def _contract_payload(row: UpstreamResourceContractRecord) -> dict:
    return {
        "contract_id": row.contract_id,
        "contract_name": row.contract_name,
        "resource_type": row.resource_type,
        "delivery_point_name": row.delivery_point_name,
        "gas_year": row.gas_year,
        "delivery_quantity_mwh_per_day": row.delivery_quantity_mwh_per_day,
        "contract_price_gbp_mwh": row.contract_price_gbp_mwh,
        "settlement_frequency": row.settlement_frequency,
        "upstream_payment_lag_days": row.upstream_payment_lag_days,
        "screen_sale_cash_lag_days": row.screen_sale_cash_lag_days,
        "delivery_tolerance_pct": row.delivery_tolerance_pct,
        "nomination_tolerance_pct": row.nomination_tolerance_pct,
        "tolerance_risk_allowance_gbp_mwh": row.tolerance_risk_allowance_gbp_mwh,
        "annual_financing_rate_pct": row.annual_financing_rate_pct,
        "owned_entry_capacity_mwh_per_day": row.owned_entry_capacity_mwh_per_day,
        "owned_exit_capacity_mwh_per_day": row.owned_exit_capacity_mwh_per_day,
        "allowed_exit_points": row.allowed_exit_points,
        "eligible_sale_modes": row.eligible_sale_modes,
        "updated_at_utc": row.updated_at_utc.isoformat(),
    }


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _route_candidate_payload(row: RouteCandidateRecord) -> dict:
    return {
        "route_id": row.route_id,
        "route_name": row.route_name,
        "start_point_name": row.start_point_name,
        "target_point_name": row.target_point_name,
        "business_model": row.business_model,
        "route_legs": row.route_legs,
        "required_entry_point_name": row.required_entry_point_name,
        "required_exit_point_name": row.required_exit_point_name,
        "required_tso_access": row.required_tso_access,
        "source_systems": row.source_systems,
    }
