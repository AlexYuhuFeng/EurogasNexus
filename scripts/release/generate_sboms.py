#!/usr/bin/env python
"""Generate SPDX 2.3 SBOMs from the enforced dependency locks.

Covers Python runtime dependencies, Web Node dependencies, Desktop Node
dependencies and Desktop Rust dependencies. ``sbom-manifest.json`` records
every component document, the SHA-256 of each lock input it was derived from
and the known limits of that inventory. A ``THIRD_PARTY_NOTICES.md`` is
generated for shipped dependency notices.

The documents are lock-derived inventories, not artifact-complete SBOMs:
container-image OS packages, native/installer binaries and vendored code are
outside this inventory, and lock-declared license expressions are not a
license-text or legal-completeness review.

Every lock input is validated strictly: a Python requirement that is not a
fully parsed hash-pinned declaration, a malformed npm entry, or a Cargo
``source``/``checksum`` of the wrong type or shape fails the run instead of
producing a partial inventory, and only the exact canonical crates.io index
sources count as crates.io.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from scripts.release.release_artifacts import sha256_file  # noqa: E402
from scripts.release.reviewed_cargo_license_choices import (  # noqa: E402
    CRATES_IO_SOURCES,
    ReviewedChoiceError,
    load_reviewed_choices,
)
from scripts.release.reviewed_cargo_license_choices import (
    verify_package_authors_file as verify_package_authors_file,
)

ROOT = Path(__file__).resolve().parents[2]

#: This repository's own packages are the SBOM subject, not third-party components.
PROJECT_PACKAGE_NAMES = frozenset({"eurogas-nexus", "eurogas-nexus-web", "eurogas-nexus-desktop"})

DOCUMENT_NAMESPACE_BASE = "https://eurogas-nexus.invalid/spdx"

#: component key -> (lock file path relative to the repository root, purl ecosystem).
LOCK_INPUTS: tuple[tuple[str, str, str], ...] = (
    ("python-runtime", "requirements-runtime.lock", "pypi"),
    ("web-node", "clients/web/package-lock.json", "npm"),
    ("desktop-node", "clients/desktop/package-lock.json", "npm"),
    ("desktop-rust", "clients/desktop/src-tauri/Cargo.lock", "cargo"),
)

#: Machine-readable statement of what these lock-derived documents do and do not cover.
INVENTORY_SCOPE: dict[str, Any] = {
    "basis": "dependency-locks",
    "inputs": "only the lock inputs listed in 'inputs'; no runtime or container filesystem scan",
    "includes_dev_and_build_dependencies": True,
    "target_over_inclusion": (
        "lock files resolve all platforms, optional features and dev/build dependencies, so "
        "packages that are not installed in the shipped artifact can be listed"
    ),
    "license_metadata": (
        "license expressions are copied from the locks where present; 'NOASSERTION' means the "
        "lock carried none (Cargo.lock and requirements-runtime.lock carry none)"
    ),
    "missing_inventory": [
        "operating-system packages inside the runtime container image",
        "native binaries bundled by installers or Tauri sidecars",
        "vendored third-party source",
    ],
    "excluded_entries": (
        "lock entries that are not third-party packages are disclosed per input under "
        "'excluded_entries' (npm 'link: true' workspace links and this repository's own "
        "project packages) and are not counted in the package inventory"
    ),
    "notices_scope": (
        "THIRD_PARTY_NOTICES.md lists locked packages and lock-declared license expressions "
        "only; it contains no full license texts and is not a legal review"
    ),
    "acceptance_note": (
        "lock-derived documents only; not artifact-complete SBOM coverage and not G10 acceptance"
    ),
}

_PEP503_RUN_RE = re.compile(r"[-_.]+")

_NPM_NAME_RE = re.compile(r"^(@[A-Za-z0-9._-]+/)?[A-Za-z0-9._~-]+$")

#: The exact canonical crates.io index sources are owned by the shared reviewed-
#: choice validator so the audit and SBOM cannot disagree. A custom registry or
#: mirror whose URL merely contains ``crates.io-index`` is not crates.io.
_CRATES_IO_SOURCES = CRATES_IO_SOURCES

_CARGO_CHECKSUM_RE = re.compile(r"[0-9a-fA-F]{64}")

#: pip's supported ``--hash`` algorithms with their hex digest lengths.
_PY_HASH_DIGEST_LENGTHS: dict[str, int] = {
    "md5": 32,
    "sha1": 40,
    "sha224": 56,
    "sha256": 64,
    "sha384": 96,
    "sha512": 128,
}
_PY_HASH_RE = re.compile(r"--hash=(?P<algorithm>[A-Za-z0-9]+):(?P<digest>[0-9a-fA-F]+)")
_PY_DECLARATION_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[(?P<extras>[A-Za-z0-9._-]+(?:,[A-Za-z0-9._-]+)*)\])?"
    r"==(?P<version>[0-9][0-9A-Za-z.!+_-]*)"
    r"(?:\s*;\s*(?P<marker>.+))?"
)
#: PEP 508 environment variables and operators seen in the enforced lock.
#: Markers outside this subset are refused instead of being guessed at.
_PY_MARKER_VARIABLES = (
    "extra",
    "implementation_name",
    "implementation_version",
    "os_name",
    "platform_machine",
    "platform_python_implementation",
    "platform_release",
    "platform_system",
    "platform_version",
    "python_full_version",
    "python_version",
    "sys_platform",
)
_PY_MARKER_OPERATORS = ("===", "==", "!=", "<=", ">=", "~=", "<", ">", "not in", "in")
_PY_MARKER_ATOM = (
    rf"(?:{'|'.join(_PY_MARKER_VARIABLES)})\s*"
    rf"(?:{'|'.join(re.escape(operator) for operator in _PY_MARKER_OPERATORS)})\s*"
    r"(?:'[^']*'|\"[^\"]*\")"
)
_PY_MARKER_RE = re.compile(rf"\(*\s*{_PY_MARKER_ATOM}(?:\s+(?:and|or)\s+{_PY_MARKER_ATOM})*\s*\)*")


class SbomInputError(RuntimeError):
    """A required lock input is missing, unreadable, malformed or empty."""

    def __init__(self, errors: str | list[str]) -> None:
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class LockInventory:
    """Packages parsed from one lock input plus entries excluded from inventory.

    ``excluded`` lists entries the parser recognised but deliberately did not
    inventory as packages (npm ``link: true`` workspace links and this
    repository's own project entries) so they are disclosed in the manifest
    instead of silently disappearing.
    """

    packages: list[dict]
    excluded: list[dict[str, str]] = field(default_factory=list)


def utc_timestamp(now: datetime | None = None) -> str:
    """Return an SPDX-valid UTC timestamp (``YYYY-MM-DDThh:mm:ssZ``)."""
    instant = now if now is not None else datetime.now(UTC)
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quote_component(value: str) -> str:
    """Percent-encode one purl path segment via RFC 3986 rules."""
    return quote(value, safe="")


def _normalize_name(ecosystem: str, name: str) -> str:
    """Apply only the per-ecosystem purl name rules.

    PyPI names use the PEP 503 canonical form (lowercase with every ``-``,
    ``_`` or ``.`` run collapsed to a single ``-``); npm names and scopes are
    lowercased; Cargo crate names keep their case and underscores because they
    are meaningful to the registry.
    """
    if ecosystem == "pypi":
        return _PEP503_RUN_RE.sub("-", name).lower()
    if ecosystem == "npm":
        return name.lower()
    return name


def build_purl(ecosystem: str, name: str, version: str, *, namespace: str | None = None) -> str:
    """Build a package URL for the package-manager ecosystem."""
    segments = []
    if namespace:
        segments.append(_quote_component(_normalize_name(ecosystem, namespace)))
    segments.append(_quote_component(_normalize_name(ecosystem, name)))
    return f"pkg:{ecosystem.lower()}/{'/'.join(segments)}@{_quote_component(version)}"


def _read_required_text(path: Path) -> str:
    if not path.is_file():
        raise SbomInputError(f"required lock input missing: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise SbomInputError(f"required lock input unreadable: {path}: {error}") from error


def _load_required_json(path: Path) -> Any:
    text = _read_required_text(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise SbomInputError(f"{path}: invalid JSON: {error}") from error


def _valid_npm_name(name: str) -> bool:
    return bool(name) and _NPM_NAME_RE.match(name) is not None


def npm_package_name(spec: str, item: dict[str, Any]) -> str | None:
    """Resolve the package identity of one ``package-lock.json`` entry.

    The explicit ``name`` is preferred when it is a valid npm package name;
    otherwise the identity is the path after the last ``node_modules/``
    segment, which keeps scoped names (``@scope/pkg``) intact in both cases.
    """
    explicit = item.get("name")
    if isinstance(explicit, str) and _valid_npm_name(explicit.strip()):
        return explicit.strip()
    if "node_modules/" not in spec:
        return None
    tail = spec.rsplit("node_modules/", 1)[1].strip()
    return tail if _valid_npm_name(tail) else None


def _valid_python_marker(marker: str) -> bool:
    """Accept only markers built from the supported atoms joined by and/or."""
    if _PY_MARKER_RE.fullmatch(marker) is None:
        return False
    return marker.count("(") == marker.count(")")


def _python_logical_lines(lock_path: Path, text: str) -> list[tuple[int, str]]:
    """Join backslash continuations into logical lines with their line numbers."""
    logical: list[tuple[int, str]] = []
    start_line = 0
    buffered = ""
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            if buffered:
                raise SbomInputError(
                    f"{lock_path}:{lineno}: comment or blank line inside a continued requirement"
                )
            continue
        continued = line.endswith("\\")
        part = line[:-1].strip() if continued else line
        if not buffered:
            start_line = lineno
        buffered = f"{buffered} {part}".strip()
        if not continued:
            logical.append((start_line, buffered))
            buffered = ""
    if buffered:
        raise SbomInputError(f"{lock_path}: last line ends with a line continuation")
    return logical


def python_packages(lock_path: Path) -> LockInventory:
    """Parse the enforced Python runtime lock.

    Every non-comment line must be a fully parsed, hash-pinned
    ``name==version`` declaration with optional extras, environment marker and
    one or more ``--hash=<algorithm>:<hex>`` entries. Directives, URLs,
    editables and range specifiers fail the parse instead of being dropped, so
    a successful parse covers every requirement declaration in the file.
    """
    text = _read_required_text(lock_path)
    packages = []
    excluded: list[dict[str, str]] = []
    for lineno, logical in _python_logical_lines(lock_path, text):
        tokens = logical.split()
        hashes_at = next(
            (index for index, token in enumerate(tokens) if token.startswith("--hash=")),
            len(tokens),
        )
        match = _PY_DECLARATION_RE.fullmatch(" ".join(tokens[:hashes_at]))
        if match is None:
            raise SbomInputError(
                f"{lock_path}:{lineno}: unsupported or malformed requirement (only hash-pinned "
                f"'name==version' declarations are supported): {logical!r}"
            )
        marker = match.group("marker")
        if marker is not None and not _valid_python_marker(marker):
            raise SbomInputError(
                f"{lock_path}:{lineno}: unsupported environment marker: {marker!r}"
            )
        hash_tokens = tokens[hashes_at:]
        if not hash_tokens:
            raise SbomInputError(
                f"{lock_path}:{lineno}: requirement has no --hash entries: {logical!r}"
            )
        for token in hash_tokens:
            hash_match = _PY_HASH_RE.fullmatch(token)
            if hash_match is not None:
                algorithm = hash_match.group("algorithm").lower()
                digest = hash_match.group("digest")
                expected = _PY_HASH_DIGEST_LENGTHS.get(algorithm)
                if expected is not None and len(digest) == expected:
                    continue
            raise SbomInputError(
                f"{lock_path}:{lineno}: unsupported or malformed hash entry: {token!r}"
            )
        name, version = match.group("name"), match.group("version")
        if _normalize_name("pypi", name) in PROJECT_PACKAGE_NAMES:
            excluded.append(
                {"spec": f"{name}=={version}", "reason": "project-package", "name": name}
            )
            continue
        packages.append(
            {
                "name": name,
                "version": version,
                "license": None,
                "purl": build_purl("pypi", name, version),
                "origin": "registry",
            }
        )
    if not packages:
        raise SbomInputError(f"{lock_path}: no third-party packages resolved from lock input")
    return LockInventory(packages, excluded)


def npm_packages(package_lock_path: Path) -> LockInventory:
    """Parse an npm ``package-lock.json`` (lockfile version 2/3 ``packages`` map).

    Ordinary entries must carry a string version and a resolvable package
    identity; malformed entries fail the parse instead of being skipped.
    ``link: true`` workspace links have no version and are not registry
    packages, so they are disclosed as exclusions rather than dropped or
    inventoried.
    """
    data = _load_required_json(package_lock_path)
    if not isinstance(data, dict) or not isinstance(data.get("packages"), dict):
        raise SbomInputError(f"{package_lock_path}: unsupported npm lock: missing 'packages' map")
    packages = []
    excluded: list[dict[str, str]] = []
    for spec, item in data["packages"].items():
        if not isinstance(item, dict):
            raise SbomInputError(
                f"{package_lock_path}: malformed npm lock entry {spec!r}: expected an object"
            )
        link = item.get("link")
        if link is not None and not isinstance(link, bool):
            raise SbomInputError(
                f"{package_lock_path}: malformed npm lock entry {spec!r}: 'link' is not a boolean"
            )
        name = npm_package_name(spec, item)
        if link is True:
            exclusion = {"spec": spec, "reason": "workspace-link", "name": name or spec}
            resolved = item.get("resolved")
            if isinstance(resolved, str):
                exclusion["resolved"] = resolved
            excluded.append(exclusion)
            continue
        version = item.get("version")
        if not isinstance(version, str) or not version:
            raise SbomInputError(
                f"{package_lock_path}: malformed npm lock entry {spec!r}: "
                "missing or non-string 'version'"
            )
        if name is None:
            raise SbomInputError(
                f"{package_lock_path}: cannot resolve npm package identity for entry {spec!r}"
            )
        if name in PROJECT_PACKAGE_NAMES:
            excluded.append({"spec": spec, "reason": "project-package", "name": name})
            continue
        namespace = None
        purl_name = name
        if name.startswith("@") and "/" in name:
            namespace, purl_name = name.split("/", 1)
        packages.append(
            {
                "name": name,
                "version": version,
                "license": item.get("license"),
                "purl": build_purl("npm", purl_name, version, namespace=namespace),
                "origin": "registry",
            }
        )
    if not packages:
        raise SbomInputError(
            f"{package_lock_path}: no third-party packages resolved from lock input"
        )
    return LockInventory(packages, excluded)


def cargo_origin(source: str | None) -> str:
    """Classify a Cargo package origin from its ``source`` field.

    Only the exact canonical crates.io index sources count as crates.io: a
    custom registry or mirror whose URL merely contains ``crates.io-index`` is
    ``registry-other`` and never receives a crates.io purl.
    """
    if source is None:
        return "path"
    if source in _CRATES_IO_SOURCES:
        return "registry"
    if source.startswith(("registry+", "sparse+")):
        return "registry-other"
    if source.startswith("git+"):
        return "git"
    return "other"


def rust_packages(lock_path: Path) -> LockInventory:
    """Parse ``Cargo.lock`` via TOML and keep origin provenance.

    Only crates.io registry packages receive a crates.io purl; git, path and
    alternate-registry packages keep their raw ``source`` string instead so the
    document never claims a registry identity the lock does not assert. A
    wrong-typed or malformed ``source``/``checksum`` value fails the parse.
    """
    text = _read_required_text(lock_path)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise SbomInputError(f"{lock_path}: invalid TOML: {error}") from error
    entries = data.get("package")
    if not isinstance(entries, list):
        raise SbomInputError(f"{lock_path}: unsupported Cargo.lock: missing 'package' array")
    packages = []
    excluded: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise SbomInputError(f"{lock_path}: Cargo.lock package entry is not a table")
        name, version = entry.get("name"), entry.get("version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise SbomInputError(f"{lock_path}: Cargo.lock package entry missing name/version")
        if name in PROJECT_PACKAGE_NAMES:
            excluded.append(
                {"spec": f"{name} {version}", "reason": "project-package", "name": name}
            )
            continue
        source = entry.get("source")
        if source is not None and (not isinstance(source, str) or not source):
            raise SbomInputError(
                f"{lock_path}: Cargo.lock package {name!r} has a malformed 'source' field"
            )
        checksum = entry.get("checksum")
        if checksum is not None and (
            not isinstance(checksum, str) or _CARGO_CHECKSUM_RE.fullmatch(checksum) is None
        ):
            raise SbomInputError(
                f"{lock_path}: Cargo.lock package {name!r} has a malformed SHA256 'checksum'"
            )
        origin = cargo_origin(source)
        item: dict[str, Any] = {
            "name": name,
            "version": version,
            "license": None,
            "origin": origin,
            "source": source,
            "checksum": checksum,
        }
        if origin == "registry":
            item["purl"] = build_purl("cargo", name, version)
        packages.append(item)
    if not packages:
        raise SbomInputError(f"{lock_path}: no third-party packages resolved from lock input")
    return LockInventory(packages, excluded)


_PARSERS = {
    "python-runtime": python_packages,
    "web-node": npm_packages,
    "desktop-node": npm_packages,
    "desktop-rust": rust_packages,
}

_CARGO_ORIGINS = ("registry", "registry-other", "git", "path", "other")


def _input_provenance(
    key: str, relative: str, ecosystem: str, path: Path, inventory: LockInventory
) -> dict[str, Any]:
    packages = inventory.packages
    entry: dict[str, Any] = {
        "component": key,
        "path": relative,
        "ecosystem": ecosystem,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "packages": len(packages),
        "excluded_entries": inventory.excluded,
    }
    if ecosystem == "cargo":
        origins = dict.fromkeys(_CARGO_ORIGINS, 0)
        for item in packages:
            origin = item.get("origin")
            origins[origin if origin in origins else "other"] += 1
        entry["origins"] = origins
        reviewed = [
            {
                "record_id": item["review_record_id"],
                "name": item["name"],
                "version": item["version"],
                "declared_expression": item["license"],
                "chosen_license": item["license_concluded"],
                "text_path": item["review_text_path"],
                "text_sha256": item["review_text_sha256"],
                "text_size_bytes": item["review_text_size"],
                "reference": item.get("review_reference"),
            }
            for item in packages
            if item.get("review_record_id")
        ]
        if reviewed:
            entry["reviewed_choices"] = reviewed
    return entry


def _apply_reviewed_choices(root: Path, packages: list[dict]) -> None:
    """Annotate exact approved Cargo.lock identities with the reviewed choice.

    Cargo.lock carries no license expression, so an approved reviewed record
    supplies the exact upstream ``licenseDeclared`` and the selected MIT
    conclusion. Every approved record must match exactly one canonical
    registry package and the lock checksum must match; proposed, unapproved,
    stale or mismatched records fail the whole run instead of emitting a
    partial or misleading notice.
    """

    choices = load_reviewed_choices(root)
    if not choices:
        return
    for choice in choices:
        if not choice.approved:
            raise ReviewedChoiceError(
                f"reviewed choice {choice.id} ({choice.described}) is {choice.state!r}; "
                "SBOM/notice generation refuses proposed or unapproved records"
            )
    by_identity = {choice.identity: choice for choice in choices}
    applied: dict[str, int] = {choice.id: 0 for choice in choices}
    for item in packages:
        identity = (item["name"], item["version"], item.get("source"))
        choice = by_identity.get(identity)
        if choice is None:
            continue
        if item.get("origin") != "registry":
            raise ReviewedChoiceError(
                f"reviewed choice {choice.id} ({choice.described}) matched a "
                f"{item.get('origin')!r} package; only canonical crates.io registry "
                "identities may receive a reviewed choice"
            )
        if item.get("checksum") != choice.checksum_sha256:
            raise ReviewedChoiceError(
                f"reviewed choice {choice.id} ({choice.described}): Cargo.lock checksum "
                f"{item.get('checksum')!r} does not match the record checksum "
                f"{choice.checksum_sha256!r}"
            )
        text_path = root / choice.text_repo_path
        try:
            text = text_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ReviewedChoiceError(
                f"reviewed choice {choice.id} ({choice.described}): retained text is not "
                f"readable UTF-8 ({type(error).__name__}): {choice.text_repo_path}"
            ) from error
        item["license"] = choice.declared_expression
        item["license_concluded"] = choice.chosen_license
        item["license_comments"] = (
            f"Project-selected {choice.chosen_license} branch per reviewed record "
            f"{choice.id}; declared expression {choice.declared_expression!r}; retained "
            f"text {choice.text_repo_path} SHA-256 {choice.text_sha256}; evidence reference "
            f"{choice.reference}; technical review evidence, not legal clearance"
        )
        item["review_record_id"] = choice.id
        item["review_text_path"] = choice.text_repo_path
        item["review_text_sha256"] = choice.text_sha256
        item["review_text_size"] = len(text.encode("utf-8"))
        item["review_reference"] = choice.reference
        item["review_text"] = text
        applied[choice.id] += 1
    for choice in choices:
        if applied.get(choice.id, 0) != 1:
            raise ReviewedChoiceError(
                f"stale reviewed choice {choice.id} ({choice.described}): matched exactly "
                f"{applied.get(choice.id, 0)} time(s) in the Cargo.lock inventory; an "
                "approved record must match exactly once or be removed/re-reviewed"
            )


def collect_components(
    *, root: Path | None = None
) -> tuple[dict[str, list[dict]], list[dict[str, Any]]]:
    """Parse every required lock input and return components plus provenance.

    Raises :class:`SbomInputError` listing every missing, malformed or empty
    input instead of emitting silently incomplete documents.
    """
    base = Path(root) if root is not None else ROOT
    components: dict[str, list[dict]] = {}
    inputs: list[dict[str, Any]] = []
    errors: list[str] = []
    for key, relative, ecosystem in LOCK_INPUTS:
        path = base / relative
        try:
            inventory = _PARSERS[key](path)
        except SbomInputError as error:
            errors.extend(error.errors)
            continue
        components[key] = inventory.packages
        if key == "desktop-rust":
            try:
                _apply_reviewed_choices(base, inventory.packages)
            except ReviewedChoiceError as error:
                errors.extend(error.errors)
                continue
        inputs.append(_input_provenance(key, relative, ecosystem, path, inventory))
    if errors:
        raise SbomInputError(errors)
    return components, inputs


def _add_packages(document: dict[str, Any], packages: list[dict]) -> None:
    for index, item in enumerate(packages, start=1):
        spdx_id = f"SPDXRef-Package-{index}"
        package: dict[str, Any] = {
            "SPDXID": spdx_id,
            "name": item["name"],
            "versionInfo": item["version"],
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": item.get("license_concluded") or "NOASSERTION",
            "licenseDeclared": item.get("license") or "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "supplier": "NOASSERTION",
        }
        if item.get("license_comments"):
            package["licenseComments"] = item["license_comments"]
        if item.get("purl"):
            package["externalRefs"] = [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": item["purl"],
                }
            ]
        if item.get("checksum"):
            package["checksums"] = [{"algorithm": "SHA256", "checksumValue": item["checksum"]}]
        if item.get("source"):
            package["sourceInfo"] = item["source"]
        document["packages"].append(package)
        document["relationships"].append(
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relatedSpdxElement": spdx_id,
                "relationshipType": "DESCRIBES",
            }
        )


def write_component_sbom(
    output_dir: Path,
    key: str,
    packages: list[dict],
    *,
    created: str | None = None,
) -> Path:
    """Write one SPDX 2.3 document with a unique namespace for this run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = created if created is not None else utc_timestamp()
    document: dict[str, Any] = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"eurogas-nexus-{key}",
        "documentNamespace": f"{DOCUMENT_NAMESPACE_BASE}/eurogas-nexus-{key}-{uuid.uuid4()}",
        "creationInfo": {
            "created": created_at,
            "creators": ["Tool: eurogas-nexus-release-tooling"],
        },
        "packages": [],
        "relationships": [],
    }
    _add_packages(document, packages)
    target = output_dir / f"eurogas-nexus-{key}.spdx.json"
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def notices(packages_by_component: dict[str, list[dict]]) -> str:
    lines = [
        "# Third-Party Notices",
        "",
        "Eurogas Nexus is proprietary software. This file lists the packages and",
        "lock-declared license expressions recorded in the enforced dependency",
        "locks used by the corresponding release build. `NOASSERTION` means the",
        "lock carried no machine-readable license expression for that package, not",
        "that no license applies.",
        "",
        "Scope limits:",
        "",
        "- Lock files over-cover the shipped artifact: npm locks include dev/optional",
        "  dependencies and Cargo.lock includes build/dev dependencies for all",
        "  targets, so packages not installed on a customer machine can appear.",
        "- The Python lock is the runtime lock; Python build/test tooling is not",
        "  inventoried here.",
        "- Cargo.lock and the Python lock carry no license metadata, so their",
        "  packages are reported as `NOASSERTION` and need manual review, except",
        "  exact approved reviewed-choice records whose evidence is reproduced below.",
        "- Operating-system packages inside the runtime container image, native",
        "  binaries bundled by the installers, and vendored third-party code are",
        "  not inventoried here.",
        "- npm `link: true` workspace entries are local paths, not registry",
        "  packages; they are excluded from these lists and disclosed under",
        "  `excluded_entries` in `sbom-manifest.json`.",
        "- Reviewed Cargo license choices select only the named MIT branch for one",
        "  exact package identity; the original expression remains declared above,",
        "  the other branches are not approved, and this is not legal clearance.",
        "- This file is not a legal review; it includes full retained AUTHORS text",
        "  only for exact reviewed Cargo choices and otherwise no full license texts.",
        "  Obtain other texts from the upstream packages and confirm obligations with",
        "  legal counsel before distribution.",
        "",
        "Package counts and the SHA-256 of every lock input are recorded in",
        "`sbom-manifest.json`.",
        "",
    ]
    for component, packages in sorted(packages_by_component.items()):
        declared = sum(1 for item in packages if item.get("license"))
        reviewed = sum(1 for item in packages if item.get("review_record_id"))
        lines.append(f"## {component}")
        lines.append("")
        lines.append(
            f"{len(packages)} packages recorded: {declared} with a lock-declared license "
            f"expression, {len(packages) - declared} unknown (`NOASSERTION`), "
            f"{reviewed} exact reviewed choice(s)."
        )
        lines.append("")
        if not packages:
            lines.append("_No packages recorded._")
            continue
        for item in sorted(
            packages, key=lambda package: (package["name"].lower(), package["version"])
        ):
            license_text = item.get("license") or "NOASSERTION"
            if item.get("review_record_id"):
                lines.append(
                    f"- {item['name']} {item['version']} - declared: {license_text}; "
                    f"selected: {item['license_concluded']} (record "
                    f"{item['review_record_id']}; text SHA-256 "
                    f"{item['review_text_sha256']}; {item['review_text_size']} bytes)"
                )
            else:
                lines.append(f"- {item['name']} {item['version']} ({license_text})")
        lines.append("")
    reviewed_items = [
        item
        for packages in packages_by_component.values()
        for item in packages
        if item.get("review_record_id")
    ]
    if reviewed_items:
        lines.extend(
            [
                "## Reviewed Cargo license-choice evidence",
                "",
                "These records select the MIT branch for exact package identities only.",
                "The original upstream expression is retained above and in the SPDX",
                "`licenseDeclared`; the other expression terms are not approved. The",
                "complete retained upstream AUTHORS text is reproduced below as notice",
                "evidence. This is technical review evidence, not legal clearance.",
                "",
            ]
        )
        for item in sorted(
            reviewed_items, key=lambda package: (package["name"].lower(), package["version"])
        ):
            lines.extend(
                [
                    f"### {item['name']} {item['version']} - {item['review_record_id']}",
                    "",
                    f"- Declared expression: `{item['license']}`",
                    f"- Selected license: `{item['license_concluded']}`",
                    f"- Evidence text: `{item['review_text_path']}` (SHA-256 "
                    f"`{item['review_text_sha256']}`, {item['review_text_size']} bytes)",
                    "- Record reference: "
                    f"{item.get('review_reference') or 'reviewed-choice record file'}",
                    "",
                    "```text",
                    *item["review_text"].splitlines(),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="release-assets/sbom")
    parser.add_argument("--notices", default="release-assets/sbom/THIRD_PARTY_NOTICES.md")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    notices_path = Path(args.notices)
    try:
        components, inputs = collect_components()
    except SbomInputError as error:
        print(json.dumps({"ok": False, "errors": error.errors}, indent=2))
        return 1

    generated_at = utc_timestamp()
    files = {
        key: write_component_sbom(output_dir, key, packages, created=generated_at)
        for key, packages in components.items()
    }
    notices_path.parent.mkdir(parents=True, exist_ok=True)
    notices_path.write_text(notices(components), encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "format": "SPDX-2.3",
        "components": {key: path.name for key, path in files.items()},
        "artifacts": {},
        "notes": notices_path.name,
        "generated_at_utc": generated_at,
        "inputs": inputs,
        "inventory_scope": INVENTORY_SCOPE,
        "component_packages": {
            key: {
                "packages": len(packages),
                "license_declared": sum(1 for item in packages if item.get("license")),
                "license_unknown": sum(1 for item in packages if not item.get("license")),
            }
            for key, packages in components.items()
        },
    }
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
