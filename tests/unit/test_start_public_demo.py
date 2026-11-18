"""Start-up of the hosted test/demo server (root Dockerfile): configuration and catch-up."""

from __future__ import annotations

import importlib.util
import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IdentityPrincipalRecord
from eurogas_nexus.db.models.observation import AuditEventRecord

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "start_public_demo.py"


def _load():
    spec = importlib.util.spec_from_file_location("start_public_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _required() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgres://user:placeholder@db.example:24865/defaultdb?sslmode=require",
        "EUROGAS_NEXUS_SECRET_KEY": "1mDk0Q0m9K4pXc2rWb7tLzYvHsAeNfRgUjOiPlMnQ4E=",
        "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD": secrets.token_urlsafe(18),
    }


def test_missing_settings_are_all_named_and_nothing_is_generated():
    start = _load()
    with pytest.raises(start.StartupError) as error:
        start.configure_environment({"EUROGAS_NEXUS_DEV_LOGIN_PASSWORD": "short"})
    message = str(error.value)
    assert "DATABASE_URL" in message
    assert "EUROGAS_NEXUS_SECRET_KEY" in message
    assert "at least" in message or "shorter than 12" in message


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"EUROGAS_NEXUS_ENV": "release"}, "development"),
        ({"EUROGAS_NEXUS_API_PROFILE": "release"}, "demo profile only"),
        ({"DATABASE_URL": "db.example:5432/app"}, "unusable"),
    ],
)
def test_the_demo_refuses_a_release_shape_or_a_bad_url(override, fragment):
    start = _load()
    with pytest.raises(start.StartupError, match=fragment):
        start.configure_environment({**_required(), **override})


def test_platform_uri_and_defaults():
    start = _load()
    environ = _required()
    start.configure_environment(environ)
    assert environ["RUNTIME_STORE_DATABASE_URL"].startswith("postgresql+pg8000://")
    assert ":24865/defaultdb?sslmode=require" in environ["RUNTIME_STORE_DATABASE_URL"]
    assert environ["EUROGAS_NEXUS_API_PROFILE"] == "demo"
    assert environ["EUROGAS_NEXUS_ENV"] == "development"
    assert environ["EUROGAS_NEXUS_DEV_LOGIN_USERNAME"].split(",") == list(start.TESTER_NAMES)
    assert environ["EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED"] == "false"
    # Enough connections for a page's parallel reads, within a 20-connection managed plan
    # beside a catch-up step (1-3).
    pool = int(environ["EUROGAS_NEXUS_DB_POOL_SIZE"]) + int(
        environ["EUROGAS_NEXUS_DB_MAX_OVERFLOW"]
    )
    assert 10 <= pool <= 16
    assert float(environ["EUROGAS_NEXUS_DB_POOL_TIMEOUT"]) >= 10
    # The deployment-token path is closed by an unknown random value, never a default.
    assert len(environ["EUROGAS_NEXUS_PUBLIC_API_TOKEN"]) >= 32
    other = _required()
    start.configure_environment(other)
    assert other["EUROGAS_NEXUS_PUBLIC_API_TOKEN"] != environ["EUROGAS_NEXUS_PUBLIC_API_TOKEN"]


def test_a_model_key_turns_ai_on_and_an_explicit_choice_wins():
    start = _load()
    with_key = {**_required(), "EUROGAS_NEXUS_LLM_API_KEY": "placeholder-not-a-key"}
    start.configure_environment(with_key)
    assert with_key["EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED"] == "true"
    forced_off = {**with_key, "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED": "false"}
    start.configure_environment(forced_off)
    assert forced_off["EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED"] == "false"


def test_testers_cover_every_role_and_job_function():
    from eurogas_nexus.security.capabilities import FunctionalAssignment
    from eurogas_nexus.security.identity import Role

    start = _load()
    roles = {role for row in start.TESTERS for role in row[3]}
    functions = {item for row in start.TESTERS for item in row[4]}
    assert roles == {role.value for role in Role}
    assert functions == {item.value for item in FunctionalAssignment}
    assert len(set(start.TESTER_NAMES)) == len(start.TESTER_NAMES)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_testers_are_created_once_and_a_tester_s_admin_changes_survive_a_restart(session):
    start = _load()
    created, restored = start.ensure_testers(session, reapply=False)
    session.commit()
    assert (created, restored) == (len(start.TESTERS), 0)
    trader = session.query(IdentityPrincipalRecord).filter_by(name="demo.trader").one()
    trader.status = "DISABLED"  # an administrator tester changed it
    session.commit()
    assert start.ensure_testers(session, reapply=False) == (0, 0)
    assert trader.status == "DISABLED"
    assert start.ensure_testers(session, reapply=True) == (0, len(start.TESTERS))
    assert trader.status == "ACTIVE"
    assert trader.data_scopes == ["*"]


def test_seed_marker_drives_seed_once_and_reset(session):
    start = _load()
    assert start.last_seed_token(session) is None
    start.record_seed(session, "", "empty store")
    session.commit()
    assert start.last_seed_token(session) == ""
    start.record_seed(session, "2026-11-16", "reset token changed")
    session.commit()
    assert start.last_seed_token(session) in {"", "2026-11-16"}  # same-second ordering


def test_catch_up_window_is_the_gap_since_the_last_good_round_bounded(session):
    start = _load()
    now = datetime(2026, 11, 16, 9, tzinfo=UTC)
    assert start.catch_up_window_days(session, now, 45) == 45  # never ran: the maximum
    for days_ago, outcome in ((14, "success"), (2, "partial")):
        session.add(
            AuditEventRecord(
                event_id=f"e-{days_ago}", event_type="governance.demo", severity="info",
                principal="demo-refresh", action=start.CATCH_UP_ACTION, resource="public_sources",
                outcome=outcome, detail="", event_ts_utc=now - timedelta(days=days_ago),
                source_system="demo-start", human_review_required=False,
            )
        )
    session.commit()
    assert start.catch_up_window_days(session, now, 45) == 15  # a 2-week pause
    assert start.catch_up_window_days(session, now, 7) == 7
    assert start.catch_up_window_days(session, now + timedelta(days=40), 45) == 45


def test_catch_up_runs_keyless_sources_and_keyed_ones_only_with_their_key():
    start = _load()
    now = datetime(2026, 11, 16, 9, tzinfo=UTC)
    keyless = start.catch_up_steps(5, now, environ={})
    keys = [step.key for step in keyless]
    assert keys[:2] == ["ecb", "entsog"]
    assert {"national-gas-supply", "national-gas-demand", "elexon", "rates-sonia",
            "rates-estr", "rates-sofr", "entsog-umm", "replace-simulated"} <= set(keys)
    assert not {"gie", "eia", "entsoe", "remit-iip", "entsog-history"} & set(keys)
    keyed = start.catch_up_steps(
        15, now, environ={"GIE_API_KEY": "x", "EIA_API_KEY": "x", "ENTSOE_SECURITY_TOKEN": "x"}
    )
    by_key = {step.key: step.command for step in keyed}
    assert {"gie", "eia", "entsoe", "remit-iip"} <= set(by_key)
    # The scheduler's complete-read bounds, a rolling week and the daily reference refresh.
    entsog = by_key["entsog"]
    assert entsog[entsog.index("--entsog-lookback-gas-days") + 1] == "7"
    assert entsog[entsog.index("--entsog-page-size") + 1] == "1000"
    assert entsog[entsog.index("--limit") + 1] == "50000"
    assert "entsog-reference" in entsog and "--entsog-reference-max-age-hours" in entsog
    # Each window: the gap, at least what the scheduler reads, at most the script's limit.
    assert by_key["eia"][-2:] == ["--days", "15"]
    assert by_key["entsoe"][-2:] == ["--days", "7"] and "--commit" in by_key["entsoe"]
    assert by_key["gie"][by_key["gie"].index("--limit") + 1] == "30"
    assert by_key["elexon"][-2:] == ["--days", "7"]
    assert by_key["remit-iip"][-2:] == ["--days", "15"]
    # Older weeks of a 15-day gap: ENTSOG flows in explicit windows of at most a week.
    history = [step.command for step in keyed if step.key == "entsog-history"]
    windows = [(c[c.index("--entsog-from") + 1], c[c.index("--entsog-to") + 1]) for c in history]
    assert windows == [("2026-11-02", "2026-11-09"), ("2026-11-01", "2026-11-02")]
    assert all("entsog-capacity" not in c for c in history)


def test_a_step_that_failed_reads_its_own_gap_again(session):
    start = _load()
    now = datetime(2026, 11, 16, 9, tzinfo=UTC)
    session.add(
        AuditEventRecord(
            event_id="e-partial", event_type="governance.demo", severity="warning",
            principal="demo-refresh", action=start.CATCH_UP_ACTION, resource="public_sources",
            outcome="partial", detail="days=45; ok=ecb,entsog; failed=gie",
            event_ts_utc=now - timedelta(hours=6), source_system="demo-start",
            human_review_required=False,
        )
    )
    session.commit()
    assert start.catch_up_window_days(session, now, 45, "ecb") == 1
    assert start.catch_up_window_days(session, now, 45, "gie") == 45  # never succeeded
    steps = start.catch_up_steps(1, now, environ={"GIE_API_KEY": "x"}, windows={"gie": 45})
    gie = next(step.command for step in steps if step.key == "gie")
    assert gie[gie.index("--limit") + 1] == "45"


def test_step_report_is_one_line_and_a_failure_code_fails_the_step():
    start = _load()
    ok, text = start._report_summary(
        'progress\n{"ok": true, "failures": [], "sources": {"ENTSOG": {"records": 12, '
        '"inserted": 10, "updated": 2}, "ENTSOG-reference": {"records": 0, '
        '"status": "skipped_fresh"}}}'
    )
    assert ok is True and text.startswith("records 12, inserted 10, updated 2")
    assert "ENTSOG-reference fresh" in text
    ok, text = start._report_summary(
        '{"ok": false, "failures": [{"source": "GIE", "code": "source_gate_blocked"}], '
        '"sources": {}}'
    )
    assert ok is False and "source_gate_blocked" in text
    assert start._report_summary("not json") == (None, "")
    # An indented report (ingest_public_sources.py --json) whose list items parse on their own.
    indented = json.dumps({"ok": True, "failures": [], "sources": {"GIE-AGSI": {
        "records": 45, "inserted": 45, "queries": ["agsi;page=1"]}}}, indent=2)
    assert start._report_summary(indented) == (True, "records 45, inserted 45")


def _certify(session, start, *, stage="live_validated", expires_in_days=90, now=None):
    from eurogas_nexus.db.repositories.certification import upsert_provider_certification

    now = now or datetime(2026, 11, 16, 9, tzinfo=UTC)
    upsert_provider_certification(
        session, source_system="ENTSOG", stage=stage,
        checks=["simulated_shape_match", "live_sample_validation", "sample_archived"],
        evidence={"live_test": "passed"}, evaluated_by=start.DEMO_CERTIFY_ACTOR,
        note="test", now_utc=now, expires_at_utc=now + timedelta(days=expires_in_days),
    )
    session.commit()


def test_certification_is_run_only_when_the_record_is_missing_failed_or_expiring(session):
    start = _load()
    now = datetime(2026, 11, 16, 9, tzinfo=UTC)
    assert start.certification_due(session, "ENTSOG", now) == "no certification record"
    _certify(session, start, stage="connection_verified")
    assert start.certification_due(session, "ENTSOG", now).startswith("gate ")
    _certify(session, start)
    assert start.certification_due(session, "ENTSOG", now) is None
    assert start.certification_due(session, "ENTSOG", now + timedelta(days=85)).startswith(
        "expires "
    )


def test_certification_step_runs_the_documented_command_as_the_demo_actor(
    session, monkeypatch
):
    """The demo performs the operator's certification command; it never writes the record
    itself or weakens the gate, and it records who did it and why."""

    start = _load()
    now = datetime(2026, 11, 16, 9, tzinfo=UTC)
    calls = []

    class Done:
        returncode = 0
        stdout = '{"ok": true, "results": [{"state": "approved"}]}'
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        return Done()

    monkeypatch.setattr(start.subprocess, "run", fake_run)
    _certify(session, start, stage="connection_verified")
    bind = session.get_bind()
    from sqlalchemy.orm import sessionmaker

    start.certify_public_sources(sessionmaker(bind=bind), now, environ={})
    assert len(calls) == 1  # GIE without a key is not certified
    command = calls[0]
    assert command[1:4] == ["scripts/ops/approve_public_source.py", "--source", "entsog"]
    assert command[command.index("--operator") + 1] == "demo-start"
    assert "demo profile" in command[command.index("--reason") + 1]
    assert "--accept-terms" in command
    event = (
        session.query(AuditEventRecord)
        .filter(AuditEventRecord.action == start.CERTIFY_ACTION)
        .one()
    )
    assert event.principal == "demo-start" and event.outcome == "success"
    assert "source=ENTSOG" in event.detail and "reason=demo profile" in event.detail


def test_live_sources_follow_keys_unless_set(monkeypatch):
    start = _load()
    for name in (*start.PUBLIC_SOURCE_KEYS, "EUROGAS_NEXUS_DEMO_LIVE_SOURCES"):
        monkeypatch.delenv(name, raising=False)
    assert start.live_sources_enabled() is False
    monkeypatch.setenv("EIA_API_KEY", "placeholder")
    assert start.live_sources_enabled() is True
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_LIVE_SOURCES", "off")
    assert start.live_sources_enabled() is False
    monkeypatch.delenv("EIA_API_KEY")
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_LIVE_SOURCES", "on")
    assert start.live_sources_enabled() is True


@pytest.fixture
def restored_environ():
    """``run`` writes its defaults into the real process environment; put it back."""

    import os

    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def test_run_maps_the_url_and_becomes_the_command(monkeypatch, restored_environ):
    start = _load()
    for name, value in _required().items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    seen = {}

    def fake_execvp(program, args):
        import os

        seen["program"], seen["args"] = program, args
        seen["url"] = os.environ["RUNTIME_STORE_DATABASE_URL"]
        return 0

    monkeypatch.setattr(start.os, "execvp", fake_execvp)
    monkeypatch.setattr(start.os, "chdir", lambda _path: None)
    start.main(["start_public_demo.py", "run", "--", "python", "scripts/ops/check_config.py"])
    assert seen["args"] == ["python", "scripts/ops/check_config.py"]
    assert seen["url"].startswith("postgresql+pg8000://")
    assert start.main(["start_public_demo.py", "run"]) == 1


def test_the_demo_scans_for_alerts_with_its_own_configuration(monkeypatch):
    """The demo raises its alerts at start and hourly, under the demo's configuration (demo
    marks on), so the strip and the bell agree with the risk page; no model call unless AI is
    on."""

    start = _load()
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", "false")
    command = start.monitoring_command()
    assert command[1:] == ["scripts/ops/run_monitoring_worker.py", "--once", "--no-llm"]
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", "true")
    assert "--no-llm" not in start.monitoring_command()
    # Hourly: an item is news on the strip for six hours.
    assert start.DEMO_EVENTS_INTERVAL_SECONDS == 3600
    calls = []
    monkeypatch.setattr(
        start.subprocess, "run", lambda command, **_: calls.append(command) or _Done(3)
    )
    start.scan_alerts()  # a failed scan is logged, never fatal
    assert calls and calls[0][1] == "scripts/ops/run_monitoring_worker.py"


class _Done:
    def __init__(self, code: int) -> None:
        self.returncode = code
