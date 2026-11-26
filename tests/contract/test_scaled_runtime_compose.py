"""The several-process runtime (P1-A's compose.scale.yaml) keeps P1-C's guarantees.

* every API process writes its metrics to one shared directory, so one scrape sums them;
* only the API is multiplied: the scheduler and the other run-once workers stay one container
  each (the scheduler also holds its PostgreSQL lock), and the demo launcher starts its loops
  before it runs a single uvicorn process;
* the release stack never upgrades the database on start, scaled or not;
* the preflight sees the scaled topology and accepts it only with the shared cache.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from eurogas_nexus.core.preflight import _check_serving

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "deploy" / "runtime"


def _load(name: str) -> dict:
    return yaml.safe_load((RUNTIME / name).read_text(encoding="utf-8"))


def _merged_environment(service: str) -> dict[str, str]:
    base = _load("compose.yaml")["services"][service].get("environment", {})
    scale = _load("compose.scale.yaml")["services"].get(service, {}).get("environment", {})
    return {**base, **scale}


def _resolve(value: str) -> str:
    """``${NAME:-default}`` -> ``default`` (the value with nothing set in the env file)."""

    value = str(value)
    if value.startswith("${") and ":-" in value:
        return value.split(":-", 1)[1].rsplit("}", 1)[0]
    return value


def test_the_scaled_api_processes_share_one_metrics_directory() -> None:
    base = _load("compose.yaml")["services"]["api"]
    scale = _load("compose.scale.yaml")["services"]["api"]
    environment = _merged_environment("api")
    directory = environment["PROMETHEUS_MULTIPROC_DIR"]
    assert directory.startswith("/")
    # One tmpfs of the api container: every uvicorn worker process in it sees the same files.
    assert any(str(mount).split(":", 1)[0] == directory for mount in base["tmpfs"])
    assert "tmpfs" not in scale and "volumes" not in scale and "command" not in scale
    assert int(_resolve(environment["UVICORN_WORKERS"])) > 1


def test_only_the_api_is_multiplied() -> None:
    scale = _load("compose.scale.yaml")["services"]
    base = _load("compose.yaml")["services"]
    for name in ("public-ingestion-worker", "market-events-worker", "monitoring-worker"):
        assert name not in scale, name
        assert "deploy" not in base[name] and "scale" not in base[name], name
    assert "scripts/ops/run_dataops_scheduler.py" in base["public-ingestion-worker"]["command"]
    for name, service in scale.items():
        assert "deploy" not in service and "scale" not in service, name
    # The demo launcher starts its feed, events and scheduler, then runs one uvicorn process.
    launcher = (ROOT / "scripts" / "demo" / "start_public_demo.py").read_text(encoding="utf-8")
    assert '"--workers",\n        "1",' in launcher


def test_the_release_stack_never_upgrades_on_start_scaled_or_not() -> None:
    for service in ("migrate", "api", "config-check"):
        environment = _merged_environment(service)
        assert environment["EUROGAS_NEXUS_ENV"] == "release"
        assert "EUROGAS_NEXUS_AUTO_MIGRATE" not in environment, service
    migrate = _load("compose.yaml")["services"]["migrate"]
    assert migrate["command"] == ["python", "scripts/ops/upgrade_database.py", "on-start"]
    assert "command" not in _load("compose.scale.yaml")["services"]["migrate"]


def test_the_preflight_checks_the_topology_that_runs() -> None:
    scaled = {key: _resolve(value) for key, value in _merged_environment("config-check").items()}
    assert _merged_environment("config-check")["UVICORN_WORKERS"] == _merged_environment("api")[
        "UVICORN_WORKERS"
    ]
    assert _check_serving(scaled) == []
    without_cache = {**scaled, "EUROGAS_NEXUS_SHARED_CACHE_URL": ""}
    [finding] = _check_serving(without_cache)
    assert finding.code == "shared_cache_required"
