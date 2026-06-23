# R16: Release Pack and Final Validation Report

**Milestone ID:** R16 | **Status:** SUPERSEDED | **Date:** 2026-05-29

## Superseded By Holistic Runtime Test

This report is no longer the current release-readiness authority. A later
holistic runtime test found that official V1 release readiness is not yet
complete.

Use these files instead:

- `data/release_v1/holistic_real_test_report.md`
- `docs/release/V1_RELEASE_READINESS.md`
- `docs/architecture/CURRENT_PAUSE_POINT.md`

Current release status: `NOT READY FOR OFFICIAL V1 RELEASE`.

Historical content below is retained for traceability.

## V1 Release Summary

Eurogas Nexus V1 backend, API, SDK, and CLI are COMPLETE.
Web and Windows clients are PARTIAL — accepted for offline mode.

### Milestone Status

| ID | Milestone | Status |
|---|---|---|
| R1 | DB Runtime Foundation | COMPLETE |
| R2 | Runtime Store & Governance | COMPLETE |
| R3 | Reference Network | COMPLETE |
| R4 | Source Registry & Ingestion | COMPLETE |
| R5 | Context Observations | COMPLETE |
| R6 | Research Workflow Models | COMPLETE |
| R7 | Route Cost & Netback | COMPLETE |
| R8 | Feasibility & Allocation | COMPLETE |
| R9 | Monitoring & Nowcast | COMPLETE |
| R10 | Backtest & Shadow Run | COMPLETE |
| R11 | Research Brief & Reporting | COMPLETE |
| R12 | SDK Release Surface | COMPLETE |
| R13 | CLI Release Surface | COMPLETE |
| R14 | Web Research Workspace | PARTIAL |
| R15 | Windows Client Shell | PARTIAL |
| R16 | Release Pack & Validation | COMPLETE |

### Stop Condition

- **13 release milestones COMPLETE** (backend/API/SDK/CLI)
- **2 client milestones PARTIAL** — accepted for offline mode
- **1 release pack COMPLETE**
- Backend/API/SDK/CLI ready for operator use
- Web/Windows require later online/toolchain milestone

### Final Validation

```
ruff check .        → All checks passed!
pytest (full suite) → 293 passed
app import          → import ok, 52 routes
```

### API Surface (52 routes)

health (2), reference network (7), sources (3), market (3), physical (3),
LNG (2), storage (2), weather (3), contracts (2), workflows GET (10),
glossary (2), research POST (8), compat (5)

### What Is PARTIAL

- **R14 Web**: Source files complete at `clients/web/`. Needs `npm install`
  (internet required) for React, Vite, MapLibre GL, deck.gl, Zustand, i18next.
- **R15 Windows**: Documented at `clients/desktop/README.md`. Needs Rust/Tauri
  toolchain and web workspace build before packaging.

### Gap Report (Accepted Limitations)

- Live connector execution: mocked; needs credentials, entitlement review, internet
- LLM provider: models exist; needs API keys, internet
- Live PostgreSQL: script exists; needs operator-configured DB URL
- npm/Tauri toolchains: needed for web build and Windows packaging

### Exclusions Verified

- No secrets, credentials, .env files, or real vendor data committed
- No order entry, order routing, trade capture, nomination submission
- No trade execution, official approval, legal advice, trading recommendations
- No auto-trading, ETRM replacement, company SSO/OIDC
- No Electron, Next.js, Tailwind, Material UI, Ant Design, Bootstrap, Redux, SQLite, GPL
- No client connects to PostgreSQL directly

### Exact Next Prompt for R14/R15 Toolchain Completion

```text
docs/architecture/CURRENT_PAUSE_POINT.md.

Internet is now available. Run:
  cd clients/web && npm install && npm run build

Then implement the MapLibre GL + deck.gl map component and complete the
remaining workspace pages (Network, Market, Scenario, Strategy, Review,
Sources, Glossary, Runtime, Settings) with English/Mandarin i18n and
light/dark/system theme support.

After web build passes, install the Tauri toolchain:
  cargo install tauri-cli
  cd clients/desktop && tauri init

Configure backend base URL, build the Windows installer, and update
R14 and R15 reports to COMPLETE.
```
