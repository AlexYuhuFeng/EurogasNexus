"""CAP-1 measurement script: sizes and row counts, read-only.

Run on SQLite here; the PostgreSQL statements are checked to be reads.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3

import pytest

from scripts.capacity import measure_db


def _store(path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE flow_observations (id TEXT PRIMARY KEY, value REAL)")
    connection.execute("CREATE INDEX ix_flow_value ON flow_observations (value)")
    connection.execute("CREATE TABLE market_events (seq INTEGER PRIMARY KEY, payload TEXT)")
    connection.executemany(
        "INSERT INTO flow_observations VALUES (?, ?)", [(f"f{i}", i * 1.5) for i in range(250)]
    )
    connection.executemany(
        "INSERT INTO market_events (payload) VALUES (?)", [("x" * 200,) for _ in range(40)]
    )
    connection.commit()
    connection.close()


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_counts_rows_per_table_and_leaves_the_file_unchanged(tmp_path, capsys):
    store = tmp_path / "store.db"
    _store(store)
    before = _digest(store)

    assert measure_db.main(["--url", f"sqlite:///{store}", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)
    rows = {table["table_name"]: table["rows"] for table in result["tables"]}
    assert rows == {"flow_observations": 250, "market_events": 40}
    assert result["dialect"] == "sqlite"
    assert result["database"] == "store.db"
    assert result["database_bytes"] > 0
    assert all(table["rows_basis"] == "exact" for table in result["tables"])
    assert _digest(store) == before


def test_text_output_names_the_database_but_not_the_url(tmp_path, capsys):
    store = tmp_path / "secret-path-store.db"
    _store(store)

    assert measure_db.main(["--url", f"sqlite:///{store}", "--top", "1"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("sqlite database secret-path-store.db:")
    assert str(tmp_path) not in out
    # --top 1 keeps one table row under the header.
    assert len([line for line in out.splitlines() if line.startswith(("flow_", "market_"))]) == 1


def test_the_store_is_opened_read_only(tmp_path):
    store = tmp_path / "store.db"
    _store(store)
    from sqlalchemy.engine import make_url

    connection = sqlite3.connect(measure_db._sqlite_read_only_url(make_url(f"sqlite:///{store}")),
                                 uri=True)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        connection.execute("DELETE FROM market_events")
    connection.close()


def test_an_in_memory_store_is_refused():
    with pytest.raises(SystemExit):
        measure_db.measure("sqlite://")


WRITES = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|VACUUM|ANALYZE|COPY)\b"


def test_postgres_statements_are_reads_in_a_read_only_transaction():
    assert measure_db.POSTGRES_READ_ONLY_SQL == "SET TRANSACTION READ ONLY"
    for statement in (measure_db.POSTGRES_TABLES_SQL, measure_db.POSTGRES_DATABASE_SQL):
        assert statement.strip().upper().startswith("SELECT")
        assert not re.search(WRITES, statement.upper())


def test_missing_url_is_an_error(monkeypatch, capsys):
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    assert measure_db.main([]) == 2
    assert "RUNTIME_STORE_DATABASE_URL" in capsys.readouterr().err
