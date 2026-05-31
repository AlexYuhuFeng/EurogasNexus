"""Tariff-source models for route-cost research."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    PointType,
    TariffDirection,
    TariffStatus,
)


class TariffSourceDocument(BaseModel):
    document_id: str
    country: str
    tso: str
    market_area: str
    source_url: str
    document_title: str
    published_date: date
    effective_from: date
    effective_to: date | None = None
    gas_years_covered: list[str] = Field(default_factory=list)
    status: TariffStatus
    retrieved_at: datetime | None = None
    checksum: str | None = None
    parser_status: str
    manual_review_required: bool = True
    source_refs: list[str] = Field(default_factory=list)


class TariffPoint(BaseModel):
    point_id: str
    source_point_name: str
    canonical_point_id: str | None = None
    country: str
    tso: str
    market_area: str
    point_type: PointType
    hub_binding: str | None = None
    is_virtual: bool = False
    is_physical: bool = True
    source_refs: list[str] = Field(default_factory=list)
    manual_review_required: bool = True


class CapacityTariff(BaseModel):
    tariff_id: str
    document_id: str
    country: str
    tso: str
    market_area: str
    gas_year: str
    point_id: str
    source_point_name: str
    direction: TariffDirection
    capacity_product: CapacityProduct
    firmness: Firmness
    tariff_value: float
    currency: str
    unit: str
    effective_from: date
    effective_to: date | None = None
    tariff_status: TariffStatus
    source_table: str
    source_page: int | None = None
    source_refs: list[str] = Field(default_factory=list)
    manual_review_required: bool = True

