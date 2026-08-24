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


def test_identity_api_key_migration_chains_to_0021() -> None:
    migration = ROOT / "alembic" / "versions" / "0022_identity_api_keys.py"
    text = migration.read_text(encoding="utf-8")

    assert migration.is_file()
    assert 'revision = "0022_identity_api_keys"' in text
    assert 'down_revision = "0021_raw_payload_archives"' in text
    for token in [
        '"identity_principals"',
        '"identity_api_keys"',
        '"key_hash"',
        '"data_scopes"',
        '"revoked_at_utc"',
    ]:
        assert token in text


def test_storage_nomination_master_migration_chains_to_0022() -> None:
    migration = ROOT / "alembic" / "versions" / "0023_storage_nomination_masters.py"
    text = migration.read_text(encoding="utf-8")

    assert migration.is_file()
    assert 'revision = "0023_storage_nomination_masters"' in text
    assert 'down_revision = "0022_identity_api_keys"' in text
    for token in [
        '"storage_facility_masters"',
        '"storage_inventory_observations"',
        '"nomination_window_masters"',
    ]:
        assert token in text
