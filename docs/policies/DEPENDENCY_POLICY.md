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

`scripts/ci/audit_dependencies.py` scans installed Python distributions'
`*.dist-info/METADATA` for the restricted terms above. It is a
**review-required detection**, not a legal determination:

- A clean result means no restricted license terms were detected in the
  scanned metadata; it is **not** a commercial clearance.
- `License-Expression` follows the Core Metadata specification: it replaces the
  legacy `License` header and takes precedence when both are present.
- Every `License ::` classifier is read, not only the OSI-approved subset.
- Folded and repeated headers are parsed with the standard library email
  parser.

Metadata reference: [PyPA Core Metadata specification](https://packaging.python.org/en/latest/specifications/core-metadata/).

What the audit does not cover, and therefore cannot clear:

- Node/npm dependencies (for example `clients/web` and the desktop bundle's
  Node tooling) and Rust/crate dependencies (for example
  `clients/desktop/src-tauri`); those reviews are still outstanding.
- Full license texts, bundled `LICENSE`/`NOTICE` files, vendored code,
  container base images and SPDX documents; the audit matches declared
  metadata terms only.
- The legal effect of `OR`/`WITH` expressions or exceptions: any restricted
  term in any scanned field is reported for review, and no exception is
  treated as permission.

Fail-closed behaviour: a target with no distribution metadata at all, a
`*.dist-info` directory without `METADATA`, and missing, unreadable or
malformed metadata all fail the audit because those distributions were not
audited. Unknown licenses (metadata with no license evidence) are listed for
review and do not fail the run, matching the existing policy.

Until the Node and Rust dependency licenses and the relevant full license
texts have been reviewed, a clean audit result must not be reported as full
delivery license compliance.

## Review Requirements

Every new dependency must document:

- purpose;
- license;
- runtime or development scope;
- why the standard library or existing dependency is insufficient;
- whether it introduces network, process, data, or deployment risk.
