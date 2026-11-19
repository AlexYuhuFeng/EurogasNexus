"""The customer runtime can run every public source the product's scheduler schedules.

Why this test exists. Until 2026-11-17 the customer image shipped only the ECB/ENTSOG/GIE
ingestor, and its worker read only those three: EIA, ENTSO-E, Elexon, National Gas, the
rate fixings and the REMIT collectors had no script in the image, so a customer
installation could never fill those screens although the scheduler listed them. One
mechanism now serves both stores (``scripts/ops/run_dataops_scheduler.py``), and this test
holds the three lists together so the gap cannot reopen:

1. the sources the scheduler can run (``_SOURCE_ARGS`` and ``_SCRIPT_COMMANDS``) are exactly
   the registry's schedulable sources;
2. every script those commands start is in the customer image (``Dockerfile.api``) and in
   its artifact policy, and imports nothing that is not shipped;
3. the customer compose worker runs that scheduler;
4. the sources gated on a key are exactly the schedulable sources the approval module
   classifies as needing one.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml

from eurogas_nexus.application.scheduled_source_keys import SCHEDULED_SOURCE_KEYS
from eurogas_nexus.domain.dataops.registry import schedulable_definitions
from eurogas_nexus.domain.ingestion.source_approval import classify_source
from eurogas_nexus.domain.ingestion.source_registry import registered_sources
from scripts.ops.run_dataops_scheduler import (
    _SCRIPT_COMMANDS,
    _SOURCE_ARGS,
    ENTSOG_HISTORY_COMMAND,
    INGEST_SCRIPT,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "scripts/release/runtime_artifact_policy.json").read_text())
DOCKERFILE = (ROOT / "deploy/runtime/Dockerfile.api").read_text(encoding="utf-8")


def _scheduler_scripts() -> set[str]:
    scripts = {f"scripts/ops/{INGEST_SCRIPT.name}"} if _SOURCE_ARGS else set()
    scripts |= {f"scripts/ops/{command[0]}" for command in _SCRIPT_COMMANDS.values()}
    # Started after a successful scheduled ENTSOG read, not as a source of its own.
    scripts.add(f"scripts/ops/{ENTSOG_HISTORY_COMMAND[0]}")
    return scripts


def test_the_scheduler_runs_exactly_the_registry_schedulable_sources() -> None:
    schedulable = {definition.source_id for definition in schedulable_definitions()}
    runnable = set(_SOURCE_ARGS) | set(_SCRIPT_COMMANDS)
    assert runnable == schedulable, (
        f"scheduler without a runner: {sorted(schedulable - runnable)}; "
        f"runner without a schedule: {sorted(runnable - schedulable)}"
    )


def test_every_script_the_scheduler_starts_ships_in_the_customer_image() -> None:
    shipped = set(POLICY["runtime_scripts"])
    for script in sorted(_scheduler_scripts() | {"scripts/ops/run_dataops_scheduler.py"}):
        assert script in shipped, f"{script} is not in runtime_artifact_policy.json"
        assert f"{script} \\" in DOCKERFILE or f"{script} ./scripts/ops/" in DOCKERFILE, (
            f"{script} is not copied by deploy/runtime/Dockerfile.api"
        )


def test_shipped_scheduler_scripts_import_only_the_product_package() -> None:
    for script in sorted(_scheduler_scripts() | {"scripts/ops/run_dataops_scheduler.py"}):
        tree = ast.parse((ROOT / script).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith(("scripts", "tests", "apps")), (
                    f"{script} imports {name}, which the customer image does not ship"
                )


def test_the_customer_worker_is_the_scheduler_and_the_demo_start_is_not_shipped() -> None:
    compose = yaml.safe_load((ROOT / "deploy/runtime/compose.yaml").read_text(encoding="utf-8"))
    worker = compose["services"]["public-ingestion-worker"]["command"]
    assert worker[:2] == ["python", "scripts/ops/run_dataops_scheduler.py"]
    assert "--entsog-lookback-gas-days" in worker
    assert not any(path.startswith("scripts/demo/") for path in POLICY["runtime_scripts"])
    assert "scripts/demo" not in DOCKERFILE


def test_keyed_sources_are_exactly_the_schedulable_sources_that_need_a_key() -> None:
    rows = {row["source_id"]: row for row in registered_sources()}
    needs_key = {
        definition.source_id
        for definition in schedulable_definitions()
        if classify_source(rows[definition.source_id]) in {"key_only", "approval_and_key"}
    }
    assert set(SCHEDULED_SOURCE_KEYS) == needs_key
