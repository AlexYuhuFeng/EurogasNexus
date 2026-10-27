"""Query-count and output-parity tests for batched Decision Case reads.

The lists and packs are read paths, so their correctness is both the payload they
return and the number of statements the database executes. These tests count the
SELECTs SQLAlchemy actually sends to SQLite: one page of cases must cost the same
whether it holds one case or fifty, and resolving one cited snapshot must cost
the same as resolving many (including duplicates and misses).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.decision_pack import load_decision_pack
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AnalysisSnapshotRecord
from eurogas_nexus.db.models.decision import DecisionCaseDecisionRecord, DecisionCaseRecord
from eurogas_nexus.db.repositories.data_platform import get_existing_analysis_snapshot_ids
from eurogas_nexus.db.repositories.decision import (
    _to_domain,
    _to_domains,
    get_decision_case,
    list_decision_cases,
)

_BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _prepare(tmp_path) -> Engine:
    db_path = tmp_path / "decision-query-batching.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    assert engine.dialect.name == "sqlite"
    Base.metadata.create_all(engine)
    return engine


def _add_case(
    session: Session,
    *,
    case_id: str,
    index: int,
    status: str = "OPEN",
    evidence: list[dict] | None = None,
    snapshot_id: str = "",
) -> None:
    session.add(
        DecisionCaseRecord(
            case_id=case_id,
            objective=f"Objective {index}",
            status=status,
            created_by="analyst",
            created_at_utc=_BASE,
            updated_at_utc=_BASE + timedelta(minutes=index),
            gas_day="2026-09-15",
            delivery_product="day-ahead",
            hub_id="NBP",
            portfolio_ref="",
            snapshot_id=snapshot_id,
            assumptions_json=[
                {"key": "carry", "value": str(index), "source": "BACKEND", "note": ""}
            ],
            alternatives_json=[
                {
                    "alternative_id": f"alt-{index}",
                    "label": "Alternative",
                    "description": "",
                    "economics_ref": "",
                    "warnings": [],
                }
            ],
            evidence_json=(
                [
                    {
                        "kind": "MARKET_CONTEXT",
                        "ref": f"ev-{index}",
                        "label": "",
                        "as_of_utc": "",
                        "snapshot_id": f"snap-{index:03d}",
                    }
                ]
                if evidence is None
                else evidence
            ),
            ai_findings_json=[],
            warnings_json=[],
        )
    )
    # Inserted out of chronological order to prove the read orders by
    # recorded_at_utc rather than by insertion or primary key.
    for order, minute in enumerate((7, 2, 5)):
        session.add(
            DecisionCaseDecisionRecord(
                record_id=f"drec-{index:03d}-{order}",
                case_id=case_id,
                outcome="accepted" if order == 2 else "needs_attention",
                actor=f"reviewer-{order}",
                note=f"note-{order}",
                evidence_refs_json=[f"ev-{index}"],
                recorded_at_utc=_BASE + timedelta(minutes=minute),
            )
        )


def _seed_cases(engine: Engine, count: int = 50) -> None:
    with Session(engine) as session:
        for index in range(count):
            _add_case(
                session,
                case_id=f"case-{index:03d}",
                index=index,
                status="OPEN" if index % 2 == 0 else "DECIDED",
            )
        session.commit()


def _seed_snapshots(engine: Engine, count: int = 10) -> None:
    with Session(engine) as session:
        for index in range(count):
            session.add(
                AnalysisSnapshotRecord(
                    snapshot_id=f"snap-{index:02d}",
                    schema_version="analysis-snapshot-1",
                    as_of_utc=_BASE,
                    gas_day="2026-09-15",
                    gas_day_calendar="EU",
                    time_basis="UTC",
                    created_at_utc=_BASE,
                    created_by="analyst",
                    content_hash=f"sha256:test-{index}",
                )
            )
        session.commit()


def _count_selects(engine: Engine, operation):
    statements: list[str] = []

    def _before_cursor_execute(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    try:
        result = operation()
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)
    return result, len(statements)


def _list(engine: Engine, **kwargs) -> list[dict]:
    with Session(engine) as session:
        return list_decision_cases(session, **kwargs)


def _load_pack(engine: Engine, case_id: str) -> dict | None:
    with Session(engine) as session:
        return load_decision_pack(session, case_id)


def _expected_summary(full: dict) -> dict:
    records = full["records"]
    return {
        "case_id": full["case_id"],
        "objective": full["objective"][:160],
        "status": full["status"],
        "gas_day": full["gas_day"],
        "delivery_product": full["delivery_product"],
        "hub_id": full["hub_id"],
        "evidence_count": len(full["evidence"]),
        "alternative_count": len(full["alternatives"]),
        "assumption_count": len(full["assumptions"]),
        "record_count": len(records),
        "reproducible": full["reproducible"],
        "last_record": (
            {
                "outcome": records[-1]["outcome"],
                "actor": records[-1]["actor"],
                "recorded_at_utc": records[-1]["recorded_at_utc"],
            }
            if records
            else None
        ),
    }


def test_list_read_count_is_constant_from_one_case_to_fifty(tmp_path) -> None:
    engine = _prepare(tmp_path)
    _seed_cases(engine, 50)

    one, one_selects = _count_selects(engine, lambda: _list(engine, limit=1))
    fifty, fifty_selects = _count_selects(engine, lambda: _list(engine, limit=50))

    assert len(one) == 1
    assert len(fifty) == 50
    # One case query plus one decision-record query, not 1 + N and 1 + 50.
    assert one_selects == 2
    assert fifty_selects == 2
    assert [row["case_id"] for row in one] == ["case-049"]
    assert [row["case_id"] for row in fifty] == [
        f"case-{index:03d}" for index in range(49, -1, -1)
    ]


def test_batched_summaries_match_full_payload_and_decision_order(tmp_path) -> None:
    engine = _prepare(tmp_path)
    _seed_cases(engine, 50)

    with Session(engine) as session:
        summaries = list_decision_cases(session, limit=50)
        rows = (
            session.query(DecisionCaseRecord)
            .order_by(DecisionCaseRecord.updated_at_utc.desc())
            .limit(50)
            .all()
        )
        batched_domains = _to_domains(session, rows)
        single_domains = [_to_domain(session, row) for row in rows]

        # The batch read maps through the same domain path, so every field and
        # the full record order are identical to loading each case on its own.
        assert batched_domains == single_domains
        assert summaries == [
            _expected_summary(get_decision_case(session, domain.case_id))
            for domain in batched_domains
        ]

        for domain in batched_domains:
            assert [record.recorded_at_utc for record in domain.records] == sorted(
                record.recorded_at_utc for record in domain.records
            )
            assert [record.actor for record in domain.records] == [
                "reviewer-1",
                "reviewer-2",
                "reviewer-0",
            ]


def test_list_status_filter_limit_and_empty_cases_are_unchanged(tmp_path) -> None:
    engine = _prepare(tmp_path)
    _seed_cases(engine, 50)

    open_cases, _ = _count_selects(
        engine, lambda: _list(engine, status="OPEN", limit=50)
    )
    assert [row["case_id"] for row in open_cases] == [
        f"case-{index:03d}" for index in range(48, -1, -2)
    ]
    assert {row["status"] for row in open_cases} == {"OPEN"}

    clamped, _ = _count_selects(engine, lambda: _list(engine, status="OPEN", limit=0))
    assert len(clamped) == 1
    assert clamped[0]["case_id"] == "case-048"

    empty, empty_selects = _count_selects(
        engine, lambda: _list(engine, status="NOT_A_STATUS")
    )
    assert empty == []
    # An empty page does not issue the decision-record read at all.
    assert empty_selects == 1


def test_pack_snapshot_resolution_is_constant_and_keeps_unresolved_duplicates(
    tmp_path,
) -> None:
    engine = _prepare(tmp_path)
    _seed_snapshots(engine, 10)

    many_evidence = [
        {
            "kind": "MARKET_CONTEXT",
            "ref": f"ev-{index}",
            "label": "",
            "as_of_utc": "",
            "snapshot_id": f"snap-{index % 10:02d}",
        }
        for index in range(12)
    ]
    many_evidence.extend(
        [
            {
                "kind": "MARKET_CONTEXT",
                "ref": "ev-missing-a",
                "label": "",
                "as_of_utc": "",
                "snapshot_id": "snap-missing",
            },
            {
                "kind": "MARKET_CONTEXT",
                "ref": "ev-missing-b",
                "label": "",
                "as_of_utc": "",
                "snapshot_id": "snap-missing",
            },
        ]
    )
    with Session(engine) as session:
        _add_case(
            session,
            case_id="case-one-evidence",
            index=60,
            evidence=[
                {
                    "kind": "MARKET_CONTEXT",
                    "ref": "ev-one",
                    "label": "",
                    "as_of_utc": "",
                    "snapshot_id": "snap-00",
                }
            ],
        )
        _add_case(
            session,
            case_id="case-many-evidence",
            index=61,
            evidence=many_evidence,
        )
        session.commit()

    one_pack, one_selects = _count_selects(
        engine, lambda: _load_pack(engine, "case-one-evidence")
    )
    many_pack, many_selects = _count_selects(
        engine, lambda: _load_pack(engine, "case-many-evidence")
    )

    assert one_selects == 4
    assert many_selects == 4
    assert one_pack is not None
    assert many_pack is not None
    assert len(one_pack["evidence"]) == 1
    assert one_pack["evidence"][0]["snapshot_resolvable"] is True

    assert len(many_pack["evidence"]) == 14
    assert [entry["snapshot_resolvable"] for entry in many_pack["evidence"][:12]] == [
        True
    ] * 12
    assert [entry["ref"] for entry in many_pack["evidence"][-2:]] == [
        "ev-missing-a",
        "ev-missing-b",
    ]
    assert many_pack["evidence"][-1]["snapshot_resolvable"] is False
    assert "DECISION_PACK_SNAPSHOT_UNRESOLVED" in many_pack["blockers"]

    with Session(engine) as session:
        full_case = get_decision_case(session, "case-many-evidence")
    assert full_case is not None
    assert many_pack["history"] == full_case["records"]
    assert many_pack["decision"] == full_case["records"][-1]
    assert [record["recorded_at_utc"] for record in many_pack["history"]] == sorted(
        record["recorded_at_utc"] for record in many_pack["history"]
    )


def test_existing_snapshot_id_read_deduplicates_and_skips_an_empty_set(tmp_path) -> None:
    engine = _prepare(tmp_path)
    _seed_snapshots(engine, 3)

    existing, existing_selects = _count_selects(
        engine,
        lambda: _read_existing(
            engine,
            ["snap-00", "snap-00", "snap-01", "snap-missing", "snap-01"],
        ),
    )
    empty, empty_selects = _count_selects(
        engine, lambda: _read_existing(engine, [])
    )

    assert existing == {"snap-00", "snap-01"}
    assert existing_selects == 1
    assert empty == set()
    assert empty_selects == 0


def _read_existing(engine: Engine, snapshot_ids: list[str]) -> set[str]:
    with Session(engine) as session:
        return get_existing_analysis_snapshot_ids(session, snapshot_ids)
