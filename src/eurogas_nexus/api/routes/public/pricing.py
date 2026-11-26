"""Source-precedence reads (TAR-2): which source a rate comes from, tier by tier.

``GET /api/pricing/fx-rate``: an FX rate as of an instant by the firm's source order (its
contracted bank's rate, a published reference fixing, the ECB), with every tier tried and why
it was used or skipped. ``GET /api/pricing/source-precedence``: the order in force for each
quantity kind (and a calculation context), the configured financial institutions (each with
its live feed's connection state, ``live_feed_status``, worked out without a network call)
and the terms of a live bank feed. Reads only; nothing is fetched from a bank.

TAR-2：数据来源优先级只读接口：按企业配置顺序给出汇率及逐层说明，并列出当前生效顺序与银行配置。
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from eurogas_nexus.api.dependencies.row_entitlement import current_principal
from eurogas_nexus.api.routes.public.tariffs import _as_of, _db_is_configured, _db_unavailable

router = APIRouter(tags=["pricing"])

_CONTEXT = "^[a-z0-9_]{1,48}$"


def _env(data: object, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": False,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }


def _allowed_systems(session, principal) -> set[str]:
    """Reference fixings by the reader's entitlement; the firm's own banks' rates are the
    firm's data, readable by every signed-in user of the firm."""

    from eurogas_nexus.application.source_precedence import (
        ECB_SYSTEMS,
        PUBLISHED_REFERENCE_SYSTEMS,
        configured_institutions,
    )
    from eurogas_nexus.security.identity import principal_allows_source_family

    allowed = {
        system
        for system in (*PUBLISHED_REFERENCE_SYSTEMS, *ECB_SYSTEMS)
        if principal_allows_source_family(principal, system)
    }
    return allowed | {bank.source_system for bank in configured_institutions(session)}


@router.get("/api/pricing/fx-rate")
def read_fx_rate(
    request: Request,
    from_ccy: str = Query(alias="from", pattern="^[A-Za-z]{3}$"),
    to_ccy: str = Query(alias="to", pattern="^[A-Za-z]{3}$"),
    as_of: str | None = Query(default=None, description="ISO 8601 UTC instant; default now"),
    context: str = Query(default="", pattern=f"({_CONTEXT})?$"),
    rate_type: str | None = Query(default=None, pattern="^(mid|buy|sell)$"),
) -> dict:
    """How many ``to`` one ``from`` buys as of ``as_of``, by the firm's source order, with
    the sources in precedence order and the one used marked.

    按企业来源顺序给出汇率，列出各来源层级及所用来源。
    """

    from datetime import UTC, datetime

    moment = _as_of(as_of) or datetime.now(UTC)
    if not _db_is_configured():
        return _env(
            {"value": None, "sources": []},
            source="runtime-db-not-configured",
            warnings=["No runtime DB configured; FX rates are unavailable."],
        )
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.source_precedence import resolve_fx_rate
    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            resolution = resolve_fx_rate(
                session, from_ccy, to_ccy, moment, context, rate_type=rate_type,
                allowed_systems=_allowed_systems(session, current_principal(request)),
            )
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    data = resolution.as_dict() | {"from": from_ccy.upper(), "to": to_ccy.upper()}
    warnings = [] if resolution.value is not None else [
        "No source in the order holds a usable rate; see sources for why."
    ]
    return _env(data, source="runtime-postgresql", warnings=warnings)


@router.get("/api/pricing/source-precedence")
def read_source_precedence(
    request: Request,
    context: str = Query(default="", pattern=f"({_CONTEXT})?$"),
) -> dict:
    """The source order in force for every quantity kind (in ``context`` where the firm set
    one), the firm's configured banks and what a live bank feed needs.

    各数据类型当前生效的来源顺序、已配置的银行以及实时银行接口所需条件。
    """

    from eurogas_nexus.domain.pricing import financial_institutions as fi
    from eurogas_nexus.domain.pricing import source_precedence as sp

    if not _db_is_configured():
        kinds = [
            {"kind": kind, "context": context or None, "order": list(order),
             "order_source": "default"}
            for kind, order in sp.DEFAULT_ORDERS.items()
        ]
        return _env(
            {"kinds": kinds, "institutions": [], "live_feed_terms": fi.LIVE_FEED_TERMS},
            source="runtime-db-not-configured",
            warnings=["No runtime DB configured; the defaults are shown."],
        )
    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.bank_feeds import feed_status
    from eurogas_nexus.application.source_precedence import (
        configured_institutions,
        order_in_force,
    )
    from eurogas_nexus.db.session import get_session_factory

    try:
        with get_session_factory()() as session:
            kinds = [order_in_force(session, kind, context) for kind in sp.DEFAULT_ORDERS]
            banks = [
                bank.as_dict() | {"live_feed_status": feed_status(bank)}
                for bank in configured_institutions(session)
            ]
    except SQLAlchemyError as exc:
        raise _db_unavailable(exc) from exc
    return _env(
        {"kinds": kinds, "institutions": banks, "live_feed_terms": fi.LIVE_FEED_TERMS},
        source="runtime-postgresql",
    )
