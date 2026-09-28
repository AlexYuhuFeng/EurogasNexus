"""UAT fixture gate: simulated data can never leak into trial/release."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(env: dict[str, str], *arguments: str) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    merged.pop("RUNTIME_STORE_DATABASE_URL", None)
    merged.pop("DATABASE_URL", None)
    merged.pop("EUROGAS_NEXUS_DB_DSN", None)
    merged.update(env)
    return subprocess.run(
        [sys.executable, "scripts/uat/seed_uat_fixture.py", *arguments],
        cwd=ROOT,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fixture_requires_explicit_acknowledgement() -> None:
    result = _run({"EUROGAS_NEXUS_ENV": "development"})
    assert result.returncode == 2
    assert "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED" in result.stdout


def test_fixture_is_blocked_in_release_even_with_acknowledgement() -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "release",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
        }
    )
    assert result.returncode == 2
    assert "blocked in trial/release" in result.stdout


def test_fixture_reports_missing_database_url() -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "development",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
        }
    )
    assert result.returncode == 2
    assert "Runtime DB URL missing" in result.stdout


def test_agent_window_refresh_requires_explicit_acknowledgement() -> None:
    result = _run({"EUROGAS_NEXUS_ENV": "development"}, "--agent-window-only")
    assert result.returncode == 2
    assert "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED" in result.stdout


def test_agent_window_refresh_is_blocked_in_release_even_with_acknowledgement() -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "release",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
        },
        "--agent-window-only",
    )
    assert result.returncode == 2
    assert "blocked in trial/release" in result.stdout


def test_fixture_rejects_an_argument_it_does_not_declare() -> None:
    result = _run({"EUROGAS_NEXUS_ENV": "development"}, "--agent-window")
    assert result.returncode == 2
    assert "Unknown argument(s)" in result.stdout
