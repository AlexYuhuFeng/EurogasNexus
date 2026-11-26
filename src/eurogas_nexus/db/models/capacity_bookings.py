"""TAR-2: the capacity the firm holds, so its contracted cost prices what the booking covers.

Migration ``0088_tar2_capacity_bookings`` (ADR Decision 38). One row per booking as the
ETRM, the capacity booking platform's download or the scheduling system states it
(``etrm.capacity_bookings.v1``, ``application/import_contracts.py``): pipeline entry or exit
capacity booked at auction or under a long-term contract, LNG slots bought in an allocation
or at auction, regasification and send-out capacity, storage capacity, and secondary
purchases. ``application/capacity_costs.py`` reads it first, then the public tariff for what
it does not cover (``domain/tariffs/precedence.py``).

A released or cancelled booking keeps its row with ``released_at_utc``, so a valuation as of
an earlier instant still finds what the firm held then. Nothing here books, nominates or
releases capacity; the booking platform and the ETRM stay the books of record.

TAR-2：企业已持有的容量（拍卖、长期合同、分配、二级市场），按其合同成本优先计价。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base

BOOKING_KINDS = ("entry", "exit", "lng_slot", "regas", "send_out", "storage")
ACQUIRED_VIA = ("auction", "long_term", "allocation", "secondary", "fcfs", "bilateral")


class CapacityBookingRecord(Base):
    """One booking of capacity the firm holds."""

    __tablename__ = "capacity_bookings"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('entry', 'exit', 'lng_slot', 'regas', 'send_out', 'storage')",
            name="ck_capacity_bookings_kind",
        ),
        CheckConstraint(
            "quantity_basis IN ('per_day', 'pool')", name="ck_capacity_bookings_basis"
        ),
        Index("ix_capacity_bookings_facility", "facility_id", "kind"),
        Index("ix_capacity_bookings_book", "book_id"),
    )

    #: ``<SYSTEM>:<the system's booking id>``.
    booking_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: ``None``: held at firm level (visible to head office only under book isolation).
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: ``point`` (entry/exit), ``terminal`` (slot, regas, send-out) or ``storage``.
    facility_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The point key (as ENTSOG and the tariff register name it), terminal id or storage id.
    facility_id: Mapped[str] = mapped_column(String(128), nullable=False)
    facility_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: ``ENTRY`` or ``EXIT`` for a point; ``None`` otherwise.
    direction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    #: The capacity product booked (``ANNUAL`` ... ``WITHIN_DAY``, ``slot``, ``bundled``).
    product: Mapped[str | None] = mapped_column(String(32), nullable=True)
    firmness: Mapped[str] = mapped_column(String(16), nullable=False)
    acquired_via: Mapped[str] = mapped_column(String(16), nullable=False)
    first_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    last_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    #: ``MWh/d``, ``kWh/h``, ``kWh/d``, ``MWh`` (storage space, send-out energy) or ``slot``.
    quantity_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    #: ``per_day`` (capacity each gas day) or ``pool`` (a number of slots over the period).
    quantity_basis: Mapped[str] = mapped_column(String(12), nullable=False)
    #: The contracted price as the contract states it; ``None``: not recorded (never zero).
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: A tariff unit (``EUR/(kWh/h)/y``, ``p/kWh/d``, ``EUR/MWh``) or ``<CCY>/slot``.
    price_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
