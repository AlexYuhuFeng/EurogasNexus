"""Internal scheduler trigger for shadow research evaluations."""

from __future__ import annotations

from fastapi import APIRouter, Body

router = APIRouter(tags=["internal-shadow"])


@router.post("/shadow-scheduler/tick")
def shadow_scheduler_tick(limit: int = Body(default=10, embed=True)) -> dict:
    """Run one bounded scheduler scan (operator/worker trigger)."""

    from datetime import UTC, datetime

    from eurogas_nexus.application.shadow_runtime import run_due_shadow_evaluations
    from eurogas_nexus.db.session import get_session_factory

    with get_session_factory()() as session:
        data = run_due_shadow_evaluations(
            session, now_utc=datetime.now(UTC), limit=limit
        )
        session.commit()
    return data
