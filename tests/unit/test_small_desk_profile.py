"""The small-desk deployment profile: what runs, how it comes back, and what it never runs."""

from __future__ import annotations

import base64
import re
import sys
from datetime import UTC
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "deploy" / "small-desk"
sys.path.insert(0, str(PROFILE))

from nexusctl import operations, status, systemd  # noqa: E402
from nexusctl.settings import Settings, generate_secrets, read_env, write_env  # noqa: E402
from nexusctl.stack import readiness, service_states  # noqa: E402

COMPOSE = yaml.safe_load((PROFILE / "compose.yaml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]


def test_one_stack_with_what_the_product_needs_and_nothing_optional() -> None:
    assert set(SERVICES) == {
        "postgres", "config-check", "migrate", "reference-seed", "api", "scheduler",
        "market-events", "gateway",
    }
    text = (PROFILE / "compose.yaml").read_text(encoding="utf-8")
    for absent in ("valkey", "pgbackrest", "OIDC", "scripts/demo", "DEMO", "simulat",
                   "seed_preview", "exchange_feed", "monitoring-worker"):
        assert absent not in text.replace("simulated prices.", ""), absent


def test_everything_comes_back_after_a_crash_or_power_cut() -> None:
    for name in ("postgres", "api", "scheduler", "market-events", "gateway"):
        assert SERVICES[name]["restart"] == "unless-stopped", name
    for name in ("config-check", "migrate", "reference-seed"):
        assert SERVICES[name]["restart"] == "no"
    units = systemd.units(Path("/opt/eurogas-nexus/tool/nexus"), "01:30")
    service = units[systemd.SERVICE]
    assert "After=docker.service" in service and "WantedBy=multi-user.target" in service
    assert "ExecStart=/opt/eurogas-nexus/tool/nexus start" in service
    timer = units[systemd.BACKUP_TIMER]
    assert "OnCalendar=*-*-* 01:30:00" in timer and "Persistent=true" in timer
    with pytest.raises(ValueError):
        systemd.units(Path("/x"), "25:00")


def test_database_on_the_ssd_never_published_and_only_the_gateway_listens() -> None:
    volumes = SERVICES["postgres"]["volumes"]
    assert volumes == ["${NEXUS_DATA_DIR}/postgres:/var/lib/postgresql/data"]
    published = [name for name, spec in SERVICES.items() if spec.get("ports")]
    assert published == ["gateway"]
    for name, spec in SERVICES.items():
        image = spec["image"]
        if not image.startswith("${"):
            assert "@sha256:" in image, name  # third-party images pinned by digest


def test_local_accounts_second_factor_and_book_isolation_are_on() -> None:
    api = SERVICES["api"]["environment"]
    assert api["EUROGAS_NEXUS_LOCAL_ACCOUNTS"] == "on"
    assert api["EUROGAS_NEXUS_MFA_REQUIRED"] == "all"
    assert api["EUROGAS_NEXUS_PORTFOLIO_ISOLATION"] == "true"
    assert api["EUROGAS_NEXUS_ENV"] == "release"
    assert api["EUROGAS_NEXUS_API_PROFILE"] == "release"
    assert "SINGLE_BOOK_FIRM" not in (PROFILE / "compose.yaml").read_text(encoding="utf-8")
    # The application connects as the application role; only migrate uses the schema owner.
    assert "EUROGAS_NEXUS_APP_DB_USER" in api["RUNTIME_STORE_DATABASE_URL"]
    migrate = SERVICES["migrate"]["environment"]["RUNTIME_STORE_DATABASE_URL"]
    assert "EUROGAS_NEXUS_OWNER_DB_USER" in migrate
    assert SERVICES["migrate"]["command"][-1] == "on-start"  # checks, never migrates on start


def test_remit_pollers_run_at_the_fastest_interval_the_documented_limit_allows() -> None:
    scheduler = SERVICES["scheduler"]["environment"]
    # Both connector manifests declare 6 requests an hour: 10 minutes is 6 runs an hour.
    assert scheduler["EUROGAS_NEXUS_REMIT_IIP_INTERVAL_SECONDS"] == "600"
    assert scheduler["EUROGAS_NEXUS_REMIT_ENTSOG_INTERVAL_SECONDS"] == "600"


def test_gateway_gives_web_pages_the_same_hardening_as_the_api() -> None:
    from eurogas_nexus.api.web_client import CONTENT_SECURITY_POLICY

    caddy = (PROFILE / "Caddyfile").read_text(encoding="utf-8")
    match = re.search(r'Content-Security-Policy "([^"]+)"', caddy)
    assert match and match.group(1) == CONTENT_SECURITY_POLICY
    for header in ("X-Frame-Options \"DENY\"", "X-Content-Type-Options \"nosniff\"",
                   "Strict-Transport-Security"):
        assert header in caddy
    assert "handle /metrics" in caddy and "reverse_proxy api:8000" in caddy


def test_secrets_are_fresh_private_and_well_formed(tmp_path) -> None:
    first, second = generate_secrets(), generate_secrets()
    assert all(first[name] != second[name] for name in first)
    assert len(base64.urlsafe_b64decode(first["EUROGAS_NEXUS_SECRET_KEY"])) == 32  # Fernet
    path = tmp_path / "stack.env"
    write_env(path, first)
    assert oct(path.stat().st_mode)[-3:] == "600"
    assert read_env(path) == first
    sql = operations.roles_sql(
        {**first, "POSTGRES_DB": "eurogas"}, ROOT / "deploy/runtime/database_roles.sql"
    )
    assert sql.startswith("\\set owner_password '''")
    assert "CREATE ROLE eurogas_app" in sql
    with pytest.raises(ValueError):
        operations.roles_sql({**first, "EUROGAS_NEXUS_APP_DB_PASSWORD": "x'; DROP",
                              "POSTGRES_DB": "e"}, ROOT / "deploy/runtime/database_roles.sql")


def test_settings_round_trip(tmp_path) -> None:
    settings = Settings(root=tmp_path, data_dir=Path("/var/lib/eurogas-nexus"),
                        backup_dir=Path("/srv/nexus-backup"), copy_dir=Path("/mnt/office"),
                        server_names=["desk-server", "192.168.1.20"], https_port=8443)
    settings.save()
    loaded = Settings.load(tmp_path)
    assert loaded == settings
    assert loaded.browser_address() == "https://desk-server:8443"
    assert loaded.site_addresses() == "https://desk-server:443, https://192.168.1.20:443"


def test_readiness_waits_and_names_what_failed() -> None:
    rows = [
        {"Service": "postgres", "State": "running", "Health": "healthy"},
        {"Service": "config-check", "State": "exited", "ExitCode": 0},
        {"Service": "migrate", "State": "exited", "ExitCode": 1},
        {"Service": "reference-seed", "State": "created"},
        {"Service": "api", "State": "running", "Health": "starting"},
    ]
    ready, waiting, failed = readiness(service_states(rows))
    assert not ready and failed == ["migrate"] and "api" in waiting


def test_status_says_what_to_do_in_plain_words() -> None:
    from datetime import datetime, timedelta

    now = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)
    running = {name: {"state": "running", "health": "healthy", "exit_code": 0}
               for name in ("postgres", "api", "scheduler", "market-events", "gateway")}
    facts = {
        "services": running,
        "gateway": {"ok": True, "address": "https://desk-server"},
        "probe": {
            "database": {"reachable": True, "revision": "r", "required_revision": "r"},
            "scheduler": {"age_seconds": 20},
            "sources": [
                {"dataset": "ENTSOG flows", "state": "current", "age_minutes": 42},
                {"dataset": "GIE storage", "state": "stale", "age_minutes": 60 * 50},
            ],
        },
        "last_backup": {"finished_at_utc": (now - timedelta(hours=7)).isoformat()},
        "disks": [{"label": "backup disk", "path": "/srv", "free": 500 * 1024**3,
                   "total": 1000 * 1024**3}],
        "clock": {"synchronized": True, "offset": 0.003},
    }
    findings = status.evaluate(facts, now)
    assert status.overall(findings) == "PROBLEMS"
    messages = [item.message for item in findings]
    assert "ENTSOG flows: newest 42 minutes old." in messages
    stale = next(item for item in findings if item.message.startswith("GIE storage"))
    assert stale.status == "fail" and "2 days" in stale.message and "internet" in stale.todo
    assert any(item.message.startswith("Last good backup 7 hours ago") for item in findings)

    facts["probe"]["sources"].pop()
    assert status.overall(status.evaluate(facts, now)) == "HEALTHY"
    facts["last_backup"] = {"finished_at_utc": (now - timedelta(hours=30)).isoformat()}
    late = next(item for item in status.evaluate(facts, now) if item.area == "backup")
    assert late.status == "fail" and "sudo nexus backup" in late.todo
    facts["services"] = {}
    down = status.evaluate(facts, now)
    assert down[0].message == "The product is not running." and "nexus start" in down[0].todo


def test_changing_commands_run_one_at_a_time(tmp_path) -> None:
    from nexusctl import cli

    first = cli.one_at_a_time(tmp_path, wait_seconds=0)
    assert first is not None
    # A second process would be refused; flock locks per open file, so a second handle in this
    # process stands in for it.
    assert cli.one_at_a_time(tmp_path, wait_seconds=0) is None
    first.close()
    again = cli.one_at_a_time(tmp_path, wait_seconds=0)
    assert again is not None
    again.close()
    assert {"backup", "update", "undo-update", "restore"} <= cli.CHANGING
    assert "status" not in cli.CHANGING and "diagnostics" not in cli.CHANGING


def test_status_lists_only_the_sources_the_desk_is_connected_to() -> None:
    from eurogas_nexus.application.desk_status import connected_rows

    rows = [
        {"source_id": "src-ecb", "last_received_at_utc": "2026-11-27T08:00:00+00:00"},
        {"source_id": "src-gie", "last_received_at_utc": None},
        {"source_id": "src-eia", "last_received_at_utc": None},
    ]
    states = {"src-gie": {"enabled": True}, "src-eia": {"enabled": False}}
    assert [row["source_id"] for row in connected_rows(rows, states)] == ["src-ecb", "src-gie"]
