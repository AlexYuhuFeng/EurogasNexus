"""The valuation snapshot reader over the runtime store (commercial design basis 2, J.1).

:func:`open_valuation_snapshot` is the one function every evaluator's inputs come through.
For an evaluation instant it reads, on request and once per key:

- **prices**: an executable quote side (class ``sourced``), else a settlement or assessment
  (``indicative``: real but not executable), else the firm's own mark (``firm_mark``); on a
  demo desk only, a demo price (``simulated``). A real input always wins over a simulated
  one, and on a real desk simulated rows are never read at all;
- **FX** through an adapter: :class:`ForwardFx` (design D.5: licensed forward ``sourced``,
  covered interest parity ``derived`` with its tolerance, spot for a prompt period); the
  spot-only :class:`SpotEcbFx` labels a forward period converted at spot ``indicative``;
- **rates** (the currency's overnight benchmark), **tariffs** (published FINAL ``sourced``,
  INDICATIVE ``indicative``, demo rows ``simulated`` on a demo desk only), **capacity**,
  **outages** (REMIT), the firm's **approved assumption set** in force (``assumption``) and
  the **book** (approved hedge bands and the cover held).

Everything read is recorded with class, source family, reference and as-of; the manifest is
persisted by :func:`freeze_snapshot` and a :class:`~eurogas_nexus.domain.valuation.snapshot.
ReplayReader` built by :func:`replay_snapshot` reproduces the evaluation's figures exactly.
Rows the caller is not entitled to are never read (fail closed on the source family).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

from eurogas_nexus.application.caller import Caller
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import (
    FX_METHOD_FORWARD,
    FX_METHOD_SPOT,
    InputKind,
    RecordingReader,
    ReplayReader,
    SnapshotInput,
    SnapshotManifest,
    missing,
)

#: Decimal places every stored input is held to, so a replay reads the exact same figure.
_PLACES = Decimal("1E-10")

#: The family recorded for the customer's own entries (marks, book): public baseline, so
#: entitlement never hides them; book scope governs who sees an opportunity built on them.
FIRM_FAMILY = "operator-input"
#: Demo rows on a demo desk.
DEMO_FAMILY = "DEMO"

_TARIFF_RANK = {"FINAL": 0, "INDICATIVE": 1, "PROVISIONAL": 2, "DRAFT": 3, "SIMULATOR_ONLY": 4}


def _dec(value: float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(_PLACES)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


def _is_simulated(source_system: str | None, metadata: dict | None) -> bool:
    return bool((metadata or {}).get("simulated")) or str(source_system or "").endswith("_Sim")


# ----------------------------------------------------------------------------- FX adapter


@dataclass(frozen=True)
class FxAnswer:
    """One conversion rate with how it was obtained."""

    rate: Decimal
    input_class: InputClass
    method: str
    as_of_utc: datetime
    value_date: str
    source_family: str
    source_ref: str
    note: str
    tolerance: Decimal | None = None


class FxSource(Protocol):
    """Units of ``quote`` per one ``base`` for cash flows of a delivery period.

    The forward-FX service (design D.5, ``GET /api/market/fx-forward``: pair and value date
    to rate, method, inputs and tolerance) plugs in here when it lands; until then the spot
    adapter answers, labelled so nothing reads as a forward.
    """

    def __call__(
        self, session: Any, base: str, quote: str, period: DeliveryPeriod, as_of_utc: datetime
    ) -> FxAnswer | None: ...


class SpotEcbFx:
    """ECB euro reference rates, crossed through EUR; demo rates only on a demo desk.

    Spot is the right rate for a day-ahead or within-day cash flow (design D.5 step 3), so
    those conversions are ``sourced``. For a forward period, spot ignores the interest
    differential, so the conversion is ``indicative`` and labelled "FX: spot".
    """

    method = FX_METHOD_SPOT

    def __init__(self, *, demo_desk: bool) -> None:
        self.demo_desk = demo_desk

    def _leg(self, session, currency: str, as_of_utc: datetime):
        from eurogas_nexus.db.models import FxObservationRecord

        if currency == "EUR":
            return None
        sources = ("ECB", "DEMO_Sim") if self.demo_desk else ("ECB",)
        rows = (
            session.query(FxObservationRecord)
            .filter(FxObservationRecord.base_currency == "EUR")
            .filter(FxObservationRecord.quote_currency == currency)
            .filter(FxObservationRecord.source_system.in_(sources))
            .filter(FxObservationRecord.value_date <= as_of_utc.date().isoformat())
            .all()
        )
        if not rows:
            return False
        # A real ECB fixing always wins over a demo rate; then the latest value date.
        return max(rows, key=lambda row: (row.source_system == "ECB", row.value_date))

    def __call__(self, session, base, quote, period, as_of_utc) -> FxAnswer | None:
        legs = [self._leg(session, code, as_of_utc) for code in (base, quote)]
        if any(leg is False for leg in legs):
            return None
        rate = Decimal(1)
        base_leg, quote_leg = legs
        if base_leg is not None:
            rate /= Decimal(str(base_leg.rate))
        if quote_leg is not None:
            rate *= Decimal(str(quote_leg.rate))
        used = [leg for leg in legs if leg is not None]
        simulated = any(leg.source_system != "ECB" for leg in used)
        value_date = min((leg.value_date for leg in used), default=as_of_utc.date().isoformat())
        observed = max((_aware(leg.observed_at_utc) for leg in used), default=as_of_utc)
        spot_is_right = period.kind == "day"
        if simulated:
            klass = InputClass.SIMULATED
        elif spot_is_right:
            klass = InputClass.SOURCED
        else:
            klass = InputClass.INDICATIVE
        note = f"FX: spot (ECB reference rate of {value_date})"
        if not spot_is_right:
            note += "; forward FX not applied to this delivery period"
        return FxAnswer(
            rate=rate.quantize(_PLACES),
            input_class=klass,
            method=self.method,
            as_of_utc=observed,
            value_date=value_date,
            source_family=DEMO_FAMILY if simulated else "ECB",
            source_ref=",".join(leg.observation_id for leg in used) or "identity",
            note=note,
        )


class ForwardFx:
    """Forward FX for the delivery period (design D.5, ``domain/market/fx_forward.py``).

    The rate a cash flow of the period could be hedged at today: a licensed outright forward
    held through the customer's entitlement (``sourced``), else covered interest parity from
    the ECB reference rate and the overnight benchmarks (``derived``, with its tolerance), or
    the spot reference rate for a prompt period or one whose value date has passed
    (``sourced``). Demo rows are read only on a demo desk and make the rate ``simulated``.
    A refusal (no rate, no benchmark, beyond 24 months without licensed forwards) is missing.
    """

    method = FX_METHOD_FORWARD

    def __init__(self, *, demo_desk: bool, caller: Caller) -> None:
        self.demo_desk = demo_desk
        self.caller = caller
        self._holdings = None

    def _load(self, session):
        from eurogas_nexus.application.market_normalisation import _interest_rate_rows
        from eurogas_nexus.application.projections.market_reads import (
            filter_entitled_rows,
            fx_observations,
        )
        from eurogas_nexus.domain.market.fx_forward import FxHoldings, is_simulated_source

        def keep(rows):
            rows = filter_entitled_rows(self.caller.principal, rows, source_key="source_system")
            if self.demo_desk:
                return rows
            return [row for row in rows if not is_simulated_source(row.get("source_system"))]

        return FxHoldings.from_rows(
            keep(fx_observations(session)), keep(_interest_rate_rows(session))
        )

    def __call__(self, session, base, quote, period, as_of_utc) -> FxAnswer | None:
        from eurogas_nexus.domain.market.fx_forward import (
            METHOD_LICENSED,
            Delivery,
            FxForwardError,
            conversion_rate,
        )

        if self._holdings is None:
            self._holdings = self._load(session)
        kind = {"day": "day_ahead"}.get(period.kind, period.kind)
        delivery = Delivery(period.start, period.end - timedelta(days=1), kind, period.label)
        try:
            found = conversion_rate(
                self._holdings, base, quote, as_of=as_of_utc.date(), delivery=delivery
            )
        except FxForwardError:
            # No forward can be derived (no overnight benchmark held, or beyond the horizon):
            # the spot reference rate still converts the figure, as "indicative, FX: spot" for
            # a forward period. Only no rate at all leaves the conversion missing.
            return SpotEcbFx(demo_desk=self.demo_desk)(session, base, quote, period, as_of_utc)
        klass = {
            "simulated": InputClass.SIMULATED,
            "derived": InputClass.DERIVED,
        }.get(found.input_class, InputClass.SOURCED)
        if found.simulated:
            family = DEMO_FAMILY
        elif found.method == METHOD_LICENSED and found.licensed is not None:
            family = found.licensed.source_system
        else:
            family = "ECB"
        refs = []
        if found.spot is not None:
            refs.append(f"spot {found.spot.value_date.isoformat()}")
        refs += [
            f"{item.benchmark.benchmark_id} {item.fixing_date.isoformat()}" for item in found.rates
        ]
        value_date = (found.value_date or as_of_utc.date()).isoformat()
        return FxAnswer(
            rate=Decimal(str(found.rate)).quantize(_PLACES),
            input_class=klass,
            method=found.method,
            as_of_utc=datetime.combine(
                found.spot.value_date if found.spot else as_of_utc.date(),
                datetime.min.time(),
                tzinfo=UTC,
            ),
            value_date=value_date,
            source_family=family,
            source_ref="; ".join(refs) or found.method,
            note=f"FX: {found.label}, value date {value_date}",
            tolerance=(
                Decimal(str(found.tolerance_abs)).quantize(_PLACES) if found.tolerance_pct else None
            ),
        )


# ----------------------------------------------------------------------------- live reader


class LiveSnapshotReader(RecordingReader):
    """Reads the runtime store for one evaluation instant, as one caller."""

    def __init__(
        self,
        session,
        *,
        caller: Caller,
        as_of_utc: datetime,
        demo_desk: bool,
        fx_source: FxSource,
        assumption: tuple[str, Any] | None,
        hedge_cover_loader: Callable[[], list[dict]] | None = None,
        book_reads=None,
    ) -> None:
        super().__init__(
            as_of_utc=as_of_utc,
            demo_desk=demo_desk,
            fx_method=getattr(fx_source, "method", FX_METHOD_SPOT),
            assumption_version=assumption[0] if assumption else None,
        )
        self.session = session
        self.caller = caller
        self.fx_source = fx_source
        self._assumption = assumption
        self._hedge_cover_loader = hedge_cover_loader
        self._book_reads = book_reads
        self._naive = session.get_bind().dialect.name == "sqlite"

    def _bound(self, moment: datetime) -> datetime:
        return moment.replace(tzinfo=None) if self._naive else moment

    def _entitled(self, source_system: str | None) -> bool:
        from eurogas_nexus.application.projections.market_reads import row_allowed

        return row_allowed(self.caller.principal, source_system)

    # ---- prices
    def _load_price(self, key, hub, period, side) -> SnapshotInput:
        label = f"{hub} {period.label}"
        for loader in (self._quote, self._settlement, self._firm_mark):
            found = loader(key, hub, period, side, label, simulated=False)
            if found is not None:
                return found
        if self.demo_desk:
            # The demo market: its two-sided board first (bid and offer, as a screen), then its
            # closes; class ``simulated`` either way, and never read on a customer desk.
            for loader in (self._quote, self._settlement):
                found = loader(key, hub, period, side, label, simulated=True)
                if found is not None:
                    return found
        return missing(key, InputKind.PRICE, f"{label} {side}", reason="no price held")

    def _period_rows(self, rows, period, start_attr, end_attr):
        out = []
        for row in rows:
            start = _aware(getattr(row, start_attr)).date()
            end = _aware(getattr(row, end_attr)).date()
            if start == period.start and end in {period.end, period.end - timedelta(days=1)}:
                out.append(row)
        return out

    def _quote(self, key, hub, period, side, label, *, simulated) -> SnapshotInput | None:
        from eurogas_nexus.db.models import MarketQuoteRecord

        rows = (
            self.session.query(MarketQuoteRecord)
            .filter(MarketQuoteRecord.hub == hub)
            .filter(MarketQuoteRecord.observed_at_utc <= self._bound(self.as_of_utc))
            .order_by(MarketQuoteRecord.observed_at_utc.desc())
            .limit(500)
            .all()
        )
        for row in self._period_rows(rows, period, "delivery_start_utc", "delivery_end_utc"):
            if (row.simulated or _is_simulated(row.source_system, row.metadata_json)) != simulated:
                continue
            if not self._entitled(row.source_system):
                continue
            bid, ask = row.bid_price, row.ask_price
            if side == "bid":
                price, klass = bid, InputClass.SOURCED
            elif side == "ask":
                price, klass = ask, InputClass.SOURCED
            else:
                price = None if bid is None or ask is None else (bid + ask) / 2
                klass = InputClass.INDICATIVE  # a mid is not executable
            if simulated:
                klass = InputClass.SIMULATED
            if price is None:
                continue
            return self._price_input(
                key,
                price,
                row.unit,
                row.currency,
                row.observed_at_utc,
                row.source_system,
                row.quote_id,
                f"{label} {side} ({row.venue}{', simulated' if simulated else ''})",
                klass,
                {
                    "basis": "quote",
                    "side": side,
                    "venue": row.venue,
                    "depth_mwh": row.bid_quantity_mwh if side == "bid" else row.ask_quantity_mwh,
                },
            )
        return None

    def _settlement(self, key, hub, period, side, label, *, simulated) -> SnapshotInput | None:
        from eurogas_nexus.db.models import MarketObservationRecord
        from eurogas_nexus.domain.ontology.identity import resolve_hub

        rows = (
            self.session.query(MarketObservationRecord)
            .filter(MarketObservationRecord.observed_at_utc <= self._bound(self.as_of_utc))
            .filter(
                MarketObservationRecord.period_start_utc
                >= self._bound(datetime.combine(period.start, datetime.min.time(), tzinfo=UTC))
            )
            .filter(
                MarketObservationRecord.period_start_utc
                < self._bound(
                    datetime.combine(period.start + timedelta(days=1), datetime.min.time(), UTC)
                )
            )
            .order_by(MarketObservationRecord.observed_at_utc.desc())
            .limit(500)
            .all()
        )
        for row in self._period_rows(rows, period, "period_start_utc", "period_end_utc"):
            metadata = row.metadata_json or {}
            if resolve_hub(metadata.get("hub") or row.product).hub != hub:
                continue
            if _is_simulated(row.source_system, metadata) != simulated:
                continue
            if not self._entitled(row.source_system):
                continue
            klass = InputClass.SIMULATED if simulated else InputClass.INDICATIVE
            return self._price_input(
                key,
                row.price,
                row.unit,
                row.currency,
                row.observed_at_utc,
                row.source_system,
                row.observation_id,
                f"{label} {'simulated price' if simulated else 'settlement'} ({row.market_venue})",
                klass,
                {
                    "basis": "demo" if simulated else "settlement",
                    "side": side,
                    "venue": row.market_venue,
                },
            )
        return None

    def _firm_mark(self, key, hub, period, side, label, *, simulated) -> SnapshotInput | None:
        from eurogas_nexus.db.repositories.commercial_assumptions import current_firm_marks

        for mark in current_firm_marks(self.session, as_of_utc=self.as_of_utc, hub=hub):
            if mark.period.label != period.label:
                continue
            return self._price_input(
                key,
                mark.value,
                mark.unit,
                mark.currency,
                mark.entered_at_utc,
                FIRM_FAMILY,
                mark.mark_id,
                f"{label} firm's mark",
                mark.input_class,
                {"basis": "firm_mark", "side": side, "entered_by": mark.entered_by},
            )
        return None

    def _price_input(
        self, key, price, unit, currency, observed, source, ref, label, klass, detail
    ) -> SnapshotInput | None:
        from eurogas_nexus.application.projections.daily_closes import per_mwh

        unit_text = unit if "/" in str(unit) else f"{currency}/{unit}"
        converted = per_mwh(float(price), unit_text)
        if converted is None:
            return None
        value, unit_mwh = converted
        family = (
            DEMO_FAMILY
            if klass is InputClass.SIMULATED
            else FIRM_FAMILY
            if klass is InputClass.FIRM_MARK
            else source
        )
        return SnapshotInput(
            key=key,
            kind=InputKind.PRICE,
            input_class=klass,
            value=_dec(value),
            unit=unit_mwh,
            currency=unit_mwh.split("/")[0],
            as_of_utc=_aware(observed),
            source_family=family,
            source_ref=str(ref),
            label=label,
            detail={**detail, "native_value": str(_dec(price)), "native_unit": unit_text},
        )

    # ---- FX and rates
    def _load_fx(self, key, base, quote, period) -> SnapshotInput:
        answer = self.fx_source(self.session, base, quote, period, self.as_of_utc)
        if answer is None:
            return missing(key, InputKind.FX, f"{base}/{quote}", reason="no reference rate held")
        return SnapshotInput(
            key=key,
            kind=InputKind.FX,
            input_class=answer.input_class,
            value=answer.rate,
            unit=f"{quote}/{base}",
            currency=quote,
            as_of_utc=answer.as_of_utc,
            source_family=answer.source_family,
            source_ref=answer.source_ref,
            label=answer.note,
            detail={
                "method": answer.method,
                "value_date": answer.value_date,
                "tolerance": None if answer.tolerance is None else str(answer.tolerance),
            },
        )

    def _load_rate(self, key, currency) -> SnapshotInput:
        from eurogas_nexus.db.models import InterestRateObservationRecord
        from eurogas_nexus.domain.market.interest_rates import DEFAULT_BENCHMARK_FOR_CURRENCY

        benchmark = DEFAULT_BENCHMARK_FOR_CURRENCY.get(currency)
        row = None
        if benchmark:
            row = (
                self.session.query(InterestRateObservationRecord)
                .filter(InterestRateObservationRecord.benchmark_id == benchmark)
                .filter(InterestRateObservationRecord.value_date <= self.as_of_utc.date())
                .order_by(InterestRateObservationRecord.value_date.desc())
                .first()
            )
        if row is None or not self._entitled(row.source_system):
            return missing(key, InputKind.RATE, f"{currency} overnight rate", benchmark=benchmark)
        return SnapshotInput(
            key=key,
            kind=InputKind.RATE,
            input_class=InputClass.SOURCED,
            value=_dec(row.rate_pct),
            unit="%/yr",
            currency=currency,
            as_of_utc=datetime.combine(row.value_date, datetime.min.time(), tzinfo=UTC),
            source_family=row.source_system,
            source_ref=row.observation_id,
            label=f"{benchmark} fixing of {row.value_date.isoformat()}",
            detail={"benchmark": benchmark, "day_count": row.day_count},
        )

    # ---- network
    def _load_tariff(self, key, point_id, direction, product, period, tso=None) -> SnapshotInput:
        from sqlalchemy import func, or_

        from eurogas_nexus.application.route_tariff_cost import _tso_matches
        from eurogas_nexus.db.models import TsoTariffRecord

        start = self._bound(datetime.combine(period.start, datetime.min.time(), tzinfo=UTC))
        rows = (
            self.session.query(TsoTariffRecord)
            .filter(TsoTariffRecord.point_id == point_id)
            .filter(func.upper(TsoTariffRecord.direction) == direction)
            .filter(func.upper(TsoTariffRecord.capacity_product) == product.upper())
            .filter(TsoTariffRecord.effective_from <= start)
            .filter(
                or_(TsoTariffRecord.effective_to.is_(None), TsoTariffRecord.effective_to > start)
            )
            .all()
        )
        usable = []
        for row in rows:
            simulated = row.tariff_status == "SIMULATOR_ONLY"
            if simulated and not self.demo_desk:
                continue
            if tso and not _tso_matches(str(row.tso or ""), tso):
                continue  # another operator's charge at the same point
            usable.append(row)
        if not usable:
            return missing(
                key,
                InputKind.TARIFF,
                f"{point_id} {direction} {product}",
                reason="tariff not held",
                point_id=point_id,
            )
        row = min(
            usable, key=lambda item: (_TARIFF_RANK.get(item.tariff_status, 9), item.tariff_id)
        )
        klass = {
            "FINAL": InputClass.SOURCED,
            "SIMULATOR_ONLY": InputClass.SIMULATED,
        }.get(row.tariff_status, InputClass.INDICATIVE)
        # The register holds what the operator published; a capacity price per period is
        # read as a cost per MWh at 100 % load factor for the delivery period's first day
        # (domain/route_cost/tariff_units.py). An energy unit passes unchanged.
        from eurogas_nexus.domain.route_cost.tariff_units import parse_unit, per_mwh

        value, unit, currency = row.tariff_value, row.unit, row.currency
        parsed = parse_unit(row.unit)
        if parsed is not None and parsed.is_capacity:
            read = per_mwh(
                row.tariff_value,
                row.unit,
                on=period.start,
                anniversary=_aware(row.effective_from).date(),
                currency=row.currency,
            )
            if read is None:
                return missing(
                    key,
                    InputKind.TARIFF,
                    f"{point_id} {direction} {product}",
                    reason=f"tariff unit not understood: {row.unit}",
                    point_id=point_id,
                )
            value, unit, currency = read.value, read.unit, read.currency
        return SnapshotInput(
            key=key,
            kind=InputKind.TARIFF,
            input_class=klass,
            value=_dec(value),
            unit=unit,
            currency=currency,
            as_of_utc=_aware(row.created_at_utc),
            source_family=DEMO_FAMILY if klass is InputClass.SIMULATED else "ENTSOG",
            source_ref=row.tariff_id,
            label=f"{row.tso} {row.source_point_name} {row.direction} {row.capacity_product}",
            detail={
                "document_id": row.document_id,
                "tariff_status": row.tariff_status,
                "gas_year": row.gas_year,
                "point_id": row.point_id,
                "point_name": row.source_point_name,
                "effective_from": _aware(row.effective_from).isoformat(),
                "effective_to": (
                    _aware(row.effective_to).isoformat() if row.effective_to else None
                ),
                # The figure the register holds, as the operator published it.
                "published": f"{row.tariff_value:g} {row.unit}",
            },
        )

    def _load_capacity(self, key, point_id, direction, period) -> SnapshotInput:
        from sqlalchemy import func

        from eurogas_nexus.application.identity_resolution import identity_clause
        from eurogas_nexus.db.models import CapacityObservationRecord

        start = self._bound(datetime.combine(period.start, datetime.min.time(), tzinfo=UTC))
        rows = (
            self.session.query(CapacityObservationRecord)
            .filter(identity_clause(self.session, CapacityObservationRecord))
            .filter(CapacityObservationRecord.point_id == point_id)
            .filter(func.upper(CapacityObservationRecord.direction) == direction)
            .filter(CapacityObservationRecord.period_start_utc <= start)
            .filter(CapacityObservationRecord.period_end_utc > start)
            .filter(CapacityObservationRecord.observed_at_utc <= self._bound(self.as_of_utc))
            .order_by(CapacityObservationRecord.observed_at_utc.desc())
            .limit(50)
            .all()
        )
        for row in rows:
            simulated = _is_simulated(row.source_system, row.metadata_json)
            if (simulated and not self.demo_desk) or not self._entitled(row.source_system):
                continue
            return SnapshotInput(
                key=key,
                kind=InputKind.CAPACITY,
                input_class=InputClass.SIMULATED if simulated else InputClass.SOURCED,
                value=_dec(row.capacity_mcm_d),
                unit="mcm/d",
                as_of_utc=_aware(row.observed_at_utc),
                source_family=DEMO_FAMILY if simulated else row.source_system,
                source_ref=row.observation_id,
                label=f"{row.point_name} {row.direction} {row.capacity_type}",
                detail={"capacity_type": row.capacity_type, "point_id": point_id},
            )
        return missing(key, InputKind.CAPACITY, f"{point_id} {direction}", reason="not held")

    def _load_outages(self, zone, period) -> list[SnapshotInput]:
        from eurogas_nexus.db.models import RemitUmmRecord

        start = self._bound(datetime.combine(period.start, datetime.min.time(), tzinfo=UTC))
        end = self._bound(datetime.combine(period.end, datetime.min.time(), tzinfo=UTC))
        rows = (
            self.session.query(RemitUmmRecord)
            .filter(RemitUmmRecord.published_at_utc <= self._bound(self.as_of_utc))
            .filter(RemitUmmRecord.event_start_utc < end)
            .all()
        )
        latest: dict[str, Any] = {}
        for row in rows:
            if zone not in (row.balancing_zone or "").upper():
                continue
            held = latest.get(row.message_id)
            if held is None or row.version > held.version:
                latest[row.message_id] = row
        out = []
        for row in sorted(latest.values(), key=lambda item: item.message_id):
            stop = _aware(row.event_stop_utc)
            if stop is not None and stop <= _aware(start):
                continue
            if str(row.event_status).lower() in {"dismissed", "inactive", "cancelled"}:
                continue
            simulated = row.source_system == "DEMO"
            if (simulated and not self.demo_desk) or not self._entitled(row.source_system):
                continue
            out.append(
                SnapshotInput(
                    key=f"outage:{row.message_id}",
                    kind=InputKind.OUTAGE,
                    input_class=InputClass.SIMULATED if simulated else InputClass.SOURCED,
                    value=_dec(row.unavailable_gwh_d),
                    unit="GWh/d",
                    as_of_utc=_aware(row.published_at_utc),
                    source_family=DEMO_FAMILY if simulated else row.source_system,
                    source_ref=row.record_id,
                    label=f"{row.asset_name} ({row.unavailability_type})",
                    detail={
                        "message_id": row.message_id,
                        "version": row.version,
                        "asset_eic": row.asset_eic,
                        "asset_name": row.asset_name,
                        "balancing_zone": row.balancing_zone,
                        "unavailability_type": row.unavailability_type,
                        "technical_capacity": row.technical_capacity,
                        "unavailable_capacity": row.unavailable_capacity,
                        "capacity_unit": row.unit,
                        "event_start_utc": _aware(row.event_start_utc).isoformat(),
                        "event_stop_utc": (
                            _aware(row.event_stop_utc).isoformat() if row.event_stop_utc else None
                        ),
                    },
                )
            )
        return out

    # ---- assumptions and book
    def _load_assumption(self, key, catalogue_key) -> SnapshotInput:
        if self._assumption is None:
            return missing(key, InputKind.ASSUMPTION, catalogue_key, reason="no approved set")
        version_id, version = self._assumption
        value = version.value(catalogue_key)
        if value is None:
            return missing(
                key,
                InputKind.ASSUMPTION,
                catalogue_key,
                reason="not in the approved set",
                set_id=version.set_id,
                version=version.version,
            )
        return SnapshotInput(
            key=key,
            kind=InputKind.ASSUMPTION,
            input_class=InputClass.ASSUMPTION,
            value=value.value,
            unit=value.unit,
            currency=value.currency,
            as_of_utc=version.approved_at_utc,
            source_family=FIRM_FAMILY,
            source_ref=f"{version_id}:{catalogue_key}",
            label=f"{version.name} v{version.version}: {catalogue_key}",
            detail={
                "set_id": version.set_id,
                "set_name": version.name,
                "version": version.version,
                "set_by": version.created_by,
                "set_at_utc": version.created_at_utc.isoformat(),
                "approved_by": version.approved_by,
                "range_low": None if value.range_low is None else str(value.range_low),
                "range_high": None if value.range_high is None else str(value.range_high),
                "origin": "firm_set",
            },
        )

    def _load_hedge_cover(self) -> list[SnapshotInput]:
        rows = self._hedge_cover_loader() if self._hedge_cover_loader else []
        klass = InputClass.SIMULATED if self.demo_desk else InputClass.SOURCED
        out = []
        for row in rows:
            out.append(
                SnapshotInput(
                    key=f"book:hedge:{row['contract_id']}:{row['month']}",
                    kind=InputKind.BOOK,
                    input_class=klass,
                    value=_dec(row["contract_mwh"]),
                    unit="MWh",
                    as_of_utc=_aware(row.get("as_of_utc")) or self.as_of_utc,
                    source_family=DEMO_FAMILY if self.demo_desk else FIRM_FAMILY,
                    source_ref=f"hedge_approval:{row['contract_id']}",
                    label=f"{row['contract_name']} {row['month']}",
                    detail={
                        key: (str(_dec(value)) if isinstance(value, float) else value)
                        for key, value in row.items()
                        if key != "as_of_utc"
                    },
                )
            )
        return out

    def _load_collection(self, name: str) -> list[SnapshotInput]:
        from eurogas_nexus.application import opportunity_reads

        reads = self._book_reads
        if name == "outage_feed":
            feed = opportunity_reads.outage_feed(self.session, demo_desk=self.demo_desk)
            held = feed["messages"] > 0
            only_demo = held and feed["sources"] == ["DEMO"]
            return [
                SnapshotInput(
                    key="outage_feed:messages",
                    kind=InputKind.OUTAGE,
                    input_class=(
                        InputClass.SIMULATED
                        if only_demo
                        else InputClass.SOURCED
                        if held
                        else InputClass.MISSING
                    ),
                    value=Decimal(feed["messages"]) if held else None,
                    unit="messages",
                    as_of_utc=self.as_of_utc,
                    source_family=DEMO_FAMILY if only_demo else "REMIT",
                    source_ref=",".join(feed["sources"]),
                    label="outage messages held",
                    detail=feed,
                )
            ]
        if reads is None:
            return []
        if name == "positions":
            rows, key, value = reads.positions(), ("book_id", "hub", "month"), "net_mwh"
        elif name == "contracts":
            rows, key, value = reads.contracts(), ("contract_id",), "mwh_per_day"
        elif name == "mandates":
            rows, key, value = (
                opportunity_reads.mandates(self.session),
                ("mandate_id",),
                "max_net_mwh_per_month",
            )
        elif name == "held_capacity":
            rows, key, value = (
                opportunity_reads.held_capacity(self.session, reads.contracts()),
                ("route_id",),
                "capacity_mwh_per_day",
            )
        elif name == "storage":
            rows, key, value = (
                opportunity_reads.storage(self.session),
                ("facility_id",),
                "working_gas_mwh",
            )
        elif name == "resource_pool":
            tomorrow = self.as_of_utc.date() + timedelta(days=1)
            rows, key, value = (
                opportunity_reads.resource_pool(self.session, self.caller.principal, tomorrow),
                ("row_kind", "id"),
                "available_quantity_mwh_per_day",
            )
        else:  # residuals
            rows, key, value = reads.residuals(self.session), ("book_id", "hub"), "residual_mwh"
        klass = InputClass.SIMULATED if self.demo_desk else InputClass.SOURCED

        def row_class(row) -> InputClass:
            # A sale option is priced from a market observation: a settlement (indicative)
            # or a demo price (simulated); a demo storage row is simulated.
            if (
                row.get("sale_price_simulated")
                or row.get("contract_cost_simulated")
                or _is_simulated(row.get("source_system"), None)
            ):
                return InputClass.SIMULATED
            if row.get("row_kind") == "option":
                return InputClass.SIMULATED if self.demo_desk else InputClass.INDICATIVE
            return klass

        return [
            SnapshotInput(
                key=f"{name}:" + ":".join(str(row.get(part) or "-") for part in key),
                kind=InputKind.BOOK,
                input_class=row_class(row),
                value=None if row.get(value) is None else _dec(row[value]),
                unit="MWh/d" if value == "mwh_per_day" else "MWh",
                as_of_utc=self.as_of_utc,
                source_family=DEMO_FAMILY if self.demo_desk else FIRM_FAMILY,
                source_ref=f"{name}:{row.get(key[0])}",
                label=f"{name} " + " ".join(str(row.get(part) or "-") for part in key),
                detail=_json_safe(row),
            )
            for row in rows
        ]


def _json_safe(value):
    """Floats as decimal text, everything else JSON-safe (rows become recorded detail)."""

    if isinstance(value, float):
        return str(_dec(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if value is None or isinstance(value, str | int | bool):
        return value
    return str(value)


def hedge_cover_rows(caller: Caller, today: date) -> list[dict]:
    """Approved hedge bands against the cover the linked trades give, per contract and month.

    The same calculation as ``GET /api/portfolio/hedge-approvals`` (``deal_hedge_usage`` over
    the position ladder's legs), flattened to one row per remaining month.
    """

    from eurogas_nexus.application.limits_service import horizon
    from eurogas_nexus.application.position_inputs import ladder_inputs
    from eurogas_nexus.db.models import HedgeApprovalRecord
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.risk.limits import HedgeApproval, VolumeLeg, deal_hedge_usage

    with get_session_factory()() as session:
        approvals = (
            session.query(HedgeApprovalRecord).order_by(HedgeApprovalRecord.contract_id).all()
        )
        # The approver in words (display name), never a login id.
        from eurogas_nexus.db.models import IdentityPrincipalRecord

        approvers = {
            row.name: row.display_name
            for row in session.query(IdentityPrincipalRecord).filter(
                IdentityPrincipalRecord.name.in_({a.updated_by for a in approvals if a.updated_by})
            )
        }
        session.expunge_all()
    if not approvals:
        return []
    start, end = horizon(today)
    inputs = ladder_inputs(caller, today, start, end)
    linked: dict[str, list[str]] = {}
    for order in inputs.orders:
        target = getattr(order, "linked_resource_id", None)
        if target:
            linked.setdefault(str(target), []).append(order.order_observation_id)
    legs = {leg.reference: leg for leg in inputs.legs}
    names = {contract.contract_id: contract.contract_name for contract in inputs.contracts}

    def volume(leg) -> VolumeLeg:
        return VolumeLeg(leg.reference, leg.first_gas_day, leg.last_gas_day, leg.mwh_per_day)

    rows: list[dict] = []
    for approval in approvals:
        contract = legs.get(approval.contract_id)
        if contract is None or contract.kind != "physical":
            continue  # retired, outside the caller's books, or not a physical contract
        hedges = [legs[ref] for ref in linked.get(approval.contract_id, []) if ref in legs]
        usage = deal_hedge_usage(
            HedgeApproval(
                contract_id=approval.contract_id,
                min_hedge_ratio_pct=approval.min_hedge_ratio_pct,
                max_hedge_ratio_pct=approval.max_hedge_ratio_pct,
                approval_ref=approval.approval_ref,
                valid_until=approval.valid_until,
            ),
            [volume(contract)],
            [volume(leg) for leg in hedges],
            today=today,
        )
        if usage["status"] == "expired":
            continue
        for month in usage["months"]:
            rows.append(
                {
                    "contract_id": approval.contract_id,
                    "contract_name": names.get(approval.contract_id, approval.contract_id),
                    "book_id": contract.book_id or None,
                    "hub": contract.hub,
                    "month": month["month"],
                    "contract_mwh": float(month["contract_mwh"]),
                    "hedged_mwh": float(month["hedged_mwh"]),
                    "band_low_pct": approval.min_hedge_ratio_pct,
                    "band_high_pct": approval.max_hedge_ratio_pct,
                    "approval_ref": approval.approval_ref,
                    "approved_by": approvers.get(approval.updated_by, approval.updated_by),
                    "approved_at_utc": (
                        _aware(approval.updated_at_utc).isoformat()
                        if approval.updated_at_utc
                        else None
                    ),
                    "valid_until": (
                        approval.valid_until.isoformat() if approval.valid_until else None
                    ),
                    "linked_trades": len(hedges),
                    "as_of_utc": approval.updated_at_utc,
                }
            )
    return rows


def open_valuation_snapshot(
    session,
    *,
    caller: Caller,
    as_of_utc: datetime | None = None,
    assumption_set_id: str | None = None,
    book_id: str | None = None,
    fx_source: FxSource | None = None,
    demo_desk: bool | None = None,
) -> LiveSnapshotReader:
    """Open the reader an evaluation runs on.

    Args:
        session: Runtime-store session.
        caller: Whose entitlement the reads run under (a person, or the firm's service
            caller for a scheduled evaluation).
        as_of_utc: The evaluation instant (default now). Nothing observed after it is read.
        assumption_set_id: The assumption set to read; default the book's own approved set,
            else the organisation's most recently approved one.
        book_id: The book an on-demand evaluation is for (selects a book-owned set).
        fx_source: FX adapter; default :class:`ForwardFx` (design D.5); :class:`SpotEcbFx`
            remains for a caller that wants the spot reference rate alone.
        demo_desk: Override the deployment's demo-marks setting (tests).

    Returns:
        A recording reader; :func:`freeze_snapshot` persists what it read.
    """

    from eurogas_nexus.application.opportunity_reads import BookReads
    from eurogas_nexus.core.config import demo_marks_allowed
    from eurogas_nexus.db.repositories.commercial_assumptions import resolve_assumption_version

    moment = _aware(as_of_utc) or datetime.now(UTC)
    demo = demo_marks_allowed() if demo_desk is None else demo_desk
    assumption = resolve_assumption_version(
        session, day=moment.date(), set_id=assumption_set_id, book_id=book_id
    )
    return LiveSnapshotReader(
        session,
        caller=caller,
        as_of_utc=moment,
        demo_desk=demo,
        fx_source=fx_source or ForwardFx(demo_desk=demo, caller=caller),
        assumption=assumption,
        hedge_cover_loader=lambda: hedge_cover_rows(caller, moment.date()),
        book_reads=BookReads(caller, moment.date()),
    )


def freeze_snapshot(
    session, reader: RecordingReader, *, purpose: str, created_by: str
) -> SnapshotManifest:
    """Persist everything the reader read; returns the stored manifest."""

    from eurogas_nexus.db.repositories.commercial_assumptions import save_snapshot

    manifest = reader.manifest(f"vsnap-{uuid4().hex[:24]}")
    save_snapshot(session, manifest, purpose=purpose, created_by=created_by)
    return manifest


def replay_snapshot(session, snapshot_id: str) -> ReplayReader | None:
    """A reader that answers only from a stored snapshot, or ``None`` when unknown."""

    from eurogas_nexus.db.repositories.commercial_assumptions import load_snapshot

    loaded = load_snapshot(session, snapshot_id)
    return None if loaded is None else ReplayReader(loaded[1])
