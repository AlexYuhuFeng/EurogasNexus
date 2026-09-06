#!/usr/bin/env python
"""Enforce the single canonical version contract.

Canonical source of truth: ``pyproject.toml`` ``[project] version``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"

PY_ASSIGNMENT = re.compile(
    r'^(?P<name>APPLICATION_VERSION|DEFAULT_RELEASE_CHANNEL)\s*=\s*"(?P<value>[^"]+)"\s*$'
)
CARGO_PACKAGE_RE = re.compile(
    r'^\[\[package\]\]\s*\nname\s*=\s*"eurogas-nexus-desktop"\s*\nversion\s*=\s*"([^"]+)"',
    re.MULTILINE,
)


def canonical_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = str(data["project"]["version"])
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        raise ValueError(f"Canonical pyproject version is not X.Y.Z: {version!r}")
    return version


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _read_python_version() -> str:
    text = _read("src/eurogas_nexus/version.py")
    for line in text.splitlines():
        match = PY_ASSIGNMENT.match(line)
        if match and match.group("name") == "APPLICATION_VERSION":
            return match.group("value")
    raise RuntimeError("APPLICATION_VERSION not found in src/eurogas_nexus/version.py")


def _write_python_version(value: str) -> None:
    path = ROOT / "src" / "eurogas_nexus" / "version.py"
    text = path.read_text(encoding="utf-8")
    lines = []
    replaced = False
    for line in text.splitlines():
        match = PY_ASSIGNMENT.match(line)
        if match and match.group("name") == "APPLICATION_VERSION":
            lines.append(f'APPLICATION_VERSION = "{value}"')
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise RuntimeError("APPLICATION_VERSION assignment not found.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_ts_version() -> str:
    text = _read("clients/web/src/app/releaseMetadata.ts")
    match = re.search(r'export const CLIENT_APPLICATION_VERSION = "([^"]+)";', text)
    if match is None:
        raise RuntimeError("CLIENT_APPLICATION_VERSION not found in releaseMetadata.ts")
    return match.group(1)


def _write_ts_version(value: str) -> None:
    path = ROOT / "clients" / "web" / "src" / "app" / "releaseMetadata.ts"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        re.sub(
            r'(export const CLIENT_APPLICATION_VERSION = ")[^"]+(";)',
            lambda match: f"{match.group(1)}{value}{match.group(2)}",
            text,
        ),
        encoding="utf-8",
    )


def machine_surfaces() -> list[dict]:
    """Version-bearing files that --write may update automatically."""

    return [
        {
            "kind": "py",
            "path": "src/eurogas_nexus/version.py",
            "write": lambda value: _write_python_version(value),
            "current": lambda: _read_python_version(),
        },
        {"kind": "json-key", "path": "clients/web/package.json", "key": "version"},
        {"kind": "json-root", "path": "clients/web/package-lock.json"},
        {"kind": "json-key", "path": "clients/desktop/package.json", "key": "version"},
        {"kind": "json-root", "path": "clients/desktop/package-lock.json"},
        {"kind": "json-key", "path": "clients/desktop/src-tauri/tauri.conf.json", "key": "version"},
        {"kind": "cargo-toml", "path": "clients/desktop/src-tauri/Cargo.toml"},
        {"kind": "cargo-lock", "path": "clients/desktop/src-tauri/Cargo.lock"},
        {
            "kind": "ts",
            "path": "clients/web/src/app/releaseMetadata.ts",
            "write": lambda value: _write_ts_version(value),
            "current": lambda: _read_ts_version(),
        },
    ]


def _surface_current(surface: dict) -> str:
    if "current" in surface:
        return surface["current"]()
    path = ROOT / surface["path"]
    text = path.read_text(encoding="utf-8")
    kind = surface["kind"]
    if kind == "json-key":
        return str(json.loads(text)[surface["key"]])
    if kind == "json-root":
        return str(json.loads(text)["version"])
    if kind == "cargo-toml":
        match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
        if match is None:
            raise RuntimeError(f"version not found in {surface['path']}")
        return match.group(1)
    if kind == "cargo-lock":
        match = CARGO_PACKAGE_RE.search(text)
        if match is None:
            raise RuntimeError(f"eurogas-nexus-desktop not found in {surface['path']}")
        return match.group(1)
    raise RuntimeError(f"unknown surface kind {kind}")


def _write_surface(surface: dict, value: str) -> None:
    if "write" in surface:
        surface["write"](value)
        return
    path = ROOT / surface["path"]
    text = path.read_text(encoding="utf-8")
    kind = surface["kind"]
    if kind == "json-key":
        data = json.loads(text)
        data[surface["key"]] = value
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return
    if kind == "json-root":
        data = json.loads(text)
        data["version"] = value
        data["packages"][""]["version"] = value
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return
    if kind == "cargo-toml":
        path.write_text(
            re.sub(
                r'^version\s*=\s*"[^"]+"\s*$',
                f'version = "{value}"',
                text,
                count=1,
                flags=re.MULTILINE,
            ),
            encoding="utf-8",
        )
        return
    if kind == "cargo-lock":
        path.write_text(
            CARGO_PACKAGE_RE.sub(
                f'[[package]]\nname = "eurogas-nexus-desktop"\nversion = "{value}"',
                text,
                count=1,
            ),
            encoding="utf-8",
        )
        return
    raise RuntimeError(f"unknown write kind {kind}")


def _require_text(relative: str, expected: str, label: str) -> tuple[str, bool, str]:
    text = _read(relative)
    ok = expected in text
    detail = f"{expected!r} present in {relative}" if ok else f"missing in {relative}"
    return label, ok, detail


def _require_version_or_template(relative: str, version: str, label: str) -> tuple[str, bool, str]:
    text = _read(relative)
    ok = version in text or "{VERSION}" in text
    detail = (
        f"version/template present in {relative}"
        if ok
        else f"neither {version!r} nor {{VERSION}} present in {relative}"
    )
    return label, ok, detail


def documentation_surfaces(version: str) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []
    checks.append(_require_text("README.md", f"Package version: `{version}`", "README"))
    checks.append(_require_text("CHANGELOG.md", f"package version `{version}`", "CHANGELOG"))
    checks.append(
        _require_version_or_template("docs/deployment/DEPLOYMENT_ROLES-EN.md", version, "roles EN")
    )
    checks.append(
        _require_version_or_template("docs/deployment/DEPLOYMENT_ROLES-CN.md", version, "roles CN")
    )
    checks.append(_require_text("docs/ontology/eurogas-nexus-grm.ttl", version, "GRM turtle"))
    checks.append(_require_text("docs/ontology/OWL_GAS_ROLE_MODEL.md", version, "OWL EN"))
    checks.append(_require_text("docs/ontology/OWL_GAS_ROLE_MODEL-CN.md", version, "OWL CN"))
    checks.append(_require_text("docs/ontology/europe-natural-gas.md", version, "ontology"))
    checks.append(
        _require_version_or_template("docs/operations/RELEASE_SIGNING.md", version, "signing")
    )
    return checks


def policy_surfaces() -> list[tuple[str, bool, str]]:
    """Surfaces that must not silently hard-code a divergent release version."""

    failures: list[tuple[str, bool, str]] = []
    workflow = _read(".github/workflows/release.yml")
    if "0.5.0" in workflow:
        failures.append(
            (
                ".github/workflows/release.yml",
                False,
                "hard-coded 0.5.0 found; derive artifact names/tags from release-context.json",
            )
        )
    else:
        failures.append((".github/workflows/release.yml", True, "no hard-coded release version"))

    config = _read("src/eurogas_nexus/core/config.py")
    if 'default="0.5.0"' in config:
        failures.append(("src/eurogas_nexus/core/config.py", False, "hard-coded version fallback"))
    else:
        failures.append(("src/eurogas_nexus/core/config.py", True, "uses runtime version module"))

    registry = _read("src/eurogas_nexus/domain/strategy_lab/registry.py")
    if 'application_version: str = "0.5.0"' in registry:
        failures.append(
            (
                "src/eurogas_nexus/domain/strategy_lab/registry.py",
                False,
                "hard-coded version fallback",
            )
        )
    else:
        failures.append(
            (
                "src/eurogas_nexus/domain/strategy_lab/registry.py",
                True,
                "uses runtime version module",
            )
        )

    client_metadata = _read("clients/web/src/app/releaseMetadata.ts")
    if f'CLIENT_MINIMUM_SUPPORTED_SERVER = "{canonical_version()}";' in client_metadata:
        failures.append(
            ("clients/web/src/app/releaseMetadata.ts", True, "client minimum server is canonical")
        )
    else:
        failures.append(
            (
                "clients/web/src/app/releaseMetadata.ts",
                False,
                "CLIENT_MINIMUM_SUPPORTED_SERVER diverges from canonical version",
            )
        )

    for script in (
        "scripts/install/windows/Deploy-EurogasNexus.ps1",
        "scripts/install/windows/Install-EurogasNexusServerRuntime.ps1",
        "scripts/release/build_release.ps1",
    ):
        text = _read(script)
        if "0.5.0" in text or "0.5-preview" in text:
            failures.append((script, False, "hard-coded release version/tag in script"))
        else:
            failures.append((script, True, "no hard-coded release version"))
    return failures


def evaluate() -> dict:
    version = canonical_version()
    machine = []
    for surface in machine_surfaces():
        try:
            current = _surface_current(surface)
        except Exception as exc:
            machine.append({"path": surface["path"], "ok": False, "detail": exc.__class__.__name__})
            continue
        machine.append(
            {
                "path": surface["path"],
                "ok": current == version,
                "expected": version,
                "actual": current,
            }
        )
    docs = [
        {"path": path, "ok": ok, "detail": detail}
        for path, ok, detail in documentation_surfaces(version)
    ]
    policy = [{"path": path, "ok": ok, "detail": detail} for path, ok, detail in policy_surfaces()]
    failures = [item for item in [*machine, *docs, *policy] if not item["ok"]]
    return {
        "ok": not failures,
        "canonical_version": version,
        "surfaces": [*machine, *docs, *policy],
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="sync machine-readable files")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    version = canonical_version()
    if args.write:
        for surface in machine_surfaces():
            _write_surface(surface, version)
        print(f"Machine version surfaces synchronized to {version}.", file=sys.stderr)

    report = evaluate()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["surfaces"]:
            state = "ok" if item["ok"] else "FAIL"
            detail = item.get("detail")
            actual = item.get("actual")
            suffix = f" ({detail})" if detail else (f" actual={actual!r}" if actual else "")
            print(f"{state:4} {item['path']}{suffix}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
