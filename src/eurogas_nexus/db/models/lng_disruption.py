"""LNG-3: what a disruption re-optimisation needs beyond the cargo and its slot, and its record.

Migration ``0086_lng_disruption`` (ADR Decision 36). The engine is
``domain/lng/disruption.py``; the reads and the one write are
``application/lng_disruption.py``.

* ``lng_slot_terms``: a held regas slot's product terms (slot length in gas days, storage
  right and its profile, what releasing it would fetch). Without a row the slot is read from
  ``regas_slots`` with a declining storage right equal to the slot's energy, named as such.
* ``lng_capacity_offers``: terminal capacity the desk could borrow in tank or buy (extra
  send-out, extra storage, interruptible), as quoted by a counterparty or the terminal, or
  as an indicative figure the desk entered.
* ``lng_delivery_obligations``: gas the book must deliver at a terminal or point each gas day
  of a window; a firm one is a hard constraint.
* ``lng_voyage_terms``: per cargo or charter, laytime, demurrage, boil-off and whether the
  cargo may be diverted (otherwise the cargo contract's master agreement and the firm's
  boil-off assumption are used, and named).
* ``pipeline_supplies``: pipeline supply contracts of the book and the days curtailed.
* ``lng_disruption_runs``: every re-optimisation run, the timeline of the recommendation.
* ``lng_disruption_decisions``: the option a person chose (a record only: nothing is booked).

LNG-4 (migration ``0087_lng4_options_demurrage``, ADR Decision 37) adds optional
columns (demurrage in its contract currency and terms, an obligation's breach terms, a pipeline
supply's asset dependencies and outage mode, the recommended set on a run and a decision, the
hub a spot slot offer reaches, the berth days a call holds under a slot's terms) and two
tables:

* ``pipeline_outage_links``: a held REMIT message linked to a pipeline supply that depends on
  its asset: what matched, why, the gas days and MWh it curtails, and whether it still applies.
* ``lng_berth_calls``: other users' ships due at a terminal's berth (the line-up, where the
  firm holds it), so an option that takes the berth carries the knock-on it causes.

Migration ``0090_lng_berth_rules`` (ADR Decision 37, addendum of 2026-11-26, the owner's berth
priority and third-party demurrage decisions) adds:

* ``lng_terminal_berth_rules``: a terminal's berth access rule where the firm records one (the
  arrival window, where a late ship's laytime starts, whether a swap of berth turn needs the
  terminal's approval), with its citation and basis (``terminal_code``, ``example`` or
  ``assumption``); without a row the engine's default rule applies and says so;
* on ``lng_berth_calls``: the company whose ship it is and its negotiated quote to give up its
  berth turn (amount, currency, reference), one total. The call's own laytime, demurrage and
  boil-off columns stay but are no longer read: another company's demurrage is never counted
  in the book's P&L.

Every figure here is the firm's own entry or import; nothing is a terminal's tariff copied
into the product.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class LngSlotTermsRecord(Base):
    __tablename__ = "lng_slot_terms"

    slot_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    #: Gas days of send-out the slot gives from its first gas day.
    slot_days: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    #: ``linear_decline`` (the storage right falls to zero over the slot) or ``flat``.
    storage_profile: Mapped[str] = mapped_column(String(24), nullable=False)
    #: What the secondary market would pay per MWh of send-out right if released (indicative).
    release_value_eur_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: LNG-4: gas days a call holds the terminal's berth under these terms (berthing,
    #: unloading, sailing); ``None``: one gas day (desk standard).
    berth_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LngCapacityOfferRecord(Base):
    __tablename__ = "lng_capacity_offers"
    __table_args__ = (Index("ix_lng_capacity_offers_terminal", "terminal_name", "kind"),)

    offer_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    #: ``None``: open to every book.
    book_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    terminal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    #: ``borrow``, ``send_out``, ``storage`` or ``interruptible``.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    first_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    last_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    price_eur_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    max_mwh_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_price_eur_mwh_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: LNG-4: the hub a ``slot`` (spot slot) offer's gas reaches.
    hub: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: ``quoted`` (a counterparty or the terminal named a price), ``tariff`` or ``indicative``.
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    counterparty: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    valid_until_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LngDeliveryObligationRecord(Base):
    __tablename__ = "lng_delivery_obligations"
    __table_args__ = (Index("ix_lng_delivery_obligations_book", "book_id"),)

    obligation_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    #: A terminal name (LNG send-out there counts) or a hub code (any supply at it counts).
    point: Mapped[str] = mapped_column(String(128), nullable=False)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    first_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    last_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    firm: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: Non-firm: the cost per MWh short. Firm: the contract's liquidated damages per MWh
    #: short where held (``None``: not held; a breach is then stated, not valued).
    penalty_eur_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: LNG-4: the breach terms as the contract states them (a cap, a cure period).
    penalty_terms: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LngVoyageTermsRecord(Base):
    __tablename__ = "lng_voyage_terms"

    cargo_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    charter_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    laytime_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    demurrage_eur_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: LNG-4: the demurrage rate per day in the currency the contract names (it wins over
    #: ``demurrage_eur_per_day``), and the laytime and demurrage terms as written.
    demurrage_rate_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    demurrage_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    demurrage_terms: Mapped[str | None] = mapped_column(String(256), nullable=True)
    boil_off_pct_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: ``None``: the contract says nothing the desk recorded; a DES cargo is then not diverted.
    diversion_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    diversion_note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PipelineSupplyRecord(Base):
    __tablename__ = "pipeline_supplies"
    __table_args__ = (Index("ix_pipeline_supplies_book", "book_id"),)

    supply_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    hub: Mapped[str] = mapped_column(String(16), nullable=False)
    point: Mapped[str] = mapped_column(String(128), nullable=False)
    first_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    last_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    mwh_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    cost_eur_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Days curtailed as entered by hand: [[gas day ISO, MWh not delivered], ...]. A day
    #: named here wins over a REMIT outage linked to the supply (the manual override).
    curtailed: Mapped[list] = mapped_column(JSON, nullable=False)
    #: LNG-4: the assets the supply flows through, each one of ``{"asset_eic": ...}``,
    #: ``{"asset_name": ...}`` or ``{"gie_facility_eic": ...}``, with an optional ``kind``
    #: (entry point, interconnector, field, facility), ``direction``, ``share_pct`` of the
    #: supply that flows through it, and ``capacity_mwh_d`` when a message gives no technical
    #: capacity. ``None``: no REMIT outage is linked.
    depends_on: Mapped[list | None] = mapped_column(JSON, nullable=True)
    #: ``auto`` (``None``): linked REMIT outages curtail the supply; ``manual``: only the
    #: days entered by hand do (the links are still recorded).
    outage_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LngDisruptionRunRecord(Base):
    """One re-optimisation of a book: the timeline of the recommendation."""

    __tablename__ = "lng_disruption_runs"
    __table_args__ = (Index("ix_lng_disruption_runs_book", "book_id", "computed_at_utc"),)

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: What started it: ``event:<event_id>`` or ``read``.
    trigger: Mapped[str] = mapped_column(String(160), nullable=False)
    #: The disrupted supplies, the recommended option and the frontier (option ids and keys).
    digest: Mapped[str] = mapped_column(String(40), nullable=False)
    disrupted: Mapped[list] = mapped_column(JSON, nullable=False)
    recommended_option_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recommended_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_pnl_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    frontier: Mapped[list] = mapped_column(JSON, nullable=False)
    #: Each option's key, feasibility and objectives, so the timeline is readable later.
    options: Mapped[list] = mapped_column(JSON, nullable=False)
    #: ``recommendation``, ``frontier``, ``pnl`` or ``None`` (no material change).
    change: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: LNG-4: the recommended set, ``[{"basis", "option_id", "key", "title", "reason"}]``
    #: (``None`` on an LNG-3 run, which had one default in ``recommended_*``).
    recommended_set: Mapped[list | None] = mapped_column(JSON, nullable=True)


class LngDisruptionDecisionRecord(Base):
    """The option a person chose for a disruption. A record: nothing is booked or sent."""

    __tablename__ = "lng_disruption_decisions"
    __table_args__ = (Index("ix_lng_disruption_decisions_cargo", "cargo_id", "decided_at_utc"),)

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cargo_id: Mapped[str] = mapped_column(String(96), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    option_id: Mapped[str] = mapped_column(String(32), nullable=False)
    option_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_option_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    objectives: Mapped[dict] = mapped_column(JSON, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: LNG-4: the recommended set when the choice was made, the chosen option's flags,
    #: breaches and the supplies it moves, and the FX choice its figures were valued at.
    recommended_set: Mapped[list | None] = mapped_column(JSON, nullable=True)
    consequences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fx: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PipelineOutageLinkRecord(Base):
    """A held REMIT message linked to a pipeline supply that depends on its asset (LNG-4).

    One row per supply and message; a new version of the message revises the row, and a
    withdrawn or ended message keeps the row with ``status`` saying so and no curtailment.
    Advisory: the curtailment it carries is the platform's reading of the message.
    """

    __tablename__ = "pipeline_outage_links"
    __table_args__ = (
        Index("ux_pipeline_outage_links_supply_message", "supply_id", "message_id", unique=True),
        Index("ix_pipeline_outage_links_book", "book_id"),
    )

    link_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    supply_id: Mapped[str] = mapped_column(String(96), nullable=False)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The message version the row reflects, and its status as published.
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_status: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(160), nullable=False)
    asset_eic: Mapped[str] = mapped_column(String(32), nullable=False)
    #: ``asset_eic``, ``asset_name`` or ``gie_facility_eic`` (through the reviewed aliases).
    matched_on: Mapped[str] = mapped_column(String(24), nullable=False)
    #: The supply's dependency entry that matched.
    dependency: Mapped[dict] = mapped_column(JSON, nullable=False)
    #: Why, in a sentence: the match and how the volume was derived.
    why: Mapped[str] = mapped_column(Text, nullable=False)
    #: Share of the asset's capacity that is unavailable (0..1); ``None``: not derivable.
    fraction: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: [[gas day ISO, MWh not delivered], ...] while the link applies.
    curtailed: Mapped[list] = mapped_column(JSON, nullable=False)
    #: ``applied``, ``unsized`` (matched, volume not derivable), ``withdrawn`` (dismissed)
    #: or ``ended`` (inactive).
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_linked_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LngBerthCallRecord(Base):
    """Another company's ship due at a terminal's berth (LNG-4), from the terminal's line-up
    as the firm holds it. It is an on-time slot holder: a late cargo of the book never
    displaces it. Its laytime, demurrage and boil-off (LNG-4 columns) are kept as recorded but
    not read since 2026-11-26: an option that takes its berth turn is a negotiated swap, costed
    at the company's quote (``quote_amount`` in ``quote_currency``, converted with the reader's
    FX choice), or pending when no quote is entered."""

    __tablename__ = "lng_berth_calls"
    __table_args__ = (Index("ix_lng_berth_calls_terminal", "terminal_name", "berth_gas_day"),)

    call_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    terminal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    berth_gas_day: Mapped[date] = mapped_column(Date, nullable=False)
    berth_days: Mapped[int] = mapped_column(Integer, nullable=False)
    laytime_left_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    demurrage_rate_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    demurrage_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    boil_off_mwh_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: 0090: the company whose ship it is, the party a swap of berth turn is negotiated with.
    counterparty: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: 0090: its quote to give up its berth turn, one total (its demurrage and margin
    #: together); ``None``: no quote entered, the swap's cost is pending.
    quote_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    quote_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)


class LngTerminalBerthRuleRecord(Base):
    """A terminal's berth access rule as the firm records it (0090). Without a row the engine's
    default applies: a ship within its arrival window (one gas day from its slot's first gas
    day) is berthed in turn, a late ship takes the next free gap without displacing on-time
    slot holders and its laytime starts at berthing, and a swap of berth turn needs the
    terminal's approval. ``basis`` says where a row comes from: ``terminal_code`` (the
    terminal's access code, cited), ``example`` (illustrative, never a terminal's published
    rule) or ``assumption`` (the desk's)."""

    __tablename__ = "lng_terminal_berth_rules"

    terminal_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    #: Gas days from a slot's first gas day within which an arriving ship is on time.
    arrival_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: ``berthing`` or ``arrival``: where a late ship's laytime starts.
    late_laytime_from: Mapped[str] = mapped_column(String(16), nullable=False)
    swap_needs_terminal_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The clause or document the rule is read from.
    citation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    #: The rule as the code words it, where held.
    rule_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
