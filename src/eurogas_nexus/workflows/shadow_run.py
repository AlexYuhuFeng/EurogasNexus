"""Shadow run (paper evaluation) — research-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ShadowRunStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


class PaperAction(StrEnum):
    RESEARCH_CANDIDATE = "research_candidate"
    CANDIDATE_RANKING = "candidate_ranking"
    RESEARCH_SIGNAL = "research_signal"
    CANDIDATE_ACTION_FOR_REVIEW = "candidate_action_for_review"


@dataclass(frozen=True)
class ShadowSignal:
    signal_id: str
    route_name: str
    action: PaperAction = PaperAction.RESEARCH_CANDIDATE
    score: float = 0.0
    note: str = ""


@dataclass(frozen=True)
class ShadowRunInput:
    strategy_name: str
    started_at_utc: str = ""
    signals: list[ShadowSignal] = field(default_factory=list)
    paper_pnl_eur: float = 0.0


@dataclass(frozen=True)
class ShadowRunOutput:
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
        elapsed_days=len(input_.signals),
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
