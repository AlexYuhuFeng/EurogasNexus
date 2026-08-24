"""Runtime PostgreSQL backup helper (pg_dump wrapper).

Produces timestamped custom-format dumps under ``backups/`` and prints the
matching restore command. Restore drills are an operator procedure documented
in ``docs/operations/BACKUP_RESTORE.md``.

Usage:
    python scripts/ops/backup_runtime.py [output_dir]
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from eurogas_nexus.db.session import resolve_database_url


def pg_dump_args(database_url: str, output_path: Path) -> list[str]:
    """Build a pg_dump argument list for a DSN (postgresql+driver://...)."""

    parsed = urlparse(database_url)
    if not (parsed.scheme.startswith("postgresql") or parsed.scheme == "postgres"):
        raise ValueError(
            f"backup requires a PostgreSQL URL, got scheme {parsed.scheme!r}"
        )
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    args = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        f"--host={host}",
        f"--port={port}",
        f"--username={unquote(parsed.username)}" if parsed.username else "--username=postgres",
        f"--file={output_path}",
    ]
    if parsed.path and parsed.path.strip("/"):
        args.append(parsed.path.strip("/"))
    else:
        args.append("postgres")
    return args


def build_backup_command(database_url: str, output_dir: Path) -> tuple[list[str], Path]:
    """Return (pg_dump argv, output path) for one timestamped backup."""

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"nexus-runtime-{stamp}.dump"
    return pg_dump_args(database_url, output_path), output_path


def main(argv: list[str] | None = None) -> int:
    """    Back up the runtime store to the output directory."""
    args = list(argv) if argv is not None else sys.argv[1:]
    output_dir = Path(args[0]) if args else Path("backups")
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    try:
        command, output_path = build_backup_command(database_url, output_dir)
    except ValueError as exc:
        print(f"backup refused: {exc}")
        return 2

    print("Running: " + " ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print(f"pg_dump failed with exit code {result.returncode}")
        return 1
    print(f"Backup written: {output_path}")
    print(
        "Restore (see docs/operations/BACKUP_RESTORE.md): "
        f"pg_restore --clean --if-exists --dbname=<target> {output_path.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
