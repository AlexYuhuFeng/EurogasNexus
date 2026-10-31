# Dependency licence review for commercial use (2026-10-30)

Eurogas Nexus ships commercially and closed-source, so every dependency must permit
proprietary commercial use and redistribution. The enforcing gate is the existing
fail-closed audit `scripts/ci/audit_dependencies.py` (policy:
`docs/policies/DEPENDENCY_POLICY.md`). It runs in the CI `dependency-audit` job over the
installed Python environment, both npm lock files and the desktop crate graph
(`cargo metadata`, exact identity match against `Cargo.lock`), and fails on
GPL-family, SSPL, BUSL, Elastic, Commons Clause, PolyForm and on unknown or file-only
licences.

## Result of this review

| Ecosystem | Packages | Copyleft / non-commercial | Notes |
|---|---|---|---|
| Python (runtime and dev locks) | 45 | 0 | `certifi` CA bundle is MPL-2.0; `pypdf` (contract intake, added 2026-10-31) is BSD-3-Clause |
| npm (web and desktop locks) | 101 | 0 | `lightningcss` (build-time CSS tool) is MPL-2.0 |
| Rust (desktop crate graph) | 434 | 0 | `cssparser`, `cssparser-macros`, `selectors`, `dtoa-short`, `option-ext` are MPL-2.0; `r-efi` uses its reviewed MIT branch (RCLC-0001/0002) |

No dependency had to be replaced. MPL-2.0 is file-level copyleft: the files may be
used in proprietary products as long as they are not modified. Any change to an
MPL-2.0 file must be published under MPL-2.0. On Linux the desktop app links the
system WebKitGTK/GTK libraries (LGPL) dynamically, which LGPL permits.

Non-code assets:

- Fonts are system fonts; none are bundled.
- Map tiles default to no basemap; public OSM/CARTO tiles are marked not for
  commercial use (`clients/web/src/app/mapTileProviders.ts`).

Optional OCR for scanned contracts calls a Tesseract binary (Apache-2.0) that the customer
installs; the product neither bundles it nor any GPL tool such as Poppler.

Data-provider terms, which carry more commercial risk here than code licences, are in
[DATA_SOURCE_TERMS.md](DATA_SOURCE_TERMS.md).

This is an engineering review, not legal advice.
