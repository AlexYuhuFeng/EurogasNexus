"""Inspect real customer wheels and replay the exact copied image tool payload.

No Docker build, provider access or database changes. The temporary build contains
only product sources and packaging inputs, never local secrets or data.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from scripts.release.verify_customer_artifact import (
    ArtifactError,
    load_policy,
    verify_members,
    verify_runtime_tree,
    verify_wheel,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = load_policy()


@pytest.fixture(scope="module")
def customer_wheel(tmp_path_factory) -> Path:
    staging = tmp_path_factory.mktemp("customer-wheel")
    for name in ("pyproject.toml", "setup.py", "README.md"):
        shutil.copy2(ROOT / name, staging / name)
    for relative in ("src", "packages/python-sdk/src"):
        shutil.copytree(
            ROOT / relative,
            staging / relative,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
        )
    result = subprocess.run(
        [sys.executable, "setup.py", "bdist_wheel", "--dist-dir", "wheel-output"],
        cwd=staging,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    wheels = list((staging / "wheel-output").glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_actual_customer_wheel_excludes_producer_preserves_runtime(customer_wheel) -> None:
    verify_wheel(customer_wheel, POLICY)
    with zipfile.ZipFile(customer_wheel) as archive:
        members = archive.namelist()
        assert "eurogas_nexus/ingestion/simulated_market_prices.py" not in members
        assert "eurogas_nexus/ingestion/provenance_versions.py" in members
        assert "eurogas_nexus/ingestion/gie_transport.py" in members


def test_incremental_build_refuses_stale_excluded_producer(customer_wheel) -> None:
    staging = customer_wheel.parent.parent
    stale = staging / "build/lib/eurogas_nexus/ingestion/simulated_market_prices.py"
    assert stale.parent.is_dir()
    stale.write_text("# test-only stale build output", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "setup.py", "bdist_wheel", "--dist-dir", "rejected-wheel-output"],
        cwd=staging,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode != 0
    assert "Stale simulator in build output" in result.stderr
    assert not list((staging / "rejected-wheel-output").glob("*.whl"))


def test_actual_wheel_snapshot_and_shipped_tool_imports_without_source(
    customer_wheel, tmp_path
) -> None:
    # Replay only files explicitly selected by the final Docker stage. The
    # subprocess cwd and PYTHONPATH do not include this repository's source.
    shutil.copytree(
        ROOT / "apps", tmp_path / "apps",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for relative in (
        POLICY["runtime_scripts"] + POLICY["required_runtime_members"]
        + [POLICY["runtime_policy_path"]]
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    verify_runtime_tree(tmp_path, POLICY)
    env = os.environ.copy()
    dependency_paths = [
        path for path in sys.path
        if path and Path(path).name.startswith(".dnx") and "src" not in Path(path).parts
    ]
    # Wheels are installed directories, not importable ZIP applications: some
    # API subpackages are namespace packages. Replay the same no-dependency,
    # no-index install used by Docker, in an isolated temporary target.
    installed = customer_wheel.parent.parent / "installed-runtime"
    installation = subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
            "--target", str(installed), str(customer_wheel),
        ],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert installation.returncode == 0, installation.stdout + installation.stderr
    env["PYTHONPATH"] = os.pathsep.join([str(installed), *dependency_paths])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["EUROGAS_NEXUS_ENV"] = "test"
    env["EUROGAS_NEXUS_API_PROFILE"] = "development"
    # Do not inherit database/provider configuration into this import replay.
    for key in list(env):
        if key in {"DATABASE_URL", "RUNTIME_STORE_DATABASE_URL"} or "API_KEY" in key:
            del env[key]
    result = subprocess.run(
        [sys.executable, "scripts/release/verify_customer_artifact.py", "--runtime-root", "."],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Customer artifact verification PASS" in result.stdout


@pytest.mark.parametrize(
    "forbidden",
    [
        "eurogas_nexus/ingestion/simulated_market_prices.py",
        "eurogas_nexus/ingestion/simulated_market_prices.pyc",
        "eurogas_nexus/ingestion/__pycache__/simulated_market_prices.cpython-312.pyc",
        ".dnx-out/local-secret.txt",
        "tests/fixtures/sample.json",
    ],
)
def test_content_gate_refuses_injected_wheel_members(forbidden) -> None:
    with pytest.raises(ArtifactError):
        verify_members([*POLICY["required_wheel_members"], forbidden], POLICY)


def test_content_gate_refuses_missing_required_runtime_members() -> None:
    with pytest.raises(ArtifactError, match="missing"):
        verify_members(POLICY["required_wheel_members"][:-1], POLICY)


@pytest.mark.parametrize(
    "extra", ["scripts/ops/seed_future.py", ".dnx-pgdata/data", ".env", "tests/sample.json"]
)
def test_runtime_gate_refuses_unreviewed_script_or_local_data(tmp_path, extra) -> None:
    for relative in (
        POLICY["runtime_scripts"] + POLICY["required_runtime_members"]
        + [POLICY["runtime_policy_path"], extra]
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    with pytest.raises(ArtifactError):
        verify_runtime_tree(tmp_path, POLICY)


def test_runtime_gate_refuses_missing_startup_payload(tmp_path) -> None:
    for relative in (
        POLICY["runtime_scripts"] + POLICY["required_runtime_members"][1:]
        + [POLICY["runtime_policy_path"]]
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    with pytest.raises(ArtifactError, match="startup or migration"):
        verify_runtime_tree(tmp_path, POLICY)


def test_docker_copy_payload_matches_policy_and_excludes_local_context() -> None:
    dockerfile = (ROOT / "deploy/runtime/Dockerfile.api").read_text(encoding="utf-8")
    assert "COPY scripts ./scripts" not in dockerfile
    final_stage = re.split(r"(?m)^FROM\s+", dockerfile)[-1]
    instructions = final_stage.replace("\\\n", " ").splitlines()
    copied = []
    for line in instructions:
        if line.startswith("COPY scripts/"):
            copied.extend(line.split()[1:-1])
    assert set(copied) == set(POLICY["runtime_scripts"]) | {POLICY["runtime_policy_path"]}
    assert len(copied) == len(set(copied))
    assert "&& python scripts/release/verify_customer_artifact.py --wheel" in dockerfile
    assert "RUN python scripts/release/verify_customer_artifact.py" in final_stage
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".dnx*" in ignore
    assert "**/.dnx*" in ignore


def test_customer_compose_and_operator_allowlist_have_no_development_payload() -> None:
    compose = yaml.safe_load((ROOT / "deploy/runtime/compose.yaml").read_text(encoding="utf-8"))
    assert {"config-check", "migrate", "api", "public-ingestion"} <= set(compose["services"])
    assert not {"preview-seed", "simulated-prices"} & set(compose["services"])
    for service in compose["services"].values():
        for token in service.get("command", []):
            if token.startswith("scripts/"):
                assert token in POLICY["runtime_scripts"]
    bundle_policy = json.loads(
        (ROOT / "scripts/release/package_deployment_bundle.policy.json").read_text(encoding="utf-8")
    )
    assert not any("SIMULATED_MARKET" in entry["source"] for entry in bundle_policy["entries"])
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "python scripts/release/verify_customer_artifact.py" in workflow
    assert workflow.index("Reject development producers") < workflow.index(
        "- name: Record container acceptance evidence"
    )
