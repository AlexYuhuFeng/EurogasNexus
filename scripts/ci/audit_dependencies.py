"""Offline dependency license audit against the AGENTS.md license policy.

Scans an installed site-packages directory (default ``.deps``) by reading each
``*.dist-info/METADATA``, extracts license fields/classifiers, and fails closed
on any license matching the forbidden set (GPL-family, SSPL, BUSL, Elastic,
Redis-RSAL, Commons-Clause, PolyForm). Unknown licenses are reported
prominently but do not fail the build (they still require review before
release).

Usage:
    python scripts/ci/audit_dependencies.py [site_packages_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN_LICENSE_TERMS = (
    "gpl",
    "lgpl",
    "agpl",
    "sspl",
    "busl",
    "elastic license",
    "rsal",
    "commons clause",
    "commons-clause",
    "polyform",
)

FORBIDDEN_CLASSIFIER_TERMS = (
    "gpl",
    "lgpl",
    "agpl",
    "sspl",
    "busl",
    "elastic",
    "rsal",
    "commons clause",
    "polyform",
)

LICENSE_CLASSIFIER_PREFIX = "License :: OSI Approved :: "


def _metadata_paths(site_packages: Path) -> list[Path]:
    return sorted(site_packages.glob("*.dist-info/METADATA"))


def _read_metadata(metadata_path: Path) -> tuple[str, list[str], list[str]]:
    """Return (name, license fields, license classifiers)."""

    name = metadata_path.parent.name.removesuffix(".dist-info")
    license_fields: list[str] = []
    classifiers: list[str] = []
    for line in metadata_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("License:"):
            license_fields.append(line.split(":", 1)[1].strip())
        elif line.startswith("Classifier: " + LICENSE_CLASSIFIER_PREFIX):
            classifiers.append(line.split("::", 2)[-1].strip())
    return name, license_fields, classifiers


def _forbidden_hit(text: str, terms: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for term in terms:
        if term in lowered:
            return term
    return None


def audit(site_packages: Path) -> int:
    """    Audit installed packages against the approved dependency policy.

    Returns:
        Exit code: 0 clean, 1 when violations are found."""
    violations: list[str] = []
    unknowns: list[str] = []
    ok: list[str] = []

    for metadata_path in _metadata_paths(site_packages):
        name, license_fields, classifiers = _read_metadata(metadata_path)
        combined = " | ".join([*license_fields, *classifiers])
        if not combined.strip():
            unknowns.append(name)
            continue
        hit = _forbidden_hit(combined, FORBIDDEN_LICENSE_TERMS) or _forbidden_hit(
            combined, FORBIDDEN_CLASSIFIER_TERMS
        )
        if hit is not None:
            violations.append(f"{name}: {combined!r} (forbidden term {hit!r})")
        else:
            ok.append(f"{name}: {combined[:80]}")

    print(f"Audited {len(ok) + len(unknowns) + len(violations)} packages")
    if unknowns:
        print("UNKNOWN LICENSE (requires review):")
        print("  " + "\n  ".join(sorted(unknowns)))
    if violations:
        print("FORBIDDEN LICENSE (fail-closed):")
        print("  " + "\n  ".join(sorted(violations)))
        return 1
    print("License policy: OK (no forbidden licenses)")
    return 0


def main(argv: list[str] | None = None) -> int:
    """    CLI entry point for the dependency audit."""
    args = list(argv) if argv is not None else sys.argv[1:]
    target = args[0] if args else ".deps"
    site_packages = Path(target)
    if not site_packages.is_dir():
        print(f"site-packages directory not found: {site_packages}")
        return 2
    return audit(site_packages)


if __name__ == "__main__":
    raise SystemExit(main())
