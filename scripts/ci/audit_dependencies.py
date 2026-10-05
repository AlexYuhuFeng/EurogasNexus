"""Offline dependency license audit against docs/policies/DEPENDENCY_POLICY.md.

Python mode (default / positional argument) scans an installed Python
site-packages directory (default ``.deps``) by reading each
``*.dist-info/METADATA`` with the standard library email parser, and fails
closed on license text matching the restricted set (GPL-family, SSPL, BUSL,
Elastic, Redis-RSAL, Commons-Clause, PolyForm).

npm mode (``--npm-lock PATH``, repeatable) audits the exact npm
``package-lock.json`` files named on the command line with the shared
structured lock inventory reader from ``scripts.release.generate_sboms``: the
reader's package identity, nesting/scoping and workspace-link exclusion
behaviour is reused, not re-implemented. Every inventory entry must carry a
non-blank string license that is not ``UNLICENSED``, is not a file-only
reference such as ``SEE LICENSE IN ...``, and contains no restricted term
anywhere -- an ``OR``/``WITH`` expression is never approved because one branch
is permissive. The npm inventory covers the whole lock file, dev and optional
entries included: that is conservative lock coverage, not shipped-artifact
proof, and only the named lock files are read (never an installed
``node_modules``).

Per the Core Metadata specification, a ``License-Expression`` header replaces
the legacy ``License`` header and takes precedence when both are present; every
``License ::`` classifier is read, not only the OSI-approved subset; and folded
or repeated headers follow email/RFC 5322 rules instead of ad-hoc line
parsing.

This is a review-required detection, not a legal determination: a clean result
means "no restricted license terms were detected in the scanned metadata",
not a commercial clearance. It does not read full license texts and does not
cover Rust dependencies or artifact redistribution; see the dependency policy
for the scope and its outstanding limitations. Unknown Python licenses are
listed for review; missing, unreadable or malformed Python metadata -- including
a target with no distribution metadata at all -- fails closed, because nothing
was audited. An npm lock the shared reader cannot fully inventory also fails
closed, and neither mode interprets SPDX ``OR``/``WITH`` expressions legally.

Usage:
    python scripts/ci/audit_dependencies.py [site_packages_dir]
    python scripts/ci/audit_dependencies.py --npm-lock clients/web/package-lock.json \
        --npm-lock clients/desktop/package-lock.json
"""

from __future__ import annotations

import email
import email.errors
import email.policy
import re
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

NPM_LOCK_FLAG = "--npm-lock"

#: License values that name a file instead of an expression. ``SEE LICENSE IN``
#: is caught separately (it can carry any file name); this pattern catches bare
#: license-file references such as ``LICENSE``, ``./LICENSE.md``,
#: ``docs/COPYING`` or ``NOTICE.txt``.
_NPM_FILE_REFERENCE_RE = re.compile(
    r"(?:[A-Za-z0-9._-]+/)*(?:licen[cs]e|copying|notice)(?:[._-][A-Za-z0-9._-]+)*",
    re.IGNORECASE,
)


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
        "Scope: installed Python dist-info metadata only; this scan does not cover "
        "npm locks (use --npm-lock), Rust or full license texts."
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


def _npm_license_problem(value: object) -> str | None:
    """Return a fail-closed reason for one npm license value, or None.

    Reasons cover missing, blank and non-string values, the explicit
    ``UNLICENSED`` marker, file-only references pending review, and restricted
    terms anywhere in the expression -- including inside an ``OR``/``WITH``
    combination, which is never approved because one branch is permissive.
    """

    if value is None:
        return "missing 'license' value"
    if not isinstance(value, str):
        return f"non-string 'license' value ({type(value).__name__})"
    expression = value.strip()
    if not expression:
        return "blank 'license' value"
    lowered = expression.casefold()
    if lowered in {"unknown", "none", "noassertion", "n/a"} or "licenseref-" in lowered:
        return "unreviewed license placeholder or custom license reference"
    if lowered == "unlicensed":
        return "explicit UNLICENSED (npm private-package marker)"
    if lowered.startswith("see license in") or _NPM_FILE_REFERENCE_RE.fullmatch(expression):
        return f"file-only license reference {expression!r} (pending review)"
    hit = _forbidden_hit(expression, FORBIDDEN_LICENSE_TERMS) or _forbidden_hit(
        expression, FORBIDDEN_CLASSIFIER_TERMS
    )
    if hit is not None:
        return f"restricted term {hit!r} in {expression!r}"
    return None


def audit_npm_locks(lock_paths: list[Path]) -> int:
    """Audit npm ``package-lock.json`` licenses with the shared lock reader.

    Each named lock is parsed by ``scripts.release.generate_sboms.npm_packages``
    so package identity, nested/scoped resolution and workspace
    (``link: true``) exclusions keep their single implementation; missing,
    malformed, empty or uninventoriable locks fail closed through that reader.
    Every remaining inventory entry, dev and optional entries included, must
    pass the strict license gate in :func:`_npm_license_problem`.

    Returns:
        Exit code: 0 when every third-party entry in every given lock carries a
        non-restricted, non-file-reference string license, 1 when any lock
        could not be inventoried or any entry fails the npm license gate.
    """

    # Imported here so the Python metadata audit stays dependency-light and a
    # broken lock-tooling import cannot change the Python-mode behaviour. The
    # repository root goes on sys.path because running this file as a script
    # puts only ``scripts/ci`` there, unlike ``-m`` or pytest.
    repository_root = Path(__file__).resolve().parents[2]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from scripts.release.generate_sboms import SbomInputError, npm_packages

    if not lock_paths:
        print("No npm lock paths given.")
        print("Refusing to report a clean audit: nothing was audited.")
        return 1

    problems: list[str] = []
    violations: list[str] = []
    ok: list[str] = []
    excluded = 0
    inventoried = 0
    for lock_path in lock_paths:
        try:
            inventory = npm_packages(lock_path)
        except SbomInputError as error:
            problems.extend(f"{lock_path}: {message}" for message in error.errors)
            continue
        inventoried += 1
        excluded += len(inventory.excluded)
        for item in inventory.packages:
            identity = f"{item['name']}@{item['version']}"
            problem = _npm_license_problem(item.get("license"))
            if problem is None:
                ok.append(f"{lock_path}: {identity}: {item['license']}")
            else:
                violations.append(f"{lock_path}: {identity}: {problem}")

    print(
        f"Audited {len(ok) + len(violations)} npm third-party package entries "
        f"from {inventoried} of {len(lock_paths)} lock file(s)."
    )
    print(
        f"Excluded {excluded} non-third-party lock entries (workspace links and "
        "this repository's own project packages) per the shared inventory reader."
    )
    print(
        "Scope: package-lock.json inventories for exactly the given lock files, "
        "including dev and optional entries and every nested or scoped duplicate. "
        "This is conservative lock coverage, not a shipped-artifact proof, and it "
        "reads lock-declared expressions only: no full license texts, no SPDX "
        "legal interpretation of OR/WITH and no redistribution clearance."
    )
    if problems:
        print("LOCK PROBLEMS (fail-closed; these locks were not audited):")
        print("  " + "\n  ".join(sorted(problems)))
    if violations:
        print(
            "NPM LICENSE PROBLEMS (fail-closed; review-required detection, not a "
            "legal determination):"
        )
        print("  " + "\n  ".join(sorted(violations)))
    if problems or violations:
        return 1
    print(
        "npm license policy: OK (no restricted, missing, UNLICENSED or file-only "
        "license values detected in the scanned lock inventories; conservative "
        "lock coverage, not a commercial or redistribution clearance)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the dependency audit.

    ``main(["site-packages-dir"])`` keeps the original Python metadata audit,
    including its default of ``.deps``. ``main(["--npm-lock", path, ...])``
    switches to the npm lock audit for the exact lock files given; combining
    the two forms is refused instead of guessing which audit was meant.
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    npm_locks: list[Path] = []
    positional: list[str] = []
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == NPM_LOCK_FLAG:
            if index + 1 >= len(args) or not args[index + 1].strip():
                print(f"{NPM_LOCK_FLAG} requires a lock path argument")
                return 2
            npm_locks.append(Path(args[index + 1]))
            index += 2
        elif argument.startswith(f"{NPM_LOCK_FLAG}="):
            value = argument.split("=", 1)[1]
            if not value.strip():
                print(f"{NPM_LOCK_FLAG} requires a lock path argument")
                return 2
            npm_locks.append(Path(value))
            index += 1
        else:
            positional.append(argument)
            index += 1

    if npm_locks:
        if positional:
            print("choose either a site-packages directory or --npm-lock paths, not both")
            return 2
        return audit_npm_locks(npm_locks)

    target = positional[0] if positional else ".deps"
    site_packages = Path(target)
    if not site_packages.is_dir():
        print(f"site-packages directory not found: {site_packages}")
        return 2
    return audit(site_packages)


if __name__ == "__main__":
    raise SystemExit(main())
