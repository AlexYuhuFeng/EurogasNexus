"""Migration contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ingestion_runs_migration_exists_and_chains_to_baseline() -> None:
    migration = ROOT / "alembic" / "versions" / "0002_m4_create_ingestion_runs.py"
    text = migration.read_text(encoding="utf-8")

    assert migration.is_file()
    assert 'revision = "0002_m4_create_ingestion_runs"' in text
    assert 'down_revision = "0001_m2_baseline"' in text


def test_ingestion_runs_migration_declares_expected_columns() -> None:
    text = (ROOT / "alembic" / "versions" / "0002_m4_create_ingestion_runs.py").read_text(
        encoding="utf-8"
    )

    for token in [
        '"run_id"',
        '"source_name"',
        '"status"',
        '"started_at_utc"',
        '"finished_at_utc"',
        '"notes"',
    ]:
        assert token in text
