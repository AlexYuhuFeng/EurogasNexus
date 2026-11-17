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
| npm (web and desktop locks) | 102 | 0 | `lightningcss` (build-time CSS tool) is MPL-2.0; `uplot` (charts, added 2026-11-16) is MIT |
| Rust (desktop crate graph) | 434 | 0 | `cssparser`, `cssparser-macros`, `selectors`, `dtoa-short`, `option-ext` are MPL-2.0; `r-efi` uses its reviewed MIT branch (RCLC-0001/0002) |

No dependency had to be replaced. MPL-2.0 is file-level copyleft: the files may be
used in proprietary products as long as they are not modified. Any change to an
MPL-2.0 file must be published under MPL-2.0. On Linux the desktop app links the
system WebKitGTK/GTK libraries (LGPL) dynamically, which LGPL permits.

## Chart library (UX-09, 2026-11-16)

One chart library was approved: uPlot (MIT) or Observable Plot (ISC). Both were checked
against this policy and built into a minimal line chart with the project's Vite:

| Candidate | Licence | Runtime packages pulled in | Minimal chart, minified JS (gzip) |
|---|---|---|---|
| `uplot` 1.6.32 | MIT | 1 (no dependencies) | 51.8 kB (22.6 kB) + 1.6 kB CSS |
| `@observablehq/plot` 0.6.19 | ISC | 41: all of `d3` 7 (ISC, `d3-ease` BSD-3-Clause), `interval-tree-1d` and `binary-search-bounds` (MIT), `isoformat` (ISC), `delaunator` (ISC), `robust-predicates` (Unlicense), and `d3-dsv`'s CLI dependencies `commander`, `iconv-lite`, `safer-buffer` (MIT), `rw` (BSD-3-Clause) | 275.3 kB (92.4 kB) |

Both are permitted for proprietary commercial use. **uPlot was chosen**: one MIT package
instead of 41, a quarter of the bundle, and a canvas renderer built for dense time series
(thousands of points per series redraw without DOM churn), which is what a trading terminal
draws all day. Observable Plot's strength, a grammar of SVG marks, is not needed for the
desk's line, step, bar, curve and spread charts.

Purpose: the chart layer `clients/web/src/components/ui/charts/` (`docs/product/DESIGN_TOKENS.md`).
Scope: runtime (web and desktop bundles). Network, process, data or deployment risk: none
(a pure client-side drawing library; no requests, no workers, no storage). It is recorded in
`clients/web/package-lock.json` (audited by the fail-closed npm gate) and in
`THIRD_PARTY_NOTICES.md` (`web-node`, regenerated with `scripts/release/generate_sboms.py`).

Non-code assets:

- One font is bundled: Inter (SIL OFL 1.1, Latin and Latin Extended WOFF2 subsets, from
  `@fontsource-variable/inter` 5.3.0, copied as data; the package is not a dependency). The OFL
  allows bundling in a commercial product as long as the font is not sold by itself and the
  licence travels with it: it is reproduced in `THIRD_PARTY_NOTICES.md` and emitted as
  `dist/licenses/Inter-OFL-1.1.txt`. Record: `clients/web/src/assets/fonts/fonts.json`. Chinese
  text uses the device's own CJK face.
- Map tiles default to no basemap; public OSM/CARTO tiles are marked not for
  commercial use (`clients/web/src/app/mapTileProviders.ts`).

Optional OCR for scanned contracts calls a Tesseract binary (Apache-2.0) that the customer
installs; the product neither bundles it nor any GPL tool such as Poppler.

Data-provider terms, which carry more commercial risk here than code licences, are in
[DATA_SOURCE_TERMS.md](DATA_SOURCE_TERMS.md).

This is an engineering review, not legal advice.
