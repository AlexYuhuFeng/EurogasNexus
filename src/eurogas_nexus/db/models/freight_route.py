"""LNG voyage distances, versioned (CP-12, design C.5 ``freight_route``). Migration 0070.

A distance is a fact about a routing (load port to discharge port, direct, via Suez or Panama,
or round the Cape); the firm enters it, naming where it came from. A change adds a version;
nothing is overwritten, so a cargo evaluation names the version it used.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class FreightRouteRecord(Base):
    """One version of one route's distance."""

    __tablename__ = "freight_route"
    __table_args__ = (
        UniqueConstraint("route_id", "version", name="uq_freight_route_version"),
        CheckConstraint(
            "routing IN ('direct', 'suez', 'panama', 'cape')", name="ck_freight_route_routing"
        ),
        CheckConstraint("distance_nm > 0", name="ck_freight_route_distance"),
        Index("ix_freight_route_route", "route_id"),
    )

    row_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    load_port: Mapped[str] = mapped_column(String(96), nullable=False)
    discharge_port: Mapped[str] = mapped_column(String(96), nullable=False)
    #: The terminal the route discharges at, where it is one (joins the tariff register).
    discharge_terminal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    routing: Mapped[str] = mapped_column(String(16), nullable=False)
    distance_nm: Mapped[float] = mapped_column(Float, nullable=False)
    #: none, suez, panama: a canal routing needs a toll entered with the cargo.
    canal: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    #: Where the distance came from ("measured on a nautical chart", a vendor table, ...).
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The approved proposal that set this row (P-17); ``None`` when set without a second person.
    change_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
