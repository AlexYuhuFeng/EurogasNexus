"""Print table sizes and row counts of a runtime store, read-only (CAP-1).

    python scripts/capacity/measure_db.py                        # RUNTIME_STORE_DATABASE_URL
    python scripts/capacity/measure_db.py --url sqlite:///store.db --json
    python scripts/capacity/measure_db.py --exact --top 25       # count(*) per table

The figures feed the capacity model in
docs/engineering/Commercial-Intelligence-V3/19_DATA_CAPACITY_AND_INFRASTRUCTURE.md: rows,
bytes on disk (heap, indexes and TOAST on PostgreSQL) and bytes per row, per table.

Read-only by construction: on PostgreSQL every statement runs in a transaction set
``READ ONLY`` and is a ``SELECT`` over the catalogue (row counts come from the planner's
estimate unless ``--exact``); on SQLite the file is opened with ``mode=ro``. The database URL
is never printed, only its dialect and database name.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

#: Every statement this script sends to PostgreSQL. A test checks they are all reads.
POSTGRES_TABLES_SQL = """
SELECT c.relname AS table_name,
       GREATEST(c.reltuples, 0)::bigint AS estimated_rows,
       pg_relation_size(c.oid) AS heap_bytes,
       pg_indexes_size(c.oid) AS index_bytes,
       pg_total_relation_size(c.oid) AS total_bytes
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p')
ORDER BY pg_total_relation_size(c.oid) DESC
"""
POSTGRES_DATABASE_SQL = "SELECT current_database(), pg_database_size(current_database())"
POSTGRES_READ_ONLY_SQL = "SET TRANSACTION READ ONLY"


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _postgres(engine, exact: bool) -> dict[str, Any]:
    from sqlalchemy import text

    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text(POSTGRES_READ_ONLY_SQL))
            name, database_bytes = connection.execute(text(POSTGRES_DATABASE_SQL)).one()
            rows = [dict(row._mapping) for row in connection.execute(text(POSTGRES_TABLES_SQL))]
            for row in rows:
                # TOAST (large text and JSON stored out of line) is what the total holds
                # beyond the heap and the indexes.
                row["toast_bytes"] = row["total_bytes"] - row["heap_bytes"] - row["index_bytes"]
                row["rows"] = row.pop("estimated_rows")
                row["rows_basis"] = "estimate"
                if exact:
                    statement = f"SELECT count(*) FROM {_quote_identifier(row['table_name'])}"
                    row["rows"] = connection.execute(text(statement)).scalar_one()
                    row["rows_basis"] = "exact"
    return {"database": name, "database_bytes": int(database_bytes), "tables": rows}


def _sqlite_read_only_url(url) -> str:
    database = url.database or ""
    if not database or database == ":memory:":
        raise SystemExit("an SQLite store must be a file to be measured read-only")
    return f"file:{Path(database).resolve()}?mode=ro"


def _sqlite(url) -> dict[str, Any]:
    import sqlite3

    path = _sqlite_read_only_url(url)
    connection = sqlite3.connect(path, uri=True)
    try:
        names = [
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        sizes: dict[str, int] = {}
        try:
            for name, size in connection.execute(
                "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name"
            ):
                sizes[name] = int(size)
        except sqlite3.DatabaseError:
            sizes = {}
        index_owner = dict(
            connection.execute(
                "SELECT name, tbl_name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        )
        tables = []
        for name in names:
            count = connection.execute(f"SELECT count(*) FROM {_quote_identifier(name)}")
            heap = sizes.get(name)
            index = sum(size for idx, size in sizes.items() if index_owner.get(idx) == name)
            tables.append(
                {
                    "table_name": name,
                    "rows": int(count.fetchone()[0]),
                    "rows_basis": "exact",
                    "heap_bytes": heap,
                    "index_bytes": index if sizes else None,
                    "total_bytes": (heap or 0) + index if sizes else None,
                }
            )
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    finally:
        connection.close()
    tables.sort(key=lambda row: (row["total_bytes"] or 0, row["rows"]), reverse=True)
    return {
        "database": Path(url.database).name,
        "database_bytes": int(page_size) * int(page_count),
        "tables": tables,
    }


def measure(url_text: str, *, exact: bool = False) -> dict[str, Any]:
    """Return the store's size and per-table rows and bytes; changes nothing."""

    from sqlalchemy.engine import make_url

    url = make_url(url_text)
    dialect = url.get_backend_name()
    if dialect == "sqlite":
        result = _sqlite(url)
    elif dialect == "postgresql":
        from eurogas_nexus.db.session import get_engine

        result = _postgres(get_engine(url_text), exact)
    else:
        raise SystemExit(f"unsupported database dialect: {dialect}")
    for row in result["tables"]:
        total, rows = row.get("total_bytes"), row.get("rows") or 0
        row["bytes_per_row"] = round(total / rows) if total is not None and rows else None
    result["dialect"] = dialect
    return result


def _human(value: int | None) -> str:
    if value is None:
        return "-"
    size = float(value)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} TB"


def as_text(result: dict[str, Any], top: int) -> str:
    tables = result["tables"][:top] if top else result["tables"]
    lines = [
        f"{result['dialect']} database {result['database']}: "
        f"{_human(result['database_bytes'])} in {len(result['tables'])} tables",
        "",
        f"{'table':40} {'rows':>14} {'basis':>8} {'heap':>11} {'indexes':>11} "
        f"{'total':>11} {'B/row':>8}",
    ]
    for row in tables:
        lines.append(
            f"{row['table_name'][:40]:40} {row['rows']:>14,} {row['rows_basis']:>8} "
            f"{_human(row['heap_bytes']):>11} {_human(row['index_bytes']):>11} "
            f"{_human(row['total_bytes']):>11} "
            f"{row['bytes_per_row'] if row['bytes_per_row'] is not None else '-':>8}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", help="database URL (default: RUNTIME_STORE_DATABASE_URL)")
    parser.add_argument("--exact", action="store_true", help="count(*) each table (slower)")
    parser.add_argument("--top", type=int, default=0, help="show only the N largest tables")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    url = args.url or os.environ.get("RUNTIME_STORE_DATABASE_URL")
    if not url:
        print("Pass --url or set RUNTIME_STORE_DATABASE_URL.", file=sys.stderr)
        return 2
    result = measure(url, exact=args.exact)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(as_text(result, args.top), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
