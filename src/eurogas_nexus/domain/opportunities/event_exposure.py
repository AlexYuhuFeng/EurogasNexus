"""Type E: an outage that reduces the firm's supply, and what covering it costs.

For each active supply contract and each published unavailability in its hub's balancing
zone that is active now or starts within :data:`HORIZON_DAYS`, linked to the contract by its
source (below), per MWh in the hub's currency:

    exposure = P_cover - P_contract,   volume = DCQ x unavailable / technical x days

``P_cover`` is the day-ahead offer at the hub when held, else the current month's; the
volume is the contract's daily quantity scaled by the share of the asset that is out, over
the outage's remaining gas days (to its published end, else the horizon). The value is the
cost of buying the missing gas back against what the contract would have cost (negative when
the market is below the contract price: the shortfall still has to be covered, at a gain).

**Linking an outage to a contract.** The contract record names no source asset, so the link
is the contract's source name (the first word of the contract name, at least four letters)
appearing in the outage's asset name, in the contract hub's balancing zone. The rule is
stated on the conversion row; a contract that names its source differently is not linked
(never guessed). An own unpublished outage may feed this type (operations), never a margin
type (the insider wall in the controls).

Worked example: Haldor supply 24,000 MWh/d at NBP, contract price 29.50 GBP/MWh; outage at
"Haldor field" 52 of 70 mcm/d out for 3 more gas days: share 0.742857 (6 dp), affected
17,828.568 MWh/d x 3 d = 53,485.7 MWh; day-ahead offer 33.80 GBP/MWh: 33.80 - 29.50 = 4.30
GBP/MWh; GBP 229,988.51.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal

from eurogas_nexus.domain.market.gas_day import gas_day_label
from eurogas_nexus.domain.opportunities.claims import grouped
from eurogas_nexus.domain.opportunities.evaluator import EvaluationContext, register
from eurogas_nexus.domain.opportunities.model import (
    Candidate,
    Falsifier,
    Leg,
    LegKind,
    Measure,
    OpportunityType,
    Sensitivity,
)
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod, month_of
from eurogas_nexus.domain.valuation.snapshot import (
    InputKind,
    SnapshotReader,
    missing,
)

HORIZON_DAYS = 14
MONEY = Decimal("0.01")
Q = Decimal("0.000001")
_GENERIC = {"demo", "supply", "contract", "the", "gas", "lng", "term", "spot"}


def source_name(contract_name: str) -> str | None:
    """The contract's source as it names it: the first word of four letters or more."""

    for word in contract_name.replace("(", " ").split():
        clean = "".join(ch for ch in word if ch.isalpha())
        if len(clean) >= 4 and clean.casefold() not in _GENERIC:
            return clean
    return None


def _moment(text: object) -> datetime | None:
    return None if not text else datetime.fromisoformat(str(text))


class EventExposureEvaluator:
    """Type E over the ``contracts`` collection and the outages in each hub's zone."""

    name = "event_exposure"
    version = "1"
    type = OpportunityType.EVENT_EXPOSURE

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """One candidate per (contract, linked outage)."""

        now = context.as_of_utc
        today = DeliveryPeriod.parse(gas_day_label(now)).start
        horizon = now + timedelta(days=HORIZON_DAYS)
        for contract in snapshot.collection("contracts"):
            detail = contract.detail
            source = source_name(str(detail.get("contract_name") or ""))
            hub = str(detail.get("hub") or "")
            if source is None or not hub:
                continue
            for outage in snapshot.outages(hub, month_of(today)):
                found = self._candidate(snapshot, context, contract, outage, source, hub, horizon)
                if found is not None:
                    yield found

    def _candidate(self, snapshot, context, contract, outage, source, hub, horizon):
        now = context.as_of_utc
        asset = str(outage.detail.get("asset_name") or outage.label)
        if source.casefold() not in asset.casefold():
            return None
        start = _moment(outage.detail.get("event_start_utc")) or now
        stop = _moment(outage.detail.get("event_stop_utc"))
        if start > horizon or (stop is not None and stop <= now):
            return None
        technical = outage.detail.get("technical_capacity")
        unavailable = outage.detail.get("unavailable_capacity")
        if not technical or unavailable is None:
            return None
        share = (Decimal(str(unavailable)) / Decimal(str(technical))).quantize(Q)
        end = stop if stop is not None and stop < horizon else horizon
        days = max(1, math.ceil((end - max(start, now)).total_seconds() / 86_400))
        dcq = Decimal(str(contract.value or 0))
        affected = (dcq * share).quantize(Decimal("0.001"))
        volume = (affected * days).quantize(Decimal("0.1"))
        if volume <= 0:
            return None
        today = DeliveryPeriod.parse(gas_day_label(now)).start
        cover = snapshot.price(hub, DeliveryPeriod.gas_day(today + timedelta(days=1)), "ask")
        if not cover.held:
            cover = snapshot.price(hub, month_of(today), "ask")
        contract_price = contract.detail.get("price")
        price = Decimal(str(contract_price)) if contract_price is not None else None
        unit = cover.unit or f"{contract.detail.get('price_currency') or 'EUR'}/MWh"
        currency = unit.split("/")[0]
        p_cover = cover.value if cover.held else Decimal(0)
        p_contract = price if price is not None else Decimal(0)
        terms = [
            Leg(
                kind=LegKind.TERM,
                label_key="event.cover",
                label=f"Cover at {hub} ({cover.label or 'price not held'})",
                rate=Measure(p_cover, unit),
                contribution=Measure(p_cover, unit),
                input_class=cover.input_class,
                source_family=cover.source_family,
                source_ref=cover.source_ref,
                as_of_utc=cover.as_of_utc,
                input_keys=(cover.key,),
            ),
            Leg(
                kind=LegKind.TERM,
                label_key="event.contract_price",
                label=f"Contract price of {contract.detail.get('contract_name')}",
                label_params={"contract": str(contract.detail.get("contract_name") or "")},
                rate=Measure(p_contract, unit),
                contribution=Measure(-p_contract, unit),
                input_class=contract.input_class,
                source_family=contract.source_family,
                source_ref=contract.source_ref,
                input_keys=(contract.key,),
            ),
        ]
        net = p_cover - p_contract
        value = (net * volume).quantize(MONEY)
        legs = (
            Leg(
                kind=LegKind.CONVERSION,
                label_key="event.link",
                label=f"Linked: the outage asset '{asset}' names the contract's source "
                f"'{source}' in the {hub} zone",
                input_class=outage.input_class,
                source_family=outage.source_family,
                source_ref=outage.source_ref,
                as_of_utc=outage.as_of_utc,
                input_keys=(outage.key,),
            ),
            Leg(
                kind=LegKind.CONVERSION,
                label_key="event.share",
                label=f"Share out {unavailable} / {technical} "
                f"{outage.detail.get('capacity_unit') or ''} = {grouped(share * 100, 1)} % "
                f"of {grouped(dcq)} MWh/d = {grouped(affected, 0)} MWh/d",
                rate=Measure(share, "ratio"),
                quantity=Measure(affected, "MWh/d"),
            ),
            *terms,
            Leg(LegKind.RESULT, "event.net", "Cover cost per MWh", subtotal=Measure(net, unit)),
            Leg(
                LegKind.VOLUME,
                "event.volume",
                f"{grouped(affected, 0)} MWh/d x {days} d",
                quantity=Measure(volume, "MWh"),
                label_params={"mwh_d": grouped(affected, 0), "days": str(days)},
            ),
            Leg(LegKind.VALUE, "event.value", "Cover cost", quantity=Measure(value, currency)),
        )
        inputs = (outage, contract, cover)
        if price is None:
            inputs = (
                *inputs,
                missing(
                    f"{contract.key}#price",
                    InputKind.BOOK,
                    f"contract price of {contract.detail.get('contract_name')} in {currency}",
                ),
            )
        period = DeliveryPeriod(
            max(start, now).date(), end.date() + timedelta(days=1), f"{today.isoformat()}+{days}d"
        )
        return Candidate(
            type=self.type,
            identity=(
                f"contract:{contract.detail.get('contract_id')}",
                f"outage:{outage.detail.get('message_id')}",
            ),
            period=period,
            book_ids=tuple(item for item in (contract.detail.get("book_id"),) if item),
            claim_key="event.exposure",
            claim_fields={
                "asset": asset,
                "contract": str(contract.detail.get("contract_name")),
                "mwh_d": grouped(affected),
                "days": str(days),
                "volume": grouped(volume),
                "cover": f"{grouped(p_cover, 2)} {unit}",
                "contract_price": f"{grouped(p_contract, 2)} {unit}",
                "value": f"{currency} {grouped(value)}",
            },
            headline=Measure(net, unit),
            volume=Measure(volume, "MWh"),
            value=Measure(value, currency),
            legs=legs,
            falsifiers=(
                Falsifier(
                    "event.outage_ends",
                    f"The outage at {asset} ends before {end.date().isoformat()}.",
                ),
                Falsifier(
                    "event.not_our_source",
                    f"{contract.detail.get('contract_name')} is not supplied from {asset}.",
                ),
                Falsifier(
                    "event.price", f"{hub} trades at or below {grouped(p_contract, 2)} {unit}."
                ),
            ),
            sensitivity=(
                Sensitivity(
                    "cover_price",
                    "per_unit",
                    Measure(volume.quantize(MONEY), currency),
                    f"±1 {unit} on the cover price = ±{currency} {grouped(volume)}",
                ),
                Sensitivity(
                    "cover_price",
                    "breakeven",
                    Measure(p_contract, unit),
                    f"No extra cost at {grouped(p_contract, 2)} {unit}",
                ),
            ),
            expires_at_utc=end,
            deadline_utc=max(start, now),
            inputs=inputs,
            evaluator=self.name,
            evaluator_version=self.version,
        )


EVENT_EXPOSURE = register(EventExposureEvaluator())
