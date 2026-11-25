"""Why a gas day's trades, confirmations and nominations disagree (SCHED-1), pure.

The scheduler's daily reconciliation, per gas day, hub (point) and counterparty:

- **traded**: the bilateral deals delivering on the gas day (the book of record), signed
  ``in`` (the firm receives: a purchase) positive, ``out`` negative;
- **confirmed**: the part of it the counterparty has confirmed, where confirmation statuses
  are imported (``trade_confirmation`` steps);
- **nominated**: what the scheduling system nominated against that counterparty;
- **TSO**: what the TSO matched and confirmed, where its response is imported, and the
  counterparty's own nominated quantity where the matching report gives it.

Three layers of comparison, each break named once with its arithmetic in plain words and the
next thing to check:

1. *deal against counterparty*: a deal the counterparty has not confirmed or disputes
   (``not_confirmed``);
2. *book against nomination*: per nomination that names a deal, the wrong counterparty
   (``counterparty_mismatch``) or the wrong direction (``wrong_direction``); then the rest of
   the group, net: nothing nominated (``not_nominated``), a nomination with no deal
   (``nomination_without_trade``), a quantity in another unit (``unit_mismatch``), a deal or
   nomination on another gas day or outside the 06:00-06:00 CET gas day
   (``gas_day_misaligned``), deals booked after the last nomination (``late``), else a
   quantity difference (``quantity_mismatch``, in MWh and kWh/h);
3. *nomination against the TSO*: a counterparty shipper code the TSO did not match
   (``shipper_code_mismatch``), the lesser rule cutting the nomination to the counterparty's
   quantity (``lesser_rule_cut``), and a nomination recorded after the deadline it was due by
   (``late``).

Each break carries the MWh it puts at risk and its signed effect on the firm's balance at the
hub (long positive), so a caller can value it at a cash-out rate. Nothing here nominates or
sends anything (AGENTS.md rule 8).

调度对账（SCHED-1，纯函数）：按燃气日、枢纽与交易对手比较交易、对手确认、提名与TSO匹配结果，
逐项说明差异原因与算式及下一步检查事项；不提交任何提名。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

IN, OUT = "in", "out"
#: Below this a difference is rounding, not a break (MWh for the gas day).
TOLERANCE_MWH = 1.0
#: The break kinds, in the order a scheduler reads them.
KINDS = (
    "not_nominated",
    "nomination_without_trade",
    "quantity_mismatch",
    "counterparty_mismatch",
    "shipper_code_mismatch",
    "wrong_direction",
    "lesser_rule_cut",
    "late",
    "unit_mismatch",
    "gas_day_misaligned",
    "not_confirmed",
)
#: 1 MWh in therms (``domain/market/units``: 1 MWh = 34.1214163 th).
THERM_PER_MWH = 34.1214163
#: A cut-off this close (or passed with the gas day still running) is "due soon".
DUE_SOON = timedelta(hours=3)
#: Within this the break is critical.
IMMINENT = timedelta(hours=1)


# ----------------------------------------------------------------------------- facts


@dataclass(frozen=True)
class TradeFact:
    """One bilateral deal's share of the gas day."""

    trade_id: str
    deal_ref: str
    hub: str
    counterparty: str
    direction: str  # in (buy) | out (sell)
    mwh: float  # this gas day's quantity, positive
    first_day: date
    last_day: date
    traded_at: datetime | None = None
    book_id: str = ""
    #: The day's quantity is a pro-rated part of a delivery that does not start or end on
    #: the gas day's 06:00 CET boundary (``hours_in_day`` of the gas day fall in it).
    misaligned: bool = False
    hours_in_day: float | None = None
    #: The counterparty's confirmation as imported: confirmed, sent (awaiting),
    #: mismatch_queried (disputed); None when none is held.
    confirmation: str | None = None
    confirmation_at: datetime | None = None
    confirmation_by: str | None = None
    simulated: bool = False

    @property
    def signed(self) -> float:
        return self.mwh if self.direction == IN else -self.mwh


@dataclass(frozen=True)
class NominationFact:
    """One nominated line of one gas day, from its newest recorded statuses."""

    gas_day: date
    line_ref: str
    hub: str
    #: The deal the line names (``trade:<id>``), resolved; None for a counterparty-level line.
    trade_id: str | None = None
    #: The named deal's first and last gas day, when it does not deliver on ``gas_day``.
    trade_days: tuple[date, date] | None = None
    counterparty: str | None = None
    direction: str | None = None
    point: str | None = None
    shipper_code: str | None = None
    counterparty_shipper_code: str | None = None
    step: str = "nomination"
    #: The newest status of the line.
    status: str = "sent"
    nominated_mwh: float | None = None
    nominated_at: datetime | None = None
    #: The TSO's matched (confirmed) quantity after the newest nomination; None when no
    #: response is held. ``tso_status``: confirmed, mismatch, awaiting, not_sent.
    tso_mwh: float | None = None
    tso_status: str = "awaiting"
    tso_at: datetime | None = None
    #: The counterparty's own nominated quantity, as the TSO's matching reported it.
    counterparty_mwh: float | None = None
    book_id: str | None = None
    recorded_by: str | None = None
    source_system: str | None = None
    simulated: bool = False


@dataclass(frozen=True)
class CutoffFact:
    key: str  # nomination | last_renomination | window | gas_day_end
    at_utc: datetime
    basis: str
    source: str
    name: str | None = None


@dataclass
class Break:
    kind: str
    hub: str
    point: str | None
    counterparty: str
    mwh_at_risk: float
    #: Signed effect on the firm's balance at the hub (long positive); None: no imbalance
    #: follows from it by itself (a confirmation still open).
    gap_mwh: float | None
    text_en: str
    text_zh: str
    next_en: str
    next_zh: str
    trade_ids: tuple[str, ...] = ()
    line_refs: tuple[str, ...] = ()
    figures: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.hub}:{self.point or ''}:{counterparty_key(self.counterparty)}:{self.kind}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "hub": self.hub,
            "point": self.point,
            "counterparty": self.counterparty,
            "mwh_at_risk": round(self.mwh_at_risk, 1),
            "gap_mwh": None if self.gap_mwh is None else round(self.gap_mwh, 1),
            "explanation": self.text_en,
            "explanation_zh": self.text_zh,
            "next_step": self.next_en,
            "next_step_zh": self.next_zh,
            "trade_ids": list(self.trade_ids),
            "line_refs": list(self.line_refs),
            "figures": self.figures,
        }


@dataclass
class Group:
    """One hub, point and counterparty of the gas day."""

    hub: str
    point: str | None
    counterparty: str
    trades: list[TradeFact] = field(default_factory=list)
    nominations: list[NominationFact] = field(default_factory=list)
    breaks: list[Break] = field(default_factory=list)

    @property
    def traded_mwh(self) -> float:
        return sum(t.signed for t in self.trades)

    @property
    def confirmed_mwh(self) -> float | None:
        if not any(t.confirmation for t in self.trades):
            return None
        return sum(t.signed for t in self.trades if t.confirmation == "confirmed")

    @property
    def nominated_mwh(self) -> float | None:
        held = [n for n in self.nominations if n.nominated_mwh is not None]
        if not held:
            return None
        return sum(_sign(self, n) * float(n.nominated_mwh or 0.0) for n in held)

    @property
    def tso_mwh(self) -> float | None:
        held = [n for n in self.nominations if n.tso_mwh is not None]
        if not held:
            return None
        return sum(_sign(self, n) * float(n.tso_mwh or 0.0) for n in held)

    @property
    def shipper_codes(self) -> list[str]:
        return sorted({n.counterparty_shipper_code for n in self.nominations
                       if n.counterparty_shipper_code})

    @property
    def mwh_at_risk(self) -> float:
        return max((b.mwh_at_risk for b in self.breaks), default=0.0)


# ----------------------------------------------------------------------------- words


def counterparty_key(name: str | None) -> str:
    """A counterparty name compared without case, spaces or punctuation."""

    return re.sub(r"[^0-9a-z]+", "", str(name or "").casefold())


def _sign(group: Group | None, nomination: NominationFact) -> float:
    direction = nomination.direction
    if direction is None and nomination.trade_id and group is not None:
        trade = next((t for t in group.trades if t.trade_id == nomination.trade_id), None)
        direction = trade.direction if trade else None
    if direction is None and group is not None:
        direction = OUT if group.traded_mwh < 0 else IN
    return 1.0 if direction == IN else -1.0


def _q(mwh: float, hub: str) -> str:
    text = f"{abs(mwh):,.0f} MWh"
    if hub.upper() == "NBP":
        text += f" ({abs(mwh) * THERM_PER_MWH:,.0f} th)"
    return text


def _qzh(mwh: float, hub: str) -> str:
    text = f"{abs(mwh):,.0f} MWh"
    if hub.upper() == "NBP":
        text += f"（{abs(mwh) * THERM_PER_MWH:,.0f} 撒姆）"
    return text


def _kwh_h(mwh: float, hours: float) -> float:
    return mwh * 1000.0 / hours if hours else 0.0


def _at(moment: datetime | None) -> str:
    return "time not held" if moment is None else f"{moment:%d %b %H:%M} UTC"


def _at_zh(moment: datetime | None) -> str:
    return "时间未记录" if moment is None else f"{moment:%m-%d %H:%M} UTC"


def _side(direction: str) -> str:
    return "purchase" if direction == IN else "sale"


def _side_zh(direction: str) -> str:
    return "买入" if direction == IN else "卖出"


def _way(direction: str, counterparty: str) -> str:
    return f"in from {counterparty}" if direction == IN else f"out to {counterparty}"


def _way_zh(direction: str, counterparty: str) -> str:
    return f"自{counterparty}流入" if direction == IN else f"向{counterparty}流出"


def _state(gap: float) -> str:
    return "long" if gap > 0 else "short"


def _state_zh(gap: float) -> str:
    return "多头" if gap > 0 else "空头"


def _deals(trades: Sequence[TradeFact]) -> str:
    refs = [t.deal_ref for t in trades][:4]
    more = len(trades) - len(refs)
    return ", ".join(refs) + (f" and {more} more" if more > 0 else "")


#: Quantity read in the wrong unit: (factor nominated/traded, words, words in Chinese).
def _unit_factors(hours: float) -> list[tuple[float, str, str]]:
    return [
        (hours, "a MWh/d quantity sent as MW (MWh per hour), or the reverse",
         "MWh/d 数量按 MW（每小时 MWh）填报，或相反"),
        (1000.0, "kWh read as MWh", "kWh 被当作 MWh"),
        (1000.0 / hours, "kWh/h read as MWh/d", "kWh/h 被当作 MWh/d"),
        (THERM_PER_MWH, "therms read as MWh", "撒姆被当作 MWh"),
        (1000.0 * hours, "MWh/d sent as kWh/h figures in a MWh field",
         "MWh/d 按 kWh/h 填入 MWh 字段"),
    ]


def unit_factor(
    nominated: float, traded: float, hours: float
) -> tuple[float, str, str, bool] | None:
    """The unit slip that turns ``traded`` into ``nominated`` (within 1 %), if any: the
    factor, its words and whether the nomination is the larger (``True``) or smaller."""

    nominated, traded = abs(nominated), abs(traded)
    if nominated <= 0 or traded <= 0:
        return None
    ratio = nominated / traded
    for factor, words, words_zh in _unit_factors(hours):
        if abs(ratio - factor) <= factor * 0.01:
            return factor, words, words_zh, True
        if abs(1.0 / ratio - factor) <= factor * 0.01:
            return factor, words, words_zh, False
    return None


# ----------------------------------------------------------------------------- cut-offs


def next_cutoff(cutoffs: Iterable[CutoffFact], now: datetime) -> CutoffFact | None:
    """The next cut-off a nomination or renomination can still meet (not the day's end)."""

    ahead = [cut for cut in cutoffs if cut.key != "gas_day_end" and cut.at_utc > now]
    return min(ahead, key=lambda cut: cut.at_utc) if ahead else None


def urgency(cutoffs: Sequence[CutoffFact], now: datetime) -> dict[str, Any]:
    """How long is left to fix a break at this hub on this gas day.

    ``due_soon`` within :data:`DUE_SOON` of the next cut-off; ``open`` further away;
    ``passed`` when no renomination is left but the gas day still runs (the difference will
    be cashed out); ``closed`` once the gas day has ended. ``severity`` is ``critical``
    within :data:`IMMINENT` or once passed, ``warning`` when due soon, else ``info``.
    """

    cut = next_cutoff(cutoffs, now)
    end = next((c.at_utc for c in cutoffs if c.key == "gas_day_end"), None)
    if cut is None:
        bucket = "closed" if end is not None and end <= now else "passed"
        return {"bucket": bucket, "cutoff": None, "minutes_left": None,
                "severity": "critical" if bucket == "passed" else "info"}
    left = cut.at_utc - now
    bucket = "due_soon" if left <= DUE_SOON else "open"
    severity = "critical" if left <= IMMINENT else "warning" if bucket == "due_soon" else "info"
    return {
        "bucket": bucket,
        "cutoff": {"key": cut.key, "name": cut.name, "at_utc": cut.at_utc.isoformat(),
                   "basis": cut.basis, "source": cut.source},
        "minutes_left": int(left.total_seconds() // 60),
        "severity": severity,
    }


BUCKET_RANK = {"due_soon": 0, "open": 1, "passed": 2, "closed": 3}


def _deadline_words(cut: CutoffFact | None) -> tuple[str, str]:
    if cut is None:
        return ("no renomination is left for this gas day: the difference will be cashed out",
                "本燃气日已无再提名窗口：差额将按不平衡结算")
    label = {"nomination": "the nomination deadline",
             "last_renomination": "the last renomination"}.get(cut.key, cut.name or "the window")
    label_zh = {"nomination": "提名截止", "last_renomination": "最后一次再提名"}.get(
        cut.key, cut.name or "窗口")
    return f"before {label} at {_at(cut.at_utc)}", f"于{label_zh}（{_at_zh(cut.at_utc)}）之前"


# ----------------------------------------------------------------------------- grouping


def group_facts(trades: Iterable[TradeFact], nominations: Iterable[NominationFact]
                ) -> list[Group]:
    """Deals by hub and counterparty; a nomination that names a deal joins the deal's group
    (so a wrong counterparty on it is one break, not two), any other by its own hub, point
    and counterparty ("counterparty not held" when the line names none)."""

    groups: dict[tuple[str, str, str], Group] = {}
    by_trade: dict[str, tuple[str, str, str]] = {}
    for trade in trades:
        key = (trade.hub, "", counterparty_key(trade.counterparty))
        group = groups.setdefault(key, Group(trade.hub, None, trade.counterparty))
        group.trades.append(trade)
        by_trade[trade.trade_id] = key
    for nomination in nominations:
        key = by_trade.get(nomination.trade_id or "")
        if key is None:
            name = nomination.counterparty or "counterparty not held"
            key = (nomination.hub, nomination.point or "", counterparty_key(name))
            groups.setdefault(key, Group(nomination.hub, nomination.point, name))
        groups[key].nominations.append(nomination)
    return list(groups.values())


# ----------------------------------------------------------------------------- reconcile


def reconcile(
    gas_day: date,
    trades: Sequence[TradeFact],
    nominations: Sequence[NominationFact],
    *,
    hours: float = 24.0,
    cutoffs: dict[str, Sequence[CutoffFact]] | None = None,
    adjacent: Sequence[NominationFact] = (),
    tolerance_mwh: float = TOLERANCE_MWH,
    now: datetime | None = None,
) -> list[Group]:
    """Every group of the gas day with its breaks (``Group.breaks``).

    ``nominations`` are the lines of ``gas_day``; ``adjacent`` the lines of the day before
    and after (a deal nominated on the wrong gas day, and the shipper codes the TSO matched
    for a counterparty); ``cutoffs`` per hub, for the deadline a nomination was due by and the
    next step's words.
    """

    cutoffs = cutoffs or {}
    groups = group_facts(trades, nominations)
    matched_codes = _matched_codes([*nominations, *adjacent], tolerance_mwh)
    for group in groups:
        cuts = list(cutoffs.get(group.hub, ()))
        _check(gas_day, group, hours, cuts, adjacent, matched_codes, tolerance_mwh, now)
    return groups


def _matched_codes(nominations: Iterable[NominationFact], tolerance: float
                   ) -> dict[tuple[str, str], set[str]]:
    """Counterparty shipper codes the TSO matched, per hub and counterparty."""

    out: dict[tuple[str, str], set[str]] = {}
    for n in nominations:
        if (n.counterparty_shipper_code and n.counterparty and n.tso_mwh is not None
                and n.tso_mwh > tolerance):
            out.setdefault((n.hub, counterparty_key(n.counterparty)), set()).add(
                n.counterparty_shipper_code)
    return out


def _deadline(cuts: Sequence[CutoffFact], key: str) -> CutoffFact | None:
    return next((cut for cut in cuts if cut.key == key), None)


def _check(gas_day: date, group: Group, hours: float, cuts: list[CutoffFact],
           adjacent: Sequence[NominationFact], matched_codes, tolerance: float,
           now: datetime | None) -> None:
    hub, cpty = group.hub, group.counterparty
    trades = {t.trade_id: t for t in group.trades}
    consumed_trades: set[str] = set()
    consumed_noms: set[str] = set()
    # The next step names the next cut-off still ahead at ``now`` (none: cashed out).
    if now is not None:
        next_cut = next_cutoff(cuts, now)
    else:
        next_cut = next((c for c in cuts if c.key != "gas_day_end"), None)
    deadline_en, deadline_zh = _deadline_words(next_cut)

    def add(kind, mwh, gap, en, zh, next_en, next_zh, trade_ids=(), refs=(), **figures):
        group.breaks.append(Break(kind, hub, group.point, cpty, abs(mwh), gap, en, zh,
                                  next_en, next_zh, tuple(trade_ids), tuple(refs), figures))

    # 1. deal against counterparty confirmation
    for t in group.trades:
        if t.confirmation in ("sent", "mismatch_queried", "to_send"):
            disputed = t.confirmation == "mismatch_queried"
            add("not_confirmed", t.mwh, None,
                f"Deal {t.deal_ref} ({_side(t.direction)} of {_q(t.mwh, hub)} for the day with "
                f"{cpty}) is {'disputed by' if disputed else 'not yet confirmed by'} {cpty}"
                f" (confirmation {'queried' if disputed else 'sent'} {_at(t.confirmation_at)}). "
                "A nomination against an unconfirmed deal may not be matched.",
                f"交易 {t.deal_ref}（与{cpty}当日{_side_zh(t.direction)}{_qzh(t.mwh, hub)}）"
                f"{'被对手提出异议' if disputed else '尚未获对手确认'}"
                f"（确认{'有疑问' if disputed else '已发送'}于 {_at_zh(t.confirmation_at)}）。"
                "未确认交易的提名可能无法匹配。",
                f"Chase {cpty}'s confirmation of {t.deal_ref} with the back office "
                f"{deadline_en}, and check the deal's quantity, price and dates with the trader.",
                f"{deadline_zh}请后台跟进{cpty}对 {t.deal_ref} 的确认，并与交易员核对数量、价格与日"
                f"期。",
                trade_ids=[t.trade_id], confirmation=t.confirmation,
                confirmation_by=t.confirmation_by)

    # 2a. per nomination that names a deal: counterparty and direction
    for n in group.nominations:
        t = trades.get(n.trade_id or "")
        if t is None or n.nominated_mwh is None:
            continue
        q = float(n.nominated_mwh)
        if n.counterparty and counterparty_key(n.counterparty) != counterparty_key(t.counterparty):
            flow = 0.0 if n.tso_mwh is None else float(n.tso_mwh)
            add("counterparty_mismatch", t.mwh, (flow * (1 if t.direction == IN else -1))
                - t.signed,
                f"Deal {t.deal_ref} is with {t.counterparty}, but its nomination "
                f"({n.line_ref}) names {n.counterparty}: {_q(q, hub)} nominated against the "
                f"wrong counterparty, so {t.counterparty}'s side finds nothing to match and "
                f"the {_side(t.direction)} of {_q(t.mwh, hub)} will not flow.",
                f"交易 {t.deal_ref} 的对手为{t.counterparty}，但其提名（{n.line_ref}）写的是"
                f"{n.counterparty}：{_qzh(q, hub)} 提名给了错误的对手，{t.counterparty}一方无法匹配"
                f"，"
                f"当日{_side_zh(t.direction)}{_qzh(t.mwh, hub)} 将不会交割。",
                f"Renominate {_q(t.mwh, hub)} {_way(t.direction, t.counterparty)} and withdraw "
                f"the line against {n.counterparty} {deadline_en}.",
                f"{deadline_zh}重新提名{_qzh(t.mwh, hub)}（{_way_zh(t.direction, t.counterparty)}）"
                f"，"
                f"并撤回对{n.counterparty}的提名。",
                trade_ids=[t.trade_id], refs=[n.line_ref],
                nominated_counterparty=n.counterparty)
            consumed_trades.add(t.trade_id)
            consumed_noms.add(n.line_ref)
            continue
        if n.direction and n.direction != t.direction:
            signed_nom = q if n.direction == IN else -q
            gap = signed_nom - t.signed
            add("wrong_direction", gap, gap,
                f"Deal {t.deal_ref} is a {_side(t.direction)} ({t.direction.upper()}) of "
                f"{_q(t.mwh, hub)} with {cpty}, but it was nominated {n.direction.upper()}: "
                f"the firm's balance moves by {signed_nom:+,.0f} − ({t.signed:+,.0f}) = "
                f"{gap:+,.0f} MWh, {_state(gap)} {_q(gap, hub)}.",
                f"交易 {t.deal_ref} 为{_side_zh(t.direction)}（{t.direction.upper()}）"
                f"{_qzh(t.mwh, hub)}，但提名方向为 {n.direction.upper()}：平衡变动 "
                f"{signed_nom:+,.0f} − ({t.signed:+,.0f}) = {gap:+,.0f} MWh，"
                f"{_state_zh(gap)}{_qzh(gap, hub)}。",
                f"Renominate the line {t.direction.upper()} ({_way(t.direction, cpty)}) "
                f"{deadline_en}.",
                f"{deadline_zh}将该提名改为 {t.direction.upper()}（{_way_zh(t.direction, cpty)}）"
                f"。",
                trade_ids=[t.trade_id], refs=[n.line_ref], nominated_direction=n.direction,
                traded_direction=t.direction)
            consumed_trades.add(t.trade_id)
            consumed_noms.add(n.line_ref)

    # 2b. the rest of the group, net
    rest_t = [t for t in group.trades if t.trade_id not in consumed_trades]
    rest_n = [n for n in group.nominations if n.line_ref not in consumed_noms]
    held_n = [n for n in rest_n if n.nominated_mwh is not None and n.nominated_mwh > 0]
    traded = sum(t.signed for t in rest_t)
    nominated = sum(_sign(group, n) * float(n.nominated_mwh or 0.0) for n in held_n)
    delta = nominated - traded
    if abs(delta) > tolerance:
        _book_break(gas_day, group, add, rest_t, held_n, traded, nominated, delta, hours,
                    adjacent, deadline_en, deadline_zh, tolerance, cuts)

    # 3. nomination against the TSO
    for n in rest_n:
        if n.nominated_mwh is None or n.tso_mwh is None:
            continue
        nominated_q, matched = float(n.nominated_mwh), float(n.tso_mwh)
        cut = nominated_q - matched
        if cut <= tolerance:
            continue
        sign = _sign(group, n)
        known = matched_codes.get((hub, counterparty_key(n.counterparty or cpty)), set())
        code = n.counterparty_shipper_code
        if code and known and code not in known:
            add("shipper_code_mismatch", cut, -sign * cut,
                f"The nomination {n.line_ref} names {cpty}'s shipper code {code}, but the TSO "
                f"matched {cpty} under {', '.join(sorted(known))} elsewhere: it matched "
                f"{_q(matched, hub)} of the {_q(nominated_q, hub)} nominated, "
                f"{_q(cut, hub)} not flowing.",
                f"提名 {n.line_ref} 使用的{cpty}托运人代码为 {code}，而 TSO 在其他提名中以 "
                f"{'、'.join(sorted(known))} 匹配{cpty}：所提名 {_qzh(nominated_q, hub)} 中仅匹配 "
                f"{_qzh(matched, hub)}，{_qzh(cut, hub)} 不会交割。",
                f"Check {cpty}'s shipper code in the scheduling system's counterparty data and "
                f"renominate under {sorted(known)[0]} {deadline_en}.",
                f"核对调度系统中{cpty}的托运人代码，并{deadline_zh}以 {sorted(known)[0]} 重新提名"
                f"。",
                trade_ids=[n.trade_id] if n.trade_id else [], refs=[n.line_ref],
                nominated_code=code, matched_codes=sorted(known),
                nominated_mwh=round(nominated_q, 1), matched_mwh=round(matched, 1))
            continue
        other = n.counterparty_mwh
        if other is not None and abs(float(other) - matched) <= tolerance:
            why_en = (f"{cpty} nominated {_q(float(other), hub)}, so the TSO's lesser rule "
                      f"confirmed the smaller of {nominated_q:,.0f} and {float(other):,.0f}")
            why_zh = (f"{cpty}仅提名 {_qzh(float(other), hub)}，"
                      f"TSO 按较小值规则在 {nominated_q:,.0f} 与 {float(other):,.0f} 中确认较小者")
        else:
            why_en = ("the counterparty's quantity is not in the TSO's response; the usual "
                      "cause is the lesser rule against a smaller counterparty nomination")
            why_zh = "TSO 回复未给出对手的提名量；通常原因是对手提名较小、按较小值规则确认"
        add("lesser_rule_cut", cut, -sign * cut,
            f"Nominated {_q(nominated_q, hub)} {_way('in' if sign > 0 else 'out', cpty)}; the TSO "
            f"confirmed {_q(matched, hub)} ({_at(n.tso_at)}): {nominated_q:,.0f} − "
            f"{matched:,.0f} = {cut:,.0f} MWh cut; {why_en}. The firm is "
            f"{_state(-sign * cut)} {_q(cut, hub)} unless fixed.",
            f"已提名 {_qzh(nominated_q, hub)}（{_way_zh('in' if sign > 0 else 'out', cpty)}），TSO "
            f"确认 "
            f"{_qzh(matched, hub)}（{_at_zh(n.tso_at)}）：{nominated_q:,.0f} − {matched:,.0f} = "
            f"{cut:,.0f} MWh 被削减；{why_zh}。如不处理，公司将{_state_zh(-sign * cut)}"
            f"{_qzh(cut, hub)}。",
            f"Call {cpty}'s scheduler to agree the quantity and both renominate "
            f"{deadline_en}; if {cpty} is short on the deal, tell the trader.",
            f"致电{cpty}调度确认数量，双方{deadline_zh}重新提名；如对手履约不足，请告知交易员。",
            trade_ids=[n.trade_id] if n.trade_id else [], refs=[n.line_ref],
            nominated_mwh=round(nominated_q, 1), matched_mwh=round(matched, 1),
            counterparty_mwh=None if other is None else round(float(other), 1))

    # 3b. a nomination recorded after the deadline it was due by, not yet confirmed
    deadline = _deadline(cuts, "nomination")
    for n in rest_n:
        if (deadline is None or n.step != "nomination" or n.nominated_at is None
                or n.nominated_at <= deadline.at_utc or n.tso_status == "confirmed"
                or not n.nominated_mwh):
            continue
        q = float(n.nominated_mwh)
        add("late", q, -_sign(group, n) * q,
            f"The nomination {n.line_ref} ({_q(q, hub)}) was recorded {_at(n.nominated_at)}, "
            f"after the nomination deadline {_at(deadline.at_utc)}, and the TSO has not "
            "confirmed it: it is processed as a renomination in a later cycle, if at all.",
            f"提名 {n.line_ref}（{_qzh(q, hub)}）记录于 {_at_zh(n.nominated_at)}，晚于提名截止 "
            f"{_at_zh(deadline.at_utc)}，且 TSO 尚未确认：如被受理，将在之后的再提名周期处理。",
            f"Check the TSO accepted it as a renomination {deadline_en}; if not, renominate.",
            f"{deadline_zh}确认 TSO 是否已作为再提名受理；如未受理，请重新提名。",
            trade_ids=[n.trade_id] if n.trade_id else [], refs=[n.line_ref],
            flavour="nominated_after_deadline", deadline_utc=deadline.at_utc.isoformat())


def _shifted(gas_day: date, trades: Sequence[TradeFact],
             adjacent: Sequence[NominationFact]) -> NominationFact | None:
    """A nomination on the day before or after for one of these deals (which does not
    deliver then): the deal was nominated on the wrong gas day."""

    ids = {t.trade_id: t for t in trades}
    for n in adjacent:
        t = ids.get(n.trade_id or "")
        if t is None or not n.nominated_mwh or n.gas_day == gas_day:
            continue
        if not t.first_day <= n.gas_day <= t.last_day:
            return n
    return None


def _book_break(gas_day, group, add, rest_t, held_n, traded, nominated, delta, hours,
                adjacent, deadline_en, deadline_zh, tolerance, cuts) -> None:
    hub, cpty = group.hub, group.counterparty
    refs = [n.line_ref for n in held_n]
    ids = [t.trade_id for t in rest_t]
    day = gas_day.isoformat()
    direction = OUT if traded < 0 else IN
    if not held_n:
        shifted = _shifted(gas_day, rest_t, adjacent)
        if shifted is not None:
            add("gas_day_misaligned", delta, delta,
                f"Traded {_q(traded, hub)} ({_side(direction)}, {_deals(rest_t)}) with {cpty} "
                f"for gas day {day}, but it was nominated for gas day "
                f"{shifted.gas_day.isoformat()} ({shifted.line_ref}), when the deal does not "
                "deliver: a gas day (06:00 to 06:00 CET) read as a calendar day, or the wrong "
                f"day picked. Gas day {day} is {_state(delta)} {_q(delta, hub)}.",
                f"已与{cpty}就燃气日 {day} 交易 {_qzh(traded, hub)}（{_side_zh(direction)}，"
                f"{_deals(rest_t)}），但提名在燃气日 {shifted.gas_day.isoformat()}"
                f"（{shifted.line_ref}），"
                f"该日并无交割：可能把燃气日（欧洲中部时间 06:00 至 06:00）当成了日历日，或选错日期"
                f"。"
                f"燃气日 {day} {_state_zh(delta)}{_qzh(delta, hub)}。",
                f"Move the nomination to gas day {day} {deadline_en}, and withdraw the one on "
                f"{shifted.gas_day.isoformat()}.",
                f"{deadline_zh}将提名改到燃气日 {day}，并撤回 {shifted.gas_day.isoformat()} 的提名"
                f"。",
                trade_ids=ids, refs=[shifted.line_ref], flavour="other_gas_day",
                nominated_gas_day=shifted.gas_day.isoformat())
            return
        add("not_nominated", traded, delta,
            f"Traded {_q(traded, hub)} with {cpty} ({_side(direction)}, deal "
            f"{_deals(rest_t)}); nothing nominated for gas day {day}. The book counts it and "
            f"the TSO will not: {_state(delta)} {_q(delta, hub)} at {hub}.",
            f"已与{cpty}交易 {_qzh(traded, hub)}（{_side_zh(direction)}，交易 {_deals(rest_t)}），"
            f"燃气日 {day} 未见提名。账簿已计入而 TSO 不会：{hub} {_state_zh(delta)}"
            f"{_qzh(delta, hub)}。",
            f"Nominate {_q(traded, hub)} {_way(direction, cpty)} {deadline_en}; if the deal "
            "was moved or cancelled, ask the trader and the ETRM import.",
            f"{deadline_zh}提名 {_qzh(traded, hub)}（{_way_zh(direction, cpty)}）；若交易已调整或取"
            f"消，"
            "请与交易员及 ETRM 导入核实。",
            trade_ids=ids, traded_mwh=round(traded, 1))
        return
    if not rest_t:
        n_dir = IN if nominated > 0 else OUT
        shifted = next((n for n in held_n if n.trade_days is not None
                        and not n.trade_days[0] <= gas_day <= n.trade_days[1]), None)
        if shifted is not None:
            first, last = shifted.trade_days
            add("gas_day_misaligned", delta, delta,
                f"Nominated {_q(nominated, hub)} {_way(n_dir, cpty)} for gas day {day} against "
                f"{shifted.line_ref}, but that deal delivers {first.isoformat()} to "
                f"{last.isoformat()}: a gas day (06:00 to 06:00 CET) read as a calendar day, or "
                f"the wrong day picked. Gas day {day} is {_state(delta)} {_q(delta, hub)}.",
                f"燃气日 {day} 已就 {shifted.line_ref} 提名 {_qzh(nominated, hub)}"
                f"（{_way_zh(n_dir, cpty)}），但该交易交割期为 {first.isoformat()} 至 "
                f"{last.isoformat()}：可能把燃气日（欧洲中部时间 06:00 至 06:00）当成了日历日，或选"
                f"错日期。"
                f"燃气日 {day} {_state_zh(delta)}{_qzh(delta, hub)}。",
                f"Move the nomination to the deal's gas days {deadline_en}.",
                f"{deadline_zh}将提名改到交易的燃气日。",
                refs=refs, flavour="other_gas_day")
            return
        add("nomination_without_trade", nominated, delta,
            f"Nominated {_q(nominated, hub)} {_way(n_dir, cpty)} for gas day {day} "
            f"({', '.join(refs)}), but no deal with {cpty} delivers at {hub} that day: "
            f"{_state(delta)} {_q(delta, hub)} against the book.",
            f"燃气日 {day} 已提名 {_qzh(nominated, hub)}（{_way_zh(n_dir, cpty)}，{'、'.join(refs)}"
            f"），"
            f"但当日与{cpty}在 {hub} 无任何交易交割：相对账簿{_state_zh(delta)}{_qzh(delta, hub)}"
            f"。",
            f"Check the deal reached the ETRM import (trade date, book, counterparty name); "
            f"if there is none, withdraw the nomination {deadline_en}.",
            f"核实交易是否已进入 ETRM 导入（交易日、账簿、对手名称）；若无此交易，请{deadline_zh}撤"
            f"回提名。",
            refs=refs, nominated_mwh=round(nominated, 1))
        return
    misaligned = [t for t in rest_t if t.misaligned]
    if misaligned:
        t = misaligned[0]
        add("gas_day_misaligned", delta, delta,
            f"Deal {t.deal_ref}'s delivery does not start or end at the 06:00 CET gas-day "
            f"boundary: only {t.hours_in_day or 0:.0f} of the gas day's {hours:.0f} hours fall in "
            f"it, so the book counts {_q(traded, hub)} where {_q(nominated, hub)} is nominated "
            f"(difference {delta:+,.0f} MWh). The deal was likely booked in calendar days "
            "(midnight) or in another time zone.",
            f"交易 {t.deal_ref} 的交割起止不在欧洲中部时间 06:00 的燃气日边界：燃气日 {hours:.0f} "
            f"小时中"
            f"仅 {t.hours_in_day or 0:.0f} 小时落入其中，因此账簿计入 {_qzh(traded, hub)}，而提名为"
            f" "
            f"{_qzh(nominated, hub)}（差 {delta:+,.0f} MWh）。交易可能按日历日（零点）或其他时区录"
            f"入。",
            f"Ask the trader or back office to correct the deal's delivery times in the ETRM, "
            f"then check the nomination {deadline_en}.",
            f"请交易员或后台在 ETRM 中更正交割时间，并{deadline_zh}复核提名。",
            trade_ids=[t.trade_id], refs=refs, flavour="calendar_day",
            hours_in_day=t.hours_in_day)
        return
    slip = unit_factor(nominated, traded, hours)
    if slip is not None:
        factor, words, words_zh, larger = slip
        relation = (f"{abs(nominated):,.0f} = {abs(traded):,.0f} × {factor:,.2f}" if larger
                    else f"{abs(nominated):,.0f} = {abs(traded):,.0f} ÷ {factor:,.2f}")
        add("unit_mismatch", delta, delta,
            f"Traded {_q(traded, hub)} with {cpty} but nominated {_q(nominated, hub)}: "
            f"{relation}, the mark of {words}. The day is {_state(delta)} {_q(delta, hub)}.",
            f"与{cpty}交易 {_qzh(traded, hub)}，但提名 {_qzh(nominated, hub)}：{relation}，"
            f"典型的{words_zh}。当日{_state_zh(delta)}{_qzh(delta, hub)}。",
            f"Correct the nominated quantity to {_q(traded, hub)} "
            f"({_kwh_h(abs(traded), hours):,.0f} kWh/h) {deadline_en}.",
            f"{deadline_zh}将提名量更正为 {_qzh(traded, hub)}（{_kwh_h(abs(traded), hours):,.0f}"
            f" kWh/h）。",
            trade_ids=ids, refs=refs, factor=round(factor, 4), traded_mwh=round(traded, 1),
            nominated_mwh=round(nominated, 1))
        return
    last_nominated = max((n.nominated_at for n in held_n if n.nominated_at), default=None)
    late = [t for t in rest_t if last_nominated is not None and t.traded_at is not None
            and t.traded_at > last_nominated]
    if late and abs(sum(t.signed for t in late) + delta) <= tolerance:
        later = sum(t.signed for t in late)
        add("late", delta, delta,
            f"Deal {_deals(late)} ({_q(later, hub)}, {_side(late[0].direction)}) was booked "
            f"{_at(late[0].traded_at)}, after the last nomination to {cpty} "
            f"({_at(last_nominated)}): nominated {nominated:+,.0f} MWh against traded "
            f"{traded:+,.0f} MWh, the difference {delta:+,.0f} MWh is that deal.",
            f"交易 {_deals(late)}（{_qzh(later, hub)}，{_side_zh(late[0].direction)}）录入于 "
            f"{_at_zh(late[0].traded_at)}，晚于对{cpty}的最后一次提名（{_at_zh(last_nominated)}）："
            f"提名 "
            f"{nominated:+,.0f} MWh 对比交易 {traded:+,.0f} MWh，差额 {delta:+,.0f} MWh 即该笔交易"
            f"。",
            f"Renominate {cpty} to {traded:+,.0f} MWh {deadline_en}.",
            f"{deadline_zh}将对{cpty}的提名改为 {traded:+,.0f} MWh。",
            trade_ids=[t.trade_id for t in late], refs=refs, flavour="traded_after_nomination",
            traded_mwh=round(traded, 1), nominated_mwh=round(nominated, 1))
        return
    add("quantity_mismatch", delta, delta,
        f"Traded {traded:+,.0f} MWh with {cpty}, nominated {nominated:+,.0f} MWh: "
        f"{nominated:+,.0f} − ({traded:+,.0f}) = {delta:+,.0f} MWh "
        f"({_kwh_h(delta, hours):+,.0f} kWh/h over the {hours:.0f}-hour gas day), "
        f"{_state(delta)} {_q(delta, hub)}.",
        f"与{cpty}交易 {traded:+,.0f} MWh，提名 {nominated:+,.0f} MWh：{nominated:+,.0f} − "
        f"({traded:+,.0f}) = {delta:+,.0f} MWh（按 {hours:.0f} 小时燃气日为 "
        f"{_kwh_h(delta, hours):+,.0f} kWh/h），{_state_zh(delta)}{_qzh(delta, hub)}。",
        f"Check each deal with {cpty} against the nomination lines and renominate to "
        f"{traded:+,.0f} MWh {deadline_en}.",
        f"逐笔核对与{cpty}的交易与提名，并{deadline_zh}将提名改为 {traded:+,.0f} MWh。",
        trade_ids=ids, refs=refs, traded_mwh=round(traded, 1), nominated_mwh=round(nominated, 1),
        delta_mwh=round(delta, 1), delta_kwh_h=round(_kwh_h(delta, hours), 0))
