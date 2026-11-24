"""Run every documented SDK example against a live server.

The examples in ``examples/sdk`` are the code shown in ``docs/sdk/EXAMPLES.md`` and the SDK
readme. This test keeps them runnable: it executes each script in a fresh interpreter against a
running server and fails on a non-zero exit or empty output.

It needs a server with the demo desk seeded (see ``docs/sdk/QUICKSTART.md``). Point the test at
it with two variables of its own, because ``tests/conftest.py`` pins
``EUROGAS_NEXUS_PUBLIC_API_TOKEN`` to a test value for the whole suite:

* ``EUROGAS_NEXUS_EXAMPLES_BASE_URL``, for example ``http://127.0.0.1:8000``;
* ``EUROGAS_NEXUS_EXAMPLES_API_TOKEN``, that server's deployment token.

The test is skipped when the address is unset. It sends nothing outside that server.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((REPO_ROOT / "examples" / "sdk").glob("[0-9][0-9]_*.py"))
BASE_URL = os.environ.get("EUROGAS_NEXUS_EXAMPLES_BASE_URL", "")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="set EUROGAS_NEXUS_EXAMPLES_BASE_URL and EUROGAS_NEXUS_EXAMPLES_API_TOKEN to run",
)


def test_examples_exist() -> None:
    assert EXAMPLES, "examples/sdk holds no numbered example scripts"


@pytest.mark.parametrize("script", EXAMPLES, ids=lambda path: path.name)
def test_example_runs(script: Path) -> None:
    env = {
        **os.environ,
        "EUROGAS_NEXUS_BASE_URL": BASE_URL,
        "EUROGAS_NEXUS_PUBLIC_API_TOKEN": os.environ.get("EUROGAS_NEXUS_EXAMPLES_API_TOKEN", ""),
    }
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stdout.strip(), f"{script.name} printed nothing"
