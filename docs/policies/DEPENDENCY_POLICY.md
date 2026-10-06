# Dependency Policy

## Allowed Backend Default Stack

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- HTTPX
- pandas
- NumPy
- PyArrow
- python-dateutil
- PyYAML
- pytest
- Ruff

## Bootstrap Dependency Scope

Backend foundation milestones use the smallest useful subset:

- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- HTTPX
- pytest
- Ruff

Heavy optional dependencies are deferred until a milestone proves they are
needed.

## Active Client Stack

The supported client set includes SDK, CLI, web, and Windows client surfaces.

Allowed only when the selected milestone activates that surface:

- SDK and CLI: Python standard library plus HTTPX/Pydantic if already approved
  for backend client use.
- Web client: React, TypeScript, Vite, plain CSS or CSS modules, test tooling,
  and MapLibre GL where dependencies are available.
- Windows client: Tauri and Rust wrapping the web workspace.

Client dependencies must not be added during backend foundation milestones.
Electron is not approved.

If internet access is unavailable and dependencies are not already installed,
the client milestone must create local file structure, interfaces, mocks, and a
gap report instead of claiming a working build.

## Restricted Licenses

Do not add dependencies under GPL, LGPL, AGPL, SSPL, BUSL, Elastic,
Redis-RSAL, Commons-Clause, or PolyForm terms without explicit review.

## License Audit Scope and Limitations

`scripts/ci/audit_dependencies.py` provides three bounded gates. All are
**review-required detection**, not legal determinations.

### Python metadata (default mode)

`python scripts/ci/audit_dependencies.py [site_packages_dir]` scans installed
Python distributions' `*.dist-info/METADATA` for the restricted terms above:

- A clean result means no restricted license terms were detected in the
  scanned metadata; it is **not** a commercial clearance.
- `License-Expression` follows the Core Metadata specification: it replaces the
  legacy `License` header and takes precedence when both are present.
- Every `License ::` classifier is read, not only the OSI-approved subset.
- Folded and repeated headers are parsed with the standard library email
  parser.

Fail-closed behaviour: a target with no distribution metadata at all, a
`*.dist-info` directory without `METADATA`, and missing, unreadable or
malformed metadata all fail the audit because those distributions were not
audited. Unknown licenses (metadata with no license evidence) are listed for
review and do not fail the run, matching the existing policy.

### Node/npm locks (npm mode)

`python scripts/ci/audit_dependencies.py --npm-lock <path> ...` audits the exact
`package-lock.json` files named on the command line with the shared structured
lock inventory reader in `scripts/release/generate_sboms.py`, so package
identity, nested/scoped resolution and workspace exclusions have one
implementation. CI and the release workflow run it for
`clients/web/package-lock.json` and `clients/desktop/package-lock.json` before
packaging and evidence publication.

The npm gate is strict and fails closed on:

- missing, blank or non-string `license` values; an entry with no auditable
  license is refused, never treated as clean;
- explicit `UNLICENSED`;
- unknown placeholders (`UNKNOWN`, `NONE`, `NOASSERTION`, `N/A`) and custom
  `LicenseRef-` references, including within combined expressions, pending review;
- file-only references pending review (`SEE LICENSE IN ...` and bare
  `LICENSE`/`LICENCE`/`COPYING`/`NOTICE` file names);
- any restricted term anywhere in the expression, including inside `OR`,
  `AND` or `WITH` combinations. A permissive branch never auto-approves an
  expression that also names a restricted license, and the tool does not
  interpret the legal effect of `OR`/`WITH`.

Locks that are missing, malformed, empty or uninventoriable are rejected
through the same reader that builds the SPDX inventories, so a lock that
cannot be fully inventoried fails the gate instead of yielding a partial
result.

Coverage and its limits:

- The audit covers the complete lock inventory of the named locks, including
  dev and optional entries and every nested/scoped duplicate. Lock files
  over-cover the shipped artifact, so this is **conservative lock coverage,
  not shipped-artifact proof**; install-time resolution in `npm ci` is not
  re-verified.
- `link: true` workspace entries and this repository's own project packages
  are local, not registry third-party packages; the shared reader excludes
  them and the audit reports how many entries were excluded.
- Lock-declared expressions are not license texts. The audit does not read
  bundled `LICENSE`/`NOTICE` files or vendored code, and it does not clear
  redistribution obligations.

Metadata reference: [PyPA Core Metadata specification](https://packaging.python.org/en/latest/specifications/core-metadata/).

### Rust crate graph (cargo mode)

`python scripts/ci/audit_dependencies.py --cargo-lock clients/desktop/src-tauri/Cargo.lock`
audits the desktop crate graph's declared licenses. The third-party inventory
is the shared structured `Cargo.lock` reader in
`scripts/release/generate_sboms.py`, and the resolved graph is collected with
`cargo metadata --locked --format-version 1 --all-features --manifest-path
clients/desktop/src-tauri/Cargo.toml` (no `--no-deps`) through an argv
subprocess with an explicit timeout. `--locked` turns a stale lock into a hard
failure, so the audited inventory and the Cargo-resolved graph must agree. The
release workflow runs this gate after the Rust toolchain setup and before scan
evidence is published. Ordinary CI also runs the same command after pinned
toolchain setup, so failures can be discovered without attempting publication.
A configured workflow is not a passed audit: inspect its actual job result.
Gate failures report only the exit/status and a safe instruction: raw `cargo`
stderr or exception payloads are deliberately not echoed, because they can
contain private registry URLs or credentials.

Every `Cargo.lock` third-party entry must match a `cargo metadata` package by
exact name/version/source identity -- never by name alone. The gate fails
closed on:

- a missing `cargo` executable, a timeout, any non-zero exit (including a
  `--locked` refusal) and output that is not valid JSON;
- an absent, empty or non-list `packages` array, malformed package fields, or
  an entry without a name/version/source/manifest path;
- a lock entry omitted from, duplicated in or contradicted by the metadata,
  and any metadata package the `Cargo.lock` inventory does not cover;
- a missing, unreadable, malformed or `[package]`-identity-less sibling
  `Cargo.toml`, more or fewer than one metadata package resolving its
  `manifest_path` to that exact manifest, a root whose `source` is not null or
  whose name/version differ from the manifest, and a `Cargo.lock` project-name
  disclosure that is not exactly the verified root;
- missing, blank, non-string, `UNLICENSED`, unknown-placeholder,
  `LicenseRef-` or file-only (`SEE LICENSE IN ...`, bare `LICENSE`/`NOTICE`
  file names) declarations, and any restricted term anywhere in the
  expression, exactly as the npm gate checks them;
- a `Cargo.lock` the shared reader cannot fully inventory.

The only excluded package is the audited root, verified from both sides: the
sibling `Cargo.toml` is read structurally with the standard library `tomllib`
and must carry a `[package]` name/version, exactly one `cargo metadata` entry
must resolve its `manifest_path` to that exact manifest with a null `source`
and the same name/version, and `Cargo.lock` must disclose exactly one project
package with that same name/version. `workspace_members` is never trusted, and
every other lock-disclosed project name or same-name package at another path
is reported as an unaudited gap instead of inheriting the exemption. Git, path
and alternate-registry packages are audited for restricted terms but remain
listed for provenance review and fail the gate; a warning-only successful exit
does not count as review. They are never auto-approved.

Coverage and its limits:

- `--all-features` and the full resolved graph over-include build, dev and
  inactive-feature packages that may not be shipped, so this is
  **conservative lock coverage, not shipped-artifact proof**.
- Declared license expressions only: no full license texts, no vendored code,
  no OS/native/installer artifacts, no container contents, and no legal
  interpretation of `OR`/`WITH`; redistribution obligations are not cleared.

Metadata reference: [cargo metadata](https://doc.rust-lang.org/stable/cargo/commands/cargo-metadata.html).

### Python license text collection (installed evidence, not wired into releases)

`python scripts/release/collect_python_license_texts.py --site-packages <dir>
--output-dir <new-dir> [--runtime-lock requirements-runtime.lock]` collects the
actual installed license/notice text files for the exact
`requirements-runtime.lock` name/version inventory. The lock is read with the
shared structured lock reader, `METADATA` is parsed with the standard library
email parser and `RECORD` as CSV. Evidence comes from the matching
distribution's `License-File` headers (resolved at the PEP 639
`<dist-info>/licenses/` location or the legacy `<dist-info>/` location, and
still required to be listed in that distribution's own `RECORD`) or, only
when a distribution declares no `License-File` headers, from its `RECORD`
entries whose basename is a recognized license/notice/copying/copyright name.

Both input paths are explicit; nothing is downloaded, installed or invented,
and the output directory must not already exist. Absolute, traversal,
non-portable, symlinked/junctioned or unrecorded paths are refused, and
RECORD rows outside the site-packages tree (pip records installed console
scripts at paths such as `../../Scripts/*.exe`) are disclosed and skipped,
never followed; missing, duplicate, version-mismatched or metadata-broken
distributions leave the package unresolved with an explicit recorded reason.
A run that does not collect at least one text for every locked package exits
non-zero, but still writes `manifest.json` plus any partial texts, clearly
marked `status: incomplete`. The manifest records only relative paths, the
lock SHA-256, the exact lock name/version, the installed dist-info directory,
the declared-license evidence and the SHA-256 of every copied file.

Limits: this is technical evidence collection, not legal clearance or a
redistribution review. It does not interpret license terms, verify that a
copied text is complete or authoritative, or cover packages outside the
runtime lock, the build/test toolchain, vendored source, native/installer
binaries or container contents. It is deliberately not invoked by CI or the
release workflow until installed/locked coverage has been verified on the
release runner.

What the audits do not cover, and therefore cannot clear:

- Rust/crate dependencies beyond the declared-license metadata of the desktop
  crate graph: the full Rust license texts, vendored code and the
  artifact-level redistribution review for crates remain outstanding.
- Full license texts, bundled `LICENSE`/`NOTICE` files, vendored code,
  container base images and SPDX documents; every mode matches declared
  metadata terms only.
- Operating-system packages inside the runtime container image and
  native/installer binaries bundled by the clients.
- The legal effect of `OR`/`WITH` expressions or exceptions: any restricted
  term in any scanned metadata field or lock expression is reported for
  review, and no exception is treated as permission.

Until the Rust full license texts and the artifact-level redistribution
review have been completed, a clean audit result (including the npm and cargo
declared-license gates) must not be reported as full delivery license
compliance.

## Review Requirements

Every new dependency must document:

- purpose;
- license;
- runtime or development scope;
- why the standard library or existing dependency is insufficient;
- whether it introduces network, process, data, or deployment risk.
