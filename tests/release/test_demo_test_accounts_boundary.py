"""Demo test accounts (a shared weak password) exist only on the hosted demo server.

The customer runtime (release profile, the API image's ``uvicorn apps.api.main:app``) must
refuse to start with ``EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS`` set, preflight must report it,
and the setting's parser must refuse an admin account that is not named explicitly.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import local_accounts
from eurogas_nexus.core.config import Settings
from eurogas_nexus.core.preflight import check_environment

ROOT = Path(__file__).resolve().parents[2]
SETTING = local_accounts.DEMO_TEST_ACCOUNTS_ENV


@pytest.mark.parametrize(
    ("profile", "environment"),
    [("release", "release"), ("release", "trial"), ("release", "development"),
     ("internal", "development"), ("development", "development")],
)
def test_the_api_refuses_to_start_with_demo_accounts_outside_the_demo_profile(
    monkeypatch, profile, environment
):
    monkeypatch.setenv(SETTING, "test_trader:12345678")
    with pytest.raises(RuntimeError, match=SETTING):
        create_app(Settings(api_profile=profile, environment=environment))


def test_the_demo_profile_accepts_the_setting(monkeypatch):
    monkeypatch.setenv(SETTING, "test_trader:12345678")
    create_app(Settings(api_profile="demo", environment="development"))


def test_preflight_reports_the_setting_on_a_customer_server():
    env = {
        "EUROGAS_NEXUS_ENV": "release",
        "EUROGAS_NEXUS_API_PROFILE": "release",
        SETTING: "test_trader:12345678",
    }
    codes = [f.code for f in check_environment(env).findings if f.severity == "error"]
    assert "demo_test_accounts_outside_demo" in codes
    env.pop(SETTING)
    codes = [f.code for f in check_environment(env).findings]
    assert "demo_test_accounts_outside_demo" not in codes


def test_the_customer_runtime_never_sets_the_setting():
    for path in ("deploy/runtime/compose.yaml", "deploy/runtime/Dockerfile.api"):
        assert SETTING not in (ROOT / path).read_text(encoding="utf-8"), path
    # The generated server template lists every declared variable; this one stays empty, in
    # the demo-server section, and says it is refused elsewhere.
    text = (ROOT / "deploy/runtime/env.server.example").read_text(encoding="utf-8")
    assert f"\n{SETTING}=\n" in text
    demo_section = text.split("# --- Hosted test/demo server")[1].split("# --- ")[0]
    assert SETTING in demo_section and "Refused outside the demo profile" in demo_section


def test_the_demo_example_lists_the_nine_accounts_commented():
    text = (ROOT / "deploy/demo/.env.example").read_text(encoding="utf-8")
    (line,) = [row for row in text.splitlines() if row.startswith(f"# {SETTING}=")]
    names = [entry.split(":")[0] for entry in line.split("=", 1)[1].split(",")]
    assert names == list(local_accounts.DEFAULT_DEMO_TEMPLATES)
    assert f"\n{SETTING}=\n" in text  # off unless the operator sets it
    assert "test_admin:12345678:admin" in line


def test_parser_forms_and_refusals():
    specs = local_accounts.parse_demo_accounts(
        "test_trader:12345678, test_admin:12345678:admin"
    )
    assert [(s.username, s.template, s.allow_admin) for s in specs] == [
        ("test_trader", "demo.trader", False),
        ("test_admin", "demo.admin", True),
    ]
    json_specs = local_accounts.parse_demo_accounts(
        '[{"username": "desk_one", "password": "12345678", "as": "demo.trader"}]'
    )
    assert json_specs[0].template == "demo.trader"
    for bad in ("test_trader:1234", "nobody:12345678", "test_trader:12345678,test_trader:x",
                "[{]"):
        with pytest.raises(ValueError) as raised:
            local_accounts.parse_demo_accounts(bad)
        assert "12345678" not in str(raised.value)


def _demo_script():
    spec = importlib.util.spec_from_file_location(
        "tests.start_public_demo", ROOT / "scripts" / "demo" / "start_public_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_start_refuses_an_admin_account_not_named_explicitly():
    script = _demo_script()
    env = {
        "DATABASE_URL": "postgresql://u:p@db:5432/demo",
        "EUROGAS_NEXUS_SECRET_KEY": "k" * 44,
        "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD": "a-strong-tester-password",
        SETTING: "test_admin:12345678",
    }
    with pytest.raises(script.StartupError, match="ADMIN"):
        script.configure_environment(dict(env))
    ok = dict(env, **{SETTING: "test_admin:12345678:admin,test_trader:12345678"})
    script.configure_environment(ok)
    # Every default name maps to an existing demo tester.
    for template in local_accounts.DEFAULT_DEMO_TEMPLATES.values():
        assert template in script.TESTER_BY_NAME
