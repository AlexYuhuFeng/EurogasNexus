"""Sandbox-scenario enforcement for research routes (audit item 2).

Research endpoints are explicit what-if sandboxes: clients may supply full
assumptions (prices, topology, contracts), but a request must never be able
to claim RUNTIME_DECISION semantics — runtime decisions consume DB snapshots
via the optimization endpoints, not client-supplied inputs.

沙箱语义是本模块的核心：研究路由只做"假设推演"，禁止冒充运行时决策；
决策上下文在请求状态中显式标记，供下游审计与响应标签使用。
"""

from __future__ import annotations

import json

from fastapi import HTTPException, Request

SANDBOX_SCENARIO = "SANDBOX_SCENARIO"
RUNTIME_DECISION = "RUNTIME_DECISION"


async def require_sandbox_scenario(request: Request) -> None:
    """Reject RUNTIME_DECISION claims and label the request as sandbox-only.

    研究路由的沙箱强制依赖：拒绝任何声称 RUNTIME_DECISION 的请求体。

    Args:
        request: The incoming FastAPI request; on success its state is
            labelled ``decision_context=SANDBOX_SCENARIO`` for downstream
            audit and response tagging.

    Returns:
        None when the request is sandbox-compatible.

    Raises:
        HTTPException: 422 ``runtime_decision_not_supported`` when the JSON
            body declares ``decision_context=RUNTIME_DECISION``.
    """

    body = await request.body()
    if body:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            # 非 JSON 请求体（如表单/文件）不参与决策上下文判定。
            payload = None
        if isinstance(payload, dict) and payload.get("decision_context") == RUNTIME_DECISION:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "runtime_decision_not_supported",
                    "message": (
                        "Research endpoints are sandbox-only (client-supplied "
                        "inputs); RUNTIME_DECISION is not supported here."
                    ),
                    "research_only": True,
                    "human_review_required": True,
                },
            )
    # 通过后显式打标：审计日志与响应可据此区分沙箱与研究外场景。
    request.state.decision_context = SANDBOX_SCENARIO
