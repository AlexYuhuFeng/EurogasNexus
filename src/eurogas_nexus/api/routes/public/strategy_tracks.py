"""Tracked strategies (paper shadow run) and the feed tick ingestion that drives them.

- ``GET  /api/research/strategy-tracks``: the caller's own tracks with their state.
- ``POST /api/research/strategy-tracks``: save a StrategySpec as a track (daily or intraday).
- ``GET  /api/research/strategy-tracks/{track_id}``: state, signals, paper blotter, equity.
- ``POST /api/research/strategy-tracks/{track_id}/stop``: stop tracking (kept for review).
- ``POST /api/market/ticks``: a licensed feed adapter (or the demo simulator) delivers a batch
  of quotes and trade prints; the tracks listening to them are evaluated in the same call.

Saving and stopping need ``strategy.shadow.manage``, reading ``strategy.read``; a track is the
owner's alone (another user's track reads as unknown). Delivering ticks is a data-operations
act (``source.run``, OPERATOR floor). Nothing here places an order, a nomination or an
instruction: every fill is a paper fill, labelled ``paper``.

跟踪策略（纸面影子运行）与驱动它的行情逐笔入库；仅纸面成交，不下单。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.security.authorization import Permission, authorize
from eurogas_nexus.security.identity import AuthenticatedPrincipal, legacy_public_token_principal

router = APIRouter(tags=["research"])


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
            "paper_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": warnings or [],
        },
    }


class TrackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    mode: Literal["daily", "intraday"]
    spec: dict[str, Any]
    rule: dict[str, Any] | None = None


@router.get("/api/research/strategy-tracks")
def list_strategy_tracks(request: Request) -> dict:
    """The caller's tracked strategies. 调用者自己的跟踪策略。"""

    principal = _require(request, Permission.STRATEGY_READ)
    from eurogas_nexus.application.strategy_tracking import list_tracks

    with _session() as session:
        return _env(list_tracks(session, principal))


@router.post("/api/research/strategy-tracks")
def create_strategy_track(body: TrackInput, request: Request) -> dict:
    """Track a strategy: paper positions only, evaluated on new closes or arriving quotes.

    Raises:
        HTTPException: 422 ``track_invalid`` with the field at fault.
    """

    principal = _require(request, Permission.STRATEGY_SHADOW_MANAGE)
    from eurogas_nexus.application.strategy_tracking import TrackError, create_track, run_due

    with _session() as session:
        try:
            data = create_track(session, principal, name=body.name, spec=body.spec,
                                mode=body.mode, rule=body.rule)
        except TrackError as exc:
            raise HTTPException(status_code=422, detail={
                "code": "track_invalid", "field": exc.code, "message": str(exc)}) from exc
        session.commit()
        # First evaluation at once, so the track opens with a state, not an empty card.
        run_due(session)
        session.commit()
        from eurogas_nexus.application.strategy_tracking import get_track

        return _env(get_track(session, principal, data["track_id"]))


@router.get("/api/research/strategy-tracks/{track_id}")
def read_strategy_track(
    track_id: str, request: Request, limit: int = Query(default=500, ge=1, le=5000)
) -> dict:
    """One track: state, signals, paper blotter and equity marks."""

    principal = _require(request, Permission.STRATEGY_READ)
    from eurogas_nexus.application.strategy_tracking import get_track

    with _session() as session:
        data = get_track(session, principal, track_id, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_track"})
    return _env(data)


@router.post("/api/research/strategy-tracks/{track_id}/stop")
def stop_strategy_track(track_id: str, request: Request) -> dict:
    """Stop a track; its history is kept for review."""

    principal = _require(request, Permission.STRATEGY_SHADOW_MANAGE)
    from eurogas_nexus.application.strategy_tracking import stop_track

    with _session() as session:
        data = stop_track(session, principal, track_id)
        if data is None:
            raise HTTPException(status_code=404, detail={"code": "unknown_track"})
        session.commit()
    return _env(data)


class TickBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_system: str = Field(min_length=2, max_length=64)
    quotes: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    trades: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    #: Simulated sessions only: evaluate at the batch's exchange time (a compressed replay).
    replay: bool = False


@router.post("/api/market/ticks")
def ingest_market_ticks(body: TickBatch, request: Request) -> dict:
    """Store a batch of quotes and trade prints and evaluate the tracks listening to them.

    Raises:
        HTTPException: 403 ``source_not_granted`` (a licensed label the key's data scopes do
            not name); 422 ``ticks_invalid`` (unknown source, an implausible price, a future
            exchange time, a jump no market makes, a bad tick; nothing stored).
    """

    principal = _require(request, Permission.SOURCE_RUN)
    from eurogas_nexus.application.market_ticks import ingest_ticks, publisher_refusal
    from eurogas_nexus.core.config import simulated_sources_allowed
    from eurogas_nexus.domain.market.feed import FeedError

    refusal = publisher_refusal(principal, body.source_system)
    if refusal is not None:
        raise HTTPException(
            status_code=403, detail={"code": "source_not_granted", "message": refusal}
        )

    with _session() as session:
        try:
            result = ingest_ticks(session, source_system=body.source_system, quotes=body.quotes,
                                  trades=body.trades,
                                  simulated_allowed=simulated_sources_allowed(),
                                  replay=body.replay)
        except (FeedError, ValueError) as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail={
                "code": "ticks_invalid", "message": str(exc)}) from exc
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
