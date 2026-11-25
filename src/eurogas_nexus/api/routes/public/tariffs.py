"""Read-only tariff book routes (TAR-1): tariff versions, publishers, capacity notices.

``GET /api/tariffs``: the public tariffs in force now or as known at ``as_of``, or every
version of one tariff (``history=true``), each labelled ``INDICATIVE`` or ``FINAL`` with the
reason, its source URL and when this platform read it. ``GET /api/tariffs/publishers``: the
publisher registry with what is held, when each was last read and whether an expected update
was missed. ``GET /api/capacity/notices``: upcoming capacity auctions, LNG slot offers and
secondary-capacity windows, rule-derived ones labelled so.

Rows are filtered by the reader's source-family entitlement; a terminal operator whose terms
need the firm's permission is left out until that permission is recorded.

TAR-1：公开费率版本簿、发布方登记与容量通知的只读接口。
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.dependencies.row_entitlement import current_principal

router = APIRouter(tags=["tariffs"])

_AS_OF_DESCRIPTION = (
    "ISO 8601 UTC instant (e.g. 2026-11-20T17:30:00Z). Answer with the tariff versions this "
    "platform held at that instant. Omitted: the versions held now."
)


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


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for tariff reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _as_of(text: str | None) -> datetime | None:
    from eurogas_nexus.application.as_of_reads import AsOfError, parse_as_of

    try:
        return parse_as_of(text)
    except AsOfError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from exc


def readable_publishers(session, principal) -> list[str]:
    """Publishers whose figures this reader may see: entitled to the source family, and,
    for a terminal operator whose terms need the firm's permission, that permission held."""

    from eurogas_nexus.application.tariff_book import _firm_permission
    from eurogas_nexus.domain.tariffs.publishers import NEEDS_FIRM_TERMS, PUBLISHERS
    from eurogas_nexus.security.identity import principal_allows_source_family

    allowed: list[str] = []
    families: dict[str, bool] = {}
    for item in PUBLISHERS:
        if item.source_family not in families:
            families[item.source_family] = principal_allows_source_family(
                principal, item.source_family
            )
        if not families[item.source_family]:
            continue
        if item.reuse == NEEDS_FIRM_TERMS and not _firm_permission(session, item):
            continue
        allowed.append(item.publisher_id)
    return allowed


@router.get("/api/tariffs")
def list_tariffs(
    request: Request,
    publisher: str | None = Query(default=None, max_length=64),
    facility: str | None = Query(default=None, max_length=128, description="Point or terminal id"),
    operator: str | None = Query(default=None, max_length=128),
    direction: str | None = Query(default=None, pattern="^(ENTRY|EXIT|entry|exit)$"),
    product: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, pattern="^(INDICATIVE|FINAL|indicative|final)$"),
    on: date | None = Query(default=None, description="Only tariffs that apply on this gas day"),
    key: str | None = Query(default=None, max_length=200, description="One tariff's key"),
    as_of: str | None = Query(default=None, description=_AS_OF_DESCRIPTION),
    history: bool = Query(default=False, description="Every version (needs key or facility)"),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Public tariffs with their versions; indicative and final are labelled, never merged.

    公开费率及其版本；指示性与最终费率分别标注，不会静默合并。
    """

    moment = _as_of(as_of)
    if history and not (key or facility):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "history_needs_scope",
                "message": "history=true needs key or facility (one tariff or one facility).",
            },
        )
    if not _db_is_configured():
        return _env(
            {"rows": [], "total": 0, "as_of": None, "history": history},
            source="runtime-db-not-configured",
            warnings=["No runtime DB configured; the tariff book is unavailable."],
        )
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.tariff_book import TariffFilter
    from eurogas_nexus.application.tariff_book import list_tariffs as read
    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            allowed = readable_publishers(session, current_principal(request))
            data = read(
                session,
                filters=TariffFilter(
                    publisher_id=publisher,
                    facility_id=facility,
                    operator=operator,
                    direction=direction,
                    product=product,
                    status=status,
                    on=on,
                    tariff_key=key,
                ),
                as_of=moment,
                history=history,
                allowed_publishers=allowed,
                limit=limit,
                offset=offset,
            )
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    data["limit"] = limit
    data["offset"] = offset
    warnings = []
    if any(row["status"] == "INDICATIVE" for row in data["rows"]):
        warnings.append(
            "Some tariffs are INDICATIVE (status_basis says why); valuations using them are "
            "labelled indicative."
        )
    return _env(data, source="runtime-postgresql", warnings=warnings)


@router.get("/api/tariffs/publishers")
def list_tariff_publishers(request: Request) -> dict:
    """The tariff publisher registry: access (API, rule, parsed, manual), reuse terms, poll
    cadence, last read and whether an expected update was missed.

    费率发布方登记：接入方式、再利用条款、轮询频率、最近读取与是否错过预期更新。
    """

    from eurogas_nexus.domain.tariffs.publishers import PUBLISHERS

    if not _db_is_configured():
        rows = [item.to_json() | {"state": "unknown"} for item in PUBLISHERS]
        return _env(
            {"rows": rows},
            source="runtime-db-not-configured",
            warnings=["No runtime DB configured; read state is unknown."],
        )
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.tariff_book import publisher_status
    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            allowed = set(readable_publishers(session, current_principal(request)))
            rows = publisher_status(session)
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    for row in rows:
        # The registry is public; the counts of a publisher the reader may not see are not.
        row["readable"] = row["publisher_id"] in allowed
        if not row["readable"]:
            row["tariffs_final"] = row["tariffs_indicative"] = row["notices"] = None
            row["missed_publications"] = []
    return _env({"rows": rows}, source="runtime-postgresql")


@router.get("/api/capacity/notices")
def list_capacity_notices(
    request: Request,
    kind: str | None = Query(default=None, pattern="^(auction|lng_slot|secondary_capacity)$"),
    product: str | None = Query(default=None, max_length=32),
    facility: str | None = Query(default=None, max_length=128),
    publisher: str | None = Query(default=None, max_length=64),
    days: int = Query(default=120, ge=1, le=400, description="How far ahead"),
    past_days: int = Query(default=0, ge=0, le=31, description="Include windows opened lately"),
) -> dict:
    """Upcoming capacity windows: CAM standard auctions (rule-derived, labelled so), LNG slot
    offers and secondary-capacity windows imported from a publisher's notice.

    即将开放的容量窗口：CAM 标准拍卖（按规则推导并标注）、LNG 窗口与二级容量。
    """

    if not _db_is_configured():
        return _env(
            {"rows": []},
            source="runtime-db-not-configured",
            warnings=["No runtime DB configured; capacity notices are unavailable."],
        )
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.tariff_book import list_notices
    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            allowed = readable_publishers(session, current_principal(request))
            rows = list_notices(
                session,
                days=days,
                kind=kind,
                product=product,
                facility_id=facility,
                publisher_id=publisher,
                include_past_days=past_days,
                allowed_publishers=allowed,
            )
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    warnings = []
    if any(row["basis"] == "rule_derived" for row in rows):
        warnings.append(
            "Auction dates marked rule_derived follow the CAM network code's default calendar; "
            "ENTSOG's published calendar and the booking platform are authoritative."
        )
    return _env({"rows": rows}, source="runtime-postgresql", warnings=warnings)
