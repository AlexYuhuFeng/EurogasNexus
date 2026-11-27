"""The parallel browser-acceptance shards together run the whole sweep.

Hosted CI splits ``scripts/uat/browser_workflow_smoke.mjs`` into shards
(``scripts/uat/browser_shards.json``), one job each, behind one required check. A workspace or
stage that no shard names would silently stop being checked, and a shard the CI matrix does not
run would do the same; a shard the file does not declare would make its job fail at start. The
sweep itself refuses an incomplete shard file at run time; this holds the file, the harness and
the workflow to each other without a browser.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "uat" / "browser_workflow_smoke.mjs"
SHARDS = ROOT / "scripts" / "uat" / "browser_shards.json"
CI = ROOT / ".github" / "workflows" / "ci.yml"

WORKSPACES_BLOCK = re.compile(r"const WORKSPACES = \[(?P<body>.*?)\]", re.DOTALL)
STAGES_BLOCK = re.compile(r"const SWEEP_STAGES = \[(?P<body>.*?)\]", re.DOTALL)
QUOTED = re.compile(r'"([a-z-]+)"')


def _declared(pattern: re.Pattern[str]) -> list[str]:
    match = pattern.search(HARNESS.read_text(encoding="utf-8"))
    assert match, pattern.pattern
    return QUOTED.findall(match.group("body"))


def _shards() -> dict[str, dict[str, list[str]]]:
    return json.loads(SHARDS.read_text(encoding="utf-8"))["shards"]


def test_every_workspace_and_stage_is_in_exactly_one_shard() -> None:
    workspaces = _declared(WORKSPACES_BLOCK)
    stages = _declared(STAGES_BLOCK)
    assert len(workspaces) >= 14 and stages == ["phone-overflow", "interactions"]

    owners: dict[str, list[str]] = {}
    for name, shard in _shards().items():
        assert set(shard) <= {"workspaces", "stages"}, name
        for workspace in shard.get("workspaces", []):
            assert workspace in workspaces, (name, workspace)
            owners.setdefault(workspace, []).append(name)
        for stage in shard.get("stages", []):
            assert stage in stages, (name, stage)
            owners.setdefault(stage, []).append(name)

    assert {item: names for item, names in owners.items() if len(names) != 1} == {}
    assert sorted(owners) == sorted([*workspaces, *stages])


def test_the_ci_matrix_runs_every_declared_shard_behind_the_required_check() -> None:
    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]
    shard_job = jobs["browser-acceptance-shard"]
    matrix = shard_job["strategy"]["matrix"]["include"]
    assert sorted(entry["shard"] for entry in matrix) == sorted(_shards())
    assert shard_job["strategy"]["fail-fast"] is False

    sweep = next(
        step for step in shard_job["steps"] if "browser_workflow_smoke.mjs" in str(step.get("run"))
    )
    assert sweep["env"]["EUROGAS_UAT_SHARD"] == "${{ matrix.shard }}"

    # The map host check and the geometry audit still run, each exactly once.
    assert sum(1 for entry in matrix if entry.get("map_check")) == 1
    assert sum(1 for entry in matrix if entry.get("geometry_audit")) == 1
    runs = [str(step.get("run")) for step in shard_job["steps"]]
    assert "node scripts/uat/map_no_third_party.mjs" in runs
    assert "node scripts/uat/geometry_audit.mjs --report" in runs

    # The required check keeps its name and passes only on every shard's success.
    gate = jobs["browser-acceptance"]
    assert gate["name"] == "Browser acceptance (EN/ZH, 3 viewports)"
    assert gate["if"] == "always()"
    assert "browser-acceptance-shard" in gate["needs"]
    assert "browser-acceptance-build" in gate["needs"]
    check = gate["steps"][0]["run"]
    assert 'test "$SHARDS" = "success"' in check
    assert 'test "$BUILD" = "success"' in check
