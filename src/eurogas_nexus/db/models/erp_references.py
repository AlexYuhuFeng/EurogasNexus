"""ERP reference rows: counterparties and invoices as the firm's ERP holds them (DATA-1).

The ERP (SAP and the like) is the book of record for who the firm's counterparties are in
finance and what has been invoiced. Eurogas Nexus keeps a reference copy, imported through the
``erp.counterparties.v1`` and ``erp.invoices.v1`` contracts (``application/import_contracts``),
so a trade, a credit line or a cargo can be reconciled to the ERP's own identifiers. It is a
reference, never a ledger: nothing here posts, pays, settles or changes the ERP.

One row per (system, kind, external id). ``fields`` holds the contract's other columns as
imported; ``content_hash`` is their digest, so a re-import of the same row changes nothing.
Bank accounts and tax identifiers are not part of either contract, and a file that carries
them is refused.

ERP 参考数据：从 ERP 导入的交易对手与发票引用，仅用于对账，不记账、不付款。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class ErpReferenceRecord(Base):
    """One counterparty or invoice reference from one ERP."""

    __tablename__ = "erp_references"
    __table_args__ = (
        Index("ix_erp_references_system_kind", "system", "kind"),
        Index("ix_erp_references_counterparty", "counterparty_id"),
    )

    #: ``<system>:<kind>:<external_id>``.
    reference_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    system: Mapped[str] = mapped_column(String(32), nullable=False)
    #: ``counterparty`` or ``invoice``.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The ERP's own key (a business partner or customer/vendor number, an invoice number).
    external_id: Mapped[str] = mapped_column(String(96), nullable=False)
    #: The counterparty as this platform names it (``credit_lines.counterparty_id``), if mapped.
    counterparty_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: An invoice's counterparty as the ERP names it (its ``external_id``).
    counterparty_external_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    #: The trade, contract or cargo an invoice refers to, as the ETRM or ERP names it.
    trade_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    first_imported_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_changed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
