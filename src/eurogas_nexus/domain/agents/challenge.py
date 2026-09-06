"""Structured Risk Challenger (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ChallengeResult(StrEnum):
    PASS = "PASS"
    CONCERN = "CONCERN"
    FAIL = "FAIL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ChallengeItem(BaseModel):
    challenge: str
    severity: str = "medium"
    evidence: dict[str, Any] = Field(default_factory=dict)
    result: ChallengeResult
    recommended_follow_up: str = ""


class ChallengeReport(BaseModel):
    challenge_report_id: str
    strategy_version_id: str | None = None
    backtest_run_id: str | None = None
    agent_run_id: str | None = None
    items: list[ChallengeItem] = Field(default_factory=list)
    overall_result: ChallengeResult = ChallengeResult.PASS
    recommended_follow_up: str = ""
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def public_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def challenge_backtest_result(
    *,
    challenge_report_id: str,
    strategy_version_id: str | None,
    backtest_run_id: str | None,
    metrics: dict[str, Any],
    warnings: list[str] | None = None,
    missing_inputs: list[str] | None = None,
    sample_size: int | None = None,
    period: str | None = None,
    cost_policy: str | None = None,
) -> ChallengeReport:
    """Deterministically attempt to invalidate a candidate strategy.

    This is not a second optimistic summary. Every challenge is evidence-based
    and structured; insufficient evidence never becomes PASS.
    """

    items: list[ChallengeItem] = []
    run_warnings = list(warnings or [])
    run_missing = list(missing_inputs or [])

    if sample_size is not None and sample_size < 30:
        items.append(
            ChallengeItem(
                challenge="Is the sample too small to support the claim?",
                severity="high",
                evidence={"sample_size": sample_size},
                result=ChallengeResult.INSUFFICIENT_EVIDENCE,
                recommended_follow_up="Collect a larger sample before any conclusion.",
            )
        )
    if run_missing:
        items.append(
            ChallengeItem(
                challenge="Could missing inputs invalidate the result?",
                severity="high",
                evidence={"missing_inputs": run_missing},
                result=ChallengeResult.FAIL,
                recommended_follow_up="Resolve missing inputs and rerun the backtest.",
            )
        )
    if any("CARRY_FORWARD" in item.upper() for item in run_warnings):
        items.append(
            ChallengeItem(
                challenge="Could stale carried-forward data dominate the result?",
                severity="medium",
                evidence={"warnings": run_warnings},
                result=ChallengeResult.CONCERN,
                recommended_follow_up="Review carry-forward age against policy.",
            )
        )
    drawdown = float(metrics.get("max_drawdown_gbp") or 0.0)
    net_pnl = float(metrics.get("net_indicative_pnl_gbp") or 0.0)
    if drawdown and net_pnl and abs(drawdown) > abs(net_pnl):
        items.append(
            ChallengeItem(
                challenge="Does drawdown exceed total net PnL?",
                severity="high",
                evidence={"net_pnl": net_pnl, "max_drawdown": drawdown},
                result=ChallengeResult.CONCERN,
                recommended_follow_up="Review risk controls and exposure sizing.",
            )
        )
    if cost_policy and "UNMODELED" in cost_policy.upper():
        items.append(
            ChallengeItem(
                challenge="Could unmodeled transaction costs reverse the result?",
                severity="high",
                evidence={"cost_policy": cost_policy},
                result=ChallengeResult.INSUFFICIENT_EVIDENCE,
                recommended_follow_up="Run explicit cost sensitivity checks.",
            )
        )
    if period:
        items.append(
            ChallengeItem(
                challenge="Could one crisis period dominate the result?",
                severity="medium",
                evidence={"period": period},
                result=ChallengeResult.INSUFFICIENT_EVIDENCE,
                recommended_follow_up="Run period-sensitivity segmentation.",
            )
        )
    if not items:
        items.append(
            ChallengeItem(
                challenge="No evidence-based invalidation found for the supplied inputs.",
                severity="low",
                evidence={"metrics": metrics},
                result=ChallengeResult.PASS,
                recommended_follow_up="Keep the structured evidence in the review pack.",
            )
        )
    results = [item.result for item in items]
    if ChallengeResult.FAIL in results:
        overall = ChallengeResult.FAIL
    elif ChallengeResult.INSUFFICIENT_EVIDENCE in results:
        overall = ChallengeResult.INSUFFICIENT_EVIDENCE
    elif ChallengeResult.CONCERN in results:
        overall = ChallengeResult.CONCERN
    else:
        overall = ChallengeResult.PASS
    follow_ups = [item.recommended_follow_up for item in items if item.recommended_follow_up]
    return ChallengeReport(
        challenge_report_id=challenge_report_id,
        strategy_version_id=strategy_version_id,
        backtest_run_id=backtest_run_id,
        items=items,
        overall_result=overall,
        recommended_follow_up="; ".join(dict.fromkeys(follow_ups)),
    )
