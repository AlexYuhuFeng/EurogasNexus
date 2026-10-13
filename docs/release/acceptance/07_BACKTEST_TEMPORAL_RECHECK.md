# Historical backtest temporal recheck — 2026-10-08

Status: bounded future-window guard implemented and verified; full temporal acceptance remains blocked.

## Authority and architecture boundary

Accepted `docs/product/BACKTEST_ENGINE_SPEC.md` owns this behavior: section 1 promises historical evaluation; section 3 distinguishes observation, availability and delivery times; section 6 requires component/product delivery filtering; section 11 forbids unrestricted forward fill and requires explicit bounded carry-forward. Section 15 defines coverage as completed evaluations / all evaluations, not independent fresh-observation coverage.

The preceding real UI run and READ ONLY DB trace in report06 proved 365 future decisions reused one identical price-reference set, with matched observations ending before the evaluation window. This is not acceptable historical-data coverage. Existing records and evidence must remain unchanged.

An initial proposal to require every quote's delivery interval to contain the decision instant was **withdrawn before implementation**: day-ahead/month-ahead quotes can legitimately be observed before their delivery period. The associated DeepSeek worker was stopped before product changes; it is not running alongside its replacement. A product-aware target-delivery contract is necessary, and an arbitrary observation TTL or unconditional point-in-window filter would silently alter forward-market semantics.

## Independent bounded fix

The completed worker implements only the established historical boundary: reject a professional BACKTEST whose evaluation end exceeds the application request timestamp, using the already injectable request clock. Equality remains allowed; deterministic pure-domain replay has no wall-clock dependency. The application refuses before snapshot/run writes and returns a structured, useful 422 through the actual UI. EVALUATION/scenario behavior, price-selection numerics, coverage formula and existing run rows are unchanged. Both current production callers reach this guard: the API passes no client-selected request clock, and the agent capability also omits the injectable clock. Experiment-linked execution uses the same service. Injection is an internal test seam, not a request field that bypasses the guard.

No full acceptance is claimed. In particular rejecting future windows does **not** repair expired-price reuse inside an otherwise historical period or establish that the Coverage label means fresh/adequate market coverage; that requires the separate delivery-product design below.

## Actual host verification (2026-10-08 04:51 Asia/Shanghai)

The worker's `historical-boundary-evidence.json` originally described generated instrumentation and unit validation, not browser execution. It was preserved as `worker-validation-evidence.json`. Reviewer confirmed the local API process signature, stopped old PID12052 and used the existing hidden launcher to load reviewed source (new API PID20524). Web PID5052 and PostgreSQL PID5400 remained the same local stack; no installation or database reset occurred.

Host Playwright then actually submitted 2026-10-07 through 2027-10-07 using the existing frozen version. The server returned **422 backtest_request_invalid**, explaining that the end is after the server request time. The rendered alert remained visible at desktop and 390px width. A fresh GET showed the same four run IDs after refusal. The test then submitted exactly one historical control window, 2026-10-05 through 2026-10-07: HTTP200 created `strategy-run-1330aed95b0d4b7483d878e8`; full reload/history selection reopened that exact run.

Independent PostgreSQL READ ONLY fingerprints before/after prove all four pre-existing run rows are unchanged, with runs 4→5 and snapshots 4→5. The API focused test separately proves future refusal alone leaves zero run/snapshot/job records. The browser script's no-job note is not treated as an independent browser assertion of job counts.

Actual evidence: `.dnx-out/uat-temporal-20261008/evidence.json`, `historical-boundary-evidence.json`, `host.log`, `before.json`, `after.json`. Inspected screenshots include `future-refusal-section.png`, `future-refusal-mobile-viewport.png`, and `historical-run-after-reload-viewport.png`. The historical control displays two evaluations and indicative GBP1,738.88; this establishes plumbing, not freshness or profitability. The alert is explicit but verbose/raw API-style; mobile has existing navigation/identity overflow, so this is not a full responsive UX pass.

Reviewer independently ran **48 Python tests passed** (future guard, backtest API, engine and coverage warning), **10 frontend tests passed**, TypeScript `tsc --noEmit` and focused diff check passed. Existing golden/numerical expected values were not rewritten; domain calculation and engine version were not changed. Worker additionally reports its pre-edit baseline44 and wider focused post99 checks; these are supplementary to the host checks. Whole-tree EOF whitespace issue noted in report06 remains outside this slice.

Files: `src/eurogas_nexus/application/backtest_service.py`, `tests/api/test_backtest_api.py`, new `tests/unit/test_backtest_future_window_guard.py`, `clients/web/src/components/strategy/StrategyBacktestWorkspace.tsx`, EN/ZH locale heading, new `clients/web/tests/strategyBacktestRefusal.test.ts`, report07 and execution checkpoint. No commit/push yet. Final runtime API ready=ready and Web HTTP200.

## Unresolved delivery-product design

The frozen component exposes hubs, tenors and price_basis, but these do not yet establish a complete mapping between decision time and target delivery period for same-day physical valuation, day-ahead pricing, reference assessments and forward products. Review must identify the existing supported semantics, explicitly resolve unknown/invalid delivery windows, preserve legitimate future-delivery quotes, and apply existing bounded carry-forward/fallback only to the correct series/product. Canonical gas-day DST and hourly interval boundaries require tests. No new numerical semantics or golden expected values may be introduced silently.

The worker analysis is `.dnx-out/uat-temporal-20261008/architecture-delivery-admissibility.md`; it is advisory, not an accepted ADR. Its proposed DELIVERED_WINDOW match cannot merely accept a row's own window/tenor, which could still recycle an expired product. The following is the concrete next design proposal for review:

| Component leg / intended use | Required target and evidence match |
| --- | --- |
| Same-gas-day physical valuation | Resolve explicit target gas-day interval using the canonical calendar; require rows for that product/interval and availability at or before decision time. |
| Day-ahead leg | Declare whether the leg prices next gas day or compares a previously quoted price for the current delivery day. Resolve that target interval explicitly; a future delivery start is legitimate when it matches the declared target. |
| Hourly/month-ahead/forward leg | Freeze the target tenor and roll convention or explicit delivery interval; match the resolved interval, hub, units and price basis. Same tenor text alone is insufficient across different delivery months. |
| Assessment/reference level | Declare its role separately from executable delivery-price valuation; attach validity/publication and any approved carry-forward rule. Never infer a fresh market observation from a reused reference value. |

Normal evidence selection must apply availability AND the declared product interval. Only after finding no admissible evidence may an explicitly configured, series/product-compatible carry-forward or fallback apply; existing maximum age must be enforced even if a stale row with the same name exists somewhere in the batch. Such reuse must be marked separately from observed coverage. Missing/invalid product mapping must produce an explicit unresolved/blocked state, not an invented 24-hour delivery window. Historical records remain unchanged; any revised selection engine needs versioned provenance, expected numeric-difference review and unchanged-control/golden/DST/interval tests. Existing scenario evaluation remains separate until its own semantics are explicitly aligned.

This introduces a declaration absent from the frozen fixture, so field ownership, compatibility of existing frozen definitions, source normalization mappings and accepted CR-04 amendment need a reviewed design decision before implementing this numerical selection change. Future-window refusal does not substitute for this mandatory next work.

Contract retirement, remaining Hub/Pipeline/LNG acceptance, research splits/OOS, API management, permission negatives and reviewed delivery/push remain part of the full goal.
