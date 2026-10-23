"""A restore drill must probe the target DB with the required migration head."""

import os
import runpy
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from eurogas_nexus.db.registry import get_metadata
from eurogas_nexus.release.constants import DB_SCHEMA_REVISION


@pytest.mark.parametrize(
    "revision,expected", [(DB_SCHEMA_REVISION, 200), ("0040_strategy_owner_sharing", 503)]
)
def test_restore_probe_uses_target_and_restores_source_configuration(
    tmp_path, monkeypatch, revision, expected
):
    target = "sqlite+pysqlite:///" + str(tmp_path / "restored.sqlite")
    engine = create_engine(target)
    get_metadata().create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(64))")
        conn.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (revision,))
    engine.dispose()
    source = "sqlite+pysqlite:///" + str(tmp_path / "untouched-source.sqlite")
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", source)
    script = Path(__file__).resolve().parents[2] / "scripts/ops/backup_restore_drill.py"
    probe = runpy.run_path(str(script))["restored_api_readiness"]
    assert probe(target) == expected
    assert os.environ["RUNTIME_STORE_DATABASE_URL"] == source
    assert not (tmp_path / "untouched-source.sqlite").exists()
