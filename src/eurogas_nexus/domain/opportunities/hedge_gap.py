"""Type G: hedge cover outside its approved band (design basis 2, B.3; reference evaluator).

For each contract with a band approved by risk, and each remaining month, the cover the
linked trades give is compared with the band: ``gap = band_edge - cover`` (below the band)
or ``gap = cover - band_edge`` (above it), in MWh, where ``band_edge = band % x |contract
volume of the month|`` and ``cover = hedge % x |contract volume|``. It needs no market data:
the inputs are the book (contract volume, linked trades, the approved band).

Worked example (design B.4): contract "Norsk-2027", Q1-27 month, contract volume 300,000 MWh,
cover 126,000 MWh (42 %), approved band 60-80 %: band edge 60 % x 300,000 = 180,000 MWh;
gap 180,000 - 126,000 = 54,000 MWh below the band. No margin is claimed: it is an
obligation, listed in the must-act lane, due when the month's delivery starts.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date
from eurogas_nexus.domain.opportunities.claims import grouped, period_label
from eurogas_nexus.domain.opportunities.evaluator import EvaluationContext, register
from eurogas_nexus.domain.opportunities.model import (
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
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod, PeriodError
from eurogas_nexus.domain.valuation.snapshot import SnapshotInput, SnapshotReader

_TENTH = Decimal("0.1")
_HUNDRED = Decimal(100)


def _dec(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _band_text(low: Decimal | None, high: Decimal | None) -> str:
    if low is not None and high is not None:
        return f"{grouped(low)}–{grouped(high)} %"
    if low is not None:
        return f"at least {grouped(low)} %"
    return f"at most {grouped(high)} %"


class HedgeGapEvaluator:
    """Cover per contract and month against the approved hedge band."""

    name = "hedge_gap"
    version = "1"
    type = OpportunityType.HEDGE_GAP

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """One candidate per contract-month outside its band."""

        for row in snapshot.hedge_cover():
            candidate = self._month(row, context)
            if candidate is not None:
                yield candidate

    def _month(self, row: SnapshotInput, context: EvaluationContext) -> Candidate | None:
        detail = row.detail
        volume = _dec(detail.get("contract_mwh"))
        hedged = _dec(detail.get("hedged_mwh"))
        low = _dec(detail.get("band_low_pct"))
        high = _dec(detail.get("band_high_pct"))
        if volume is None or hedged is None or volume == 0 or (low is None and high is None):
            return None
        try:
            period = DeliveryPeriod.parse(str(detail.get("month")))
        except PeriodError:
            return None
        exposure = abs(volume)
        # Offsetting cover in MWh (positive when the trades hedge the contract).
        cover = (hedged if volume > 0 else -hedged).quantize(_TENTH)
        cover_pct = cover / exposure * _HUNDRED
        if low is not None and cover_pct < low:
            side, edge_pct = "below", low
        elif high is not None and cover_pct > high:
            side, edge_pct = "above", high
        else:
            return None
        edge = (edge_pct / _HUNDRED * exposure).quantize(_TENTH)
        contract = str(detail.get("contract_name") or detail.get("contract_id"))
        common = {
            "input_class": row.input_class,
            "source_family": row.source_family,
            "source_ref": row.source_ref,
            "as_of_utc": row.as_of_utc,
            "input_keys": (row.key,),
        }
        edge_leg = Leg(
            kind=LegKind.TERM,
            label_key="hedge_gap.band_edge",
            label=f"Band edge: {grouped(edge_pct)} % of {grouped(exposure)} MWh",
            label_params={"pct": grouped(edge_pct), "mwh": grouped(exposure)},
            quantity=Measure(exposure, "MWh"),
            rate=Measure(edge_pct, "%"),
            contribution=Measure(edge if side == "below" else -edge, "MWh"),
            **common,
        )
        trades = int(detail.get("linked_trades") or 0)
        cover_leg = Leg(
            kind=LegKind.TERM,
            label_key="hedge_gap.cover_held",
            label=f"Cover held: {trades} linked trade(s), {grouped(cover_pct)} %",
            label_params={"trades": str(trades), "pct": grouped(cover_pct)},
            quantity=Measure(cover, "MWh"),
            rate=Measure(cover_pct.quantize(_TENTH), "%"),
            contribution=Measure(-cover if side == "below" else cover, "MWh"),
            **common,
        )
        gap = (edge - cover) if side == "below" else (cover - edge)
        terms = [edge_leg, cover_leg] if side == "below" else [cover_leg, edge_leg]
        result = Leg(
            kind=LegKind.RESULT,
            label_key=f"hedge_gap.{side}_band",
            label=f"{'Below' if side == 'below' else 'Above'} the band edge",
            subtotal=Measure(gap, "MWh"),
        )
        valid_until = detail.get("valid_until")
        approved_by = str(detail.get("approved_by") or "risk")
        ref = detail.get("approval_ref")
        start = gas_day_start_for_date(period.start)
        months = period_label(period.label)
        return Candidate(
            type=self.type,
            identity=(f"contract:{detail.get('contract_id')}", f"side:{side}"),
            period=period,
            book_ids=tuple(item for item in (detail.get("book_id"),) if item),
            claim_key=f"hedge_gap.{side}_band",
            claim_fields={
                "contract": contract,
                "period": months,
                "cover_pct": grouped(cover_pct),
                "band": _band_text(low, high),
                "gap_mwh": grouped(gap),
                "approved_by": approved_by,
                "approval_ref": f" (ref {ref})" if ref else "",
            },
            headline=Measure(gap, "MWh"),
            volume=Measure(gap, "MWh"),
            legs=(*terms, result),
            falsifiers=(
                Falsifier(
                    "hedge_gap.cover_reaches_edge",
                    f"Cover for {months} reaches {grouped(edge)} MWh "
                    f"({grouped(edge_pct)} % of {grouped(exposure)} MWh).",
                ),
                Falsifier(
                    "hedge_gap.band_changed",
                    f"The approved band for {contract} is changed or withdrawn.",
                ),
                Falsifier(
                    "hedge_gap.volume_changed",
                    f"The contract volume for {months} differs from {grouped(exposure)} MWh.",
                ),
            ),
            sensitivity=(
                Sensitivity(
                    "band_edge",
                    "per_unit",
                    Measure((exposure / _HUNDRED).quantize(_TENTH), "MWh"),
                    f"1 percentage point of band = {grouped(exposure / _HUNDRED)} MWh",
                ),
                Sensitivity(
                    "cover",
                    "breakeven",
                    Measure(edge, "MWh"),
                    f"Cover at which the gap closes: {grouped(edge)} MWh",
                ),
            ),
            checks=(
                Check(
                    CheckKind.CONTRACT,
                    CheckResult.PASS,
                    f"approved band valid until {valid_until}"
                    if valid_until
                    else "approved band has no end date",
                    reference=str(row.source_ref),
                ),
                Check(
                    CheckKind.MANDATE,
                    CheckResult.NOT_ASSESSED,
                    "mandate headroom for the volume that closes the gap is not assessed",
                ),
            ),
            expires_at_utc=gas_day_start_for_date(period.end),
            deadline_utc=start,
            inputs=(row,),
            evaluator=self.name,
            evaluator_version=self.version,
            extra={"contract_id": detail.get("contract_id"), "hub": detail.get("hub")},
        )


HEDGE_GAP = register(HedgeGapEvaluator())
