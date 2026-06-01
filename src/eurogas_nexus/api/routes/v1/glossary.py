"""Read-only /api/v1/glossary routes for English and Mandarin terms."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.domain.analysis import build_glossary_context
from eurogas_nexus.domain.glossary import GlossaryTerm, baseline_glossary_terms

router = APIRouter(tags=["glossary"])


@router.get("/api/v1/glossary")
def list_terms(
    request: Request,
    lang: str = Query("en", pattern="^(en|zh|zh-CN)$"),
    category: str | None = Query(None),
    q: str | None = Query(None),
) -> dict:
    terms, source, warnings = _load_terms()
    filtered = _filter_terms(terms, category=category, query=q)
    return _env(
        [term.localized(lang) for term in filtered],
        source=source,
        warnings=warnings,
    )


@router.get("/api/v1/glossary/{term}")
def get_term(
    term: str,
    request: Request,
    lang: str = Query("en", pattern="^(en|zh|zh-CN)$"),
) -> dict:
    terms, source, warnings = _load_terms()
    normalized = term.strip().lower()
    for item in terms:
        candidates = {
            item.term.lower(),
            item.term_id.lower(),
            *(alias.lower() for alias in item.aliases),
        }
        if normalized in candidates:
            return _env(item.localized(lang), source=source, warnings=warnings)
    raise HTTPException(404, f"Term '{term}' not found.")


@router.get("/api/v1/glossary/{term}/context")
def get_term_context(
    term: str,
    request: Request,
    lang: str = Query("en", pattern="^(en|zh|zh-CN)$"),
    duration_start_utc: Annotated[datetime | None, Query()] = None,
    duration_end_utc: Annotated[datetime | None, Query()] = None,
) -> dict:
    """Return operational context for a glossary term when known."""

    from eurogas_nexus.api.routes.v1.analysis import _load_snapshot

    snapshot = _load_snapshot(
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    context = build_glossary_context(
        term,
        snapshot,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
        lang=lang,
    )
    return _env(
        context.model_dump(mode="json"),
        source=snapshot.source,
        warnings=context.warnings,
    )


def _filter_terms(
    terms: list[GlossaryTerm],
    *,
    category: str | None,
    query: str | None,
) -> list[GlossaryTerm]:
    filtered = terms
    if category:
        category_key = category.strip().lower()
        filtered = [term for term in filtered if term.category.lower() == category_key]
    if query:
        query_key = query.strip().lower()
        filtered = [
            term
            for term in filtered
            if query_key in term.term.lower()
            or query_key in term.definition_en.lower()
            or query_key in term.definition_zh_cn.lower()
            or any(query_key in alias.lower() for alias in term.aliases)
        ]
    return sorted(filtered, key=lambda item: (item.category, item.term.lower()))


def _load_terms() -> tuple[list[GlossaryTerm], str, list[str]]:
    if not _db_is_configured():
        return (
            baseline_glossary_terms(),
            "baseline-glossary",
            ["No runtime DB configured; using built-in bilingual glossary baseline."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import GlossaryTermRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(GlossaryTermRecord).filter(
                GlossaryTermRecord.active.is_(True)
            ).order_by(GlossaryTermRecord.category, GlossaryTermRecord.term)
            terms = [
                GlossaryTerm(
                    term_id=row.term_id,
                    term=row.term,
                    category=row.category,
                    definition_en=row.definition_en,
                    definition_zh_cn=row.definition_zh_cn,
                    aliases=row.aliases,
                    related_terms=row.related_terms,
                    source_refs=row.source_refs,
                )
                for row in rows.all()
            ]
        if terms:
            return terms, "runtime-postgresql", []
        return (
            baseline_glossary_terms(),
            "baseline-glossary",
            ["Runtime DB has no active glossary terms; using built-in bilingual baseline."],
        )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for glossary reads.",
            "error_class": exc.__class__.__name__,
        },
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
