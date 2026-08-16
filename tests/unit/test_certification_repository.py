"""Provider certification repository tests."""

from unittest.mock import MagicMock

from eurogas_nexus.db.repositories.certification import (
    latest_certification,
    list_certifications,
    upsert_provider_certification,
)

REQUIRED_CHECKS = ["simulated_shape_match", "live_sample_validation"]


def _session_with_existing_none() -> MagicMock:
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    return session


def test_upsert_provider_certification_validates_persists_and_audits() -> None:
    session = _session_with_existing_none()

    result = upsert_provider_certification(
        session,
        source_system="EEX",
        stage="live_validated",
        checks=REQUIRED_CHECKS,
        evidence={"reference": "eex-replay-2026-07"},
        evaluated_by="ops-user",
        note="first live gate",
    )

    assert result["source_system"] == "EEX"
    assert result["stage"] == "live_validated"
    assert result["evaluated_by"] == "ops-user"
    # certification row first, then the audit event
    assert session.add.call_count == 2
    record = session.add.call_args_list[0].args[0]
    assert record.certification_id.startswith("cert-")
    # audit helper flush + final flush
    assert session.flush.call_count == 2


def test_upsert_replaces_existing_certification_in_place() -> None:
    session = MagicMock()
    existing = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = existing

    upsert_provider_certification(
        session,
        source_system="EEX",
        stage="simulation_matched",
        checks=["credential_verified"],
        evidence={},
        evaluated_by="ops-user",
    )

    assert session.add.call_count == 1  # audit event only
    assert existing.stage == "simulation_matched"
    assert existing.checks == ["credential_verified"]


def test_upsert_rejects_invalid_stage() -> None:
    import pytest

    session = MagicMock()
    with pytest.raises(ValueError):
        upsert_provider_certification(
            session,
            source_system="EEX",
            stage="blessed",
            checks=[],
            evidence={},
            evaluated_by="ops-user",
        )


def test_latest_certification_and_list_payloads() -> None:
    session = MagicMock()
    row = MagicMock()
    row.certification_id = "cert-1"
    row.source_system = "EEX"
    row.stage = "live_validated"
    row.checks = REQUIRED_CHECKS
    row.evidence = {"reference": "eex-replay"}
    row.evaluated_by = "ops-user"
    row.note = None
    row.evaluated_at_utc = MagicMock()
    row.evaluated_at_utc.isoformat.return_value = "2026-07-22T10:00:00+00:00"
    session.query.return_value.filter.return_value.first.return_value = row

    latest = latest_certification(session, "EEX")

    assert latest["stage"] == "live_validated"
    assert latest["checks"] == REQUIRED_CHECKS

    session.query.return_value.order_by.return_value.all.return_value = [row]
    assert list_certifications(session) == [latest]
