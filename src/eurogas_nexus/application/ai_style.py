"""How the model writes for a trading desk, and the checks its text must pass.

Traders read in seconds, between prices. Every model output in Eurogas Nexus is a desk
note: at most three short sentences, figures with units, the fact first, no preamble, no
filler, no advice to trade. The model is given the deterministic facts and may only
reorder, condense and connect them. Its text is shown only if it passes
:func:`checked_note` (a desk note) or :func:`checked_answer` (an answer to a question):
within length, citing only the sources it was given, with no number that is not in the
evidence, no advice to trade or nominate, no simulated price that reads as a market price,
and grounded in the ontology (``application/grounding.py``): no hub, unit, direction,
superlative, source or name the evidence does not contain. Otherwise the rule text stands.

:func:`note_verdict` and :func:`answer_verdict` say *which* check refused the text; the
evaluation set (``tests/evals/test_ai_note_evals.py``) and the on-demand provider run
(``scripts/ai/run_note_eval.py``) use them to report refusal reasons.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MAX_SENTENCES = 3
MAX_CHARS = 360
#: An answer to a question: at most five sentences or bullet lines, under 100 words.
ANSWER_MAX_SENTENCES = 5
ANSWER_MAX_WORDS = 100
ANSWER_MAX_CHARS = 900

#: The common system instruction. Each use adds only its task and output fields.
DESK_NOTE_RULES = (
    "You write desk notes for commercial gas traders and risk managers. Rules: "
    "at most three short sentences, under 60 words in total. "
    "Lead with the fact that matters, then why it matters, then what to check. "
    "Use only the facts supplied; never add a number, date, name or source that is not in "
    "them, and do not compute new figures (differences, sums, shares). "
    "Keep units as given (GWh/d, MWh, EUR/MWh, p/th). "
    "No preamble, no restating the question, no hedging filler, no markdown. "
    "Never recommend or describe executing a trade, nomination or settlement. "
    "If the facts are not enough, say in one sentence what is missing."
)

#: For an answer to a question (alert analysis, Copilot, Ask): a little more room, same style.
ANSWER_RULES = (
    "You answer commercial gas traders and risk managers between trades. Rules: "
    "the answer first, in at most five short sentences or five bullet lines, under 100 "
    "words. Figures with their units and dates. Use only the facts supplied and cite "
    "them; never invent a number, name or source, and do not compute new figures "
    "(differences, sums, shares). Say plainly what is fact, what is "
    "simulated and what is missing. No preamble, no restating the question, no filler. "
    "Never recommend or describe executing a trade, nomination or settlement; a person "
    "decides."
)

#: Provider call budgets. ``max_tokens`` bounds reasoning *and* reply: a reasoning model
#: (DeepSeek V4 Flash) spends several hundred tokens thinking before it writes, so a 300-token
#: budget returned an empty reply on most calls and the rule text always stood (AI-04 live
#: run, 2026-11-15). The reply's own length is held by the checks, not by this budget.
NOTE_CALL = {"temperature": 0.1, "max_tokens": 3000, "timeout_seconds": 30.0}
ANSWER_CALL = {"temperature": 0.15, "max_tokens": 2000, "timeout_seconds": 45.0}
ENRICHMENT_CALL = {"temperature": 0.1, "max_tokens": 2000, "timeout_seconds": 45.0}

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass(frozen=True)
class CheckedNote:
    text: str
    cites: tuple[str, ...]


@dataclass(frozen=True)
class Verdict:
    """The outcome of the checks. ``check`` names the first check that refused the text."""

    ok: bool
    check: str = ""
    detail: str = ""
    note: CheckedNote | None = None


def source_aliases(sources: list[str]) -> dict[str, str]:
    """``{"S1": "<first source id>", ...}``: what the model sees instead of internal ids.

    The model only needs to say which facts it used; the platform's own identifiers
    (counterparty ids, snapshot ids, provider references) stay on the platform.
    """

    return {f"S{index}": source for index, source in enumerate(sources, start=1)}


def language_rule(language: str | None) -> str:
    """The instruction that fixes the reply's language (the interface's language)."""

    if str(language or "").lower().startswith("zh"):
        return ("Write in Simplified Chinese, even when the facts are in English; keep hub "
                "names, contract codes, units and figures exactly as given.")
    return "Write in English."


def language_ok(text: str, language: str | None) -> bool:
    """Whether ``text`` is written in ``language``: a Chinese reply is mostly Chinese characters
    (figures, units and hub names aside); an English one has none."""

    cjk = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    if str(language or "").lower().startswith("zh"):
        letters = len(re.findall(r"[A-Za-z]", re.sub(
            r"\b(?:[A-Z][A-Za-z]*[-\d]*|GWh/d|MWh|TWh|EUR|GBp|p/th|mcm/d|LNG)\b", "", text or "")))
        return cjk >= 4 and cjk >= letters
    return cjk == 0


def note_messages(task: str, facts: dict, *, language: str) -> list[dict[str, str]]:
    """System and user messages for one desk note over ``facts``."""

    return [
        {
            "role": "system",
            "content": (
                f"{DESK_NOTE_RULES} {language_rule(language)} {task} "
                'Return JSON only: {"text": "<the note>", "cites": ["<source ids used>"]}.'
            ),
        },
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)},
    ]


def _numbers(text: str) -> set[str]:
    out = set()
    for match in _NUMBER.findall(text or ""):
        value = match.replace(",", "")
        # "07 Nov" and "7 Nov" are the same day; "0.51" keeps its leading zero.
        if value.isdigit():
            value = value.lstrip("0") or "0"
        out.add(value)
    return out


# ------------------------------------------------------------------------ style checks

#: Trading or nomination advice. Refused unless the evidence itself uses the word (a route
#: row may say ``buy_hub``; that is a field name, not a word, and does not count).
_ADVICE_EN = re.compile(
    r"\b(buy|buying|sell|selling|hedge|hedging|nominate|nominating|renominate|execute|"
    r"executing|unwind|recommend|recommends|recommended|recommendation|advise|advice|"
    r"go long|go short|take profit|close out|lift the offer|hit the bid|place an order|"
    r"place orders?)\b",
    re.IGNORECASE,
)
_ADVICE_ZH = ("买入", "卖出", "建议", "对冲", "提名", "平仓", "加仓", "减仓", "下单", "抛售")

#: Wording that presents a figure as a traded or published market price.
_MARKET_PRICE_EN = re.compile(
    r"\b(market prices?|market levels?|market close|traded at|trades at|trading at|"
    r"settled at|settles at|settlement price|exchange prices?|screen prices?|live prices?|"
    r"quoted at)\b",
    re.IGNORECASE,
)
_MARKET_PRICE_ZH = ("市场价", "成交价", "结算价", "实盘", "交易所价格")
_NOT_MARKET = re.compile(
    r"\bnot (?:a |the )?(?:real |actual )?market prices?\b|非市场价|不是市场价|并非市场价",
    re.IGNORECASE,
)
_SIMULATED_WORDS = re.compile(
    r"\b(simulated|demo|synthetic|illustrative)\b|模拟|演示|示例", re.IGNORECASE
)
#: A quoted price: a figure with a price unit (EUR/MWh, p/th, USD/MMBtu ...).
_PRICE_FIGURE = re.compile(
    r"\d[\d.,]*\s?(?:EUR|GBP|USD|GBp|€|£|\$|p)\s?/\s?(?:MWh|th|therm|MMBtu|GJ)(?![A-Za-z])"
    r"|\d[\d.,]*\s?(?:欧元|英镑|便士|美元)\s?/"
)


def _in_evidence(word: str, evidence_lower: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(word.lower())}(?![A-Za-z0-9_])"
    return re.search(pattern, evidence_lower) is not None


def _style_refusal(text: str, evidence_text: str, simulated: bool) -> tuple[str, str] | None:
    evidence_lower = evidence_text.lower()
    for match in _ADVICE_EN.finditer(text):
        if not _in_evidence(match.group(0), evidence_lower):
            return "advice", match.group(0)
    for word in _ADVICE_ZH:
        if word in text and word not in evidence_text:
            return "advice", word
    if simulated:
        unnegated = _NOT_MARKET.sub(" ", text)
        match = _MARKET_PRICE_EN.search(unnegated)
        if match:
            return "simulated_as_market", match.group(0)
        for word in _MARKET_PRICE_ZH:
            if word in unnegated:
                return "simulated_as_market", word
        if _PRICE_FIGURE.search(text) and not _SIMULATED_WORDS.search(text):
            return "simulated_as_market", "a simulated price quoted without saying so"
    return None


def _evidence_is_simulated(evidence_text: str) -> bool:
    compact = evidence_text.replace(" ", "").lower()
    return '"simulated_inputs":true' in compact or '"simulated":true' in compact


def text_verdict(
    text: str,
    *,
    evidence_text: str,
    simulated: bool | None = None,
    max_sentences: int = MAX_SENTENCES,
    max_chars: int = MAX_CHARS,
    max_words: int | None = None,
    language: str | None = None,
) -> Verdict:
    """Every content check over plain model text. See the module text. With ``language`` the
    reply must be written in it (the interface's language), else the rule text stands."""

    if not text or not text.strip():
        return Verdict(False, "empty")
    if language is not None and not language_ok(text, language):
        return Verdict(False, "language", f"not written in {language}")
    if len(text) > max_chars:
        return Verdict(False, "length", f"{len(text)} characters")
    if max_words is not None:
        words = len(re.findall(r"[A-Za-z0-9][\w./%-]*", text)) + len(
            re.findall(r"[一-鿿]", text)
        ) // 2
        if words > max_words:
            return Verdict(False, "length", f"{words} words")
    sentences = 0
    for line in (line for line in text.splitlines() if line.strip()):
        sentences += max(1, len(re.findall(r"[.!?。！？](?:\s|$)", line + " ")))
    if sentences > max_sentences:
        return Verdict(False, "sentences", f"{sentences} sentences")
    # Every figure the model writes must be one it was given.
    new = _numbers(text) - _numbers(evidence_text)
    if new:
        return Verdict(False, "number", ", ".join(sorted(new)))
    if simulated is None:
        simulated = _evidence_is_simulated(evidence_text)
    style = _style_refusal(text, evidence_text, simulated)
    if style:
        return Verdict(False, *style)
    # And it must stay inside the evidence's hubs, units, directions and names.
    from eurogas_nexus.application.grounding import check_grounding

    grounding = check_grounding(text, evidence_text)
    if not grounding.ok:
        return Verdict(False, grounding.check, grounding.reason)
    return Verdict(True)


def note_verdict(
    content: str | None,
    *,
    evidence_text: str,
    sources: list[str],
    simulated: bool | None = None,
    language: str | None = None,
) -> Verdict:
    """The checks on a desk note returned as ``{"text": ..., "cites": [...]}``."""

    if not content:
        return Verdict(False, "empty")
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`").removeprefix("json").strip()
    try:
        payload = json.loads(candidate)
    except ValueError:
        return Verdict(False, "format", "not JSON")
    if not isinstance(payload, dict):
        return Verdict(False, "format", "not a JSON object")
    text = " ".join(str(payload.get("text") or "").split())
    cites = tuple(str(item) for item in payload.get("cites") or [] if str(item).strip())
    if not text:
        return Verdict(False, "empty")
    if len(text) > MAX_CHARS:
        return Verdict(False, "length", f"{len(text)} characters")
    if not cites or not set(cites) <= set(sources):
        return Verdict(False, "cites", ", ".join(sorted(set(cites) - set(sources))) or "none")
    verdict = text_verdict(text, evidence_text=evidence_text, simulated=simulated,
                           language=language)
    if not verdict.ok:
        return verdict
    return Verdict(True, note=CheckedNote(text=text, cites=cites))


def checked_note(
    content: str | None,
    *,
    evidence_text: str,
    sources: list[str],
    simulated: bool | None = None,
    language: str | None = None,
) -> CheckedNote | None:
    """The model's note if it passes every check, else ``None``."""

    return note_verdict(
        content, evidence_text=evidence_text, sources=sources, simulated=simulated,
        language=language,
    ).note


def answer_verdict(
    content: str | None, *, evidence_text: str, simulated: bool | None = None,
    language: str | None = None,
) -> Verdict:
    """The checks on a plain-text answer to a question (``ANSWER_RULES``)."""

    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    return text_verdict(
        text,
        evidence_text=evidence_text,
        simulated=simulated,
        max_sentences=ANSWER_MAX_SENTENCES,
        max_chars=ANSWER_MAX_CHARS,
        max_words=ANSWER_MAX_WORDS,
        language=language,
    )


def checked_answer(
    content: str | None, *, evidence_text: str, simulated: bool | None = None,
    language: str | None = None,
) -> str | None:
    """The model's answer if it passes every check, else ``None``."""

    if answer_verdict(content, evidence_text=evidence_text, simulated=simulated,
                      language=language).ok:
        return (content or "").strip()
    return None
