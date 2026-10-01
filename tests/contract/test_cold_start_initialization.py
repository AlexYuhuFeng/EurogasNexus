"""Cold-start dependency initialization contract (CI run 36878083383).

Evidence: on 2026-10-01 CI run ``36878083383`` (baseline ``58afd8a``) failed
the in-process API load smoke in a CPython 3.11 ``_ModuleLock('sqlalchemy.exc')``
import deadlock: eight concurrent first requests reached the lazily imported
runtime database layer from FastAPI worker threads at the same time.

Every check here runs in a fresh subprocess, because the condition under test
is first-import state: a pytest process that already imported SQLAlchemy
cannot observe the race. The checks prove, without retries, serialized
workloads, warm-up requests or relaxed thresholds, that:

* importing the API still does not load the DB layer (the import boundary
  ``tests/contract/test_db_foundation.py`` pins);
* the application lifespan startup completes the runtime dependency imports on
  one thread before any request runs, so no request worker can be the first
  importer; and
* the smoke's concurrent first requests succeed in a fresh process and the
  runtime DB graph was not first imported by a request worker thread.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Synthetic caller credential for the isolated smoke subprocess only. It is
# never a deployment secret and never reaches a real database: the DB
# environment variables are removed below.
SYNTHETIC_TOKEN = "cold-start-contract-token"
DB_ENV_VARS = (
    "RUNTIME_STORE_DATABASE_URL",
    "DATABASE_URL",
    "EUROGAS_NEXUS_DB_DSN",
)


def _isolated_env(**overrides: str) -> dict[str, str]:
    """Fresh-process environment with no ambient DB URL and a synthetic token."""

    env = dict(os.environ)
    for name in (*DB_ENV_VARS, "EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS"):
        env.pop(name, None)
    env["EUROGAS_NEXUS_PUBLIC_API_TOKEN"] = SYNTHETIC_TOKEN
    pythonpath = [str(ROOT / "src"), str(ROOT)]
    pythonpath.extend(part for part in env.get("PYTHONPATH", "").split(os.pathsep) if part)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    env.update(overrides)
    return env


def _run_cold_script(
    script: str,
    *,
    env: dict[str, str],
    args: tuple[str, ...] = (),
    timeout: int = 300,
):
    return subprocess.run(
        [sys.executable, "-c", script, *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


_IMPORT_RECORDER = """
class _ImportRecorder(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.first_sight = []
        self._seen = set()

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("sqlalchemy", "eurogas_nexus.db")):
            if fullname not in self._seen:
                self._seen.add(fullname)
                self.first_sight.append((fullname, threading.current_thread().name))
        return None
"""


def test_startup_initializes_runtime_dependencies_before_requests() -> None:
    """The lifespan startup, not a request worker, completes the DB imports."""

    script = (
        "import asyncio, importlib.abc, json, sys, threading\n"
        "from apps.api.main import app\n"
        "from eurogas_nexus.api import runtime_dependencies\n"
        + _IMPORT_RECORDER
        + "recorder = _ImportRecorder()\n"
        "sys.meta_path.insert(0, recorder)\n"
        "before = {\n"
        "    'initialized': runtime_dependencies.runtime_dependencies_initialized(),\n"
        "    'db_in_modules': 'eurogas_nexus.db' in sys.modules,\n"
        "    'sqlalchemy_in_modules': 'sqlalchemy' in sys.modules,\n"
        "}\n"
        "async def main():\n"
        "    async with app.router.lifespan_context(app):\n"
        "        return {\n"
        "            'initialized': runtime_dependencies.runtime_dependencies_initialized(),\n"
        "            'missing': [\n"
        "                name for name in runtime_dependencies.RUNTIME_DEPENDENCY_MODULES\n"
        "                if name not in sys.modules\n"
        "            ],\n"
        "        }\n"
        "after = asyncio.run(main())\n"
        "print(json.dumps({\n"
        "    'before': before,\n"
        "    'after_startup': after,\n"
        "    'first_sight_threads': sorted({thread for _, thread in recorder.first_sight}),\n"
        "    'main_thread': threading.main_thread().name,\n"
        "}))\n"
    )

    result = _run_cold_script(script, env=_isolated_env())

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # Importing the API stays light: the DB layer is still not loaded, so the
    # import boundary contract holds and non-server processes pay nothing.
    assert payload["before"] == {
        "initialized": False,
        "db_in_modules": False,
        "sqlalchemy_in_modules": False,
    }
    # Startup completes the lazy imports: after it, every runtime dependency is
    # in sys.modules, so no request thread can be the first importer.
    assert payload["after_startup"] == {"initialized": True, "missing": []}
    # The evidenced deadlock happened because a request worker thread performed
    # the first import. Initialization must run on the startup thread.
    assert payload["first_sight_threads"] == [payload["main_thread"]]


def test_startup_needs_no_database_and_opens_no_connection() -> None:
    """Startup completes with an explicitly unreachable DSN, with no retries."""

    script = (
        "import asyncio, json\n"
        "from apps.api.main import app\n"
        "from eurogas_nexus.api import runtime_dependencies\n"
        "async def main():\n"
        "    async with app.router.lifespan_context(app):\n"
        "        return runtime_dependencies.runtime_dependencies_initialized()\n"
        "print(json.dumps({'initialized': asyncio.run(main())}))\n"
    )
    # Port 1 on loopback refuses immediately, so a connection attempt during
    # startup would fail the process instead of passing quietly.
    env = _isolated_env(
        RUNTIME_STORE_DATABASE_URL="postgresql+pg8000://nexus:nexus@127.0.0.1:1/nexus"
    )

    result = _run_cold_script(script, env=env)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"initialized": True}


def test_initialization_is_idempotent() -> None:
    """A second initialization is a no-op that imports nothing new."""

    from eurogas_nexus.api import runtime_dependencies

    runtime_dependencies.initialize_runtime_dependencies()
    assert runtime_dependencies.runtime_dependencies_initialized()

    modules_after_first_call = set(sys.modules)
    runtime_dependencies.initialize_runtime_dependencies()

    assert set(sys.modules) == modules_after_first_call


def test_cold_process_concurrent_first_requests_after_startup() -> None:
    """Fresh process: the smoke workload succeeds and no worker imports the DB."""

    script = (
        "import importlib.abc, importlib.util, json, sys, threading\n"
        + _IMPORT_RECORDER
        + "from pathlib import Path\n"
        "root = Path(sys.argv[1])\n"
        "spec = importlib.util.spec_from_file_location(\n"
        "    'cold_start_load_smoke', root / 'scripts' / 'ops' / 'load_smoke.py'\n"
        ")\n"
        "smoke = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(smoke)\n"
        "recorder = _ImportRecorder()\n"
        "sys.meta_path.insert(0, recorder)\n"
        "latencies, errors = smoke.run_requests(40, 8, smoke.SMOKE_PATHS)\n"
        "from eurogas_nexus.api import runtime_dependencies\n"
        "print(json.dumps({\n"
        "    'latencies': len(latencies),\n"
        "    'errors': errors,\n"
        "    'initialized': runtime_dependencies.runtime_dependencies_initialized(),\n"
        "    'first_sight_threads': sorted({thread for _, thread in recorder.first_sight}),\n"
        "    'main_thread': threading.main_thread().name,\n"
        "}))\n"
    )

    result = _run_cold_script(script, env=_isolated_env(), args=(str(ROOT),))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["latencies"] == 40
    assert payload["errors"] == []
    assert payload["initialized"] is True
    assert payload["first_sight_threads"] == [payload["main_thread"]]
