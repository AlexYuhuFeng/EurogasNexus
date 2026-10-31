"""Credit lines, trader mandates, daily contract deliveries and LNG terminal terms.

Firm-maintained reference data that turns positions into controls: how much the firm may
owe or be owed by each counterparty, what each trader may hold, how each bilateral supply
contract actually delivered against its nominations, and what each regas terminal costs.
"""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class CreditLineRecord(Base):
    """An approved credit limit for one counterparty (risk / credit function)."""

    __tablename__ = "credit_lines"

    counterparty_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Other spellings of the name as the ETRM extract carries them.
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    legal_entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    limit_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    #: Letters of credit, parent guarantees and cash collateral held against the exposure.
    collateral_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Upstream supply contracts facing this counterparty.
    contract_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    #: Days of deliveries at risk before payment (delivery month plus payment terms).
    receivable_days: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TraderMandateRecord(Base):
    """What one trader may hold: books, hubs, net size per month and tenor."""

    __tablename__ = "trader_mandates"

    mandate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: The trader's sign-in principal or the account label their trades carry.
    trader: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    book_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    hubs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    max_net_mwh_per_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tenor_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    physical_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    financial_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Hedge policy per hub-month: financial cover as a share of the physical position.
    min_hedge_ratio_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_hedge_ratio_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Instruments allowed (future, forward, swap, option); empty or NULL means any.
    instruments: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ContractDeliveryRecord(Base):
    """One gas day of a bilateral supply contract: nominated and allocated quantity."""

    __tablename__ = "contract_daily_deliveries"

    contract_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    gas_day: Mapped[date] = mapped_column(Date, primary_key=True)
    nominated_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    allocated_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: The TSO or system the shipper is registered with for this point (e.g. Gassco, GTS).
    tso: Mapped[str | None] = mapped_column(String(64), nullable=True)
    point: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LngTerminalTermsRecord(Base):
    """The firm's cost to land a cargo at one regas terminal, in the hub's currency."""

    __tablename__ = "lng_terminal_terms"

    terminal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    regas_tariff_per_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    entry_tariff_per_mwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Gas retained by the terminal for fuel and losses, percent of the cargo.
    fuel_retention_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    port_costs_per_cargo: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    other_per_mwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Extra sailing days versus the firm's reference terminal, for boil-off and charter.
    extra_sailing_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_note: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
