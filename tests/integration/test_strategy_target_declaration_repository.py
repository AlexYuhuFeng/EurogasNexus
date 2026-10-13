"""Frozen evidence-target declarations survive store, read and fork.

CR-04 phase 1 stores the typed per-leg declaration in the immutable strategy
version definition. These tests use the repository's ordinary in-memory SQLite
fixture (the same pattern as the existing registry repository tests) to prove
three things the later target-aware engine depends on:

* a declared definition round-trips through persistence;
* forking reads the declaration back and writes a *new* draft with it, without
  touching the frozen source row;
* an undeclared legacy row still reads and forks, so old definitions remain
  readable while they are refused for new historical runs.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories import strategy_registry as repo
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyEvidenceTarget,
    StrategyVersionDefinition,
    canonical_content_hash,
)

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _targets() -> list[StrategyEvidenceTarget]:
    return [
        StrategyEvidenceTarget.model_validate(
            {
                "leg_id": "day_ahead",
                "price_names": ["SAP"],
                "role": "DELIVERY_PRICE",
                "hub": "NBP",
                "tenor": "day-ahead",
                "price_basis": "MID",
                "target_basis": "EXPLICIT_INTERVAL",
                "delivery_start_utc": "2026-09-30T05:00:00Z",
                "delivery_end_utc": "2026-10-01T05:00:00Z",
            }
        )
    ]


def _definition(*, targets: list[StrategyEvidenceTarget] | None) -> StrategyVersionDefinition:
    return StrategyVersionDefinition(
        components=[
            StrategyComponentSpec(
                component_id="ocm-da-1",
                component_type="OCM_VS_DAY_AHEAD",
                hubs=["NBP"],
                extension_json={
                    "weight": 1.0,
                    "day_ahead_price_names": ["SAP"],
                    "intraday_price_names": ["ICE_OCM"],
                },
                evidence_targets=targets,
            )
        ]
    )


def _frozen(session: Session, *, targets: list[StrategyEvidenceTarget] | None):
    repo.create_strategy(
        session,
        strategy_id="target-store",
        name="Target store",
        description="declaration persistence",
        created_by="operator",
        now_utc=NOW,
    )
    version = repo.create_strategy_version(
        session,
        strategy_id="target-store",
        definition=_definition(targets=targets),
        hypothesis="store the declaration",
        created_by="operator",
        now_utc=NOW,
        definition_overrides={"strategy_name": "Target store", "run_mode": "BACKTEST"},
    )
    frozen = repo.freeze_strategy_version(
        session,
        strategy_version_id=version.strategy_version_id,
        frozen_by="operator",
        now_utc=NOW,
    )
    session.flush()
    return frozen


def test_a_declared_definition_round_trips_through_the_store(session: Session) -> None:
    version = _frozen(session, targets=_targets())

    stored = repo.get_strategy_version(session, version.strategy_version_id)
    assert stored is not None
    parsed = StrategyVersionDefinition.model_validate(stored.definition_json)
    target = parsed.components[0].evidence_targets
    assert target is not None
    assert target[0].leg_id == "day_ahead"
    assert target[0].delivery_start_utc == datetime(2026, 9, 30, 5, 0, tzinfo=UTC)
    # The stored hash covers the declaration, so a submitted declaration is
    # identity-bearing rather than cosmetic metadata.
    assert stored.content_hash == canonical_content_hash(stored.definition_json)


def test_a_legacy_definition_reads_and_forks_without_a_declaration(session: Session) -> None:
    source = _frozen(session, targets=None)
    assert "evidence_targets" not in source.definition_json["components"][0]

    forked = repo.fork_strategy_version(
        session,
        source_version_id=source.strategy_version_id,
        definition=None,
        hypothesis=None,
        created_by="operator",
        now_utc=NOW,
    )
    session.flush()

    assert forked.status == "DRAFT"
    assert forked.parent_version_id == source.strategy_version_id
    assert "evidence_targets" not in forked.definition_json["components"][0]
    # Forking is additive: the frozen source row is unchanged.
    assert source.status == "FROZEN"


def test_a_fork_inherits_the_declaration_and_leaves_the_source_byte_identical(
    session: Session,
) -> None:
    source = _frozen(session, targets=_targets())
    before_json = copy.deepcopy(source.definition_json)
    before_hash = source.content_hash
    before_status = source.status

    forked = repo.fork_strategy_version(
        session,
        source_version_id=source.strategy_version_id,
        definition=None,
        hypothesis="fork with the same declaration",
        created_by="operator",
        now_utc=NOW,
    )
    session.flush()

    assert forked.definition_json["components"][0]["evidence_targets"] == (
        source.definition_json["components"][0]["evidence_targets"]
    )
    assert forked.content_hash == source.content_hash
    assert forked.strategy_version_id != source.strategy_version_id

    # The original frozen row was not rewritten by the fork, and its parent
    # link points back at it rather than replacing it.
    reread = repo.get_strategy_version(session, source.strategy_version_id)
    assert reread is not None
    assert reread.definition_json == before_json
    assert reread.content_hash == before_hash
    assert reread.status == before_status


def test_an_edited_fork_carries_a_new_declaration_and_a_new_hash(session: Session) -> None:
    source = _frozen(session, targets=_targets())
    source_hash = source.content_hash

    edited = StrategyVersionDefinition.model_validate(source.definition_json)
    moved = StrategyEvidenceTarget.model_validate(
        {
            **edited.components[0].evidence_targets[0].model_dump(mode="json"),
            "delivery_end_utc": "2026-10-02T05:00:00Z",
        }
    )
    edited.components[0].evidence_targets = [moved]

    forked = repo.fork_strategy_version(
        session,
        source_version_id=source.strategy_version_id,
        definition=edited,
        hypothesis="move the target interval",
        created_by="operator",
        now_utc=NOW,
    )
    session.flush()

    assert forked.content_hash != source_hash
    assert forked.definition_json["components"][0]["evidence_targets"][0][
        "delivery_end_utc"
    ] == "2026-10-02T05:00:00Z"
    assert repo.get_strategy_version(
        session, source.strategy_version_id
    ).content_hash == source_hash
