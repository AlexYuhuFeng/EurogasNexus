"""Alembic import-safety tests."""

import importlib.util
from pathlib import Path

from eurogas_nexus.db.registry import list_required_tables

ROOT = Path(__file__).resolve().parents[2]


def test_alembic_env_imports_metadata_without_running_migrations() -> None:
    env_path = ROOT / "alembic" / "env.py"
    spec = importlib.util.spec_from_file_location("tests.alembic_env_import_safe", env_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.target_metadata is not None


def test_required_table_registry_is_explicit_and_stable() -> None:
    required = list_required_tables()
    assert "alembic_version" in required
    assert "ingestion_runs" in required
