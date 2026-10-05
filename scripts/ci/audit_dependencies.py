"""Offline dependency license audit against docs/policies/DEPENDENCY_POLICY.md.

Scans an installed Python site-packages directory (default ``.deps``) by
reading each ``*.dist-info/METADATA`` with the standard library email parser,
and fails closed on license text matching the restricted set (GPL-family,
SSPL, BUSL, Elastic, Redis-RSAL, Commons-Clause, PolyForm).

Per the Core Metadata specification, a ``License-Expression`` header replaces
the legacy ``License`` header and takes precedence when both are present; every
``License ::`` classifier is read, not only the OSI-approved subset; and folded
or repeated headers follow email/RFC 5322 rules instead of ad-hoc line
parsing.

This is a review-required detection, not a legal determination: a clean result
means "no restricted license terms were detected in the scanned Python
metadata", not a commercial clearance. It does not read full license texts and
does not cover Node or Rust dependencies; see the dependency policy for the
scope and its outstanding limitations. Unknown licenses are listed for review;
missing, unreadable or malformed metadata -- including a target with no
distribution metadata at all -- fails closed, because nothing was audited.

Usage:
    python scripts/ci/audit_dependencies.py [site_packages_dir]
"""

from __future__ import annotations

import email
import email.errors
import email.policy
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

LICENSE_CLASSIFIER_PREFIX = "License ::"
LICENSE_EXPRESSION_HEADER = "License-Expression"
LEGACY_LICENSE_HEADER = "License"


def _dist_info_dirs(site_packages: Path) -> list[Path]:
    """Return every ``*.dist-info`` directory, including ones without METADATA."""

    return sorted(path for path in site_packages.glob("*.dist-info") if path.is_dir())


def _distribution_name(dist_info_dir: Path) -> str:
    """Derive the distribution name from its dist-info directory name."""

    return dist_info_dir.name.removesuffix(".dist-info")


def _normalized(value: object) -> str:
    """Collapse header folding and whitespace runs into single spaces."""

    return " ".join(str(value).split())


def _header_values(message: email.message.Message, header: str) -> list[str]:
    """Return every non-empty occurrence of ``header``, whitespace-normalised."""

    values = [_normalized(value) for value in message.get_all(header, [])]
    return [value for value in values if value]


def _read_metadata(metadata_path: Path) -> tuple[str, list[str], str | None]:
    """Return (distribution name, license evidence, metadata problem).

    The METADATA file is parsed with the standard library email parser, so
    folded headers, repeated headers and header case follow email rules rather
    than ad-hoc line parsing. A returned problem means the distribution could
    not be audited; callers fail closed instead of treating it as clean.
    """

    name = _distribution_name(metadata_path.parent)
    try:
        raw = metadata_path.read_bytes()
    except OSError as exc:
        return name, [], f"{name}: unreadable METADATA ({exc.__class__.__name__})"

    try:
        message = email.message_from_bytes(raw, policy=email.policy.default)
    except email.errors.MessageError as exc:
        return name, [], f"{name}: unparseable METADATA ({exc.__class__.__name__})"

    defects = sorted({type(defect).__name__ for defect in message.defects})
    if defects:
        return name, [], f"{name}: malformed METADATA ({', '.join(defects)})"
    if not message.items():
        return name, [], f"{name}: empty METADATA (no headers)"

    evidence: list[str] = []
    expressions = _header_values(message, LICENSE_EXPRESSION_HEADER)
    if expressions:
        # Core Metadata: License-Expression replaces License; when both are
        # present, the expression takes precedence.
        evidence.extend(f"License-Expression: {value}" for value in expressions)
    else:
        evidence.extend(
            f"License: {value}" for value in _header_values(message, LEGACY_LICENSE_HEADER)
        )

    for value in message.get_all("Classifier", []):
        classifier = _normalized(value)
        if classifier.startswith(LICENSE_CLASSIFIER_PREFIX):
            evidence.append(f"Classifier: {classifier}")

    return name, evidence, None


def _forbidden_hit(text: str, terms: tuple[str, ...]) -> str | None:
    """Return the first restricted term present in ``text``, if any."""

    lowered = text.lower()
    for term in terms:
        if term in lowered:
            return term
    return None


def audit(site_packages: Path) -> int:
    """Audit installed distributions against the approved dependency policy.

    Returns:
        Exit code: 0 when no restricted license terms were detected, 1 when
        restricted terms or unauditable metadata were found."""
    violations: list[str] = []
    problems: list[str] = []
    unknowns: list[str] = []
    ok: list[str] = []

    dist_info_dirs = _dist_info_dirs(site_packages)
    if not dist_info_dirs:
        print(f"No distribution metadata (*.dist-info) found under {site_packages}.")
        print("Refusing to report a clean audit: nothing was audited.")
        return 1

    for dist_info_dir in dist_info_dirs:
        metadata_path = dist_info_dir / "METADATA"
        if not metadata_path.is_file():
            problems.append(f"{_distribution_name(dist_info_dir)}: no METADATA file")
            continue

        name, evidence, problem = _read_metadata(metadata_path)
        if problem is not None:
            problems.append(problem)
            continue

        combined = " | ".join(evidence)
        if not combined.strip():
            unknowns.append(name)
            continue
        hit = _forbidden_hit(combined, FORBIDDEN_LICENSE_TERMS) or _forbidden_hit(
            combined, FORBIDDEN_CLASSIFIER_TERMS
        )
        if hit is not None:
            violations.append(f"{name}: {combined!r} (restricted term {hit!r})")
        else:
            ok.append(f"{name}: {combined[:80]}")

    print(f"Audited {len(ok) + len(unknowns) + len(violations) + len(problems)} packages")
    print(
        "Scope: installed Python dist-info metadata only; Node, Rust and full "
        "license text review are not covered."
    )
    if unknowns:
        print("UNKNOWN LICENSE (requires review; not a clearance):")
        print("  " + "\n  ".join(sorted(unknowns)))
    if problems:
        print("METADATA PROBLEMS (fail-closed; these distributions were not audited):")
        print("  " + "\n  ".join(sorted(problems)))
    if violations:
        print(
            "FORBIDDEN LICENSE TERMS (fail-closed; review-required detection, "
            "not a legal determination):"
        )
        print("  " + "\n  ".join(sorted(violations)))
    if problems or violations:
        return 1
    print(
        "License policy: OK (no restricted license terms detected in the scanned "
        "Python metadata; review-required detection, not a commercial clearance)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the dependency audit."""
    args = list(argv) if argv is not None else sys.argv[1:]
    target = args[0] if args else ".deps"
    site_packages = Path(target)
    if not site_packages.is_dir():
        print(f"site-packages directory not found: {site_packages}")
        return 2
    return audit(site_packages)


if __name__ == "__main__":
    raise SystemExit(main())
