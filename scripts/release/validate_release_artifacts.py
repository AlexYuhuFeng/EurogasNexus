#!/usr/bin/env python
"""Validate a complete release bundle before publishing.

Checks artifact naming, manifest completeness, checksum reconciliation, SBOM
coverage and the absence of secret-shaped files. The checksums are expected to
have been computed after final signing/packaging.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.release_artifacts import sha256_file, verify_checksums  # noqa: E402
from scripts.release.release_metadata import read_context  # noqa: E402

SECRET_FILENAMES = {".env", ".pfx", ".p12", ".pem", ".key", "id_rsa", "private.key"}


def expected_artifacts(context: dict) -> list[str]:
    version = context["release_version"].lstrip("v")
    return [
        f"Eurogas-Nexus-Client-{version}-windows-x64-setup.exe",
        f"Eurogas-Nexus-Client-{version}-linux-x64.deb",
        f"Eurogas-Nexus-Client-{version}-linux-arm64.deb",
        f"Eurogas-Nexus-Server-{version}-Windows.zip",
        f"eurogas-nexus-web-{version}.tar.gz",
        f"eurogas-nexus-sboms-{version}.tar.gz",
        "release-manifest.json",
        "SHA256SUMS",
    ]


def validate(
    context: dict,
    manifest: dict,
    artifacts_dir: Path,
    sbom_dir: Path,
    *,
    allow_missing_platform_artifacts: bool = False,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if manifest["version"] != context["app_version"]:
        errors.append("manifest application version != release context")
    if manifest["release_version"] != context["release_version"]:
        errors.append("manifest release version != release context")
    if manifest["channel"] != context["channel"]:
        errors.append("manifest channel != release context")
    if manifest["git_sha"] != context["git_sha"]:
        errors.append("manifest git_sha != release context")
    if manifest["database_schema_revision"] != context["database_schema_revision"]:
        errors.append("manifest database schema revision != release context")

    checksums = verify_checksums(artifacts_dir)
    if not checksums["ok"]:
        errors.extend(checksums["errors"])

    manifest_hash = sha256_file(artifacts_dir / "release-manifest.json")
    checksum_entries = {
        line.split("  ", 1)[1]: line.split("  ", 1)[0]
        for line in (artifacts_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    }
    if checksum_entries.get("release-manifest.json") != manifest_hash:
        errors.append("SHA256SUMS does not contain the final release-manifest.json hash")

    actual = {path.name: path for path in artifacts_dir.iterdir() if path.is_file()}
    for expected in expected_artifacts(context):
        if expected not in actual:
            if allow_missing_platform_artifacts and expected in {
                f"Eurogas-Nexus-Client-{context['release_version'].lstrip('v')}-linux-x64.deb",
                f"Eurogas-Nexus-Client-{context['release_version'].lstrip('v')}-linux-arm64.deb",
                f"Eurogas-Nexus-Client-{context['release_version'].lstrip('v')}-windows-x64-setup.exe",
            }:
                warnings.append(f"platform artifact not present in local dry-run: {expected}")
            else:
                errors.append(f"expected release artifact missing: {expected}")

    for item in manifest["artifacts"]:
        path = artifacts_dir / item["path"]
        if not path.is_file():
            errors.append(f"manifest artifact missing on disk: {item['path']}")
            continue
        if path.stat().st_size != item["size"]:
            errors.append(f"size mismatch for {item['name']}")
        if sha256_file(path) != item["sha256"]:
            errors.append(f"manifest hash mismatch for {item['name']}")
        if checksum_entries.get(item["path"]) != item["sha256"]:
            errors.append(f"SHA256SUMS hash missing/mismatched for {item['path']}")
        if item["channel" if False else "signing_state"] in {
            "authenticode_verified",
            "gpg_signed_verified",
            "checksum_attestation_baseline",
            "unsigned_pending_external",
        }:
            continue
        errors.append(f"invalid signing_state for {item['name']}: {item['signing_state']}")

    for sbom in manifest["sbom_files"]:
        path = sbom_dir / sbom["name"]
        if not path.is_file():
            errors.append(f"SBOM missing: {sbom['name']}")
        elif sha256_file(path) != sbom["sha256"]:
            errors.append(f"SBOM hash mismatch: {sbom['name']}")

    for path in artifacts_dir.rglob("*"):
        if path.name.lower() in SECRET_FILENAMES or path.suffix.lower() in {".pfx", ".p12", ".pem"}:
            errors.append(
                f"secret-shaped file in release bundle: {path.relative_to(artifacts_dir)}"
            )
    for path in artifacts_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".txt", ".asc"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
            errors.append(f"private key material found in {path.name}")

    image = manifest["runtime_images"][0]
    if not image["digest"]:
        warnings.append("container digest is empty; digest must be recorded before GA")
    if "sha256:" in image["digest"]:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image["digest"]):
            errors.append("container digest is malformed")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--sbom-dir", default="release-assets/sbom")
    parser.add_argument(
        "--allow-missing-platform-artifacts",
        action="store_true",
        help="local dry-run only; strict CI publishing never passes this flag",
    )
    args = parser.parse_args(argv)

    context = read_context(args.context)
    manifest = json.loads(
        (Path(args.artifacts_dir) / "release-manifest.json").read_text(encoding="utf-8")
    )
    report = validate(
        context,
        manifest,
        Path(args.artifacts_dir),
        Path(args.sbom_dir),
        allow_missing_platform_artifacts=args.allow_missing_platform_artifacts,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
