"""Fail closed on development simulation producers in actual customer artifacts.

Wheel mode inspects ZIP members, not source-selection claims. Runtime mode
inspects /app and the interpreter's installed distribution, then exercises
the snapshot metadata seam and imports the allowlisted tools without invoking
their commands. No database connection, provider request or credential read is
needed. Historical simulator metadata and defensive filters are deliberately
retained; a simulation-free artifact is not evidence that an existing database
contains no simulated rows.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

POLICY_PATH = Path(__file__).with_name("runtime_artifact_policy.json")


class ArtifactError(RuntimeError):
    """The artifact violates the customer content policy."""


def load_policy(path: Path = POLICY_PATH) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("schema_version") != 1:
        raise ArtifactError("Unsupported customer artifact policy")
    for key in (
        "runtime_scripts", "required_runtime_members",
        "required_wheel_members", "excluded_wheel_modules"
    ):
        values = policy.get(key)
        if not isinstance(values, list) or not values or len(values) != len(set(values)):
            raise ArtifactError(f"Invalid policy list: {key}")
        for value in values:
            parts = PurePosixPath(value).parts
            if not isinstance(value, str) or not parts or ".." in parts or value.startswith("/"):
                raise ArtifactError(f"Unsafe policy path: {key}")
    return policy


def verify_members(members: list[str], policy: dict) -> None:
    """Check installed wheel inventory or wheel ZIP inventory."""
    if not members or len(members) != len(set(members)):
        raise ArtifactError("Empty or duplicate wheel inventory")
    for member in members:
        parts = PurePosixPath(member).parts
        if any(part.startswith(".dnx") for part in parts):
            raise ArtifactError("Local development artifacts found in wheel")
        if any(
            member.startswith(module + ".")
            or (PurePosixPath(module).name + ".") in PurePosixPath(member).name
            for module in policy["excluded_wheel_modules"]
        ):
            raise ArtifactError("Executable market simulator found in wheel")
        if parts and parts[0] in {"tests", "data", "scripts", "deploy"}:
            raise ArtifactError("Development or unreviewed payload found in wheel")
    missing = set(policy["required_wheel_members"]) - set(members)
    if missing:
        raise ArtifactError("Required runtime wheel members missing: " + ", ".join(sorted(missing)))


def verify_wheel(path: Path, policy: dict) -> None:
    with zipfile.ZipFile(path) as archive:
        verify_members([item.filename for item in archive.infolist() if not item.is_dir()], policy)


def verify_runtime_tree(root: Path, policy: dict) -> None:
    """Exact script allowlist and no local/development directories in /app."""
    scripts = root / "scripts"
    if not scripts.is_dir():
        raise ArtifactError("Runtime scripts directory missing")
    actual = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ArtifactError("Symlink found in customer runtime payload")
        if any(part.startswith(".dnx") for part in relative.parts):
            raise ArtifactError("Local development artifacts found in runtime")
        if relative.parts[0] not in {
            "scripts", "apps", "alembic", "alembic.ini", "requirements-runtime.lock"
        }:
            raise ArtifactError("Unreviewed payload found in runtime")
        if relative.parts[0] == "scripts" and path.is_file():
            # Import checks may create bytecode on a local replay; source payload
            # selection is still exact. Docker sets PYTHONDONTWRITEBYTECODE=1.
            if "__pycache__" not in relative.parts:
                actual.add(relative.as_posix())
    expected = set(policy["runtime_scripts"]) | {policy["runtime_policy_path"]}
    if actual != expected:
        raise ArtifactError("Runtime script allowlist mismatch")
    if any(not (root / member).is_file() for member in policy["required_runtime_members"]):
        raise ArtifactError("Required startup or migration payload missing")


def verify_runtime_imports(root: Path, policy: dict) -> None:
    """Import shipped tools and the metadata seam; never call operational main()."""
    sys.path.insert(0, str(root))
    for path in policy["runtime_scripts"]:
        importlib.import_module(path.removesuffix(".py").replace("/", "."))
    from apps.api.main import app
    from eurogas_nexus.application.data_platform_snapshots import _model_calculation_versions

    if not app.routes:
        raise ArtifactError("API entrypoint has no routes")
    if _model_calculation_versions()["market_simulator_version"] != "sim-market-v1":
        raise ArtifactError("Historical simulator provenance version changed")
    try:
        importlib.import_module("eurogas_nexus.ingestion.simulated_market_prices")
    except ModuleNotFoundError as error:
        if error.name != "eurogas_nexus.ingestion.simulated_market_prices":
            raise
    else:
        raise ArtifactError("Executable simulator is importable in customer runtime")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--runtime-root", type=Path, default=Path("/app"))
    args = parser.parse_args(argv)
    try:
        policy = load_policy()
        if args.wheel:
            verify_wheel(args.wheel, policy)
        else:
            verify_runtime_tree(args.runtime_root, policy)
            distribution = importlib.metadata.distribution("eurogas-nexus")
            verify_members(
                [str(path).replace("\\", "/") for path in distribution.files or []], policy
            )
            verify_runtime_imports(args.runtime_root, policy)
    except Exception as error:
        # No raw import/tool errors: they may disclose deployment configuration.
        print(f"Customer artifact verification FAIL ({type(error).__name__})")
        return 1
    print("Customer artifact verification PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
