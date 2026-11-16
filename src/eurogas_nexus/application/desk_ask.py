"""Ask from the answer bar: a desk question answered from the facts the desk already holds.

A trader types a question into the search bar ("what's going on with Norwegian supply this
week", "why did storage withdrawal jump") and presses Enter. The answer is built in three
steps, each one an existing part of the product:

1. **Facts.** The Today read (``application/desk_today.build_today``) for this caller: prices
   and day change, outages, alerts, storage and the NW Europe balance, and the book and the
   tightest limit when the caller may read the book. Every figure there already carries its
   unit, as-of time and simulated flag, and is what the caller may see on its own page. The
   facts are written as short desk lines, each with its source and as-of, and only the topics
   the question is about are kept (all market topics when it names none).
2. **Answer.** When the deployment enables the model and the caller holds the analysis
   capability, the model answers under ``ai_style.ANSWER_RULES`` from exactly those lines
   (``ai_payloads.ask_payload``: the question, the lines, ``S1`` source aliases, the
   simulated flag; no identifiers). Its text is shown only if it passes
   ``ai_style.answer_verdict`` (length, no advice to trade or nominate, no number, hub, unit,
   direction or source the facts lack: ``application/grounding``). Otherwise the fact lines
   stand on their own and the reply says why.
3. **Record.** Every model call is audited under the caller's identity, as "Why?" and the
   brief are.

Nothing here writes data, executes anything or reads a figure the caller cannot already see.

答案栏提问：以"今日概览"中调用者可见的事实（带来源与时间）为依据，模型仅可在
ai_style 规则与 grounding 校验通过时给出简答，否则只显示事实行。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.application.caller import Caller

#: What a question is about, by the words it uses (English and Chinese). A question that
#: names no topic gets every market topic; the book is only ever included when asked for.
TOPIC_WORDS: dict[str, tuple[str, ...]] = {
    "outages": (
        "outage", "maintenance", "remit", "umm", "trip", "offline", "unavailab", "shut",
        "停运", "检修", "故障", "中断",
    ),
    "supply": (
        "norway", "norwegian", "landing", "lng", "send-out", "sendout", "supply", "storage",
        "withdraw", "inject", "balance", "flow", "fill", "inventory", "demand",
        "挪威", "液化", "供应", "储气", "库存", "注气", "采气", "流量", "平衡", "需求",
    ),
    "prices": (
        "price", "ttf", "nbp", "peg", "ztp", "psv", "curve", "front month", "move",
        "rall", "fell", "fall", "drop", "rise", "rose", "market",
        "价格", "价", "上涨", "下跌", "市场",
    ),
    "alerts": ("alert", "warning", "告警", "预警"),
    "book": (
        "position", "book", "long", "short", "exposure", "credit", "limit", "mandate",
        "headroom", "counterpart", "p&l", "pnl", "hedge",
        "头寸", "敞口", "信用", "限额", "盈亏", "对冲", "账簿",
    ),
}
MARKET_TOPICS = ("prices", "outages", "supply", "alerts")
MAX_LINES_PER_TOPIC = 5
MAX_QUESTION_CHARS = 500


@dataclass
class FactLine:
    topic: str
    text: str
    source: str
    as_of: str | None
    simulated: bool = False


@dataclass
class Answer:
    question: str
    topics: list[str]
    answer: str | None
    basis: str  # "model" when the checked model text is shown, else "facts"
    ai: str  # "used", "off" (no model for this caller/deployment), "refused", "failed"
    lines: list[FactLine]
    sources: list[str]
    simulated: bool
    as_of: str
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["lines"] = [line.__dict__ for line in self.lines]
        return data


ModelCall = Callable[[list[dict[str, str]]], str | None]


def _says(text: str, word: str) -> bool:
    """Whether ``text`` uses ``word``: Latin words from a word start, Chinese anywhere."""

    if not word.isascii():
        return word in text
    return re.search(r"(?<![a-z])" + re.escape(word), text) is not None


def topics_for(question: str, *, book_allowed: bool) -> list[str]:
    """The topics a question is about, in a fixed order; the market topics when none."""

    text = question.lower()
    found = [topic for topic, words in TOPIC_WORDS.items() if any(_says(text, w) for w in words)]
    # Norwegian supply is read net of REMIT outages, so a Norway question gets them too.
    if ("norw" in text or "挪威" in text) and "outages" not in found:
        found.insert(0, "outages")
    found = [topic for topic in TOPIC_WORDS if topic in found]
    if not book_allowed:
        found = [topic for topic in found if topic != "book"]
    return found or list(MARKET_TOPICS)


def ask(
    session,
    caller: Caller,
    question: str,
    *,
    language: str = "en",
    model: ModelCall | None = None,
    book_allowed: bool = False,
    balance_reader: Callable[[], dict | None] | None = None,
    now: datetime | None = None,
) -> Answer:
    """Answer ``question`` from the caller's Today facts, with the model when it may be used."""

    from eurogas_nexus.application.desk_today import build_today

    now = now or datetime.now(UTC)
    question = question.strip()[:MAX_QUESTION_CHARS]
    topics = topics_for(question, book_allowed=book_allowed)
    today = build_today(session, caller, now=now, balance_reader=balance_reader)
    lines = [
        line
        for line in fact_lines(today, book_allowed=book_allowed, language=language)
        if line.topic in topics
    ]
    simulated = any(line.simulated for line in lines)
    sources = sorted({line.source for line in lines})
    answer = Answer(
        question=question,
        topics=topics,
        answer=None,
        basis="facts",
        ai="off" if model is None else "failed",
        lines=lines,
        sources=sources,
        simulated=simulated,
        as_of=now.isoformat(),
        warnings=list(today.get("warnings") or []),
    )
    if model is None or not lines:
        if not lines:
            answer.warnings.append("ASK_NO_FACTS")
        return answer

    from eurogas_nexus.application.ai_payloads import ask_messages
    from eurogas_nexus.application.ai_style import answer_verdict

    messages = ask_messages(question, lines, simulated=simulated, language=language)
    content = model(messages)
    if not content:
        answer.warnings.append("ASK_MODEL_NO_REPLY")
        return answer
    verdict = answer_verdict(content, evidence_text=messages[1]["content"], simulated=simulated)
    if not verdict.ok:
        answer.ai = "refused"
        answer.warnings.append(f"ASK_MODEL_TEXT_REFUSED:{verdict.check}")
        return answer
    answer.answer = content.strip()
    answer.basis = "model"
    answer.ai = "used"
    return answer


# ------------------------------------------------------------------------------ fact lines


def _day(value: str | None) -> str:
    """``15 Nov`` from an ISO date or instant; the input when it is not a date."""

    if not value:
        return "n/a"
    try:
        parsed = (
            date.fromisoformat(value)
            if len(value) == 10
            else datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
    except ValueError:
        return value
    return f"{parsed:%d %b}"


def _number(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}"


def _price_decimals(unit: str) -> int:
    return 3 if unit.endswith("/MWh") else 2


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DAY_MONTH = re.compile(r"\b(\d{1,2}) (" + "|".join(_MONTHS) + r")\b")


def _zh_dates(text: str) -> str:
    """``15 Nov`` as ``11月15日``: a Chinese answer writes the month as a number, which the
    number check must find in the facts it was given."""

    return _DAY_MONTH.sub(lambda m: f"{_MONTHS.index(m.group(2)) + 1}月{int(m.group(1))}日", text)


def fact_lines(
    today: dict[str, Any], *, book_allowed: bool, language: str = "en"
) -> list[FactLine]:
    """The Today read as desk lines, each with its topic, source and as-of."""

    rows = {row.get("key"): row for row in today.get("rows") or []}
    out: list[FactLine] = []
    out += _price_lines(rows.get("key_figures") or {})
    changes = rows.get("changes") or {}
    out += _outage_lines(changes.get("outages") or {})
    out += _alert_lines(changes.get("alerts") or {})
    out += _supply_lines(rows.get("fundamentals") or {})
    if book_allowed:
        out += _book_lines(rows.get("key_figures") or {}, rows.get("book") or {})
    by_topic: dict[str, int] = {}
    kept = []
    for line in out:
        by_topic[line.topic] = by_topic.get(line.topic, 0) + 1
        if by_topic[line.topic] <= MAX_LINES_PER_TOPIC:
            kept.append(line)
    if language.lower().startswith("zh"):
        for line in kept:
            line.text = _zh_dates(line.text)
    return kept


def _price_lines(key_figures: dict[str, Any]) -> list[FactLine]:
    lines = []
    for price in key_figures.get("prices") or []:
        if price.get("value") is None:
            continue
        unit = str(price.get("unit") or "")
        decimals = _price_decimals(unit)
        text = f"{price.get('label')} {_number(price['value'], decimals)} {unit} " \
               f"(close {_day(price.get('close_day'))})"
        if price.get("day_change") is not None:
            text += f", {price['day_change']:+.{decimals}f} on the day"
        if price.get("simulated"):
            text += ", simulated demo price, not a market price"
        lines.append(FactLine("prices", text + ".", f"price:{price.get('hub')}",
                              price.get("as_of"), bool(price.get("simulated"))))
    return lines


def _outage_lines(outages: dict[str, Any]) -> list[FactLine]:
    counts = outages.get("counts") or {}
    if not counts:
        return []
    lines = [
        FactLine(
            "outages",
            f"{counts.get('active', 0)} outages active now and {counts.get('scheduled', 0)} "
            f"scheduled in the next {outages.get('horizon_days', 14)} days (REMIT).",
            "remit:counts",
            outages.get("as_of"),
            any(item.get("simulated") for item in outages.get("items") or []),
        )
    ]
    for item in outages.get("items") or []:
        size = item.get("unavailable")
        amount = f"{_number(size, 0)} {item.get('unit') or ''} unavailable" if size is not None \
            else "capacity offline not stated"
        until = f", until {_day(item.get('end_utc'))}" if item.get("end_utc") else ", no end date"
        when = "now" if item.get("status") == "active" else f"from {_day(item.get('start_utc'))}"
        lines.append(
            FactLine(
                "outages",
                f"{item.get('facility')} ({item.get('zone') or 'n/a'}): {amount} {when}{until}.",
                f"remit:{item.get('event_id')}",
                item.get("as_of"),
                bool(item.get("simulated")),
            )
        )
    return lines


def _alert_lines(alerts: dict[str, Any]) -> list[FactLine]:
    lines = []
    for item in alerts.get("items") or []:
        severity = "Critical" if item.get("severity") == "critical" else "Watch"
        lines.append(FactLine("alerts", f"{severity}: {item.get('title')}.",
                              f"alert:{item.get('alert_id')}", item.get("as_of"),
                              bool(item.get("simulated"))))
    return lines


def _supply_lines(fundamentals: dict[str, Any]) -> list[FactLine]:
    lines = []
    storage = fundamentals.get("storage") or {}
    latest = storage.get("latest") if isinstance(storage, dict) else None
    if latest and latest.get("value") is not None:
        series = storage.get("series") or []
        text = f"{latest.get('label')} {latest['value']:.1f}% on {_day(latest.get('as_of'))}"
        if series:
            text += f", {series[-1]['inventory_twh']:,.1f} TWh"
        if len(series) >= 8 and series[-8].get("fill_pct") is not None:
            text += f"; {series[-8]['fill_pct']:.1f}% on {_day(series[-8]['day'])}"
        lines.append(FactLine("supply", text + ".", "storage:nwe", latest.get("as_of"),
                              bool(latest.get("simulated"))))
    balance = fundamentals.get("balance") or {}
    series = balance.get("series") if isinstance(balance, dict) else None
    latest = balance.get("latest") if isinstance(balance, dict) else None
    if series and latest:
        last, simulated = series[-1], bool(latest.get("simulated"))
        week = series[-8] if len(series) >= 8 else series[0]
        for key, name in (
            ("norway_gwh", "Norwegian supply to NW Europe"),
            ("lng_gwh", "LNG send-out in NW Europe"),
            ("storage_net_withdrawal_gwh", "Net storage withdrawal in NW Europe"),
            ("call_gwh", "NW Europe supply call"),
        ):
            if last.get(key) is None:
                continue
            text = f"{name} {_number(last[key], 0)} GWh/d on {_day(last['day'])}"
            if week is not last and week.get(key) is not None:
                text += f", {_number(week[key], 0)} GWh/d on {_day(week['day'])}"
            lines.append(FactLine("supply", text + ".", f"balance:{key}",
                                  latest.get("as_of"), simulated))
    return lines


def _book_lines(key_figures: dict[str, Any], book: dict[str, Any]) -> list[FactLine]:
    lines = []
    for hub in book.get("hubs") or []:
        today, front = hub.get("position_today") or {}, hub.get("position_front_month") or {}
        parts = [
            f"{'long' if figure['value'] > 0 else 'short'} {_number(abs(figure['value']), 0)} "
            f"{figure.get('unit')} {label}"
            for label, figure in (("today", today), (front.get("label", "front month"), front))
            if figure.get("value") not in (None, 0)
        ]
        if parts:
            lines.append(FactLine("book", f"{hub.get('hub')} net position: {', '.join(parts)}.",
                                  f"position:{hub.get('hub')}", today.get("as_of"), False))
    limit = key_figures.get("tightest_limit")
    if limit and limit.get("value") is not None:
        lines.append(
            FactLine(
                "book",
                f"{limit.get('label')}: {_number(limit['value'], 0)} {limit.get('unit')}, "
                f"{limit.get('utilisation_pct', 0):.0f}% used ({limit.get('status')}).",
                f"limit:{limit.get('kind')}",
                limit.get("as_of"),
                bool(limit.get("simulated")),
            )
        )
    return lines


def evidence_text(lines: list[FactLine]) -> str:
    """The fact lines as one text, for logs and tests."""

    return json.dumps([line.text for line in lines], ensure_ascii=False)
