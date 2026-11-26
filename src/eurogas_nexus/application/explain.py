""""Why?": a short explanation attached to the thing that needs it.

A trader clicks "Why?" next to an alert, an outage, a credit line, a mandate or a P&L figure.
The server loads that object's evidence itself (the client sends only its id), writes two
to four deterministic desk lines from it, and, when the caller may use the model, asks the
model to condense them into one desk note (``ai_style``). The note is shown only if it
cites the sources it was given and adds no number of its own; otherwise the rule lines
stand. Either way the answer names its sources, and nothing in it executes anything.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.application.ai_style import source_aliases
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.desk_text import (
    credit_lines,
    hub_for_zone,
    mandate_lines,
    money,
)
from eurogas_nexus.application.position_inputs import is_simulated_marks_warning

SUBJECTS = ("alert", "outage", "credit", "mandate", "pnl")
CACHE_SECONDS = 600
_CACHE: OrderedDict[str, tuple[float, Explanation]] = OrderedDict()


class NotFound(LookupError):
    """The object does not exist, or the caller may not see it."""


@dataclass
class Facts:
    """What a "Why?" may say: deterministic lines, the evidence and its sources."""

    title: str
    lines: list[str]
    evidence: dict[str, Any]
    sources: list[str]
    simulated: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class Explanation:
    subject: str
    object_id: str
    title: str
    text: str
    lines: list[str]
    sources: list[str]
    basis: str  # "rule" or "model"
    simulated: bool
    warnings: list[str]
    as_of: str

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


ModelCall = Callable[[list[dict[str, str]]], str | None]


def explain(
    session,
    caller: Caller,
    subject: str,
    object_id: str,
    *,
    language: str = "en",
    model: ModelCall | None = None,
    now: datetime | None = None,
) -> Explanation:
    """Explain one object for the caller. ``model`` is None when the model may not be used."""

    if subject not in SUBJECTS:
        raise NotFound(subject)
    now = now or datetime.now(UTC)
    from eurogas_nexus.application.reports.lang import writing

    with writing(language):
        # The rule text the panel shows when the model is off or refused is in the
        # interface's language too.
        facts = _FACTS[subject](session, caller, object_id, now)
    key = _cache_key(subject, object_id, language, facts, model is not None)
    cached = _CACHE.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    text, basis = " ".join(facts.lines), "rule"
    warnings = list(facts.warnings)
    if model is not None and not _entitled(caller, facts.evidence):
        model = None  # the rule text stands; a licensed row never reaches the model
    if model is not None:
        note = _model_note(model, facts, language)
        if note is not None:
            text, basis = note, "model"
        else:
            warnings.append("The model's note did not pass the checks; showing the rule text.")
    result = Explanation(
        subject=subject,
        object_id=object_id,
        title=facts.title,
        text=text,
        lines=facts.lines,
        sources=facts.sources,
        basis=basis,
        simulated=facts.simulated,
        warnings=warnings,
        as_of=now.isoformat(),
    )
    _CACHE[key] = (time.monotonic(), result)
    while len(_CACHE) > 256:
        _CACHE.popitem(last=False)
    return result


def model_payload(facts: Facts) -> dict[str, Any]:
    """Exactly what a "Why?" sends to the model: the rule lines and nothing else of the row.

    The lines already state every figure the note may use. The raw evidence row (ids,
    provider references, timestamps, unrounded values) stays on the platform: the model does
    not need it, and a number it copied from there would not match the lines anyway. Sources
    go as ``S1``, ``S2`` (``ai_style.source_aliases``).
    """

    return {
        "object": facts.title,
        "facts": facts.lines,
        "sources": list(source_aliases(facts.sources)),
        "simulated_inputs": facts.simulated,
    }


def model_task(facts: Facts) -> str:
    return (
        "Explain to the desk why this matters now, in at most three sentences. "
        + ("Mark the figures as simulated once (simulated prices). " if facts.simulated else "")
    )


def _model_note(model: ModelCall, facts: Facts, language: str) -> str | None:
    from eurogas_nexus.application.ai_style import checked_note, note_messages

    payload = model_payload(facts)
    content = model(note_messages(model_task(facts), payload, language=language))
    evidence_text = json.dumps(payload, ensure_ascii=False, default=str)
    note = checked_note(
        content,
        evidence_text=evidence_text,
        sources=payload["sources"],
        simulated=facts.simulated,
        language=language,
    )
    return note.text if note else None


def _entitled(caller: Caller, evidence: Any) -> bool:
    """Whether every source family named in the evidence is one the caller holds."""

    from eurogas_nexus.security.identity import principal_allows_source_family

    if getattr(caller.principal, "auth_method", "") == "legacy_public_token":
        return True
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"source_system", "source_family"} and isinstance(item, str):
                    found.append(item)
                else:
                    walk(item)
        elif isinstance(value, list | tuple):
            for item in value:
                walk(item)

    walk(evidence)
    return all(principal_allows_source_family(caller.principal, item) for item in found)


def _cache_key(subject, object_id, language, facts: Facts, with_model: bool) -> str:
    digest = hashlib.sha256(
        json.dumps([facts.lines, facts.evidence], sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return f"{subject}:{object_id}:{language}:{int(with_model)}:{digest}"


# ------------------------------------------------------------------------------ facts


def _alert_facts(session, caller: Caller, alert_id: str, now: datetime) -> Facts:
    from eurogas_nexus.application.alert_scope import alert_visibility
    from eurogas_nexus.db.repositories.monitoring import get_monitoring_alert

    row = get_monitoring_alert(session, alert_id)
    if row is None or not alert_visibility(session)(row):
        raise NotFound(alert_id)
    evidence = dict(row.evidence_snapshot or {})
    zh = language_is_zh()
    message = (row.message_zh_cn or row.message_en) if zh else row.message_en
    lines = [message] if message else []
    if row.category == "limits" and row.alert_type == "credit" and "net_exposure" in evidence:
        lines = credit_lines(evidence)
    elif row.category == "limits" and row.alert_type == "mandate" and "status" in evidence:
        lines = mandate_lines(evidence)
    elif row.alert_type == "outage":
        desk = _desk_line(caller, evidence.get("balancing_zone"), now)
        if desk:
            lines.append(desk)
    return Facts(
        title=(row.title_zh_cn or row.title_en) if zh else row.title_en,
        lines=[line for line in lines if line][:4],
        evidence=evidence,
        sources=list(row.source_refs or []) or [f"alert:{alert_id}"],
        simulated=bool(row.simulated),
        warnings=list(row.warnings or []),
    )


def _outage_facts(session, caller: Caller, event_id: str, now: datetime) -> Facts:
    from eurogas_nexus.application.remit_outages import load_outage_rows

    row = next(
        (item for item in load_outage_rows(session, now=now, horizon_days=60)
         if str(item["event_id"]) == event_id),
        None,
    )
    if row is None:
        raise NotFound(event_id)
    technical, unavailable = row.get("technical_capacity"), row.get("unavailable_capacity")
    ratio = (float(unavailable) / float(technical)
             if technical and unavailable is not None else None)
    gwh = row.get("unavailable_gwh_d")
    volume = f"{float(gwh):,.0f} GWh/d" if gwh is not None else f"{unavailable} {row.get('unit')}"
    zone = row.get("balancing_zone")
    kind = str(row.get("event_type") or "")
    if language_is_zh():
        end = _when(row.get("end_utc")) if row.get("end_utc") else "未给出结束日期"
        kinds = {"planned": "计划", "unplanned": "非计划"}
        lines = [
            f"{row['facility_name']}{f'（{zone}）' if zone else ''}不可用{volume}"
            + (f"（占技术容量的{ratio:.0%}）" if ratio is not None else "")
            + f"，UTC {_when(row['start_utc'])}至{end}。",
            f"{kinds.get(kind, '未说明类型的')}停运；原因：{row.get('description') or '未说明'}。",
        ]
    else:
        end = _when(row.get("end_utc")) if row.get("end_utc") else "no end date"
        lines = [
            f"{row['facility_name']}{f' ({zone})' if zone else ''}: {volume} unavailable"
            + (f" ({ratio:.0%} of technical capacity)" if ratio is not None else "")
            + f", {_when(row['start_utc'])} to {end} UTC.",
            f"{(kind or 'unspecified').capitalize()} outage; reason: "
            f"{row.get('description') or 'not stated'}.",
        ]
    desk = _desk_line(caller, row.get("balancing_zone"), now)
    if desk:
        lines.append(desk)
    return Facts(
        title=(f"{row['facility_name']}停运" if language_is_zh()
               else f"{row['facility_name']} outage"),
        lines=lines,
        evidence={key: row.get(key) for key in row if key not in {"raw"}},
        sources=[f"remit:{event_id}:v{row.get('version')}"],
        # Demo messages are fictional (seed_demo_desk); say so like any demo figure.
        simulated=str(row.get("source_reference") or "").lower().startswith("demo"),
    )


def _credit_facts(session, caller: Caller, counterparty_id: str, now: datetime) -> Facts:
    from eurogas_nexus.application.limits_service import credit_exposure_rows

    result = credit_exposure_rows(caller, now.date())
    row = next((r for r in result.rows if r["counterparty_id"] == counterparty_id), None)
    if row is None:
        raise NotFound(counterparty_id)
    demo = [w for w in result.warnings if is_simulated_marks_warning(w)]
    return Facts(
        title=(f"{row['counterparty']}信用额度：{STATUS_ZH.get(row['status'], row['status'])}"
               if language_is_zh() else f"{row['counterparty']} credit: {row['status']}"),
        lines=credit_lines(row),
        evidence=row,
        sources=[f"credit-line:{counterparty_id}"],
        simulated=bool(demo),
        warnings=demo,
    )


def _mandate_facts(session, caller: Caller, mandate_id: str, now: datetime) -> Facts:
    from eurogas_nexus.application.limits_service import mandate_usage_rows

    result = mandate_usage_rows(caller, now.date())
    row = next((r for r in result.rows if r["mandate_id"] == mandate_id), None)
    if row is None:
        raise NotFound(mandate_id)
    demo = [w for w in result.warnings if is_simulated_marks_warning(w)]
    return Facts(
        title=(f"{row['name']}授权：{STATUS_ZH.get(row['status'], row['status'])}"
               if language_is_zh() else f"{row['name']} mandate: {row['status']}"),
        lines=mandate_lines(row),
        evidence=row,
        sources=[f"mandate:{mandate_id}"],
        simulated=bool(demo),
        warnings=demo,
    )


def _pnl_facts(session, caller: Caller, snapshot_id: str, now: datetime) -> Facts:
    from eurogas_nexus.application.projections.portfolio_reads import pnl_snapshots

    rows = pnl_snapshots(session, principal_id=caller.principal_id)
    row = next((r for r in rows if r.pnl_snapshot_id == snapshot_id), None)
    if row is None:
        raise NotFound(snapshot_id)
    previous = next(
        (
            r
            for r in rows
            if r.portfolio_id == row.portfolio_id
            and r.strategy_id == row.strategy_id
            and r.valuation_time_utc < row.valuation_time_utc
        ),
        None,
    )
    if language_is_zh():
        lines = [
            f"指示性损益{money(row.indicative_pnl_gbp, 'GBP')}：已实现"
            f"{money(row.realized_pnl_gbp, 'GBP')}，未实现{money(row.unrealized_pnl_gbp, 'GBP')}，"
            f"对应{row.quantity_mwh:,.0f} MWh。",
            f"估值时间 UTC {_when(row.valuation_time_utc)}，依据{row.valuation_basis}。",
        ]
    else:
        lines = [
            f"Indicative P&L {money(row.indicative_pnl_gbp, 'GBP')}: realised "
            f"{money(row.realized_pnl_gbp, 'GBP')}, unrealised "
            f"{money(row.unrealized_pnl_gbp, 'GBP')} on {row.quantity_mwh:,.0f} MWh.",
            f"Valued {_when(row.valuation_time_utc)} UTC on {row.valuation_basis}.",
        ]
    if previous is not None:
        change = row.indicative_pnl_gbp - previous.indicative_pnl_gbp
        moved = row.unrealized_pnl_gbp - previous.unrealized_pnl_gbp
        lines.append(
            f"自 UTC {_when(previous.valuation_time_utc)}以来变化{money(change, 'GBP')}，其中"
            f"{money(moved, 'GBP')}为按市值计价。" if language_is_zh() else
            f"{money(change, 'GBP')} since {_when(previous.valuation_time_utc)} UTC, of which "
            f"{money(moved, 'GBP')} is mark-to-market."
        )
    evidence = row.model_dump()
    return Facts(
        title=f"{'损益' if language_is_zh() else 'P&L'} {row.portfolio_id}",
        lines=lines,
        evidence=evidence,
        sources=[f"pnl:{snapshot_id}", f"{row.source_system}:{row.source_reference}"],
        simulated=str(row.source_system).endswith("_Sim"),
        warnings=list(row.warnings),
    )


def _when(value: object) -> str:
    """``06 Nov 02:43``: how a desk writes a gas-day time."""

    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    if language_is_zh():
        return f"{moment.month}月{moment.day}日 {moment:%H:%M}"
    return moment.strftime("%d %b %H:%M")


def _desk_line(caller: Caller, zone: str | None, now: datetime) -> str | None:
    """The desk's net physical and financial position at the zone's hub today."""

    hub = hub_for_zone(zone or "")
    if hub is None:
        return None
    from eurogas_nexus.application.position_inputs import ladder_inputs

    today = now.date()
    try:
        inputs = ladder_inputs(caller, today, today, today)
    except Exception:  # noqa: BLE001 - the explanation stands without the position line
        return None
    net = sum(
        leg.mwh_per_day
        for leg in inputs.legs
        if leg.hub == hub and leg.first_gas_day <= today <= leg.last_gas_day
    )
    if not net:
        return (f"交易台今日在{hub}没有未平仓头寸。" if language_is_zh()
                else f"The desk has no open position at {hub} today.")
    if language_is_zh():
        return f"交易台今日在{hub}{'多头' if net > 0 else '空头'}{abs(net):,.0f} MWh/d。"
    side = "long" if net > 0 else "short"
    return f"The desk is {side} {abs(net):,.0f} MWh/d at {hub} today."


def language_is_zh() -> bool:
    from eurogas_nexus.application.reports.lang import zh

    return zh()


STATUS_ZH = {"breach": "超限", "watch": "观察", "ok": "正常", "expired": "已过期",
             "incomplete": "不完整"}

_FACTS: dict[str, Callable[..., Facts]] = {
    "alert": _alert_facts,
    "outage": _outage_facts,
    "credit": _credit_facts,
    "mandate": _mandate_facts,
    "pnl": _pnl_facts,
}
