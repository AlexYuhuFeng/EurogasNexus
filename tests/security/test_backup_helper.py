"""Backup helper argument building tests (Gate 4)."""

import importlib.util
from pathlib import Path

import pytest

_backup_module = importlib.util.spec_from_file_location(
    "backup_runtime",
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "backup_runtime.py",
)
backup_runtime = importlib.util.module_from_spec(_backup_module)
_backup_module.loader.exec_module(backup_runtime)

pg_dump_args = backup_runtime.pg_dump_args
build_backup_command = backup_runtime.build_backup_command


def test_pg_dump_args_parse_dsn() -> None:
    args = pg_dump_args(
        "postgresql+pg8000://nexus:secret@db.internal:5433/nexus_test",
        Path("out.dump"),
    )
    assert args[0] == "pg_dump"
    assert "--host=db.internal" in args
    assert "--port=5433" in args
    assert "--username=nexus" in args
    assert "--file=out.dump" in args
    assert args[-1] == "nexus_test"


def test_pg_dump_args_rejects_non_postgres_urls() -> None:
    with pytest.raises(ValueError, match="requires a PostgreSQL URL"):
        pg_dump_args("sqlite+pysqlite:///x.sqlite", Path("out.dump"))


def test_build_backup_command_creates_timestamped_path(tmp_path) -> None:
    command, output_path = build_backup_command(
        "postgresql+pg8000://nexus@localhost:5432/nexus",
        tmp_path,
    )
    assert output_path.parent == tmp_path
    assert output_path.name.startswith("nexus-runtime-")
    assert output_path.name.endswith(".dump")
    assert "--format=custom" in command
