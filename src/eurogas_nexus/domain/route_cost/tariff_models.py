"""Tariff-source models for route-cost research.

运费率来源（tariff source）的 Pydantic 数据契约：文档、点位、容量费率
三层结构，全部携带 ``source_refs`` 溯源与 ``manual_review_required``
人工复核标记；任何一层缺溯源都不得进入可执行路径。
"""

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
    """One published tariff source document (charging statement etc.).

    Attributes:
        document_id: Stable document identifier.
        country: Country code (e.g. ``GB``, ``NL``).
        tso: TSO publishing the document.
        market_area: Market area the document applies to.
        source_url: Public source URL.
        document_title: Title as published.
        published_date: Publication date.
        effective_from: First effective day.
        effective_to: Last effective day; None when still effective.
        gas_years_covered: Gas years covered (e.g. ``["2025/26"]``).
        status: FINAL / INDICATIVE / PROVISIONAL / DRAFT / SIMULATOR_ONLY.
        retrieved_at: When the document was retrieved, or None.
        checksum: Content checksum for change detection, or None.
        parser_status: Parsing status tag.
        manual_review_required: True when human review is mandatory.
        source_refs: Provenance references.
    """

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
    """One tariff point (physical or virtual) with canonical mapping.

    Attributes:
        point_id: Stable point identifier.
        source_point_name: Name as published by the source.
        canonical_point_id: Canonical ontology point id, or None when the
            mapping is not yet established.
        country: Country code.
        tso: Operating TSO.
        market_area: Market area.
        point_type: Physical or virtual point type.
        hub_binding: Hub code when the point binds to a hub, or None.
        is_virtual: True for virtual points.
        is_physical: True for physical points.
        source_refs: Provenance references.
        manual_review_required: True when human review is mandatory.
    """

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
    """One capacity tariff row extracted from a source document.

    Attributes:
        tariff_id: Stable tariff identifier.
        document_id: Owning source document.
        country: Country code.
        tso: Operating TSO.
        market_area: Market area.
        gas_year: Gas year (e.g. ``2025/26``).
        point_id: Tariff point reference.
        source_point_name: Point name as published.
        direction: Entry / exit / storage direction.
        capacity_product: Capacity product (daily, monthly, yearly...).
        firmness: Firm / interruptible.
        tariff_value: Tariff amount.
        currency: ISO 4217 currency code.
        unit: Tariff unit (e.g. ``GBP/MWh/d``).
        effective_from: First effective day.
        effective_to: Last effective day; None when still effective.
        tariff_status: FINAL / INDICATIVE / PROVISIONAL / DRAFT.
        source_table: Table within the source document.
        source_page: Page number, or None.
        source_refs: Provenance references.
        manual_review_required: True when human review is mandatory.
    """

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
