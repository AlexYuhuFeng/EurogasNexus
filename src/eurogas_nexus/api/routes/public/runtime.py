"""Runtime DB and service status route 鈥?/api/runtime/db."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["runtime"])


@router.get("/api/runtime/db")
def runtime_db_status(request: Request) -> dict:
    """Read-only runtime DB status with research metadata."""
    from eurogas_nexus.db.registry import list_required_tables
    from eurogas_nexus.db.session import redact_database_url, resolve_database_url

    url = resolve_database_url()
    report = {
        "database_url_present": url is not None,
        "redacted_database_url": redact_database_url(url),
        "connectivity": {"ok": False, "error": None},
        "alembic_revision": None,
        "required_tables": list(list_required_tables()),
        "missing_tables": list(list_required_tables()),
        "warnings": [],
    }

    if url is None:
        report["connectivity"]["error"] = "No database URL configured."
        report["warnings"].append(
            "Set RUNTIME_STORE_DATABASE_URL, DATABASE_URL, or EUROGAS_NEXUS_DB_DSN."
        )
    else:
        try:
            from eurogas_nexus.db.health import check_db_connectivity, get_alembic_revision
            from eurogas_nexus.db.session import get_engine

            conn = check_db_connectivity(url)
            report["connectivity"] = {"ok": conn.ok, "error": conn.error}
            if conn.ok:
                report["alembic_revision"] = get_alembic_revision(url)
                engine = get_engine(url)
                try:
                    from eurogas_nexus.db.registry import list_missing_required_tables
                    missing = list(list_missing_required_tables(engine))
                    report["missing_tables"] = missing
                    if missing:
                        report["warnings"].append(f"Missing tables: {', '.join(missing)}")
                finally:
                    engine.dispose()
        except Exception as exc:
            report["connectivity"]["error"] = f"{exc.__class__.__name__}: {exc}"
            report["warnings"].append("DB connectivity check failed.")

    return {
        "data": report,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [
                "runtime-postgresql" if report["connectivity"]["ok"] else "runtime-unavailable"
            ],
            "warnings": report["warnings"],
        },
    }
