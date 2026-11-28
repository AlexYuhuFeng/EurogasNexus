"""Licensed feed tick ingestion and the prompt desk read.

- ``POST /api/market/ticks``: a licensed feed adapter (or the demo simulator) delivers a batch
  of quotes and trade prints; they are stored under the source family.
- ``GET  /api/market/prompt``: within-day and day-ahead for one hub, with today's post-trade
  performance.

Nothing here places an order, a nomination or an instruction. Delivering ticks is a
data-operations act (``source.run``, OPERATOR floor).

许可行情逐笔入库与即日/日前行情读取；不下单。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.security.authorization import Permission, authorize
from eurogas_nexus.security.identity import AuthenticatedPrincipal, legacy_public_token_principal

router = APIRouter(tags=["market"])


def _principal(request: Request) -> AuthenticatedPrincipal:
    identity = getattr(request.state, "identity", None)
    return identity if isinstance(identity, AuthenticatedPrincipal) else (
        legacy_public_token_principal()
    )


def _require(request: Request, permission: Permission) -> AuthenticatedPrincipal:
    principal = _principal(request)
    if not authorize(principal, permission).allowed:
        raise HTTPException(
            status_code=403, detail={"code": "permission_denied", "permission": permission.value}
        )
    return principal


def _session():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_required"})
    return get_session_factory()()


def _env(data: object, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": warnings or [],
        },
    }


class TickBatch(BaseModel):
    """One feed batch of quotes and trade prints."""

    model_config = ConfigDict(extra="forbid")
    source_system: str = Field(min_length=2, max_length=64)
    quotes: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    trades: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)


def _tick_actor(principal) -> str:
    return str(getattr(principal, "principal_id", None) or "unknown")[:64]


@router.post("/api/market/ticks")
def ingest_market_ticks(body: TickBatch, request: Request) -> dict:
    """Store a batch of quotes and trade prints.

    Raises:
        HTTPException: 403 ``source_not_granted`` (a licensed label the key's data scopes do
            not name); 422 ``ticks_invalid`` (unknown source, an implausible price, a future
            exchange time, a jump no market makes, a bad tick; nothing stored).
    """

    principal = _require(request, Permission.SOURCE_RUN)
    from eurogas_nexus.application.market_ticks import ingest_ticks, publisher_refusal
    from eurogas_nexus.core.config import simulated_sources_allowed
    from eurogas_nexus.db.repositories.audit import record_audit_event, record_governed_audit
    from eurogas_nexus.domain.market.feed import FeedError

    refusal = publisher_refusal(principal, body.source_system)
    if refusal is not None:
        # A refused attempt to write a venue's price is itself evidence (H4).
        with _session() as session:
            record_audit_event(
                session,
                event_type="governance.market_data",
                principal=_tick_actor(principal),
                action="market.ticks.refused",
                resource=f"market_ticks:{body.source_system}"[:128],
                outcome="denied",
                severity="warning",
                detail=(
                    f"quotes={len(body.quotes)}; trades={len(body.trades)}; "
                    f"auth={getattr(principal, 'auth_method', '')}"
                ),
                source_system="market-ticks",
            )
            session.commit()
        raise HTTPException(
            status_code=403, detail={"code": "source_not_granted", "message": refusal}
        )

    with _session() as session:
        try:
            result = ingest_ticks(session, source_system=body.source_system, quotes=body.quotes,
                                  trades=body.trades,
                                  simulated_allowed=simulated_sources_allowed())
        except (FeedError, ValueError) as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail={
                "code": "ticks_invalid", "message": str(exc)}) from exc
        # Every tick batch is audited with the identity that wrote it (H4).
        record_governed_audit(
            session,
            event_type="governance.market_data",
            principal=_tick_actor(principal),
            action="market.ticks.ingested",
            resource=f"market_ticks:{body.source_system}"[:128],
            outcome="stored",
            severity="info",
            detail=(
                f"quotes={len(body.quotes)}; trades={len(body.trades)}; "
                f"auth={getattr(principal, 'auth_method', '')}"
            ),
            source_system="market-ticks",
        )
        session.commit()
    return _env(result.as_dict())


@router.get("/api/market/prompt")
def read_prompt_market(
    request: Request, hub: str = Query(default="TTF", min_length=2, max_length=16),
) -> dict:
    """Within-day and day-ahead for one hub: the live screen (bid/offer with size, last, VWAP,
    volume, trades, settlement), the WD − DA spread and the post-trade performance of today's
    booked prompt trades. Nothing is sent anywhere.

    即日/日前实时行情（含量、成交、VWAP）与当日成交后绩效。
    """

    principal = _require(request, Permission.MARKET_READ)
    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.application.prompt_market import prompt_market

    with _session() as session:
        data = prompt_market(session, Caller(principal), hub)
    warnings = list(data.get("warnings") or [])
    if data.get("simulated"):
        warnings.insert(0, "Simulated prices: not a market price.")
    return _env(data, warnings)
