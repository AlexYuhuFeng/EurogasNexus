"""Power-system observations (ENTSO-E Transparency): prices, load and generation by fuel."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class PowerObservationRecord(Base):
    """One value of one metric for one bidding zone and delivery period.

    ``published_at_utc`` is the source document's creation time: the earliest moment the
    value can have been known, which point-in-time datasets use as availability.
    """

    __tablename__ = "power_observations"
    __table_args__ = (
        Index(
            "ix_power_observations_zone_metric_period",
            "zone",
            "metric",
            text("period_start_utc DESC"),
        ),
    )

    observation_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    zone: Mapped[str] = mapped_column(String(32), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    process_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    published_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
