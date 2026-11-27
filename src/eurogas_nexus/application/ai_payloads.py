"""What each AI use sends to the provider, and nothing more (AI-04 payload minimisation).

Every provider call in Eurogas Nexus builds its user message from one of the functions
here or from the use's own ``*_payload`` function (``explain.model_payload``,
``desk_brief.lead_payload``). The field lists are the allowlist that
``tests/security/test_ai_payload_allowlist.py`` holds the outgoing messages to, and that
``docs/operations/LLM_MONITORING-EN.md`` ("Provider payloads and the evaluation set")
documents. A field is on the list only if the text the model writes can use it.

Identifiers (alert, entity, opportunity, route, counterparty, snapshot ids, fingerprints,
provider references) are never sent: the model cites ``S1``-style aliases or nothing, and
the platform keeps the mapping. Earlier model output (``llm_summary_*``) is never fed back.
"""

from __future__ import annotations

import json
from typing import Any

#: The alert fields an answer about one alert may use (``/api/monitoring/alerts/{id}/analysis``).
ALERT_ANSWER_FIELDS = (
    "category",
    "alert_type",
    "severity",
    "status",
    "title",
    "message",
    "event_time_utc",
    "occurrence_count",
    "evidence",
    "simulated",
)

#: The alert fields the background enrichment sends (``monitoring_service``).
ALERT_ENRICHMENT_FIELDS = (
    "category",
    "type",
    "severity",
    "title_en",
    "message_en",
    "evidence",
    "simulated",
)

#: One market-report section's commentary for rewording (``reports/rewrite.section_payload``):
#: the section title, its rule lines, its sources as ``S1`` aliases and two flags.
REPORT_SECTION_FIELDS = ("section", "lines", "sources", "simulated_inputs", "forecast")

#: The report editor's fact sheet (``reports/editor.fact_sheet_payload``): the report's kind,
#: audience, period and question; the facts (F-ids, labels, values, units, days, comparisons,
#: scores and reasons, states, rule sentences, derivable implications); each section's fact
#: ids and permitted exhibits; the At a glance menu; the length limits. No identifier, row or
#: book fact for an audience that may not see the book.
REPORT_EDITOR_FIELDS = ("report", "facts", "sections", "glance_menu", "limits", "cannot_tell")

#: A question to a report plan (``reports/plan.plan_payload``): the question, the catalogue's
#: section keys with one-line descriptions, hub and country codes, the audience. No figure.
REPORT_PLAN_FIELDS = ("question", "sections", "hubs", "countries", "audience")

#: A question from the answer bar (``desk_ask``): the question, the Today fact lines by topic
#: with their as-of dates written into the line, the sources as ``S1`` aliases, one flag.
ASK_FIELDS = ("question", "facts", "sources", "simulated_inputs")


def is_identifier(key: str) -> bool:
    """Whether a field name is an identifier or a provider reference, never sent."""

    lowered = key.lower()
    return (
        lowered == "id"
        or lowered.endswith("_id")
        or lowered.endswith("_ids")
        or lowered.endswith("_eic")
        or "fingerprint" in lowered
        or "reference" in lowered
        or lowered in {"source_refs", "principal", "actor", "raw"}
    )


def without_identifiers(value: Any) -> Any:
    """``value`` with every identifier field removed, recursively."""

    if isinstance(value, dict):
        return {
            key: without_identifiers(item)
            for key, item in value.items()
            if not is_identifier(str(key))
        }
    if isinstance(value, list | tuple):
        return [without_identifiers(item) for item in value]
    return value


def alert_for_answer(snapshot: dict[str, Any], language: str) -> dict[str, Any]:
    """One alert as an answer may see it: title and message in the reply language."""

    zh = language.lower().startswith("zh")
    return {
        "category": snapshot.get("category"),
        "alert_type": snapshot.get("alert_type"),
        "severity": snapshot.get("severity"),
        "status": snapshot.get("status"),
        "title": snapshot.get("title_zh_cn" if zh else "title_en"),
        "message": snapshot.get("message_zh_cn" if zh else "message_en"),
        "event_time_utc": snapshot.get("event_time_utc"),
        "occurrence_count": snapshot.get("occurrence_count"),
        "evidence": without_identifiers(dict(snapshot.get("evidence_snapshot") or {})),
        "simulated": bool(snapshot.get("simulated")),
    }


def alert_for_enrichment(alert: Any) -> dict[str, Any]:
    """One persisted alert as the background enrichment sends it."""

    return {
        "category": alert.category,
        "type": alert.alert_type,
        "severity": alert.severity,
        "title_en": alert.title_en,
        "message_en": alert.message_en,
        "evidence": without_identifiers(dict(alert.evidence_snapshot or {})),
        "simulated": bool(alert.simulated),
    }


def alert_answer_messages(
    snapshot: dict[str, Any], question: str, language: str
) -> list[dict[str, str]]:
    """The messages for an answer about one alert (``ANSWER_RULES``)."""

    from eurogas_nexus.application.ai_style import ANSWER_RULES, language_rule

    language_instruction = language_rule(language)
    return [
        {
            "role": "system",
            "content": (
                f"{ANSWER_RULES} Answer the analyst's question about the supplied alert "
                f"and its evidence only. {language_instruction}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"question": question, "alert": alert_for_answer(snapshot, language)},
                ensure_ascii=False,
                default=str,
            ),
        },
    ]


def ask_payload(question: str, lines: list[Any], *, simulated: bool) -> dict[str, Any]:
    """Exactly what an answer-bar question sends: ``ASK_FIELDS``, no identifiers.

    Each fact line is sent as ``"S<n>: <text>"`` so the model can cite it; the platform's
    own source ids (REMIT event ids, alert ids) stay on the platform.
    """

    from eurogas_nexus.application.ai_style import source_aliases

    sources = sorted({line.source for line in lines})
    alias = {source: key for key, source in source_aliases(sources).items()}
    facts: dict[str, list[str]] = {}
    for line in lines:
        facts.setdefault(line.topic, []).append(f"{alias[line.source]}: {line.text}")
    return {
        "question": question,
        "facts": facts,
        "sources": list(alias.values()),
        "simulated_inputs": simulated,
    }


def ask_messages(
    question: str, lines: list[Any], *, simulated: bool, language: str
) -> list[dict[str, str]]:
    """The messages for an answer-bar question (``ANSWER_RULES``)."""

    from eurogas_nexus.application.ai_style import ANSWER_RULES, language_rule

    language_instruction = language_rule(language)
    simulated_instruction = (
        " The facts use simulated prices: name that as their source once, and never call a "
        "simulated price a market price." if simulated else ""
    )
    return [
        {
            "role": "system",
            "content": (
                f"{ANSWER_RULES} Answer the trader's question from the supplied facts only, "
                "in two to five short sentences, with each figure's date as the fact gives "
                "it. Plain text, no source tags, and do not refer to 'the facts' or 'the "
                f"data'.{simulated_instruction} {language_instruction}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                ask_payload(question, lines, simulated=simulated),
                ensure_ascii=False,
                default=str,
            ),
        },
    ]


# ------------------------------------------------------------------ counterparty names (F)

#: How long the set of known counterparty names is reused before it is read again.
NAMES_TTL_SECONDS = 300.0
#: Shorter names are not replaced (they would match ordinary words).
MIN_NAME_LENGTH = 3
_NAMES_CACHE: dict[str, Any] = {"at": 0.0, "names": ()}


def _alias(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return f"Counterparty {letters}"


def known_counterparty_names(session: Any | None = None) -> tuple[str, ...]:
    """Every counterparty name the firm's records hold, longest first.

    Credit lines (name and the ETRM spellings in ``aliases``) and every table with a
    ``counterparty`` text column (deals, contracts, cargoes, nominations), so a table added
    later is covered without a change here. Read at most every :data:`NAMES_TTL_SECONDS`.
    """

    import time

    now = time.monotonic()
    if session is None and now - _NAMES_CACHE["at"] < NAMES_TTL_SECONDS:
        return _NAMES_CACHE["names"]
    names: set[str] = set()
    try:
        names = _read_names(session)
    except Exception:  # noqa: BLE001 - no store: nothing is known, and nothing is aliased
        names = set()
    ordered = tuple(sorted((n for n in names if len(n) >= MIN_NAME_LENGTH),
                           key=lambda n: (-len(n), n)))
    if session is None:
        _NAMES_CACHE.update(at=now, names=ordered)
    return ordered


def _read_names(session: Any | None) -> set[str]:
    from sqlalchemy import String, select

    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import CreditLineRecord

    if session is None:
        from eurogas_nexus.db.session import get_session_factory, resolve_database_url

        if resolve_database_url() is None:
            return set()
        with get_session_factory()() as own:
            return _read_names(own)
    from eurogas_nexus.security.portfolio_scope import system_scope

    names: set[str] = set()
    with system_scope():  # every book: a name must be hidden whoever's book it is in
        for name, aliases in session.execute(
            select(CreditLineRecord.name, CreditLineRecord.aliases)
        ):
            names.add(str(name).strip())
            names.update(str(alias).strip() for alias in (aliases or []))
        for table in Base.metadata.sorted_tables:
            for column_name in ("counterparty", "counterparty_name"):
                column = table.columns.get(column_name)
                if column is None or not isinstance(column.type, String):
                    continue
                try:
                    rows = session.execute(
                        select(column).where(column.is_not(None)).distinct().limit(5000)
                    )
                    names.update(str(value).strip() for (value,) in rows if value)
                except Exception:  # noqa: BLE001 - a table not created yet holds no names
                    session.rollback()
    return {name for name in names if name}


class CounterpartyAliases:
    """Replace counterparty names by ``Counterparty A``, ``B``... and put them back.

    Applied to every message a governed model call sends while the administrator has not
    allowed counterparty names to be sent (``ai_data_sharing.counterparty_names``), and to the
    reply in reverse, so the reader sees the real name and the provider never does.
    """

    def __init__(self, names: tuple[str, ...] | list[str]):
        import re

        self._names = tuple(names)
        self._to_alias: dict[str, str] = {}
        self._from_alias: dict[str, str] = {}
        self._pattern = (
            re.compile(
                "|".join(rf"(?<!\w){re.escape(name)}(?!\w)" for name in self._names), re.I
            )
            if self._names
            else None
        )

    @classmethod
    def from_store(cls, session: Any | None = None) -> CounterpartyAliases:
        return cls(known_counterparty_names(session))

    def _alias_for(self, match: Any) -> str:
        found = match.group(0)
        key = next((n for n in self._names if n.lower() == found.lower()), found)
        if key not in self._to_alias:
            alias = _alias(len(self._to_alias))
            self._to_alias[key] = alias
            self._from_alias[alias.lower()] = key
        return self._to_alias[key]

    def hide(self, text: str) -> str:
        if self._pattern is None or not text:
            return text
        return self._pattern.sub(self._alias_for, text)

    def hide_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            {**message, "content": self.hide(str(message.get("content") or ""))}
            for message in messages
        ]

    def restore(self, text: str) -> str:
        import re

        if not self._from_alias or not text:
            return text
        pattern = re.compile(
            "|".join(rf"(?<!\w){re.escape(alias)}(?!\w)"
                     for alias in sorted(self._from_alias, key=len, reverse=True)),
            re.I,
        )
        return pattern.sub(lambda m: self._from_alias[m.group(0).lower()], text)

    @property
    def hidden(self) -> dict[str, str]:
        """The names hidden so far and their aliases (for tests and the audit)."""

        return dict(self._to_alias)
