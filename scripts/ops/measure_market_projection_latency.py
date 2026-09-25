"""Measure the ``/api/projections/market-context`` read paths against the runtime DB.

This is a **read-only triage harness**, written for the bounded latency
investigation of that projection. It never writes, never runs migrations, never
prints the DSN, and refuses to guess: a statement that cannot run is reported as
an error, not as a zero.

Isolation is the other half of that promise. Every statement run - and every
repetition of it - gets its own connection and its own read-only transaction, so
a statement that aborts (a ``statement_timeout`` cancellation, a missing table,
a syntax error) is contained to the run that hit it. One transaction for the
whole sweep is exactly the shape that turned a single cancellation into a
``PendingRollbackError`` on every statement measured after it. Each transaction
is opened with ``SET TRANSACTION READ ONLY`` before anything is explained, and
the driver's socket timeout is kept above the server's ``statement_timeout``, so
a slow plan is stopped by the server's own clean cancellation rather than by the
client tearing the connection down.

What it measures (``--db``, the default):

1. how many rows the tables of the projection's call tree actually hold;
2. the indexes that exist on them (an avoidable full scan is usually a missing
   index, and that decision needs the real plan, not a guess);
3. ``EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`` for every statement the call tree
   issues, in the shape the application issues it (read-only SELECTs only), with
   the top plan node, actual rows, actual milliseconds and shared buffer reads.
4. ``market_observations`` per source: how many rows each source holds, how many
   of them are gas rows, and its newest observed instant - the inventory a reader
   needs to judge the source-coverage read's cost;
5. the source-coverage read in **both** shapes: the superseded one keeps its two
   statements (``normalized.source_count`` and
   ``normalized.source_coverage_window``, the second ranking every gas row of the
   table), and the shipped one is measured as its actual per-source pages
   (``normalized.source_page.<source>``, one statement per source, each bounded by
   the page limit the repository applies). ``comparison`` sums each shape's
   measured medians and states what that does and does not include; the two shapes
   are compared by their *measured* statements, never by an assumed speedup.
   The superseded statements are also the repository's fallback when the
   reservation cannot fit, so they stay measurable for that case too.

What it measures (``--python-only``), without any database connection: the
per-row Python costs the bounded repair changes - one latest-rate graph build per
conversion (the pre-repair shape) versus one per view, and observation row
shaping - on synthetic fixture records held in memory. It never reads or writes
the runtime database and never persists a price anywhere.

Neither mode is a performance gate: it reports what the database did on this
machine at this moment.

Usage:
    python scripts/ops/measure_market_projection_latency.py
    python scripts/ops/measure_market_projection_latency.py --repeat 3 --json
    python scripts/ops/measure_market_projection_latency.py --python-only
    python scripts/ops/measure_market_projection_latency.py --statement-timeout-ms 20000
    python scripts/ops/measure_market_projection_latency.py --max-sources 4
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

#: Slice bounds the projection applies by default (api/routes/public/projections.py).
QUOTE_LIMIT = 500
OBSERVATION_LIMIT = 500
ALERT_LIMIT = 100
OPPORTUNITY_LIMIT = 100

#: Bound on the per-statement server abort and on the driver's own socket timeout.
MIN_STATEMENT_TIMEOUT_MS = 1000
MAX_STATEMENT_TIMEOUT_MS = 600_000

#: The driver's socket timeout is the server's statement timeout plus this margin,
#: and is itself bounded: the server must be the side that aborts a slow plan, so
#: this must stay strictly above ``statement_timeout``.
DRIVER_TIMEOUT_HEADROOM_SECONDS = 30
MAX_DRIVER_TIMEOUT_SECONDS = MAX_STATEMENT_TIMEOUT_MS // 1000 + DRIVER_TIMEOUT_HEADROOM_SECONDS

#: Tables the projection's call tree reads, with the columns it materializes.
_OBSERVATION_COLUMNS = (
    "observation_id, market_venue, product, price, unit, currency, "
    "period_start_utc, period_end_utc, observed_at_utc, source_system, "
    "source_reference, source_record_id, freshness, quality_score, research_only, "
    "metadata_json"
)

#: The repository's per-source reservation bound (``per_source_limit``), and the
#: row bound the normalized endpoint asks for (``QUOTE_LIMIT``). The per-source
#: page the repository issues is ``min(per_source_limit, limit)`` rows.
PER_SOURCE_LIMIT = 40

#: Sources whose per-source page is measured by default. The shipped read issues one
#: statement per source, so this harness's own runtime grows with the source count;
#: the cap keeps a deployment with many sources measurable, and the report says how
#: many sources were measured and how many were left out.
DEFAULT_MAX_SOURCES = 12

#: Statement-name prefix that marks one measured per-source page.
SOURCE_PAGE_PREFIX = "normalized.source_page."

#: Source values are data, so the harness interpolates one into its own read-only
#: SQL only when it is a plain identifier. Anything else is reported as unmeasured
#: rather than quoted into a statement.
_SOURCE_VALUE_PATTERN = re.compile(r"[A-Za-z0-9_.:\-]{1,64}\Z")


def _statements(source_systems: Sequence[str] = ()) -> list[tuple[str, str]]:
    """Return the (name, SQL) pairs of the projection's read statements.

    The SQL is written the way the ORM issues it, so a plan measured here is the
    plan the endpoint gets. ``observations.unbounded`` is the shape the market
    context read used before its slice was bounded in SQL; it is kept in the
    report so the avoided cost is measurable rather than asserted.

    ``normalized.source_count`` and ``normalized.source_coverage_window`` are the
    superseded source-coverage shape, kept for the same reason: the cost the
    per-source pages avoid stays measurable instead of asserted. Those two statements
    are also what the repository keeps for the rare case where the reservation cannot
    fit (more gas sources than the payload bound), so the superseded numbers are that
    fallback's cost as well. Every name in ``source_systems`` adds that source's page
    statement, the shape
    :func:`eurogas_nexus.db.repositories.market_intelligence.list_market_observations_with_source_coverage`
    now issues - one bounded read per source, ordered by the route's own order fields
    (rows tied on all three are left to the store, as the ranking window left them).
    """

    observation_order = "ORDER BY observed_at_utc DESC, market_venue, product"
    page_bound = min(PER_SOURCE_LIMIT, QUOTE_LIMIT)
    statements = [
        (
            "observations.count",
            "SELECT count(*) AS raw_count FROM market_observations",
        ),
        (
            "observations.unbounded",
            f"SELECT {_OBSERVATION_COLUMNS} FROM market_observations {observation_order}",
        ),
        (
            "observations.bounded",
            f"SELECT {_OBSERVATION_COLUMNS} FROM market_observations "
            f"{observation_order} LIMIT {OBSERVATION_LIMIT}",
        ),
        (
            "observations.allowed_sources",
            "SELECT DISTINCT source_system FROM market_observations",
        ),
        (
            "fx.allowed_sources",
            "SELECT DISTINCT source_system FROM fx_observations",
        ),
        (
            "normalized.newest_observations",
            f"SELECT {_OBSERVATION_COLUMNS} FROM market_observations "
            f"{observation_order} LIMIT {QUOTE_LIMIT}",
        ),
        (
            "normalized.source_count",
            "SELECT count(DISTINCT source_system) FROM market_observations "
            "WHERE unit ILIKE '%MWH%'",
        ),
        (
            "normalized.source_coverage_window",
            "SELECT market_observations.observation_id, anon_1.source_rank "
            "FROM market_observations JOIN ("
            "SELECT market_observations.observation_id AS observation_id, "
            "row_number() OVER (PARTITION BY market_observations.source_system "
            "ORDER BY market_observations.observed_at_utc DESC, "
            "market_observations.market_venue, market_observations.product) "
            "AS source_rank FROM market_observations "
            "WHERE unit ILIKE '%MWH%') AS anon_1 "
            "ON anon_1.observation_id = market_observations.observation_id "
            "WHERE anon_1.source_rank <= 40",
        ),
    ]
    statements += [
        (
            f"{SOURCE_PAGE_PREFIX}{source}",
            f"SELECT {_OBSERVATION_COLUMNS} FROM market_observations "
            f"WHERE source_system = '{source}' AND unit ILIKE '%MWH%' "
            "ORDER BY observed_at_utc DESC, market_venue, product "
            f"LIMIT {page_bound}",
        )
        for source in source_systems
    ]
    statements += [
        (
            "normalized.fx_rows",
            "SELECT observation_id, pair, base_currency, quote_currency, rate, "
            "rate_type, value_date, observed_at_utc, source_system "
            "FROM fx_observations ORDER BY observed_at_utc DESC, pair",
        ),
        (
            "normalized.ecb_fallback",
            "SELECT observation_id, market_venue, product, price, unit, currency, "
            "observed_at_utc FROM market_observations "
            "WHERE source_system = 'ECB' ORDER BY observed_at_utc DESC",
        ),
        (
            "quotes.newest",
            "SELECT quote_id, source_system, venue, instrument_id, hub, product, "
            "bid_price, ask_price, last_price, currency, unit, observed_at_utc, "
            "freshness, quality_score, simulated FROM market_quotes "
            f"ORDER BY observed_at_utc DESC LIMIT {QUOTE_LIMIT}",
        ),
        (
            "opportunities.newest",
            "SELECT opportunity_id, status, buy_hub, sell_hub, product, "
            "gross_spread, detected_at_utc, valid_until_utc FROM intraday_opportunities "
            f"ORDER BY detected_at_utc DESC LIMIT {OPPORTUNITY_LIMIT}",
        ),
        (
            "monitoring.summary_rows",
            "SELECT alert_id, status, severity, simulated, llm_status "
            "FROM monitoring_alerts",
        ),
        (
            "monitoring.alerts",
            "SELECT alert_id, status, severity, updated_at_utc, detected_at_utc "
            "FROM monitoring_alerts ORDER BY updated_at_utc DESC, "
            f"detected_at_utc DESC LIMIT {ALERT_LIMIT}",
        ),
    ]
    return statements


def _table_inventory(connection) -> list[dict[str, Any]]:
    """Report estimated row counts for the projection's tables (no writes)."""

    from sqlalchemy import text

    tables = (
        "market_observations",
        "fx_observations",
        "market_quotes",
        "intraday_opportunities",
        "monitoring_alerts",
    )
    rows = connection.execute(
        text(
            """
            SELECT relname AS table_name, reltuples::bigint AS estimated_rows
            FROM pg_class
            WHERE relname = ANY(:names)
            ORDER BY relname
            """
        ),
        {"names": list(tables)},
    ).mappings()
    return [dict(row) for row in rows]


def _index_inventory(connection) -> list[dict[str, Any]]:
    """Report the indexes the projection's queries can actually use."""

    from sqlalchemy import text

    rows = connection.execute(
        text(
            """
            SELECT tablename AS table_name, indexname AS index_name, indexdef AS definition
            FROM pg_indexes
            WHERE tablename IN (
                'market_observations', 'fx_observations', 'market_quotes',
                'intraday_opportunities', 'monitoring_alerts'
            )
            ORDER BY tablename, indexname
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def _source_inventory(connection) -> list[dict[str, Any]]:
    """Report ``market_observations`` per source: rows, gas rows and newest instant.

    The source-coverage read issues one statement per source, so how many sources
    exist and how large each one is *is* the scaling answer; it is measured rather
    than assumed. Counts and one timestamp per source are reported - no price, no
    identity and no row content.
    """

    from sqlalchemy import text

    rows = connection.execute(
        text(
            """
            SELECT source_system,
                   count(*) AS row_count,
                   count(*) FILTER (WHERE unit ILIKE '%MWH%') AS gas_row_count,
                   max(observed_at_utc) AS newest_observed_at_utc
            FROM market_observations
            GROUP BY source_system
            ORDER BY count(*) DESC, source_system
            """
        )
    ).mappings()
    inventory: list[dict[str, Any]] = []
    for row in rows:
        newest = row["newest_observed_at_utc"]
        inventory.append(
            {
                "source_system": row["source_system"],
                "row_count": int(row["row_count"] or 0),
                "gas_row_count": int(row["gas_row_count"] or 0),
                "newest_observed_at_utc": (
                    newest.isoformat() if hasattr(newest, "isoformat") else newest
                ),
            }
        )
    return inventory


def _measureable_sources(
    inventory: Sequence[dict[str, Any]] | None,
    *,
    max_sources: int,
) -> tuple[list[str], list[str]]:
    """Split the inventory into the sources whose page is measured and the rest.

    The inventory arrives largest first. A source whose value is not a plain
    identifier is never quoted into this harness's own SQL, and a source beyond
    ``max_sources`` is not measured either - both are returned in the "not
    measured" list so the report can say what it left out instead of quietly
    measuring a subset.
    """

    if not inventory:
        return [], []
    names = [str(row.get("source_system") or "") for row in inventory]
    readable = [name for name in names if _SOURCE_VALUE_PATTERN.fullmatch(name)]
    unreadable = [name for name in names if not _SOURCE_VALUE_PATTERN.fullmatch(name)]
    return readable[: max(1, max_sources)], readable[max(1, max_sources) :] + unreadable


def _measurement(entry: dict[str, Any] | None) -> float | None:
    """One measured statement's median milliseconds, or None when it did not run."""

    if entry is None:
        return None
    value = entry.get("execution_ms_median")
    return float(value) if isinstance(value, int | float) else None


def _compare_shapes(
    statements: Sequence[dict[str, Any]],
    *,
    page_bound: int,
    sources_measured: Sequence[str],
    sources_not_measured: Sequence[str],
) -> dict[str, Any]:
    """Sum each source-coverage read shape's measured statement medians.

    Both sides are sums of *measured server plan times*: the superseded shape is its
    gas source count plus its ranking window, the shipped shape is one bounded page
    per measured source. Summing server times excludes the network round trips the
    shapes pay in production - two for the superseded shape whatever the source
    count, one per source for the shipped shape - so the comparison exposes the
    statement cost, not the trip cost. Neither side is estimated, and a side with a
    statement that did not run is reported as unmeasured rather than as a zero.
    """

    by_name = {entry.get("name"): entry for entry in statements}
    superseded = [
        _measurement(by_name.get("normalized.source_count")),
        _measurement(by_name.get("normalized.source_coverage_window")),
    ]
    per_source = [
        _measurement(entry)
        for name, entry in by_name.items()
        if isinstance(name, str) and name.startswith(SOURCE_PAGE_PREFIX)
    ]
    superseded_total = (
        None if any(value is None for value in superseded) else round(sum(superseded), 3)
    )
    per_source_total = (
        None
        if not per_source or any(value is None for value in per_source)
        else round(sum(per_source), 3)
    )
    return {
        "superseded_shape": {
            "statements": ["normalized.source_count", "normalized.source_coverage_window"],
            "execution_ms": superseded_total,
        },
        "per_source_shape": {
            "statement_count": len(per_source),
            "page_bound": page_bound,
            "sources_measured": list(sources_measured),
            "sources_not_measured": list(sources_not_measured),
            "execution_ms": per_source_total,
        },
        "ratio_superseded_over_per_source": (
            round(superseded_total / per_source_total, 2)
            if superseded_total is not None and per_source_total
            else None
        ),
        "notes": [
            "SQL plan times from EXPLAIN (ANALYZE, BUFFERS), excluding Python "
            "shaping, row transfer and connection setup.",
            "Both sides are sums of server plan times, so neither includes network "
            "round trips: in production the superseded shape pays two round trips "
            "whatever the source count, the shipped shape one per source.",
            "The superseded statements are also the repository's fallback when the "
            "candidate sources outnumber the payload bound (the reservation may not "
            "fit), so these numbers are that fallback's cost as well.",
            "The shipped read also issues one source enumeration unless the caller "
            "already holds its entitled source set (observations.allowed_sources "
            "is the projection's, and is measured above but excluded from both "
            "sums).",
            "Each per-source page is written for an index on (source_system, "
            "observed_at_utc); the plan nodes under its statement show whether this "
            "deployment's planner used one.",
            "A statement that did not run leaves its side - and the ratio - "
            "unmeasured rather than zero.",
            "This is a triage measurement on this machine at this moment, not a "
            "performance gate and not production load acceptance.",
        ],
    }


def _explain(connection, statement: str) -> dict[str, Any]:
    """Run one read-only ``EXPLAIN (ANALYZE, BUFFERS)`` and summarize the plan."""

    from sqlalchemy import text

    payload = connection.execute(
        text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {statement}")
    ).scalar()
    top = payload[0] if isinstance(payload, list) else payload
    top = top if isinstance(top, dict) else {}
    plan = top.get("Plan") or {}
    return {
        "execution_ms": float(plan.get("Actual Total Time", 0.0)),
        "total_ms": float(top.get("Execution Time", 0.0) or 0.0),
        "planning_ms": float(top.get("Planning Time", 0.0) or 0.0),
        "actual_rows": int(plan.get("Actual Rows", 0) or 0),
        "top_node": plan.get("Node Type"),
        "shared_hit_blocks": int(plan.get("Shared Hit Blocks", 0) or 0),
        "shared_read_blocks": int(plan.get("Shared Read Blocks", 0) or 0),
        "scan_nodes": _scan_nodes(plan),
    }


def _scan_nodes(plan: dict[str, Any], depth: int = 0) -> list[dict[str, Any]]:
    """Collect the scan/sort nodes that make up a plan, with their row counts."""

    nodes: list[dict[str, Any]] = []
    node_type = str(plan.get("Node Type") or "")
    if node_type in {"Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Sort"}:
        nodes.append(
            {
                "type": node_type,
                "relation": plan.get("Relation Name"),
                "actual_rows": int(plan.get("Actual Rows", 0) or 0),
                "actual_ms": float(plan.get("Actual Total Time", 0.0) or 0.0),
                "depth": depth,
            }
        )
    for child in plan.get("Plans") or []:
        nodes.extend(_scan_nodes(child, depth + 1))
    return nodes


def _bounded_statement_timeout_ms(statement_timeout_ms: int) -> int:
    """Clamp the requested per-statement abort into the harness's supported range."""

    return min(max(int(statement_timeout_ms), MIN_STATEMENT_TIMEOUT_MS), MAX_STATEMENT_TIMEOUT_MS)


def _driver_socket_timeout_seconds(statement_timeout_ms: int) -> tuple[int, int]:
    """Return ``(statement_timeout_ms, driver_socket_timeout_seconds)``, both bounded.

    ``get_engine(connect_timeout_seconds=...)`` is the driver's own socket
    timeout (pg8000 applies it to socket operations), so it must exceed the
    server's ``statement_timeout``: the server has to be the side that stops a
    slow plan, with a clean cancellation, instead of the client giving up on a
    socket and tearing the connection down mid-statement.
    """

    bounded_ms = _bounded_statement_timeout_ms(statement_timeout_ms)
    timeout_seconds = math.ceil(bounded_ms / 1000) + DRIVER_TIMEOUT_HEADROOM_SECONDS
    return bounded_ms, min(timeout_seconds, MAX_DRIVER_TIMEOUT_SECONDS)


@contextmanager
def _read_only_connection(engine: Any, statement_timeout_ms: int) -> Iterator[Any]:
    """Yield one connection holding one fresh, read-only, bounded transaction.

    ``SET TRANSACTION READ ONLY`` is the transaction's first statement, so the
    server itself refuses a write even if this harness ever grew one, and ``SET
    LOCAL statement_timeout`` bounds each statement below the driver's socket
    timeout. The transaction is rolled back on the way out whether the body
    succeeded or raised, and the connection is closed (returned to the pool)
    afterwards - so an aborted statement leaves nothing behind for the next
    statement to inherit.
    """

    from sqlalchemy import text

    connection = engine.connect()
    try:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}"))
        yield connection
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def _measure_statement(
    engine: Any,
    name: str,
    statement: str,
    *,
    repeat: int,
    statement_timeout_ms: int,
) -> dict[str, Any]:
    """Explain one statement ``repeat`` times, one isolated transaction per run.

    A run that aborts is recorded as that run's error and nothing more: the run
    after it opens a new connection, so a missing table or a statement timeout
    cannot hide the statements measured after it.
    """

    entry: dict[str, Any] = {
        "name": name,
        "sql": " ".join(statement.split()),
        "runs": [],
        "errors": [],
    }
    for index in range(max(1, repeat)):
        try:
            with _read_only_connection(engine, statement_timeout_ms) as connection:
                run = {"run": index + 1, **_explain(connection, statement)}
        except Exception as exc:
            message = f"run {index + 1}: {exc.__class__.__name__}: {exc}"
            entry["errors"].append(message)
            entry["runs"].append({"run": index + 1, "error": message})
        else:
            entry["runs"].append(run)
    successful = [run for run in entry["runs"] if "error" not in run]
    if successful:
        entry["execution_ms_min"] = round(min(run["execution_ms"] for run in successful), 3)
        entry["execution_ms_median"] = round(
            statistics.median(run["execution_ms"] for run in successful), 3
        )
        entry["last_run"] = successful[-1]
    return entry


def _measure_db(
    repeat: int,
    statement_timeout_ms: int,
    *,
    max_sources: int = DEFAULT_MAX_SOURCES,
) -> tuple[dict[str, Any], int]:
    """Measure every statement of the projection's call tree, read-only.

    The report identifies the database by presence only: the DSN never enters
    it, redacted or otherwise. The source inventory decides which per-source pages
    are measured (largest sources first, at most ``max_sources`` of them); the
    report names the ones it did not measure.
    """

    from sqlalchemy import text

    from eurogas_nexus.db import get_engine, resolve_database_url

    database_url = resolve_database_url()
    statement_timeout_ms, driver_timeout_seconds = _driver_socket_timeout_seconds(
        statement_timeout_ms
    )
    report: dict[str, Any] = {
        "mode": "db",
        "database_url_present": database_url is not None,
        "statement_timeout_ms": statement_timeout_ms,
        "driver_timeout_seconds": driver_timeout_seconds,
        "repeat": repeat,
        # ``None`` reads as "not measured" (see the printer and the warnings);
        # an empty list would read as "there are none".
        "tables": None,
        "indexes": None,
        "sources": None,
        "statements": [],
        "statements_failed": 0,
        "comparison": None,
        "warnings": [
            "EXPLAIN (ANALYZE) executes each SELECT; it writes nothing, but it does "
            "read the tables and can be slow on the largest ones.",
        ],
    }
    if database_url is None:
        report["warnings"].append(
            "Set RUNTIME_STORE_DATABASE_URL, DATABASE_URL or EUROGAS_NEXUS_DB_DSN."
        )
        return report, 2

    engine = get_engine(database_url, connect_timeout_seconds=driver_timeout_seconds)
    try:
        # A store that cannot be reached at all is not "measured with failures":
        # one probe decides that, before any statement is reported on.
        try:
            with _read_only_connection(engine, statement_timeout_ms) as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            report["warnings"].append(f"Measurement aborted: {exc.__class__.__name__}.")
            return report, 2
        for key, reader in (
            ("tables", _table_inventory),
            ("indexes", _index_inventory),
            ("sources", _source_inventory),
        ):
            try:
                with _read_only_connection(engine, statement_timeout_ms) as connection:
                    report[key] = reader(connection)
            except Exception as exc:  # a missing table must not hide the statements
                report[key] = None
                report["warnings"].append(
                    f"{key.capitalize()} inventory could not be read: "
                    f"{exc.__class__.__name__}."
                )
        measured_sources, unmeasured_sources = _measureable_sources(
            report["sources"],
            max_sources=max_sources,
        )
        if report["sources"] is None:
            report["warnings"].append(
                "Per-source pages were not measured: the source inventory could not "
                "be read, so the shipped source-coverage shape is not in the "
                "comparison."
            )
        elif unmeasured_sources:
            report["warnings"].append(
                f"Per-source pages measured for {len(measured_sources)} source(s); "
                f"{len(unmeasured_sources)} not measured (cap {max(1, max_sources)}, "
                "or a value that is not a plain identifier)."
            )
        for name, statement in _statements(measured_sources):
            entry = _measure_statement(
                engine,
                name,
                statement,
                repeat=repeat,
                statement_timeout_ms=statement_timeout_ms,
            )
            if entry["errors"]:
                report["statements_failed"] += 1
            report["statements"].append(entry)
        report["comparison"] = _compare_shapes(
            report["statements"],
            page_bound=min(PER_SOURCE_LIMIT, QUOTE_LIMIT),
            sources_measured=measured_sources,
            sources_not_measured=unmeasured_sources,
        )
    except Exception as exc:
        report["warnings"].append(f"Measurement aborted: {exc.__class__.__name__}.")
        return report, 2
    finally:
        engine.dispose()
    return report, 0


def _measure_python(rates_count: int, rows_count: int) -> dict[str, Any]:
    """Measure the per-row Python costs on synthetic in-memory fixture records."""

    import types
    from datetime import UTC, datetime, timedelta

    from eurogas_nexus.application.projections.market_reads import market_observation_row
    from eurogas_nexus.domain.market_intelligence.normalized_view import (
        FxRateInput,
        MarketObservationInput,
        build_normalized_market_view,
        latest_fx_edges,
    )

    now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    rows = [
        types.SimpleNamespace(
            observation_id=f"fixture-{index:08d}",
            market_venue="EEX",
            product="NBP Day-Ahead",
            price=31.0,
            unit="EUR/MWh",
            currency="EUR",
            period_start_utc=now - timedelta(seconds=index),
            period_end_utc=now,
            observed_at_utc=now - timedelta(seconds=index),
            source_system="EEX_Sim",
            source_reference="fixture:measurement",
            source_record_id=f"fixture-{index}",
            freshness="live",
            quality_score=0.9,
            research_only=True,
            metadata_json={"hub": "NBP"},
        )
        for index in range(rows_count)
    ]
    rates = [
        FxRateInput(
            pair=f"EUR{index:03d}",
            base_currency="EUR",
            quote_currency="GBP",
            rate=0.85,
            observed_at_utc=now.isoformat(),
        )
        for index in range(rates_count)
    ]
    observations = [
        MarketObservationInput(
            market_venue="EEX",
            product="NBP Day-Ahead",
            price=31.0,
            currency="EUR",
            unit="EUR/MWh",
            observed_at_utc=now.isoformat(),
            period_start_utc=now.isoformat(),
            metadata_json={"hub": "NBP"},
        )
        for _ in range(rows_count)
    ]

    started = time.perf_counter()
    for row in rows:
        market_observation_row(row)
    shaping_seconds = time.perf_counter() - started

    started = time.perf_counter()
    latest_fx_edges(rates)
    one_graph_seconds = time.perf_counter() - started

    started = time.perf_counter()
    build_normalized_market_view(observations, rates)
    shared_graph_seconds = time.perf_counter() - started

    return {
        "rows": rows_count,
        "rates": rates_count,
        "observation_shaping_seconds": round(shaping_seconds, 4),
        "observation_shaping_rows_per_second": round(rows_count / max(shaping_seconds, 1e-9)),
        "one_latest_fx_graph_seconds": round(one_graph_seconds, 6),
        "normalized_view_shared_graph_seconds": round(shared_graph_seconds, 4),
        "normalized_view_per_row_graph_seconds_estimate": round(
            one_graph_seconds * rows_count, 4
        ),
    }


def _print_human(report: dict[str, Any]) -> None:
    """Print one report for a human reader."""

    if report["mode"] == "python-only":
        fixture = report["python_fixture"]
        print("Eurogas Nexus market-context latency triage (in-memory fixtures, no database)")
        print(f"Rows shaped: {fixture['rows']}, FX rates: {fixture['rates']}")
        print(
            "Observation shaping: "
            f"{fixture['observation_shaping_seconds']}s "
            f"({fixture['observation_shaping_rows_per_second']} rows/s)"
        )
        print(f"One latest-rate graph: {fixture['one_latest_fx_graph_seconds']}s")
        print(
            "Normalized view, one shared graph: "
            f"{fixture['normalized_view_shared_graph_seconds']}s"
        )
        print(
            "Normalized view, per-row graph rebuild (pre-repair shape): "
            f"~{fixture['normalized_view_per_row_graph_seconds_estimate']}s"
        )
        return

    print("Eurogas Nexus market-context latency triage (read-only, runtime PostgreSQL)")
    presence = "configured" if report["database_url_present"] else "not configured"
    print(f"Runtime database: {presence}")
    print(
        f"statement_timeout: {report['statement_timeout_ms']} ms, "
        f"driver socket timeout: {report['driver_timeout_seconds']} s, "
        f"repeat: {report['repeat']}"
    )
    print("\nTables (estimated rows):")
    if report["tables"] is None:
        print("  not measured (see warnings)")
    else:
        for table in report["tables"]:
            print(f"  {table['table_name']}: {table['estimated_rows']}")
    print("\nIndexes:")
    if report["indexes"] is None:
        print("  not measured (see warnings)")
    else:
        for index in report["indexes"]:
            print(f"  {index['index_name']}: {index['definition']}")
    print("\nmarket_observations per source (rows / gas rows / newest):")
    if report["sources"] is None:
        print("  not measured (see warnings)")
    else:
        for source in report["sources"]:
            print(
                f"  {source['source_system']}: {source['row_count']} rows, "
                f"{source['gas_row_count']} gas rows, "
                f"newest {source['newest_observed_at_utc']}"
            )
    print("\nStatements:")
    for entry in report["statements"]:
        run = entry.get("last_run")
        if run is not None:
            scans = ", ".join(
                f"{node['type']}"
                + (f"({node['relation']})" if node["relation"] else "")
                + f"={node['actual_rows']}r/{node['actual_ms']}ms"
                for node in run["scan_nodes"]
            )
            print(
                f"  {entry['name']}: {entry['execution_ms_min']} ms (min), "
                f"{entry['execution_ms_median']} ms (median), {run['actual_rows']} rows, "
                f"plan {run['planning_ms']} ms, "
                f"buffers hit={run['shared_hit_blocks']} read={run['shared_read_blocks']}"
            )
            if scans:
                print(f"      {scans}")
        for failure in entry["errors"]:
            print(f"  {entry['name']}: ERROR {failure}")
    print(
        f"\nStatements measured: {len(report['statements'])}, "
        f"failed: {report['statements_failed']}"
    )
    comparison = report.get("comparison")
    print("\nSource-coverage shapes (measured SQL plan time only):")
    if not comparison:
        print("  not compared (the measurement did not complete)")
    else:
        superseded = comparison["superseded_shape"]["execution_ms"]
        per_source = comparison["per_source_shape"]["execution_ms"]
        print(
            "  superseded (count + ranking window): "
            + (f"{superseded} ms" if superseded is not None else "not measured")
        )
        print(
            "  shipped (one bounded page per source): "
            + (
                f"{per_source} ms over "
                f"{comparison['per_source_shape']['statement_count']} statement(s), "
                f"page bound {comparison['per_source_shape']['page_bound']} rows"
                if per_source is not None
                else "not measured"
            )
        )
        measured = comparison["per_source_shape"]["sources_measured"]
        skipped = comparison["per_source_shape"]["sources_not_measured"]
        print(f"  sources measured: {len(measured)}, not measured: {len(skipped)}")
        ratio = comparison["ratio_superseded_over_per_source"]
        print(f"  ratio superseded / shipped: {ratio if ratio is not None else 'not measured'}")
        for note in comparison["notes"]:
            print(f"  note: {note}")
    for warning in report["warnings"]:
        print(f"Warning: {warning}")


def main(argv: list[str] | None = None) -> int:
    """Run the read-only measurement this harness documents."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-only",
        action="store_true",
        help="Measure the in-memory per-row Python costs without touching any database.",
    )
    parser.add_argument(
        "--repeat", type=int, default=1, help="EXPLAIN ANALYZE runs per statement (min/median)."
    )
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        default=60000,
        help=(
            "Per-statement server abort, so a slow plan cannot hang the operator "
            f"({MIN_STATEMENT_TIMEOUT_MS}..{MAX_STATEMENT_TIMEOUT_MS} ms)."
        ),
    )
    parser.add_argument("--rows", type=int, default=20000, help="Fixture rows for --python-only.")
    parser.add_argument(
        "--rates", type=int, default=20000, help="Fixture FX rates for --python-only."
    )
    parser.add_argument(
        "--max-sources",
        type=int,
        default=DEFAULT_MAX_SOURCES,
        help=(
            "Sources whose per-source page statement is measured, largest first. The "
            "shipped read issues one statement per source, so this bounds the "
            f"harness's own runtime (default {DEFAULT_MAX_SOURCES})."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    if args.python_only:
        report: dict[str, Any] = {
            "mode": "python-only",
            "python_fixture": _measure_python(max(1, args.rates), max(1, args.rows)),
            "warnings": [
                "Fixture records in memory only; no database was opened and no price "
                "was written anywhere.",
            ],
        }
        exit_code = 0
    else:
        report, exit_code = _measure_db(
            max(1, args.repeat),
            args.statement_timeout_ms,
            max_sources=max(1, args.max_sources),
        )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
