"""Isolation and disclosure tests for the market-context latency harness.

Written from a real measurement run against the runtime store: the first
statement (``observations.unbounded``) hit ``statement_timeout``, and every
statement measured after it failed with ``PendingRollbackError`` instead of a
plan - one connection, one transaction and one cancellation for the whole sweep.
The harness now opens one connection and one read-only transaction per statement
run, and these tests pin that with a fake engine that poisons its transaction
exactly the way the real one did.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError, PendingRollbackError, ProgrammingError

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "measure_market_projection_latency.py"

#: A DSN whose every part is distinctive enough to be searched for in a report.
DSN = "postgresql+pg8000://latency-operator:latency-secret@db.internal:5432/eurogas_nexus"
DSN_FRAGMENTS = (DSN, "latency-operator", "latency-secret", "db.internal")

#: Verbs that cannot run inside a read-only transaction, as the server enforces it.
_WRITE_VERBS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "COPY",
    "GRANT",
)


def _harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "measure_market_projection_latency_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    """One ``execute`` result: a scalar plan payload or a mapping sequence."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def scalar(self) -> Any:
        return self._payload

    def mappings(self) -> Any:
        return self._payload


class _FakeConnection:
    """A connection with the failed-transaction behaviour of the real driver.

    After an execute raises, every further execute raises ``PendingRollbackError``
    until ``rollback()`` is called: the exact state that turned a single
    cancellation into "every later query failed".
    """

    def __init__(self, engine: _FakeEngine) -> None:
        self.engine = engine
        self.executed: list[str] = []
        self.failed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, statement: Any, parameters: Any = None) -> _FakeResult:
        sql = " ".join(str(statement).split())
        if self.failed:
            raise PendingRollbackError(
                "This connection is on an inactive transaction.  Please rollback() "
                "prior to further commands."
            )
        self.executed.append(sql)
        self.engine.executed.append(sql)
        if self.engine.is_write(sql):
            self.engine.refusals.append(sql)
            raise ProgrammingError(
                "cannot execute a write in a read-only transaction", None, None
            )
        if self.engine.fail(sql):
            self.failed = True
            raise OperationalError(
                sql, None, Exception("canceling statement due to statement timeout")
            )
        return self.engine.result_for(sql)

    def rollback(self) -> None:
        self.failed = False
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class _FakeEngine:
    """An engine stand-in that records every connection and statement it hands out."""

    def __init__(self, fail: Any = None) -> None:
        self.fail = fail or (lambda sql: False)
        self.connections: list[_FakeConnection] = []
        self.executed: list[str] = []
        self.refusals: list[str] = []
        self.disposed = False
        self.kwargs: dict[str, Any] = {}
        self.database_url: str | None = None

    def connect(self) -> _FakeConnection:
        connection = _FakeConnection(self)
        self.connections.append(connection)
        return connection

    def dispose(self) -> None:
        self.disposed = True

    def is_write(self, sql: str) -> bool:
        """Whether the server would refuse this statement inside a read-only transaction."""

        padded = f" {sql.upper()} "
        return any(f" {verb} " in padded for verb in _WRITE_VERBS)

    def result_for(self, sql: str) -> _FakeResult:
        if "FROM pg_class" in sql:
            return _FakeResult(
                [{"table_name": "market_observations", "estimated_rows": 4_000_000}]
            )
        if "FROM pg_indexes" in sql:
            return _FakeResult(
                [
                    {
                        "table_name": "market_observations",
                        "index_name": "ix_market_observations_observed_venue_product",
                        "definition": "CREATE INDEX ... (observed_at_utc DESC)",
                    }
                ]
            )
        if "GROUP BY source_system" in sql:
            return _FakeResult(
                [
                    {
                        "source_system": "SIM_TICKS",
                        "row_count": 900_000,
                        "gas_row_count": 860_000,
                        "newest_observed_at_utc": "2026-09-25T06:00:00+00:00",
                    },
                    {
                        "source_system": "ICIS",
                        "row_count": 1_200,
                        "gas_row_count": 1_200,
                        "newest_observed_at_utc": "2026-09-25T05:30:00+00:00",
                    },
                ]
            )
        return _FakeResult(
            [
                {
                    "Plan": {
                        "Node Type": "Limit",
                        "Actual Rows": 500,
                        "Actual Total Time": 1.5,
                        "Shared Hit Blocks": 3,
                        "Shared Read Blocks": 0,
                        "Plans": [],
                    },
                    "Execution Time": 2.0,
                    "Planning Time": 0.4,
                }
            ]
        )


def _measure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repeat: int = 1,
    dsn: str = DSN,
    fail: Any = None,
) -> tuple[ModuleType, _FakeEngine, dict[str, Any], int]:
    """Run the harness's DB measurement against the fake engine."""

    from eurogas_nexus import db as db_module

    module = _harness()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", dsn)
    engine = _FakeEngine(fail=fail)

    def fake_get_engine(database_url: str, **kwargs: Any) -> _FakeEngine:
        engine.database_url = database_url
        engine.kwargs = kwargs
        return engine

    monkeypatch.setattr(db_module, "get_engine", fake_get_engine)
    report, exit_code = module._measure_db(repeat, 60_000)
    return module, engine, report, exit_code


def _explained_sql(module: ModuleType, index: int = 0) -> str:
    """The statement the harness actually issues for one measured entry."""

    _, statement = module._statements()[index]
    return " ".join(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {statement}".split())


def _measured_connections(engine: _FakeEngine) -> list[_FakeConnection]:
    """The connections that carried a measured statement, in issue order."""

    return [
        connection
        for connection in engine.connections
        if any(sql.startswith("EXPLAIN") for sql in connection.executed)
    ]


def test_a_timed_out_statement_does_not_poison_the_statements_measured_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first statement aborting is one failed run, not the end of the sweep."""

    module = _harness()
    timed_out = _explained_sql(module)
    _, engine, report, exit_code = _measure(monkeypatch, fail=lambda sql: sql == timed_out)

    assert exit_code == 0
    first, second = report["statements"][0], report["statements"][1]
    assert len(first["errors"]) == 1
    assert first["errors"][0].startswith("run 1: OperationalError:")
    assert "OperationalError" in first["runs"][0]["error"]
    assert "statement timeout" in first["runs"][0]["error"]
    # The statement after the failure was measured on its own connection, so it
    # reports a plan rather than inheriting a poisoned transaction.
    assert second["errors"] == []
    assert second["runs"][0]["execution_ms"] == 1.5
    assert second["runs"][0]["actual_rows"] == 500
    assert report["statements_failed"] == 1
    assert all(entry["errors"] == [] for entry in report["statements"][1:])
    assert not any(
        "PendingRollbackError" in failure
        for entry in report["statements"]
        for failure in entry["errors"]
    )
    # The probe and the three inventory reads (tables, indexes, sources), then one
    # connection per measured run.
    assert len(engine.connections) == len(report["statements"]) + 4
    measured = _measured_connections(engine)
    assert len(measured) == len(report["statements"])
    failed_connection = measured[0]
    assert failed_connection.executed[-1] == timed_out
    assert failed_connection.rolled_back is True
    assert failed_connection.closed is True
    assert engine.disposed is True


def test_a_failed_repetition_does_not_stop_the_next_repetition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each repetition is its own transaction, so run 2 survives run 1's timeout."""

    module = _harness()
    timed_out = _explained_sql(module)
    remaining = {"failures": 1}

    def fail_first_occurrence(sql: str) -> bool:
        if sql == timed_out and remaining["failures"]:
            remaining["failures"] -= 1
            return True
        return False

    _, engine, report, exit_code = _measure(monkeypatch, repeat=2, fail=fail_first_occurrence)

    assert exit_code == 0
    entry = report["statements"][0]
    assert len(entry["runs"]) == 2
    assert "error" in entry["runs"][0]
    assert entry["runs"][1]["execution_ms"] == 1.5
    assert entry["execution_ms_min"] == 1.5
    assert entry["execution_ms_median"] == 1.5
    assert report["statements_failed"] == 1
    # Two runs of the first statement, on two different connections.
    measured = _measured_connections(engine)
    assert len(engine.connections) == 2 * len(report["statements"]) + 4
    assert len(measured) == 2 * len(report["statements"])
    assert measured[0] is not measured[1]


def test_every_measured_run_gets_its_own_read_only_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read-only first, one connection per run, rolled back and closed after it."""

    module, engine, report, exit_code = _measure(monkeypatch)

    assert exit_code == 0
    # The probe and the three inventory reads (tables, indexes, sources), then one
    # connection per measured run.
    assert len(engine.connections) == len(report["statements"]) + 4
    for connection in engine.connections:
        assert connection.executed[0] == "SET TRANSACTION READ ONLY"
        assert connection.executed[1] == "SET LOCAL statement_timeout = 60000"
        assert connection.rolled_back is True
        assert connection.closed is True
    assert engine.connections[0].executed[-1] == "SELECT 1"
    assert len(_measured_connections(engine)) == len(report["statements"])
    # No connection carried two measured statements, and no statement the harness
    # issued is one a read-only transaction would refuse.
    assert engine.refusals == []
    assert all(sql.startswith(("SET ", "EXPLAIN ", "SELECT ")) for sql in engine.executed)
    assert all(statement.lstrip().startswith("SELECT") for _, statement in module._statements())


def test_both_source_coverage_shapes_are_measured_with_their_real_statements() -> None:
    """The superseded shape stays measurable, and the shipped pages are its own SQL."""

    module = _harness()
    names = [name for name, _ in module._statements(["ICIS", "SIM_TICKS"])]
    statements = dict(module._statements(["ICIS", "SIM_TICKS"]))

    assert "normalized.source_count" in names
    assert "normalized.source_coverage_window" in names
    assert "row_number() OVER (PARTITION BY" in statements[
        "normalized.source_coverage_window"
    ]
    assert [
        name for name in names if name.startswith(module.SOURCE_PAGE_PREFIX)
    ] == [
        f"{module.SOURCE_PAGE_PREFIX}ICIS",
        f"{module.SOURCE_PAGE_PREFIX}SIM_TICKS",
    ]
    page = statements[f"{module.SOURCE_PAGE_PREFIX}ICIS"]
    assert page.lstrip().startswith("SELECT")
    assert "source_system = 'ICIS'" in page
    assert "unit ILIKE '%MWH%'" in page
    # The route's own order fields, with no tie-break appended: rows tied on all
    # three are the store's choice, exactly as they were for the ranking window.
    assert "ORDER BY observed_at_utc DESC, market_venue, product LIMIT" in page
    assert "observation_id DESC" not in page
    # The shipped read's page bound is the repository's per-source bound.
    assert f"LIMIT {min(module.PER_SOURCE_LIMIT, module.QUOTE_LIMIT)}" in page
    assert "row_number" not in page.lower()


def test_a_source_value_that_is_not_a_plain_identifier_is_never_quoted_into_sql() -> None:
    """Source values are data: the harness reports them instead of interpolating them."""

    module = _harness()
    measured, skipped = module._measureable_sources(
        [
            {"source_system": "SIM_TICKS"},
            {"source_system": "O'Hara; DROP TABLE market_observations"},
            {"source_system": ""},
        ],
        max_sources=5,
    )

    assert measured == ["SIM_TICKS"]
    assert skipped == ["O'Hara; DROP TABLE market_observations", ""]
    assert all(
        "DROP" not in statement for _, statement in module._statements(measured)
    )


def test_the_source_cap_is_reported_instead_of_measuring_a_silent_subset() -> None:
    """Sources beyond the cap are named as not measured, not dropped quietly."""

    module = _harness()
    inventory = [{"source_system": f"SRC_{index}"} for index in range(5)]

    measured, skipped = module._measureable_sources(inventory, max_sources=2)

    assert measured == ["SRC_0", "SRC_1"]
    assert skipped == ["SRC_2", "SRC_3", "SRC_4"]


def test_the_comparison_sums_measured_statements_and_never_invents_a_number() -> None:
    """Each shape's total is a sum of measurements, and a missing side stays unknown."""

    module = _harness()
    statements = [
        {"name": "normalized.source_count", "execution_ms_median": 786.0},
        {"name": "normalized.source_coverage_window", "execution_ms_median": 3336.0},
        {"name": "normalized.source_page.SIM_TICKS", "execution_ms_median": 0.4},
        {"name": "normalized.source_page.ICIS", "execution_ms_median": 0.2},
    ]

    comparison = module._compare_shapes(
        statements,
        page_bound=40,
        sources_measured=["SIM_TICKS", "ICIS"],
        sources_not_measured=[],
    )

    assert comparison["superseded_shape"]["execution_ms"] == 4122.0
    assert comparison["per_source_shape"]["execution_ms"] == 0.6
    assert comparison["per_source_shape"]["statement_count"] == 2
    assert comparison["per_source_shape"]["page_bound"] == 40
    assert comparison["ratio_superseded_over_per_source"] == 6870.0
    # The comparison is server plan time, and says that it excludes round trips.
    assert any("neither includes network round trips" in note for note in comparison["notes"])
    assert any("fallback" in note for note in comparison["notes"])
    assert any("not a performance gate" in note for note in comparison["notes"])

    # A measured statement that failed, and a side that never ran at all, are
    # "not measured" rather than zero.
    failed_page = module._compare_shapes(
        [entry for entry in statements if entry["name"] != "normalized.source_page.ICIS"]
        + [{"name": "normalized.source_page.ICIS", "errors": ["run 1: OperationalError"]}],
        page_bound=40,
        sources_measured=["SIM_TICKS", "ICIS"],
        sources_not_measured=[],
    )
    missing_superseded = module._compare_shapes(
        [entry for entry in statements if entry["name"] != "normalized.source_coverage_window"],
        page_bound=40,
        sources_measured=["SIM_TICKS", "ICIS"],
        sources_not_measured=[],
    )

    assert failed_page["per_source_shape"]["execution_ms"] is None
    assert failed_page["ratio_superseded_over_per_source"] is None
    assert missing_superseded["superseded_shape"]["execution_ms"] is None
    assert missing_superseded["ratio_superseded_over_per_source"] is None


def test_the_measured_per_source_pages_come_from_the_source_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fake store's own sources decide which pages are measured."""

    _, _, report, exit_code = _measure(monkeypatch)
    names = [entry["name"] for entry in report["statements"]]

    assert exit_code == 0
    assert [name for name in names if name.startswith("normalized.source_page.")] == [
        "normalized.source_page.SIM_TICKS",
        "normalized.source_page.ICIS",
    ]
    assert report["sources"] == [
        {
            "source_system": "SIM_TICKS",
            "row_count": 900_000,
            "gas_row_count": 860_000,
            "newest_observed_at_utc": "2026-09-25T06:00:00+00:00",
        },
        {
            "source_system": "ICIS",
            "row_count": 1_200,
            "gas_row_count": 1_200,
            "newest_observed_at_utc": "2026-09-25T05:30:00+00:00",
        },
    ]
    assert report["comparison"]["per_source_shape"]["sources_measured"] == [
        "SIM_TICKS",
        "ICIS",
    ]
    assert report["comparison"]["per_source_shape"]["sources_not_measured"] == []
    # Both sides are sums of the same fake plans, so neither is a placeholder.
    assert report["comparison"]["superseded_shape"]["execution_ms"] == 3.0
    assert report["comparison"]["per_source_shape"]["execution_ms"] == 3.0


def test_the_source_cap_bounds_the_measured_pages_and_is_disclosed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``max_sources`` bounds the harness's own runtime and says what it left out."""

    module = _harness()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", DSN)
    engine = _FakeEngine()

    def fake_get_engine(database_url: str, **kwargs: Any) -> _FakeEngine:
        engine.database_url = database_url
        engine.kwargs = kwargs
        return engine

    from eurogas_nexus import db as db_module

    monkeypatch.setattr(db_module, "get_engine", fake_get_engine)
    report, exit_code = module._measure_db(1, 60_000, max_sources=1)

    names = [entry["name"] for entry in report["statements"]]
    assert exit_code == 0
    assert [name for name in names if name.startswith("normalized.source_page.")] == [
        "normalized.source_page.SIM_TICKS"
    ]
    assert report["comparison"]["per_source_shape"]["sources_measured"] == ["SIM_TICKS"]
    assert report["comparison"]["per_source_shape"]["sources_not_measured"] == ["ICIS"]
    assert any("not measured (cap 1" in warning for warning in report["warnings"])


def test_a_failed_source_inventory_leaves_the_comparison_one_sided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable inventory is reported, and the shipped side stays unmeasured."""

    module = _harness()
    _, engine, report, exit_code = _measure(
        monkeypatch,
        fail=lambda sql: "GROUP BY source_system" in sql,
    )

    assert exit_code == 0
    assert report["sources"] is None
    assert report["statements_failed"] == 0
    assert [entry["name"] for entry in report["statements"]] == [
        name for name, _ in module._statements()
    ]
    assert report["comparison"]["per_source_shape"]["execution_ms"] is None
    assert report["comparison"]["per_source_shape"]["statement_count"] == 0
    assert report["comparison"]["ratio_superseded_over_per_source"] is None
    assert any(
        "Per-source pages were not measured" in warning for warning in report["warnings"]
    )
    # The inventory statement was attempted, and its own connection was closed.
    assert any("GROUP BY source_system" in sql for sql in engine.executed)
    assert all(connection.closed for connection in engine.connections)


def test_the_report_never_carries_the_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The harness documents "never prints the DSN"; the report names presence only."""

    module, engine, report, exit_code = _measure(monkeypatch)

    assert exit_code == 0
    assert engine.database_url == DSN
    assert report["database_url_present"] is True
    assert "redacted_database_url" not in report
    encoded = json.dumps(report, indent=2, sort_keys=True)
    module._print_human(report)
    printed = capsys.readouterr().out
    for fragment in DSN_FRAGMENTS:
        assert fragment not in encoded, fragment
        assert fragment not in printed, fragment
    assert "Runtime database: configured" in printed
    assert f"driver socket timeout: {report['driver_timeout_seconds']} s" in printed


def test_no_configured_database_reports_presence_only_and_exit_code_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a store there is nothing to measure, and the report says so."""

    for name in ("RUNTIME_STORE_DATABASE_URL", "DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(name, raising=False)

    report, exit_code = _harness()._measure_db(1, 60_000)

    assert exit_code == 2
    assert report["database_url_present"] is False
    assert report["statements"] == []
    assert report["tables"] is None
    assert report["indexes"] is None
    assert "redacted_database_url" not in report
    assert any("RUNTIME_STORE_DATABASE_URL" in warning for warning in report["warnings"])


def test_an_unreachable_store_aborts_instead_of_reporting_every_statement_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store that cannot be reached was not measured, whatever the error said."""

    from eurogas_nexus import db as db_module

    module = _harness()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", DSN)

    class _UnreachableEngine(_FakeEngine):
        def connect(self) -> _FakeConnection:
            raise OperationalError(
                "SELECT 1",
                None,
                Exception(f"could not connect to {DSN}"),
            )

    engine = _UnreachableEngine()
    monkeypatch.setattr(
        db_module,
        "get_engine",
        lambda database_url, **kwargs: engine,
    )

    report, exit_code = module._measure_db(1, 60_000)

    assert exit_code == 2
    assert report["statements"] == []
    assert report["statements_failed"] == 0
    assert report["tables"] is None
    assert report["indexes"] is None
    assert report["warnings"][-1] == "Measurement aborted: OperationalError."
    assert engine.disposed is True
    for fragment in DSN_FRAGMENTS:
        assert fragment not in json.dumps(report, sort_keys=True), fragment


def test_the_driver_socket_timeout_stays_above_the_server_statement_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The server must be the side that aborts a slow plan, and both bounds are finite."""

    module = _harness()

    for requested in (0, 1000, 20_000, 60_000, 599_999, 600_000, 10_000_000):
        statement_timeout_ms, driver_seconds = module._driver_socket_timeout_seconds(requested)
        assert module.MIN_STATEMENT_TIMEOUT_MS <= statement_timeout_ms
        assert statement_timeout_ms <= module.MAX_STATEMENT_TIMEOUT_MS
        assert driver_seconds > statement_timeout_ms / 1000
        assert driver_seconds <= module.MAX_DRIVER_TIMEOUT_SECONDS
    assert module._driver_socket_timeout_seconds(0)[0] == module.MIN_STATEMENT_TIMEOUT_MS
    assert module._driver_socket_timeout_seconds(10**9)[0] == module.MAX_STATEMENT_TIMEOUT_MS

    _, engine, report, _ = _measure(monkeypatch)
    assert engine.kwargs == {"connect_timeout_seconds": report["driver_timeout_seconds"]}
    assert report["driver_timeout_seconds"] > report["statement_timeout_ms"] / 1000


def test_the_fake_connection_poisons_further_statements_until_rollback() -> None:
    """The isolation tests would be vacuous if the fake did not behave like the driver.

    This is the failure that hid every statement behind the first one's timeout:
    an execute after a raised execute raises ``PendingRollbackError`` until the
    aborted transaction is rolled back.
    """

    engine = _FakeEngine(fail=lambda sql: sql.startswith("EXPLAIN"))
    connection = engine.connect()

    with pytest.raises(OperationalError):
        connection.execute("EXPLAIN ANALYZE SELECT 1")
    with pytest.raises(PendingRollbackError):
        connection.execute("SELECT count(*) FROM market_observations")

    connection.rollback()

    assert connection.execute("SELECT count(*) FROM market_observations").scalar() is not None
