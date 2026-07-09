"""DB runtime hardening contract tests (DB-free)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# --- registry contract -------------------------------------------------------

def test_required_table_registry_exists_and_is_importable() -> None:
    from eurogas_nexus.db.registry import REQUIRED_TABLES, RequiredTable

    assert len(REQUIRED_TABLES) >= 2
    assert isinstance(REQUIRED_TABLES[0], RequiredTable)


def test_registry_introduced_in_matches_known_migrations() -> None:
    from eurogas_nexus.db.registry import REQUIRED_TABLES

    revisions = {t.introduced_in for t in REQUIRED_TABLES}
    assert "0001_m2_baseline" in revisions
    assert "0002_m4_create_ingestion_runs" in revisions


def test_required_table_names_returns_ordered_list() -> None:
    from eurogas_nexus.db.registry import required_table_names

    names = required_table_names()
    assert "alembic_version" in names
    assert "ingestion_runs" in names


# --- health contract ---------------------------------------------------------

def test_db_health_module_exports_status_type() -> None:
    from eurogas_nexus.db.health import DbRuntimeStatus

    status = DbRuntimeStatus(reachable=True, redacted_dsn="pg://u:****@h/db")
    assert status.reachable is True
    assert "****" in status.redacted_dsn


def test_db_connectivity_status_is_importable() -> None:
    from eurogas_nexus.db.health import DbConnectivityStatus

    status = DbConnectivityStatus(
        ok=True, database_url_present=True, redacted_database_url="pg://u:****@h/db"
    )
    assert status.ok is True
    assert "****" in (status.redacted_database_url or "")


# --- runtime store contract --------------------------------------------------

def test_result_envelope_has_required_metadata_fields() -> None:
    from eurogas_nexus.runtime_store.contracts import ResultEnvelope

    envelope = ResultEnvelope(payload={"key": "val"})
    assert envelope.research_only is True
    assert envelope.human_review_required is True
    assert isinstance(envelope.assumptions, list)
    assert isinstance(envelope.missing_inputs, list)
    assert isinstance(envelope.warnings, list)
    assert isinstance(envelope.source_references, list)
    assert isinstance(envelope.lineage, list)


def test_result_envelope_defaults_to_research_only() -> None:
    from eurogas_nexus.runtime_store.contracts import ResultEnvelope

    envelope = ResultEnvelope(payload=42)
    assert envelope.research_only is True


def test_no_file_fallback_raises_in_trial_and_release() -> None:
    from eurogas_nexus.runtime_store.contracts import (
        _no_file_fallback_in_trial_or_release,
    )

    for env in ("trial", "release"):
        with __import__("pytest").raises(RuntimeError, match="forbidden"):
            _no_file_fallback_in_trial_or_release(env)


def test_no_file_fallback_allows_development() -> None:
    from eurogas_nexus.runtime_store.contracts import (
        _no_file_fallback_in_trial_or_release,
    )

    # Must not raise.
    _no_file_fallback_in_trial_or_release("development")
    _no_file_fallback_in_trial_or_release("test")


# --- docs existence ----------------------------------------------------------

def test_live_postgresql_v1_doc_exists() -> None:
    assert (ROOT / "docs" / "operations" / "LIVE_POSTGRESQL_V1.md").is_file()


def test_db_runtime_hardening_doc_exists() -> None:
    assert (ROOT / "docs" / "operations" / "DB_RUNTIME_HARDENING.md").is_file()


def test_milestone_2_report_files_exist() -> None:
    assert (ROOT / "data" / "milestone_2" / "db_runtime_hardening_report.md").is_file()
    assert (ROOT / "data" / "milestone_2" / "db_runtime_hardening_report.json").is_file()


def test_milestone_2_json_report_is_valid() -> None:
    data = json.loads(
        (ROOT / "data" / "milestone_2" / "db_runtime_hardening_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["milestone"] == "M2"
    assert data["status"] == "complete"


# --- validation script -------------------------------------------------------

def test_validation_script_exists_and_is_executable() -> None:
    script = ROOT / "scripts" / "ops" / "validate_v1_runtime_db.py"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert "from validate_runtime_db import main" in content
    assert "migration away from milestone-style naming" in content


def test_validation_script_references_redaction() -> None:
    script = ROOT / "scripts" / "ops" / "validate_runtime_db.py"
    content = script.read_text(encoding="utf-8")
    assert "redact_database_url" in content
    assert "never prints a full dsn" in content.lower()
