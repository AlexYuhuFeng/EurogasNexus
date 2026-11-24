"""Type T: a time spread captured with storage (design basis 2, B.3).

Inject in period 1, withdraw in period 2. Per MWh, in the hub's currency:

    net = P_2(bid) - P_1(ask) - injection fee - withdrawal fee - fuel x P_1
          - P_1 x r x dt - network charges - capacity fee (only when the storage is not held)

- **Held storage** (the storage facility masters the firm nominates against): the capacity
  fee is sunk; the injection and withdrawal fees come from the record (its columns are in
  GBP; converted when the hub quotes otherwise); fuel is the round-trip loss
  ``1 - injection efficiency x withdrawal efficiency``; volume = working gas, capped by
  the injection rate over period 1 and the withdrawal rate over period 2.
- **Storage not held**: the firm's own storage tariff (assumption set: ``storage.capacity_fee``,
  ``storage.injection_fee``, ``storage.withdrawal_fee``, ``storage.fuel``), so the result is
  at most indicative; volume = the hub's supply contracts over period 1 (what could be put
  away). Without the firm's tariff nothing is claimed.
- **Financing** ``r``: the firm's ``financing.rate``; without one, the currency's overnight
  benchmark fixing is used and the row says so (indicative). ``dt`` = days between the
  starts of the two periods / 365.
- **Network charges** at the storage point: the firm's ``storage.network_charges`` when set;
  otherwise not included, and a falsifier says so.

Rate-dependent limits (ratchets) are not modelled: the capacity check reads "not assessed".
Candidates: the next summer -> winter pair, and the best month pair in the next 12 months.

Worked example (design B.4, Sum-27 into Win-27, storage not held): 31.50 - 28.00 = 3.50
gross; capacity 2.20, injection 0.20 + withdrawal 0.15, fuel 1 % x 28.00 = 0.28, financing
28.00 x 3.0 % x 183 / 365 = 0.421151, network charges 0.20: costs 3.451151; net 0.048849
EUR/MWh - below the 0.10 minimum, so "watch" (the control doing its job). The design's
illustrative 0.42 uses half a year; the engine counts the 183 days between the period starts.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
from eurogas_nexus.domain.ontology.markets import quote_currency
from eurogas_nexus.domain.opportunities.claims import grouped, period_label, signed
from eurogas_nexus.domain.opportunities.evaluator import EvaluationContext, register
from eurogas_nexus.domain.opportunities.locational import forward_months
from eurogas_nexus.domain.opportunities.model import (
    AssumptionUse,
    Candidate,
    Check,
    CheckKind,
    CheckResult,
    Falsifier,
    Leg,
    LegKind,
    Measure,
    OpportunityType,
    Sensitivity,
)
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import InputKind, SnapshotInput, SnapshotReader

Q = Decimal("0.000001")
MONEY = Decimal("0.01")
HUNDRED = Decimal(100)
YEAR_DAYS = Decimal(365)
MONTH_PAIRS = 12


def _dec(value: object) -> Decimal | None:
    return None if value is None or value == "" else Decimal(str(value))


def season_pair(as_of_day) -> tuple[DeliveryPeriod, DeliveryPeriod]:
    """The next summer (April-September) and the winter after it."""

    year = as_of_day.year + (1 if as_of_day.month >= 4 else 0)
    return DeliveryPeriod.season("SUM", year % 100), DeliveryPeriod.season("WIN", year % 100)


class StorageSpreadEvaluator:
    """Type T for held storage and, with the firm's tariff, storage not held."""

    name = "storage_spread"
    version = "1"
    type = OpportunityType.TIME_SPREAD

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """The season pair and the best month pair, per held facility and per supplied hub."""

        day = context.as_of_utc.date()
        months = forward_months(day)
        extra = []
        last = months[-1]
        for _ in range(MONTH_PAIRS - len(months)):
            nxt = DeliveryPeriod.month(last.end.year, last.end.month)
            extra.append(nxt)
            last = nxt
        months = [*months, *extra]
        pairs = [season_pair(day)] + [(a, b) for i, a in enumerate(months) for b in months[i + 1 :]]
        for facility in snapshot.collection("storage"):
            best = self._best(snapshot, context, pairs, facility.detail["hub"], facility, None)
            yield from best
        if not snapshot.assumption("storage.capacity_fee").held:
            return
        hubs: dict[str, list[SnapshotInput]] = {}
        for contract in snapshot.collection("contracts"):
            hubs.setdefault(str(contract.detail.get("hub")), []).append(contract)
        for hub, contracts in sorted(hubs.items()):
            yield from self._best(snapshot, context, pairs, hub, None, contracts)

    def _best(self, snapshot, context, pairs, hub, facility, contracts) -> list[Candidate]:
        season = [self._price(snapshot, context, hub, *pairs[0], facility, contracts)]
        months = [
            self._price(snapshot, context, hub, first, second, facility, contracts)
            for first, second in pairs[1:]
        ]
        months = [item for item in months if item is not None]
        chosen = [item for item in season if item is not None]
        if months:
            chosen.append(max(months, key=lambda item: item.headline.value))
        return chosen

    def _price(self, s, context, hub, first, second, facility, contracts) -> Candidate | None:
        buy = s.price(hub, first, "ask")
        sell = s.price(hub, second, "bid")
        if not (buy.held and sell.held):
            return None
        unit = buy.unit or f"{quote_currency(hub)}/MWh"
        currency = unit.split("/")[0]
        p1, p2 = buy.value, sell.value
        gross = p2 - p1
        if gross <= 0:
            return None
        inputs: list[SnapshotInput] = [buy, sell]
        assumptions: list[AssumptionUse] = []
        legs = [
            self._term(
                "storage.withdraw", f"Sell {hub} {period_label(second.label)} bid", sell, p2, unit
            ),
            self._term(
                "storage.inject", f"Buy {hub} {period_label(first.label)} offer", buy, -p1, unit
            ),
            Leg(
                LegKind.SUBTOTAL,
                "storage.gross",
                "Gross time spread",
                subtotal=Measure(gross, unit),
            ),
        ]
        running = gross
        held = facility is not None

        def fee(key: str, label: str, amount: Decimal, item: SnapshotInput | None):
            nonlocal running
            amount = amount.quantize(Q)
            running -= amount
            legs.append(self._term(key, label, item, -amount, unit))

        def converted(value: Decimal, from_ccy: str) -> Decimal | None:
            if from_ccy == currency:
                return value
            fx = s.fx(from_ccy, currency, first)
            inputs.append(fx)
            return None if not fx.held else value * fx.value

        if held:
            detail = facility.detail
            inputs.append(facility)
            for key, label in (
                ("injection_fee", "Injection fee"),
                ("withdrawal_fee", "Withdrawal fee"),
            ):
                amount = converted(
                    _dec(detail.get(key)) or Decimal(0), str(detail.get("fee_currency") or currency)
                )
                if amount is None:
                    return None
                fee(f"storage.{key}", f"{label} ({detail.get('name')})", amount, facility)
            efficiency = (_dec(detail.get("injection_efficiency")) or Decimal(1)) * (
                _dec(detail.get("withdrawal_efficiency")) or Decimal(1)
            )
            fee(
                "storage.fuel",
                f"Round-trip loss {grouped((1 - efficiency) * 100, 2)} % of the purchase",
                (1 - efficiency) * p1,
                facility,
            )
        else:
            for key, label in (
                ("storage.capacity_fee", "Storage capacity (firm's tariff)"),
                ("storage.injection_fee", "Injection fee (firm's tariff)"),
                ("storage.withdrawal_fee", "Withdrawal fee (firm's tariff)"),
            ):
                item = s.assumption(key)
                inputs.append(item)
                if not item.held:
                    continue
                assumptions.append(self._use(item))
                amount = converted(item.value, item.currency or currency)
                if amount is None:
                    return None
                fee(key, label, amount, item)
            loss = s.assumption("storage.fuel")
            if loss.held:
                inputs.append(loss)
                assumptions.append(self._use(loss))
                fee(
                    "storage.fuel",
                    f"Storage fuel {loss.value} % of the purchase (firm's assumption)",
                    loss.value / HUNDRED * p1,
                    loss,
                )
        network = s.assumption("storage.network_charges")
        if network.held:
            inputs.append(network)
            assumptions.append(self._use(network))
            amount = converted(network.value, network.currency or currency)
            if amount is None:
                return None
            fee(
                "storage.network",
                "Network entry and exit at the storage point (firm's assumption)",
                amount,
                network,
            )
        rate = s.assumption("financing.rate")
        if rate.held:
            inputs.append(rate)
            assumptions.append(self._use(rate))
            rate_label = "firm's financing rate"
        else:
            rate = s.rate(currency)
            inputs.append(rate)
            if rate.held:
                inputs.append(
                    SnapshotInput(
                        key=f"{rate.key}#proxy",
                        kind=InputKind.RATE,
                        input_class=InputClass.INDICATIVE,
                        value=rate.value,
                        unit=rate.unit,
                        as_of_utc=rate.as_of_utc,
                        source_family=rate.source_family,
                        source_ref=rate.source_ref,
                        label="overnight benchmark used: the firm has set no financing rate",
                    )
                )
            rate_label = f"{rate.detail.get('benchmark') or 'overnight'} benchmark (no firm rate)"
        days = Decimal((second.start - first.start).days)
        if rate.held:
            fee(
                "storage.financing",
                f"Financing {grouped(rate.value, 2)} % x {days} d / 365 on the purchase "
                f"({rate_label})",
                p1 * rate.value / HUNDRED * days / YEAR_DAYS,
                rate,
            )
        net = running
        complete = all(item.held for item in inputs)
        if complete and net <= 0:
            return None
        if held:
            detail = facility.detail
            volume = min(
                _dec(detail.get("working_gas_mwh")) or Decimal(0),
                (_dec(detail.get("max_injection_mwh_per_day")) or Decimal(0)) * first.days,
                (_dec(detail.get("max_withdrawal_mwh_per_day")) or Decimal(0)) * second.days,
            )
        else:
            volume = sum((Decimal(str(c.value or 0)) * first.days for c in contracts), Decimal(0))
            inputs.extend(contracts)
        volume = volume.quantize(Decimal("0.1"))
        if volume <= 0:
            return None
        value = (net * volume).quantize(MONEY)
        legs += [
            Leg(LegKind.RESULT, "storage.net", "Net time spread", subtotal=Measure(net, unit)),
            Leg(
                LegKind.VOLUME,
                "storage.volume",
                "Working gas within the injection and withdrawal rates"
                if held
                else f"Supply at {hub} over {period_label(first.label)}",
                quantity=Measure(volume, "MWh"),
            ),
            Leg(LegKind.VALUE, "storage.value", "Value", quantity=Measure(value, currency)),
        ]
        to_eur = None
        if currency == "EUR":
            to_eur = (net, value)
        else:
            fx = s.fx(currency, "EUR", first)
            if fx.held:
                to_eur = ((net * fx.value).quantize(Q), (value * fx.value).quantize(MONEY))
        costs = gross - net
        expires = gas_day_start_for_date(first.start)
        if expires <= context.as_of_utc:
            return None
        where = str(facility.detail.get("name")) if held else "storage not held (firm's tariff)"
        return Candidate(
            type=self.type,
            identity=(hub, where),
            period=first,
            book_ids=tuple(
                sorted(
                    {
                        str(c.detail.get("book_id"))
                        for c in contracts or []
                        if c.detail.get("book_id")
                    }
                )
            ),
            claim_key="storage.spread",
            claim_fields={
                "hub": hub,
                "first": period_label(first.label),
                "second": period_label(second.label),
                "where": where,
                "margin": f"{signed(net, 3)} {unit}",
                "volume": grouped(volume),
                "value": f"{currency} {grouped(value)}",
            },
            headline=Measure(net, unit),
            volume=Measure(volume, "MWh"),
            value=Measure(value, currency),
            value_eur=None if to_eur is None else Measure(to_eur[1], "EUR"),
            margin_eur=None if to_eur is None else Measure(to_eur[0], "EUR/MWh"),
            route_cost_eur=None,
            legs=tuple(legs),
            assumptions=tuple(assumptions),
            falsifiers=(
                Falsifier(
                    "storage.spread",
                    f"{hub} {period_label(second.label)} - {period_label(first.label)} below "
                    f"{grouped(costs, 3)} {unit}.",
                ),
                Falsifier(
                    "storage.ratchets",
                    "Rate-dependent injection or withdrawal limits (ratchets) bind; they "
                    "are not modelled.",
                ),
                *(
                    ()
                    if network.held
                    else (
                        Falsifier(
                            "storage.network",
                            "Network charges at the storage point (not held) exceed the net.",
                        ),
                    )
                ),
            ),
            sensitivity=(
                Sensitivity(
                    "spread",
                    "breakeven",
                    Measure(costs.quantize(Q), unit),
                    f"Breakeven time spread {grouped(costs, 3)} {unit}",
                ),
                Sensitivity(
                    "spread",
                    "per_unit",
                    Measure((volume / 10).quantize(MONEY), currency),
                    f"±0.10 {unit} on the spread = ±{currency} {grouped(volume / 10)}",
                ),
            ),
            checks=(
                Check(
                    CheckKind.CAPACITY,
                    CheckResult.NOT_ASSESSED,
                    "rate-dependent injection and withdrawal limits are not modelled",
                ),
            ),
            expires_at_utc=expires,
            inputs=tuple(dict((item.key, item) for item in inputs).values()),
            evaluator=self.name,
            evaluator_version=self.version,
        )

    @staticmethod
    def _term(key, label, item, contribution, unit) -> Leg:
        return Leg(
            kind=LegKind.TERM,
            label_key=key,
            label=label,
            rate=None if item is None or item.value is None else Measure(item.value, item.unit),
            contribution=Measure(contribution, unit),
            input_class=None if item is None else item.input_class,
            source_family=None if item is None else item.source_family,
            source_ref="" if item is None else item.source_ref,
            as_of_utc=None if item is None else item.as_of_utc,
            input_keys=() if item is None else (item.key,),
        )

    @staticmethod
    def _use(item: SnapshotInput) -> AssumptionUse:
        return AssumptionUse.of(item)


STORAGE_SPREAD = register(StorageSpreadEvaluator())
