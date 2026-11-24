# 16 Competitive and design study

On 2026-11-24 the owner asked for a comparison with the products a gas and LNG desk works
beside, buys from or competes with: market data and analytics (Kpler, Bloomberg, Platts,
Argus, ICIS, LSEG, Montel, Vortexa, Spark, Trayport), ETRM and scheduling systems, LNG
shipping tools, and Kraken. The aim is to learn, not to copy: find where those products
support a workflow, a data practice or a governance control better, and decide what that
means for Eurogas Nexus. The client and web experience got its own study.

Both studies use public sources only, cite every product claim, and mark inferences.

- [research/16A_PRODUCTS_AND_WORKFLOWS.md](research/16A_PRODUCTS_AND_WORKFLOWS.md): ten
  lessons, a gap matrix, what not to copy, 54 sources.
- [research/16B_UI_UX_AND_DESIGN_SYSTEM.md](research/16B_UI_UX_AND_DESIGN_SYSTEM.md): twelve
  recommendations ranked by user impact, today versus best practice per topic, what not to
  adopt, 53 sources.

## What we take, and where it lands

Each line is a decision; the reasoning is in the study and in [08](08_DECISION_LOG.md).

### Products, data and governance

| # | Lesson | Decision | Lands in |
| --- | --- | --- | --- |
| P1 | Price corrections are typed, dated facts readable "as known at T" | Adopt: revision history and as-of reads for prices, FX and firm marks, with change kinds correction, backfill, deletion | After the shared price resolver (P-08); migration and ADR first |
| P2 | Clients sync only what changed | Adopt: a change feed over `market_events` with entitlements, plus an SDK call | After M7 |
| P3 | Estimates say they are estimates | Adopt: ETA basis and confidence on cargo imports and the cargo plan | LNG slice after QA-L-05 |
| P4 | Each figure explains how it was made; method changes are governed | Adopt: curve derivation and excluded quotes exposed; an event when a calculation manifest changes; maker-checker (P-17) | With P-17 |
| P5 | Audit is part of the write | Adopt: governed writes (limits, hedges, approvals, users, keys) write their audit row in the same transaction and fail without it | Next governance slice, before M8 |
| P6 | Licensed data use is reported | Adopt: usage log per licensed source; export decisions applied to files | With P5 |
| P7 | Excel next to the API | Adopt the first step only: key-authenticated reads that Power Query can refresh, and a committed OpenAPI document. An add-in needs an ADR | After P2 |
| P8 | Nomination tools earn their keep explaining mismatches | Adopt read-only: "why is this out" in the gas-day checklist, matching trades and confirmations to nominations. Nothing is sent | Scheduler slice |
| P9 | Alerts are subscribed per person and escalate | Adopt: per-user subscriptions on outbox event keys, a webhook channel, escalation | M7 (in progress) |
| P10 | Kraken's engineering discipline: enforced module boundaries, compatible releases, parallel runs before a switch | Adopt: import contracts with a burn-down of known violations; one kernel each for LNG economics, P&L and freshness; retire the legacy engine by a parallel run | Ongoing; legacy engine in M7 |

### Client and web experience

All twelve recommendations are adopted. Order, by user impact and risk:

1. R5 keyboard focus that survives Windows High Contrast (a bug). **Done** (wip/ux).
2. R1 a colour-blind-safe palette option and a colour-distance test.
3. R2 direction shown by ▲/▼ and the signed change; the flash keyed to the instrument.
4. R3 one formatter per measure (proper minus sign, unit spacing) and a lint.
5. R9 one licensed icon set (Lucide, ISC) behind one `Icon` component; status by shape and colour.
6. R4 raised and overlay surfaces in dark mode; a slight brand tint.
7. R10 one source of truth for motion, radii and control heights; exit easing.
8. R11 a Comfortable/Compact density preference (row height only).
9. R8 the command palette finds hubs, contracts, cargoes and vessels.
10. R12 Settings split into Personal, Workspace, Organisation and Connection.
11. R6 desktop capabilities claimed only when their plugin ships (a correctness bug).
12. R7 the native menu matches the current workspaces, is translated, and has the standard
    shortcuts.

### What we do not take

Terminal-style function codes as the primary navigation, vendor-locked add-ins without an
ADR, per-vendor visual identity, and features whose public description is marketing only.
The full lists are in sections 3 of both studies.
