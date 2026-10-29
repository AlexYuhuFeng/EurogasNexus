"""Explicit EEX NGP operator-CLI wiring tests (RFC0006 stage C).

These tests never contact EEX. They exercise the actual ``main()`` gate order,
explicit source selection, isolated EEX session and safe failure reporting with
local SQLite sessions and stubbed transport/persistence seams.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "ingest_public_sources.py"
)
FIRST_RECEIPT = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)
HEADER = "Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let"
ROW_FINAL = "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"
ROW_FINAL_SECOND = "30/05/2026;32.100;900.0;Final NGP;30/05/2026 14:30"


def _load_script():
    spec = importlib.util.spec_from_file_location("ingest_public_sources", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sqlite_session_factory(tmp_path):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from eurogas_nexus.db.base import Base

    db_path = tmp_path / "eex-cli-gates.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)

    # pysqlite otherwise emits its own implicit BEGIN/COMMIT around DDL and
    # SAVEPOINT, which releases savepoints outside SQLAlchemy's transaction and
    # can persist rows even when the caller rolls back.  The documented
    # explicit-transaction recipe keeps the fixture faithful to PostgreSQL.
    @event.listens_for(engine, "connect")
    def _disable_pysqlite_implicit_transactions(
        dbapi_connection, connection_record
    ) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _emit_explicit_begin(connection) -> None:
        connection.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _allow_eex_certification(engine) -> None:
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.repositories.certification import upsert_provider_certification

    with Session(engine) as session:
        upsert_provider_certification(
            session,
            source_system="EEX",
            stage="live_validated",
            checks=["simulated_shape_match", "live_sample_validation"],
            evidence={"live_test": "passed"},
            evaluated_by="operator",
            dataset="ttf-ngp-15min",
        )
        session.commit()


def _stub_capture(rows: tuple[str, ...] = (ROW_FINAL,)):
    from eurogas_nexus.ingestion.eex_public_download import (
        OFFICIAL_SOURCE_URL,
        EexPublicCapture,
    )

    body = ("\ufeff" + HEADER + "\r\n" + "\r\n".join(rows) + "\r\n").encode("utf-8")
    return EexPublicCapture(
        raw_bytes=body,
        source_url=OFFICIAL_SOURCE_URL,
        final_url=OFFICIAL_SOURCE_URL,
        retrieved_at_utc=FIRST_RECEIPT,
        content_type="text/csv",
        content_encoding="identity",
        status_code=200,
        http_attempts=1,
        redirect_count=0,
    )


class _RecordingHttpClient:
    instances = []

    def __init__(self, **kwargs) -> None:
        self.calls = []
        _RecordingHttpClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("unexpected live HTTP fetch")


def _install_main_runtime(script, monkeypatch, engine, session_factory) -> None:
    monkeypatch.setattr(
        script, "resolve_database_url", lambda: "sqlite+pysqlite:///eex-cli-test"
    )
    monkeypatch.setattr(script, "get_engine", lambda database_url: engine)
    monkeypatch.setattr(
        script, "create_session_factory", lambda active_engine: session_factory
    )
    _RecordingHttpClient.instances.clear()
    monkeypatch.setattr(script.httpx, "Client", _RecordingHttpClient)


def test_selection_expands_all_without_implicit_eex_and_preserves_explicit_route():
    script = _load_script()

    assert script._resolve_selected_sources([]) == set(script.DEFAULT_SOURCE_SELECTION)
    all_only = script._resolve_selected_sources(["all"])
    assert all_only == set(script.DEFAULT_SOURCE_SELECTION)
    assert "eex-ngp" not in all_only
    assert script._resolve_selected_sources(["all", "eex-ngp"]) == (
        set(script.DEFAULT_SOURCE_SELECTION) | {"eex-ngp"}
    )
    assert script._resolve_selected_sources(["eex-ngp"]) == {"eex-ngp"}


def test_eex_gate_family_runtime_id_and_certification_requirement_are_registered():
    script = _load_script()

    assert "EEX" in script.CERTIFICATION_REQUIRED_SOURCES
    assert script.SOURCE_RUNTIME_ID_BY_FAMILY["EEX"] == "src-eex"


@pytest.mark.parametrize(
    ("source_name", "expected_source_id"),
    [
        ("ECB", "src-ecb"),
        ("ENTSOG", "src-entsog"),
        ("ENTSOG-capacity", "src-entsog"),
        ("ENTSOG-reference", "src-entsog"),
        ("GIE-AGSI", "src-gie"),
        ("GIE-ALSI", "src-gie"),
        ("EEX-NGP", "src-eex"),
        ("UNLISTED-SOURCE", ""),
    ],
)
def test_record_run_persists_only_declared_source_ids(
    tmp_path, source_name, expected_source_id
) -> None:
    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)
    started = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)
    run_id = f"run-alias-{source_name.lower()}"

    with session_factory() as session:
        script._record_run(
            session,
            source_name,
            "failed",
            started,
            0,
            "fixture",
            run_id=run_id,
        )
        session.commit()

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import IngestionRunRecord

    with Session(engine) as session:
        run = session.get(IngestionRunRecord, run_id)
        assert run is not None
        assert run.source_name == source_name
        assert run.source_id == expected_source_id
        # Only EEX NGP has a declared dataset; every other run stays blank.
        assert run.dataset == (
            "ttf-ngp-15min" if source_name == "EEX-NGP" else ""
        )


def test_record_run_stamps_known_eex_dataset_and_preserves_legacy_rows_and_audits(
    tmp_path,
) -> None:
    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)
    started = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import (
        AuditEventRecord,
        IngestionRunRecord,
    )
    from eurogas_nexus.db.repositories.audit import record_audit_event

    with Session(engine) as session:
        session.add(
            IngestionRunRecord(
                run_id="run-legacy-eex",
                source_name="EEX-NGP",
                source_id="",
                dataset="",
                status="failed",
                started_at_utc=started,
                finished_at_utc=started,
                notes="legacy failure",
            )
        )
        record_audit_event(
            session,
            event_type="ingestion",
            principal="operator",
            action="legacy_ingest",
            resource="source:EEX-NGP",
            outcome="failed",
            severity="warning",
            detail="legacy audit detail",
            now_utc=started,
        )
        session.commit()

    with Session(engine) as session:
        script._record_run(
            session,
            "EEX-NGP",
            "succeeded",
            started,
            2,
            script.EEX_NGP_SOURCE_REFERENCE,
            run_id="run-new-eex",
        )
        session.commit()

    with Session(engine) as session:
        legacy = session.get(IngestionRunRecord, "run-legacy-eex")
        assert legacy is not None
        assert legacy.source_name == "EEX-NGP"
        assert legacy.source_id == ""
        assert legacy.dataset == ""
        assert legacy.status == "failed"
        assert legacy.notes == "legacy failure"

        current = session.get(IngestionRunRecord, "run-new-eex")
        assert current is not None
        assert current.source_name == "EEX-NGP"
        assert current.source_id == "src-eex"
        assert current.dataset == "ttf-ngp-15min"
        assert current.status == "succeeded"

        audits = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.resource == "source:EEX-NGP")
            .all()
        )
        assert len(audits) == 2
        legacy_audit = next(audit for audit in audits if audit.action == "legacy_ingest")
        assert legacy_audit.outcome == "failed"
        assert legacy_audit.detail == "legacy audit detail"
        current_audit = next(
            audit for audit in audits if audit.action == "public_source_ingest"
        )
        assert current_audit.outcome == "succeeded"


def test_gate_blocked_eex_is_structured_failure_audited_and_never_fetches(
    tmp_path, monkeypatch, capsys
) -> None:
    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)
    _install_main_runtime(script, monkeypatch, engine, session_factory)

    monkeypatch.setattr(
        script,
        "fetch_eex_public_capture",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("EEX fetch must not run")),
    )
    monkeypatch.setattr(
        sys, "argv", ["ingest_public_sources.py", "--source", "eex-ngp", "--json"]
    )

    result = script.main()

    assert result == 1
    assert _RecordingHttpClient.instances
    assert all(client.calls == [] for client in _RecordingHttpClient.instances)
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["failures"] == [
        {"source": "EEX-NGP", "code": "eex_gate_blocked"}
    ]
    assert payload["sources"]["EEX-NGP"] == {
        "records": 0,
        "status": "failed",
        "code": "eex_gate_blocked",
    }
    assert any(
        "certification:certification_stage_not_live_validated" in warning
        for warning in payload["warnings"]
    )

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import (
        AuditEventRecord,
        IngestionRunRecord,
        ProviderCertificationRecord,
        SourceRuntimeStateRecord,
    )

    with Session(engine) as session:
        runs = session.query(IngestionRunRecord).all()
        assert [run.source_name for run in runs] == ["EEX-NGP"]
        assert [run.status for run in runs] == ["failed"]
        assert "certification:" in runs[0].notes
        audits = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.resource == "source:EEX-NGP")
            .all()
        )
        assert [audit.outcome for audit in audits] == ["failed"]
        # The gate only reads: no activation or certification override is written.
        assert session.query(ProviderCertificationRecord).count() == 0
        assert session.query(SourceRuntimeStateRecord).count() == 0


def test_allowed_stub_capture_passes_calendar_run_id_and_limit_without_a_key(
    tmp_path, monkeypatch, capsys
) -> None:
    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)
    _allow_eex_certification(engine)
    _install_main_runtime(script, monkeypatch, engine, session_factory)

    capture = _stub_capture()
    fetch_calls = []

    def fake_fetch(**kwargs):
        fetch_calls.append(kwargs)
        return capture

    captured = {}

    def fake_persist(
        session,
        *,
        capture,
        gas_day_calendar_contract,
        run_id,
        max_records,
    ):
        captured.update(
            {
                "session": session,
                "capture": capture,
                "calendar": gas_day_calendar_contract,
                "run_id": run_id,
                "max_records": max_records,
            }
        )
        return {
            "records": 2,
            "received_records": 2,
            "skipped_records": 0,
            "archived_pages": 1,
            "archived": 1,
            "archive_id": "raw-test",
            "inserted": 2,
            "unchanged": 0,
            "duplicates": 0,
        }

    monkeypatch.setattr(script, "fetch_eex_public_capture", fake_fetch)
    monkeypatch.setattr(script, "persist_eex_ngp_capture", fake_persist)
    monkeypatch.setattr(
        script,
        "_resolve_gie_api_key",
        lambda session_factory: (_ for _ in ()).throw(
            AssertionError("no GIE key path for EEX")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_public_sources.py",
            "--source",
            "eex-ngp",
            "--limit",
            "7",
            "--json",
        ],
    )

    result = script.main()

    assert result == 0
    assert fetch_calls == [{}]  # fixed official transport, no URL/key argument
    assert captured["capture"] is capture
    assert captured["max_records"] == 7
    assert captured["calendar"].calendar_id == "EU-CAM-UTC-2025"
    evidence = captured["calendar"].evidence
    assert "Index Description v25 sections 1 and 2.5" in evidence
    assert "Index_Description_v25_clean.pdf" in evidence
    assert "Contract Specifications 0105a section 1.2.3" in evidence
    assert "20261002_EEX_Contract_Spezifications_0105a_E_FINAL.pdf" in evidence
    assert "06:00 Europe/Berlin" in evidence
    assert "does not certify rights" in evidence

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    detail = payload["sources"]["EEX-NGP"]
    assert detail["status"] == "succeeded"
    assert detail["records"] == 2
    assert detail["received_records"] == 2
    assert detail["skipped_records"] == 0
    assert detail["archived_pages"] == 1
    assert detail["archive_id"] == "raw-test"
    assert detail["inserted"] == 2
    assert detail["unchanged"] == 0
    assert detail["raw_sha256"] == capture.raw_sha256

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import AuditEventRecord, IngestionRunRecord

    with Session(engine) as session:
        runs = session.query(IngestionRunRecord).all()
        assert len(runs) == 1
        assert runs[0].run_id == captured["run_id"]
        assert runs[0].source_name == "EEX-NGP"
        assert runs[0].status == "succeeded"
        audits = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.resource == "source:EEX-NGP")
            .all()
        )
        assert [audit.outcome for audit in audits] == ["succeeded"]
    assert all(client.calls == [] for client in _RecordingHttpClient.instances)


def test_actual_helper_record_limit_refusal_reports_retained_archive_after_commit(
    tmp_path, monkeypatch, capsys
) -> None:
    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)
    _allow_eex_certification(engine)
    _install_main_runtime(script, monkeypatch, engine, session_factory)
    capture = _stub_capture((ROW_FINAL, ROW_FINAL_SECOND))

    monkeypatch.setattr(script, "fetch_eex_public_capture", lambda **kwargs: capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_public_sources.py",
            "--source",
            "eex-ngp",
            "--limit",
            "1",
            "--json",
        ],
    )

    result = script.main()

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    detail = payload["sources"]["EEX-NGP"]
    assert detail["status"] == "failed"
    assert detail["code"] == "eex_ngp_record_limit"
    assert detail["archived_pages"] == 1
    archive_id = detail["archive_id"]
    assert isinstance(archive_id, str) and archive_id.startswith("raw-")

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import (
        AuditEventRecord,
        IngestionRunRecord,
        RawPayloadArchiveRecord,
    )

    with Session(engine) as session:
        archives = session.query(RawPayloadArchiveRecord).all()
        assert [archive.archive_id for archive in archives] == [archive_id]
        run = session.query(IngestionRunRecord).one()
        assert run.source_name == "EEX-NGP"
        assert run.source_id == "src-eex"
        assert run.dataset == "ttf-ngp-15min"
        assert run.status == "failed"
        assert f"eex:{detail['code']}" in run.notes
        audits = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.resource == "source:EEX-NGP")
            .all()
        )
        assert [audit.outcome for audit in audits] == ["failed"]


def test_commit_failure_cannot_claim_raw_retention(
    tmp_path, monkeypatch, capsys
) -> None:
    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)
    _allow_eex_certification(engine)
    _install_main_runtime(script, monkeypatch, engine, session_factory)
    capture = _stub_capture((ROW_FINAL, ROW_FINAL_SECOND))

    monkeypatch.setattr(script, "fetch_eex_public_capture", lambda **kwargs: capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_public_sources.py",
            "--source",
            "eex-ngp",
            "--limit",
            "1",
            "--json",
        ],
    )

    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    real_record_run = script._record_run
    armed = {"value": False}

    def record_then_arm(session, *args, **kwargs):
        real_record_run(session, *args, **kwargs)
        armed["value"] = True

    real_commit = Session.commit

    def refuse_commit(session):
        if armed["value"]:
            raise SQLAlchemyError("simulated commit failure")
        return real_commit(session)

    monkeypatch.setattr(script, "_record_run", record_then_arm)
    monkeypatch.setattr(Session, "commit", refuse_commit)

    result = script.main()

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    detail = payload["sources"]["EEX-NGP"]
    assert detail["status"] == "failed"
    assert detail["code"] == "eex_ngp_record_limit"
    # The helper annotated a retention candidate, but the commit failed, so the
    # CLI must report the count as unknown and no retained archive id.
    assert detail["archived_pages"] is None
    assert "archive_id" not in detail

    from eurogas_nexus.db.models import RawPayloadArchiveRecord

    with Session(engine) as session:
        assert session.query(RawPayloadArchiveRecord).count() == 0


def test_eex_fetch_failure_is_safe_nonzero_and_keeps_independent_provider(
    tmp_path, monkeypatch, capsys
) -> None:
    script = _load_script()
    engine, session_factory = _sqlite_session_factory(tmp_path)
    _install_main_runtime(script, monkeypatch, engine, session_factory)

    from eurogas_nexus.db.models import IngestionRunRecord
    from eurogas_nexus.ingestion.eex_public_download import EexPublicDownloadError

    monkeypatch.setattr(script, "_gate_blockers", lambda session, source: [])
    monkeypatch.setattr(script, "_resolve_gie_api_key", lambda factory: None)

    def fake_entsog(
        client,
        session,
        *,
        route,
        args,
        started,
        report,
        point_directions=None,
    ):
        session.merge(
            IngestionRunRecord(
                run_id="run-independent-provider",
                source_name="ENTSOG",
                status="succeeded",
                started_at_utc=started,
                finished_at_utc=started,
                notes="independent provider fixture committed before EEX",
            )
        )
        report["sources"]["ENTSOG"] = {"records": 3}

    def failing_fetch(**kwargs):
        raise EexPublicDownloadError("timeout", "safe synthetic transport refusal")

    monkeypatch.setattr(script, "_ingest_entsog_source", fake_entsog)
    monkeypatch.setattr(script, "fetch_eex_public_capture", failing_fetch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_public_sources.py",
            "--source",
            "entsog",
            "--source",
            "eex-ngp",
            "--json",
        ],
    )

    result = script.main()

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["sources"]["ENTSOG"] == {"records": 3}
    assert payload["sources"]["EEX-NGP"]["status"] == "failed"
    assert payload["sources"]["EEX-NGP"]["code"] == "timeout"
    # A transport refusal happens before any raw bytes can be archived.
    assert payload["sources"]["EEX-NGP"]["archived_pages"] == 0
    assert "archive_id" not in payload["sources"]["EEX-NGP"]
    assert payload["failures"] == [{"source": "EEX-NGP", "code": "timeout"}]
    assert any("no synthetic data" in warning for warning in payload["warnings"])
    assert "safe synthetic transport refusal" not in json.dumps(payload)

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        independent = session.get(IngestionRunRecord, "run-independent-provider")
        assert independent is not None
        assert independent.status == "succeeded"
        eex_run = (
            session.query(IngestionRunRecord)
            .filter(IngestionRunRecord.source_name == "EEX-NGP")
            .one()
        )
        assert eex_run.status == "failed"
        assert "eex:timeout" in eex_run.notes


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_eex_limit_is_refused_before_database_or_fetch(
    monkeypatch, capsys, limit
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "resolve_database_url",
        lambda: (_ for _ in ()).throw(AssertionError("database must not be resolved")),
    )
    monkeypatch.setattr(
        script,
        "fetch_eex_public_capture",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("EEX fetch must not run")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_public_sources.py",
            "--source",
            "eex-ngp",
            "--limit",
            str(limit),
            "--json",
        ],
    )

    result = script.main()

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["failures"] == [
        {"source": "EEX-NGP", "code": "eex_ngp_invalid_record_limit"}
    ]
    assert payload["sources"] == {}
    assert any("no download" in warning for warning in payload["warnings"])


@pytest.mark.parametrize("max_records", [0, -1, True, False, 1.5, "10", None])
def test_helper_rejects_invalid_record_limit_before_any_write(max_records) -> None:
    from eurogas_nexus.ingestion import eex_ngp_ingestion as ingestion

    session = MagicMock()

    with pytest.raises(ingestion.EexNgpInputError) as caught:
        ingestion.persist_eex_ngp_capture(
            session,
            capture=object(),
            gas_day_calendar_contract=object(),
            run_id="run-invalid-limit",
            max_records=max_records,
        )

    assert caught.value.code == "eex_ngp_invalid_input"
    assert session.mock_calls == []


def test_helper_default_record_limit_is_10000() -> None:
    from eurogas_nexus.ingestion import eex_ngp_ingestion as ingestion

    default = inspect.signature(
        ingestion.persist_eex_ngp_capture
    ).parameters["max_records"].default
    assert default == 10000
    assert type(default) is int
