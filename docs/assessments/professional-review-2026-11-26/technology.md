# Eurogas Nexus: technology review (trading-systems dev, SRE, data engineer, infosec, enterprise architect)

Reviewed 2026-11-26. Code: `/home/user/EurogasNexus-merge`. It moved from `3a1f81a` to `870da77` during the review, and migrations 0092/0093 (TimescaleDB) arrived mid-read. Demo: probed read-only as `test_ops` and `test_admin` (screenshots in `scratchpad/review/test_admin`). Size: about 250k lines of Python backend, 100k of TypeScript client, 187k of tests, 384 route handlers, 93 Alembic revisions, about 165 tables and 39 ADRs.

## 1. Verdict

1. The engineering is unusually disciplined for a product of this age. It has one PostgreSQL source of truth, a transactional outbox, provenance on every row, entitlement checks on every read and stream, licensed-use metering, OIDC with PKCE, SBOMs, digest-pinned images and a CI that runs on PostgreSQL. A technology committee would not reject it on design hygiene.
2. They would adopt it as an internal decision-support and fundamentals application, beside the ETRM and Trayport and not integrated into the trade path. Its feeds would be public fundamentals, EOD settlements and ETRM extracts loaded as files.
3. Three things block production adoption:
   - The runtime topology is one uvicorn worker on one Compose host, with no tested multi-instance mode.
   - Recovery is a daily `pg_dump`: RPO 24 h, no PITR and no standby.
   - Every licensed real-time connector (Trayport, ICE, EEX, Platts, Kpler) is a 20-line manifest with `implemented=False`, so "live by default" does not reach the prices a desk trades.
4. The demo is the evidence. With a handful of concurrent reviewers, mean API latency was 4 to 6 s per route group, `/api/health` averaged 1.5 s, four reads returned 502 after 20 s, and 11 of 12 pool connections were checked out.
5. All of this is fixable without a rewrite. A few ADRs are justified now: standby with PITR, object storage, a shared cache when there is more than one API process, and a feed-handler process once a feed is licensed. Kafka, Kubernetes and microservices are not.

## 2. Per persona

### 2.1 Trading-systems / quant developer

**The job in a day:**
- Keep ETRM-to-analytics trade and position feeds reconciled.
- Wire Trayport and exchange data into curves.
- Give analysts Python access.
- Field "why is this number different from Endur".

**What works:**
- Idempotent ETRM CSV import keyed on (system, trade id), with cancellations removing trades (`ingestion/etrm_trades.py`).
- Versioned import contracts with row-level reasons and a `validate` endpoint (`docs/integration/ETRM_ERP_IMPORT_CONTRACTS.md`).
- A cursor-based change feed (`GET /api/market/changes`, SDK `sync_market_changes`).
- `as_of` reads.
- One units, currency and gas-day foundation (ADR 27).
- A signed, idempotent decision hand-off for middleware, which never books.
- Typed Pydantic SDK models carrying lineage `meta`.

**Gaps:**
- **Must-have:**
  - Real connectors for Trayport (Joule / Trading Gateway API), ICE and EEX (or the firm's market-data platform: LSEG RTDS or TREP, Bloomberg B-PIPE), Platts and Kpler. Today `domain/connectors/builtin/trayport.py` declares `AccessMode.SOCKET_FEED` but `implemented=False`, and the Admin page still offers "Connect".
  - A richer trade model. The ETRM row is flat (one quantity per day and a fixed price). It has no index or formula pricing (TTF-linked or oil-indexed), no hourly shape, no swing or option volume, no strike, no counterparty or legal-entity master and no pricing fixings, so positions for a real portfolio will not reconcile with Endur or Allegro.
  - A downloadable OpenAPI spec in the release profile. `/openapi.json` returns 404 and the spec is non-release only.
- **Should-have:**
  - A version policy. The URL has no version (`docs/api/API_PATH_POLICY.md`), while `ERP_ETRM_INTEGRATION.md` calls the API "versioned". Choose one approach (a header or `/api/v1` with deprecation windows).
  - One pagination style. There are four today (audit A5).
  - A client/server version handshake. The newer client polled `/api/stream/live` and `/api/me/alert-state` against an older server and got 404s on every page (`review/test_trader/report.json`).
  - An SDK client object with session auth, retry and DataFrame or Arrow returns (it is module functions taking `base_url`), published to an internal package index.
- **Nice-to-have:** push of decided cases to a message queue the firm already runs (IBM MQ or Solace) instead of pull only.

**Redundant:**
- `streaming/contracts.py:StreamingEnvelope`, described in its own docstring as the "Milestone 12 shell", is unused.
- Inline strategy evaluation inside tick ingestion (`market_ticks.ingest_ticks` → `notify_inputs_changed`) couples a research feature to the hot write path.

**How to organise it for this persona:** an "Integration" admin area holding API keys and service identities, import contracts with a validate-and-upload history, change-feed consumers and their lag, OpenAPI and SDK downloads, and a reconciliation report (ETRM trade count and volume by book against what is stored).

### 2.2 Platform / SRE

**The job in a day:**
- Keep it up during trading hours.
- Patch it.
- Know before the desk does that a source is stale.
- Restore it after a failure.
- Pass change-advisory-board (CAB) review.

**What works:**
- A config-check container that refuses a misconfigured stack.
- Migration and seed one-shot jobs.
- A health/ready split.
- Release signing and SBOM jobs (`.github/workflows/release.yml`).
- A rollback runbook.
- Stale-job recovery.
- Outbox processing with `FOR UPDATE SKIP LOCKED` and dead letters.
- Readiness gates visible in Admin → Runtime.

**Gaps:**
- **Must-have:**
  - A supported HA topology. `deploy/runtime/compose.yaml` runs one `api` container whose CMD is a single uvicorn process (`deploy/runtime/Dockerfile.api`); the demo pins `--workers 1` (`scripts/demo/start_public_demo.py:637`). `infra/systemd`, `infra/nginx` and `infra/deployment` hold READMEs only.
  - PITR and a standby. `DISASTER_RECOVERY.md` gives RPO ≤ 24 h with a logical dump, and `BACKUP_RESTORE.md` says WAL/PITR is "out of scope until a production deployment is authorized".
  - A leader lock for the scheduler. `run_dataops_scheduler.py` has no advisory lock, so two replicas would double-ingest.
  - Scrapeable metrics:
    - `/api/runtime/metrics` returns Prometheus text wrapped inside a JSON envelope (`{"data":"# HELP …"}`) behind session auth, so Prometheus cannot scrape it.
    - It emits sums with no histogram buckets, although `_LATENCY_BUCKETS` is defined.
    - Labels are coarse: on the demo, `/api/other` held 3,034 of about 4,700 requests.
- **Should-have:**
  - OpenTelemetry traces. None exist; `request_id` exists but there is no trace propagation.
  - JSON structured logs with a log-rotation policy (audit L5).
  - Outbox lag and source freshness as metrics. The gauges are declared but were empty on the demo.
  - A documented capacity model.
- **Nice-to-have:** a Helm chart or Ansible role in the firm's style.

**Redundant or confusing:**
- Admin → Data Sources shows ECB as "Live" while the same panel says freshness "Unknown" and "Next run: Scheduler disabled", and Release checks show "Data operations scheduler: Blocked, 0/42".
- The Infrastructure tab is one page about 31,000 px tall.

**How to organise it for this persona:** one operations console with service health per process (API, scheduler, outbox, monitoring), DB pool and replication lag, source freshness against SLA, dead letters, and job history. Release checks belong to the deployment pipeline, not a page.

### 2.3 Data engineer

**The job in a day:**
- Ingest, backfill and certify sources.
- Answer "where did this number come from".
- Manage history depth and entitlements.

**What works:**
- Provenance columns on every observation, plus a raw-payload archive.
- Revisions with `as_of`.
- Per-source retry and circuit policy with failure classification (audit L2).
- Source approval and certification.
- A per-request licensed-use counter (ADR 31), which matters when Trayport or ICE audit display versus non-display use.
- Bounded reads that fail loudly (audit A4).
- An honest capacity study (`docs/engineering/Commercial-Intelligence-V3/19_DATA_CAPACITY_AND_INFRASTRUCTURE.md`).

**Gaps:**
- **Must-have:**
  - Configurable retention. `application/retention.py` hard-codes 30 days for quotes and 90 days for **market observations**, so running the prune deletes settlement and curve history, which contradicts the 5-year backfill plan.
  - Deduplication and offload of the raw archive. Every hourly ENTSOG page is re-archived about 168 times, roughly 107 MB a day today and about 3.2 GB a day with hourly flows (doc 19 §1.4).
  - A latest-value table per instrument. "Current price" reads are `ORDER BY observed_at DESC` on append-only tables.
- **Should-have:**
  - NUMERIC (or scaled integer) prices instead of `Float` in `market_quotes`, needed for reconciliation to ETRM marks.
  - The missing indexes from audit P4.
  - Monthly partitioning of observations before backfill (ADR 24 trigger).
  - A data catalogue export (OpenLineage or similar) for the firm's governance tool.
- **Nice-to-have:** Parquet history on object storage, read with DuckDB for research and backtests (doc 19 already recommends this).

**Redundant:** TimescaleDB (ADR 39) converts only `market_quotes`, `market_trades` and the raw archive. The observation tables, where the history actually lives, cannot be converted because of their upsert keys. Fixing archive deduplication and retention gives most of the benefit without a licence-scoped extension.

### 2.4 Information-security architect / IT risk

**What works:**
- OIDC authorisation code with PKCE for web and desktop, with group-to-role and group-to-scope maps and pre-provisioned mode.
- Hashed session tokens.
- A central route-permission registry that returns 500 on an undeclared route.
- Persona never grants authority (rule 7).
- Origin/CSRF guard.
- Full security headers on the demo (HSTS, CSP, XFO DENY, COOP).
- Provider keys Fernet-encrypted at rest.
- Secrets kept out of `docker inspect`.
- SBOM, provenance attestations, collected licence texts and a dependency audit in CI.
- A no-execution boundary.

**Gaps:**
- **Must-have:**
  - Separate database roles. `migrate` and `api` share one `RUNTIME_STORE_DATABASE_URL` (`deploy/runtime/compose.yaml`), so the application can run DDL and delete audit rows.
  - A tamper-evident audit trail. Audit is an ordinary table with no hash chain or WORM export, and `audit_retention.py`'s docstring says 365 days while the code default is 1,827.
  - An independent penetration test. Admin → Runtime itself shows "Security acceptance: Blocked".
  - LLM egress controls. The default endpoint is `https://api.deepseek.com` (`llm/provider.py`), and the demo enables it. For an EU trading house this must be off, or pointed at an approved EU or on-prem endpoint, with a documented data-flow review.
- **Should-have:**
  - KMS, Vault or HSM integration for `EUROGAS_NEXUS_SECRET_KEY` and key rotation.
  - SCIM or scheduled directory reconciliation for leavers.
  - Keyed API-key hashing (pending per `ENTERPRISE_IDENTITY_AUTHORIZATION_SPEC.md`).
  - A shared rate limiter (the current one is process-local).
  - A narrower desktop CSP: `connect-src https:` allows any host.
- **Nice-to-have:** a DORA ICT third-party register pack and a NIS2 supply-chain questionnaire answer set.

**Vendor assessment flags:**
- One named copyright holder (`tauri.conf.json`), so there is a single-person bus factor.
- Development by autonomous agents that send repository content to a third-party model API (`AGENTS.md` rule 3). Infosec will ask about source-code exposure and the secure development lifecycle.
- A planned China installation with one-way exports (ADR 22). This needs a data-flow and export-control review before an EU firm signs.
- Windows signing records `unsigned_pending_external` unless the customer supplies a certificate.

### 2.5 Enterprise architect (build, buy or fit)

The product fits as a fundamentals and decision-support layer. It replaces in-house Python and Excel notebooks for:
- ENTSOG, GIE, REMIT and ENTSO-E ingestion;
- route and tariff costing;
- LNG netbacks;
- the NWE balance.

It complements Montel, ICIS or Kpler, which remain the content source, and the ETRM, which remains the book of record. It should not duplicate:
- **Risk and positions:** position ladders and limits shadow Endur and Allegro and will disagree with them until the trade model is enriched (§2.1).
- **Strategy lab, shadow runtime, research agents and MCP:** IT will question their maintenance cost.

Codebase breadth, about 540k lines for one owner plus agents with a tree that changed while I reviewed it, is the main total-cost-of-ownership risk. The firm would want source escrow, a release cadence that matches its CAB (for example monthly, with an LTS line) and a support SLA.

## 3. Cross-cutting gaps

| # | Gap | Why a firm needs it | Evidence | Severity | Fix size |
|---|---|---|---|---|---|
| 1 | Blocking concurrency model | ~50 users with several tabs each need sub-second screens | 356 of 361 route handlers are sync and share the default threadpool. The SSE loops in `api/routes/public/streaming.py` (lines ~118–125 and 795–822) run synchronous DB queries inside `async` generators every 1.5 s **per connection**, which blocks the event loop. Single worker. Demo `/api/runtime/metrics`: mean ms per request of 4,467 (`/api/market`), 4,407 (`/api/other`), 6,361 (`/api/sources`), 1,514 (`/api/health`); pool 11 of 8+4 checked out; 502 after 20 s on `/api/runtime/source-operations`, `/api/market/quotes`, `/api/research/spreads/board`, `/api/runtime/db` | Blocker | Feature: one shared poller per process with in-memory fan-out, DB work in threads, N workers, an async or faster driver (asyncpg or psycopg 3 instead of pure-Python pg8000) |
| 2 | No HA, no PITR | Gas-day deadlines; auditors expect tested RPO/RTO | `DISASTER_RECOVERY.md` (RPO 24 h); one `api` service; no scheduler lock | Blocker | Config plus feature: Patroni or a managed primary/standby, pgBackRest WAL to object storage, advisory-lock leader for the scheduler |
| 3 | Licensed real-time connectors absent | Desks price off Trayport and ICE, not public data | `domain/connectors/builtin/{trayport,ice_ocm,eex,platts,kpler}.py` are manifests with `implemented=False`; data arrives only via `POST /api/market/ticks` or CSV | Blocker for live pricing | Architectural: a feed-handler process |
| 4 | Tick path will not scale | A real Trayport/ICE feed runs thousands of L1 updates a second across hundreds of instruments | `ingest_ticks` runs a dedup `IN` query, then one "previous mid" query per instrument (no index on `instrument_id, delivery_start`), then strategy evaluation **in the same transaction**. One implausible jump raises `FeedError` and refuses the whole batch (≤5,000). Rows are 888 B with JSON metadata and a 128-char string PK. Doc 19 sizes scenario C at 3–5k rows/s in bursts and about 3 TB/yr. The demo's ~22 quotes/s is two orders of magnitude lower | Major | Architectural: conflate at the edge (see §4) |
| 5 | Unscrapeable, process-local metrics; no tracing | SRE needs alerts on lag, freshness and p99 | `api/middleware/observability.py`; JSON-wrapped output | Major | Feature: `/metrics` in plain text for a scrape identity, histograms, OpenTelemetry SDK |
| 6 | Hard-coded retention | History is the asset | `retention.py`: observations 90 days | Major | Config |
| 7 | Raw archive growth | Storage cost and backup time | doc 19 §1.4 | Major | Feature: digest deduplication plus offload |
| 8 | Shared DB role, mutable audit | SoD, SOX-style ITGC, REMIT record keeping | compose file; `governance/audit.py` | Major | Config plus feature: roles, append-only grants, hash chain, SIEM export |
| 9 | API contract governance | Integrations outlive releases | No version, OpenAPI hidden in release, 4 pagination styles, 404 version skew | Major | Feature |
| 10 | Thin ETRM trade model | Reconciliation with Endur/Allegro | `etrm_trades.py` columns | Major | Architectural (data model) |
| 11 | Desktop distribution | Desktop teams deploy via Intune or SCCM | NSIS only, no MSI, no updater, WebView2 bootstrapper needs internet (an offline conf exists), CSP `connect-src https:` | Minor | Config |
| 12 | Process-local state | Blocks horizontal scale | Warm views (`application/warm_views.py`), rate limit and metrics are all per process; warm views are keyed per principal, so N workers recompute N times | Major once >1 process | Feature or ADR (shared cache) |
| 13 | Default LLM endpoint offshore | Data residency, GDPR, MNPI leakage | `llm/provider.py` `DEFAULT_BASE_URL` | Major (policy) | Config: default off, allow-list |

## 4. Structural limits, and the infrastructure a real deployment needs

**What limits the product:**
- **One process holds the hot state.** Warm views, rate limit, metrics and each SSE poller live in process memory, so scaling out means rewriting those four pieces, not adding replicas.
- **PostgreSQL is both the event log and the tick store.** That suits slow data: about 5 rows/s average and about 1k/s peaks (doc 19), against about 14k rows/s measured raw insert. It does not suit storing every L1 update with per-row JSON provenance and per-batch evaluation.
- **Integration is file-and-pull.** There are no vendor adapters, and the trade model is flat.
- **Licensing:** Trayport and ICE charge for non-display use and redistribution. Storing and recomputing on their ticks needs the customer's non-display licence; the metering exists, but the contract does not.

**Recommended topology.** The owner can provide hardware. Sizes are estimates.

| Stage | Component | Spec | Product change needed |
|---|---|---|---|
| Pilot (≤30 users, public + EOD + ETRM files) | 2 app VMs behind the firm's load balancer | 8 vCPU / 32 GB each, running the API with 4–8 workers and the workers on one node | Fix gap 1; scheduler advisory lock; sticky sessions or a shared cache for warm views |
| | PostgreSQL 16 primary + streaming standby | 16 vCPU / 128 GB / 2×2 TB NVMe each (the AX102 class from doc 19) | Separate migration and runtime roles; configurable retention; Patroni or managed HA |
| | Object storage (S3-compatible: the firm's Ceph/NetApp/Azure Blob; avoid AGPL MinIO if redistributed) | 5–10 TB | pgBackRest WAL archive (PITR, RPO ≤ 5 min); raw-archive offload; later Parquet history |
| | Observability: the firm's Prometheus/Grafana and Splunk or ELK | none (reuse) | Plain-text `/metrics`, JSON logs, OpenTelemetry |
| Analysts load | +1 read replica | as the primary | A read-only session factory for reports, research and backtests |
| Live Trayport/ICE | Feed-handler process in the market-data zone | 8 vCPU / 32 GB | **New service (ADR).** It subscribes via the vendor API or the firm's market-data platform, keeps an in-memory last-value cache, conflates to 1-second snapshots and 1-minute bars for Postgres, upserts a `latest_quotes` table, sends `NOTIFY`, and runs jump checks per tick (dropping the tick, not the batch). Strategy evaluation moves to an async consumer |
| | Shared cache (Valkey, BSD; not Redis ≥7.4, whose licence conflicts with rule 18) | 2 × 2 vCPU / 8 GB | **ADR.** Warm views, rate limit and SSE fan-out across API processes |
| Only if tick history is licensed and kept | ClickHouse (Apache-2.0) | 16 vCPU / 64 GB / 4 TB NVMe | **ADR.** Ticks and bars; Postgres keeps everything else |

**Network zones (on-prem):**
- **DMZ or user zone:** the load balancer, with OIDC to the firm's IdP.
- **Application zone:** API and workers.
- **Data zone:** PostgreSQL and object storage.
- **Market-data zone:** the feed handler.
- **Egress:** a proxy allow-listed to ENTSOG, GIE, ENTSO-E, ECB and the other public sources; the LLM is off or on-prem.

**Cloud:** managed PostgreSQL works, but most managed services ship TimescaleDB without compression (TIMESCALEDB.md), so stay on plain partitioning.

**Not worth adding:**
- Kafka (the outbox suffices until cross-system fan-out exists; ADR 28 triggers).
- Kubernetes or a service mesh for a 3–6 node estate.
- Microservices splitting the domain.
- pgvector, Temporal or Iceberg.
- TimescaleDB for the observation tables (incompatible keys).
- A separate time-series database before partitioning and archive fixes are measured.

**AGENTS.md rules 4–6.** I agree with them as a default. I would argue a reviewed ADR is justified **now** for three items:
- (a) Standby with WAL archiving to object storage. This is a control requirement, not a performance optimisation, so no "measured need" should be demanded.
- (b) Multi-process API with a shared cache. The demo measurement above is the measured need.
- (c) Object storage for backups and the raw archive. The 107 MB/day growth is measured.

I would also prepare (d), the feed-handler process, as an ADR to accept on the day a licensed feed is contracted. ClickHouse and Kafka should stay behind their measured triggers.

## 4a. Stack choices versus the industry

What I name below as industry practice is what I would expect from experience at European utility trading arms, oil majors' trading houses, commodity merchants and banks' commodity desks. It is general practice, not a disclosure by any one firm.

The governing fact: this workstation's latency budget is human (about 1 s to show a change), and the measured slowness is query shape, a blocked event loop and a pure-Python DB driver. It is not language speed. Jane Street uses OCaml because a proprietary market maker needs type-level correctness and predictable latency in code that sends orders at microsecond scale. Neither condition applies to a no-execution decision-support tool, and OCaml would cut the hiring pool to near zero.

| Layer | Today | What the industry runs, and why | Verdict and trigger |
|---|---|---|---|
| Backend language | Python 3.13, FastAPI, sync SQLAlchemy, pure-Python `pg8000` | **Python** dominates analytics, fundamentals and quant teams at energy houses (one language from notebook to service, and the largest hiring pool). **Java/Kotlin and C#/.NET** run the transactional systems: Endur is C++ with Java and .NET extension APIs, Allegro is .NET, Trayport Joule is a .NET desktop, and banks' risk platforms are Java/C#. **C++/Rust** appear in exchange-facing gateways. **OCaml** is Jane Street and a few prop shops. **kdb+/q** is used for tick history at banks and some large merchants (fast, but a costly licence and scarce skills). **Go** appears in infrastructure tooling | **Keep Python.** Rewriting about 250k lines in OCaml, Rust, Java or C# is 2–4 person-years and gains nothing at the real bottleneck. **Change now:** the driver to asyncpg (Apache-2.0) or psycopg 3 (LGPL, fine when linked unmodified); I estimate 2–5× on large row reads. **Compiled code only at named hot paths:** (1) tick conflation and validation in the feed handler, as a Rust (PyO3) extension or a small Rust/Go/Java service, when sustained updates exceed about 2,000/s or Python p99 handling exceeds 50 ms; (2) storage and swing valuation by Monte Carlo (LSMC) or a large dynamic-programming grid, using NumPy/Numba first and Rust only if still too slow (for example a full-book revaluation over 60 s); (3) network LP/MIP through a compiled solver, not hand-written code |
| Numerical core | No NumPy or SciPy at runtime (`requirements.lock`). Hand-written successive-shortest-path min-cost flow (`optimization/network_flow.py`) and a pure-Python dynamic-programming storage solver (`optimization/storage.py`). `pyarrow` only in the research extra | Desks use **NumPy, SciPy and pandas**, increasingly **Polars and Arrow**, and solvers such as **HiGHS** (MIT), OR-Tools (Apache), Gurobi or CPLEX (commercial) via Pyomo, PuLP or cvxpy. Storage desks use LSMC or rolling-intrinsic models in NumPy/Numba or C++ libraries | **Change now (small):** add NumPy, SciPy and HiGHS (`highspy`). Pure-Python solvers are slower by one to two orders of magnitude, carry more correctness risk, and a quant reviewer cannot validate them against a standard solver. Keep the hand-written ones as tests or oracles. Add Polars or DuckDB for research reads over Arrow |
| Database and time series | PostgreSQL 16 (+ optional TimescaleDB on three tables) | **PostgreSQL, Oracle or SQL Server** for transactional and reference data everywhere. At majors, **Databricks or Snowflake** lakes on Azure or AWS hold history. **kdb+** at banks for ticks; **ClickHouse** is growing; **QuestDB** is rare in this sector. **Parquet/DuckDB** for research | **Keep PostgreSQL.** Add a Parquet history on object storage when observation history passes about 50M rows per table (ADR 24). Add **ClickHouse** (Apache-2.0) only if tick history is licensed and kept beyond about 1bn rows or 3 months. Not kdb+: the licence and skills cost is unjustified without bank-scale ticks. Not QuestDB: small ecosystem in the sector. Integrate with the firm's lake by **exporting Parquet**, not by replacing the store |
| Messaging | None. Postgres outbox, LISTEN/NOTIFY, SSE polling | Banks run **Solace or AMPS** for real-time state and market data; majors' data platforms run **Kafka** (Confluent, Event Hubs, MSK); **NATS and Redpanda** are niche. Market data usually arrives through **LSEG RTDS/TREP or B-PIPE** | **Keep the outbox.** Add **Kafka** (or the firm's existing bus) at the ADR 28 trigger: three or more external consumers needing replay, or a mandate to publish to the firm's bus. Then connect to the firm's broker rather than operate your own. The feed handler should subscribe to the firm's market-data platform |
| Cache | Process memory | **Redis**, often in-memory grids at banks | **Change at the second API process:** Valkey (BSD) |
| API style | REST + JSON, SSE | **REST** for integration, **WebSocket or SSE** for push, **gRPC** between internal services in latency-sensitive stacks. **GraphQL** is rare in trading back ends | **Keep REST + SSE.** Add a WebSocket only if the client needs bidirectional subscriptions. gRPC only for the feed handler's internal link if it becomes a separate service. No GraphQL |
| Client | React 19 + Vite web; Tauri 2 desktop (system WebView2) | Trading desktops are **WPF/.NET** (Joule, many in-house tools), **Electron** or **OpenFin**-style Chromium containers at banks, with **FDC3** (FINOS) for app interop, and plain **web** for analytics. **Excel** is universal | **Keep React; keep Tauri** (small footprint, Rust shell). Electron would fix the rendering engine version (WebView2 varies by machine) at about 10× the installer size; that is not worth a change unless WebView2 policy breaks it at a customer. **Add FDC3** context broadcast (instrument, gas day, cargo) when a customer runs an interop desktop. No WPF rewrite. No mobile beyond read-only alerts |
| Excel | Power Query how-to; keys live in the workbook (`docs/sdk/POWER_QUERY.md`) | Desks run **Excel-DNA (.NET) add-ins with RTD**, vendor add-ins (Bloomberg, LSEG, ICIS, Montel), **PyXLL** or xlwings, and increasingly **Office.js** custom functions | **Change now; this has the highest adoption value of any item in this section.** Build an add-in with single sign-on: Excel-DNA (zlib licence) RTD for latest price, freshness and alerts, plus UDFs for curve strip, route cost, netback and balance lines. An Office.js version is an option if the firm is fully on M365. It reuses the existing API; no new backend |
| Deployment | Docker Compose on one host | **VMs with config management** at many utilities; **Kubernetes/OpenShift/AKS** where a platform team exists; a mix of on-prem and **Azure** (common) or AWS | **Keep containers on VMs for pilot and production** (3–6 nodes). Ship a Helm chart only when a customer's platform requires it; that is packaging, not architecture |
| Identity | OIDC (PKCE), local accounts, API keys | **Entra ID** dominates, then Okta or Ping, with SCIM and PIM for admin roles | **Keep OIDC.** Add SCIM at the first customer with more than about 50 users. Disable local accounts in release except break-glass |

## 5. Top 10 changes, in priority order

1. **Fix the serving model.** Use a single shared SSE poller per process with fan-out, keep DB calls off the event loop, run several workers, and load-test 50 users with 3 tabs each against a p95 budget.
2. **HA and recovery.** Primary plus standby, pgBackRest PITR to object storage, a scheduler leader lock, and a restore drill with measured RPO and RTO in the runbook.
3. **Security baseline for go-live.** Split migration and runtime DB roles, make the audit append-only with a hash chain and SIEM export, set the LLM off by default with an EU/on-prem allow-list, and commission an external penetration test.
4. **Observability.** Plain-text Prometheus `/metrics` with histograms and fine route labels, an OpenTelemetry tracing SDK, JSON logs, and alerts on outbox lag, source freshness and pool saturation.
5. **Retention and archive.** Per-table configurable retention (never prune settlements or curves by default), raw-archive digest deduplication plus offload, and the P4 indexes and monthly partitions before the 5-year backfill.
6. **Feed-handler ADR and reference adapter.** Start with one real feed, probably the firm's market-data platform rather than Trayport directly, with conflation, a latest-value table, per-tick rejection, and evaluation moved out of the write transaction.
7. **ETRM trade model.** Index and formula pricing, hourly shapes, optional volume, counterparty and legal entity, and a reconciliation report against the ETRM.
8. **API contract and Excel.** Publish OpenAPI in release, adopt a version and deprecation policy, use one pagination style, add the version handshake, and provide an SDK client object with DataFrame output. Build an Excel-DNA RTD/UDF add-in with single sign-on (§4a).
9. **Horizontal-scale readiness and numerical core.** Make warm views, rate limiting and metrics shareable (Valkey ADR) or explicitly per-node with sticky routing. Switch to the asyncpg or psycopg 3 driver. Add NumPy, SciPy and HiGHS and keep the hand-written solvers only as test oracles.
10. **Enterprise packaging and vendor pack.** MSI plus an updater or Intune guidance, a narrower CSP and mandatory code signing; an SSDF/vendor questionnaire answer set covering AI-assisted development and model egress, DORA/NIS2 supplier annexes, escrow, and an LTS release line.
