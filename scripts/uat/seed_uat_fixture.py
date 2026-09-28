#!/usr/bin/env python
"""Deterministic UAT fixture pack for CR-13 (development/test only).

The fixture is clearly simulated and never activates in trial/release:
``EUROGAS_NEXUS_ENV`` must be development/test and
``EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1`` must be set. It seeds 60 days of
source-shaped simulated market observations so backtest/shadow workflows have
deterministic historical evidence, plus the paired NBP/TTF day-ahead samples the
governed research run reads. ``--agent-window-only`` re-stamps just those samples
in the UTC day it is run in and reports that day, which is how the browser
harness coordinates them with the run's own clock read (see
``refresh_agent_window``); it never writes real licensed vendor data.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eurogas_nexus.db.models import (  # noqa: E402
    CanonicalEntityRecord,
    FxObservationRecord,
    MarketObservationRecord,
    NominationWindowMasterRecord,
    SeriesDefinitionRecord,
)
from eurogas_nexus.db.session import (  # noqa: E402
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.ingestion.simulated_market_prices import (  # noqa: E402
    SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS,
    generate_simulated_market_observations,
)

FIXTURE_DAYS = 60
AGENT_SAMPLE_HUBS = (("NBP", 33.0), ("TTF", 31.0))
AGENT_WINDOW_FLAG = "--agent-window-only"
#: ``analytics.spread_distribution`` refuses fewer than two values a side and the orchestrator
#: files a spread finding only from ``n >= 2`` paired timestamps, so a refreshed window has to
#: hold at least this many - inside the run's own UTC day and at or before the clock that stamps
#: them.
AGENT_WINDOW_MIN_PAIRED_TIMESTAMPS = 2
#: First attempt plus the attempts a UTC midnight crossed *during* the write needs to stamp the
#: day that begins. Bounded on purpose: a day that cannot hold the samples honestly is reported,
#: never covered with a future-dated row.
AGENT_WINDOW_MAX_ATTEMPTS = 3


def agent_dayahead_observation_rows(now: datetime) -> list[dict[str, Any]]:
    """Return the paired NBP/TTF day-ahead samples for the UTC day ``now`` belongs to.

    The governed research orchestrator deliberately reads market observations from the start of its
    *current UTC day* (``market_rows(start_utc=...replace(hour=0, ...))``) and files a spread
    finding only from paired NBP/TTF timestamps inside that window; both are production semantics
    this fixture serves rather than changes. CI36360322601 (seeded 2026-09-27T23:56:30Z, run filed
    2026-09-28T00:01:04Z) blocked with ``INSUFFICIENT_HISTORY`` because the samples were stamped in
    the *seed* day only: five minutes later the window the run read was the day that began at
    midnight, and it held no paired history. Every sample is therefore stamped inside ``now``'s own
    UTC day and **at or before ``now``** - never after the clock that writes it - and
    ``refresh_agent_window`` re-stamps the same ids into the day the run will read immediately
    before it files. The role of each set, not a date, is in the row ids, so re-stamping moves the
    rows instead of accumulating a set per day. Simulated development/test rows only: ``main``
    refuses to seed in trial/release.
    """

    day_start = _day_start(now)
    available_microseconds = max(int((now - day_start).total_seconds() * 1_000_000), 6)
    rows: list[dict[str, Any]] = []
    for sample in range(5):
        observed = now - timedelta(microseconds=available_microseconds * (sample + 1) // 8)
        for hub, base_value in AGENT_SAMPLE_HUBS:
            rows.append(
                {
                    "observation_id": f"uat-agent-{hub.lower()}-{sample}",
                    "market_venue": hub,
                    "product": "DAY_AHEAD",
                    "price": base_value + sample * 0.1,
                    "unit": "EUR/MWh",
                    "currency": "EUR",
                    "period_start_utc": observed,
                    "period_end_utc": observed + timedelta(hours=1),
                    "observed_at_utc": observed,
                    "source_system": "EEX_Sim",
                    "source_reference": f"uat-sim:agent:{hub}:{sample}",
                    "source_record_id": None,
                    "freshness": "simulated_live",
                    "quality_score": 0.8,
                    "research_only": True,
                    "metadata_json": {
                        "hub": hub,
                        "tenor": "day-ahead",
                        "simulated": True,
                        "fixture": "browser-uat",
                    },
                }
            )
    return rows


@dataclass(frozen=True)
class AgentWindowRefresh:
    """One agent-window refresh that landed: the day it stamped, its clock read, and the rows."""

    day_start_utc: datetime
    stamped_at_utc: datetime
    rows: tuple[dict[str, Any], ...]

    @property
    def latest_observed_utc(self) -> datetime:
        return max(row["observed_at_utc"] for row in self.rows)


def refresh_agent_window(
    *,
    clock: Callable[[], datetime],
    write: Callable[[list[dict[str, Any]]], None],
    attempts: int = AGENT_WINDOW_MAX_ATTEMPTS,
    minimum_paired_timestamps: int = AGENT_WINDOW_MIN_PAIRED_TIMESTAMPS,
) -> AgentWindowRefresh | None:
    """Stamp the agent-window samples into the UTC day a run's own clock read will cover.

    Returns the refresh that landed, or ``None`` when the current UTC day could not hold it within
    the bounded attempts - the case the caller *reports* instead of covering: a run whose window
    this fixture cannot fill honestly must block with the product's own ``INSUFFICIENT_HISTORY``
    rather than be handed samples dated in its future. Nothing is stamped after the clock read that
    writes it, and a write that crosses UTC midnight is re-stamped for the day that begins (the
    rows written for the day that just ended stay valid day-D rows; they are simply not the set the
    run will read).
    """

    for _ in range(max(1, attempts)):
        now = clock()
        day_start = _day_start(now)
        rows = [
            row
            for row in agent_dayahead_observation_rows(now)
            if day_start <= row["observed_at_utc"] <= now
        ]
        if _paired_timestamps(rows) < minimum_paired_timestamps:
            # The UTC day has not elapsed far enough to hold the pairs (its first moments cannot):
            # read the clock again rather than stamp a timestamp the run's history has not reached.
            continue
        write(rows)
        if _day_start(clock()) != day_start:
            # UTC midnight passed while the samples were written: they belong to the day that just
            # ended, so stamp again for the day the run's own clock read will cover.
            continue
        return AgentWindowRefresh(day_start_utc=day_start, stamped_at_utc=now, rows=tuple(rows))
    return None


def _day_start(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _paired_timestamps(rows: Iterable[dict[str, Any]]) -> int:
    """Count the instants carrying both hubs, the way the orchestrator's spread analysis pairs."""

    hubs: dict[datetime, set[str]] = {}
    for row in rows:
        hubs.setdefault(row["observed_at_utc"], set()).add(str(row["metadata_json"]["hub"]))
    return sum(1 for names in hubs.values() if {"NBP", "TTF"} <= names)


def _refresh_agent_window_command(session_factory, database_url: str) -> int:
    """``--agent-window-only``: re-stamp the agent-window samples and report the day they landed in.

    The browser harness runs this through its own fixture process immediately before it files the
    governed research run, parses the reported ``day_start`` and re-runs the command (bounded) if
    its UTC day has moved on - never through a product write endpoint. A refusal is a reported
    block, not a failure covered by future-dated rows.
    """

    def write(rows: list[dict[str, Any]]) -> None:
        with session_factory() as session:
            for row in rows:
                session.merge(MarketObservationRecord(**row))
            session.commit()

    print(f"Runtime DB: {redact_database_url(database_url)}")
    refresh = refresh_agent_window(clock=lambda: datetime.now(UTC), write=write)
    if refresh is None:
        print(
            "Agent-window refresh refused: the current UTC day could not hold "
            f"{AGENT_WINDOW_MIN_PAIRED_TIMESTAMPS} paired NBP/TTF samples at or before the clock "
            f"that stamps them within {AGENT_WINDOW_MAX_ATTEMPTS} attempts (UTC midnight rollover, "
            "or a day that has only just begun). No sample was dated after the clock; a research "
            "run reading this day reports INSUFFICIENT_HISTORY instead of receiving future data.",
            file=sys.stderr,
        )
        return 3
    print(
        "UAT agent window ready:"
        f" day_start={refresh.day_start_utc.isoformat()}"
        f" stamped_at={refresh.stamped_at_utc.isoformat()}"
        f" latest_observed={refresh.latest_observed_utc.isoformat()}"
        f" rows={len(refresh.rows)}"
    )
    return 0


def main() -> int:
    arguments = list(sys.argv[1:])
    unknown = sorted({argument for argument in arguments if argument != AGENT_WINDOW_FLAG})
    if unknown:
        print(f"Unknown argument(s): {', '.join(unknown)}. Supported: {AGENT_WINDOW_FLAG}")
        return 2
    agent_window_only = AGENT_WINDOW_FLAG in arguments

    environment = os.getenv("EUROGAS_NEXUS_ENV", "development").strip().lower()
    if environment in {"trial", "release"}:
        print("UAT fixtures are blocked in trial/release environments.")
        return 2
    if os.getenv("EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED", "").strip() != "1":
        print("Set EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1 to acknowledge simulated UAT data.")
        return 2
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2

    session_factory = get_session_factory(database_url=database_url)
    if agent_window_only:
        return _refresh_agent_window_command(session_factory, database_url)

    print(f"Runtime DB: {redact_database_url(database_url)}")
    now = datetime.now(UTC).replace(microsecond=0)
    inserted = 0
    with session_factory() as session:
        for days_ago in range(FIXTURE_DAYS - 1, -1, -1):
            observed_at = (now - timedelta(days=days_ago)).replace(hour=4, minute=0, second=0)
            rows = generate_simulated_market_observations(
                observed_at_utc=observed_at,
                source_systems=SIMULATED_MARKET_PRICE_SOURCE_SYSTEMS,
            )
            for row in rows:
                session.merge(MarketObservationRecord(**row))
                inserted += 1
            # SAP-style NBP day-ahead series required by the default
            # OCM_VS_DAY_AHEAD strategy component. Clearly synthetic test data.
            session.merge(
                FxObservationRecord(
                    observation_id=f"uat-fx-eurgbp-{observed_at:%Y%m%d}",
                    pair="EURGBP",
                    base_currency="EUR",
                    quote_currency="GBP",
                    rate=0.86,
                    rate_type="reference",
                    value_date=observed_at.strftime("%Y-%m-%d"),
                    observed_at_utc=observed_at,
                    source_system="ECB_UAT_Sim",
                    source_reference=f"uat-sim:ecb:{observed_at:%Y-%m-%d}",
                    source_record_id=None,
                    freshness="simulated_live",
                    research_only=True,
                    metadata_json={"simulated": True},
                )
            )
            session.merge(
                MarketObservationRecord(
                    observation_id=(f"uat-sap-sim-nbp-dayahead-{observed_at:%Y%m%dT%H%M%S}"),
                    market_venue="SAP_Sim",
                    product="NBP day-ahead",
                    price=33.2,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=observed_at,
                    period_end_utc=observed_at + timedelta(days=1),
                    observed_at_utc=observed_at,
                    source_system="SAP_Sim",
                    source_reference=f"uat-sim:sap:{observed_at:%Y-%m-%d}",
                    source_record_id=None,
                    freshness="simulated_live",
                    quality_score=0.6,
                    research_only=True,
                    metadata_json={
                        "hub": "NBP",
                        "tenor": "day-ahead",
                        "price_name": "SAP",
                        "simulated": True,
                    },
                )
            )
            inserted += 1

        # CR-15 deterministic research semantics. These are schema/identity
        # fixtures only; no licensed vendor data is introduced.
        for code in ("NBP", "TTF"):
            session.merge(
                CanonicalEntityRecord(
                    canonical_entity_id=f"ent:market_hub:{code}",
                    entity_type="market_hub",
                    canonical_code=code,
                    display_name=f"{code} UAT hub",
                    description="Deterministic UAT canonical hub.",
                    metadata_json={"simulated": True, "fixture": "browser-uat"},
                    created_at_utc=now,
                )
            )

        series = (
            SeriesDefinitionRecord(
                series_id="market.price.NBP.DAY_AHEAD",
                name="NBP Day-Ahead UAT",
                metric_type="price",
                entity_type="market_hub",
                entity_id="ent:market_hub:NBP",
                product_id="DAY_AHEAD",
                direction=None,
                source_class="EEX_Sim",
                native_frequency="1h",
                native_unit="EUR/MWh",
                currency="EUR",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                created_at_utc=now,
            ),
            SeriesDefinitionRecord(
                series_id="market.price.TTF.DAY_AHEAD",
                name="TTF Day-Ahead UAT",
                metric_type="price",
                entity_type="market_hub",
                entity_id="ent:market_hub:TTF",
                product_id="DAY_AHEAD",
                direction=None,
                source_class="EEX_Sim",
                native_frequency="1h",
                native_unit="EUR/MWh",
                currency="EUR",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                created_at_utc=now,
            ),
            SeriesDefinitionRecord(
                series_id="market.fx.EUR.GBP",
                name="EUR/GBP UAT",
                metric_type="fx",
                entity_type="currency_pair",
                entity_id="EURGBP",
                product_id=None,
                direction=None,
                source_class="ECB_UAT_Sim",
                native_frequency="1d",
                native_unit="GBP/EUR",
                currency="GBP",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                created_at_utc=now,
            ),
        )
        for item in series:
            session.merge(item)

        # The governed research run reads the current UTC day; `--agent-window-only` re-stamps
        # these samples in that day immediately before the run (the browser harness runs it), and
        # `agent_dayahead_observation_rows` states the day/window contract they satisfy.
        for row in agent_dayahead_observation_rows(now):
            session.merge(MarketObservationRecord(**row))
            inserted += 1

        # The desk's clock. `nomination_window_masters` is a deployment declaration, so without one
        # the browser UAT can only exercise the *absence* of a window: the nomination task reports
        # `NOMINATION_WINDOWS_MISSING` and the day board has no deadline to show. These two are
        # simulated declarations on the UTC clock the engine matches against, chosen inside the gas
        # day all year (its boundary is 04:00-05:00 UTC), so a deadline exists whatever the run's
        # wall-clock time. 06:00 UTC is the winter boundary's own hour - the moment a gas day starts
        # in the CAM calendar - and 12:00 UTC sits in the middle of the day.
        for window_id, name, opens_at, closes_at, maximum_change_mwh, maximum_change_pct in (
            (
                "uat-window-day-open",
                "UAT simulated window at the gas-day open",
                time(6, 0),
                time(6, 30),
                150.0,
                None,
            ),
            (
                "uat-window-midday",
                "UAT simulated midday renomination window",
                time(12, 0),
                time(12, 30),
                None,
                10.0,
            ),
        ):
            session.merge(
                NominationWindowMasterRecord(
                    window_id=window_id,
                    name=name,
                    country="DE",
                    opens_at=opens_at,
                    closes_at=closes_at,
                    maximum_change_mwh=maximum_change_mwh,
                    maximum_change_pct=maximum_change_pct,
                    valid_from_utc=datetime(2020, 1, 1, tzinfo=UTC),
                    valid_to_utc=None,
                    source_system="CAM_UAT_Sim",
                    source_reference=f"uat-sim:cam:{window_id}",
                    active=True,
                    created_at_utc=now,
                )
            )

        session.commit()
    print(
        f"Seeded {inserted} simulated UAT market observations across "
        f"{FIXTURE_DAYS} days (source systems marked *_Sim)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
