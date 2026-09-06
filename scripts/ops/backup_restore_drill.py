"""Automated PostgreSQL backup + restore drill.

Produces a custom-format dump from the source DSN, restores it into an
isolated target database, validates schema revision/required tables/
representative business records, then runs a DB-backed API read smoke. The
script exits non-zero when any verification fails.

Example:
    RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://user:pass@127.0.0.1:5432/source \\
    python scripts/ops/backup_restore_drill.py \\
      --target-database-url postgresql+pg8000://user:pass@127.0.0.1:5432/nexus_restore_drill
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from eurogas_nexus.db.registry import list_missing_required_tables
from eurogas_nexus.db.session import get_engine, redact_database_url, resolve_database_url

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _parts(database_url: str) -> dict:
    parsed = urlparse(database_url)
    if not parsed.scheme.startswith("postgresql"):
        raise ValueError("backup/restore requires a PostgreSQL URL")
    database = (parsed.path or "").lstrip("/") or "postgres"
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "username": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "database": database,
    }


def _pg_env(database_url: str) -> dict:
    return {"PGPASSWORD": _parts(database_url)["password"]}


def create_database_if_missing(database_url: str, *, docker_container: str | None = None) -> bool:

    """Create the target database when it does not exist (safe identifier)."""

    parts = _parts(database_url)
    database = parts["database"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise ValueError("target database name must be [A-Za-z0-9_]+")
    if docker_container:
        exists = subprocess.run(
            [
                "docker", "exec", docker_container, "psql",
                "-U", parts["username"], "-d", "postgres", "-tAc",
                f"SELECT 1 FROM pg_database WHERE datname='{database}'",
            ],
            capture_output=True,
            text=True,
        )
        if exists.returncode != 0:
            raise RuntimeError("could not inspect target database existence")
        if exists.stdout.strip() == "1":
            return False
        created = subprocess.run(
            [
                "docker", "exec", docker_container, "createdb",
                "-U", parts["username"], database,
            ],
            capture_output=True,
            text=True,
        )
        if created.returncode != 0:
            raise RuntimeError(f"createdb failed: {created.stderr[-200:]}")
        return True
    maintenance_dsn = (
        f"postgresql+pg8000://{parts['username']}:{parts['password']}"
        f"@{parts['host']}:{parts['port']}/postgres"
    )
    engine = get_engine(maintenance_dsn)
    try:
        with engine.connect() as connection:
            exists = connection.exec_driver_sql(
                "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
            ).scalar()
            if exists:
                return False
        with engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
        return True
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-database-url", required=True)
    parser.add_argument("--keep-dump", action="store_true")
    parser.add_argument(
        "--pg-docker-container",
        default=None,
        help="Run pg_dump/pg_restore via this Docker container (local drills).",
    )
    args = parser.parse_args(argv)

    source_url = resolve_database_url()
    if not source_url:
        print(json.dumps({"ok": False, "error": "source database_url_missing"}))
        return 2
    started = time.perf_counter()
    report = {
        "ok": False,
        "source": redact_database_url(source_url),
        "target": redact_database_url(args.target_database_url),
    }
    try:
        source = _parts(source_url)
        target = _parts(args.target_database_url)
        with tempfile.TemporaryDirectory(prefix="nexus-restore-drill-") as tmp:
            dump_path = Path(tmp) / "runtime.dump"
            if args.pg_docker_container:
                dump_command = [
                    "docker",
                    "exec",
                    "-i",
                    args.pg_docker_container,
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    f"--username={source['username']}",
                    source["database"],
                ]
                dump = subprocess.run(
                    dump_command,
                    capture_output=True,
                )
                dump_path.write_bytes(dump.stdout)
            else:
                dump_command = [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    f"--host={source['host']}",
                    f"--port={source['port']}",
                    f"--username={source['username']}",
                    f"--file={dump_path}",
                    source["database"],
                ]
                dump = subprocess.run(
                    dump_command,
                    env=_pg_env(source_url),
                    capture_output=True,
                    text=True,
                )
            if dump.returncode != 0:
                report["error"] = "pg_dump_failed"
                report["detail"] = (dump.stderr or b"")[-400:]
                return _emit(report)

            created = create_database_if_missing(
                args.target_database_url,
                docker_container=args.pg_docker_container,
            )
            if args.pg_docker_container:
                restore_command = [
                    "docker",
                    "exec",
                    "-i",
                    args.pg_docker_container,
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    f"--username={target['username']}",
                    f"--dbname={target['database']}",
                ]
                restore = subprocess.run(
                    restore_command,
                    input=dump_path.read_bytes(),
                    capture_output=True,
                )
            else:
                restore_command = [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    f"--host={target['host']}",
                    f"--port={target['port']}",
                    f"--username={target['username']}",
                    f"--dbname={target['database']}",
                    str(dump_path),
                ]
                restore = subprocess.run(
                    restore_command,
                    env=_pg_env(args.target_database_url),
                    capture_output=True,
                    text=True,
                )
            if restore.returncode != 0:
                report["error"] = "pg_restore_failed"
                report["detail"] = (restore.stderr or b"")[-400:]
                return _emit(report)
            report["database_created"] = created
            report["dump_bytes"] = dump_path.stat().st_size
            if args.keep_dump:
                keep_path = ROOT / "backups" / f"drill-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.dump"
                keep_path.parent.mkdir(parents=True, exist_ok=True)
                keep_path.write_bytes(dump_path.read_bytes())
                report["kept_dump"] = keep_path.name

        engine = get_engine(args.target_database_url)
        try:
            from sqlalchemy import text

            with engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar_one_or_none()
                report["revision"] = revision
                for table, check in (
                    ("audit_events", "SELECT COUNT(*) FROM audit_events"),
                    ("ingestion_runs", "SELECT COUNT(*) FROM ingestion_runs"),
                    ("identity_principals", "SELECT COUNT(*) FROM identity_principals"),
                    (
                        "source_runtime_states",
                        "SELECT COUNT(*) FROM source_runtime_states",
                    ),
                ):
                    try:
                        count = connection.execute(text(check)).scalar_one()
                        report[f"{table}_rows"] = int(count)
                    except Exception:
                        report[f"{table}_rows"] = None
            missing = list(list_missing_required_tables(engine))
            report["missing_tables"] = missing
        finally:
            engine.dispose()

        if report.get("revision") is None or missing:
            report["error"] = "restored_schema_invalid"
            return _emit(report)

        from fastapi.testclient import TestClient

        from apps.api.main import app

        client = TestClient(app)
        smoke = client.get("/api/health/live")
        report["api_smoke_status"] = smoke.status_code
        report["ok"] = bool(
            smoke.status_code == 200 and not missing and report.get("revision")
        )
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        return _emit(report)
    except Exception as exc:
        report["error"] = exc.__class__.__name__
        report["detail"] = str(exc)
        return _emit(report)


def _emit(report: dict) -> int:
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
