#!/usr/bin/env python
"""Generate SPDX 2.3 SBOMs from the enforced dependency locks.

Covers Python runtime dependencies, Web Node dependencies, Desktop Node
dependencies and Desktop Rust dependencies. A machine-readable
``sbom-manifest.json`` maps release artifacts to their SBOM files and a
``THIRD_PARTY_NOTICES.md`` is generated for shipped dependency notices.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

ROOT = Path(__file__).resolve().parents[2]


def _purl(ecosystem: str, name: str, version: str) -> str:
    normalized = name.lower().replace("_", "-")
    return f"pkg:{ecosystem}/{normalized}@{version}"


def _spdx_document(name: str, namespace: str) -> dict[str, Any]:
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": name,
        "documentNamespace": namespace,
        "creationInfo": {
            "created": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "creators": ["Tool: eurogas-nexus-release-tooling"],
        },
        "packages": [],
        "relationships": [],
    }


def _add_packages(document: dict[str, Any], packages: list[dict]) -> None:
    for index, item in enumerate(packages):
        spdx_id = f"SPDXRef-Package-{index + 1}"
        document["packages"].append(
            {
                "SPDXID": spdx_id,
                "name": item["name"],
                "versionInfo": item["version"],
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": item.get("license") or "NOASSERTION",
                "copyrightText": "NOASSERTION",
                "supplier": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": item["purl"],
                    }
                ],
            }
        )
        document["relationships"].append(
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relatedSpdxElement": spdx_id,
                "relationshipType": "DESCRIBES",
            }
        )


def python_packages() -> list[dict]:
    text = (ROOT / "requirements-runtime.lock").read_text(encoding="utf-8")
    packages = []
    for match in re.finditer(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+\-]+)", text, re.MULTILINE):
        name, version = match.group(1), match.group(2)
        if name in {"eurogas-nexus"}:
            continue
        packages.append(
            {
                "name": name,
                "version": version,
                "license": None,
                "purl": _purl("pypi", name, version),
            }
        )
    return packages


def _npm_packages(package_lock_path: Path) -> list[dict]:
    data = json.loads(package_lock_path.read_text(encoding="utf-8"))
    packages = []
    for spec, item in data.get("packages", {}).items():
        if not spec:
            continue
        name = item.get("name") or spec.removeprefix("node_modules/")
        version = item.get("version")
        if not name or not version:
            continue
        if name in {"eurogas-nexus-web", "eurogas-nexus-desktop"}:
            continue
        packages.append(
            {
                "name": name,
                "version": version,
                "license": item.get("license"),
                "purl": _purl("npm", name, version),
            }
        )
    return packages


def rust_packages() -> list[dict]:
    text = (ROOT / "clients" / "desktop" / "src-tauri" / "Cargo.lock").read_text(encoding="utf-8")
    packages = []
    for match in re.finditer(
        r"^\[\[package\]\]\s*\nname\s*=\s*\"([^\"]+)\"\s*\nversion\s*=\s*\"([^\"]+)\"",
        text,
        re.MULTILINE,
    ):
        name, version = match.group(1), match.group(2)
        if name == "eurogas-nexus-desktop":
            continue
        packages.append(
            {
                "name": name,
                "version": version,
                "license": None,
                "purl": _purl("cargo", name, version),
            }
        )
    return packages


def write_component_sbom(output_dir: Path, key: str, packages: list[dict]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    document = _spdx_document(
        f"eurogas-nexus-{key}",
        f"https://eurogas-nexus.invalid/spdx/eurogas-nexus-{key}",
    )
    _add_packages(document, packages)
    target = output_dir / f"eurogas-nexus-{key}.spdx.json"
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def notices(packages_by_component: dict[str, list[dict]]) -> str:
    lines = [
        "# Third-Party Notices",
        "",
        "Eurogas Nexus is proprietary software. The dependency locks below were",
        "used by the corresponding release build. This file is generated from the",
        "locked dependency metadata; `NOASSERTION` means the lock did not carry a",
        "machine-readable license expression for that package.",
        "",
    ]
    for component, packages in sorted(packages_by_component.items()):
        lines.append(f"## {component}")
        lines.append("")
        if not packages:
            lines.append("_No packages recorded._")
            continue
        for item in sorted(
            packages, key=lambda package: (package["name"].lower(), package["version"])
        ):
            license_text = item.get("license") or "NOASSERTION"
            lines.append(f"- {item['name']} {item['version']} ({license_text})")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="release-assets/sbom")
    parser.add_argument("--notices", default="release-assets/sbom/THIRD_PARTY_NOTICES.md")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    components = {
        "python-runtime": python_packages(),
        "web-node": _npm_packages(ROOT / "clients" / "web" / "package-lock.json"),
        "desktop-node": _npm_packages(ROOT / "clients" / "desktop" / "package-lock.json"),
        "desktop-rust": rust_packages(),
    }
    files = {
        key: write_component_sbom(output_dir, key, packages) for key, packages in components.items()
    }
    notices_path = Path(args.notices)
    notices_path.write_text(notices(components), encoding="utf-8")

    def sbom_names_for_artifact(name: str) -> list[str]:
        lowered = name.lower()
        if "server" in lowered and lowered.endswith(".zip"):
            return [files["python-runtime"].name]
        if "web" in lowered and lowered.endswith(".tar.gz"):
            return [files["web-node"].name]
        if lowered.endswith(".exe") or lowered.endswith(".msi") or lowered.endswith(".deb"):
            return [files["desktop-node"].name, files["desktop-rust"].name, files["web-node"].name]
        return []

    manifest = {
        "schema_version": 1,
        "format": "SPDX-2.3",
        "components": {key: path.name for key, path in files.items()},
        "artifacts": {
            "Eurogas-Nexus-Client-Windows-setup.exe": sbom_names_for_artifact("windows-setup.exe"),
            "Eurogas-Nexus-Client-Windows.deb": sbom_names_for_artifact("windows.deb"),
        },
        "notes": notices_path.name,
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    manifest["artifacts"] = {"_pattern": "see build_release_manifest.py for per-artifact sbom_ref"}
    (output_dir / "sbom-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"ok": True, "output_dir": str(output_dir), "components": manifest["components"]},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
