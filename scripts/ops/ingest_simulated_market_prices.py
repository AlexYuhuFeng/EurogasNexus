"""Inject simulated exchange, broker-screen, and assessment rows into PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from eurogas_nexus.db.session import (
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.ingestion.simulated_market_prices import (
    DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS,
    run_simulated_market_price_loop,
    upsert_simulated_market_observations,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2

    print(f"Runtime DB: {redact_database_url(database_url)}")
    session_factory = get_session_factory(database_url=database_url)
    if args.loop:
        intervals_seconds = {
            "EEX_Sim": args.eex_interval_seconds,
            "ICE_OCM_Sim": args.ice_ocm_interval_seconds,
            "Trayport_Sim": args.trayport_interval_seconds,
            "ICIS_Sim": args.icis_interval_seconds,
        }
        print(
            "Starting simulated market price worker: "
            f"intervals_seconds={intervals_seconds}"
        )
        try:
            run_simulated_market_price_loop(
                session_factory,
                intervals_seconds=intervals_seconds,
                max_iterations=args.max_iterations,
                emit=print,
            )
        except KeyboardInterrupt:
            print("Stopped simulated market price worker.")
        return 0

    observed_at = datetime.now(UTC)
    with session_factory() as session:
        summary = upsert_simulated_market_observations(
            session,
            observed_at_utc=observed_at,
        )
        session.commit()

    print(
        "Injected simulated market prices: "
        f"{summary['rows_upserted']} rows at {summary['observed_at_utc']} "
        f"from {summary['source_counts']}"
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inject simulated EEX, ICE OCM, and ICIS market prices."
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously and inject each simulated source at its configured cadence.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Stop after this many due-source ticks; useful for validation.",
    )
    parser.add_argument(
        "--eex-interval-seconds",
        type=float,
        default=DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS["EEX_Sim"],
        help="Simulated EEX tick cadence in seconds.",
    )
    parser.add_argument(
        "--ice-ocm-interval-seconds",
        type=float,
        default=DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS["ICE_OCM_Sim"],
        help="Simulated ICE OCM tick cadence in seconds.",
    )
    parser.add_argument(
        "--trayport-interval-seconds",
        type=float,
        default=DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS["Trayport_Sim"],
        help="Simulated Trayport broker-screen tick cadence in seconds.",
    )
    parser.add_argument(
        "--icis-interval-seconds",
        type=float,
        default=DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS["ICIS_Sim"],
        help="Simulated ICIS daily-assessment cadence in seconds.",
    )
    args = parser.parse_args(argv)
    if args.max_iterations is not None and args.max_iterations <= 0:
        parser.error("--max-iterations must be positive when provided.")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
