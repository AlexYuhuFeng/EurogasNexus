"""The public LNG terminal tariff register and the firm's permission per operator (CP-11).

``LngTerminalTermsRecord`` (risk_controls.py) stays the firm's own terms; these rows are what
terminal operators publish, versioned by source document and reviewed four-eyes before they
price anything actionable. Migration 0069.
"""

from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class LngTerminalTariffRecord(Base):
    """One published tariff figure at one terminal, from one source document."""

    __tablename__ = "lng_terminal_tariff"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('CANDIDATE', 'REVIEWED')", name="ck_lng_terminal_tariff_review"
        ),
        Index("ix_lng_terminal_tariff_terminal", "terminal_id", "valid_from"),
        Index("ix_lng_terminal_tariff_source", "source_sha256"),
    )

    tariff_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    terminal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    terminal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The ENTSOG point the terminal sends out through (joins the tariff register and graph).
    entry_point_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: regulated, regulated_indexed, auction, negotiated, exempt.
    regime: Mapped[str] = mapped_column(String(24), nullable=False)
    #: bundled_slot, unloading, storage, sendout, additional_storage, ... reload.
    service: Mapped[str] = mapped_column(String(32), nullable=False)
    #: term, annual, spot, prompt, auction_period.
    product: Mapped[str] = mapped_column(String(24), nullable=False)
    #: per_cargo, per_cargo_class, per_mwh_unloaded, per_mwh_d_sendout, percent_in_kind.
    charge_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    by_cargo_class: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: none, cpi_monthly, annual_update.
    indexation: Mapped[str] = mapped_column(String(24), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slot_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    sendout_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    included_storage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uioli_notice_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: The use-it-or-lose-it rule in at most 25 words where no notice period is stated.
    uioli_rule: Mapped[str | None] = mapped_column(String(256), nullable=True)
    secondary_market: Mapped[str | None] = mapped_column(String(128), nullable=True)
    excludes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document_title: Mapped[str] = mapped_column(String(256), nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LngTerminalOperatorTermsRecord(Base):
    """Whether the firm recorded a terminal operator's permission to reuse its documents."""

    __tablename__ = "lng_terminal_operator_terms"
    __table_args__ = (
        CheckConstraint(
            "permission_state IN ('needs_firm_terms', 'permitted')",
            name="ck_lng_terminal_operator_terms_state",
        ),
    )

    operator: Mapped[str] = mapped_column(String(64), primary_key=True)
    permission_state: Mapped[str] = mapped_column(String(24), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    recorded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recorded_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
