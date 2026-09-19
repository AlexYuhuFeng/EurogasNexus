"""The runtime DB validator's report must not state more than it checked.

Found while finishing slice D: pointing `RUNTIME_STORE_DATABASE_URL` at a bare
`postgresql://` URL - the scheme most operators would type, and one that makes SQLAlchemy select
psycopg2, a driver this project does not depend on - made the validator print all 93 required
tables as missing after a connectivity failure. The database had not been shown to be missing
anything; nothing had been inspected. That is the same defect the platform refuses to make about
missing data elsewhere: an unmeasured result rendered as a measured one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "validate_runtime_db.py"


def _validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_runtime_db_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _status(ok: bool, error: str | None) -> Any:
    from eurogas_nexus.db import DbConnectivityStatus

    return DbConnectivityStatus(ok=ok, database_url_present=True, error=error)


def test_no_configured_database_is_not_a_list_of_missing_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    report, exit_code = _validator()._build_report()

    assert exit_code == 2
    assert report["database_url_present"] is False
    # Not inspected is a different statement from empty, and the report says which one it is.
    assert report["missing_tables"] is None
    assert report["table_inspection"] == "not-performed"
    assert any("RUNTIME_STORE_DATABASE_URL" in warning for warning in report["warnings"])


def test_an_unreachable_database_reports_the_driver_the_url_chose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus import db as db_module

    monkeypatch.setenv(
        "RUNTIME_STORE_DATABASE_URL",
        "postgresql://nexus:secret@db.internal:5432/eurogas_nexus",
    )
    monkeypatch.setattr(
        db_module,
        "check_db_connectivity",
        lambda url=None: _status(False, "ModuleNotFoundError: No module named 'psycopg2'"),
    )

    report, exit_code = _validator()._build_report()

    assert exit_code == 2
    assert report["missing_tables"] is None
    assert report["table_inspection"] == "not-performed"
    warnings = " ".join(report["warnings"])
    # The operator is told which driver the URL selected and which one the project uses.
    assert "psycopg2" in warnings
    assert "pg8000" in warnings
    assert "postgresql+pg8000://" in warnings
    assert "did not run" in warnings
    # The credentials never reach the report.
    assert "secret" not in warnings
    assert "secret" not in str(report["redacted_database_url"])


def test_a_reachable_database_still_reconciles_the_required_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus import db as db_module

    monkeypatch.setenv(
        "RUNTIME_STORE_DATABASE_URL",
        "postgresql+pg8000://nexus:secret@db.internal:5432/eurogas_nexus",
    )
    monkeypatch.setattr(db_module, "check_db_connectivity", lambda url=None: _status(True, None))
    monkeypatch.setattr(db_module, "list_missing_required_tables", lambda engine: [])
    monkeypatch.setattr(db_module, "get_alembic_revision", lambda url: "0036_job_records")

    class _Engine:
        def dispose(self) -> None:
            return None

    monkeypatch.setattr(db_module, "get_engine", lambda url: _Engine())

    report, exit_code = _validator()._build_report()

    assert exit_code == 0
    assert report["table_inspection"] == "performed"
    assert report["missing_tables"] == []
    assert report["alembic_revision"] == "0036_job_records"
    assert report["warnings"] == []


def test_a_missing_table_is_still_reported_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus import db as db_module

    monkeypatch.setenv(
        "RUNTIME_STORE_DATABASE_URL",
        "postgresql+pg8000://nexus:secret@db.internal:5432/eurogas_nexus",
    )
    monkeypatch.setattr(db_module, "check_db_connectivity", lambda url=None: _status(True, None))
    monkeypatch.setattr(
        db_module, "list_missing_required_tables", lambda engine: ["decision_cases"]
    )
    monkeypatch.setattr(db_module, "get_alembic_revision", lambda url: "0035_decision_cases")

    class _Engine:
        def dispose(self) -> None:
            return None

    monkeypatch.setattr(db_module, "get_engine", lambda url: _Engine())

    report, exit_code = _validator()._build_report()

    assert exit_code == 2
    assert report["table_inspection"] == "performed"
    assert report["missing_tables"] == ["decision_cases"]
