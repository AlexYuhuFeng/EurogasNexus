"""/api/research/spreads: describe a spread study, check it, evaluate it.

- ``POST /api/research/spreads/interpret``: text (or pasted code, read as text) → a
  StrategySpec with the questions that stand before it can run. The model only translates,
  and only when the deployment and the caller may use it; the deterministic parser works
  without one. Audited as ``ai.spreads`` when the model is used.
- ``POST /api/research/spreads/evaluate``: a spec (from the form or the interpretation) →
  the checks, and the result computed by the engine: the forward curve by delivery month net of
  the route's published tariffs, or a daily history through the spread lab with the route cost
  as horizontal lines.

Both are research calls (the ``/api/research/`` family: GOVERNED); nothing is stored and no
order, nomination or instruction exists.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["research"])


def _env(data: object, *, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": warnings or [],
        },
    }


def _holdings(request: Request, today: date | None = None):
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.projections.daily_closes import ObservationWindowTooLarge
    from eurogas_nexus.application.spreads_workbench import load_holdings

    try:
        return load_holdings(request, today=today)
    except ObservationWindowTooLarge as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "spreads_too_large", "message": "too many observations held"},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_unavailable", "error_class": exc.__class__.__name__},
        ) from exc


class InterpretInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=4000)
    language: Literal["en", "zh-CN"] = "en"
    #: The parser only, even where a model is available (a test, a reproducible run).
    model: bool = True


@router.post("/api/research/spreads/interpret")
def interpret_description(body: InterpretInput, request: Request) -> dict:
    """A description → StrategySpec, with questions for what is unclear or not held.

    文字描述 → StrategySpec；不清楚或未持有的内容以问题与选项返回。
    """

    from eurogas_nexus.api.dependencies.ai_authority import ai_caller
    from eurogas_nexus.api.routes.public.explain import _audit, _model_for
    from eurogas_nexus.application.spreads_workbench import interpret

    holdings = _holdings(request)
    model = None
    principal = None
    if body.model:
        principal = ai_caller(request)
        model = _model_for(principal, answer=True)
    result = interpret(body.text, holdings, language=body.language, model=model)
    if model is not None and principal is not None:
        from sqlalchemy.exc import SQLAlchemyError

        from eurogas_nexus.db.session import get_session_factory

        try:
            with get_session_factory()() as session:
                _audit(session, request, principal, "spreads:interpret",
                       f"{result.basis}; ai={result.ai}", action="ai.spreads")
                session.commit()
        except SQLAlchemyError:
            pass  # the audit store being down does not hide the interpretation
    return _env(result.as_dict())


class EvaluateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: dict[str, Any]
    #: Anchor date (tests and rehearsals); today by default.
    as_of: date | None = None


@router.post("/api/research/spreads/evaluate")
def evaluate_spec(body: EvaluateInput, request: Request) -> dict:
    """The checks and, when none stands, the result of a spec, every figure from the engine.

    检查规格；无阻碍时由确定性引擎计算结果（远期曲线净运输费，或历史序列与运输成本线）。
    """

    from eurogas_nexus.application.spreads_workbench import (
        check,
        evaluate_curve,
        route_lines,
        stored_tenor,
    )
    from eurogas_nexus.domain.research.strategy_spec import spec_from_dict

    spec = spec_from_dict(body.spec)
    holdings = _holdings(request, body.as_of)
    issues = list(spec.issues) + check(spec, holdings)
    if issues:
        return _env({"spec": spec.as_dict(), "issues": [i.as_dict() for i in issues],
                     "result": None})
    if spec.kind == "curve":
        result = evaluate_curve(spec, holdings)
        warnings = (["Simulated inputs: the spread is not a market price."]
                    if result["simulated"] else [])
        return _env({"spec": spec.as_dict(), "issues": [], "result": result}, warnings=warnings)

    from eurogas_nexus.api.routes.public.spread_lab import (
        SpreadAnalysisInput,
        run_spread_analysis,
    )

    legs = [
        {"hub": leg.hub, "tenor": stored_tenor(holdings, leg.hub, leg.tenor or "") or leg.tenor,
         "weight": leg.weight}
        for leg in spec.legs
    ]
    rule = spec.rule.as_dict() if spec.rule else {"kind": "zscore", "lookback": 20}
    rule = {key: value for key, value in rule.items() if value is not None}
    if spec.volume_mwh_per_day:
        rule["volume_mwh_per_day"] = spec.volume_mwh_per_day
    analysis = run_spread_analysis(
        SpreadAnalysisInput(legs=legs, rule=rule, unit=spec.unit), request
    )
    data = analysis["data"]
    result = {
        "kind": "history",
        "unit": data.get("unit"),
        "analysis": data,
        "route": route_lines(spec, holdings, data.get("unit") or spec.unit or "EUR/MWh"),
        "simulated": any(
            "simulated" in str(item).lower() for item in analysis["meta"]["warnings"]
        ) or any(item.get("simulated") for item in data.get("normalisation") or []),
    }
    return _env({"spec": spec.as_dict(), "issues": [], "result": result},
                warnings=analysis["meta"]["warnings"])
