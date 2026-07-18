# R30B Intraday Decision Feed ExecPlan

## 1. Goal

Deliver a DB-first intraday market decision feed that can surface cross-hub,
cross-venue gas spread candidates on the main map workspace. Simulated EEX,
ICE OCM, and Trayport feeds must use the same normalized quote contract that
future licensed connectors will use. The backend must calculate and persist
candidate economics; Web and desktop clients only read API results and refresh
visible data every 10 seconds.

The first validated scenario is a compatible TTF/NBP delivery product where a
sellable bid exceeds the buyable ask plus route, capacity, trading, FX, and
configured risk buffers. The product calls this an `executable spread
candidate`, never guaranteed or risk-free profit.

## 2. Non-goals

- No order entry, order routing, auto-trading, trade capture, booking, clearing,
  nomination submission, capacity booking, or approval workflow.
- No direct client-to-database or client-to-provider connection.
- No claim that a positive modelled spread is guaranteed profit.
- No licensed EEX, ICE OCM, or Trayport network call in this increment.
- No Kafka, Redis, Celery, WebSocket, or new runtime dependency.
- No browser-owned authoritative quote, route, tariff, capacity, or opportunity
  fixture.

## 3. Product Boundary

The capability is trader decision support. Every opportunity includes data
age, source lineage, assumptions, missing inputs, warnings, capacity and depth
limits, and `human_review_required=true`. A candidate can be actionable for
human review only when both tradable quote sides, compatible delivery periods,
route cost, capacity, currency conversion, source freshness, and access posture
are sufficiently resolved. Otherwise it is stored and shown as `WATCH` or
`BLOCKED` with exact reasons.

The backend may recommend reviewing a candidate; it must never generate an
order or an execution instruction.

## 4. Files To Create Or Modify

Backend and DB:

- `alembic/versions/0014_intraday_decision_feed.py`
- `src/eurogas_nexus/db/models/market_intelligence.py`
- `src/eurogas_nexus/db/models/__init__.py`
- `src/eurogas_nexus/db/registry.py`
- `src/eurogas_nexus/db/repositories/market_intelligence.py`
- `src/eurogas_nexus/domain/market_intelligence/`
- `src/eurogas_nexus/ingestion/simulated_market_prices.py`
- `src/eurogas_nexus/api/routes/public/market.py`
- `src/eurogas_nexus/sdk/market.py`
- `scripts/ops/ingest_simulated_market_prices.py`

Clients:

- `clients/web/src/api/client.ts`
- `clients/web/src/stores/api.ts`
- `clients/web/src/app/hooks/useWorkspaceRuntime.ts`
- `clients/web/src/app/shell/AppShell.tsx`
- `clients/web/src/components/NetworkWorkspace.tsx`
- `clients/web/src/components/MarketTerminal.tsx`
- `clients/web/src/components/IntradayDecisionFeed.tsx`
- bilingual i18n and narrowly scoped styles

Documentation and tests:

- `docs/product/INTRADAY_DECISION_FEED-EN.md`
- `docs/product/INTRADAY_DECISION_FEED-CN.md`
- architecture queue and pause-point documents
- unit, integration, API, SDK, ingestion, contract, and client structure tests

## 5. Dependency Policy

Use Python standard library, SQLAlchemy, Pydantic, FastAPI, React, TypeScript,
Zustand, and the existing client stack only. Add no dependency.

## 6. Data Policy

PostgreSQL is the runtime source of truth. The normalized quote table stores
source-shaped L1 bid/ask/last values, visible quantity, delivery window,
timestamps, currency/unit, quality, provenance, simulation state, and source
record identity. The opportunity table stores only backend-derived snapshots
linked to quote, route, tariff, capacity, and FX sources.

Simulated rows are permitted before licensed subscriptions are available, but
must be visibly marked `simulated=true` and use provider-replaceable field
semantics. Test data is synthetic. No credential or vendor data is committed.

## 7. API Impact

Add stable read-only routes:

- `GET /api/market/quotes`
- `GET /api/market/opportunities`

Keep `GET /api/market/observations`, `/api/market/fx`, and
`/api/market/spreads`. `/api/market/spreads` becomes a compatibility summary of
persisted decision opportunities rather than a client-calculated spread.

All routes return the standard envelope and fail visibly when the runtime DB is
not configured or unavailable. SDK methods mirror the two new routes.

## 8. DB Impact

Migration `0014_intraday_decision_feed` adds:

- `market_quotes`: append-style normalized L1 quote ticks with bid/ask depth;
- `company_tso_access`: effective-dated operator access posture used to block
  routes the company cannot use;
- `intraday_opportunities`: persisted scan snapshots and decision status.

Indexes cover latest quote lookup by hub/product/source/time and latest
opportunity lookup by status/time. No import-time connection or automatic
migration is introduced. The simulated worker writes quotes and runs the
deterministic scan in the same explicit runtime process.

## 9. Tests

- quote simulator produces realistic bid/ask spreads and visible depth;
- simulated and future licensed rows share one model contract;
- opportunity engine uses buy ask and sell bid, never mid prices;
- mismatched delivery windows, stale quotes, missing FX, missing route cost,
  missing capacity, and unconfirmed TSO access cannot become actionable;
- maximum quantity is the minimum of buy depth, sell depth, and route capacity;
- persisted quote/opportunity rows are returned through API and SDK;
- app import remains DB-connection-free;
- network/market client refresh cadence is 10 seconds;
- main workspace renders decision candidates without calculating economics;
- existing test suites and builds continue to pass.

## 10. Validation Commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
npm --prefix clients/web run build
npm --prefix clients/web audit --audit-level=high
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

No external provider call and no live migration are part of automated tests.

## 11. Acceptance Criteria

- The runtime DB has normalized quote, company TSO access, and opportunity
  tables.
- Simulated EEX/ICE OCM/Trayport ticks update those tables at a 10-second
  default cadence without a client-side fallback.
- The backend persists TTF/NBP compatible-delivery opportunity scans using
  buy ask, sell bid, route cost, quantity limits, FX, data age, and warnings.
- Positive raw spread without required operational inputs is `WATCH` or
  `BLOCKED`, not actionable.
- Main and Market workspaces visibly refresh prices and opportunities every 10
  seconds through `/api`.
- API and SDK preserve source lineage and human-review metadata.
- Ruff, targeted tests, client build, dependency audit, and API import pass.

## 12. Rollback Notes

Application rollback can stop reading the new endpoints while retaining the
append-only tables. Migration downgrade drops only the three R30B tables and
their indexes. The existing market observation, route-cost, strategy-lab, and
portfolio paths remain compatible and independently usable.
