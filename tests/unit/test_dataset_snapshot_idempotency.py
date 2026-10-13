"""A rebuilt dataset snapshot must be idempotent, and a conflict must name itself.

Why this test exists
--------------------
A snapshot id is content-addressed: it embeds a hash of the specification and rows, so
building the same dataset twice produces the same id. The second build used to violate
`dataset_snapshots_pkey` with `23505 duplicate key value`, and because the route caught
only `KeyError`, `TypeError`, `ValueError`, `DatasetRegistryError` and `HTTPException`,
the SQLAlchemy `IntegrityError` escaped as an unhandled 500. The client renders
field-level issues from the refusal envelope, so the user saw a generic system error and
an empty panel that named nothing.

Three properties replace that:

1. a second build of unchanged content returns the stored snapshot and says it was reused;
2. the same id with a *different* content hash is refused with a named conflict, because
   returning a snapshot built from other inputs would be worse than failing;
3. the conflict carries a structured `issues` entry, so a refusal is explained rather
   than silently empty.

The tests use a real SQLAlchemy session over SQLite with only the tables this function
touches, so they exercise the repository's own SQL rather than a mock.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    DatasetArtifactRecord,
    DatasetSnapshotRecord,
    DatasetSpecRecord,
)
from eurogas_nexus.db.repositories.research import (
    DatasetSnapshotConflict,
    persist_dataset_snapshot,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    for model in (DatasetSpecRecord, DatasetSnapshotRecord, DatasetArtifactRecord):
        model.__table__.create(engine)
    with Session(engine) as active:
        yield active
    engine.dispose()


def _metadata(content_hash: str = "hash-a") -> dict:
    return {
        "dataset_snapshot_id": "dataset-snapshot-abc-spec-1",
        "dataset_spec_id": "spec-1",
        "dataset_spec_version": "spec-1@dataset-spec/v1@deadbeef",
        "ontology_version": "energy-ontology/v1",
        "source_cutoff_utc": "2026-09-01T00:00:00Z",
        "row_count": 10,
        "column_count": 3,
        "quality_report": {"coverage": 0.0, "temporal_integrity": "TEMPORAL_APPROXIMATE"},
        "content_hash": content_hash,
        "entitlement_envelope": {"export_policy": "EXPORT_RESTRICTED"},
    }


def _artifacts() -> list[dict[str, str]]:
    return [
        {
            "artifact_id": "artifact:parquet:deadbeef",
            "format": "parquet",
            "artifact_path": "dataset-snapshot-abc-spec-1/dataset.parquet",
            "sha256": "0" * 64,
        }
    ]


def test_the_first_build_creates_the_snapshot(session: Session) -> None:
    row, created = persist_dataset_snapshot(
        session, metadata=_metadata(), dependencies=[], issues=[], artifacts=_artifacts()
    )
    assert created is True
    assert row.dataset_snapshot_id == "dataset-snapshot-abc-spec-1"


def test_rebuilding_identical_content_reuses_the_stored_snapshot(session: Session) -> None:
    """The regression: this used to raise IntegrityError on the primary key."""

    first, created_first = persist_dataset_snapshot(
        session, metadata=_metadata(), dependencies=[], issues=[], artifacts=_artifacts()
    )
    second, created_second = persist_dataset_snapshot(
        session, metadata=_metadata(), dependencies=[], issues=[], artifacts=_artifacts()
    )

    assert created_first is True
    assert created_second is False, "a rebuild of identical content must not report a new snapshot"
    assert second.dataset_snapshot_id == first.dataset_snapshot_id
    assert second.content_hash == first.content_hash

    stored = session.query(DatasetSnapshotRecord).all()
    assert len(stored) == 1, (
        f"the rebuild stored {len(stored)} snapshots for one content-addressed id; the "
        "primary key collision must resolve to the existing row, not add another"
    )


def test_the_same_id_with_different_content_is_a_named_conflict(session: Session) -> None:
    """Reusing an id for other bytes must fail loudly, not return the wrong snapshot."""

    persist_dataset_snapshot(
        session, metadata=_metadata("hash-a"), dependencies=[], issues=[], artifacts=_artifacts()
    )
    with pytest.raises(DatasetSnapshotConflict) as excinfo:
        persist_dataset_snapshot(
            session,
            metadata=_metadata("hash-b"),
            dependencies=[],
            issues=[],
            artifacts=_artifacts(),
        )

    message = str(excinfo.value)
    assert "hash-a" in message and "hash-b" in message, (
        f"the conflict does not name both hashes, so it cannot be diagnosed: {message!r}"
    )
    assert "dataset-snapshot-abc-spec-1" in message


def test_repeated_builds_stay_stable_over_many_attempts(session: Session) -> None:
    """Idempotence must not degrade after the first reuse."""

    created_flags = [
        persist_dataset_snapshot(
            session, metadata=_metadata(), dependencies=[], issues=[], artifacts=_artifacts()
        )[1]
        for _ in range(5)
    ]
    assert created_flags == [True, False, False, False, False]
    assert session.query(DatasetSnapshotRecord).count() == 1


def test_a_conflict_refusal_carries_structured_issues() -> None:
    """The panel renders `issues`; a conflict must therefore populate it.

    This asserts the shape the client reads (`detail.issues`), because the original
    complaint was an empty panel rather than a wrong message.
    """

    from eurogas_nexus.api.routes.public.research_data import _snapshot_conflict_error

    error = _snapshot_conflict_error("duplicate key value violates unique constraint")
    assert error.status_code == 409
    detail = error.detail
    assert isinstance(detail, dict)
    assert detail["error"] == "dataset_snapshot_conflict"

    issues = detail["issues"]
    assert isinstance(issues, list) and issues, "a refusal with no issues renders an empty panel"
    assert issues[0]["field"] == "dataset_spec"
    assert issues[0]["code"] == "dataset_snapshot_conflict"
    assert "duplicate key" in issues[0]["message"]


def test_integrity_detail_extracts_the_constraint_sentence() -> None:
    """A driver error must be reduced to its explanation, without echoing row values."""

    from eurogas_nexus.api.routes.public.research_data import _integrity_detail

    class _Orig(Exception):
        pass

    class _Wrapped(Exception):
        def __init__(self) -> None:
            super().__init__("(pg8000.dbapi.IntegrityError) (wrapped)")
            self.orig = _Orig(
                "{'C': '23505', 'M': 'duplicate key value violates unique constraint "
                "\"dataset_snapshots_pkey\"', 't': 'dataset_snapshots'}"
            )

    detail = _integrity_detail(_Wrapped())
    assert detail == 'duplicate key value violates unique constraint "dataset_snapshots_pkey"'
    assert "parameters" not in detail.lower()
