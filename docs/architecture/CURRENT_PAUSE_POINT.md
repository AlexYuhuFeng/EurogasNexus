# Current Pause Point

Chinese companion: [CURRENT_PAUSE_POINT-CN.md](CURRENT_PAUSE_POINT-CN.md)

## Status

Date checked: 2026-07-22

Eurogas Nexus is a `0.5.0` preview-release worktree containing the FastAPI
backend, PostgreSQL runtime schema, Python SDK, CLI, React/Vite Web workspace,
Tauri Windows/Linux desktop clients, and role-based deployment tooling.

It is a European natural-gas market-intelligence, optimization, and
decision-support product. It is not an execution venue, order router,
nomination-submission system, settlement platform, legal-advice tool, or ETRM.

## Verified Runtime Baseline

The most recently validated local PostgreSQL test runtime has:

```text
alembic_revision: 0015_llm_monitoring_alerts
required_tables: 37
missing_tables: 0
source: runtime-postgresql
```

Repository schema head and the explicit local test migration are both
`0015_llm_monitoring_alerts`, with 37 required tables. No production database
was contacted.

Current import evidence:

```text
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
app import ok
87
```

Clients obtain runtime data through `/api` or the SDK. They do not connect to
PostgreSQL, read backend files, or call market/infrastructure providers.
Provider credentials are backend-owned and are never returned in plaintext.

## Current Product Shape

- Public API: stable unversioned `/api`.
- Operator API: `/api/internal`, protected by the backend internal token and
  principal header where implemented.
- Development API: `/api/dev`, profile-gated.
- Runtime truth: PostgreSQL with Alembic-managed schema.
- Web: shared map-first trader workspace.
- Desktop: Tauri shells for Windows x64 and Linux x64/ARM64.
- Deployment: distinct Server, Client-only, and AllInOne assets. The Windows
  AllInOne NSIS package provisions the loopback-only Docker/PostgreSQL/API
  runtime and desktop Client on a Docker-ready evaluation workstation. Server
  deployment remains private-network/VPN preview-only until production
  authentication is added.
- Preview market data: source-shaped simulated providers write to PostgreSQL
  and follow the same backend/API/client path as licensed feeds.
- Intraday decisions: normalized L1 quotes trigger backend route-adjusted
  scans; persisted opportunities are exposed through API/SDK and polled by the
  Network, Market, and Strategy workspaces every 10 seconds. Expired snapshots
  are never left actionable.
- Monitoring and DeepSeek: a PostgreSQL-backed worker normalizes opportunity,
  strategy, and source-failure alerts every 10 seconds. Stable fingerprints
  prevent repeated provider charges for an unchanged event. The top-bar Alert
  Center supports acknowledgement and explicit live DeepSeek dialogue. A real
  provider connection, three alert enrichments, and one interactive response
  were validated on 2026-07-22; automated tests remain offline.

## Active Workspaces

- Network: resource-pool map, persisted resources, route candidates, capacity
  blockers, route economics, PnL, and review warnings.
- Market: PostgreSQL-backed hub prices, tenors, spreads, ECB FX, source and
  simulation posture.
- Capacity: ENTSOG flow/capacity, TSO access, tariffs, GIE storage, and LNG.
- Contracts: EFET-style resource terms with backend persistence and JSON draft
  import.
- Scenario and Strategy: trader-reviewed calculations and shadow evaluation.
- Review: warnings, assumptions, source evidence, and report surfaces.
- Market Positioning: read-only external screen-order and indicative PnL
  observations, including `screen_order_observations`.
- Data Sources: source categories, credential maintenance, diagnostics,
  freshness, and ingestion history.
- Glossary, Runtime, Settings, and Manual: bilingual operating support.

## Optimization State

The four stable operator-input endpoints are:

```text
POST /api/optimization/route
POST /api/optimization/resource-pool
POST /api/optimization/capacity
POST /api/optimization/contracts
```

They return the standard `data/meta` envelope and require human review.

The shared-capacity network-flow module now uses a true residual network with
reverse arcs, final-flow accounting, capacity checks, and node-conservation
checks. Storage dispatch and nomination-window assessment remain validated
internal prototypes. None of these three is exposed through the stable facade,
SDK, or API until DB-backed input and lineage contracts are complete.

## Deployment And Release State

- GitHub Actions validates Python, API import, Web, desktop, deployment assets,
  and the multi-architecture API image.
- Normal CI runs optimizer tests and builds desktop packages on pull requests.
- Every `main` push runs the release workflow for Web, Windows Client-only,
  Windows AllInOne, Linux x64, Linux ARM64, the Server operator bundle, and the
  amd64/arm64 runtime image.
- Linux Tauri dependency installation uses the official HTTPS Ubuntu mirror and
  bounded retries to tolerate transient ARM runner mirror failures.
- Customer production signing certificates are not stored in this repository.

## Web Application Architecture

The React composition root is now nine lines and only creates the application
controller and shell. Stateful workflows live under `app/hooks`, derived
portfolio decision state lives under `app/model`, persistent chrome lives under
`app/shell`, and workspace selection lives under `app/workspaces`. Contract
tests enforce the small root and inspect the real module owners instead of
requiring all behavior to appear in `App.tsx`.

See [WEB_APPLICATION_ARCHITECTURE-EN.md](../clients/WEB_APPLICATION_ARCHITECTURE-EN.md).

## Remaining Release Limitations

1. Multi-user authentication/authorization and company SSO are not implemented;
   server roles are private-network/VPN preview deployments only.
2. Commercial providers remain gated by customer credentials, entitlement,
   licenses, and operator validation.
3. Public-source scheduling, retry policy, audit depth, export governance, and
   retention need further production hardening. Alerting now exists, but needs
   authenticated multi-user ownership and production delivery channels.
4. Route-level intraday opportunities now compose quotes, routes, tariffs,
   capacities, access rights, and FX from PostgreSQL. Production portfolio-wide
   optimization must still allocate resources over shared and alternate routes
   with contract-level PnL attribution.
5. Storage and nomination prototypes are not customer-facing workflows.
6. Orders and PnL are imported observations; no order entry, amendment,
   cancellation, routing, execution, or trade capture is performed.

## Next Work

Follow [NEXT_DEVELOPMENT_QUEUE.md](NEXT_DEVELOPMENT_QUEUE.md). The next selected
increment is DB-backed portfolio network optimization: compose persisted
resources, sale opportunities, TSO access, tariffs, and available capacity into
the validated shared-capacity model, then expose it through API and SDK only
after contracts and lineage are defined.
