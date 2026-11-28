"""Watched publications (Package G): the desk's calendar and the administrators' source list.

``GET /api/publications/calendar``: upcoming non-trading days and early closes (the
hand-maintained exchange calendars, marked so), capacity auction windows and offer-level
publication days (ENTSOG's fetched calendar, else the rule-derived dates, labelled), reminders
to check a hand-maintained calendar and sources that changed and need a person. Each item
carries its source and, for fetched ones, when it was published and fetched.

``GET /api/publications/sources``: every watched publication with its terms verdict, interval,
when it was last fetched and changed, and its state (current, needs confirmation, unreachable,
hand-maintained, link only, consented but not yet implemented, consent withdrawn), with the
consent line of a publication fetched under a publisher's written consent.
``POST /api/publications/sources/{publication_id}/confirm``: an administrator has looked at a
changed document the product could not read; the dates held stay and the alarm clears (audited).

``GET /api/publications/consents``: the publishers' written consents (owner, 2026-11-28) with
their scope and state. ``POST /api/publications/consents/{publisher_id}/withdraw`` and
``/restore``: an administrator withdraws a consent (fetching stops at once; the data held stays,
marked) or puts it back (both audited).

监控发布物：交易台日历与管理员的来源状态列表。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, HTTPException, Query, Request

from eurogas_nexus.api.dependencies.row_entitlement import current_principal

router = APIRouter(tags=["publications"])


def _env(data: object, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for publication reads.",
            "error_class": exc.__class__.__name__,
        },
    )


@router.get("/api/publications/calendar")
def publication_calendar(
    request: Request,
    days: int = Query(default=60, ge=1, le=400, description="How far ahead"),
) -> dict:
    """The desk's calendar: non-trading days, auction windows, offer-level days, reminders.

    交易台日历：非交易日、拍卖窗口、报价量公布日与核对提醒，每项附来源与时间。
    """

    from eurogas_nexus.application.publication_watch import calendar_items

    now = datetime.now(UTC)
    warnings: list[str] = []
    if not _db_is_configured():
        return _env({"items": [], "as_of_utc": now.isoformat()},
                    source="runtime-db-not-configured",
                    warnings=["No runtime DB configured; the calendar is unavailable."])
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.api.routes.public.tariffs import readable_publishers
    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            allowed = set(readable_publishers(session, current_principal(request)))
            items = calendar_items(session, now=now, days=days, allowed_publishers=allowed)
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    if any(item["source"]["basis"] == "hand_maintained"
           and item["kind"] in {"non_trading_day", "early_close"} for item in items):
        warnings.append(
            "Some exchange holidays come from the desk's hand-maintained file: the exchange's "
            "own calendar has not been read for those days yet."
        )
    if any(item["source"]["basis"] == "rule_derived" for item in items):
        warnings.append(
            "Auction dates marked rule_derived follow the CAM network code's default calendar; "
            "ENTSOG's calendar replaces them once it has been read."
        )
    return _env({"items": items, "as_of_utc": now.isoformat()}, source="runtime-postgresql",
                warnings=warnings)


@router.get("/api/publications/sources")
def publication_sources(request: Request) -> dict:
    """Every watched publication: terms verdict, interval, last fetch and change, state.

    每个监控发布物：条款结论、间隔、最近获取与变化、状态。
    """

    from eurogas_nexus.application.publication_watch import source_row, source_status
    from eurogas_nexus.domain.publications.registry import WATCHED_PUBLICATIONS

    now = datetime.now(UTC)
    if not _db_is_configured():
        rows = [source_row(item, None, now=now) for item in WATCHED_PUBLICATIONS]
        return _env({"rows": rows}, source="runtime-db-not-configured",
                    warnings=["No runtime DB configured; fetch state is unknown."])
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            rows = source_status(session, now=now)
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    return _env({"rows": rows}, source="runtime-postgresql")


@router.post("/api/publications/sources/{publication_id}/confirm")
def confirm_publication_source(publication_id: str, request: Request) -> dict:
    """An administrator has checked a changed document: keep the dates held, clear the alarm.

    管理员已核对变更的文件：保留现有日期并清除提醒（记入审计）。
    """

    from eurogas_nexus.application.publication_watch import confirm_publication
    from eurogas_nexus.domain.publications.registry import WATCHED_PUBLICATIONS

    if publication_id not in {item.publication_id for item in WATCHED_PUBLICATIONS}:
        raise HTTPException(status_code=404, detail={"code": "publication_unknown",
                                                     "message": "No such watched publication."})
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured",
                                                     "message": "No runtime DB configured."})
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.session import get_session_factory

    principal = current_principal(request).principal_id
    try:
        with get_session_factory()() as session:
            try:
                row = confirm_publication(session, publication_id, principal=principal,
                                          now=datetime.now(UTC))
            except ValueError as exc:
                raise HTTPException(status_code=409, detail={
                    "code": "nothing_to_confirm", "message": str(exc)}) from exc
            session.commit()
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    return _env({"row": row}, source="runtime-postgresql")


@router.get("/api/publications/consents")
def publisher_consents_list(request: Request) -> dict:
    """The publishers' written consents (owner, 2026-11-28): scope, basis and state.

    发布方书面同意：范围、依据与状态（有效或已撤回）。
    """

    from eurogas_nexus.application.publisher_consents import consent_row, consent_status
    from eurogas_nexus.domain.publications.consents import publisher_consents

    if not _db_is_configured():
        rows = [consent_row(c, None) for c in publisher_consents()]
        return _env({"rows": rows}, source="runtime-db-not-configured",
                    warnings=["No runtime DB configured; a withdrawal cannot be recorded."])
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            rows = consent_status(session)
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    return _env({"rows": rows}, source="runtime-postgresql")


def _consent_change(publisher_id: str, request: Request, *, withdraw: bool,
                    reason: str = "") -> dict:
    from eurogas_nexus.application.publisher_consents import restore_consent, withdraw_consent
    from eurogas_nexus.domain.publications.consents import publisher_consent

    if publisher_consent(publisher_id) is None:
        raise HTTPException(status_code=404, detail={"code": "consent_unknown",
                                                     "message": "No such publisher consent."})
    if not _db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured",
                                                     "message": "No runtime DB configured."})
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.db.session import get_session_factory

    principal = current_principal(request).principal_id
    try:
        with get_session_factory()() as session:
            try:
                if withdraw:
                    row = withdraw_consent(session, publisher_id, principal=principal,
                                           now=datetime.now(UTC), reason=reason)
                else:
                    row = restore_consent(session, publisher_id, principal=principal,
                                          now=datetime.now(UTC))
            except ValueError as exc:
                raise HTTPException(status_code=409, detail={
                    "code": "consent_unchanged", "message": str(exc)}) from exc
            session.commit()
    except SQLAlchemyError as exc:
        raise _unavailable(exc) from exc
    return _env({"row": row}, source="runtime-postgresql")


@router.post("/api/publications/consents/{publisher_id}/withdraw")
def withdraw_publisher_consent(publisher_id: str, request: Request,
                               payload: dict | None = Body(default=None)) -> dict:
    """An administrator withdraws a publisher's consent: fetching stops at once (audited).

    管理员撤回发布方的书面同意：立即停止获取，已存数据保留并标注（记入审计）。
    """

    reason = str((payload or {}).get("reason") or "")[:500]
    return _consent_change(publisher_id, request, withdraw=True, reason=reason)


@router.post("/api/publications/consents/{publisher_id}/restore")
def restore_publisher_consent(publisher_id: str, request: Request) -> dict:
    """An administrator puts a withdrawn consent back in force (audited).

    管理员恢复已撤回的书面同意（记入审计）。
    """

    return _consent_change(publisher_id, request, withdraw=False)
