"""Ontology grounding for model text: what a note may say, checked against the evidence.

The model is given deterministic facts and may only condense them. ``ai_style.checked_note``
already refuses text that cites a foreign source or contains a number the evidence lacks.
That leaves the errors a trader would act on: the right number with the wrong unit, the
wrong hub, "long" for "short", a superlative nobody measured, a counterparty that is not in
the facts. This module checks those against the ontology's vocabulary and the evidence:

- **Terms.** A hub (code or alias from the market reference model) may appear in the note
  only if the evidence names it.
- **Units.** A number followed by a unit must appear in the evidence followed by the same
  unit; a unit the evidence never uses may not appear at all.
- **Direction.** A direction word (long/short, above/below, rise/fall and their Chinese
  forms) may appear only if the evidence uses a word of the same sense, and never when the
  evidence uses only the opposite one.
- **Superlatives.** "record", "highest", "unprecedented" and the like only if the evidence
  says so.
- **Names.** A capitalised name inside a sentence must come from the evidence.

Every check is conservative: a failure returns the reason and the caller shows the rule
text. Nothing here calls a model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from eurogas_nexus.domain.ontology.identity import _hub_names
from eurogas_nexus.domain.ontology.quantity import UNITS

_ENGLISH_HUB_WORDS = frozenset({"THE"})

#: Unit spellings a desk writes, beyond the ontology's bare codes.
_RATE = r"(?:/(?:d|day|h|hour|month|year|a))?"
_UNIT_CODES = sorted(
    {*UNITS, "therm", "therms", "p/th", "GBp/th", "EUR/MWh", "GBP/MWh", "USD/MWh",
     "USD/MMBtu", "EUR/GJ", "EUR/t", "mcm", "bcm", "%"},
    key=len,
    reverse=True,
)
_UNIT = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(code) for code in _UNIT_CODES) + r")" + _RATE
    + r"(?![A-Za-z])"
)
_NUMBER = r"[-+−]?\d+(?:[.,]\d+)*"
_NUMBER_UNIT = re.compile(
    rf"({_NUMBER})\s?([kmbKMB]n?)?\s?(" + "|".join(re.escape(c) for c in _UNIT_CODES) + r")"
    + f"({_RATE})" + r"(?![A-Za-z])"
)
_MONEY = re.compile(rf"([€£$])\s?({_NUMBER})\s?([kmbKMB]n?)?")

#: Direction senses: a note may use a word only if the evidence uses the same sense.
_DIRECTIONS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("position", ("long", "多头", "做多"), ("short", "空头", "做空")),
    ("level", ("above", "over", "exceed", "exceeds", "exceeded", "高于", "超过", "超出"),
     ("below", "under", "beneath", "低于", "不足")),
    ("move", ("rose", "rise", "rises", "risen", "up", "increase", "increased", "higher",
              "gain", "gained", "上涨", "上升", "增加"),
     ("fell", "fall", "falls", "fallen", "down", "decrease", "decreased", "lower", "drop",
      "dropped", "lost", "下跌", "下降", "减少")),
    ("balance", ("surplus", "盈余", "过剩"), ("deficit", "shortfall", "缺口", "短缺")),
)
_SUPERLATIVES = (
    "record", "highest", "lowest", "largest", "smallest", "biggest", "unprecedented",
    "all-time", "ever", "worst", "best", "最高", "最低", "最大", "最小", "创纪录", "历史",
)
_NAME = re.compile(r"(?<=[a-z0-9,;:)\]] )([A-Z][A-Za-z&'.-]{2,}(?: [A-Z][A-Za-z&'.-]+)*)")


@dataclass(frozen=True)
class Grounding:
    ok: bool
    reason: str = ""


def _norm_number(text: str) -> str:
    return text.replace(",", "").replace("−", "-").lstrip("+")


def _words(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[A-Za-z][A-Za-z-]*", text)}


def _hubs_in(text: str) -> set[str]:
    names = _hub_names()
    found = set()
    for word in re.findall(r"[A-Za-z0-9_]+", text):
        key = word.upper()
        if key in names and (key not in _ENGLISH_HUB_WORDS or word.isupper()):
            found.add(names[key][0])
    return found


def _number_units(text: str) -> set[tuple[str, str]]:
    pairs = set()
    for number, scale, unit, rate in _NUMBER_UNIT.findall(text):
        pairs.add((_norm_number(number) + (scale or "").lower(), (unit + rate).lower()))
    for sign, number, scale in _MONEY.findall(text):
        pairs.add((_norm_number(number) + (scale or "").lower(), sign))
    return pairs


def _senses(text: str) -> dict[str, set[str]]:
    """Which side of each direction sense the text uses: ``{"position": {"+"}}``."""

    lower, words = text.lower(), _words(text)
    used: dict[str, set[str]] = {}
    for sense, positive, negative in _DIRECTIONS:
        for side, vocabulary in (("+", positive), ("-", negative)):
            for word in vocabulary:
                hit = word in words if word.isascii() else word in lower
                if hit:
                    used.setdefault(sense, set()).add(side)
    return used


def check_grounding(note: str, evidence_text: str) -> Grounding:
    """Whether ``note`` stays inside what ``evidence_text`` states. See the module text."""

    foreign_hubs = _hubs_in(note) - _hubs_in(evidence_text)
    if foreign_hubs:
        return Grounding(False, f"hub not in the evidence: {', '.join(sorted(foreign_hubs))}")

    evidence_units = {match.group(0).lower() for match in _UNIT.finditer(evidence_text)}
    for match in _UNIT.finditer(note):
        if match.group(0).lower() not in evidence_units:
            return Grounding(False, f"unit not in the evidence: {match.group(0)}")
    evidence_pairs = _number_units(evidence_text)
    for pair in _number_units(note):
        if pair not in evidence_pairs:
            return Grounding(False, f"number with a unit the evidence does not give: {pair}")

    evidence_senses = _senses(evidence_text)
    for sense, sides in _senses(note).items():
        if not sides <= evidence_senses.get(sense, set()):
            return Grounding(False, f"direction not stated in the evidence: {sense}")

    lower_note, lower_evidence = note.lower(), evidence_text.lower()
    note_words = _words(note)
    for word in _SUPERLATIVES:
        present = word in note_words if word.isascii() and "-" not in word else word in lower_note
        if present and word not in lower_evidence:
            return Grounding(False, f"superlative not in the evidence: {word}")

    for raw in _NAME.findall(note):
        name = raw.rstrip(".'-")
        if name.lower() not in lower_evidence and name.upper() not in _hub_names():
            return Grounding(False, f"name not in the evidence: {name}")
    return Grounding(True)
