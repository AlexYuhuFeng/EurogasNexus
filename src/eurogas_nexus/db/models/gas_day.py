"""The firm's physical schedule per gas day and who clears what (Today → My gas day).

- ``gas_day_schedule_lines``: what the firm's scheduling system (or the ETRM's physical
  schedule) holds for one gas day at one hub that no contract or trade row carries: storage
  injection and withdrawal, customer offtake, exports and imports on held capacity. Imported
  like the trades are, one row per line, quantities in MWh for the day, never typed on Today.
- ``gas_day_delegations``: part or all of a book's lines at a hub handed to one trader for a
  span of gas days (a delegated split, a cover, "assign for today"). A delegation records who is
  responsible; it never widens what that trader's mandate allows, and it is checked against
  the mandate when it is written.

Nothing here nominates or trades (AGENTS.md rule 8).
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class GasDayScheduleLineRecord(Base):
    """One scheduled physical line of one gas day at one hub (IN or OUT of the hub)."""

    __tablename__ = "gas_day_schedule_lines"
    __table_args__ = (Index("ix_gas_day_schedule_day_hub", "gas_day", "hub"),)

    line_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: ``in``: gas the firm takes at the hub; ``out``: gas it delivers there.
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    #: storage_withdrawal, storage_injection, customer_offtake, export, import, supply, sale.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The facility, customer, point or capacity the line runs through, as the desk names it.
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    point: Mapped[str | None] = mapped_column(String(160), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contract_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GasDayDelegationRecord(Base):
    """Part or all of a book's position at a hub, handed to one trader for some gas days."""

    __tablename__ = "gas_day_delegations"
    __table_args__ = (Index("ix_gas_day_delegations_span", "gas_day_from", "gas_day_to"),)

    delegation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gas_day_from: Mapped[date] = mapped_column(Date, nullable=False)
    gas_day_to: Mapped[date] = mapped_column(Date, nullable=False)
    #: Until when within the last day it holds (a shift); NULL for the whole gas day.
    until_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The line it hands over (``contract:<id>``, ``schedule:<id>``, ``lng:<slot>``,
    #: ``trade:<id>``), or NULL for the book's whole position at the hub.
    line_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: The part of the line handed over, MWh per gas day; NULL for all of it.
    mwh_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: The receiving trader as the mandate names them, and that mandate.
    trader: Mapped[str] = mapped_column(String(128), nullable=False)
    mandate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assigned_by: Mapped[str] = mapped_column(String(128), nullable=False)
    assigned_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    revoked_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)


class GasDayNominationEventRecord(Base):
    """One recorded status of one nomination step of one gas day (append-only).

    The scheduling import writes what the TSO or the nominations agent confirmed; a person
    may record a status by hand, which is labelled and audited. The current status of a step
    is its newest row. Recording a status sends nothing: nominations are made elsewhere.
    """

    __tablename__ = "gas_day_nomination_events"
    __table_args__ = (Index("ix_gas_day_nomination_events_day_ref", "gas_day", "line_ref"),)

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    #: The line the step belongs to: ``contract:<id>``, ``schedule:<id>``, ``lng:<slot>``.
    line_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: nomination, renomination, lng_unloading, lng_send_out, lng_inventory.
    step: Mapped[str] = mapped_column(String(32), nullable=False)
    #: to_send, sent, confirmed, renominated, mismatch_queried, done.
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: ``import``: the scheduling system or agent confirmation; ``manual``: entered by hand.
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
