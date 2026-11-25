"""The AI-use register (GOV-1, AI controls stage 2 in design document 14).

Every place a language model takes part in the product is one :class:`AiUse` here: who owns
it, what it is for, its level of involvement, the data it may see, the tools it may call, the
prompt it is sent (by reference, so a change to the text is detected), the evaluation set that
gates a change and the pass threshold. A model call from a use that is not in this register
fails (``application/ai_controls.governed_model``), and a test fails when code calls the
provider anywhere else.

Two further rules live here because they are data, not code:

* :data:`ROLE_TOOL_ALLOWLIST`: the capabilities a model acting for a person of each role may
  call. A capability call made on behalf of an AI use is refused unless the capability is in
  the allowlist of one of the caller's roles **and** in the use's own ``tools``.
* :data:`NEVER_MODEL_TOOLS`: capabilities no model may call whatever its role (rule H2: no
  action with an external effect, no licensed data moved out).

Import-safe: no database, web or provider import.

AI 使用登记册：每项 AI 功能的负责人、目的、参与级别、可见数据、可调用工具、提示词引用、
评估集与通过阈值；以及按角色的模型工具白名单。
"""

from __future__ import annotations

from dataclasses import dataclass

#: Levels of involvement, from document 14 section 3.
LEVELS = ("explain", "summarise", "retrieve", "classify", "draft", "propose")

#: The organisation setting that holds the per-use switches: ``{"<use>": true|false}``.
AI_FEATURES_SETTING = "ai_features"


@dataclass(frozen=True, slots=True)
class AiUse:
    """One AI feature and the controls that bound it."""

    use: str
    title: str
    #: The function accountable for the use (SR 11-7 model owner).
    owner: str
    purpose: str
    level: str
    #: Where it runs: the route or worker that calls the model.
    surfaces: tuple[str, ...]
    #: What the model may be shown (after entitlement filtering, identifiers removed).
    data: tuple[str, ...]
    #: Capabilities the model may call; ``()`` when the model calls none.
    tools: tuple[str, ...]
    #: Document 14 control letters: T, C, G, E, K, A, U.
    controls: tuple[str, ...]
    #: Prompt parts by reference ``module:attribute`` (a function counts by its source).
    prompt_refs: tuple[str, ...]
    #: Bumped by hand with every prompt change; the evaluation record pins it.
    prompt_version: str
    #: The recorded evaluation set (repository path) and how it is scored.
    evaluation_set: str
    #: ``note_cases:<filter>`` (scored here through the product's checks) or ``pytest``
    #: (every case in the module must pass, so the module itself enforces the threshold).
    scorer: str
    #: Share of evaluation cases that must get their recorded verdict.
    threshold: float
    #: True when the platform itself calls a model for this use; False when the model is
    #: outside (an analyst's own assistant over MCP) or the planner is deterministic.
    calls_model: bool = True


_NOTE = "application.ai_style"
_ROLES_READ = ("VIEWER", "SCHEDULER", "ANALYST", "REVIEWER")

AI_USES: tuple[AiUse, ...] = (
    AiUse(
        use="explain",
        title='"Why?" beside an alert, outage, credit line, mandate or P&L figure',
        owner="Product owner, desk analytics",
        purpose="Condense the deterministic evidence lines into one desk note",
        level="explain",
        surfaces=("POST /api/analysis/explain",),
        data=("the caller's entitled evidence lines with source and as-of",),
        tools=(),
        controls=("T", "C", "G", "E", "K", "U"),
        prompt_refs=(
            f"{_NOTE}:DESK_NOTE_RULES",
            f"{_NOTE}:NOTE_CALL",
            f"{_NOTE}:note_messages",
            f"{_NOTE}:language_rule",
            "application.explain:model_task",
            "application.explain:model_payload",
        ),
        prompt_version="explain-2026.11.24",
        evaluation_set="tests/evals/ai_note_cases.json",
        scorer="note_cases:explain",
        threshold=1.0,
    ),
    AiUse(
        use="brief",
        title="Lead of the morning brief and end-of-day draft",
        owner="Product owner, desk analytics",
        purpose="Write the lead sentence over the brief's computed sections for a person to edit",
        level="draft",
        surfaces=("POST /api/analysis/brief",),
        data=("the brief's sections as the caller may see them",),
        tools=(),
        controls=("T", "G", "E", "A", "U"),
        prompt_refs=(
            f"{_NOTE}:DESK_NOTE_RULES",
            f"{_NOTE}:NOTE_CALL",
            f"{_NOTE}:note_messages",
            f"{_NOTE}:language_rule",
            "application.desk_brief:lead_task",
            "application.desk_brief:lead_payload",
        ),
        prompt_version="brief-2026.11.24",
        evaluation_set="tests/evals/ai_note_cases.json",
        scorer="note_cases:brief",
        threshold=1.0,
    ),
    AiUse(
        use="answer",
        title="Answer bar",
        owner="Product owner, desk analytics",
        purpose="Answer a typed question from the caller's Today fact lines, citing them",
        level="retrieve",
        surfaces=("POST /api/analysis/ask",),
        data=("the caller's Today fact lines with source and as-of",),
        tools=(),
        controls=("T", "C", "G", "E", "K", "U"),
        prompt_refs=(
            f"{_NOTE}:ANSWER_RULES",
            f"{_NOTE}:ANSWER_CALL",
            f"{_NOTE}:language_rule",
            "application.ai_payloads:ask_messages",
        ),
        prompt_version="answer-2026.11.24",
        evaluation_set="tests/evals/ai_note_cases.json",
        scorer="note_cases:answer:ask",
        threshold=1.0,
    ),
    AiUse(
        use="alert_analysis",
        title="Question about one monitoring alert",
        owner="Product owner, monitoring",
        purpose="Answer an analyst's question about one alert from the alert's own fields",
        level="explain",
        surfaces=("POST /api/monitoring/alerts/{alert_id}/analysis",),
        data=("one alert the caller may see, minimised (no ids or references)",),
        tools=(),
        controls=("T", "G", "E", "K", "U"),
        prompt_refs=(
            f"{_NOTE}:ANSWER_RULES",
            f"{_NOTE}:ANSWER_CALL",
            f"{_NOTE}:language_rule",
            "application.ai_payloads:alert_answer_messages",
        ),
        prompt_version="alert-analysis-2026.11.24",
        evaluation_set="tests/evals/ai_note_cases.json",
        scorer="note_cases:answer:alert",
        threshold=1.0,
    ),
    AiUse(
        use="enrichment",
        title="Background note on a new monitoring alert",
        owner="Product owner, monitoring",
        purpose="Say in EN and ZH why a deterministic alert matters to a gas desk",
        level="summarise",
        surfaces=("monitoring worker (service identity, owner decision D7)",),
        data=("one alert, minimised (no ids, references or earlier warnings)",),
        tools=(),
        controls=("T", "G", "E", "U"),
        prompt_refs=(
            f"{_NOTE}:DESK_NOTE_RULES",
            f"{_NOTE}:ENRICHMENT_CALL",
            "application.monitoring_service:_alert_enrichment_messages",
            "application.ai_payloads:alert_for_enrichment",
        ),
        prompt_version="enrichment-2026.11.24",
        evaluation_set="tests/evals/ai_note_cases.json",
        scorer="note_cases:enrichment",
        threshold=1.0,
    ),
    AiUse(
        use="analysis_query",
        title="Copilot analysis over a market snapshot",
        owner="Product owner, research",
        purpose="Answer a research question from the filtered snapshot, citing rows",
        level="retrieve",
        surfaces=("POST /api/analysis/query", "POST /api/reports/portfolio"),
        data=("the entitled snapshot, contract prices only on explicit opt-in",),
        tools=(),
        controls=("T", "C", "G", "E", "U"),
        prompt_refs=(
            f"{_NOTE}:ANSWER_RULES",
            f"{_NOTE}:ANSWER_CALL",
            f"{_NOTE}:ANALYSIS_QUERY_RULES",
        ),
        prompt_version="analysis-query-2026.11.24",
        evaluation_set="tests/evals/analysis_eval_cases.json",
        scorer="pytest:tests/evals/test_analysis_evals.py",
        threshold=1.0,
    ),
    AiUse(
        use="report_editor",
        title="Market report editor",
        owner="Product owner, reports",
        purpose="Choose and order the report's facts into a plan a validator checks",
        level="draft",
        surfaces=("POST /api/reports/market",),
        data=("the report's fact sheet as the caller may see it",),
        tools=(),
        controls=("T", "G", "E", "A", "U"),
        prompt_refs=(
            "application.reports.directive:RULES",
            "application.reports.directive:PLAN_SCHEMA",
            "application.reports.directive:system_prompt",
            "application.reports.editor:EDITOR_CALL",
            "application.reports.editor:editor_messages",
        ),
        prompt_version="report-editor-directive-4",
        evaluation_set="tests/evals/editor_cases.json",
        scorer="pytest:tests/evals/test_editor_evals.py",
        threshold=1.0,
    ),
    AiUse(
        use="report_plan",
        title="Asked report: question to plan",
        owner="Product owner, reports",
        purpose="Map a question to report sections from a closed catalogue, checked before use",
        level="propose",
        surfaces=("POST /api/reports/plan",),
        data=("the question typed and the report catalogue",),
        tools=(),
        controls=("T", "G", "E", "A", "U"),
        prompt_refs=(
            f"{_NOTE}:NOTE_CALL",
            "application.reports.plan:PLAN_RULES",
            "application.reports.plan:plan_payload",
            "application.reports.plan:plan_messages",
        ),
        prompt_version="report-plan-2026.11.24",
        evaluation_set="tests/evals/report_plan_cases.json",
        scorer="pytest:tests/evals/test_report_plan_evals.py",
        threshold=1.0,
    ),
    AiUse(
        use="spreads_interpret",
        title="Spread described in words",
        owner="Product owner, research",
        purpose="Read a described spread into a structured spec a deterministic check validates",
        level="propose",
        surfaces=("POST /api/research/spreads/interpret",),
        data=("the description typed and the hubs the caller holds",),
        tools=(),
        controls=("T", "G", "E", "A", "U"),
        prompt_refs=(
            f"{_NOTE}:ANSWER_CALL",
            "application.spreads_workbench:translation_messages",
        ),
        prompt_version="spreads-interpret-2026.11.24",
        evaluation_set="tests/unit/test_spreads_workbench.py",
        scorer="pytest:tests/unit/test_spreads_workbench.py",
        threshold=1.0,
    ),
    AiUse(
        use="news_note",
        title='"What this means for my book" on a news item',
        owner="Product owner, desk analytics",
        purpose="Condense one news item, related items and the platform's own figures for "
        "the caller's book into a short note, every sentence cited",
        level="summarise",
        surfaces=("POST /api/news/{item_id}/note",),
        data=(
            "the item and related items from registered public sources",
            "the held REMIT message it is linked to",
            "the caller's matched exposures in the books they may see",
        ),
        tools=(),
        controls=("T", "C", "G", "E", "K", "U"),
        prompt_refs=(
            "application.news_note:NEWS_NOTE_RULES",
            "application.news_note:_OUTPUT",
            "application.news_note:note_messages",
            f"{_NOTE}:NOTE_CALL",
            f"{_NOTE}:language_rule",
            "application.news_grounding:check_note",
        ),
        prompt_version="news-note-2026.11.25",
        evaluation_set="tests/evals/news_note_cases.json",
        scorer="pytest:tests/evals/test_news_note_evals.py",
        threshold=1.0,
    ),
    AiUse(
        use="agent_research",
        title="Governed research run",
        owner="Product owner, research",
        purpose="Plan over registered capabilities; findings and drafts go to human review",
        level="propose",
        surfaces=("POST /api/agent/research",),
        data=("capability results under the caller's own authority and scopes",),
        tools=(
            "capabilities.*",
            "market.*",
            "ontology.*",
            "network.*",
            "capacity.*",
            "analytics.*",
            "dataset.build",
            "dataset.validate_spec",
            "dataset.inspect_snapshot",
            "dataset.get_quality_report",
            "dataset.temporal_integrity_report",
            "strategy.*",
            "backtest.*",
            "review.get",
            "review.prepare_pack",
        ),
        controls=("T", "A", "E", "U"),
        prompt_refs=("application.agents.research_orchestrator:GovernedResearchOrchestrator",),
        prompt_version="rule-based-plan/v1",
        evaluation_set="tests/evals/agent_task_evals.json",
        scorer="pytest:tests/evals/test_agent_evals.py",
        threshold=1.0,
        calls_model=False,
    ),
    AiUse(
        use="mcp_tools",
        title="Read tools for an analyst's own assistant (MCP)",
        owner="Product owner, developer platform",
        purpose="Let an assistant in the analyst's own environment read through capabilities",
        level="retrieve",
        surfaces=("eurogas-nexus MCP server (stdio)",),
        data=("capability results under the configured agent principal and scopes",),
        tools=(
            "capabilities.*",
            "market.*",
            "ontology.*",
            "network.*",
            "capacity.*",
            "analytics.*",
            "route.*",
            "portfolio.*",
            "strategy.get",
            "strategy.list",
            "strategy.compare_versions",
            "strategy.validate_spec",
            "strategy.get_data_requirements",
            "backtest.get_*",
            "backtest.validate",
            "dataset.validate_spec",
            "dataset.inspect_snapshot",
            "dataset.get_quality_report",
            "dataset.temporal_integrity_report",
            "shadow.get_*",
            "review.get",
        ),
        controls=("T", "E", "U"),
        prompt_refs=("mcp.server:_agent_context",),
        prompt_version="mcp-read-2026.11.24",
        evaluation_set="tests/evals/agent_task_evals.json",
        scorer="pytest:tests/evals/test_agent_evals.py",
        threshold=1.0,
        calls_model=False,
    ),
)

AI_USES_BY_NAME: dict[str, AiUse] = {item.use: item for item in AI_USES}

#: Capabilities no model may call, whatever its role or use (H2: no external effect, no
#: licensed data moved out, no human-only or human-confirmed act).
NEVER_MODEL_TOOLS: frozenset[str] = frozenset(
    {
        "dataset.export",
        "review.record_analytical_decision",
        "shadow.start",
        "shadow.pause",
        "shadow.resume",
        "strategy.freeze_version",
    }
)

_MARKET_READS = ("capabilities.*", "market.*", "ontology.*", "network.*", "capacity.*")

#: What a model acting for a person of each role may call. Administration is not commercial
#: work (Architecture V2 06 section 7), so OPERATOR and ADMIN reach only the catalogue.
ROLE_TOOL_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "VIEWER": _MARKET_READS,
    "SCHEDULER": _MARKET_READS,
    "ANALYST": (
        *_MARKET_READS,
        "analytics.*",
        "route.*",
        "portfolio.*",
        "dataset.*",
        "strategy.*",
        "backtest.*",
        "shadow.get_*",
        "review.get",
        "review.prepare_pack",
    ),
    "REVIEWER": (
        *_MARKET_READS,
        "analytics.*",
        "portfolio.*",
        "backtest.get_*",
        "strategy.get",
        "strategy.list",
        "strategy.compare_versions",
        "shadow.get_*",
        "review.get",
        "review.prepare_pack",
    ),
    "OPERATOR": ("capabilities.*",),
    "ADMIN": ("capabilities.*",),
}


def _matches(capability_id: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern.endswith("*"):
            if capability_id.startswith(pattern[:-1]):
                return True
        elif capability_id == pattern:
            return True
    return False


def tool_refusal(use: str, roles: list[str] | tuple[str, ...], capability_id: str) -> str:
    """Why a model acting for ``use`` and these roles may not call a capability, or ``""``."""

    item = AI_USES_BY_NAME.get(use)
    if item is None:
        return f"AI use {use!r} is not in the register"
    if capability_id in NEVER_MODEL_TOOLS:
        return f"{capability_id} is never called by a model"
    if not _matches(capability_id, item.tools):
        return f"{capability_id} is not a tool of the AI use {use!r}"
    held = [str(role).upper() for role in roles]
    if not any(_matches(capability_id, ROLE_TOOL_ALLOWLIST.get(role, ())) for role in held):
        return f"{capability_id} is not on the model allowlist of role(s) {', '.join(held)}"
    return ""


def ai_use(use: str) -> AiUse:
    """The registered use, or ``KeyError`` for a use that is not in the register."""

    try:
        return AI_USES_BY_NAME[use]
    except KeyError as exc:
        raise KeyError(f"AI use {use!r} is not in the register") from exc


__all__ = [
    "AI_FEATURES_SETTING",
    "AI_USES",
    "AI_USES_BY_NAME",
    "LEVELS",
    "NEVER_MODEL_TOOLS",
    "ROLE_TOOL_ALLOWLIST",
    "AiUse",
    "ai_use",
    "tool_refusal",
]
