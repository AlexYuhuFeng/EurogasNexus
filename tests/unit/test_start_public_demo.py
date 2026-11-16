"""Start-up of the hosted test/demo server (root Dockerfile): configuration and catch-up."""

from __future__ import annotations

import importlib.util
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
    assert int(environ["EUROGAS_NEXUS_DB_POOL_SIZE"]) <= 5
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
    names = [name for name, _ in start.catch_up_steps(15, now, environ={})]
    assert names[0].startswith("ECB") and names[1].startswith("ENTSOG")
    assert len(names) == 2
    keyed = start.catch_up_steps(
        15, now, environ={"GIE_API_KEY": "x", "EIA_API_KEY": "x", "ENTSOE_SECURITY_TOKEN": "x"}
    )
    commands = {name: command for name, command in keyed}
    assert len(commands) == 5
    entsog = next(command for name, command in keyed if name.startswith("ENTSOG"))
    assert entsog[entsog.index("--entsog-lookback-gas-days") + 1] == "15"
    eia = next(command for name, command in keyed if name.startswith("EIA"))
    assert eia[-2:] == ["--days", "15"]
    power = next(command for name, command in keyed if name.startswith("ENTSO-E"))
    assert "--commit" in power and "15" in power


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
