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
- **Names and sources.** A capitalised name inside a sentence, an acronym anywhere, or a
  known data source or publisher (Reuters, ICIS, ENTSOG ...) must come from the evidence.
- **Figures in their clause.** A direction word next to a figure must match the direction
  the evidence gives *that* figure (its own clause, or its sign: ``-0.51 on the day`` is a
  fall), and a hub named next to a figure must be a hub the evidence names with it. Without
  this, evidence that has NBP up and TTF down would let a note say "TTF rose".
- **Chinese units.** Unit spellings in Chinese (吉瓦时/天, 便士/色姆 ...) are read as their
  codes before the unit checks, so a Chinese note cannot swap units unseen.

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
_RECORD_CLAIM = (
    r"\b(?:a|new|at a|all-time) record\b|\brecord[- ](?:high|low|levels?|outage|flows?|"
    r"demand|prices?|spread|withdrawals?|injections?|imports?|exports?|send-?out)\b"
)
_NAME = re.compile(r"(?<=[a-z0-9,;:)\]] )([A-Z][A-Za-z&'.-]{2,}(?: [A-Z][A-Za-z&'.-]+)*)")


@dataclass(frozen=True)
class Grounding:
    ok: bool
    reason: str = ""
    #: The check that refused: hub, unit, number_unit, direction, superlative, name, source.
    check: str = ""


#: Data sources and publishers a model might invent as a citation. Matched in any case,
#: anywhere in the note (a sentence-initial "Reuters says" is not caught by the name rule).
_SOURCE_NAMES = (
    "reuters", "bloomberg", "platts", "argus", "icis", "montel", "refinitiv", "lseg",
    "trayport", "eex", "ice", "entsog", "gie", "agsi", "alsi", "acer", "ofgem", "elexon",
    "kpler", "vortexa", "equinor", "gassco", "gazprom", "gasunie", "fluxys", "snam",
    "national gas", "s&p", "spglobal", "financial times", "the times",
)
#: Acronyms a desk note may use without the evidence spelling them.
_ACRONYM_OK = frozenset(
    {"UTC", "EUR", "GBP", "USD", "CET", "CEST", "GMT", "LNG", "OK", "MTM", "OTC"}
)
_ACRONYM = re.compile(r"(?<![A-Za-z])([A-Z][A-Z&]{2,})(?![A-Za-z])")

#: Chinese unit spellings -> the code the evidence uses. Longest first.
_ZH_UNITS = (
    ("欧元/兆瓦时", "EUR/MWh"), ("英镑/兆瓦时", "GBP/MWh"), ("美元/百万英热单位", "USD/MMBtu"),
    ("便士/色姆", "p/th"), ("便士/撒姆", "p/th"), ("吉瓦时", "GWh"), ("兆瓦时", "MWh"),
    ("千瓦时", "kWh"), ("太瓦时", "TWh"), ("百万立方米", "mcm"), ("十亿立方米", "bcm"),
    ("色姆", "th"), ("/天", "/d"), ("每天", "/d"), ("/日", "/d"),
)

_SENTENCE = re.compile(r'["\n;；。！？]|[.!?](?=\s|$)')
_CLAUSE = re.compile(
    r'["\n;；。！？，、]|[.!?](?=\s|$)|,\s|\s(?:and|but|while|whereas|as|with)\s|而|但'
)
_SIGNED = re.compile(r"(?:^|(?<=[\s(\[:\"]))([-+−])[€£$]?(\d+(?:[.,]\d+)*)")
_PLAIN_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _norm_number(text: str) -> str:
    return text.replace(",", "").replace("−", "-").lstrip("+")


def _key(number: str) -> str:
    value = number.replace(",", "")
    return (value.lstrip("0") or "0") if value.isdigit() else value


def _zh_units(text: str) -> str:
    for zh, code in _ZH_UNITS:
        text = text.replace(zh, f" {code}" if not code.startswith("/") else code)
    return text


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


#: Spellings of one unit (the registry's ``GBp/th`` is the desk's ``p/th``).
_UNIT_SAME = {"gbp/th": "p/th"}


def _unit_key(unit: str) -> str:
    lower = unit.lower()
    return _UNIT_SAME.get(lower, lower)


def _number_units(text: str) -> set[tuple[str, str]]:
    pairs = set()
    for number, scale, unit, rate in _NUMBER_UNIT.findall(text):
        pairs.add((_norm_number(number) + (scale or "").lower(), _unit_key(unit + rate)))
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


def _signed_moves(text: str) -> dict[str, set[str]]:
    """Figures the evidence writes with a sign (``-0.51 on the day``): their move side."""

    moves: dict[str, set[str]] = {}
    for sign, number in _SIGNED.findall(text):
        moves.setdefault(_key(number), set()).add("+" if sign == "+" else "-")
    return moves


def _pieces(text: str, pattern: re.Pattern[str]) -> list[str]:
    return [piece for piece in pattern.split(text) if piece and piece.strip()]


def _figure_index(evidence: str, pattern: re.Pattern[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for piece in _pieces(evidence, pattern):
        for number in _PLAIN_NUMBER.findall(piece):
            index.setdefault(_key(number), []).append(piece)
    return index


def _clause_refusal(note: str, evidence: str) -> Grounding | None:
    """Direction and hub of each figure, clause by clause (see the module text)."""

    clauses = _figure_index(evidence, _CLAUSE)
    sentences = _figure_index(evidence, _SENTENCE)
    signed = _signed_moves(evidence)
    for clause in _pieces(note, _CLAUSE):
        numbers = {_key(n) for n in _PLAIN_NUMBER.findall(clause)}
        if not numbers:
            continue
        senses = _senses(clause)
        hubs = _hubs_in(clause)
        for number in numbers:
            for sense, sides in senses.items():
                given: set[str] = set()
                for piece in clauses.get(number, []):
                    given |= _senses(piece).get(sense, set())
                if sense == "move":
                    given |= signed.get(number, set())
                if given and not sides <= given:
                    return Grounding(
                        False,
                        f"direction of {number} is not what the evidence gives ({sense})",
                        "direction",
                    )
            if hubs:
                pieces = sentences.get(number, [])
                with_hubs = [_hubs_in(piece) for piece in pieces]
                if pieces and all(with_hubs) and not any(h & hubs for h in with_hubs):
                    return Grounding(
                        False, f"{number} belongs to another hub in the evidence", "hub"
                    )
    return None


def check_grounding(note: str, evidence_text: str) -> Grounding:
    """Whether ``note`` stays inside what ``evidence_text`` states. See the module text."""

    note = _zh_units(note)
    foreign_hubs = _hubs_in(note) - _hubs_in(evidence_text)
    if foreign_hubs:
        return Grounding(
            False, f"hub not in the evidence: {', '.join(sorted(foreign_hubs))}", "hub"
        )

    evidence_units = {_unit_key(match.group(0)) for match in _UNIT.finditer(evidence_text)}
    for match in _UNIT.finditer(note):
        if _unit_key(match.group(0)) not in evidence_units:
            return Grounding(False, f"unit not in the evidence: {match.group(0)}", "unit")
    evidence_pairs = _number_units(evidence_text)
    for pair in _number_units(note):
        if pair not in evidence_pairs:
            return Grounding(
                False, f"number with a unit the evidence does not give: {pair}", "number_unit"
            )

    evidence_senses = _senses(evidence_text)
    for number, sides in _signed_moves(evidence_text).items():
        if number:
            evidence_senses.setdefault("move", set()).update(sides)
    for sense, sides in _senses(note).items():
        if not sides <= evidence_senses.get(sense, set()):
            return Grounding(False, f"direction not stated in the evidence: {sense}", "direction")
    clause = _clause_refusal(note, evidence_text)
    if clause is not None:
        return clause

    lower_note, lower_evidence = note.lower(), evidence_text.lower()
    note_words = _words(note)
    for word in _SUPERLATIVES:
        present = word in note_words if word.isascii() and "-" not in word else word in lower_note
        if word == "record" and present:
            # "the ENTSOG point record" is a noun; "a record low", "record demand" is a claim.
            present = re.search(_RECORD_CLAIM, lower_note) is not None
        if present and word not in lower_evidence:
            return Grounding(False, f"superlative not in the evidence: {word}", "superlative")

    for source in _SOURCE_NAMES:
        pattern = rf"(?<![A-Za-z]){re.escape(source)}(?![A-Za-z])"
        if re.search(pattern, lower_note) and not re.search(pattern, lower_evidence):
            return Grounding(False, f"source not in the evidence: {source}", "source")
    hubs = _hub_names()
    for acronym in _ACRONYM.findall(note):
        if acronym in _ACRONYM_OK or acronym in hubs or acronym.lower() in lower_evidence:
            continue
        return Grounding(False, f"name not in the evidence: {acronym}", "name")
    # Per sentence: "14 Nov. That" is a date and a new sentence, not a name.
    for raw in (m for part in re.split(r"(?<=[.!?。])\s+", note) for m in _NAME.findall(part)):
        name = re.sub(r"['’]s$", "", raw.rstrip(".'-"))  # "Rhinmark's" is Rhinmark
        if name.lower() in lower_evidence or name.upper() in hubs or name in _ACRONYM_OK:
            continue
        # "TTF-to-THE", "ENTSOG Ellund": a name made of parts the evidence has is not new.
        # Only the capitalised parts name something ("ENTSOG-sourced" names ENTSOG).
        parts = [p for p in re.split(r"[\s-]+", name) if len(p) > 2 and p[0].isupper()
                 and p.lower() not in {"the", "and", "for", "via"}]
        if parts and all(p.lower() in lower_evidence or p.upper() in hubs for p in parts):
            continue
        return Grounding(False, f"name not in the evidence: {name}", "name")
    return Grounding(True)
