"""What a change to a cargo's plan means to each role (LNG-2).

A firm cargo's plan is rebuilt after every ``cargo.changed`` event and compared with a baseline:
the plan the role was last told about (its open message), else the plan before the change. The
difference is turned into one message per role, each about that role's own work:

* **trader** (the book's owner): the hedge actions the new plan proposes that the baseline did
  not (a roll, a buy-back, a sale, a short-notice cover), each with its arithmetic and the time
  it is due before either month stops trading. For approval; nothing is traded.
* **scheduler** (operations): the berth and slot status, the send-out by gas day that moved,
  and the nomination cut-off each moved gas day hits (passed ones say renominate).
* **risk**: the net exposure by hub and delivery month before and after, and every trader
  mandate the change moves (utilisation, status, breaches).
* **desk head**: only when the change is material: the exposure or hedge action at or above the
  configured threshold, a slot newly missed, or a mandate newly in breach.

A role with nothing new gets no message, and a message whose items have all gone (the ETA came
back, the trader recorded the roll) is *withdrawn*. Every message ends with the line saying how
current its inputs are, which the caller writes.

Pure: no I/O and no clock. The caller passes ``now``, the cut-offs per gas day, the mandate
movements and the threshold. Nothing here trades, nominates or books.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from eurogas_nexus.domain.lng.in_transit import BALANCED_MWH, CargoPlan, Suggestion

ROLES = ("trader", "scheduler", "risk", "desk_head")
#: The hedge actions the trader is asked to approve.
HEDGE_KINDS = ("roll", "buy_back", "sell", "short_notice")
#: A berth that moves by less than this is not news to the scheduler (hours).
BERTH_MOVE_HOURS = 1.0
#: A nomination whose cut-off is this close needs the scheduler now (the checklist's DUE_SOON).
DUE_SOON = timedelta(hours=3)
#: A hedge action due this soon is critical for the trader.
TRADER_URGENT = timedelta(hours=24)
#: A mandate's utilisation that moves by less than this (percentage points) is not news.
MANDATE_MOVE_PCT = 0.5
#: Gas days listed by name in a scheduler message; the rest are counted.
DAYS_LISTED = 6

_SEVERITY_RANK = {"info": 0, "warning": 2, "critical": 4}


def _mwh(value: float) -> str:
    return f"{abs(value):,.0f} MWh"


def _signed(value: float) -> str:
    rounded = round(value)
    if rounded == 0:
        return "0"
    return f"{rounded:+,.0f}".replace("-", "−")


def _when(moment: datetime | None) -> str:
    return "no due time" if moment is None else f"{moment:%a %d %b %H:%M} UTC"


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def worst(*severities: str | None) -> str:
    """The highest of the severities given (``info`` when none)."""

    held = [item for item in severities if item]
    return max(held, key=lambda item: _SEVERITY_RANK.get(item, 0)) if held else "info"


@dataclass(frozen=True)
class MandateMove:
    """One trader mandate before and after the change (computed by the caller)."""

    mandate_id: str
    name: str
    status_before: str
    status_after: str
    utilisation_before: float | None
    utilisation_after: float | None
    largest_at: str = ""
    breaches_after: tuple[str, ...] = ()

    @property
    def moved(self) -> bool:
        if self.status_before != self.status_after:
            return True
        before, after = self.utilisation_before, self.utilisation_after
        if before is None or after is None:
            return before != after
        return abs(after - before) >= MANDATE_MOVE_PCT

    @property
    def newly_breached(self) -> bool:
        return self.status_after == "breach" and self.status_before != "breach"

    def text(self) -> str:
        def pct(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.0f} %"

        line = (
            f"{self.name}: {pct(self.utilisation_before)} ({self.status_before}) to "
            f"{pct(self.utilisation_after)} ({self.status_after})"
        )
        if self.largest_at:
            line += f", largest net in {self.largest_at}"
        if self.breaches_after:
            line += f"; {'; '.join(self.breaches_after[:2])}"
        return line

    def as_dict(self) -> dict[str, object]:
        return {
            "mandate_id": self.mandate_id,
            "name": self.name,
            "status_before": self.status_before,
            "status_after": self.status_after,
            "utilisation_before_pct": self.utilisation_before,
            "utilisation_after_pct": self.utilisation_after,
            "largest_at": self.largest_at,
            "breaches_after": list(self.breaches_after),
        }


@dataclass(frozen=True)
class MandateCheck:
    """The mandates the cargo's book falls under, or why they could not be checked."""

    moves: tuple[MandateMove, ...] = ()
    checked: int = 0
    error: str | None = None


@dataclass(frozen=True)
class Threshold:
    """When a change reaches the desk head, and where the figure comes from."""

    mwh: float
    source: str


@dataclass(frozen=True)
class RoleMessage:
    """What one role is told about the change."""

    role: str
    severity: str
    title_en: str
    title_zh: str
    lines_en: tuple[str, ...]
    lines_zh: tuple[str, ...]
    due_utc: datetime | None
    items: tuple[dict[str, object], ...]
    #: Keys of the items (what they are about), so a cooldown can tell "same items, new
    #: figures" from "something new".
    keys: tuple[str, ...]
    material_reasons: tuple[str, ...] = field(default=())

    @property
    def digest(self) -> str:
        """Stable over identical content: the dedupe key of a notification."""

        text = json.dumps(
            [self.role, self.severity, list(self.items), _iso(self.due_utc)],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(text.encode()).hexdigest()[:20]

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "severity": self.severity,
            "title_en": self.title_en,
            "title_zh": self.title_zh,
            "lines_en": list(self.lines_en),
            "lines_zh": list(self.lines_zh),
            "due_utc": _iso(self.due_utc),
            "items": list(self.items),
            "keys": list(self.keys),
            "material_reasons": list(self.material_reasons),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class CargoFacts:
    """Who and what the messages name (the caller reads them from the cargo record)."""

    cargo_id: str
    vessel: str
    book_id: str
    terminal: str | None
    eta_before_utc: datetime | None
    eta_after_utc: datetime | None
    #: What changed: eta, departure, energy, slot, hedges, status, destination.
    change_kinds: tuple[str, ...]
    #: The ETA's basis and confidence in words, e.g. "the ETA declared in AIS, low confidence".
    eta_basis_text: str = ""
    eta_low_confidence: bool = False

    def label(self) -> str:
        return f"{self.vessel} ({self.cargo_id})"


# ------------------------------------------------------------------------------------- trader


def _action_key(item: Suggestion) -> str:
    return ":".join(str(part) for part in (item.kind, item.hub, item.from_month, item.to_month))


def _actions(plan: CargoPlan) -> dict[str, Suggestion]:
    return {_action_key(item): item for item in plan.suggestions if item.kind in HEDGE_KINDS}


def _cover_line(plan: CargoPlan, hub: str | None, month: str | None) -> str:
    cover = plan.month(hub or "", month or "")
    if cover is None:
        return f"{hub} {month}: no position"
    return (
        f"{hub} {month}: physical {_signed(cover.physical_mwh)} + hedge "
        f"{_signed(cover.hedge_mwh)} = net {_signed(cover.net_mwh)} MWh"
    )


def _arithmetic(plan: CargoPlan, item: Suggestion) -> str:
    amount = item.mwh or 0.0
    if item.kind == "roll":
        return (
            f"{_cover_line(plan, item.hub, item.from_month)}; "
            f"{_cover_line(plan, item.hub, item.to_month)}; roll the smaller of the over-hedge "
            f"and the unhedged gas: {_mwh(amount)} (buy back {item.from_month}, sell "
            f"{item.to_month})"
        )
    if item.kind == "buy_back":
        return f"{_cover_line(plan, item.hub, item.from_month)}; buy back {_mwh(amount)}"
    if item.kind == "sell":
        return f"{_cover_line(plan, item.hub, item.from_month)}; sell {_mwh(amount)}"
    side = "buy" if amount < 0 else "sell"
    return (
        f"{_cover_line(plan, item.hub, item.from_month)}; the month has stopped trading, "
        f"{side} {_mwh(amount)} in day-ahead or balance-of-month"
    )


def _phrase(item: Suggestion) -> str:
    """The action in a few words, for a title."""

    amount = _mwh(item.mwh or 0)
    if item.kind == "roll":
        return f"roll {amount} {item.hub} {item.from_month} to {item.to_month}"
    if item.kind == "buy_back":
        return f"buy back {amount} {item.hub} {item.from_month}"
    if item.kind == "sell":
        return f"sell {amount} {item.hub} {item.from_month}"
    side = "buy" if (item.mwh or 0) < 0 else "sell"
    return f"{side} {amount} {item.hub} {item.from_month} at short notice"


def _phrase_zh(item: Suggestion) -> str:
    amount = _mwh(item.mwh or 0)
    if item.kind == "roll":
        return f"展期 {amount} {item.hub} {item.from_month} 至 {item.to_month}"
    if item.kind == "buy_back":
        return f"买回 {amount} {item.hub} {item.from_month}"
    if item.kind == "sell":
        return f"卖出 {amount} {item.hub} {item.from_month}"
    side = "买入" if (item.mwh or 0) < 0 else "卖出"
    return f"以日前或月内产品{side} {amount} {item.hub} {item.from_month}"


def _due_text(item: Suggestion) -> str:
    if item.kind == "short_notice":
        return "now, before the gas is due (the month no longer trades)"
    return _when(item.due_utc)


def _trader(
    facts: CargoFacts, baseline: CargoPlan, after: CargoPlan, now: datetime
) -> RoleMessage | None:
    held = _actions(baseline)
    items = []
    picked: list[Suggestion] = []
    for key, item in _actions(after).items():
        before = held.get(key)
        if before is not None and abs((before.mwh or 0) - (item.mwh or 0)) < BALANCED_MWH:
            continue  # the baseline already proposed it: not news
        picked.append(item)
        items.append(
            {
                "key": key,
                "kind": item.kind,
                "hub": item.hub,
                "from_month": item.from_month,
                "to_month": item.to_month,
                "mwh": round(item.mwh or 0.0, 1),
                "was_mwh": None if before is None else round(before.mwh or 0.0, 1),
                "due_utc": _iso(item.due_utc),
                "arithmetic": _arithmetic(after, item),
            }
        )
    if not items:
        return None
    dues = [item.due_utc for item in picked if item.due_utc is not None]
    due = min(dues) if dues else None
    urgent = any(item.kind == "short_notice" for item in picked) or (
        due is not None and due - now <= TRADER_URGENT
    )
    severity = "critical" if urgent else "warning"
    phrases = [_phrase(item) for item in picked]
    phrases_zh = [_phrase_zh(item) for item in picked]
    title = f"Hedges no longer match {facts.label()}: " + "; ".join(phrases)
    title_zh = f"{facts.label()} 套保需调整：" + "；".join(phrases_zh)
    lines = [
        f"{_why(facts)} The forward hedges no longer match when the gas leaves the terminal.",
        *[
            f"Proposed: {item.text} Due {_due_text(item)}. {entry['arithmetic']}."
            for item, entry in zip(picked, items, strict=True)
        ],
        "For your approval: nothing is traded or booked by the platform"
        + (
            f"; the ETA rests on {facts.eta_basis_text}, confirm it before you act."
            if facts.eta_low_confidence
            else "."
        ),
    ]
    lines_zh = [
        f"{_why_zh(facts)} 远期套保与码头外输月份不再匹配。",
        *[
            f"建议：{_phrase_zh(item)}，截止 {_when(item.due_utc) if item.due_utc else '即时'}。"
            for item in picked
        ],
        "待您审批：平台不会下单或记账。",
    ]
    return RoleMessage(
        role="trader",
        severity=severity,
        title_en=title,
        title_zh=title_zh,
        lines_en=tuple(lines),
        lines_zh=tuple(lines_zh),
        due_utc=due,
        items=tuple(items),
        keys=tuple(entry["key"] for entry in items),
    )


# ---------------------------------------------------------------------------------- scheduler


def _days(plan: CargoPlan) -> dict[str, float]:
    return {day: mwh for day, mwh in plan.send_out}


def _cutoff(cuts: Sequence[dict], now: datetime) -> dict | None:
    """The cut-off a changed gas day hits: the nomination, or once that has passed the last
    renomination, else the first declared window still open."""

    def find(key: str) -> dict | None:
        return next((cut for cut in cuts if cut.get("key") == key), None)

    nomination = find("nomination")
    if nomination is not None and datetime.fromisoformat(nomination["at_utc"]) > now:
        return {**nomination, "action": "nominate"}
    renomination = find("last_renomination")
    if renomination is not None:
        return {**renomination, "action": "renominate"}
    window = next(
        (cut for cut in cuts if cut.get("key") == "window"
         and datetime.fromisoformat(cut["at_utc"]) > now),
        None,
    )
    if window is not None:
        return {**window, "action": "nominate"}
    return None if nomination is None else {**nomination, "action": "nominate"}


def _scheduler(
    facts: CargoFacts,
    baseline: CargoPlan,
    after: CargoPlan,
    now: datetime,
    cutoffs_for: Callable[[date], Sequence[dict]],
) -> RoleMessage | None:
    items: list[dict[str, object]] = []
    lines: list[str] = []
    lines_zh: list[str] = []
    dues: list[datetime] = []
    severity = "warning"

    berth_moved = (
        baseline.berth_utc is not None
        and after.berth_utc is not None
        and abs((after.berth_utc - baseline.berth_utc).total_seconds()) / 3600 >= BERTH_MOVE_HOURS
    )
    status_moved = baseline.slot_status != after.slot_status
    if status_moved or berth_moved or (baseline.berth_utc is None) != (after.berth_utc is None):
        missed = after.slot_status == "missed" and baseline.slot_status != "missed"
        find = next((item for item in after.suggestions if item.kind == "find_slot"), None)
        items.append(
            {
                "key": "berth",
                "slot_status_before": baseline.slot_status,
                "slot_status_after": after.slot_status,
                "berth_before_utc": _iso(baseline.berth_utc),
                "berth_after_utc": _iso(after.berth_utc),
                "wait_hours_after": round(after.wait_hours, 1),
                "find_slot": None if find is None else find.text,
            }
        )
        if missed:
            severity = "critical"
            lines.append(
                f"Slot missed at {facts.terminal or 'the terminal'}: "
                + (find.text if find else "find a new slot.")
            )
            lines_zh.append(f"错过 {facts.terminal or '码头'} 的卸货窗口：需另寻窗口。")
        else:
            lines.append(
                f"Berth {_when(baseline.berth_utc)} ({baseline.slot_status}) is now "
                f"{_when(after.berth_utc)} ({after.slot_status}"
                + (f", {after.wait_hours:.0f} h at anchor" if after.wait_hours >= 1 else "")
                + ")."
            )
            lines_zh.append(
                f"靠泊由 {_when(baseline.berth_utc)}（{baseline.slot_status}）改为 "
                f"{_when(after.berth_utc)}（{after.slot_status}）。"
            )

    before_days, after_days = _days(baseline), _days(after)
    moved_days = sorted(
        day
        for day in set(before_days) | set(after_days)
        if abs(after_days.get(day, 0.0) - before_days.get(day, 0.0)) >= BALANCED_MWH
    )
    day_lines: list[str] = []
    for label in moved_days:
        was, now_mwh = before_days.get(label, 0.0), after_days.get(label, 0.0)
        cut = _cutoff(cutoffs_for(date.fromisoformat(label)), now)
        at = None if cut is None else datetime.fromisoformat(cut["at_utc"])
        passed = at is not None and at <= now
        if at is not None and not passed:
            dues.append(at)
            if at - now <= DUE_SOON:
                severity = "critical"
        if passed:
            severity = "critical"
        items.append(
            {
                "key": f"gas_day:{label}",
                "gas_day": label,
                "send_out_before_mwh": round(was, 1),
                "send_out_after_mwh": round(now_mwh, 1),
                "cutoff": None
                if cut is None
                else {
                    "key": cut.get("key"),
                    "name": cut.get("name"),
                    "at_utc": cut["at_utc"],
                    "action": cut["action"],
                    "passed": passed,
                    "basis": cut.get("basis"),
                },
            }
        )
        if len(day_lines) < DAYS_LISTED:
            cut_text = (
                "no cut-off held"
                if cut is None
                else f"{cut['action']} by {_when(at)}" + (" (passed)" if passed else "")
            )
            day_lines.append(
                f"gas day {label}: {_mwh(was)} to {_mwh(now_mwh)}, {cut_text}"
            )
    if moved_days:
        more = len(moved_days) - len(day_lines)
        lines.append(
            "Send-out by gas day moves; nominations to change: "
            + "; ".join(day_lines)
            + (f"; and {more} more gas day(s)." if more > 0 else ".")
        )
        lines_zh.append(f"外输按燃气日变化，共 {len(moved_days)} 个燃气日需调整提名。")
    if abs(after.demurrage_hours - baseline.demurrage_hours) >= BERTH_MOVE_HOURS:
        items.append(
            {
                "key": "demurrage",
                "hours_before": round(baseline.demurrage_hours, 1),
                "hours_after": round(after.demurrage_hours, 1),
                "cost_after": None if after.demurrage_cost is None else round(
                    after.demurrage_cost, 2
                ),
            }
        )
        lines.append(
            f"Demurrage {baseline.demurrage_hours:.0f} h to {after.demurrage_hours:.0f} h "
            "past laytime."
        )
        lines_zh.append(f"滞期由 {baseline.demurrage_hours:.0f} 小时变为 "
                        f"{after.demurrage_hours:.0f} 小时。")
    if not items:
        return None
    lines.append("Statuses are recorded in Today's gas day checklist; nothing is nominated here.")
    lines_zh.append("状态在今日燃气日清单中记录；平台不提交提名。")
    lines.insert(0, _why(facts))
    lines_zh.insert(0, _why_zh(facts))
    missed = any(item.get("slot_status_after") == "missed" for item in items)
    first_due = min(dues) if dues else None
    if missed:
        title = f"Slot missed: {facts.label()} at {facts.terminal or 'the terminal'}"
        title_zh = f"错过卸货窗口：{facts.label()}"
    else:
        title = (
            f"Renominate {len(moved_days)} gas day(s) for {facts.label()}"
            if moved_days
            else f"Berth moves for {facts.label()}"
        )
        title_zh = (
            f"{facts.label()} 需调整 {len(moved_days)} 个燃气日的提名"
            if moved_days
            else f"{facts.label()} 靠泊时间变化"
        )
    return RoleMessage(
        role="scheduler",
        severity=severity,
        title_en=title,
        title_zh=title_zh,
        lines_en=tuple(lines),
        lines_zh=tuple(lines_zh),
        due_utc=first_due,
        items=tuple(items),
        keys=tuple(str(item["key"]) for item in items),
    )


# --------------------------------------------------------------------------------------- risk


def exposure_moves(baseline: CargoPlan, after: CargoPlan) -> list[dict[str, object]]:
    """Net exposure (physical + hedge) by hub and month that the change moved."""

    keys = sorted(
        {(cover.hub, cover.month) for cover in baseline.months}
        | {(cover.hub, cover.month) for cover in after.months},
        key=lambda key: (key[1], key[0]),
    )
    out = []
    for hub, month in keys:
        was = baseline.month(hub, month)
        now = after.month(hub, month)
        net_before = 0.0 if was is None else was.net_mwh
        net_after = 0.0 if now is None else now.net_mwh
        if abs(net_after - net_before) < BALANCED_MWH:
            continue
        out.append(
            {
                "key": f"exposure:{hub}:{month}",
                "hub": hub,
                "month": month,
                "net_before_mwh": round(net_before, 1),
                "net_after_mwh": round(net_after, 1),
                "change_mwh": round(net_after - net_before, 1),
                "trading": (now or was).trading,
                "last_trading_day": (now or was).last_trading_day.isoformat(),
            }
        )
    return out


def _risk(
    facts: CargoFacts, baseline: CargoPlan, after: CargoPlan, mandates: MandateCheck
) -> RoleMessage | None:
    moves = exposure_moves(baseline, after)
    moved_mandates = [move for move in mandates.moves if move.moved]
    if not moves and not moved_mandates:
        return None
    items: list[dict[str, object]] = list(moves)
    items += [{"key": f"mandate:{move.mandate_id}", **move.as_dict()} for move in moved_mandates]
    breach = any(move.newly_breached for move in moved_mandates)
    severity = "critical" if breach else "warning"
    lines = [_why(facts)]
    lines_zh = [_why_zh(facts)]
    if moves:
        lines.append(
            "Net exposure by month (physical + hedge): "
            + "; ".join(
                f"{move['hub']} {move['month']} {_signed(move['net_before_mwh'])} to "
                f"{_signed(move['net_after_mwh'])} MWh"
                for move in moves
            )
            + "."
        )
        lines_zh.append(
            "按月净敞口（实货 + 套保）："
            + "；".join(
                f"{move['hub']} {move['month']} {_signed(move['net_before_mwh'])} → "
                f"{_signed(move['net_after_mwh'])} MWh"
                for move in moves
            )
            + "。"
        )
    if mandates.error:
        lines.append(f"Mandates not checked: {mandates.error}.")
        lines_zh.append("授权未能检查。")
    elif moved_mandates:
        lines.append("Mandates moved: " + "; ".join(move.text() for move in moved_mandates) + ".")
        lines_zh.append(
            "授权变化："
            + "；".join(
                f"{move.name} {move.status_before} → {move.status_after}"
                for move in moved_mandates
            )
            + "。"
        )
    elif mandates.checked:
        lines.append(f"No mandate on book {facts.book_id} moves ({mandates.checked} checked).")
        lines_zh.append(f"账簿 {facts.book_id} 的授权未受影响。")
    else:
        lines.append(f"No mandate covers book {facts.book_id}.")
        lines_zh.append(f"账簿 {facts.book_id} 无授权。")
    # Due when the first moved month that still trades stops trading (end of its last day).
    dues = [
        datetime.combine(date.fromisoformat(str(move["last_trading_day"])), time.min, tzinfo=UTC)
        + timedelta(days=1)
        for move in moves
        if move["trading"]
    ]
    if breach:
        title = f"Mandate breach from {facts.label()}"
        title_zh = f"{facts.label()} 导致授权超限"
    else:
        largest = max(moves, key=lambda move: abs(float(move["change_mwh"])), default=None)
        title = (
            f"Exposure moves {_mwh(float(largest['change_mwh']))} in {largest['hub']} "
            f"{largest['month']}: {facts.label()}"
            if largest
            else f"Mandate usage moves: {facts.label()}"
        )
        title_zh = f"{facts.label()} 敞口变化"
    return RoleMessage(
        role="risk",
        severity=severity,
        title_en=title,
        title_zh=title_zh,
        lines_en=tuple(lines),
        lines_zh=tuple(lines_zh),
        due_utc=min(dues) if dues else None,
        items=tuple(items),
        keys=tuple(str(item["key"]) for item in items),
    )


# ---------------------------------------------------------------------------------- desk head


def _desk_head(
    facts: CargoFacts,
    baseline: CargoPlan,
    after: CargoPlan,
    others: dict[str, RoleMessage | None],
    mandates: MandateCheck,
    threshold: Threshold,
) -> RoleMessage | None:
    reasons: list[str] = []
    moves = exposure_moves(baseline, after)
    largest = max((abs(float(move["change_mwh"])) for move in moves), default=0.0)
    if largest >= threshold.mwh:
        reasons.append(f"net exposure moves {_mwh(largest)} in one month")
    trader = others.get("trader")
    hedged = sum(abs(float(item["mwh"])) for item in trader.items) if trader else 0.0
    if hedged >= threshold.mwh:
        reasons.append(f"hedge actions of {_mwh(hedged)} proposed")
    if after.slot_status == "missed" and baseline.slot_status != "missed":
        reasons.append("the slot is missed")
    breached = [move.name for move in mandates.moves if move.moved and move.newly_breached]
    if breached:
        reasons.append(f"mandate breach ({', '.join(breached)})")
    if not reasons:
        return None
    lines = [_why(facts), f"Material: {'; '.join(reasons)} (threshold {_mwh(threshold.mwh)}: "
             f"{threshold.source})."]
    lines_zh = [_why_zh(facts), f"重大变化：阈值 {_mwh(threshold.mwh)}。"]
    for role in ("trader", "scheduler", "risk"):
        message = others.get(role)
        if message is not None:
            lines.append(f"{role.replace('_', ' ').capitalize()}: {message.title_en}.")
            lines_zh.append(f"{role}：{message.title_zh}。")
    severity = worst(*(message.severity for message in others.values() if message))
    dues = [message.due_utc for message in others.values() if message and message.due_utc]
    return RoleMessage(
        role="desk_head",
        severity=worst(severity, "warning"),
        title_en=f"Material cargo change: {facts.label()}",
        title_zh=f"重大货船变化：{facts.label()}",
        lines_en=tuple(lines),
        lines_zh=tuple(lines_zh),
        due_utc=min(dues) if dues else None,
        items=tuple({"key": f"material:{index}", "reason": reason}
                    for index, reason in enumerate(reasons)),
        keys=("material",),
        material_reasons=tuple(reasons),
    )


# ------------------------------------------------------------------------------------- common


def _why(facts: CargoFacts) -> str:
    kinds = set(facts.change_kinds)
    if "eta" in kinds and facts.eta_before_utc and facts.eta_after_utc:
        hours = (facts.eta_after_utc - facts.eta_before_utc).total_seconds() / 3600
        way = "later" if hours > 0 else "earlier"
        days = abs(hours) / 24
        size = f"{days:.1f} days" if days >= 1 else f"{abs(hours):.0f} h"
        return (
            f"{facts.label()} ETA moves {size} {way}: {_when(facts.eta_before_utc)} to "
            f"{_when(facts.eta_after_utc)}."
        )
    named = ", ".join(sorted(kinds)) or "inputs"
    return f"{facts.label()}: the cargo's {named} changed."


def _why_zh(facts: CargoFacts) -> str:
    if "eta" in facts.change_kinds and facts.eta_before_utc and facts.eta_after_utc:
        return (
            f"{facts.label()} 预计到港时间由 {_when(facts.eta_before_utc)} 改为 "
            f"{_when(facts.eta_after_utc)}。"
        )
    return f"{facts.label()} 的计划输入已变化。"


def derive(
    facts: CargoFacts,
    baseline: CargoPlan,
    after: CargoPlan,
    *,
    now: datetime,
    cutoffs_for: Callable[[date], Sequence[dict]],
    mandates: MandateCheck,
    threshold: Threshold,
) -> dict[str, RoleMessage | None]:
    """One message per role (``None``: nothing new for that role) for a baseline and a new
    plan built at the same ``now``."""

    out: dict[str, RoleMessage | None] = {
        "trader": _trader(facts, baseline, after, now),
        "scheduler": _scheduler(facts, baseline, after, now, cutoffs_for),
        "risk": _risk(facts, baseline, after, mandates),
    }
    out["desk_head"] = _desk_head(facts, baseline, after, dict(out), mandates, threshold)
    return out


__all__ = [
    "DUE_SOON",
    "HEDGE_KINDS",
    "ROLES",
    "CargoFacts",
    "MandateCheck",
    "MandateMove",
    "RoleMessage",
    "Threshold",
    "derive",
    "exposure_moves",
    "worst",
]
