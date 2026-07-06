# V1 Release Readiness

## Current Status

Status: `RELEASE CANDIDATE FOR TESTED LOCAL SCOPE`

Release marker: `RELEASE CANDIDATE`

Date checked: 2026-06-30

Eurogas Nexus passes the current local release-candidate shape for
backend/API/SDK/CLI, PostgreSQL runtime schema, Web workspace, and Tauri
desktop shell. This status does not mean production multi-user deployment is
complete.

Actionable production work is tracked in
`docs/release/PRODUCTION_READINESS_BACKLOG.md`.

## Latest Local Evidence

Runtime API evidence from the operator's local API:

```text
GET /api/runtime/db
database_url_present=true
connectivity.ok=true
alembic_revision=0012_entsog_capacity
required_tables=33
missing_tables=0
source=runtime-postgresql
```

Source/runtime evidence from the running workspace:

```text
reference nodes=788
registered sources=20
active feeds=6
runtime records=7487
resource-pool resources=1
sale options=2
```

Local source validation:

```text
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
app import ok
76

npm --prefix clients/web run build
passed
```

## Validated Gates

- App import remains DB-free and network-free.
- Release API profile disables docs/openapi endpoints.
- No development-only routes enabled in release profile.
- No silent local file fallback in trial or release mode.
- Stable client prefix is `/api`.
- PostgreSQL runtime validation can report connected, missing-table, and
  unavailable states without printing secrets.
- Web client builds and uses `/api` through the backend boundary.
- Windows desktop packages the same Web workspace through Tauri.
- SDK and CLI remain API consumers.
- Clients do not connect directly to PostgreSQL.
- Provider credentials are backend-owned: clients can submit keys to the
  backend, but plaintext keys are not returned or stored in client state.
- Source posture panels show runtime row counts and credential/freshness state
  from backend API diagnostics.
- Market workspace renders a terminal-style major-hub board, regional TTF
  spreads, observed-row sparklines, ECB FX, and price-source posture without
  fabricating missing licensed prices.
- Order/PnL records are read-only imported observations exposed through
  `/api/portfolio/*`.
- No raw provider data, provider credentials, full DB URLs, `.env`, or real
  commercial strategy parameters are committed.

## What Runtime DB Means In The Client

`Runtime DB` means the UI is reading a backend API process that can reach the
configured PostgreSQL runtime store. It does not mean every commercial provider
has been live-called or validated.

Currently validated public/keyed source classes include local runtime evidence
for ECB, ENTSOG, GIE storage/LNG, reference network, TSO access, tariffs, and
operator-owned test portfolio/price records. Commercial feeds remain gated.

## Required Before Production Deployment

The following items are summarized here and expanded in
`docs/release/PRODUCTION_READINESS_BACKLOG.md`:

- Production scheduling/retry/monitoring for ingestion.
- Provider-specific live tests for EEX, ICE OCM, Trayport, Kpler, Platts,
  ICIS, Argus, brokers, weather, and LLM providers after credential and
  entitlement approval.
- Stronger auth, audit, entitlement, and export-governance enforcement.
- Multi-user role model and secret-manager integration.
- Persisted EFET-style customer contract/resource workflow through backend
  APIs.
- Operational runbooks for backups, migrations, incident response, and release
  rollback.

## Product Boundary

V1 release-candidate status does not authorize:

- order entry;
- order routing;
- order amendment or cancellation;
- trade capture;
- nomination submission;
- official approvals;
- settlement/accounting;
- legal advice;
- official trading recommendations;
- auto-trading;
- ETRM replacement behavior.

All route, strategy, resource-pool, analysis, order/PnL, and report outputs are
decision support and require human review.
