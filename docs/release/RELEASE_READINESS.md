# Release Readiness

## Current Status

Status: `RELEASE CANDIDATE FOR TESTED LOCAL SCOPE`

Release marker: `RELEASE CANDIDATE`

Date checked: 2026-09-03

Eurogas Nexus passes the current local release-candidate shape for
backend/API/SDK/CLI, PostgreSQL runtime schema, Web workspace, and Tauri desktop
shell. This is **not** an official production release. The repository is not
marked as a stable/GA release until the production items below and the external
security-acceptance evidence are complete.

The remaining production work is listed below.

## Latest Local Evidence

Runtime API evidence from the operator's local API:

```text
GET /api/runtime/db
database_url_present=true
connectivity.ok=true
alembic_revision=0023_storage_nomination_masters
required_tables=45
missing_tables=0
source=runtime-postgresql
```

Source/runtime evidence from the running workspace:

```text
registered sources=24
active feeds=6
runtime records=7487+
public openapi paths=84
```

Local source validation:

```text
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
app import ok

pytest (api/contract/integration/ingestion/unit/optimization/sdk/cli/release/security/streaming)
1081 passed in the local broad suite; PostgreSQL-backed smoke tests run in CI against PostgreSQL 16

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
- Linux desktop release packaging is architecture-specific: x64 and ARM64 DEB
  packages are separate artifacts, not one ambiguous Linux package.
- SDK and CLI remain API consumers.
- Clients do not connect directly to PostgreSQL.
- Provider credentials are backend-owned: clients can submit keys to the
  backend, but plaintext keys are not returned or stored in client state.
- Release profile enforces an API token on every public request
  (Bearer / X-Eurogas-Api-Key / documented SSE query channel); credential-write
  routes additionally require an explicit operator principal.
- External LLM providers are disabled in trial/release environments; LLM
  payloads exclude contract financial fields unless explicitly opted in, and
  snapshot sources are entitlement-checked before any provider call.
- Economic decisions never mix currencies: market prices and route costs are
  converted with as-of FX observations and provenance, and mismatched
  resource/sale pairs fail closed.
- Cross-zone routes require confirmed TSO access and known capacity; unknown
  access/capacity blocks the pair (never interpreted as unrestricted).
- Gas-day boundaries follow the CAM calendar (05:00 CET/CEST, DST-aware) via
  one shared versioned implementation across backend ingestion and simulation.
- Resource-pool allocation is an exact min-cost flow; results persist input
  snapshots with `run_id`/`snapshot_id` evidence, and `RUNTIME_DECISION` mode
  consumes DB snapshots only (client-supplied prices rejected).
- Dependency versions are pinned in `requirements.lock`; CI runs an offline
  license-policy audit and a pip-audit CVE scan, and release builds install
  from the lock.
- CI runs migrations and DB-backed smoke tests against a real PostgreSQL 16
  service, plus an in-process API load smoke with latency percentiles.
- Source posture panels show runtime row counts, credential state, and
  read-side freshness (live/stale/unknown) from backend API diagnostics.
- Runtime workspace exposes a commercial release-readiness matrix for DB/schema
  status, source operations, realtime delivery mode, commercial
  credential/certification posture, no-execution guardrails, and the external
  security-acceptance gate.
- Market workspace renders a terminal-style major-hub board, regional TTF
  spreads, observed-row sparklines, ECB FX, and price-source posture without
  fabricating missing licensed prices.
- Order/PnL records are read-only imported observations exposed through
  `/api/portfolio/*`.
- No raw provider data, provider credentials, full DB URLs, `.env`, or real
  commercial strategy parameters are committed.

## Release Packaging

Every successful `Build and Release` workflow publishes the following assets:

- `release-desktop-windows-x64`: Windows Client-only NSIS installer.
- `release-all-in-one-windows`: Windows one-click AllInOne NSIS installer and checksum.
- `release-deployment`: Server and advanced deployment operator toolkits.
- `ghcr.io/alexyuhufeng/eurogasnexus-api`: multi-architecture runtime image.
- `release-desktop-linux-x64`: Linux DEB package for x64 Linux users.
- `release-desktop-linux-arm64`: Linux DEB package for ARM64 Linux users.

Server deployment defaults to private-network preview. The explicit
`EUROGAS_NEXUS_DEPLOYMENT_POSTURE=security_accepted` switch only takes effect
when `EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE` points to an existing
acceptance file. Public internet and
multi-tenant deployment remain blocked until the full user directory / role
model milestone ships (release currently enforces an API token on every
request and an operator principal for credential writes, but has no per-user
accounts).

The Linux artifacts must remain explicitly architecture-labelled so ARM Linux users do not receive the x64 DEB by mistake.

## What Runtime DB Means In The Client

`Runtime DB` means the UI is reading a backend API process that can reach the
configured PostgreSQL runtime store. It does not mean every commercial provider
has been live-called or validated.

Currently validated public/keyed source classes include local runtime evidence
for ECB, ENTSOG, GIE storage/LNG, reference network, TSO access, tariffs, and
operator-owned test portfolio/price records. Commercial feeds remain gated.

## Required Before Production Deployment

The following items are the current production gaps:

- Production scheduling/retry/monitoring for ingestion.
- Provider-specific live tests for EEX, ICE OCM, Trayport, Kpler, Platts, ICIS,
  Argus, brokers, weather, and LLM providers after credential and entitlement
  approval.
- Full multi-user account lifecycle and company SSO/OIDC remain R32A; local
  PostgreSQL identities, hashed bearer keys, role authorization, and
  commercial data scopes are delivered in R32.
- Row-level entitlement enforcement across every read route (market
  observation/quote routes filter by identity scopes; remaining read routes
  still need the same filter before production).
- Persisted EFET-style customer contract/resource workflow through backend APIs.
- Operational runbooks for backups, migrations, incident response, and release
  rollback (backup tooling and restore verification checklist are in
  `docs/operations/BACKUP_RESTORE.md`; drills require a real deployment).

## Product Boundary

Release-candidate status does not authorize:

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
