"""Fixture/window contract for the browser UAT's governed research run.

CI36360322601 (commit `2d42cc1`, seeded 2026-09-27T23:56:30Z, run filed 2026-09-28T00:01:04Z) failed
only `interaction/agent-research-review`: the run blocked with `INSUFFICIENT_HISTORY`. The
orchestrator deliberately reads market observations from the start of the *current UTC day*
(``market_rows(start_utc=...replace(hour=0, ...))``) - a production semantic this fixture must
serve, not change - and the fixture had written its paired NBP/TTF day-ahead samples inside the
seed day only. Five minutes later the window the run read was the day that began at midnight, so it
held no paired history and the run correctly refused to fabricate findings.

The coordination is the fixture refresh the browser harness runs immediately before the governed
research interaction (``scripts/uat/seed_uat_fixture.py --agent-window-only``, through the harness's
own fixture process, never a product write endpoint): it re-stamps the same samples inside the UTC
day the run's own clock read will cover, and every sample is at or before the clock that writes it -
never dated into a day the run's history has not reached. Where the current UTC day cannot hold the
samples honestly (the rollover cases below) the refresh reports that instead. This module holds the
fixture to that contract, reproduces the CI block end to end through the real orchestrator, and
proves every accepted sample is at or before the research run's own as-of instant.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.agents import research_orchestrator
from eurogas_nexus.application.agents.research_orchestrator import (
    GovernedResearchOrchestrator,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CanonicalEntityRecord,
    MarketObservationRecord,
    SeriesDefinitionRecord,
)
from eurogas_nexus.domain.agents.contracts import AgentInvocationContext

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "uat" / "browser_workflow_smoke.mjs"
SEED_SCRIPT = ROOT / "scripts" / "uat" / "seed_uat_fixture.py"


def _load_seed_module() -> Any:
    spec = importlib.util.spec_from_file_location("seed_uat_fixture", SEED_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: the fixture declares a dataclass, and `dataclasses` resolves the
    # annotated names through `sys.modules[cls.__module__]` (Python 3.14 refuses a module that was
    # never registered, which is exactly what importing by path alone leaves behind).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


FIXTURE = _load_seed_module()

#: The CI36360322601 pair: seeded 23:56:30Z, and the harness's refresh lands ~1s before the run.
CI_SEEDED_AT = datetime(2026, 9, 27, 23, 56, 30, tzinfo=UTC)
CI_REFRESH_AT = datetime(2026, 9, 28, 0, 1, 3, tzinfo=UTC)
CI_RUN_AT = datetime(2026, 9, 28, 0, 1, 4, tzinfo=UTC)
CI_OBJECTIVE = (
    "Assess whether the seeded NBP-TTF day-ahead spread is persistent enough for governed UAT "
    "research."
)


def _day_start(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _utc(value: datetime) -> datetime:
    """SQLite drops tzinfo; the fixture only ever writes UTC, so read it back as UTC."""

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _paired_timestamps(
    rows: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime | None = None,
) -> dict[datetime, set[str]]:
    """Pair the fixture rows the way the orchestrator's spread analysis pairs them.

    The orchestrator reads the current UTC day with no upper bound and pairs observations that
    share an ``observed_at`` timestamp across hubs.
    """

    buckets: dict[datetime, set[str]] = {}
    for row in rows:
        observed = row["observed_at_utc"]
        if observed < window_start:
            continue
        if window_end is not None and observed >= window_end:
            continue
        buckets.setdefault(observed, set()).add(str(row["metadata_json"]["hub"]))
    return {stamp: hubs for stamp, hubs in buckets.items() if {"NBP", "TTF"} <= hubs}


def _sqlite_url(tmp_path: Path, name: str) -> str:
    return f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}"


def _stored_rows(tmp_path: Path, name: str, rows: list[dict[str, Any]]) -> Session:
    """Persist fixture rows with the identity rows the plan validation needs."""

    engine = create_engine(_sqlite_url(tmp_path, name), future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    for code in ("NBP", "TTF"):
        session.add(
            CanonicalEntityRecord(
                canonical_entity_id=f"ent:market_hub:{code}",
                entity_type="market_hub",
                canonical_code=code,
                display_name=f"{code} UAT hub",
                description="Deterministic UAT canonical hub.",
                metadata_json={"simulated": True, "fixture": "browser-uat"},
                created_at_utc=CI_SEEDED_AT,
            )
        )
    for series_id in (
        "market.price.NBP.DAY_AHEAD",
        "market.price.TTF.DAY_AHEAD",
        "market.fx.EUR.GBP",
    ):
        session.add(
            SeriesDefinitionRecord(
                series_id=series_id,
                name=series_id,
                metric_type="price" if "price" in series_id else "fx",
                entity_type="market_hub",
                entity_id="ent:market_hub:NBP",
                source_class="EEX_Sim",
                native_frequency="1h",
                native_unit="EUR/MWh",
                temporal_type="OBSERVED",
                availability_semantics="available_at_required",
                created_at_utc=CI_SEEDED_AT,
            )
        )
    for row in rows:
        session.add(MarketObservationRecord(**row))
    session.commit()
    return session


def _freeze_orchestrator_clock(monkeypatch: pytest.MonkeyPatch, run_at: datetime) -> None:
    """Inject the run instant into the orchestrator's own clock read."""

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return run_at if tz is None else run_at.astimezone(tz)

    monkeypatch.setattr(research_orchestrator, "datetime", FrozenDatetime)


def _run_research(session: Session, run_id: str):
    return GovernedResearchOrchestrator().run_research(
        session,
        run_id=run_id,
        principal=AgentInvocationContext(
            principal_id="analyst-1",
            role="ANALYST",
            roles=["ANALYST"],
            data_scopes=["*"],
        ),
        objective=CI_OBJECTIVE,
        strategy_generation_allowed=True,
    )


def _refreshed(clock_values: list[datetime]) -> tuple[Any, list[list[dict[str, Any]]]]:
    """Run the fixture's own refresh with an isolated, explicit clock; collect what it wrote."""

    values = iter(clock_values)
    writes: list[list[dict[str, Any]]] = []
    refresh = FIXTURE.refresh_agent_window(
        clock=lambda: next(values, clock_values[-1]),
        write=writes.append,
    )
    return refresh, writes


@pytest.mark.parametrize(
    "instant",
    [
        CI_SEEDED_AT,  # minutes before midnight
        datetime(2026, 9, 28, 0, 0, 0, tzinfo=UTC),  # exactly on the boundary
        datetime(2026, 9, 28, 0, 0, 0, 1, tzinfo=UTC),  # a microsecond after it
        datetime(2026, 9, 28, 0, 0, 1, tzinfo=UTC),
        datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC),  # mid-day
        datetime(2026, 9, 28, 23, 59, 59, 999999, tzinfo=UTC),  # the last microsecond
        datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),  # year boundary
    ],
)
def test_no_sample_is_ever_stamped_after_the_clock_that_stamps_it(instant: datetime) -> None:
    """The fixture's samples are history, never future-dated data.

    The first attempt at this fix wrote a second sample set inside the UTC day that begins at
    midnight - rows dated after the clock that wrote them - and the reviewer rejected it as an
    acceptance workaround. The refresh instead re-stamps immediately before the run; nothing this
    fixture writes may be stamped after its own clock read.
    """

    rows = FIXTURE.agent_dayahead_observation_rows(instant)

    assert rows
    for row in rows:
        assert row["observed_at_utc"] <= instant


@pytest.mark.parametrize(
    "instant",
    [
        CI_REFRESH_AT,
        datetime(2026, 9, 28, 0, 0, 1, tzinfo=UTC),
        datetime(2026, 9, 28, 0, 1, 0, tzinfo=UTC),
        datetime(2026, 9, 28, 6, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 28, 23, 59, 59, tzinfo=UTC),
    ],
)
def test_every_sample_sits_inside_the_utc_day_that_stamps_it(instant: datetime) -> None:
    """A refresh after the day has begun lands wholly inside that day, in pairs.

    Samples outside the day the run reads are either stale (the previous day) or future-dated (the
    next one); a sample past a hub is a pair the orchestrator cannot form, because it pairs
    observations that share an instant.
    """

    rows = FIXTURE.agent_dayahead_observation_rows(instant)
    day_start = _day_start(instant)

    for row in rows:
        assert day_start <= row["observed_at_utc"] <= instant
    paired = _paired_timestamps(
        rows, window_start=day_start, window_end=day_start + timedelta(days=1)
    )
    assert len(paired) >= FIXTURE.AGENT_WINDOW_MIN_PAIRED_TIMESTAMPS


def test_the_refresh_stamps_the_ci_instants_into_the_window_the_ci_run_reads() -> None:
    """The CI pair: refresh at 00:01:03Z, run at 00:01:04Z, window from 00:00:00Z."""

    refresh, writes = _refreshed([CI_REFRESH_AT, CI_REFRESH_AT])

    assert refresh is not None
    assert writes == [list(refresh.rows)]
    assert refresh.day_start_utc == _day_start(CI_RUN_AT)
    for row in refresh.rows:
        assert refresh.day_start_utc <= row["observed_at_utc"] <= CI_REFRESH_AT <= CI_RUN_AT

    # Exactly the orchestrator's window for the CI run instant: start of the current UTC day, no
    # upper bound. Fewer than two paired timestamps is what made the run block.
    paired = _paired_timestamps(
        list(refresh.rows),
        window_start=_day_start(CI_RUN_AT),
        window_end=CI_RUN_AT + timedelta(microseconds=1),
    )
    assert len(paired) >= FIXTURE.AGENT_WINDOW_MIN_PAIRED_TIMESTAMPS


def test_the_samples_stay_labelled_simulated_and_research_only() -> None:
    refresh, _ = _refreshed([CI_REFRESH_AT, CI_REFRESH_AT])

    assert refresh is not None
    assert refresh.rows
    for row in refresh.rows:
        assert row["research_only"] is True
        assert row["source_system"].endswith("_Sim")
        assert row["metadata_json"]["simulated"] is True
        assert row["metadata_json"]["fixture"] == "browser-uat"


def _expected_job_start_rows(day: int) -> list[tuple[str, str, datetime, float, str]]:
    """The five paired samples as the job-start seed has always written them."""

    expected: list[tuple[str, str, datetime, float, str]] = []
    for sample, (hour, minute) in enumerate(((10, 30), (9, 0), (7, 30), (6, 0), (4, 30))):
        observed = datetime(2026, 9, day, hour, minute, tzinfo=UTC)
        for hub, base_value in (("NBP", 33.0), ("TTF", 31.0)):
            expected.append(
                (
                    f"uat-agent-{hub.lower()}-{sample}",
                    hub,
                    observed,
                    base_value + sample * 0.1,
                    f"uat-sim:agent:{hub}:{sample}",
                )
            )
    return expected


def test_the_job_start_samples_are_unchanged_by_the_coordination_fix() -> None:
    """A run before midnight reads the same rows the fixture always wrote.

    The other 95 sweep checks (and any backtest/shadow read) must see no change from this fix, so
    the job-start samples are pinned to their exact pre-fix ids, timestamps, prices and references.
    Seeded at 12:00:00Z the offsets resolve to whole half-hours.
    """

    rows = FIXTURE.agent_dayahead_observation_rows(datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC))

    assert [
        (
            row["observation_id"],
            row["metadata_json"]["hub"],
            row["observed_at_utc"],
            row["price"],
            row["source_reference"],
        )
        for row in rows
    ] == _expected_job_start_rows(28)


def test_the_refresh_reports_rather_than_stamping_when_a_day_cannot_hold_the_samples() -> None:
    """Exactly on UTC midnight a stalled clock cannot honestly carry two paired instants.

    The first moments of a UTC day hold fewer past instants than the spread analysis needs, and the
    refresh must report that - the run then blocks with the product's own ``INSUFFICIENT_HISTORY`` -
    rather than cover it with samples dated after the clock. This is the refusal the review
    required; the next test shows the same instant succeeding once the day has actually elapsed.
    """

    frozen = datetime(2026, 9, 28, 0, 0, 0, tzinfo=UTC)
    values = [frozen, frozen, frozen]

    refresh, writes = _refreshed(values)

    assert refresh is None
    assert writes == []
    in_day = [
        row for row in FIXTURE.agent_dayahead_observation_rows(frozen)
        if row["observed_at_utc"] >= frozen
    ]
    assert len(_paired_timestamps(in_day, window_start=frozen)) < 2


def test_the_refresh_recovers_once_the_new_day_has_elapsed_a_moment() -> None:
    """A ticking clock a few microseconds into the day can hold the samples honestly."""

    day_start = datetime(2026, 9, 28, 0, 0, 0, tzinfo=UTC)
    stamped_at = datetime(2026, 9, 28, 0, 0, 0, 4, tzinfo=UTC)
    after = datetime(2026, 9, 28, 0, 0, 0, 5, tzinfo=UTC)

    refresh, writes = _refreshed([day_start, stamped_at, after])

    assert refresh is not None
    assert writes == [list(refresh.rows)]
    assert refresh.day_start_utc == day_start
    assert refresh.stamped_at_utc == stamped_at
    for row in refresh.rows:
        assert day_start <= row["observed_at_utc"] <= stamped_at


def test_the_refresh_reseats_the_samples_when_the_write_crosses_utc_midnight() -> None:
    """A write that crosses midnight is re-stamped for the day that begins.

    The samples written for the day that just ended remain valid day-D history; they are simply not
    the set the run will read, so the refresh stamps again instead of leaving the interaction to
    block on a window it has already seen end.
    """

    day28 = datetime(2026, 9, 28, tzinfo=UTC)
    before_midnight = datetime(2026, 9, 28, 23, 59, 59, 999000, tzinfo=UTC)
    day29 = datetime(2026, 9, 29, tzinfo=UTC)
    after_midnight = datetime(2026, 9, 29, 0, 0, 0, 400, tzinfo=UTC)
    after_write = datetime(2026, 9, 29, 0, 0, 0, 500, tzinfo=UTC)

    refresh, writes = _refreshed([before_midnight, after_midnight, after_midnight, after_write])

    assert refresh is not None
    assert len(writes) == 2
    assert all(day28 <= row["observed_at_utc"] <= before_midnight for row in writes[0])
    assert refresh.day_start_utc == day29
    assert refresh.stamped_at_utc == after_midnight
    for row in refresh.rows:
        assert day29 <= row["observed_at_utc"] <= after_midnight


def test_the_pre_fix_placement_reproduces_the_ci_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the CI symptom, reproduced deterministically.

    With only the job-start samples - what the fixture wrote when CI36360322601 ran - the
    post-midnight window holds no paired history and the run blocks with exactly the blocker that
    run reported. This is the root cause encoded as a test, not a weakened gate: the orchestrator's
    refusal is the correct behaviour, so what has to change is the fixture's placement - never the
    gate that caught it.
    """

    seed_day_rows = [
        row
        for row in FIXTURE.agent_dayahead_observation_rows(CI_SEEDED_AT)
        if row["observed_at_utc"] < _day_start(CI_RUN_AT)
    ]
    assert seed_day_rows
    assert _paired_timestamps(seed_day_rows, window_start=_day_start(CI_RUN_AT)) == {}
    session = _stored_rows(tmp_path, "ci36360322601-pre-fix.sqlite", seed_day_rows)
    _freeze_orchestrator_clock(monkeypatch, CI_RUN_AT)

    outcome = _run_research(session, "agent-run-ci-pre-fix")

    assert outcome.status.value == "BLOCKED"
    assert "INSUFFICIENT_HISTORY" in outcome.blockers


def test_the_ci_run_reaches_the_review_gate_with_the_coordinated_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CI instants plus the harness's refresh: findings, StrategyIR, review gate."""

    refresh, writes = _refreshed([CI_REFRESH_AT, CI_REFRESH_AT])
    assert refresh is not None
    assert len(writes) == 1
    session = _stored_rows(tmp_path, "ci36360322601-fixed.sqlite", list(refresh.rows))
    _freeze_orchestrator_clock(monkeypatch, CI_RUN_AT)

    outcome = _run_research(session, "agent-run-ci-fixed")

    assert outcome.status.value == "READY_FOR_HUMAN_REVIEW", outcome.blockers
    assert outcome.findings
    assert outcome.strategy_ir is not None
    assert outcome.review_pack_id

    # The samples the run accepted are the refreshed set, and every one of them was stamped at or
    # before the run's own as-of instant - the window its spread analysis read.
    run_day_start = _day_start(CI_RUN_AT)
    accepted = [
        row for row in session.query(MarketObservationRecord).all()
        if _utc(row.observed_at_utc) >= run_day_start
    ]
    assert {row.observation_id for row in accepted} == {
        row["observation_id"] for row in refresh.rows
    }
    assert all(_utc(row.observed_at_utc) <= CI_RUN_AT for row in accepted)
    paired = _paired_timestamps(
        [
            {"observed_at_utc": _utc(row.observed_at_utc), "metadata_json": row.metadata_json}
            for row in accepted
        ],
        window_start=run_day_start,
        window_end=CI_RUN_AT + timedelta(microseconds=1),
    )
    assert len(paired) >= FIXTURE.AGENT_WINDOW_MIN_PAIRED_TIMESTAMPS
    assert int(outcome.findings[0].sample) == len(paired)


def test_the_browser_harness_refreshes_the_agent_window_immediately_before_the_run() -> None:
    """The coordination lives in the interaction, not only in the fixture.

    A refresh that ran with the job-start seed would be in the *seed's* day again; the point of the
    coordination is that it happens immediately before the governed research run files, through the
    harness's own fixture process (never a product write endpoint), with the UTC-day rollover check
    bounded and explicit.
    """

    harness = HARNESS.read_text(encoding="utf-8")

    assert 'AGENT_WINDOW_FLAG = "--agent-window-only";' in harness
    assert "spawnSync(PYTHON, [AGENT_WINDOW_SCRIPT, AGENT_WINDOW_FLAG]" in harness
    assert "a product write endpoint" in harness

    script = re.search(
        r"const AGENT_WINDOW_SCRIPT = path\.join\((?P<body>.*?)\);", harness, re.DOTALL
    )
    assert script, "the harness declares the fixture script it runs"
    for part in ('"scripts"', '"uat"', '"seed_uat_fixture.py"'):
        assert part in script.group("body"), f"the refreshed fixture is the UAT seed script: {part}"

    interaction = harness.index("async function agentResearchE2E(")
    refresh_call = harness.index("refreshAgentWindowFixture(failures, scope)", interaction)
    research_post = harness.index('includes("/api/agent/research")', interaction)
    assert interaction < refresh_call < research_post, (
        "the fixture refresh happens inside the research interaction and before the run is filed"
    )

    helper = harness.index("function refreshAgentWindowFixture(")
    assert helper < interaction, "the refresh helper is declared once, above its call site"
    assert "AGENT_WINDOW_MAX_ATTEMPTS" in harness[helper:interaction], (
        "the refresh retries are bounded by the declared attempt count"
    )
    assert "utcDayStart(new Date()).getTime() === summary.dayStart.getTime()" in harness, (
        "the rollover check compares the harness day with the day the fixture stamped"
    )


def test_the_harness_parses_the_report_line_the_fixture_prints() -> None:
    """The refresh is coordination only if the harness reads the day the fixture reports.

    The fixture prints one machine-readable line for what it stamped and the harness turns it into
    the day it compares with its own; the field names on both sides are the interface between the
    two processes, so they are pinned here rather than discovered when a CI run disagrees.
    """

    fixture = SEED_SCRIPT.read_text(encoding="utf-8")
    harness = HARNESS.read_text(encoding="utf-8")
    prefix = "UAT agent window ready:"

    assert prefix in fixture and prefix in harness
    for field in ("day_start", "stamped_at", "rows"):
        assert f"{field}=" in fixture, f"the fixture reports {field}"
        assert f"fields.{field}" in harness, f"the harness parses {field}"


def test_the_agent_window_command_stamps_one_utc_day_in_an_isolated_process(
    tmp_path: Path,
) -> None:
    """The labelled CI mode, end to end against a scratch fixture database.

    Run in an isolated process (never against a local runtime database), the command must exit 0,
    report the UTC day it stamped, and leave exactly the paired samples of that day - every one of
    them inside the day and at or before the stamp the report names.
    """

    database_url = _sqlite_url(tmp_path, "uat-agent-window.sqlite")
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    env = os.environ.copy()
    env.update(
        {
            "EUROGAS_NEXUS_ENV": "test",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
            "RUNTIME_STORE_DATABASE_URL": database_url,
        }
    )
    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT), FIXTURE.AGENT_WINDOW_FLAG],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    line = next(
        entry
        for entry in result.stdout.splitlines()
        if entry.startswith("UAT agent window ready:")
    )
    fields = dict(part.split("=", 1) for part in line.split(": ", 1)[1].split())
    day_start = datetime.fromisoformat(fields["day_start"])
    stamped_at = datetime.fromisoformat(fields["stamped_at"])
    assert day_start <= stamped_at < day_start + timedelta(days=1)

    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        rows = session.query(MarketObservationRecord).all()
    engine.dispose()

    assert len(rows) == int(fields["rows"]) == 10
    for row in rows:
        assert day_start <= _utc(row.observed_at_utc) <= stamped_at
        assert row.research_only is True
        assert row.source_system.endswith("_Sim")
    paired = _paired_timestamps(
        [
            {"observed_at_utc": _utc(row.observed_at_utc), "metadata_json": row.metadata_json}
            for row in rows
        ],
        window_start=day_start,
        window_end=stamped_at + timedelta(microseconds=1),
    )
    assert len(paired) >= 2
