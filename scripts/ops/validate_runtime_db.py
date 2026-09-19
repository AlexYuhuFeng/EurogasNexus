"""Validate the runtime PostgreSQL database non-destructively.

Never writes, never prints a full DSN, never runs migrations.

The table reconciliation runs only once the database answers, so the report keeps
`missing_tables` as `None` (not inspected) until then: an unreachable database has
not been shown to be missing every required table, and saying so would be the same
mistake this project refuses to make about missing data elsewhere.

Usage:
    python scripts/ops/validate_runtime_db.py
    python scripts/ops/validate_runtime_db.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

#: The driver this project depends on, and the URL scheme that selects it.
_PROJECT_DRIVER = "pg8000"
_PROJECT_SCHEME = "postgresql+pg8000"

_MISSING_MODULE = re.compile(r"No module named '([^']+)'")


def _driver_warning(error: str | None) -> str | None:
    """Explain an unimportable DBAPI driver, because the URL chooses it and not the project.

    SQLAlchemy picks the driver from the URL: a bare `postgresql://` means psycopg2, which this
    project does not depend on. Without this line the operator sees a connectivity failure and a
    driver name, with nothing saying which scheme the deployment actually uses.
    """
    if not error or "ModuleNotFoundError" not in error:
        return None
    match = _MISSING_MODULE.search(error)
    module = match.group(1) if match else "the driver named in the URL"
    return (
        f"The driver this URL selects ({module}) is not installed. This project depends on "
        f"{_PROJECT_DRIVER}: use {_PROJECT_SCHEME}://<user>:<password>@<host>:<port>/<database>."
    )


def _build_report() -> tuple[dict[str, Any], int]:
    from eurogas_nexus.db import (  # noqa: E402
        check_db_connectivity,
        get_alembic_revision,
        get_engine,
        list_missing_required_tables,
        list_required_tables,
        redact_database_url,
        resolve_database_url,
    )

    database_url = resolve_database_url()
    required_tables = list(list_required_tables())
    report: dict[str, Any] = {
        "database_url_present": database_url is not None,
        "redacted_database_url": redact_database_url(database_url),
        "connectivity": {"ok": False, "error": None},
        "required_tables": required_tables,
        # None means "not inspected", which is a different statement from an empty list.
        "missing_tables": None,
        "table_inspection": "not-performed",
        "alembic_revision": None,
        "decision_support": True,
        "human_review_required": True,
        "warnings": [],
    }

    if database_url is None:
        report["connectivity"]["error"] = "Database URL is missing."
        report["warnings"].append(
            "Set RUNTIME_STORE_DATABASE_URL, DATABASE_URL, or legacy EUROGAS_NEXUS_DB_DSN."
        )
        return report, 2

    connectivity = check_db_connectivity(database_url)
    report["connectivity"] = {
        "ok": connectivity.ok,
        "error": connectivity.error,
    }
    if not connectivity.ok:
        report["warnings"].append("Runtime DB connectivity check failed.")
        driver_warning = _driver_warning(connectivity.error)
        if driver_warning:
            report["warnings"].append(driver_warning)
        report["warnings"].append(
            "The required-table check did not run, so the tables are not reported as missing."
        )
        return report, 2

    engine = None
    try:
        engine = get_engine(database_url)
        report["missing_tables"] = list(list_missing_required_tables(engine))
        report["table_inspection"] = "performed"
    except Exception as exc:
        report["warnings"].append(f"Required table inspection failed: {exc.__class__.__name__}.")
        return report, 2
    finally:
        if engine is not None:
            engine.dispose()

    report["alembic_revision"] = get_alembic_revision(database_url)
    if report["missing_tables"]:
        report["warnings"].append("Required runtime tables are missing.")
        return report, 2

    return report, 0


def main(argv: list[str] | None = None) -> int:
    """    Validate the runtime DB against the required table registry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    report, exit_code = _build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return exit_code

    print("Eurogas Nexus runtime DB validation")
    print(f"Database URL present: {report['database_url_present']}")
    print(f"Database URL: {report['redacted_database_url'] or 'not configured'}")
    print(f"Connectivity: {'ok' if report['connectivity']['ok'] else 'failed'}")
    if report["connectivity"]["error"]:
        print(f"Connectivity error: {report['connectivity']['error']}")
    print(f"Required tables: {', '.join(report['required_tables']) or 'none'}")
    if report["table_inspection"] == "performed":
        print(f"Missing tables: {', '.join(report['missing_tables'] or []) or 'none'}")
    else:
        print("Missing tables: not checked (no database connection)")
    print(f"Alembic revision: {report['alembic_revision'] or 'unavailable'}")
    for warning in report["warnings"]:
        print(f"Warning: {warning}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
