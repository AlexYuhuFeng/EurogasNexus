"""How the model writes for a trading desk, and the checks its text must pass.

Traders read in seconds, between prices. Every model output in Eurogas Nexus is a desk
note: at most three short sentences, figures with units, the fact first, no preamble, no
filler, no advice to trade. The model is given the deterministic facts and may only
reorder, condense and connect them. Its text is shown only if it passes
:func:`checked_note`: valid JSON, within length, citing only the sources it was given,
with no number that is not in the evidence, and grounded in the ontology
(``application/grounding.py``): no hub, unit, direction, superlative or name the evidence
does not contain. Otherwise the rule text stands.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MAX_SENTENCES = 3
MAX_CHARS = 360

#: The common system instruction. Each use adds only its task and output fields.
DESK_NOTE_RULES = (
    "You write desk notes for commercial gas traders and risk managers. Rules: "
    "at most three short sentences, under 60 words in total. "
    "Lead with the fact that matters, then why it matters, then what to check. "
    "Use only the facts supplied; never add a number, date, name or source that is not in "
    "them. Keep units as given (GWh/d, MWh, EUR/MWh, p/th). "
    "No preamble, no restating the question, no hedging filler, no markdown. "
    "Never recommend or describe executing a trade, nomination or settlement. "
    "If the facts are not enough, say in one sentence what is missing."
)

#: For an answer to a question (alert analysis, Copilot, Ask): a little more room, same style.
ANSWER_RULES = (
    "You answer commercial gas traders and risk managers between trades. Rules: "
    "the answer first, in at most five short sentences or five bullet lines, under 100 "
    "words. Figures with their units and dates. Use only the facts supplied and cite "
    "them; never invent a number, name or source. Say plainly what is fact, what is "
    "simulated and what is missing. No preamble, no restating the question, no filler. "
    "Never recommend or describe executing a trade, nomination or settlement; a person "
    "decides."
)

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass(frozen=True)
class CheckedNote:
    text: str
    cites: tuple[str, ...]


def note_messages(task: str, facts: dict, *, language: str) -> list[dict[str, str]]:
    """System and user messages for one desk note over ``facts``."""

    language_rule = (
        "Write in Simplified Chinese." if language.lower().startswith("zh") else "Write in English."
    )
    return [
        {
            "role": "system",
            "content": (
                f"{DESK_NOTE_RULES} {language_rule} {task} "
                'Return JSON only: {"text": "<the note>", "cites": ["<source ids used>"]}.'
            ),
        },
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)},
    ]


def _numbers(text: str) -> set[str]:
    return {match.replace(",", "") for match in _NUMBER.findall(text or "")}


def checked_note(
    content: str | None, *, evidence_text: str, sources: list[str]
) -> CheckedNote | None:
    """The model's note if it passes every check, else ``None``."""

    if not content:
        return None
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`").removeprefix("json").strip()
    try:
        payload = json.loads(candidate)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    text = " ".join(str(payload.get("text") or "").split())
    cites = tuple(str(item) for item in payload.get("cites") or [] if str(item).strip())
    if not text or len(text) > MAX_CHARS:
        return None
    if len(re.findall(r"[.!?。！？](?:\s|$)", text + " ")) > MAX_SENTENCES:
        return None
    if not cites or not set(cites) <= set(sources):
        return None
    # Every figure the model writes must be one it was given.
    if not _numbers(text) <= _numbers(evidence_text):
        return None
    # And it must stay inside the evidence's hubs, units, directions and names.
    from eurogas_nexus.application.grounding import check_grounding

    if not check_grounding(text, evidence_text).ok:
        return None
    return CheckedNote(text=text, cites=cites)
