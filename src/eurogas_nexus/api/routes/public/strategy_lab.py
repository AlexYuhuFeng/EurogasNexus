"""Strategy-lab decision-support endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from eurogas_nexus.domain.strategy_lab.evaluation import (
    StrategyLabScenario,
    evaluate_strategy_lab,
)

router = APIRouter(tags=["strategy-lab"])


@router.post("/api/strategy-lab/evaluate")
def post_strategy_lab_evaluation(body: StrategyLabScenario, request: Request) -> dict:
    """Evaluate backtest, shadow-run, or live-monitor strategy inputs."""

    result = evaluate_strategy_lab(body)
    return _env(
        result.model_dump(mode="json"),
        request,
        source="operator-input",
        warnings=result.warnings,
    )


def _env(
    data: object,
    _request: Request,
    *,
    source: str,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }
