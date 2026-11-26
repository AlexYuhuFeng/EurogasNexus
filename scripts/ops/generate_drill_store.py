"""Fill a scratch drill database to a realistic size with synthetic observations and quotes.

For recovery drills only (``scripts/ops/ha_drill.py``): a restore time measured on a few hundred
kilobytes says nothing about a store of tens of gigabytes. Every generated row is marked as
synthetic (``source_system`` ``DRILL-SYNTHETIC``, quotes ``simulated``, observations
``research_only``, ``metadata_json.drill``), so none can be read as a market price (AGENTS.md
rule 17), and the script refuses any database whose name does not start with ``drill``.

    python scripts/ops/generate_drill_store.py --database-url postgresql+pg8000://.../drill_nexus \\
        --target-gb 5 --min-free-gb 1.5

It stops when the database reaches the target size, or with an error before free disk space
on ``--free-space-path`` falls below ``--min-free-gb`` (the drill must never fill a shared disk).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _path in (_ROOT / "src", _ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

GIB = 1024**3
DRILL_TABLES = ("market_observations", "market_quotes", "audit_events")

_OBSERVATIONS = """
INSERT INTO market_observations (
    observation_id, market_venue, product, price, unit, currency, period_start_utc,
    period_end_utc, observed_at_utc, source_system, source_reference, source_record_id,
    freshness, quality_score, research_only, metadata_json)
SELECT
    'drill-o-' || CAST(:batch AS integer) || '-' || g,
    (ARRAY['EEX', 'ICE-ENDEX', 'PEGAS', 'HEREN'])[1 + mod(g, 4)],
    (ARRAY['TTF-DA', 'TTF-M1', 'TTF-Q1', 'THE-DA', 'THE-M1', 'NBP-M1', 'PEG-DA'])[1 + mod(g, 7)],
    round((18 + mod(g, 5000) / 125.0 + random())::numeric, 3),
    'EUR/MWh', 'EUR', ts, ts + interval '1 day', ts,
    'DRILL-SYNTHETIC', 'drill-generator', 'rec-' || CAST(:batch AS integer) || '-' || g,
    'settled', 1.0, true,
    json_build_object(
        'drill', true, 'note', 'synthetic drill row, not a market price',
        'hub', (ARRAY['TTF', 'THE', 'NBP', 'PEG'])[1 + mod(g, 4)],
        'tenor', (ARRAY['DA', 'M1', 'Q1'])[1 + mod(g, 3)],
        'batch', CAST(:batch AS integer))
FROM generate_series(1, CAST(:rows AS integer)) AS g,
     LATERAL (SELECT timestamptz '2021-01-01' + g * interval '41 seconds'
                     + CAST(:batch AS integer) * interval '3 hours') AS t(ts)
"""

_QUOTES = """
INSERT INTO market_quotes (
    quote_id, source_system, source_record_id, venue, instrument_id, hub, product,
    delivery_start_utc, delivery_end_utc, bid_price, ask_price, last_price, bid_quantity_mwh,
    ask_quantity_mwh, currency, unit, observed_at_utc, received_at_utc, source_reference,
    freshness, quality_score, simulated, metadata_json)
SELECT
    'drill-q-' || CAST(:batch AS integer) || '-' || g, 'DRILL-SYNTHETIC', 'seq-' || g, 'DRILL',
    'DRILL-' || (ARRAY['TTF', 'THE', 'NBP', 'PEG'])[1 + mod(g, 4)] || '-' || mod(g, 12),
    (ARRAY['TTF', 'THE', 'NBP', 'PEG'])[1 + mod(g, 4)],
    (ARRAY['DA', 'WD', 'M1', 'Q1'])[1 + mod(g, 4)],
    date_trunc('day', ts) + interval '1 day', date_trunc('day', ts) + interval '2 days',
    p, p + 0.05 + random() / 10, p + 0.02, 10 + mod(g, 90), 10 + mod(g, 70), 'EUR', 'EUR/MWh',
    ts, ts + interval '150 milliseconds', 'drill-generator', 'live', 1.0, true,
    json_build_object('drill', true, 'note', 'synthetic drill tick, not a market price',
                      'batch', CAST(:batch AS integer))
FROM generate_series(1, CAST(:rows AS integer)) AS g,
     LATERAL (SELECT timestamptz '2025-01-01' + g * interval '997 milliseconds'
                     + CAST(:batch AS integer) * interval '2 hours',
                     round((18 + mod(g, 3000) / 90.0 + random())::numeric, 3)) AS t(ts, p)
"""


def require_drill_database(engine) -> None:
    name = engine.url.database or ""
    if not name.startswith("drill"):
        raise SystemExit(
            f"refused: database {name!r} is not a drill database (its name must start with "
            "'drill'); this script only fills scratch stores"
        )


def available_memory_bytes() -> int | None:
    """MemAvailable on Linux (a drill may keep its volumes in memory), else ``None``."""

    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def database_bytes(connection) -> int:
    from sqlalchemy import text

    return int(connection.execute(text("SELECT pg_database_size(current_database())")).scalar())


def generate(
    engine,
    *,
    target_bytes: int,
    rows_per_batch: int = 250_000,
    min_free_bytes: int = int(1.5 * GIB),
    free_space_path: str = "/",
    first_batch: int | None = None,
    emit=print,
) -> dict:
    """Insert batches until ``pg_database_size`` reaches ``target_bytes``."""

    from sqlalchemy import text

    started = time.perf_counter()
    with engine.connect() as connection:
        size = database_bytes(connection)
        if first_batch is None:
            # A rerun on a filled store continues after the batches already there.
            first_batch = 1 + int(
                connection.execute(
                    text(
                        "SELECT coalesce(max((metadata_json->>'batch')::int), 0) "
                        "FROM market_observations WHERE source_system = 'DRILL-SYNTHETIC'"
                    )
                ).scalar()
            )
    batch = first_batch
    while size < target_bytes:
        free = shutil.disk_usage(free_space_path).free
        if free < min_free_bytes:
            raise RuntimeError(
                f"stopped: {free / GIB:.2f} GiB free on {free_space_path} is below the "
                f"{min_free_bytes / GIB:.2f} GiB margin (database at {size / GIB:.2f} GiB)"
            )
        memory = available_memory_bytes()
        if memory is not None and memory < min_free_bytes:
            raise RuntimeError(
                f"stopped: {memory / GIB:.2f} GiB of memory available is below the "
                f"{min_free_bytes / GIB:.2f} GiB margin (database at {size / GIB:.2f} GiB)"
            )
        with engine.begin() as connection:
            connection.execute(text(_OBSERVATIONS), {"batch": batch, "rows": rows_per_batch})
            connection.execute(text(_QUOTES), {"batch": batch, "rows": rows_per_batch})
        with engine.connect() as connection:
            size = database_bytes(connection)
        emit(json.dumps({"event": "drill.load.batch", "batch": batch,
                         "database_gib": round(size / GIB, 3),
                         "free_disk_gib": round(free / GIB, 2),
                         "elapsed_seconds": round(time.perf_counter() - started, 1)}))
        batch += 1
    return {
        "database_bytes": size,
        "batches": batch - first_batch,
        "next_batch": batch,
        "load_seconds": round(time.perf_counter() - started, 1),
    }


def write_marked_batch(engine, *, label: str, rows: int, batch: int) -> None:
    """A small batch whose rows are recognisable by ``label`` (before/after the target time)."""

    from sqlalchemy import text

    with engine.begin() as connection:
        connection.execute(text(_OBSERVATIONS.replace("'drill-o-'", f"'drill-{label}-o-'")),
                           {"batch": batch, "rows": rows})
        connection.execute(text(_QUOTES.replace("'drill-q-'", f"'drill-{label}-q-'")),
                           {"batch": batch, "rows": rows})
        connection.execute(
            text(
                "INSERT INTO audit_events (event_id, event_type, severity, principal, action,"
                " resource, outcome, detail, event_ts_utc, source_system,"
                " human_review_required) SELECT 'drill-' || :label || '-'"
                " || CAST(:batch AS integer)"
                " || '-' || g, 'drill', 'info',"
                " 'drill', 'drill.write', 'drill', 'recorded', '', clock_timestamp(), 'drill',"
                " false FROM generate_series(1, 50) g"
            ),
            {"label": label, "batch": batch},
        )


def fingerprint(engine, tables=DRILL_TABLES) -> dict:
    """Row count and an order-independent checksum per table (sum of 60-bit row digests)."""

    from sqlalchemy import text

    result = {}
    with engine.connect() as connection:
        for table in tables:
            count, checksum = connection.execute(
                text(
                    f"SELECT count(*), coalesce(sum(('x' || substr(md5(t::text), 1, 15))"
                    f"::bit(60)::bigint::numeric), 0) FROM {table} AS t"
                )
            ).one()
            result[table] = {"rows": int(count), "checksum": str(checksum)}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--target-gb", type=float, required=True)
    parser.add_argument("--min-free-gb", type=float, default=1.5)
    parser.add_argument("--free-space-path", default="/")
    parser.add_argument("--rows-per-batch", type=int, default=250_000)
    args = parser.parse_args(argv)

    from eurogas_nexus.db.session import get_engine

    # A command engine: the connect bound only, no statement or socket read limit (db/session.py).
    engine = get_engine(args.database_url, statement_timeout=None)
    try:
        require_drill_database(engine)
        result = generate(
            engine,
            target_bytes=int(args.target_gb * GIB),
            rows_per_batch=args.rows_per_batch,
            min_free_bytes=int(args.min_free_gb * GIB),
            free_space_path=args.free_space_path,
        )
    finally:
        engine.dispose()
    print(json.dumps({"status": "ok", **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
