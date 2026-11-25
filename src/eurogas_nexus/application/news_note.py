""""What this means for my book": a short note over one news item, cited sentence by sentence.

The evidence is deterministic and numbered: ``N1`` the item itself (publisher, time, title and
what was kept of its text), ``N2`` ... related items (the same held outage, or the same asset
and event type within :data:`RELATED_HOURS`), and ``F1`` ... the platform's own figures: the
REMIT message the item is linked to (unavailable and technical capacity as the message states
them) and each exposure of the caller's book the item touches (``news_relevance``). Every
sentence of the note cites the lines it rests on.

Two notes, one shape (``sentences``: text with cites):

* :func:`rule_note`, always: the item, the outage figures if linked, and one sentence per
  exposure touched. It needs no model, so the panel works with AI off (rule H5).
* :func:`model_note`, when the AI use ``news_note`` is on for the organisation, the deployment
  has a provider and the caller holds the analysis capability: the model condenses the same
  lines into at most five sentences, which :func:`application.news_grounding.check_note` checks
  sentence by sentence against the lines each one cites. A refused note is never shown; the
  rule note stands and the response says the model's note was refused and why.

Every note is labelled: ``basis`` ``rule`` or ``model``, and a model note carries
``label`` "AI-generated" and the prompt version. Neither note advises a trade (the desk checks
refuse advice); a person decides.

新闻"对我的账簿意味着什么"：规则文本始终可用；模型简述逐句引用、逐句校验，未通过则不显示。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from eurogas_nexus.application.ai_style import language_rule

RELATED_HOURS = 48
MAX_RELATED = 3
MAX_FIGURES = 6
AI_LABEL = "AI-generated"
AI_LABEL_ZH = "AI 生成"

#: The instruction the model gets (the register's prompt reference; bump its version with it).
NEWS_NOTE_RULES = (
    "You write a note for a commercial gas desk on what one news item means for the reader's "
    "book. Use only the numbered lines supplied: N lines are news items, F lines are the "
    "platform's own figures. Write at most four short sentences, the fact first. Every "
    "sentence cites the ids of the lines it rests on, and says only what those cited lines "
    "state: never add a number, date, hub, unit, name, cause or source that is not in them, "
    "and do not compute new figures. Say plainly when an item is a report and not a "
    "confirmed figure. Never recommend, describe or imply buying, selling, hedging, "
    "nominating or any other trade or order; a person decides. No preamble, no markdown."
)
_OUTPUT = (
    'Return JSON only: {"sentences": [{"text": "<one sentence>", "cites": ["N1", "F1"]}]}.'
)


@dataclass
class Evidence:
    """The numbered lines for one item, as the model and the checks see them."""

    lines: dict[str, str] = field(default_factory=dict)
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, prefix: str, text: str, source: dict[str, Any]) -> str:
        count = sum(1 for key in self.lines if key.startswith(prefix)) + 1
        key = f"{prefix}{count}"
        self.lines[key] = text
        self.sources[key] = source
        return key


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _when(value: datetime | None) -> str:
    moment = _aware(value)
    return f"{moment:%d %b %Y %H:%M} UTC" if moment else "time not stated"


def item_line(item: dict[str, Any]) -> str:
    """One item as a line: publisher, time, title and the kept summary."""

    published = item.get("published_at_utc")
    if isinstance(published, str):
        published = datetime.fromisoformat(published)
    body = f"{item['publisher']}, {_when(published)}: {item['title']}."
    if item.get("summary"):
        body += f" {item['summary']}"
    return body


def _citation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "item",
        "item_id": item["item_id"],
        "url": item.get("url"),
        "publisher": item["publisher"],
        "source_id": item["source_id"],
        "published_at_utc": item.get("published_at_utc"),
    }


def related_items(session, row) -> list[Any]:
    """Other items on the same held outage, or the same asset and event type, nearby in time."""

    from eurogas_nexus.db.models import NewsItemRecord

    out = []
    if row.linked_event_key:
        out = (
            session.query(NewsItemRecord)
            .filter(NewsItemRecord.linked_event_key == row.linked_event_key,
                    NewsItemRecord.item_id != row.item_id)
            .order_by(NewsItemRecord.published_at_utc.desc())
            .limit(MAX_RELATED)
            .all()
        )
    if len(out) >= MAX_RELATED:
        return out
    assets = {e.get("entity_id") for e in row.entities or [] if e.get("kind") in
              {"terminal", "pipeline", "field", "vessel"}}
    kinds = set(row.event_types or [])
    published = _aware(row.published_at_utc)
    if not assets or not kinds or published is None:
        return out
    window = timedelta(hours=RELATED_HOURS)
    naive = session.get_bind().dialect.name == "sqlite"
    low, high = published - window, published + window
    if naive:
        low, high = low.replace(tzinfo=None), high.replace(tzinfo=None)
    held = {item.item_id for item in out} | {row.item_id}
    for other in (
        session.query(NewsItemRecord)
        .filter(NewsItemRecord.published_at_utc >= low, NewsItemRecord.published_at_utc <= high)
        .order_by(NewsItemRecord.published_at_utc.desc())
        .limit(200)
    ):
        if other.item_id in held:
            continue
        theirs = {e.get("entity_id") for e in other.entities or []}
        if assets & theirs and kinds & set(other.event_types or []):
            out.append(other)
            held.add(other.item_id)
        if len(out) >= MAX_RELATED:
            break
    return out


def outage_figure(session, linked_event_key: str | None) -> tuple[str, dict[str, Any]] | None:
    """The held REMIT message an item is linked to, as one line with its figures as stated."""

    from eurogas_nexus.application.news_ingest import remit_text
    from eurogas_nexus.db.models import RemitUmmRecord

    if not linked_event_key or not linked_event_key.startswith("outage:"):
        return None
    message_id = linked_event_key.partition(":")[2]
    row = (
        session.query(RemitUmmRecord)
        .filter(RemitUmmRecord.message_id == message_id)
        .order_by(RemitUmmRecord.version.desc())
        .first()
    )
    if row is None:
        return None
    title, summary = remit_text(row)
    text = f"REMIT message {row.message_id} by {row.market_participant}: {title}. {summary}"
    return text, {"kind": "outage", "event_key": linked_event_key, "message_id": message_id,
                  "version": int(row.version), "source_reference": row.source_reference}


def build_evidence(session, item: dict[str, Any], found: list[dict[str, Any]], row=None
                   ) -> Evidence:
    """The numbered lines for ``item`` and the book matches ``found`` (see the module text)."""

    evidence = Evidence()
    evidence.add("N", item_line(item), _citation(item))
    if row is not None:
        from eurogas_nexus.application.news_reads import item_dict

        for other in related_items(session, row):
            other_item = item_dict(other)
            evidence.add("N", item_line(other_item), _citation(other_item))
    outage = outage_figure(session, item.get("linked_event_key"))
    if outage is not None:
        evidence.add("F", outage[0], outage[1])
    for match in found[:MAX_FIGURES]:
        evidence.add(
            "F",
            f"Book {match['book_id'] or 'unassigned'}: {match['figure']}.",
            {"kind": match["kind"], "ref": match["ref"], "book_id": match["book_id"],
             "source": match["source"]},
        )
    return evidence


def rule_note(item: dict[str, Any], found: list[dict[str, Any]], evidence: Evidence
              ) -> list[dict[str, Any]]:
    """The deterministic note: the item, its outage figures, each exposure touched."""

    sentences = [
        {
            "text": f"{item['publisher']} published \"{item['title']}\" at "
            f"{_when(_parse(item.get('published_at_utc')))}.",
            "cites": ["N1"],
        }
    ]
    outage_key = next((k for k, s in evidence.sources.items() if s.get("kind") == "outage"),
                      None)
    if outage_key is not None:
        sentences.append(
            {"text": f"The platform holds the operator's own message: "
                     f"{evidence.lines[outage_key].split(': ', 1)[-1]}",
             "cites": [outage_key]}
        )
    figure_keys = [k for k, s in evidence.sources.items() if k.startswith("F")
                   and s.get("kind") != "outage"]
    for key, match in zip(figure_keys, found, strict=False):
        sentences.append(
            {
                "text": f"It {match['reason']}; in book {match['book_id'] or 'unassigned'}, "
                f"{match['figure']}.",
                "cites": ["N1", key],
            }
        )
    if not found:
        sentences.append({"text": "It touches no contract, cargo or nomination in the books "
                                  "you can see.", "cites": ["N1"]})
    return sentences


def _parse(value: Any) -> datetime | None:
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def note_messages(evidence: Evidence, *, language: str) -> list[dict[str, str]]:
    """System and user messages for the model's note over the numbered lines."""

    return [
        {"role": "system",
         "content": f"{NEWS_NOTE_RULES} {language_rule(language)} {_OUTPUT}"},
        {"role": "user",
         "content": json.dumps({"lines": evidence.lines}, ensure_ascii=False)},
    ]


def model_note(model, evidence: Evidence, *, language: str) -> dict[str, Any]:
    """Call the model once and check its note; ``{"status", "sentences", "flags", ...}``."""

    from eurogas_nexus.application.news_grounding import check_note

    content = model(note_messages(evidence, language=language))
    if content is None:
        return {"status": "unavailable", "sentences": None, "flags": [], "check": "no_reply"}
    checked = check_note(content, evidence.lines, language=language)
    if not checked.ok:
        return {"status": "refused", "sentences": None, "flags": checked.flags,
                "check": checked.check, "detail": checked.detail}
    return {
        "status": "used",
        "sentences": [{"text": s.text, "cites": list(s.cites)} for s in checked.sentences],
        "flags": [],
        "check": None,
    }


def assemble(item: dict[str, Any], found: list[dict[str, Any]], evidence: Evidence, *,
             ai: dict[str, Any] | None, prompt_version: str, language: str) -> dict[str, Any]:
    """The note the reader gets: the model's when it passed, otherwise the rule note."""

    rule = rule_note(item, found, evidence)
    used = ai is not None and ai.get("status") == "used"
    citations = [{"id": key, **source, "text": evidence.lines[key]}
                 for key, source in evidence.sources.items()]
    return {
        "basis": "model" if used else "rule",
        "label": (AI_LABEL_ZH if language.startswith("zh") else AI_LABEL) if used else None,
        "sentences": ai["sentences"] if used else rule,
        "rule_sentences": rule,
        "citations": citations,
        "ai": {
            "status": "off" if ai is None else ai["status"],
            "check": None if ai is None else ai.get("check"),
            "flags": [] if ai is None else ai.get("flags", []),
            "prompt_version": prompt_version if ai is not None else None,
        },
        "advisory": "Decision support: a person decides; nothing is traded, nominated or sent.",
    }


__all__ = [
    "AI_LABEL",
    "NEWS_NOTE_RULES",
    "Evidence",
    "assemble",
    "build_evidence",
    "item_line",
    "model_note",
    "note_messages",
    "outage_figure",
    "related_items",
    "rule_note",
]
