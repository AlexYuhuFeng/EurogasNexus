"""Shadow run (paper evaluation) — research-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ShadowRunStatus(StrEnum):
    """Lifecycle status of a shadow run."""

    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


class PaperAction(StrEnum):
    """Research-only action tags (never execution instructions)."""

    RESEARCH_CANDIDATE = "research_candidate"
    CANDIDATE_RANKING = "candidate_ranking"
    RESEARCH_SIGNAL = "research_signal"
    CANDIDATE_ACTION_FOR_REVIEW = "candidate_action_for_review"


@dataclass(frozen=True)
class ShadowSignal:
    """One shadow-run signal.

    Attributes:
        signal_id: Stable signal id.
        route_name: Route display name.
        action: Research-only action tag.
        score: Signal score.
        note: Free note.
    """

    signal_id: str
    route_name: str
    action: PaperAction = PaperAction.RESEARCH_CANDIDATE
    score: float = 0.0
    note: str = ""


@dataclass(frozen=True)
class ShadowRunInput:
    """Shadow-run input.

    Attributes:
        strategy_name: Strategy display name.
        started_at_utc: Run start (ISO).
        signals: Shadow signals.
        paper_pnl_eur: Paper PnL in EUR.
    """

    strategy_name: str
    started_at_utc: str = ""
    signals: list[ShadowSignal] = field(default_factory=list)
    paper_pnl_eur: float = 0.0


@dataclass(frozen=True)
class ShadowRunOutput:
    """Shadow-run output (research-only envelope).

    Attributes:
        strategy_name: Strategy display name.
        status: Run lifecycle status.
        started_at_utc: Run start (ISO).
        elapsed_days: Days since start.
        signal_count: Signal count.
        paper_pnl_eur: Paper PnL in EUR.
        signals: Echoed signals.
        assumptions / missing_inputs / warnings: Transparency fields.
        source_references / lineage: Provenance.
        research_only / human_review_required: Always True.
        generated_at_utc: Generation time (ISO).
    """

    strategy_name: str
    status: ShadowRunStatus = ShadowRunStatus.ACTIVE
    started_at_utc: str = ""
    elapsed_days: int = 0
    signal_count: int = 0
    paper_pnl_eur: float = 0.0
    signals: list[ShadowSignal] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


def evaluate_shadow_run(input_: ShadowRunInput) -> ShadowRunOutput:
    """Evaluate a paper-trading shadow run from signal history.

    Shadow runs are paper evaluations only — no orders, trades, or
    nominations are created.
    """

    missing: list[str] = []
    warnings: list[str] = []

    if not input_.strategy_name:
        missing.append("strategy_name is required.")

    return ShadowRunOutput(
        strategy_name=input_.strategy_name,
        status=ShadowRunStatus.ACTIVE,
        started_at_utc=input_.started_at_utc,
        elapsed_days=_elapsed_days(input_.started_at_utc),
        signal_count=len(input_.signals),
        paper_pnl_eur=input_.paper_pnl_eur,
        signals=input_.signals,
        assumptions=[
            "Shadow run is a paper evaluation — no real capital at risk.",
            "Signals are research candidates requiring human review.",
            "No orders, trades, or nominations are created.",
        ],
        missing_inputs=missing,
        warnings=warnings,
        source_references=["operator-input"],
        lineage=["shadow-run-evaluation"],
        human_review_required=bool(missing or input_.signals),
    )


def _elapsed_days(started_at_utc: str) -> int:
    """Return whole elapsed days between start and generation, or 0."""

    if not started_at_utc:
        return 0
    try:
        start = datetime.fromisoformat(started_at_utc.replace("Z", "+00:00"))
    except ValueError:
        return 0
    generated = datetime.now(UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return max(0, (generated - start.astimezone(UTC)).days)
