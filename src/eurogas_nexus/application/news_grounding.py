"""The grounding check on a "what this means for my book" note: every sentence cited, every
claim supported by what it cites (NEWS-1).

The note is a list of sentences, each with the ids of the evidence lines it rests on: news
items (``N1`` ...) and the platform's own figures (``F1`` ...). :func:`check_note` refuses the
whole note when any sentence

* cites nothing, or cites an id it was not given (``cites``);
* is longer than one sentence or :data:`MAX_SENTENCE_CHARS` (``length``);
* fails the desk checks against **only the lines it cites** (``ai_style.text_verdict``): a
  number, hub, unit, direction, superlative, source or name those lines do not contain, advice
  to buy, sell, hedge or nominate, or a reply in another language than asked.

and refuses a note with no sentence citing a news item (``no_item``), more than
:data:`MAX_SENTENCES` sentences, or output that is not the JSON asked for (``format``).
Checking each sentence against its own cited lines, not the whole evidence, is what makes a
citation mean something: a figure from line ``F2`` in a sentence that cites only ``N1`` is
refused. The result names each sentence's verdict (flags), so the reader and the evaluation
set see which sentence was unsupported and why. On a refusal the deterministic note stands.

Nothing here calls a model.

依据校验：逐句检查引用是否存在、是否只依据所引条目（数字、枢纽、单位、方向、名称、建议），
任一句不受支持即整体拒绝，回退到规则文本。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_SENTENCES = 5
MAX_SENTENCE_CHARS = 300
_ID = re.compile(r"^[NF]\d{1,2}$")


@dataclass(frozen=True)
class SentenceVerdict:
    text: str
    cites: tuple[str, ...]
    ok: bool
    check: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "cites": list(self.cites), "ok": self.ok,
                "check": self.check or None, "detail": self.detail or None}


@dataclass(frozen=True)
class NoteCheck:
    ok: bool
    check: str = ""
    detail: str = ""
    sentences: tuple[SentenceVerdict, ...] = field(default=())

    @property
    def flags(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in self.sentences if not s.ok]


def _payload(content: str | None) -> Any:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


def check_note(content: str | None, lines: dict[str, str], *, language: str | None = None
               ) -> NoteCheck:
    """Check a model's note against the evidence ``lines`` (id -> text). See the module text."""

    from eurogas_nexus.application.ai_style import text_verdict

    if not content or not content.strip():
        return NoteCheck(False, "empty")
    try:
        payload = _payload(content)
    except ValueError:
        return NoteCheck(False, "format", "not JSON")
    raw = payload.get("sentences") if isinstance(payload, dict) else None
    if not isinstance(raw, list) or not raw:
        return NoteCheck(False, "format", "no sentences list")
    if len(raw) > MAX_SENTENCES:
        return NoteCheck(False, "sentences", f"{len(raw)} sentences")
    verdicts: list[SentenceVerdict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            return NoteCheck(False, "format", "a sentence is not an object")
        text = " ".join(str(entry.get("text") or "").split())
        cites = tuple(str(c).strip() for c in entry.get("cites") or [] if str(c).strip())
        if not text:
            verdicts.append(SentenceVerdict(text, cites, False, "empty"))
            continue
        unknown = [c for c in cites if not _ID.match(c) or c not in lines]
        if not cites or unknown:
            verdicts.append(SentenceVerdict(text, cites, False, "cites",
                                            ", ".join(unknown) or "no citation"))
            continue
        if len(text) > MAX_SENTENCE_CHARS:
            verdicts.append(SentenceVerdict(text, cites, False, "length",
                                            f"{len(text)} characters"))
            continue
        evidence = "\n".join(lines[c] for c in cites)
        verdict = text_verdict(text, evidence_text=evidence, simulated=False, max_sentences=1,
                               max_chars=MAX_SENTENCE_CHARS, language=language)
        verdicts.append(SentenceVerdict(text, cites, verdict.ok, verdict.check, verdict.detail))
    failed = [v for v in verdicts if not v.ok]
    if failed:
        return NoteCheck(False, failed[0].check, failed[0].detail, tuple(verdicts))
    if not any(c.startswith("N") for v in verdicts for c in v.cites):
        return NoteCheck(False, "no_item", "no sentence cites a news item", tuple(verdicts))
    return NoteCheck(True, sentences=tuple(verdicts))


__all__ = ["MAX_SENTENCES", "MAX_SENTENCE_CHARS", "NoteCheck", "SentenceVerdict", "check_note"]
