"""Load and validate the fixed reviewed Cargo license-choice records.

This is a deliberately narrow, Cargo-only exception mechanism for RFC-0002.
It is not an SPDX ``OR`` parser and not a license-name allowlist: a record
binds one exact ``(name, version, source)`` identity to the exact upstream
declared expression, the Cargo.lock archive checksum, a flat ordered term list,
the chosen ``MIT`` branch, and the SHA-256 of the complete retained upstream
AUTHORS bytes.

Only ``state: approved`` records can exempt, and only when every scalar field,
the retained text file and the actual Cargo-resolved ``AUTHORS`` file match.
The record file path is a fixed repository-relative constant; there is no CLI
flag, environment variable or alternate path that can add an approval. An
absent file means zero exemptions. Unknown fields, malformed values, duplicate
ids/identities, traversal, symlinks, junctions, hash mismatches and stale
records all fail closed.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

SCHEMA_VERSION = 1

#: Fixed public record path. It is never configurable at runtime.
RECORDS_RELATIVE_PATH = "docs/policies/reviewed-cargo-license-choices.json"

#: Retained evidence lives only under this repository-relative directory.
LICENSES_PREFIX = PurePosixPath("docs/policies/licenses")

#: The exact canonical crates.io source strings already recognized by the SBOM
#: inventory reader. A record can never target a git, path or mirror package.
CRATES_IO_SOURCES = frozenset(
    {
        "registry+https://github.com/rust-lang/crates.io-index",
        "sparse+https://index.crates.io/",
    }
)

_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_VERSION_RE = re.compile(
    r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)
_TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

_RESERVED_TERMS = frozenset({"AND", "OR", "WITH"})
_PLACEHOLDER_TERMS = frozenset({"unknown", "none", "noassertion", "unlicensed", "n/a"})

_RECORD_FIELDS = frozenset(
    {
        "id",
        "state",
        "package",
        "declared_expression",
        "expression_terms",
        "chosen_license",
        "license_text",
        "review",
    }
)
_PACKAGE_FIELDS = frozenset({"name", "version", "source", "checksum_sha256"})
_LICENSE_TEXT_FIELDS = frozenset({"repo_path", "sha256", "upstream_url"})
_REVIEW_FIELDS = frozenset({"approved_by", "approved_on", "reference"})


class ReviewedChoiceError(RuntimeError):
    """A reviewed-choice record file or an evidence file is not acceptable."""

    def __init__(self, errors: str | list[str]) -> None:
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class ReviewedChoice:
    """One validated reviewed-choice record; only ``approved`` can exempt."""

    id: str
    state: str
    name: str
    version: str
    source: str
    checksum_sha256: str
    declared_expression: str
    expression_terms: tuple[str, ...]
    chosen_license: str
    text_repo_path: str
    text_sha256: str | None
    text_size: int | None
    upstream_url: str
    approved_by: tuple[str, ...]
    approved_on: str | None
    reference: str | None

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.name, self.version, self.source)

    @property
    def approved(self) -> bool:
        return self.state == "approved"

    @property
    def described(self) -> str:
        return f"{self.name}@{self.version}"


def _fail(message: str) -> None:
    raise ReviewedChoiceError(message)


def _is_link_or_junction(path: Path) -> bool:
    """Return True for a symlink or (on Windows) any reparse-point/junction."""

    try:
        if path.is_symlink():
            return True
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return True
        except OSError:
            return True
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse)


def _expect_object(value: object, label: str, fields: frozenset[str]) -> dict:
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    keys = set(value)
    missing = sorted(fields - keys)
    unknown = sorted(keys - fields)
    if missing:
        _fail(f"{label} is missing required field(s): {', '.join(missing)}")
    if unknown:
        _fail(f"{label} has unknown field(s): {', '.join(unknown)}")
    return value


def _expect_string(
    value: object,
    label: str,
    *,
    pattern: re.Pattern[str] | None = None,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        _fail(f"{label} must be a string")
    if not allow_empty and not value:
        _fail(f"{label} must not be empty")
    if value != value.strip():
        _fail(f"{label} must not have leading or trailing whitespace")
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail(f"{label} is malformed: {value!r}")
    return value


def _expect_string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        _fail(f"{label} must be a JSON array of role strings")
    roles: list[str] = []
    for index, item in enumerate(value, start=1):
        role = _expect_string(item, f"{label}[{index}]")
        if role in roles:
            _fail(f"{label} repeats the role {role!r}")
        roles.append(role)
    return tuple(roles)


def _expect_date(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        _fail(f"{label} must be an ISO date (YYYY-MM-DD) or null")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        _fail(f"{label} is not a valid ISO date: {value!r} ({error})")
    return value


def _expect_reference(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _expect_string(value, label)


def _expect_https_url(value: object, label: str) -> str:
    url = _expect_string(value, label)
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        _fail(f"{label} must be a public HTTPS URL: {url!r}")
    if parts.username is not None or parts.password is not None:
        _fail(f"{label} must not contain credentials")
    return url


def _validate_text_path(root: Path, repo_path: str, label: str) -> Path:
    if "\\" in repo_path or ":" in repo_path:
        _fail(f"{label}.license_text.repo_path must use forward slashes: {repo_path!r}")
    pure = PurePosixPath(repo_path)
    prefix_length = len(LICENSES_PREFIX.parts)
    if pure.is_absolute() or pure.parts[:prefix_length] != LICENSES_PREFIX.parts:
        _fail(
            f"{label}.license_text.repo_path must be a relative path under "
            f"docs/policies/licenses/: {repo_path!r}"
        )
    if len(pure.parts) <= prefix_length or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        _fail(f"{label}.license_text.repo_path is not a canonical relative path: {repo_path!r}")
    current = root
    for part in pure.parts:
        current = current / part
        if _is_link_or_junction(current):
            _fail(
                f"{label}.license_text.repo_path traverses a symlink or junction: "
                f"{repo_path!r}"
            )
    return current


def _validate_terms(value: object, declared_expression: str, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        _fail(f"{label}.expression_terms must be a non-empty JSON array")
    terms: list[str] = []
    for index, item in enumerate(value, start=1):
        term = _expect_string(item, f"{label}.expression_terms[{index}]", pattern=_TERM_RE)
        if term in _RESERVED_TERMS:
            _fail(f"{label}.expression_terms must not contain the operator {term!r}")
        if term.casefold().startswith("licenseref-") or term.casefold() in _PLACEHOLDER_TERMS:
            _fail(f"{label}.expression_terms contains an unreviewed placeholder: {term!r}")
        if term in terms:
            _fail(f"{label}.expression_terms repeats the term {term!r}")
        terms.append(term)
    if " OR ".join(terms) != declared_expression:
        _fail(
            f"{label}.expression_terms joined with ' OR ' must equal "
            f"declared_expression exactly"
        )
    return tuple(terms)


def _verify_regular_file(path: Path, expected_sha256: str, label: str) -> int:
    if not path.exists():
        raise ReviewedChoiceError(f"{label} is missing: {path}")
    if _is_link_or_junction(path):
        raise ReviewedChoiceError(f"{label} is a symlink or junction: {path}")
    if not path.is_file():
        raise ReviewedChoiceError(f"{label} is not a regular file: {path}")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ReviewedChoiceError(
            f"{label} is unreadable ({type(error).__name__}): {path}"
        ) from error
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise ReviewedChoiceError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, got {actual}: {path}"
        )
    return len(payload)


def _load_choices(record_path: Path, root: Path) -> list[ReviewedChoice]:
    if not record_path.exists():
        return []
    if _is_link_or_junction(record_path):
        _fail(f"reviewed-choice record file is a symlink or junction: {record_path}")
    if not record_path.is_file():
        _fail(f"reviewed-choice record path is not a regular file: {record_path}")
    try:
        text = record_path.read_text(encoding="utf-8")
    except OSError as error:
        _fail(f"reviewed-choice record file is unreadable ({type(error).__name__}): {record_path}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        _fail(f"reviewed-choice record file is not valid JSON: {error}")

    _expect_object(payload, "reviewed-choice file", frozenset({"schema_version", "records"}))
    schema_version = payload["schema_version"]
    if isinstance(schema_version, bool) or schema_version != SCHEMA_VERSION:
        _fail(f"unsupported reviewed-choice schema_version: {schema_version!r}")
    raw_records = payload["records"]
    if not isinstance(raw_records, list):
        _fail("reviewed-choice 'records' must be a JSON array")

    choices: list[ReviewedChoice] = []
    seen_ids: set[str] = set()
    seen_identities: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(raw_records, start=1):
        label = f"reviewed-choice record #{index}"
        record = _expect_object(raw, label, _RECORD_FIELDS)
        record_id = _expect_string(record["id"], f"{label}.id", pattern=_ID_RE)
        if record_id in seen_ids:
            _fail(f"duplicate reviewed-choice record id: {record_id!r}")
        seen_ids.add(record_id)

        state = record["state"]
        if state not in {"approved", "proposed"}:
            _fail(f"{label}.state must be 'approved' or 'proposed': {state!r}")

        package = _expect_object(record["package"], f"{label}.package", _PACKAGE_FIELDS)
        name = _expect_string(package["name"], f"{label}.package.name", pattern=_NAME_RE)
        version = _expect_string(
            package["version"], f"{label}.package.version", pattern=_VERSION_RE
        )
        source = _expect_string(package["source"], f"{label}.package.source")
        if source not in CRATES_IO_SOURCES:
            _fail(
                f"{label}.package.source must be the exact canonical crates.io source: "
                f"{source!r}"
            )
        checksum = _expect_string(
            package["checksum_sha256"], f"{label}.package.checksum_sha256", pattern=_HEX64_RE
        )
        identity = (name, version, source)
        if identity in seen_identities:
            _fail(f"duplicate reviewed-choice identity: {name}@{version} ({source})")
        seen_identities.add(identity)

        declared_expression = _expect_string(
            record["declared_expression"], f"{label}.declared_expression"
        )
        terms = _validate_terms(record["expression_terms"], declared_expression, label)

        chosen_license = record["chosen_license"]
        if chosen_license != "MIT":
            _fail(f"{label}.chosen_license must be exactly 'MIT': {chosen_license!r}")
        if chosen_license not in terms:
            _fail(f"{label}.chosen_license 'MIT' must be one of expression_terms")

        license_text = _expect_object(
            record["license_text"], f"{label}.license_text", _LICENSE_TEXT_FIELDS
        )
        repo_path = _expect_string(
            license_text["repo_path"], f"{label}.license_text.repo_path"
        )
        text_path = _validate_text_path(root, repo_path, label)
        upstream_url = _expect_https_url(
            license_text["upstream_url"], f"{label}.license_text.upstream_url"
        )
        raw_sha256 = license_text["sha256"]
        text_sha256: str | None
        if raw_sha256 is None:
            text_sha256 = None
        else:
            text_sha256 = _expect_string(
                raw_sha256, f"{label}.license_text.sha256", pattern=_HEX64_RE
            )

        review = _expect_object(record["review"], f"{label}.review", _REVIEW_FIELDS)
        approved_by = _expect_string_list(review["approved_by"], f"{label}.review.approved_by")
        approved_on = _expect_date(review["approved_on"], f"{label}.review.approved_on")
        reference = _expect_reference(review["reference"], f"{label}.review.reference")

        text_size: int | None = None
        if state == "approved":
            if text_sha256 is None:
                _fail(f"{label} is approved but license_text.sha256 is null")
            if not approved_by:
                _fail(f"{label} is approved but review.approved_by is empty")
            if approved_on is None:
                _fail(f"{label} is approved but review.approved_on is null")
            if reference is None:
                _fail(f"{label} is approved but review.reference is null")
            text_size = _verify_regular_file(
                text_path, text_sha256, f"{label} retained text"
            )
        elif text_sha256 is not None:
            # A proposed record may already carry a reviewed text hash; if it
            # does, the bytes must still match so drift is visible immediately.
            text_size = _verify_regular_file(
                text_path, text_sha256, f"{label} retained text"
            )

        choices.append(
            ReviewedChoice(
                id=record_id,
                state=state,
                name=name,
                version=version,
                source=source,
                checksum_sha256=checksum,
                declared_expression=declared_expression,
                expression_terms=terms,
                chosen_license=chosen_license,
                text_repo_path=repo_path,
                text_sha256=text_sha256,
                text_size=text_size,
                upstream_url=upstream_url,
                approved_by=approved_by,
                approved_on=approved_on,
                reference=reference,
            )
        )
    return choices


def load_reviewed_choices(repository_root: Path | None = None) -> list[ReviewedChoice]:
    """Load the fixed record file for ``repository_root``.

    An absent file means no exemptions. Every malformed, duplicated, unsafe or
    hash-mismatched record raises :class:`ReviewedChoiceError`; callers fail
    closed instead of silently ignoring it.
    """

    root = (
        Path(repository_root)
        if repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    return _load_choices(root / RECORDS_RELATIVE_PATH, root)


def verify_package_authors_file(choice: ReviewedChoice, manifest_path: str) -> int:
    """Verify the actual Cargo-resolved ``<manifest parent>/AUTHORS`` bytes.

    The gate must not trust the committed evidence copy alone: the crate bytes
    Cargo actually resolved must carry the same AUTHORS text hash.
    """

    if choice.text_sha256 is None:
        raise ReviewedChoiceError(
            f"reviewed choice {choice.id} has no text SHA-256 to verify against"
        )
    authors_path = Path(manifest_path).parent / "AUTHORS"
    return _verify_regular_file(
        authors_path,
        choice.text_sha256,
        f"Cargo-resolved AUTHORS for {choice.described} (record {choice.id})",
    )
