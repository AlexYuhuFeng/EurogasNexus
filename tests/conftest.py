"""Shared test fixtures.

- The public API token env var is configured for the whole session so release
  profile tests exercise the authenticated path; individual tests may override
  it locally.
- ``tmp_path`` is replaced with a sandbox-safe implementation: this environment
  denies enumeration of directories created with mode 0o700 (the mode pytest's
  own temp machinery uses), so fixtures are created with default permissions
  under a pre-existing enumerable workspace directory.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest

_TMP_ROOT = Path(os.environ.get("EUROGAS_NEXUS_TEST_TMP_ROOT", ".tmp_work")).resolve()


@pytest.fixture(scope="session", autouse=True)
def _public_api_token_env() -> None:
    os.environ.setdefault("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "test-public-api-token")


@pytest.fixture(scope="session", autouse=True)
def _pythonpath_for_subprocesses() -> None:
    """Make ``src`` importable by scripts spawned as subprocesses."""

    root = Path(__file__).resolve().parent.parent
    src = str(root / "src")
    parts = [part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep) if part]
    if src not in parts:
        parts.insert(0, src)
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)


@pytest.fixture()
def tmp_path() -> Path:
    """Return a writable per-test directory (sandbox-safe, default mode)."""

    _TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = _TMP_ROOT / f"t-{uuid.uuid4().hex[:12]}"
    path.mkdir()
    yield path
    shutil.rmtree(path, ignore_errors=True)
