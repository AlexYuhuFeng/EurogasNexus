# Current Pause Point

## Status

Date checked: 2026-06-30

Eurogas Nexus is a V1 release-candidate worktree for the tested local scope:
backend/API/SDK/CLI, PostgreSQL runtime schema, React/Vite Web workspace, and
Tauri desktop shell.

This is a gas trader intelligence and decision-support product. It is not an
execution, order-entry, order-routing, nomination, settlement, legal-advice, or
ETRM product.

## Current Runtime Evidence

Observed against the operator's running local API on `127.0.0.1:8000`:

```text
GET /api/runtime/db
database_url_present: true
connectivity.ok: true
alembic_revision: 0013_gie_lng_dtmi_energy
required_tables: 33
missing_tables: 0
source: runtime-postgresql
```

Observed from local import/build checks:

```text
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
app import ok
76

npm --prefix clients/web run build
passed
```

The Vite Web workspace currently proxies `/api` to the running backend and can
render PostgreSQL-backed runtime data.

## Current Product Shape

- PostgreSQL is the runtime source of truth.
- FastAPI exposes stable public `/api` routes, profile-gated internal routes,
  and development-only routes.
- SDK and CLI are API consumers.
- Web is the primary trader workspace.
- Windows/Tauri wraps the Web workspace.
- Clients do not read PostgreSQL, raw vendor files, `.env`, or backend local
  runtime files.
- Provider credentials are backend-owned and never returned in plaintext.

## Current Web/Windows Workspace

The active shared workspace includes:

- Network: map-first resource-pool cockpit with active resource-path overlay,
  route options, blockers, topology state, PnL summary, and strategy/warning
  signal.
- Capacity: ENTSOG flows/capacity, TSO access, tariffs, storage, and LNG.
- Market: gas-market terminal for major European hubs, regional TTF spreads,
  ECB FX references, and exchange/broker price-source posture. Missing licensed
  prices remain unavailable rather than fabricated.
- Scenario: route-cost/resource-pool controls and result review.
- Contracts: EFET-style term capture, JSON draft import, persisted-contract
  list/edit, and an API-backed save path into `upstream_resource_contracts` for
  decision-support resource-pool inputs.
- Strategy: paper strategy evaluation.
- Review: warning stack and LLM/report review surface.
- Order Records: read-only external screen-order observations and indicative
  PnL snapshots.
- Data Sources: provider categories, credentials, diagnostics, freshness, and
  runtime row counts.
- Glossary: bilingual terms and DB-derived operational context.
- Runtime: database/API readiness and governance metadata.
- Settings: display unit/currency/session preferences, service-access posture,
  and backend-boundary guardrails. Manual: workspace map and operating
  boundary.

## Current API Surface

Representative active public routes:

- `/api/health`
- `/api/runtime/db`
- `/api/reference-network/*`
- `/api/sources`
- `/api/ingestion-runs`
- `/api/market/*`
- `/api/physical/*`
- `/api/storage/*`
- `/api/lng/*`
- `/api/contracts/*`
- `/api/credentials/*`
- `/api/route-cost/*`
- `/api/strategy-lab/evaluate`
- `/api/glossary/*`
- `/api/analysis/query`
- `/api/reports/portfolio`
- `/api/portfolio/*`

Portfolio observation tables currently include `screen_order_observations` and
`portfolio_pnl_snapshots`. They are read-only external observations, not trade
capture records.

Internal/operator-only:

- `/api/internal/portfolio/import-observations`

The internal import route requires the backend internal token and explicit
principal header, and remains unavailable to release clients.

## Current Documentation Work

The repository previously contained stale docs that described Web/Windows as
not-yet-active client work and pointed agents back to backend Milestone 2.
Those docs are being aligned under V1 R22 to match the active product.

Mandarin docs must be kept as real UTF-8 Chinese. Mojibake or private-use
replacement characters are treated as documentation defects.

## Remaining Release Limitations

1. Production scheduling, retry, monitoring, and alerting for live ingestion
   are not yet productionized.
2. Commercial providers such as EEX, ICE OCM, Trayport, Kpler, Platts, ICIS,
   Argus, brokers, weather, and LLM providers remain gated by credentials,
   entitlement, and operator validation.
3. Order/PnL records are imported read-only observations. V1 does not perform
   order entry, amendment, routing, cancellation, trade capture, or auto-trading.
4. Auth, audit depth, entitlement, and export-governance enforcement need
   hardening before multi-user production use.
5. EFET-style upstream resource contracts now support API save, list/edit, and
   JSON draft import, but customer contract lifecycle validation, versioning,
   approval, and export controls still need production hardening.
6. Route-cost and resource-pool recommendations remain decision support and
   human-review required.
7. The Market terminal currently depends on loaded runtime price observations;
   commercial exchange/broker connectors still require credentials,
   entitlement, and operator validation before live prices appear. For
   development and operator rehearsal, `EEX_Sim`, `ICE_OCM_Sim`, and `ICIS_Sim`
   can run as a continuous source-shaped PostgreSQL worker through
   `scripts/ops/ingest_simulated_market_prices.py --loop`.

## Next Work

Use `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`. The current priority is
V1 R22: documentation and client cockpit alignment. Then proceed to
source-health scheduling, entitlement/audit/export hardening, persisted
contract workflows, and cockpit review/evidence UX.
