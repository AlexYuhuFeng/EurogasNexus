"""Generalized cost-observation persistence model.

Cost observations represent time-varying commercial values for routes, entry/
exit points, LNG regas slots, or other scoped facilities. Each row is a
source-attributed observation with an effective window; the resolver chooses
the applicable observation by entitlement priority at query time.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class CostObservationRecord(Base):
    """One time-windowed cost observation.

    ``observation_type`` describes the source semantics
    (``TSO_PUBLISHED``, ``LONG_TERM_CONTRACT``, ``SECONDARY_TRANSFER``,
    ``AUCTION_BID``, ``LNG_SLOT_BOOKING``, ``MANUAL_OVERRIDE``).

    ``scope_type`` / ``scope_id`` identify the physical or commercial object:
    ``ROUTE``, ``POINT``, ``LNG_TERMINAL``, or ``RESOURCE``.
    """

    __tablename__ = "cost_observations"

    observation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    capacity_product: Mapped[str | None] = mapped_column(String(32), nullable=True)
    firmness: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gas_year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    effective_from_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    effective_to_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entitlement_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    superseded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
