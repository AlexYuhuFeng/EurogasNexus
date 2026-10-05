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

Rust mode (``--cargo-lock PATH``) audits the desktop crate graph once: the
same shared structured ``Cargo.lock`` reader supplies the third-party
inventory, and ``cargo metadata --locked --format-version 1 --all-features
--manifest-path <Cargo.toml>`` (no ``--no-deps``) is collected through a
subprocess argv list with an explicit timeout, so the audited graph is the
Cargo-resolved one instead of a guess. Every lock entry must match the
metadata by exact name/version/source identity -- never by name alone -- and
metadata may not omit, duplicate, contradict or add entries; a missing cargo
executable, a timeout, a non-zero exit, malformed JSON or fields, an empty or
absent ``packages`` array and a lock the shared reader cannot fully inventory
all fail closed. Declared ``license`` values go through the same shared
fail-closed check as npm (restricted terms anywhere, missing/blank/non-string
values, unknown placeholders, custom ``LicenseRef-`` references and file-only
references), while git, path and alternate-registry packages keep their
provenance and are listed for source review instead of being auto-approved.
Only the audited root package may be left out, and it must be verified from
both sides: the sibling ``Cargo.toml`` is read structurally with the standard
library ``tomllib`` and must carry a ``[package]`` name/version, exactly one
``cargo metadata`` package must resolve its ``manifest_path`` to that exact
manifest with a null ``source``, and ``Cargo.lock`` must disclose exactly that
same project package. ``workspace_members`` is never trusted, and any other
lock-disclosed project name or same-name package at another path is reported
as an unaudited gap instead of inheriting the exclusion. Cargo failure reports
never echo raw tool output, because ``cargo`` stderr can contain private
registry URLs or credentials: they carry only the exit/status plus a safe
instruction. ``--all-features`` and full-resolution metadata deliberately
over-include build, dev and inactive-feature packages: that is conservative
coverage, not shipped-artifact proof.

Per the Core Metadata specification, a ``License-Expression`` header replaces
the legacy ``License`` header and takes precedence when both are present; every
``License ::`` classifier is read, not only the OSI-approved subset; and folded
or repeated headers follow email/RFC 5322 rules instead of ad-hoc line
parsing.

This is a review-required detection, not a legal determination: a clean result
means "no restricted license terms were detected in the scanned metadata",
not a commercial clearance. It does not read full license texts and does not
cover artifact redistribution; see the dependency policy for the scope and its
outstanding limitations. Unknown Python licenses are listed for review;
missing, unreadable or malformed Python metadata -- including a target with no
distribution metadata at all -- fails closed, because nothing was audited. An
npm lock or Cargo crate graph the shared readers cannot fully inventory also
fails closed, and no mode interprets SPDX ``OR``/``WITH`` expressions legally.

Usage:
    python scripts/ci/audit_dependencies.py [site_packages_dir]
    python scripts/ci/audit_dependencies.py --npm-lock clients/web/package-lock.json \
        --npm-lock clients/desktop/package-lock.json
    python scripts/ci/audit_dependencies.py --cargo-lock clients/desktop/src-tauri/Cargo.lock
"""

from __future__ import annotations

import email
import email.errors
import email.policy
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
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

CARGO_LOCK_FLAG = "--cargo-lock"

#: ``cargo metadata`` timeout: long enough for a cold resolved graph in the
#: release runner, short enough that a hung toolchain fails the gate instead of
#: stalling it.
CARGO_METADATA_TIMEOUT_SECONDS = 300.0

#: Cargo failure reports never echo raw tool output -- stderr can carry private
#: registry URLs or credentials -- so they carry the exit/status plus this
#: safe instruction instead.
_CARGO_FAILURE_INSTRUCTION = (
    "raw cargo output is deliberately not echoed because it can contain private "
    "registry URLs or credentials; re-run cargo metadata in the release runner to "
    "inspect it directly"
)

#: License values that name a file instead of an expression, shared by the npm
#: and cargo declared-license checks. ``SEE LICENSE IN`` is caught separately
#: (it can carry any file name); this pattern catches bare license-file
#: references such as ``LICENSE``, ``./LICENSE.md``, ``docs/COPYING`` or
#: ``NOTICE.txt``.
_FILE_REFERENCE_RE = re.compile(
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


def _declared_license_problem(value: object) -> str | None:
    """Return a fail-closed reason for one declared license value, or None.

    Shared by the npm lock gate and the cargo crate-graph gate. Reasons cover
    missing, blank and non-string values, the explicit ``UNLICENSED`` marker,
    unknown placeholders and custom ``LicenseRef-`` references, file-only
    references pending review, and restricted terms anywhere in the expression
    -- including inside an ``OR``/``WITH``/``AND`` combination, which is never
    approved because one branch is permissive.
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
        return "explicit UNLICENSED marker (no license granted)"
    if lowered.startswith("see license in") or _FILE_REFERENCE_RE.fullmatch(expression):
        return f"file-only license reference {expression!r} (pending review)"
    hit = _forbidden_hit(expression, FORBIDDEN_LICENSE_TERMS) or _forbidden_hit(
        expression, FORBIDDEN_CLASSIFIER_TERMS
    )
    if hit is not None:
        return f"restricted term {hit!r} in {expression!r}"
    return None


def _shared_sbom_module():
    """Import and return ``scripts.release.generate_sboms`` lazily.

    The import stays inside the lock-audit paths so the Python metadata audit
    remains dependency-light and a broken lock-tooling import cannot change
    Python-mode behaviour. The repository root goes on sys.path because
    running this file as a script puts only ``scripts/ci`` there, unlike
    ``-m`` or pytest.
    """

    repository_root = Path(__file__).resolve().parents[2]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from scripts.release import generate_sboms

    return generate_sboms


def audit_npm_locks(lock_paths: list[Path]) -> int:
    """Audit npm ``package-lock.json`` licenses with the shared lock reader.

    Each named lock is parsed by ``scripts.release.generate_sboms.npm_packages``
    so package identity, nested/scoped resolution and workspace
    (``link: true``) exclusions keep their single implementation; missing,
    malformed, empty or uninventoriable locks fail closed through that reader.
    Every remaining inventory entry, dev and optional entries included, must
    pass the shared strict license gate in :func:`_declared_license_problem`.

    Returns:
        Exit code: 0 when every third-party entry in every given lock carries a
        non-restricted, non-file-reference string license, 1 when any lock
        could not be inventoried or any entry fails the npm license gate.
    """

    sboms = _shared_sbom_module()

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
            inventory = sboms.npm_packages(lock_path)
        except sboms.SbomInputError as error:
            problems.extend(f"{lock_path}: {message}" for message in error.errors)
            continue
        inventoried += 1
        excluded += len(inventory.excluded)
        for item in inventory.packages:
            identity = f"{item['name']}@{item['version']}"
            problem = _declared_license_problem(item.get("license"))
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


@dataclass(frozen=True)
class CargoMetadataEntry:
    """One validated package entry from ``cargo metadata`` output.

    ``license`` is kept as the raw JSON value so the shared declared-license
    check can report its exact problem, including non-string values.
    """

    name: str
    version: str
    source: str | None
    license: object
    license_file: str | None
    manifest_path: str

    @property
    def identity(self) -> tuple[str, str, str | None]:
        return (self.name, self.version, self.source)

    @property
    def described(self) -> str:
        return f"{self.name}@{self.version}"


def _cargo_metadata_argv(manifest_path: Path) -> list[str]:
    """Return the ``cargo metadata`` argv audited by the cargo gate.

    ``--locked`` turns a stale Cargo.lock into a hard failure instead of an
    implicit rewrite, ``--format-version 1`` is the documented JSON format and
    ``--all-features`` widens feature coverage; ``--no-deps`` is deliberately
    absent so the emitted graph is the full resolved dependency graph. See
    https://doc.rust-lang.org/stable/cargo/commands/cargo-metadata.html.
    """

    return [
        "cargo",
        "metadata",
        "--locked",
        "--format-version",
        "1",
        "--all-features",
        "--manifest-path",
        str(manifest_path),
    ]


def _resolved_path_string(path: str) -> str | None:
    """Return a normalized resolved string for one path, or None.

    ``Path.resolve`` raises for a handful of malformed inputs (for example an
    embedded null byte) and the resolved form is compared case-insensitively on
    case-insensitive filesystems. A path that cannot be resolved is never the
    audited manifest.
    """

    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError):
        return None
    return os.path.normcase(str(resolved))


def _cargo_root_identity(manifest_path: Path) -> tuple[tuple[str, str] | None, list[str]]:
    """Structurally read the audited root ``Cargo.toml`` for its package identity.

    ``tomllib`` (standard library) is the only reader, so the project-package
    exclusion cannot be widened through ad-hoc text matching. A missing or
    unreadable manifest, invalid TOML, a missing or non-table ``[package]``
    table and a missing, blank or non-string name/version are all returned as
    problems: the caller fails closed instead of silently excluding anything.
    """

    try:
        text = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, [
            f"audited root manifest is missing: {manifest_path}; the root package cannot be "
            "identified, so nothing is excluded"
        ]
    except OSError as error:
        return None, [
            f"audited root manifest could not be read ({type(error).__name__}): {manifest_path}; "
            "nothing is excluded"
        ]
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return None, [
            f"audited root manifest is not valid TOML: {manifest_path} ({error}); nothing is "
            "excluded"
        ]
    package = data.get("package")
    if not isinstance(package, dict):
        return None, [
            f"audited root manifest has no [package] table: {manifest_path}; nothing is excluded"
        ]
    name, version = package.get("name"), package.get("version")
    if not isinstance(name, str) or not name.strip():
        return None, [
            f"audited root manifest [package] has no non-blank string 'name': {manifest_path}"
        ]
    if not isinstance(version, str) or not version.strip():
        return None, [
            f"audited root manifest [package] has no non-blank string 'version': {manifest_path}"
        ]
    return (name.strip(), version.strip()), []


def _run_cargo_metadata(
    manifest_path: Path, *, timeout: float | None = None
) -> tuple[str | None, str | None]:
    """Run ``cargo metadata`` with an argv list and return (stdout, problem).

    ``subprocess.run`` is used without a shell and with an explicit timeout, so
    the audit cannot hang and shell quoting cannot change the command. A
    missing ``cargo`` executable, a timeout, an OS-level execution failure and
    any non-zero exit (including ``--locked`` refusals) are reported as
    problems; the caller fails closed instead of auditing a partial graph.

    Raw cargo output is never echoed: ``stderr`` can contain private registry
    URLs or credentials, and exception payloads can embed it, so failures carry
    only the exit/status, the audited command and a safe instruction.
    """

    effective_timeout = CARGO_METADATA_TIMEOUT_SECONDS if timeout is None else timeout
    argv = _cargo_metadata_argv(manifest_path)
    command = " ".join(argv)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
        )
    except FileNotFoundError:
        return None, (
            f"cargo executable not found; cannot collect dependency metadata: {command}; "
            "install/provide the cargo toolchain in the release runner"
        )
    except subprocess.TimeoutExpired:
        return None, (
            f"cargo metadata timed out after {effective_timeout:g}s: {command}; "
            f"{_CARGO_FAILURE_INSTRUCTION}"
        )
    except OSError as error:
        return None, (
            f"cargo metadata could not be executed ({type(error).__name__}): {command}; "
            f"{_CARGO_FAILURE_INSTRUCTION}"
        )
    if completed.returncode != 0:
        return None, (
            f"cargo metadata failed with exit code {completed.returncode}: {command}; "
            f"{_CARGO_FAILURE_INSTRUCTION}"
        )
    return completed.stdout or "", None


def _cargo_metadata_entries(stdout: str) -> tuple[list[CargoMetadataEntry], list[str]]:
    """Validate ``cargo metadata`` JSON into entries, or return problems.

    Only the fields the gate relies on are validated, and any violation of
    their shape is a problem because a malformed graph must never be audited
    partially. ``packages`` must be a non-empty array and each entry must carry
    a non-blank string ``name`` and ``version`` plus a null or non-blank string
    ``source``, a non-blank string ``manifest_path`` (cargo always emits one,
    and the root-exclusion check resolves it); ``license`` stays raw for the
    shared check and ``license_file`` must be null or a string.
    """

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        return [], [f"cargo metadata did not emit valid JSON: {error}"]
    if not isinstance(payload, dict):
        return [], ["cargo metadata JSON is not an object"]
    raw_packages = payload.get("packages")
    if not isinstance(raw_packages, list) or not raw_packages:
        return [], [
            "cargo metadata carried no dependency metadata (missing, empty or non-list 'packages')"
        ]
    entries: list[CargoMetadataEntry] = []
    problems: list[str] = []
    for index, raw in enumerate(raw_packages, start=1):
        if not isinstance(raw, dict):
            problems.append(f"cargo metadata package entry #{index} is not an object")
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"cargo metadata package entry #{index} has no non-blank string 'name'")
            continue
        version = raw.get("version")
        if not isinstance(version, str) or not version.strip():
            problems.append(f"cargo metadata package {name!r} has no non-blank string 'version'")
            continue
        source = raw.get("source")
        if source is not None and (not isinstance(source, str) or not source.strip()):
            problems.append(f"cargo metadata package {name!r} has a malformed 'source' field")
            continue
        manifest_path = raw.get("manifest_path")
        if not isinstance(manifest_path, str) or not manifest_path.strip():
            problems.append(
                f"cargo metadata package {name!r} has no non-blank string 'manifest_path'"
            )
            continue
        license_file = raw.get("license_file")
        if license_file is not None and not isinstance(license_file, str):
            problems.append(f"cargo metadata package {name!r} has a malformed 'license_file' field")
            continue
        entries.append(
            CargoMetadataEntry(
                name=name,
                version=version,
                source=source,
                license=raw.get("license"),
                license_file=license_file,
                manifest_path=manifest_path,
            )
        )
    return entries, problems


def _cargo_license_problem(entry: CargoMetadataEntry) -> str | None:
    """Apply the shared declared-license gate to one cargo metadata entry.

    A crate that declares only ``license_file`` has no machine-readable
    expression, so it fails like any other missing declaration; the file path
    is reported for review instead of being auto-approved.
    """

    problem = _declared_license_problem(entry.license)
    if (
        problem == "missing 'license' value"
        and isinstance(entry.license_file, str)
        and entry.license_file.strip()
    ):
        return (
            "missing 'license' value (license_file only: "
            f"{entry.license_file.strip()!r}; file-only references are not auto-approved)"
        )
    return problem


def _cargo_identity_problem(
    item: dict,
    metadata_by_name_version: dict[tuple[str, str], list[CargoMetadataEntry]],
    entries: list[CargoMetadataEntry],
) -> str:
    """Describe why one Cargo.lock identity is absent from cargo metadata."""

    name, version, source = item["name"], item["version"], item.get("source")
    same_name_version = metadata_by_name_version.get((name, version))
    if same_name_version:
        sources = ", ".join(repr(entry.source) for entry in same_name_version)
        return (
            f"Cargo.lock package {name}@{version} has source {source!r} but cargo metadata "
            f"reports source(s) {sources}; identities must match exactly"
        )
    versions = sorted({entry.version for entry in entries if entry.name == name})
    if versions:
        return (
            f"Cargo.lock package {name}@{version} is omitted from cargo metadata output "
            f"(metadata carries version(s): {', '.join(versions)})"
        )
    return (
        f"Cargo.lock package {name}@{version} (source {source!r}) is omitted from cargo "
        "metadata output"
    )


def audit_cargo_lock(lock_path: Path, *, timeout: float | None = None) -> int:
    """Audit the Rust crate graph's declared licenses against the policy.

    The third-party inventory is the shared structured ``Cargo.lock`` reader
    (the reader that builds the SPDX ``desktop-rust`` document), and ``cargo
    metadata`` for the sibling ``Cargo.toml`` is matched to it by exact
    name/version/source identity -- never by name alone. Absent, duplicated,
    contradictory or uncovered metadata entries, a lock the shared reader
    cannot fully inventory and any cargo collection failure all fail closed.
    Git, path and alternate-registry packages are audited for restricted terms
    but listed for provenance review instead of being auto-approved.

    The only package that may be left out of the third-party inventory is the
    audited root itself, and only after it is verified three ways: the sibling
    ``Cargo.toml`` is read structurally (standard library ``tomllib``) and must
    carry a ``[package]`` name/version, exactly one ``cargo metadata`` package
    must resolve its ``manifest_path`` to that exact manifest with a null
    ``source`` and the same name/version, and the ``Cargo.lock`` must disclose
    exactly one project package with that same name/version. ``workspace_members``
    is never trusted for this. Any other lock-disclosed project name, or a
    package that only reuses the root name/version at another path, is reported
    as an unaudited gap instead of inheriting the exemption. Raw ``cargo``
    output is never echoed: failure reports carry only the exit/status and a
    safe instruction, because stderr can contain private registry URLs or
    credentials.

    Returns:
        Exit code: 0 when every third-party lock entry was matched and carries
        an acceptable declared license, 1 when the graph could not be fully
        audited or any declared license fails the shared check.
    """

    sboms = _shared_sbom_module()
    try:
        inventory = sboms.rust_packages(lock_path)
    except sboms.SbomInputError as error:
        print(f"Cargo lock inventory: {lock_path}")
        print("CARGO GATE PROBLEMS (fail-closed; the crate graph was not audited):")
        print("  " + "\n  ".join(sorted(error.errors)))
        return 1

    manifest_path = lock_path.parent / "Cargo.toml"
    root_identity, root_problems = _cargo_root_identity(manifest_path)
    if root_identity is None:
        print(f"Cargo lock inventory: {lock_path}")
        print(
            "CARGO GATE PROBLEMS (fail-closed; the audited root manifest could not be "
            "verified, so nothing is excluded):"
        )
        print("  " + "\n  ".join(sorted(root_problems)))
        return 1
    root_spec = f"{root_identity[0]} {root_identity[1]}"

    stdout, problem = _run_cargo_metadata(manifest_path, timeout=timeout)
    if problem is not None:
        print(f"Cargo lock inventory: {lock_path}")
        print(f"Cargo metadata command: {' '.join(_cargo_metadata_argv(manifest_path))}")
        print("CARGO GATE PROBLEMS (fail-closed; the crate graph was not audited):")
        print(f"  {problem}")
        return 1
    entries, parse_problems = _cargo_metadata_entries(stdout or "")
    if parse_problems:
        print(f"Cargo lock inventory: {lock_path}")
        print(f"Cargo metadata command: {' '.join(_cargo_metadata_argv(manifest_path))}")
        print("CARGO GATE PROBLEMS (fail-closed; a malformed graph is never audited partially):")
        print("  " + "\n  ".join(sorted(parse_problems)))
        return 1
    problems: list[str] = []

    lock_counts: dict[tuple[str, str, str | None], int] = {}
    for item in inventory.packages:
        identity = (item["name"], item["version"], item.get("source"))
        lock_counts[identity] = lock_counts.get(identity, 0) + 1
    for identity, count in lock_counts.items():
        if count > 1:
            problems.append(
                f"Cargo.lock carries {count} packages with the same identity "
                f"{identity[0]}@{identity[1]} (source {identity[2]!r})"
            )

    metadata_by_identity: dict[tuple[str, str, str | None], CargoMetadataEntry] = {}
    metadata_by_name_version: dict[tuple[str, str], list[CargoMetadataEntry]] = {}
    for entry in entries:
        identity = entry.identity
        if identity in metadata_by_identity:
            problems.append(
                f"duplicate cargo metadata entries for {entry.described} (source {identity[2]!r})"
            )
            continue
        metadata_by_identity[identity] = entry
        metadata_by_name_version.setdefault((entry.name, entry.version), []).append(entry)

    violations: list[str] = []
    review: list[str] = []
    ok: list[str] = []
    matched: set[tuple[str, str, str | None]] = set()
    for item in inventory.packages:
        identity = (item["name"], item["version"], item.get("source"))
        if lock_counts[identity] > 1:
            continue  # already reported as a duplicate lock identity
        entry = metadata_by_identity.get(identity)
        if entry is None:
            problems.append(_cargo_identity_problem(item, metadata_by_name_version, entries))
            continue
        matched.add(identity)
        origin = item.get("origin", "other")
        license_problem = _cargo_license_problem(entry)
        if license_problem is not None:
            violations.append(f"{entry.described} [{origin}]: {license_problem}")
        elif origin == "registry":
            ok.append(f"{entry.described}: {entry.license}")
        else:
            review.append(f"{entry.described} [{origin}]: declared {entry.license!r}")

    # Only the audited root package may be left out of the third-party
    # inventory, and it is verified from both sides instead of trusting a
    # shared project-name record: the sibling Cargo.toml [package] identity
    # read structurally above, exactly one cargo metadata package whose
    # manifest_path resolves to that exact manifest with a null source and the
    # same name/version, and exactly one Cargo.lock disclosure of that same
    # project package. workspace_members is never consulted.
    resolved_manifest = _resolved_path_string(str(manifest_path))
    root_entries = [
        entry
        for entry in entries
        if resolved_manifest is not None
        and _resolved_path_string(entry.manifest_path) == resolved_manifest
    ]
    verified_root: CargoMetadataEntry | None = None
    if len(root_entries) != 1:
        problems.append(
            f"cargo metadata carries {len(root_entries)} package(s) whose 'manifest_path' "
            f"resolves to the audited root manifest {manifest_path}; exactly one verified root "
            "package is required and workspace_members are not trusted, so no project-package "
            "exclusion is granted"
        )
    else:
        root_entry = root_entries[0]
        if root_entry.source is not None:
            problems.append(
                f"cargo metadata root package {root_entry.described} (source "
                f"{root_entry.source!r}) must have a null source to be this repository's own "
                "root; refusing to exclude it"
            )
        elif (root_entry.name, root_entry.version) != root_identity:
            problems.append(
                f"cargo metadata root package {root_entry.described} does not match the audited "
                f"Cargo.toml [package] {root_spec}; refusing to exclude it"
            )
        else:
            verified_root = root_entry

    project_exclusions = [
        entry for entry in inventory.excluded if entry.get("reason") == "project-package"
    ]
    disclosed_root = [
        entry
        for entry in project_exclusions
        if entry.get("name") == root_identity[0] and entry.get("spec") == root_spec
    ]
    for entry in project_exclusions:
        if entry in disclosed_root:
            continue
        spec = entry.get("spec") or entry.get("name") or "<unknown>"
        problems.append(
            f"Cargo.lock discloses project package {spec!r} which is not the verified audited "
            f"root package {root_spec!r}; the shared inventory reader dropped it from the "
            "third-party inventory, so it would be left unaudited -- refusing that gap"
        )
    if verified_root is not None and verified_root.identity not in matched:
        if not disclosed_root:
            problems.append(
                f"Cargo.lock does not disclose the audited root package {root_spec!r} as a "
                "project-package exclusion; refusing to exclude a root the lock inventory does "
                "not reveal"
            )
        elif len(disclosed_root) > 1:
            problems.append(
                f"Cargo.lock discloses the audited root package {root_spec!r} "
                f"{len(disclosed_root)} times; exactly one disclosure is required"
            )
    exempted_root = (
        verified_root
        if verified_root is not None
        and verified_root.identity not in matched
        and len(disclosed_root) == 1
        else None
    )
    for identity, entry in metadata_by_identity.items():
        if identity in matched or entry == exempted_root:
            continue
        problems.append(
            f"cargo metadata package {entry.described} (source {identity[2]!r}) is not "
            "covered by the Cargo.lock inventory; refusing to leave it unaudited"
        )

    print(f"Cargo lock inventory: {lock_path}")
    print(f"Cargo metadata command: {' '.join(_cargo_metadata_argv(manifest_path))}")
    print(f"Audited root manifest: {manifest_path} (structural [package] identity {root_spec})")
    print(
        f"Audited {len(inventory.packages)} third-party crate entries from the Cargo.lock "
        f"inventory: {len(ok)} registry entries passed the declared-license check, "
        f"{len(review)} git/path/alternate-registry entries are listed for provenance review, "
        f"{len(violations)} entries carry a failing declared license."
    )
    print(
        f"Excluded {len(inventory.excluded)} non-third-party Cargo.lock entries per the shared "
        "inventory reader; the only exemption this audit grants is the verified root package "
        f"({root_spec}) via exactly one null-source cargo metadata entry whose manifest_path "
        "resolves to the audited manifest, and no other name, workspace membership or path is "
        "excluded."
    )
    print(
        "Scope: Cargo.lock entries are matched against cargo metadata output by exact "
        "name/version/source identity. cargo metadata ran with --locked --format-version 1 "
        "--all-features and no --no-deps, so this is conservative full-graph coverage that "
        "over-includes build, dev and inactive-feature packages not shipped in the installer; "
        "it is not shipped-artifact proof. Only declared license expressions are read: no "
        "full license texts, no vendored code, no OS/native/installer artifacts, no SPDX "
        "legal interpretation of OR/WITH and no redistribution clearance."
    )
    if review:
        print("PROVENANCE REVIEW (not auto-approved; manual source/license review required):")
        print("  " + "\n  ".join(sorted(review)))
    if problems:
        print("CARGO GATE PROBLEMS (fail-closed; the crate graph was not fully audited):")
        print("  " + "\n  ".join(sorted(problems)))
    if violations:
        print(
            "RUST LICENSE PROBLEMS (fail-closed; review-required detection, not a legal "
            "determination):"
        )
        print("  " + "\n  ".join(sorted(violations)))
    if problems or violations or review:
        return 1
    print(
        "cargo declared-license policy: OK (no restricted, missing, unknown, UNLICENSED or "
        "file-only declared license values detected; review-required detection, not a legal "
        "determination and not a commercial or redistribution clearance)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the dependency audit.

    ``main(["site-packages-dir"])`` keeps the original Python metadata audit,
    including its default of ``.deps``. ``main(["--npm-lock", path, ...])``
    switches to the npm lock audit for the exact lock files given,
    ``main(["--cargo-lock", path])`` audits the desktop crate graph through
    ``cargo metadata``; combining the forms is refused instead of guessing
    which audit was meant.
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    npm_locks: list[Path] = []
    cargo_locks: list[Path] = []
    positional: list[str] = []
    index = 0
    while index < len(args):
        argument = args[index]
        consumed = False
        for flag, targets in ((NPM_LOCK_FLAG, npm_locks), (CARGO_LOCK_FLAG, cargo_locks)):
            if argument == flag:
                if index + 1 >= len(args) or not args[index + 1].strip():
                    print(f"{flag} requires a lock path argument")
                    return 2
                targets.append(Path(args[index + 1]))
                index += 2
                consumed = True
                break
            if argument.startswith(f"{flag}="):
                value = argument.split("=", 1)[1]
                if not value.strip():
                    print(f"{flag} requires a lock path argument")
                    return 2
                targets.append(Path(value))
                index += 1
                consumed = True
                break
        if consumed:
            continue
        positional.append(argument)
        index += 1

    if cargo_locks:
        if len(cargo_locks) != 1:
            print(f"{CARGO_LOCK_FLAG} accepts exactly one Cargo.lock path")
            return 2
        if positional or npm_locks:
            print("choose either --cargo-lock or --npm-lock or a site-packages directory, not both")
            return 2
        return audit_cargo_lock(cargo_locks[0])

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
