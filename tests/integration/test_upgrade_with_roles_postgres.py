"""The gated upgrade with the separate database roles (security review H5 + P1-C).

``deploy/runtime/database_roles.sql`` gives the schema to an owner role and connects the
services as an application role without DDL. The gated upgrade must run as the owner (the
``migrate`` service's ``EUROGAS_NEXUS_OWNER_DB_USER``), refuse up front as the application role
instead of failing half-way, and leave the application role able to serve the new schema.

Runs when ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` names a superuser (the PostgreSQL CI job) and
``psql`` is installed (the script uses psql variables). The roles get a unique suffix and are
dropped afterwards, so parallel runs on one server do not collide.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[2]
_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")

pytestmark = [
    pytest.mark.skipif(
        not _POSTGRES_URL.startswith("postgresql"),
        reason="needs EUROGAS_NEXUS_TEST_POSTGRES_URL (the PostgreSQL CI job)",
    ),
    pytest.mark.skipif(shutil.which("psql") is None, reason="needs psql for the role script"),
]

PREVIOUS = "0094_option_settlements"
ROLES = ("eurogas_owner", "eurogas_app", "eurogas_reader", "eurogas_auditor")


def _psql_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture()
def roles_store(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    name = f"roles_upgrade_{suffix}"
    names = {role: f"{role}_{suffix}" for role in ROLES}
    admin = create_engine(_POSTGRES_URL, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    base = make_url(_POSTGRES_URL).set(database=name)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", base.render_as_string(hide_password=False))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    urls = {
        "admin": base.render_as_string(hide_password=False),
        "owner": base.set(username=names["eurogas_owner"], password="owner-pw").render_as_string(
            hide_password=False
        ),
        "app": base.set(username=names["eurogas_app"], password="app-pw").render_as_string(
            hide_password=False
        ),
    }
    yield name, names, urls
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        for role in names.values():
            connection.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
    admin.dispose()


def _apply_roles(name: str, names: dict[str, str], admin_url: str) -> None:
    sql = (ROOT / "deploy/runtime/database_roles.sql").read_text(encoding="utf-8")
    # Longest first: eurogas_app is not a prefix of another name, but keep it safe.
    for role in sorted(names, key=len, reverse=True):
        sql = sql.replace(role, names[role])
    completed = subprocess.run(
        [
            "psql", _psql_url(admin_url), "-X", "-q",
            "-v", "owner_password='owner-pw'",
            "-v", "app_password='app-pw'",
            "-v", "reader_password='reader-pw'",
            "-v", f"db={name}",
            "-f", "-",
        ],
        input=sql, text=True, capture_output=True, check=False, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr


def _upgrade(url: str, **kwargs) -> tuple[int, list[str]]:
    from eurogas_nexus.application.database_upgrade import run_upgrade

    lines: list[str] = []
    return run_upgrade(url, emit=lines.append, **kwargs), lines


def _revision(url: str) -> str:
    engine = create_engine(url, future=True)
    with engine.connect() as connection:
        value = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    return value


def test_the_gated_upgrade_runs_as_the_owner_and_refuses_as_the_application_role(roles_store):
    from alembic import command
    from eurogas_nexus.application.database_upgrade import alembic_config, build_plan
    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    name, names, urls = roles_store
    # An installation at head, then split into roles as DATABASE_ROLES.md says.
    code, lines = _upgrade(urls["admin"], operator="Ops Tester")
    assert code == 0, lines
    _apply_roles(name, names, urls["admin"])
    # A new version brings a revision: here 0095 again, after the owner took it back.
    command.downgrade(alembic_config(urls["owner"]), PREVIOUS)
    assert _revision(urls["owner"]) == PREVIOUS

    # The application role: refused before anything runs, with the owner named.
    code, lines = _upgrade(urls["app"], operator="Ops Tester", override_reason="roles test")
    assert code == 2, lines
    assert any("REFUSED" in line and "EUROGAS_NEXUS_OWNER_DB_USER" in line for line in lines)
    assert _revision(urls["admin"]) == PREVIOUS

    # The owner role: the upgrade runs, with its audit row.
    code, lines = _upgrade(urls["owner"], operator="Ops Tester", override_reason="roles test")
    assert code == 0, lines
    assert _revision(urls["admin"]) == DB_SCHEMA_REVISION

    app = create_engine(urls["app"], future=True)
    try:
        # The stack's start-up check runs as either role; the application role reads the plan.
        assert build_plan(app, alembic_config(urls["app"])).up_to_date
        with app.connect() as connection:
            # Tables the owner's migration created are usable by the application role
            # (default privileges), the audit trail stays append-only, DDL stays refused.
            connection.execute(text("SELECT count(*) FROM audit_chain")).scalar_one()
            assert connection.execute(
                text("SELECT count(*) FROM audit_events WHERE source_system = 'database-upgrade'")
            ).scalar_one() >= 2
            with pytest.raises(DBAPIError):
                connection.execute(text("UPDATE audit_events SET outcome = 'x'"))
            connection.rollback()
            with pytest.raises(DBAPIError):
                connection.execute(text("CREATE TABLE app_may_not (id int)"))
            connection.rollback()
    finally:
        app.dispose()
