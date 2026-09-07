# Post-CR15 UI Audit

Status: **in progress; not whole-product acceptance**

Baseline: `cfbcd58`, 2026-09-07. See the [campaign plan](../engineering/UX01_EXECPLAN.md)
and [CR1-15 matrix](CR1_15_REGRESSION_MATRIX.md). Component counts are being
collected separately. No frontend refactor preceded these observations.

## Runtime truth

The repository was fetched and main was already current. Initially the API,
web server and Docker engine were stopped. The existing Docker Desktop and
web/API runtime were started for this audit; no database was created or migrated.

The existing `eurogas-nexus-db` container became healthy. Read-only
`GET /api/runtime/db` then returned connectivity OK, revision
`0024_cost_observations`, and **41 missing required tables**. `python -m alembic
heads` reports `0032_agent_capability_layer`. Database connectivity is not
application readiness. The new workflows cannot be accepted against this
outdated schema. A backed-up migration and readiness check must precede normal
workflow acceptance. No credentials or database payloads belong in this report.

## Captures reviewed

The following fresh local artifacts were saved and visually inspected using
Playwright with installed Edge, explicit 1440x900 viewport and CSS-pixel output:

| Local artifact under `output/playwright/` | Actual state | Disposition |
| --- | --- | --- |
| `ux01-network-backend-offline-1440.png` | API stopped; Network default; all data requests fail | Accepted as degraded-state evidence only |
| `ux01-network-runtime-started-1440.png` | API started without runtime DB configuration | Accepted as missing-configuration evidence only |
| `ux01-network-schema-behind-1440.png` | API connected to old schema; Network still loading | Accepted as upgrade/loading evidence only; not normal-state acceptance |

These captures do not prove normal data rendering, correct topology, 1920x1080,
native desktop, all-page coverage or accessibility compliance. Initial in-app
captures were cropped relative to the requested viewport and were rejected for
desktop acceptance. A native capture did not show the selected target and was
also rejected. The CLI's default Chrome launch failed because Chrome was not
installed; the existing Edge browser successfully produced the listed captures.

## Confirmed findings

| ID | Severity | Evidence and impact | Required correction |
| --- | --- | --- | --- |
| UX01-001 | P1 | In all three captures, the topbar overlaps the analytical surface. Primary navigation, map controls, context selectors and right-rail tabs occupy the same band. Runtime/language/appearance/account controls wrap over decision content. | Give shell/context/status stable structural rows; let content start below their measured height; verify every workspace and degraded state. |
| UX01-002 | P1 | Offline capture exposes a raw endpoint-name list across the entire top edge, colliding with alerts and navigation. Retry and error text have browser-default styling inconsistent with other controls. | Canonical bounded error surface with useful summary, structured details and retry; it must participate in layout rather than cover controls. |
| UX01-003 | P2 | Network displays "Executable spread candidates" while the UI standard prohibits execution language for decision-support results. | Reconcile EN/CN candidate language with the no-execution boundary without changing calculation semantics. |
| UX01-004 | P2 | Network repeats gas day/product context in the resource panel, uses deeply framed metric/empty-state panels, and devotes substantial rail height to repeated explanatory prose. | Apply common context/evidence and empty-state rules; preserve actionable warnings and provenance while reducing repeated presentation. |

The old schema is an environment acceptance blocker, not proof of a frontend
hydration bug. Persistent loading must be retested after migration before its
root cause is assigned. Similarly, an empty map with unavailable backend data
does not prove that the current geometry implementation is wrong.

## Workflow coverage remaining

| Workspace | Current audit coverage | Required next evidence |
| --- | --- | --- |
| Market / Network / Capacity | Network degraded and loading states only | Normal overview, curves/spreads, asset/route selection, capacity evidence and Scenario handoff |
| Portfolio | Source inventory in delegated matrix only | Resource, route, economics, exposure, optimization and Review sequence |
| Decision Center | Source inventory only | Scenario inputs, run, optimization, provenance and Review interactions |
| Strategy Lab | Source inventory only | Design, version, Backtest, Compare, Shadow and persisted history |
| System | Source inventory only | Sources, Runtime, Settings, Manual, Glossary and Access |
| Research Data | Source inventory flags thin catalog UI | Feature/target/dataset navigation and dataset detail; triage missing required interactions |
| Agent Research | Source inventory flags thin artifact UI | Governed research, findings, confirmation, Review Pack and Replay |

## Inventory and follow-through

Component, typography, spacing, controls, tables, overlays, states and layouts
must be measured in the component census and reconciled with these rendered
findings. Navigation, bilingual, keyboard/focus, menus/modals, chart readability,
overflow and long-session checks remain pending. Do not replace these open
items with source-only assertions or historical UAT numbers.

The next implementation gate is the complete runtime audit plus a reviewed
Constitution/RFC, not this partial Network assessment. The campaign remains
open with confirmed P1 layout defects.

## Runtime recovery and Portfolio follow-up

The test database was backed up and explicitly upgraded from 0024 to 0032.
The custom-format archive is 52,399,199 bytes; its table of contents was readable
(195 output lines), and `pg_restore --file=/dev/null` successfully decoded the
full archive. This is archive validation, not a completed restore drill.
Backup SHA256: `6fe7f04119b25ad8e21f629f66a4ba793ce237500b2617fc0b157e042c51c745`.
The local backup remains outside the repository; no database payload is committed.

`alembic upgrade head` completed all eight pending migrations. Read-only API
validation now reports `0032_agent_capability_layer`, zero missing required
tables, and `/api/health/ready` reports `ready` with both database and required
tables OK. This supersedes the environment blocker above, not the UI findings.

Fresh follow-up captures under `output/playwright/`:

| Artifact | Observed result |
| --- | --- |
| `ux01-network-ready-1440.png` | Despite backend readiness, Network was still loading at capture; not accepted as settled normal-state evidence. |
| `ux01-portfolio-before-1440.png` | Portfolio Overview settled and displayed the existing preview resource; full-width framed sections, browser-default action buttons, oversized section headings and inconsistent account controls are visible. |
| `ux01-portfolio-routes-before-1440.png` | Routes tab works; its comparison uses button rows and full-cell pill statuses, without consistent numeric alignment. |
| `ux01-scenario-route-before-1440.png` | Selecting the TTF-BBL-NBP route opens Scenario and visibly carries its route ID; economics and resource-pool controls render. |

All four images were visually inspected. Portfolio settling establishes that
the prior loading observation is not proof of permanently broken hydration.
Load duration and per-endpoint behavior still require measurement.

Additional triage: Portfolio Overview reports no active warnings, while Routes
labels TTF-BBL-NBP `BLOCKED` yet shows allocation and margin. Scenario carries
that route and shows allocation economics. Trace the API result, feasibility
rules, preview provenance and cross-workspace warnings before deciding whether
this is a stale snapshot, distinct calculation basis or correctness defect.
Do not silently restyle away the discrepancy or present it as a proven backend
calculation error. Scenario execution, Optimize/Review and remaining workflows
have not yet been accepted.
