"""Focused repository tests for bounded market-source coverage.

The reservation half of ``list_market_observations_with_source_coverage`` used to
rank every gas row of ``market_observations`` with ``row_number()`` and count the
gas sources with a second aggregate. These tests hold the replacement - one
bounded read per source - to that shape's *answer* rather than to its cost:

- the full composition is compared, row for row, against the superseded shape
  re-implemented here verbatim (``_superseded_composition``);
- the cases the brief names are covered directly: restricted sources, sources with
  no gas row at all, a quota smaller than the source count, rows that tie on the
  whole order key, and daily rows behind a tick flood;
- the read's own bounds are pinned from the statements it issues: one statement per
  source, one row limit per source, and no statement for a source the caller is not
  entitled to.

The case the bounded read must not decide - more candidate sources than the payload
bound, so the reservation cannot fit - still selects through the superseded window
query, and is pinned to that algorithm's statements and rows rather than to a
newest-reservation rule the replacement would otherwise have introduced. Where the
superseded shape left a choice to the database - the join's row order, and rows tied
on the whole order key - the tests say so instead of pinning it.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord
from eurogas_nexus.db.repositories.market_intelligence import (
    _bounded_source_coverage_rows,
    _merge_bounded_source_coverage,
    _newest_gas_row_page,
    list_market_observations_with_source_coverage,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
PER_SOURCE_LIMIT = 40

#: The entitled set the scoped callers below hold: two gas sources (a tick feed and
#: a daily assessment) plus a source whose rows carry no gas unit at all.
ALLOWED_SOURCES = {"SIM_TICKS", "ICIS", "ENTSOG"}


def _row(observation_id: str, minute: int) -> SimpleNamespace:
    return SimpleNamespace(
        observation_id=observation_id,
        observed_at_utc=datetime(2026, 8, 30, 0, 0, tzinfo=UTC)
        + timedelta(minutes=minute),
        market_venue="fixture",
        product="day-ahead",
    )


def test_source_coverage_is_preserved_without_exceeding_limit() -> None:
    newest = [_row(f"fast-{minute}", minute) for minute in range(10, 5, -1)]
    low_frequency = _row("icis-daily", 1)

    rows = _merge_bounded_source_coverage(
        newest,
        [low_frequency, newest[0]],
        limit=4,
    )

    assert len(rows) == 4
    assert rows[0].observation_id == "fast-10"
    assert rows[-1].observation_id == "icis-daily"
    assert len({row.observation_id for row in rows}) == len(rows)


def _observation(
    observation_id: str,
    source_system: str,
    *,
    observed_at: datetime,
    venue: str = "EEX",
    product: str = "NBP Day-Ahead",
    unit: str = "EUR/MWh",
) -> MarketObservationRecord:
    return MarketObservationRecord(
        observation_id=observation_id,
        market_venue=venue,
        product=product,
        price=31.0,
        unit=unit,
        currency="EUR",
        period_start_utc=observed_at,
        period_end_utc=observed_at + timedelta(days=1),
        observed_at_utc=observed_at,
        source_system=source_system,
        source_reference=f"fixture:{source_system}",
        source_record_id=observation_id,
        freshness="live",
        quality_score=0.9,
        research_only=True,
        metadata_json={"hub": venue},
    )


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(session: Session) -> None:
    """Seed a tick feed, a daily assessment, a non-gas source and a restricted one.

    Every row carries a distinct observed instant, so both the superseded ranking
    and the bounded per-source read are fully determined and can be compared row
    for row. The tie case has its own test.
    """

    session.add_all(
        [
            _observation(
                f"tick-{index:03d}",
                "SIM_TICKS",
                observed_at=NOW - timedelta(minutes=index),
            )
            for index in range(60)
        ]
        + [
            _observation(
                f"daily-{index}",
                "ICIS",
                observed_at=NOW - timedelta(days=index + 1),
                venue="ICIS",
                product="TTF Day-Ahead",
            )
            for index in range(3)
        ]
        + [
            _observation(
                f"flow-{index}",
                "ENTSOG",
                observed_at=NOW - timedelta(hours=index + 2),
                venue="ENTSOG",
                product="NBP flows",
                unit="MCM/d",
            )
            for index in range(2)
        ]
        + [
            _observation(
                f"ice-{index}",
                "ICE_OCM",
                # Offset by a second so no restricted row ties with a tick on the
                # whole order key: the comparison below is against a shape whose
                # choice among ties was never specified.
                observed_at=NOW - timedelta(seconds=index + 1),
            )
            for index in range(5)
        ]
    )
    session.commit()


def _newest_rows(
    session: Session,
    *,
    limit: int,
    source_systems: set[str] | None,
) -> list:
    """The composition's first half, which this change does not touch."""

    query = session.query(MarketObservationRecord)
    if source_systems is not None:
        query = query.filter(MarketObservationRecord.source_system.in_(source_systems))
    return (
        query.order_by(
            MarketObservationRecord.observed_at_utc.desc(),
            MarketObservationRecord.market_venue,
            MarketObservationRecord.product,
        )
        .limit(limit)
        .all()
    )


def _superseded_coverage_rows(
    session: Session,
    *,
    limit: int,
    per_source_limit: int,
    source_systems: set[str] | None,
) -> list:
    """The removed reservation shape, kept here as the reference to compare against.

    This is the code the replacement deletes: count the gas sources with an
    aggregate, rank every gas row of the table per source, then join the ranked ids
    back to the table. It is re-implemented rather than imported so the comparison
    is against the shape that actually shipped, not against the replacement's own
    idea of it.
    """

    count_query = session.query(
        func.count(func.distinct(MarketObservationRecord.source_system))
    ).filter(MarketObservationRecord.unit.ilike("%MWH%"))
    if source_systems is not None:
        count_query = count_query.filter(
            MarketObservationRecord.source_system.in_(source_systems)
        )
    source_count = count_query.scalar() or 0
    if source_count == 0:
        return []

    source_quota = min(per_source_limit, max(1, limit // source_count))
    ranked_query = session.query(
        MarketObservationRecord.observation_id.label("observation_id"),
        func.row_number()
        .over(
            partition_by=MarketObservationRecord.source_system,
            order_by=(
                MarketObservationRecord.observed_at_utc.desc(),
                MarketObservationRecord.market_venue,
                MarketObservationRecord.product,
            ),
        )
        .label("source_rank"),
    ).filter(MarketObservationRecord.unit.ilike("%MWH%"))
    if source_systems is not None:
        ranked_query = ranked_query.filter(
            MarketObservationRecord.source_system.in_(source_systems)
        )
    ranked_rows = ranked_query.subquery()
    return (
        session.query(MarketObservationRecord)
        .join(
            ranked_rows,
            ranked_rows.c.observation_id == MarketObservationRecord.observation_id,
        )
        .filter(ranked_rows.c.source_rank <= source_quota)
        .all()
    )


def _superseded_composition(
    session: Session,
    *,
    limit: int,
    per_source_limit: int,
    source_systems: set[str] | None,
) -> list:
    """The removed composition: same newest read, same merge, removed reservation."""

    newest_rows = _newest_rows(session, limit=limit, source_systems=source_systems)
    if limit <= 0 or not newest_rows:
        return newest_rows
    return _merge_bounded_source_coverage(
        newest_rows,
        _superseded_coverage_rows(
            session,
            limit=limit,
            per_source_limit=per_source_limit,
            source_systems=source_systems,
        ),
        limit=limit,
    )


def _captured_statements(session: Session) -> list[tuple[str, tuple[Any, ...]]]:
    """Every statement the session issues from now on, with its parameters."""

    captured: list[tuple[str, tuple[Any, ...]]] = []

    def record(connection, cursor, statement, parameters, context, executemany) -> None:
        captured.append((" ".join(statement.split()), tuple(parameters or ())))

    event.listen(session.get_bind(), "before_cursor_execute", record)
    return captured


def _source_page_statements(
    statements: list[tuple[str, tuple[Any, ...]]],
) -> list[tuple[str, tuple[Any, ...]]]:
    """The per-source coverage reads, identified by their own source equality."""

    return [
        (statement, parameters)
        for statement, parameters in statements
        if "market_observations.source_system = ?" in statement
    ]


def _window_statements(
    statements: list[tuple[str, tuple[Any, ...]]],
) -> list[tuple[str, tuple[Any, ...]]]:
    """The superseded ranking window's read, identified by its window function."""

    return [
        (statement, parameters)
        for statement, parameters in statements
        if "row_number" in statement.lower()
    ]


@pytest.mark.parametrize(
    ("limit", "per_source_limit"),
    [(6, PER_SOURCE_LIMIT), (100, PER_SOURCE_LIMIT), (3, PER_SOURCE_LIMIT), (100, 3), (4, 1)],
)
def test_source_coverage_read_matches_the_superseded_composition(
    limit: int,
    per_source_limit: int,
) -> None:
    """The bounded per-source read returns what the removed ranking returned."""

    with _session() as session:
        _seed(session)
        expected = [
            row.observation_id
            for row in _superseded_composition(
                session,
                limit=limit,
                per_source_limit=per_source_limit,
                source_systems=ALLOWED_SOURCES,
            )
        ]
        actual = [
            row.observation_id
            for row in list_market_observations_with_source_coverage(
                session,
                limit=limit,
                per_source_limit=per_source_limit,
                source_systems=ALLOWED_SOURCES,
            )
        ]

    assert actual == expected
    assert len(actual) <= limit
    assert len(set(actual)) == len(actual)


@pytest.mark.parametrize("seed", [17, 20260925])
def test_seeded_source_sets_match_the_superseded_composition(seed: int) -> None:
    """A seeded sweep over source mixes and quota regimes, compared with the old shape.

    Each row carries a distinct observed instant (the tie case has its own test), so
    the reserved rows are determined in both shapes. Where the reservation fits
    inside ``limit`` the whole ordered composition is compared row for row; where it
    does not - which is exactly the case the superseded shape left to the database's
    row order - the candidate pools are compared and the shipped shape is held to
    its declared rule instead of to an unspecified one.
    """

    rng = random.Random(seed)
    sources = [f"SRC_{index}" for index in range(rng.randint(2, 5))]
    instant = NOW
    rows = []
    counter = 0
    for source in sources:
        for _ in range(rng.randint(0, 25)):
            counter += 1
            rows.append(
                _observation(
                    f"obs-{counter:03d}",
                    source,
                    observed_at=instant - timedelta(minutes=counter),
                    venue=f"V{rng.randint(1, 3)}",
                    product=f"P{rng.randint(1, 2)}",
                    unit="EUR/MWh" if rng.random() < 0.7 else "MCM/d",
                )
            )
    allowed = {source for source in sources if rng.random() < 0.8}
    gas_sources = {
        row.source_system
        for row in rows
        if row.source_system in allowed and "MWH" in (row.unit or "").upper()
    }
    # A sweep with nothing to reserve would compare two empty answers.
    assert len(gas_sources) >= 2

    with _session() as session:
        session.add_all(rows)
        session.commit()
        for limit, per_source_limit in ((1, PER_SOURCE_LIMIT), (7, 3), (40, PER_SOURCE_LIMIT)):
            quota = min(per_source_limit, max(1, limit // len(gas_sources)))
            expected = [
                row.observation_id
                for row in _superseded_composition(
                    session,
                    limit=limit,
                    per_source_limit=per_source_limit,
                    source_systems=allowed,
                )
            ]
            actual = [
                row.observation_id
                for row in list_market_observations_with_source_coverage(
                    session,
                    limit=limit,
                    per_source_limit=per_source_limit,
                    source_systems=allowed,
                )
            ]
            reserved_pool = {
                row.observation_id
                for row in _bounded_source_coverage_rows(
                    session,
                    limit=limit,
                    per_source_limit=per_source_limit,
                    source_systems=allowed,
                )
            }
            superseded_pool = {
                row.observation_id
                for row in _superseded_coverage_rows(
                    session,
                    limit=limit,
                    per_source_limit=per_source_limit,
                    source_systems=allowed,
                )
            }

            assert reserved_pool == superseded_pool
            assert len(actual) <= limit
            if len(gas_sources) * quota <= limit:
                # The reservation fits, so the quota and the read order decide the
                # payload in both shapes.
                assert actual == expected
            else:
                # The reservation cannot fit: the fallback runs the superseded window,
                # so the rows are the window's - and the row order that window leaves
                # to the database is not asserted here.
                assert set(actual) == set(expected)
                assert len(actual) == limit


def test_daily_rows_survive_the_tick_flood_only_because_they_are_reserved() -> None:
    """A daily source older than every tick keeps its quota."""

    with _session() as session:
        _seed(session)
        newest_only = [
            row.observation_id
            for row in _newest_rows(session, limit=50, source_systems=ALLOWED_SOURCES)
        ]
        covered = [
            row.observation_id
            for row in list_market_observations_with_source_coverage(
                session,
                limit=50,
                per_source_limit=PER_SOURCE_LIMIT,
                source_systems=ALLOWED_SOURCES,
            )
        ]

    assert not {"daily-0", "daily-1", "daily-2"} & set(newest_only)
    assert {"daily-0", "daily-1", "daily-2"}.issubset(covered)
    # A source with no gas-unit row reserves nothing, so the quota is 50 // 2 and
    # every daily row fits rather than 50 // 3.
    assert len(covered) == 50
    assert "flow-0" not in covered


def test_candidate_pool_matches_the_superseded_ranking_for_every_source() -> None:
    """The same rows are candidates; only the choice among them changed when bounded."""

    with _session() as session:
        _seed(session)
        superseded_pool = {
            row.observation_id
            for row in _superseded_coverage_rows(
                session,
                limit=1000,
                per_source_limit=PER_SOURCE_LIMIT,
                source_systems=ALLOWED_SOURCES,
            )
        }
        bounded_pool = {
            row.observation_id
            for row in _bounded_source_coverage_rows(
                session,
                limit=1000,
                per_source_limit=PER_SOURCE_LIMIT,
                source_systems=ALLOWED_SOURCES,
            )
        }

    assert bounded_pool == superseded_pool


def test_more_sources_than_the_bound_keeps_the_superseded_window_query() -> None:
    """The case a page order must not decide still selects through the old window.

    Four gas sources under a bound of two put the quota at one row per source, so the
    reservation is four rows and cannot fit. Which two survive was the ranking
    window's choice before, and the bounded read does not take that decision over: it
    falls back to the superseded statements. The fixture's newest reserved rows are
    the C and D rows, so a newest-reservation-wins rule would return those two
    instead of the window's pair.
    """

    with _session() as session:
        session.add_all(
            [
                _observation(
                    f"src-{source}-0",
                    source,
                    observed_at=NOW - timedelta(minutes=30 - index * 10),
                )
                for index, source in enumerate(("SRC_A", "SRC_B", "SRC_C", "SRC_D"))
            ]
            + [
                _observation(f"src-{source}-1", source, observed_at=NOW - timedelta(days=1))
                for source in ("SRC_A", "SRC_B", "SRC_C", "SRC_D")
            ]
        )
        session.commit()
        allowed = {"SRC_A", "SRC_B", "SRC_C", "SRC_D"}
        statements = _captured_statements(session)
        rows = list_market_observations_with_source_coverage(
            session,
            limit=2,
            per_source_limit=PER_SOURCE_LIMIT,
            source_systems=allowed,
        )
        composition_statements = list(statements)
        reserved = _bounded_source_coverage_rows(
            session,
            limit=2,
            per_source_limit=PER_SOURCE_LIMIT,
            source_systems=allowed,
        )
        reservation_statements = list(statements)
        # The same fallback serves a caller that holds no entitled source set.
        unscoped_rows = list_market_observations_with_source_coverage(
            session,
            limit=2,
            per_source_limit=PER_SOURCE_LIMIT,
        )
        superseded = _superseded_composition(
            session,
            limit=2,
            per_source_limit=PER_SOURCE_LIMIT,
            source_systems=allowed,
        )

    # Quota 1 with four sources under a bound of two: the reservation is the newest
    # row of every source, the candidate pool the superseded window produced.
    assert {row.observation_id for row in reserved} == {
        "src-SRC_A-0",
        "src-SRC_B-0",
        "src-SRC_C-0",
        "src-SRC_D-0",
    }
    # The fallback reads the superseded statements: no per-source page at all, and
    # the source count plus the ranking window instead.
    assert _source_page_statements(reservation_statements) == []
    assert len(_window_statements(composition_statements)) == 1
    # Same algorithm, same store: the rows are the window's own, and the payload
    # stays inside the bound.
    assert [row.observation_id for row in rows] == [
        row.observation_id for row in superseded
    ]
    assert len(rows) == 2
    assert len({row.observation_id for row in rows}) == len(rows)
    assert [row.observation_id for row in unscoped_rows] == [
        row.observation_id for row in rows
    ]


def test_rows_tied_on_the_order_key_are_not_given_a_new_tie_break() -> None:
    """Ties are cut by the store, as the superseded window cut them.

    Six rows of one source share the whole order key and the bound keeps two of them.
    Which two is the database's choice - the superseded ranking window had exactly
    that property - and the replacement does not append an ``observation_id``
    tie-break to redefine it. The test pins the parts that are defined: the bound,
    the tied candidate set, and that the payload holds rows the page itself read.
    """

    with _session() as session:
        session.add_all(
            [
                _observation(f"tie-{index}", "SIM_TICKS", observed_at=NOW)
                for index in range(6)
            ]
        )
        session.commit()
        statements = _captured_statements(session)
        rows = list_market_observations_with_source_coverage(
            session,
            limit=2,
            per_source_limit=2,
            source_systems={"SIM_TICKS"},
        )
        page_ids = {
            row.observation_id
            for row in _newest_gas_row_page(session, source="SIM_TICKS", bound=2)
        }

    assert len(rows) == 2
    assert {row.observation_id for row in rows} == page_ids
    assert page_ids <= {f"tie-{index}" for index in range(6)}
    # The page carries the route's own order fields and nothing appended to them.
    assert all("observation_id desc" not in statement.lower() for statement, _ in statements)


def test_entitlement_narrows_the_sources_read_before_the_limit() -> None:
    """A restricted source is never read, and each entitled source is read once."""

    with _session() as session:
        _seed(session)
        statements = _captured_statements(session)
        rows = list_market_observations_with_source_coverage(
            session,
            limit=8,
            per_source_limit=PER_SOURCE_LIMIT,
            source_systems=ALLOWED_SOURCES,
        )

    page_statements = _source_page_statements(statements)
    assert len(page_statements) == len(ALLOWED_SOURCES)
    assert {parameters[0] for _, parameters in page_statements} == ALLOWED_SOURCES
    assert all("ICE_OCM" not in statement for statement, _ in statements)
    assert not [row for row in rows if row.source_system == "ICE_OCM"]


def test_without_a_source_set_every_source_is_read_once_at_the_page_bound() -> None:
    """No entitlement set means one enumeration read plus one bounded read per source."""

    with _session() as session:
        _seed(session)
        source_count = (
            session.query(MarketObservationRecord.source_system).distinct().count()
        )
        statements = _captured_statements(session)
        rows = list_market_observations_with_source_coverage(
            session,
            limit=4,
            per_source_limit=PER_SOURCE_LIMIT,
        )
        read_statements = list(statements)
        reference = [
            row.observation_id
            for row in _superseded_composition(
                session,
                limit=4,
                per_source_limit=PER_SOURCE_LIMIT,
                source_systems=None,
            )
        ]

    page_statements = _source_page_statements(read_statements)
    assert source_count == 4
    assert len(page_statements) == source_count
    # One newest read, one source enumeration, one bounded page per source: the
    # statement count grows with the sources, not with the table.
    assert len(read_statements) == source_count + 2
    assert {(parameters[0], parameters[1], parameters[2]) for _, parameters in page_statements} == {
        (source, "%MWH%", 4) for source in ("ENTSOG", "ICE_OCM", "ICIS", "SIM_TICKS")
    }
    assert all("LIMIT" in statement.upper() for statement, _ in page_statements)
    assert all("row_number" not in statement.lower() for statement, _ in read_statements)
    assert len(rows) <= 4
    # The no-source-set caller (the resource-pool composition) gets the rows the
    # superseded shape returned for the same inputs.
    assert [row.observation_id for row in rows] == reference


def test_no_room_and_no_rows_read_no_source_page() -> None:
    """A bound of zero, an empty source set or no quota issues no per-source read.

    ``per_source_limit=0`` is not a "no rows" case, and never was: the reservation
    is empty and the composition returns the newest page.
    """

    with _session() as session:
        _seed(session)
        statements = _captured_statements(session)
        zero_limit = list_market_observations_with_source_coverage(
            session,
            limit=0,
            per_source_limit=PER_SOURCE_LIMIT,
            source_systems=ALLOWED_SOURCES,
        )
        no_sources = list_market_observations_with_source_coverage(
            session,
            limit=10,
            per_source_limit=PER_SOURCE_LIMIT,
            source_systems=set(),
        )
        no_quota = list_market_observations_with_source_coverage(
            session,
            limit=10,
            per_source_limit=0,
            source_systems=ALLOWED_SOURCES,
        )
        newest = [
            row.observation_id
            for row in _newest_rows(session, limit=10, source_systems=ALLOWED_SOURCES)
        ]

    assert zero_limit == []
    assert no_sources == []
    assert [row.observation_id for row in no_quota] == newest
    assert _source_page_statements(statements) == []
