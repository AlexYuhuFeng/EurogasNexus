"""Focused tests for the S1b explicit legacy contract-revision capture.

`docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md` sections 3.1 and 9: the
repository capture/read helpers are exercised against a throw-away SQLite
database holding the real model schema, so capture, idempotency, per-contract
numbering, snapshot preservation across later source-row edits, stale
identity-map refresh, capture-time validation, ambiguous-mapping rejection,
audit-writer failure rollback, integrity verification and the contract FK
restriction are executed rather than inspected. No route, startup wiring or
migration runs here; the migration DDL has its own test and PostgreSQL
concurrency runs in the opt-in CI integration job.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, tzinfo

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    UpstreamContractRevisionRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.audit import list_audit_events_for_resource
from eurogas_nexus.db.repositories.route_cost import (
    CONTRACT_REVISION_ALREADY_CAPTURED,
    CONTRACT_REVISION_CAPTURED,
    CONTRACT_REVISION_MAPPING_AMBIGUOUS,
    CONTRACT_REVISION_REJECTED,
    ContractRevisionCaptureResult,
    ContractRevisionPersistenceError,
    capture_upstream_contract_revision,
    get_upstream_contract_revision,
    list_upstream_contract_revisions,
    upsert_upstream_contract,
)
from eurogas_nexus.domain.route_cost.contract_revision import (
    CAPTURE_ORIGIN_LEGACY_CAPTURE,
    LEGACY_NOTES_NOT_STRUCTURED,
    map_legacy_contract_payload,
)

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_CONTRACT_ID = "ttf-supply-2025"


def _create_engine(url: str) -> Engine:
    """A SQLite engine with the real model schema and foreign keys enforced."""

    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record) -> None:
        dbapi_connection.execute("pragma foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def session():
    """A throw-away SQLite schema with foreign keys enforced like PostgreSQL."""

    with Session(_create_engine("sqlite+pysqlite:///:memory:")) as session:
        yield session


def _contract_payload(**overrides: object) -> dict[str, object]:
    """Return a full legacy contract payload in the repository upsert shape."""

    payload: dict[str, object] = {
        "contract_id": _CONTRACT_ID,
        "contract_name": "TTF supply 2025",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2025+",
        "delivery_quantity_mwh_per_day": 125.5,
        "contract_price_gbp_mwh": 29.75,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2.0,
        "nomination_tolerance_pct": 1.0,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
        "annual_financing_rate_pct": 6.0,
        "owned_entry_capacity_mwh_per_day": None,
        "owned_exit_capacity_mwh_per_day": None,
        "allowed_exit_points": ["NBP", "TTF"],
        "eligible_sale_modes": ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE"],
        "notes": json.dumps(
            {
                "operator_notes": "operator draft decision support",
                "variable_cost_gbp_mwh": 0.75,
            },
            sort_keys=True,
        ),
    }
    payload.update(overrides)
    return payload


def _seed_contract(session: Session, **overrides: object) -> None:
    """Persist the legacy contract row the capture reads."""

    upsert_upstream_contract(session, _contract_payload(**overrides))
    session.commit()


def _capture(
    session: Session,
    *,
    recorded_by: str = "trader-a",
    recorded_at_utc: datetime = _NOW,
) -> ContractRevisionCaptureResult:
    return capture_upstream_contract_revision(
        session,
        _CONTRACT_ID,
        recorded_by=recorded_by,
        recorded_at_utc=recorded_at_utc,
    )


def _as_utc(value: datetime) -> datetime:
    """Attach UTC to a naive datetime: SQLite fixtures drop tzinfo, PG keeps it."""

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def test_capture_persists_snapshot_display_evidence_and_one_audit_row(session) -> None:
    _seed_contract(session)
    result = _capture(session)

    assert result.outcome == CONTRACT_REVISION_CAPTURED
    assert result.created is True
    revision = result.revision
    assert revision is not None
    assert revision.revision_number == 1
    assert revision.capture_origin == CAPTURE_ORIGIN_LEGACY_CAPTURE
    assert revision.recorded_by == "trader-a"
    assert _as_utc(revision.recorded_at_utc) == _NOW

    expected = map_legacy_contract_payload(_contract_payload()).economic_snapshot
    assert revision.snapshot_json == expected.canonical_json()
    assert revision.content_hash == expected.content_hash()
    assert revision.content_hash.startswith("sha256:")
    assert json.loads(revision.display_metadata_json) == {
        "contract_name": "TTF supply 2025",
        "operator_notes": _contract_payload()["notes"],
    }

    session.commit()

    payload = get_upstream_contract_revision(session, revision.contract_revision_id)
    assert payload["contract_id"] == _CONTRACT_ID
    assert payload["revision_number"] == 1
    assert payload["capture_origin"] == CAPTURE_ORIGIN_LEGACY_CAPTURE
    assert payload["recorded_by"] == "trader-a"
    assert payload["snapshot"]["contract_price_gbp_mwh"] == "29.75"
    assert payload["snapshot"]["variable_cost_gbp_mwh"] == "0.75"
    assert payload["snapshot"]["payment_terms"] is None
    assert payload["display_metadata"]["contract_name"] == "TTF supply 2025"

    events = list_audit_events_for_resource(
        session, f"upstream_contract:{_CONTRACT_ID}"
    )
    assert len(events) == 1
    assert events[0]["action"] == "route_cost.contract.capture_revision"
    assert events[0]["principal"] == "trader-a"
    assert events[0]["outcome"] == "captured"
    assert _as_utc(datetime.fromisoformat(events[0]["event_ts_utc"])) == _NOW


def test_repeat_capture_is_idempotent_and_retains_the_original_recorder(session) -> None:
    _seed_contract(session)
    first = _capture(session)
    session.commit()
    revision_id = first.revision.contract_revision_id

    repeat = _capture(
        session,
        recorded_by="trader-b",
        recorded_at_utc=_NOW + timedelta(hours=3),
    )
    session.commit()

    assert repeat.outcome == CONTRACT_REVISION_ALREADY_CAPTURED
    assert repeat.created is False
    assert repeat.revision is not None
    assert repeat.revision.contract_revision_id == revision_id
    assert repeat.revision.revision_number == 1
    assert repeat.revision.recorded_by == "trader-a"
    assert _as_utc(repeat.revision.recorded_at_utc) == _NOW
    assert session.query(UpstreamContractRevisionRecord).count() == 1
    # A repeat is not a new capture event: it must not add a second audit row.
    assert session.query(AuditEventRecord).count() == 1


def test_changed_source_row_captures_the_next_revision_and_keeps_the_first(session) -> None:
    _seed_contract(session)
    first = _capture(session)
    session.commit()
    first_id = first.revision.contract_revision_id
    first_hash = first.revision.content_hash

    _seed_contract(session, contract_price_gbp_mwh=31.5)
    second = _capture(
        session,
        recorded_by="trader-b",
        recorded_at_utc=_NOW + timedelta(days=1),
    )
    session.commit()

    assert second.outcome == CONTRACT_REVISION_CAPTURED
    assert second.revision.revision_number == 2
    assert second.revision.content_hash != first_hash

    original = get_upstream_contract_revision(session, first_id)
    assert original["snapshot"]["contract_price_gbp_mwh"] == "29.75"
    assert original["recorded_by"] == "trader-a"
    listed = list_upstream_contract_revisions(session, _CONTRACT_ID)
    assert [item["revision_number"] for item in listed] == [1, 2]
    assert listed[1]["snapshot"]["contract_price_gbp_mwh"] == "31.5"


def test_source_row_edits_after_capture_do_not_change_the_captured_snapshot(session) -> None:
    _seed_contract(session)
    result = _capture(session)
    session.commit()
    revision_id = result.revision.contract_revision_id

    # The legacy upsert overwrites the mutable row in place; the captured
    # revision is evidence of what the row contained at capture time and keeps
    # its own price and display name.
    upsert_upstream_contract(
        session,
        _contract_payload(contract_name="Renamed TTF supply", contract_price_gbp_mwh=99.0),
    )
    session.commit()

    payload = get_upstream_contract_revision(session, revision_id)
    assert payload["snapshot"]["contract_price_gbp_mwh"] == "29.75"
    assert payload["display_metadata"]["contract_name"] == "TTF supply 2025"


def test_capture_refreshes_a_stale_identity_map_row_before_capturing(tmp_path) -> None:
    """A row committed after this session loaded it must not be captured stale."""

    engine = _create_engine(f"sqlite+pysqlite:///{tmp_path / 'stale-contract.sqlite'}")
    try:
        with Session(engine) as setup:
            upsert_upstream_contract(setup, _contract_payload())
            setup.commit()

        with Session(engine, expire_on_commit=False) as capture_session:
            stale_row = capture_session.get(UpstreamResourceContractRecord, _CONTRACT_ID)
            assert stale_row is not None
            assert stale_row.contract_price_gbp_mwh == pytest.approx(29.75)
            # End the read transaction without expiring the instance: the
            # identity map now holds the row the next transaction replaces.
            capture_session.commit()

            with Session(engine) as writer:
                writer.execute(
                    text(
                        "UPDATE upstream_resource_contracts SET"
                        " contract_price_gbp_mwh = 31.5 WHERE contract_id = :contract_id"
                    ),
                    {"contract_id": _CONTRACT_ID},
                )
                writer.commit()

            result = capture_upstream_contract_revision(
                capture_session,
                _CONTRACT_ID,
                recorded_by="trader-a",
                recorded_at_utc=_NOW,
            )
            capture_session.commit()

        assert result.outcome == CONTRACT_REVISION_CAPTURED
        assert result.revision is not None
        snapshot = json.loads(result.revision.snapshot_json)
        assert snapshot["contract_price_gbp_mwh"] == "31.5"
    finally:
        engine.dispose()


def test_unmappable_legacy_value_is_rejected_and_writes_nothing(session) -> None:
    _seed_contract(
        session,
        notes=json.dumps({"variable_cost_gbp_mwh": "not-a-number"}, sort_keys=True),
    )

    result = _capture(session)

    assert result.outcome == CONTRACT_REVISION_REJECTED
    assert result.revision is None
    assert result.refusal_code == "number_text_invalid"
    assert result.refusal_detail
    assert session.query(UpstreamContractRevisionRecord).count() == 0
    assert session.query(AuditEventRecord).count() == 0
    session.commit()


@pytest.mark.parametrize(
    "malformed_notes",
    ["variable cost 0.75 gbp/mwh", "[]", "17", "null", '"operator notes"'],
)
def test_capture_refuses_ambiguous_stored_notes_even_if_the_caller_commits(
    session, malformed_notes: str
) -> None:
    """Notes edited outside the upsert must refuse the capture, never be guessed.

    The malformed value is written straight to the stored row (bypassing the
    upsert's note sanitising, which would keep it as operator prose), so a row
    the capture never wrote can still be refused. Rejecting every nonempty
    ``mapping_issues`` entry means the ambiguous row writes neither revision nor
    audit row before the caller's commit, and the refusal names the recorded
    issue.
    """

    _seed_contract(session)
    session.execute(
        text(
            "UPDATE upstream_resource_contracts SET notes = :notes"
            " WHERE contract_id = :contract_id"
        ),
        {"notes": malformed_notes, "contract_id": _CONTRACT_ID},
    )
    session.commit()

    result = _capture(session)

    assert result.outcome == CONTRACT_REVISION_REJECTED
    assert result.revision is None
    assert result.refusal_code == CONTRACT_REVISION_MAPPING_AMBIGUOUS
    assert result.refusal_detail is not None
    assert LEGACY_NOTES_NOT_STRUCTURED in result.refusal_detail
    session.commit()

    with Session(session.get_bind()) as observer:
        assert observer.query(UpstreamContractRevisionRecord).count() == 0
        assert observer.query(AuditEventRecord).count() == 0
        assert observer.query(UpstreamResourceContractRecord).count() == 1


def test_capture_refuses_a_contract_row_that_does_not_exist(session) -> None:
    result = capture_upstream_contract_revision(
        session,
        "missing-contract",
        recorded_by="trader-a",
        recorded_at_utc=_NOW,
    )

    assert result.outcome == CONTRACT_REVISION_REJECTED
    assert result.refusal_code == "contract_row_not_found"
    assert session.query(UpstreamContractRevisionRecord).count() == 0
    assert session.query(AuditEventRecord).count() == 0


class _NullOffsetTimezone(tzinfo):
    """A ``tzinfo`` whose ``utcoffset`` is ``None``: aware but without an offset."""

    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None


@pytest.mark.parametrize(
    "capture_time",
    [
        datetime(2026, 10, 1, 9, 0),
        datetime(2026, 10, 1, 9, 0, tzinfo=_NullOffsetTimezone()),
    ],
)
def test_capture_refuses_a_capture_time_without_a_concrete_utc_offset(
    session, capture_time: datetime
) -> None:
    _seed_contract(session)

    with pytest.raises(ContractRevisionPersistenceError) as excinfo:
        _capture(session, recorded_at_utc=capture_time)

    assert excinfo.value.code == "recorded_at_not_utc"
    assert session.query(UpstreamContractRevisionRecord).count() == 0
    assert session.query(AuditEventRecord).count() == 0


def test_rollback_discards_the_revision_and_its_audit_row_together(session) -> None:
    _seed_contract(session)
    result = _capture(session)
    assert result.created is True

    session.rollback()

    assert session.query(UpstreamResourceContractRecord).count() == 1
    assert session.query(UpstreamContractRevisionRecord).count() == 0
    assert session.query(AuditEventRecord).count() == 0


def test_audit_writer_failure_fails_the_capture_and_nothing_persists(
    session, monkeypatch
) -> None:
    _seed_contract(session)
    flushes: dict[str, int] = {}

    def _refuse_audit(writer_session: Session, **_kwargs: object) -> None:
        # The revision is already flushed when the audit writer runs: the
        # refusal below must leave nothing behind after the caller rolls back.
        flushes["visible_revisions"] = writer_session.query(
            UpstreamContractRevisionRecord
        ).count()
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(
        "eurogas_nexus.db.repositories.route_cost.record_audit_event", _refuse_audit
    )

    with pytest.raises(RuntimeError, match="audit store unavailable"):
        _capture(session)

    assert flushes == {"visible_revisions": 1}
    # The caller owns the transaction boundary: rolling back discards the
    # already-flushed revision, so no revision can persist without its audit.
    session.rollback()

    with Session(session.get_bind()) as observer:
        assert observer.query(UpstreamContractRevisionRecord).count() == 0
        assert observer.query(AuditEventRecord).count() == 0
        assert observer.query(UpstreamResourceContractRecord).count() == 1


def test_deleting_a_captured_contract_is_restricted_by_the_foreign_key(session) -> None:
    _seed_contract(session)
    _capture(session)
    session.commit()

    row = session.get(UpstreamResourceContractRecord, _CONTRACT_ID)
    session.delete(row)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    assert session.query(UpstreamContractRevisionRecord).count() == 1


def _tamper(session: Session, revision_id: str, statement: str, **parameters: object) -> None:
    session.execute(text(statement), {"revision_id": revision_id, **parameters})
    session.commit()


def test_read_rejects_a_snapshot_whose_content_hash_no_longer_matches(session) -> None:
    _seed_contract(session)
    revision_id = _capture(session).revision.contract_revision_id
    session.commit()
    _tamper(
        session,
        revision_id,
        "UPDATE upstream_contract_revisions SET snapshot_json ="
        " replace(snapshot_json, '29.75', '39.75') WHERE contract_revision_id = :revision_id",
    )

    with pytest.raises(ContractRevisionPersistenceError) as excinfo:
        get_upstream_contract_revision(session, revision_id)

    assert excinfo.value.code == "contract_revision_hash_mismatch"


def test_read_rejects_a_snapshot_recorded_for_another_contract(session) -> None:
    _seed_contract(session)
    revision_id = _capture(session).revision.contract_revision_id
    session.commit()
    upsert_upstream_contract(
        session, _contract_payload(contract_id="other-supply-2025", contract_name="Other")
    )
    session.commit()
    _tamper(
        session,
        revision_id,
        "UPDATE upstream_contract_revisions SET contract_id = 'other-supply-2025'"
        " WHERE contract_revision_id = :revision_id",
    )

    with pytest.raises(ContractRevisionPersistenceError) as excinfo:
        get_upstream_contract_revision(session, revision_id)

    assert excinfo.value.code == "contract_revision_contract_id_mismatch"


def test_read_rejects_a_tampered_schema_version(session) -> None:
    _seed_contract(session)
    revision_id = _capture(session).revision.contract_revision_id
    session.commit()
    _tamper(
        session,
        revision_id,
        "UPDATE upstream_contract_revisions SET schema_version = 'upstream-contract-revision/v99'"
        " WHERE contract_revision_id = :revision_id",
    )

    with pytest.raises(ContractRevisionPersistenceError) as excinfo:
        get_upstream_contract_revision(session, revision_id)

    assert excinfo.value.code == "contract_revision_schema_version_mismatch"


def test_read_rejects_an_unreviewed_capture_origin(session) -> None:
    _seed_contract(session)
    revision_id = _capture(session).revision.contract_revision_id
    session.commit()
    _tamper(
        session,
        revision_id,
        "UPDATE upstream_contract_revisions SET capture_origin = 'migration_backfill'"
        " WHERE contract_revision_id = :revision_id",
    )

    with pytest.raises(ContractRevisionPersistenceError) as excinfo:
        get_upstream_contract_revision(session, revision_id)

    assert excinfo.value.code == "contract_revision_origin_unknown"


def test_read_of_an_unknown_revision_id_is_reported(session) -> None:
    with pytest.raises(ContractRevisionPersistenceError) as excinfo:
        get_upstream_contract_revision(session, "contract-revision-missing")

    assert excinfo.value.code == "contract_revision_not_found"
