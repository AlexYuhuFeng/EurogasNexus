"""Ranking within the two lanes and the one-line ranking reason (design B.5).

- **Must act** (hedge gap, event exposure, sell-down): by time to deadline, then size.
- **Could act** (margin types): ``score = value_in_EUR x quality_weight x
  persistence_weight``, ties by earliest expiry. A simulated opportunity is ranked only
  among simulated ones (after every real one).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from eurogas_nexus.domain.opportunities.claims import grouped
from eurogas_nexus.domain.opportunities.model import Lane
from eurogas_nexus.domain.valuation.quality import CLASS_LABEL, InputClass

#: B.5 quality weights (organisation settings later; defaults here).
QUALITY_WEIGHT: dict[InputClass, Decimal] = {
    InputClass.SOURCED: Decimal("1.0"),
    InputClass.DERIVED: Decimal("1.0"),
    InputClass.FIRM_MARK: Decimal("1.0"),
    InputClass.INDICATIVE: Decimal("0.6"),
    InputClass.ASSUMPTION: Decimal("0.4"),
    InputClass.SIMULATED: Decimal("1.0"),
    InputClass.MISSING: Decimal("0"),
}


def persistence_weight(consecutive_seen: int) -> Decimal:
    """Seen in one evaluation 0.5; two or more consecutive 1.0."""

    return Decimal("1.0") if consecutive_seen >= 2 else Decimal("0.5")


@dataclass(frozen=True)
class RankInput:
    """What ranking needs from one listed opportunity."""

    opportunity_id: str
    lane: Lane
    quality: InputClass
    simulated: bool
    consecutive_seen: int
    expires_at_utc: datetime
    deadline_utc: datetime | None
    value_eur: Decimal | None
    size: Decimal  # |headline| for must act (volume or money), |value| otherwise
    size_unit: str
    #: The market lane's order: the edge net of every cost, EUR/MWh (value beside it).
    edge_eur_mwh: Decimal | None = None


@dataclass(frozen=True)
class Ranked:
    """One ranked row: position (1-based), score and the reason line."""

    opportunity_id: str
    position: int
    score: Decimal | None
    reason: str


def score(item: RankInput) -> Decimal:
    """``value x quality_weight x persistence_weight`` (could act)."""

    value = item.value_eur or Decimal(0)
    return value * QUALITY_WEIGHT[item.quality] * persistence_weight(item.consecutive_seen)


def _ordinal(position: int) -> str:
    suffix = (
        "th" if 10 <= position % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(position % 10, "th")
    )
    return f"{position}{suffix}"


def _when(moment: datetime | None, now: datetime, word: str) -> str:
    if moment is None:
        return "no deadline"
    days = (moment - now).total_seconds() / 86_400
    if days < 0:
        return f"{word} passed {int(-days)} d ago" if days <= -1 else f"{word} passed today"
    if days < 1:
        return f"{word} today"
    return f"{word} in {int(days)} d"


def _quality_words(quality: InputClass, simulated: bool) -> str:
    if simulated:
        return "simulated inputs"
    if quality in {InputClass.SOURCED, InputClass.DERIVED}:
        return "all inputs sourced"
    return f"weakest input: {CLASS_LABEL[quality]}"


def rank(items: Iterable[RankInput], now_utc: datetime) -> list[Ranked]:
    """Rank one lane's rows; each lane is ranked separately (the lanes never mix)."""

    rows: Sequence[RankInput] = list(items)
    if not rows:
        return []
    lane = rows[0].lane
    if any(item.lane is not lane for item in rows):
        raise ValueError("one lane at a time")
    if lane is Lane.MUST_ACT:
        far = datetime.max.replace(tzinfo=now_utc.tzinfo)
        ordered = sorted(
            rows,
            key=lambda item: (
                item.simulated,
                item.deadline_utc or far,
                -item.size,
                item.opportunity_id,
            ),
        )
    elif lane is Lane.MARKET:
        ordered = sorted(
            rows,
            key=lambda item: (
                item.simulated,
                -(item.edge_eur_mwh if item.edge_eur_mwh is not None else Decimal(0)),
                -score(item),
                item.expires_at_utc,
                item.opportunity_id,
            ),
        )
    else:
        ordered = sorted(
            rows,
            key=lambda item: (
                item.simulated,
                -score(item),
                item.expires_at_utc,
                item.opportunity_id,
            ),
        )
    out = []
    for position, item in enumerate(ordered, start=1):
        if lane is Lane.MUST_ACT:
            reason = (
                f"ranked {_ordinal(position)}: {_when(item.deadline_utc, now_utc, 'due')}, "
                f"{grouped(item.size)} {item.size_unit}, "
                f"{_quality_words(item.quality, item.simulated)}"
            )
            out.append(Ranked(item.opportunity_id, position, None, reason))
        else:
            value = item.value_eur or Decimal(0)
            edge = (
                f"{grouped(item.edge_eur_mwh, 3)} EUR/MWh net, "
                if lane is Lane.MARKET and item.edge_eur_mwh is not None
                else ""
            )
            reason = (
                f"ranked {_ordinal(position)}: {edge}EUR {grouped(value / 1000)}k, "
                f"{_quality_words(item.quality, item.simulated)}, "
                f"{_when(item.expires_at_utc, now_utc, 'expires')}"
            )
            out.append(Ranked(item.opportunity_id, position, score(item), reason))
    return out
