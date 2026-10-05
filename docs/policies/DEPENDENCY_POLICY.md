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

`scripts/ci/audit_dependencies.py` provides two bounded gates. Both are
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

What the audits do not cover, and therefore cannot clear:

- Rust/crate dependencies (for example `clients/desktop/src-tauri`); that
  review is still outstanding.
- Full license texts, bundled `LICENSE`/`NOTICE` files, vendored code,
  container base images and SPDX documents; both modes match declared
  metadata terms only.
- Operating-system packages inside the runtime container image and
  native/installer binaries bundled by the clients.
- The legal effect of `OR`/`WITH` expressions or exceptions: any restricted
  term in any scanned metadata field or lock expression is reported for
  review, and no exception is treated as permission.

Until the Rust dependency licenses, the full license texts and the
artifact-level redistribution review have been completed, a clean audit result
(including the npm lock gate) must not be reported as full delivery license
compliance.

## Review Requirements

Every new dependency must document:

- purpose;
- license;
- runtime or development scope;
- why the standard library or existing dependency is insufficient;
- whether it introduces network, process, data, or deployment risk.
