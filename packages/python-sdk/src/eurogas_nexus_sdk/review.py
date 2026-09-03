"""SDK client for trader-review decision endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk._transport import ResponseMeta, SdkResult


class ReviewDecisionDTO(BaseModel):
    """One persisted trader review decision (audit record).

    Attributes:
        decision_id: Unique identifier of the decision.
        entity_type: Type of the reviewed entity.
        entity_id: Identifier of the reviewed entity.
        actor: Principal that recorded the decision.
        decision: Verdict applied to the entity.
        note: Free-text justification; None when not provided.
        created_at_utc: UTC timestamp of the decision.
    """

    decision_id: str
    entity_type: str
    entity_id: str
    actor: str
    decision: str
    # 审计面记录：note 允许为空，客户端不得因缺少注释而拒绝展示决策。
    note: str | None = None
    created_at_utc: str


class ReviewDecisionInput(BaseModel):
    """Input for recording one trader review decision.

    Attributes:
        entity_type: Kind of entity under review; restricted to known types.
        entity_id: Identifier of the reviewed entity.
        actor: Principal recording the decision.
        decision: Verdict; restricted to the accepted enumeration.
        note: Optional free-text justification.
    """

    # 决策枚举由后端审计契约钉死：用 Literal 让非法取值在序列化前
    # 就在客户端失败，而不是等后端返回 422。
    entity_type: Literal["strategy_run", "intraday_opportunity", "generated_report"]
    entity_id: str
    actor: str
    decision: Literal["accepted", "rejected", "needs_attention"]
    note: str | None = None


def fetch_review_decisions(
    base_url: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
) -> SdkResult[list[ReviewDecisionDTO]]:
    """List review decisions, newest first."""

    params = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "limit": str(limit),
    }
    # 只传非 None 参数：后端对缺省过滤条件返回全部记录；
    # 显式传空串会改变过滤语义（变成"按空值过滤"），故不能原样透传。
    response = _http.get(
        _url(base_url, "review/decisions"),
        params={key: value for key, value in params.items() if value is not None},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    return SdkResult(
        data=[ReviewDecisionDTO.model_validate(row) for row in payload["data"]],
        meta=ResponseMeta.model_validate(payload["meta"]),
    )


def record_review_decision(
    base_url: str,
    body: ReviewDecisionInput,
) -> SdkResult[ReviewDecisionDTO | None]:
    """Record a trader review decision (persisted and audited)."""

    response = _http.post(_url(base_url, "review/decisions"), json=body.model_dump(), timeout=15)
    response.raise_for_status()
    payload = response.json()
    # 后端允许 data 为 null（例如回执为空或记录被跳过），
    # 因此 SDK 返回 Optional，并保留 meta 供调用方审计。
    data = payload["data"]
    return SdkResult(
        data=ReviewDecisionDTO.model_validate(data) if data is not None else None,
        meta=ResponseMeta.model_validate(payload["meta"]),
    )


def _url(base_url: str, path: str) -> str:
    """Join a server URL with one canonical ``/api`` path."""

    # rstrip/lstrip 双向归一化：容忍调用方多传或少传斜杠，避免拼出双斜杠。
    return f"{base_url.rstrip('/')}/api/{path.lstrip('/')}"
