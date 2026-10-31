"""LNG cargoes and regasification slots the firm holds, for the live map and the book."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class LngCargoRecord(Base):
    """One LNG cargo: the firm's own (``book_id`` set) or a market cargo from a vessel feed.

    Positions and tracks come from the customer's licensed vessel-tracking feed (for
    example a Kpler export) or from the ETRM; nothing here is estimated by the product.
    """

    __tablename__ = "lng_cargoes"
    __table_args__ = (Index("ix_lng_cargoes_eta", "eta_utc"),)

    cargo_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    vessel_name: Mapped[str] = mapped_column(String(128), nullable=False)
    vessel_imo: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    load_port: Mapped[str] = mapped_column(String(128), nullable=False)
    load_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    load_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    departed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    destination_terminal: Mapped[str | None] = mapped_column(String(128), nullable=True)
    destination_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    destination_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    eta_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    position_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Past positions, oldest first: [[lon, lat, iso-utc], ...] as the feed reported them.
    track: Mapped[list | None] = mapped_column(JSON, nullable=True)
    volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_gwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RegasSlotRecord(Base):
    """A regasification slot (berthing window and send-out) the firm holds at a terminal."""

    __tablename__ = "regas_slots"
    __table_args__ = (Index("ix_regas_slots_terminal", "terminal_name"),)

    slot_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    terminal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    terminal_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    terminal_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    terminal_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    send_out_gwh_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_gwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    cargo_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
