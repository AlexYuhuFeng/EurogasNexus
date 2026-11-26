"""The upgrade command finds the migrations when the package is installed (an image).

On 2026-11-26 the demo image could not start: ``database_upgrade.ROOT`` was the directory
three levels above the module, which in an image is ``site-packages``'s parent, not the
working directory the migrations are copied to. Tests run from a source checkout, where both
are the same directory, so nothing caught it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_upgrade_plan_runs_with_the_package_outside_the_checkout(tmp_path) -> None:
    site = tmp_path / "lib" / "python" / "site-packages"
    site.mkdir(parents=True)
    shutil.copytree(REPO / "src" / "eurogas_nexus", site / "eurogas_nexus")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"RUNTIME_STORE_DATABASE_URL", "DATABASE_URL", "PYTHONPATH"}
    }
    env["PYTHONPATH"] = os.pathsep.join(
        [str(site), str(REPO / "packages" / "python-sdk" / "src")]
    )
    env["EUROGAS_NEXUS_DB_DSN"] = f"sqlite+pysqlite:///{(tmp_path / 'store.sqlite').as_posix()}"
    done = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "ops" / "upgrade_database.py"), "plan"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert "Path doesn't exist" not in done.stderr
