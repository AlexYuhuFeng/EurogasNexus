"""Shared artifact helpers: naming, hashing, scanning, checksum files."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

EXCLUDED_FROM_DISTRIBUTION = {
    "release-context.json",
    "checksums.json",
    "SHA256SUMS",
    "release-notes.md",
    "release-dry-run-report.json",
}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def artifact_files(artifacts_dir: str | Path) -> list[Path]:
    root = Path(artifacts_dir)
    candidates = [path for path in root.rglob("*") if path.is_file()]
    return sorted(
        [
            path
            for path in candidates
            if path.name not in EXCLUDED_FROM_DISTRIBUTION
            and "evidence" not in path.relative_to(root).parts
            and "sbom" not in path.relative_to(root).parts[:1]
        ],
        key=lambda path: str(path.relative_to(root)),
    )


def relative_name(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def artifact_platform_arch(name: str) -> tuple[str, str]:
    lowered = name.lower()
    if "windows" in lowered or lowered.endswith(".exe") or lowered.endswith(".msi"):
        platform = "windows"
    elif "linux-arm64" in lowered or "arm64" in lowered:
        platform = "linux"
    elif "linux" in lowered or lowered.endswith(".deb") or lowered.endswith(".appimage"):
        platform = "linux"
    elif lowered.endswith(".tar.gz") and "web" in lowered:
        platform = "web"
    elif lowered.endswith(".zip"):
        platform = "windows"
    else:
        platform = "generic"
    if "arm64" in lowered:
        arch = "arm64"
    elif "x64" in lowered or "amd64" in lowered:
        arch = "x64"
    else:
        arch = "all"
    return platform, arch


def artifact_type(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".exe"):
        return "windows-nsis-installer"
    if lowered.endswith(".msi"):
        return "windows-msi-installer"
    if lowered.endswith(".deb"):
        return "debian-package"
    if lowered.endswith(".tar.gz") and "web" in lowered:
        return "web-bundle"
    if lowered.endswith(".zip"):
        return "deployment-bundle"
    if lowered.endswith(".json"):
        return "metadata"
    return "artifact"


def checksum_map(artifacts_dir: str | Path, *, include_manifest: bool = False) -> dict[str, str]:
    root = Path(artifacts_dir)
    result: dict[str, str] = {}
    candidates = [path for path in root.rglob("*") if path.is_file()]
    for path in sorted(candidates, key=lambda item: relative_name(item, root)):
        name = path.name
        relative = relative_name(path, root)
        if name in {
            "SHA256SUMS",
            "checksums.json",
            "release-context.json",
            "release-dry-run-report.json",
        }:
            continue
        if relative.startswith("sbom/") and not name.endswith(".tar.gz"):
            continue
        if relative.startswith("release-evidence/") or relative.startswith("image-metadata/"):
            continue
        if name == "release-manifest.json" and not include_manifest:
            continue
        result[relative_name(path, root)] = sha256_file(path)
    return result


def write_checksums(artifacts_dir: str | Path, *, include_manifest: bool = False) -> Path:
    root = Path(artifacts_dir)
    values = checksum_map(root, include_manifest=include_manifest)
    lines = [f"{digest}  {name}" for name, digest in sorted(values.items())]
    checksum_file = root / "SHA256SUMS"
    checksum_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "checksums.json").write_text(
        json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return checksum_file


def verify_checksums(artifacts_dir: str | Path, require_manifest: bool = True) -> dict[str, Any]:
    root = Path(artifacts_dir)
    checksum_file = root / "SHA256SUMS"
    if not checksum_file.is_file():
        return {"ok": False, "errors": ["SHA256SUMS missing"]}
    entries: dict[str, str] = {}
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([0-9a-f]{64})\s{2}(.+)$", line)
        if match is None:
            return {"ok": False, "errors": [f"invalid checksum line: {line!r}"]}
        entries[match.group(2)] = match.group(1)
    errors = []
    for relative, expected in entries.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing file {relative}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(f"checksum mismatch for {relative}")
    if require_manifest and "release-manifest.json" not in entries:
        errors.append("release-manifest.json is not covered by SHA256SUMS")
    return {
        "ok": not errors,
        "errors": errors,
        "verified": len(entries) - len(errors),
        "total": len(entries),
    }
