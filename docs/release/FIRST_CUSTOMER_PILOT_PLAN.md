# First Customer Pilot Plan

Date: 2026-09-28. Baseline: `42d8144` (repository HEAD when this was written).
This was a planning and read-only reconciliation pass: no source behaviour was
changed, no database was read or written, no credentials were used.
Disposition: **pilot not yet approved; production not approved.**

Update 2026-09-29 (baseline `59ca893`, plus the D7 boundary hardening): the
headless monitoring enrichment path resolves a deployment-named, persisted
SERVICE principal and re-checks it at the provider boundary before loading a
credential or calling a provider, refusing missing, unknown, inactive,
human-type, downgraded and forged acting identities. D7's foundation and
boundary are therefore in code; production provisioning/revocation deployment
evidence and the persisted MCP service identity of D6 remain open (see CA-05).

This is the single current scope, acceptance and blocker register for the first
controlled customer pilot. It reuses the existing release gates
([GA release gates](GA_RELEASE_GATES.md), `scripts/release/policy/stable_gate_policy.json`,
`python scripts/release/validate_stable_release.py`) and the existing CI and
browser-acceptance workflows. It creates no competing approval system, adds no
new gate IDs for existing gates and expands no product scope; it is not legal
advice, certification or vendor comparison.

Evidence classes: **engineering acceptance** (focused suites, builds and CI jobs
here, on the stated fixtures and SHA); **controlled pilot approval** (a written
decision by the accountable role that the named boundary may run with customer
data, supported by the populated and external evidence each blocker names - CI
alone never grants it); **production approval** (unchanged and out of scope:
stable promotion stays fail-closed, and the audit disposition **NOT APPROVED FOR
CUSTOMER PRODUCTION**, audit 19, remains current).

No `PASS` may be written into a gate evidence file without the named exercise.
Simulation output (`_Sim` provenance, `-EnableSimulatedPrices`) is test evidence
only and is never provider or live-market acceptance.

## Delivery decision (proposed - owner decision required)

- **D-PILOT-1 (proposed): browser-first pilot.** Deliver the server runtime, the
  operator ZIP and a supported browser client; the Tauri desktop client joins
  only after actual native evidence exists (no Rust toolchain here, Wave 10
  native work unimplemented, packaging only in release CI). Choosing desktop
  adds G5 plus clean-machine install/upgrade evidence as hard dependencies.
- Accountable role: product owner. Exit: decision recorded; the milestone
  dependencies move with it. This plan does not silently approve desktop scope.

## Provisional pilot boundary (conservative)

- One customer, one isolated deployment (single tenant). **No shared
  multi-organisation or desk-isolation claim**: organisation/portfolio scope
  kinds remain unsupported and are reported as such by
  `ExperienceProfile.unsupported_scope_kinds`.
- European gas decision support only: market evidence to portfolio, constrained
  alternative review, reproducible strategy comparison. Power is deferred, and
  expensive model training is deferred and must not appear as pilot acceptance.
- Retained architecture: FastAPI backend, React web client, PostgreSQL/Alembic
  store, thin Tauri host. No execution, order entry/routing, nomination
  submission, settlement or ETRM behaviour; the product boundary in
  [Release readiness](RELEASE_READINESS.md) stays binding.
- The MCP tool surface is recorded as **not offered** in the pilot deployment:
  the backend and the MCP adapter refuse tool discovery and invocation in
  customer-facing profiles (`trial`/`release` environment or the `release` API
  profile) until the persisted service identity of decision D6 exists - see
  CA-05 and `docs/agents/MCP_SERVER.md`. This is a pilot-scope mitigation, not
  a security approval.
- Licensed external data only through backend ingestion under the customer's
  rights; undecided rights mean public/entitled sources only, stated as such.

## Pilot workflows (must be populated, not seeded-only)

Local runtime observation, 2026-09-29 approximately 13:06 UTC (`dae6efe`):
authenticated ANALYST reads against the development PostgreSQL deployment
returned 500 rows in each market-observation/normalized-quote/quote slice, all
marked simulated; all three slices were STALE and truncated. Portfolio orders
and PnL snapshots returned zero rows/MISSING. This is evidence of a local test
data gap, not an inventory of all stored rows or customer-environment evidence.
No fixture refresh or business-data mutation was used to change the outcome.
PB-01/PB-04 remain open; final acceptance requires governed, entitled populated
inputs, not relabelled or freshly generated simulations.

Current evidence is dominated by seeded/CI fixtures. Each workflow states what
is proven today and the exercise that closes the gap.

### WF-1 - market evidence to portfolio

- Surfaces: market cockpit over `GET /api/projections/market-context` and the
  portfolio orders workspace over `GET /api/projections/portfolio-snapshot`
  (`src/eurogas_nexus/api/routes/public/projections.py:58,104`); the market
  cockpit also renders the source posture (`/api/sources`) and FX (`/api/market/fx`).
- Proven (engineering evidence): scoped hub-board price evidence with bid/ask
  units from the authenticated projection, one card per declared hub and the
  displayed tenor, compared with the rows each card names - by exact id - for
  the displayed context (`scripts/uat/readToRender.mjs:1451`,
  `clients/web/tests/readToRender.test.ts`); portfolio projection slice
  lifecycle including declared empty states (`scripts/uat/browser_workflow_smoke.mjs:178`);
  EN/ZH three-viewport browser sweep on seeded fixtures
  (`scripts/uat/browser_workflow_smoke.mjs`, CI job `Browser acceptance (EN/ZH, 3 viewports)`).
- Not proven: populated physical rows on a customer deployment (screen orders,
  PnL snapshots, resource-pool inputs), and coverage of the market board beyond
  the six declared hubs and the four displayed tenors
  (`clients/web/src/components/MarketTerminal.tsx:53-62`).
- Not implemented (gap, not a control to rely on): the projection routes expose
  no offset/cursor or `page` parameter and no sort parameter; list slices are
  bounded (defaults 500/500/200 for orders/snapshots/contracts, 500 quotes and
  observations), and `limits.truncated` cannot be paged through these projection
  routes (`docs/api/API_CONVENTIONS.md`
  "Pagination"). The workspace batch reads no market projection, so the market
  cockpit's read-to-render comparison holds only where the browser sweep
  issues it (seeded fixtures). A live, read-only capture runner now exists
  (`scripts/uat/captureLiveBoard.mjs`, below) and has not been exercised against
  a populated deployment here; PB-04 stays open.
- Exercise: the read-only WF-1 acceptance procedure below, on the populated
  deployment, recorded against PB-01/PB-04. It is a browser session plus
  read-only API reads on the customer's entitled data; it is never run by
  seeding fixtures.

#### WF-1 read-only acceptance procedure (customer deployment)

Scope: one read-only pass by the accountable pilot reviewer (or the customer
operator the reviewer witnesses) on the populated deployment. No seed, fixture,
import, migration or configuration command is run as part of acceptance; the
read-only surfaces are the browser session the reviewer signs in to and the
projection reads that session already issues. A command that mutates data is
not an acceptance step even when it is available; the seeded in-repo sweep
(`scripts/uat/browser_workflow_smoke.mjs` with
`scripts/uat/seed_uat_fixture.py`/`scripts/uat/seed_browser_identity.py`) is
engineering evidence only - the fixture gate refuses trial/release
(`tests/uat/test_uat_fixture_gate.py`).

1. **Persona and session.** Sign in as the customer's pilot trader/analyst
   identity (a commercial role such as ANALYST). An identity holding only
   platform administration is refused the market and orders surfaces by
   `commercial_access_not_granted` (`src/eurogas_nexus/api/dependencies/commercial_access.py:32-58`)
   - that refusal is the expected result for a permissions test, not an
   acceptance failure. Confirm the deployment's declared entitlement set with
   the read-only `GET /api/me` scope report before judging "no data".
2. **Exact reads checked.** From the market workspace's numeric task
   (`curves`, the default landing view) the reviewer compares the displayed
   values with the session's own
   `GET /api/projections/market-context` read, preserving actual gas-day,
   delivery-product and hub query values (do not send empty placeholders).
   From the orders workspace, `GET /api/projections/portfolio-snapshot`
   (its `portfolio_id` filter narrows the `pnl_snapshots` slice only,
   `src/eurogas_nexus/application/projections/portfolio_snapshot.py:197-201`).
   The reviewer does not compare the projection against the legacy
   `/api/market/observations`, `/api/portfolio/screen-orders` or
   `/api/portfolio/pnl-snapshots` row-for-row: the projection is deliberately
   narrower (the entitlement record it carries says which filter ran,
   `entitlement.row_filter_applied`), so the two answers need not be equal.
   Record every query actually sent, including defaults.
3. **Identity checks per displayed value.** For each card on the market hub
   board (one card per declared-hub/tenor pair for the active tenor tab): the card's
   `data-record-id`/`data-record-slice` must name a row the projection served,
   and the displayed price, bid/ask and unit must equal that row's own values.
   The client prints a quote's currency/unit verbatim when the unit already
   names the currency and otherwise as `currency/unit`
   (`clients/web/src/components/MarketTerminal.tsx:104-115`); a card must not
   show a value from a row with a different gas day, product, hub, tenor or
   currency. A card with no served row must state absence (`n/a`), never a
   stale value.
4. **Gas day, product, tenor, as-of, source.** The shell's Active Context
   (gas day, product, hub) must match the query the session sent and the
   projection's `data.time_basis`/`data.active_context` echo; the board tenor
   tab must match the payload rows compared (`data-board-tenor`,
   `scripts/uat/readToRender.mjs` `collectQuotedBoard`); the payload's single
   `data.as_of_utc` must be the instant the surfaces state
   (`data-projection-as-of`), and every slice's freshness block is evaluated
   against that same instant. Each displayed price must name its row's
   `source_system`; a row's source identity must not be relabelled to another
   feed.
5. **Entitlement and simulation.** No restricted source may appear anywhere in
   the projection response, and no entitled slice may be wider than the
   underlying route (engineering anchors:
   `tests/api/test_projections_api.py::test_projections_are_never_wider_than_the_underlying_routes`,
   `tests/unit/test_projections_application.py`). Read, per slice,
   `entitlement.row_filter_applied`, `filtered_out` (may be `null` when the
   filter ran before the read, `src/eurogas_nexus/application/projections/market_context.py:574-598`)
   and the payload `meta.warnings` (`ENTITLEMENT_FILTERED`, `SOURCE_STALE`,
   `NO_MEASUREMENT`); a withheld-row count is disclosure, not a failure. Rows
   whose `source_system` contains `_sim` case-insensitively (or whose `metadata_json.simulated` is
   true) are simulated inputs, labelled in the UI
   (`clients/web/src/components/MarketTerminal.tsx:63`, `:523-527`); a
   populated deployment must say which rows are entitled vs simulated, and a
   session served only simulated rows is a fixture rehearsal, not customer
   acceptance. The `data_sources` slice states each source system and its
   freshness state.
6. **Empty, stale, unread, refused.** Expected honest states to record rather
   than "fix": runtime DB not configured -> HTTP 200 with every slice
   `available: false`, `MISSING` freshness and warning
   `RUNTIME_DB_NOT_CONFIGURED`; configured but unreadable -> HTTP 503
   `runtime_db_unavailable`; malformed gas day -> 422 `gas_day_invalid`; an
   empty portfolio -> summary aggregates `null` plus
   `VALUATION_EVIDENCE_MISSING`, never 0 (`tests/api/test_projections_api.py:403-436`);
   insufficient entitlement -> the 403 codes above. A missing projection must
   leave the surface's previous values in place and be qualified as degraded,
   never rendered as an empty market (`clients/web/src/stores/api.ts:496-532`).
   When data was expected and a read answers empty/stale, the acceptance
   refuses that workflow until the deployment explains why.
7. **Pagination and sort.** Confirm the reviewer understands there is no "later
   page": list slices are bounded and ordered newest-first (market
   observations by observed instant, then venue, then product,
   `src/eurogas_nexus/application/projections/market_reads.py:147-217`; screen
   orders by observed instant then venue and PnL snapshots by valuation then
   portfolio, `src/eurogas_nexus/application/projections/portfolio_reads.py:38-59`),
   and compare rendered ordering with the actual returned rows. If a slice
   reports `truncated: true`, record it as a known gap; it cannot be walked by
   these projection routes. Do not claim "all rows" or "sorted" beyond what the payload
   and screen show.
8. **Evidence retained (per run).** UTC date; reviewer and witness; persona
   name/roles/scopes from `GET /api/me`; deployment host, app version and full
   commit SHA; gas day, product, hub and tenor; the exact query strings and the
   session's captured projection response bodies for the market and orders
   reads; screenshots of both surfaces with the Active Context visible; the
   per-card comparison notes from step 3; the entitlement/freshness/warning
   readings from steps 4-6; and a statement that no data was written and no
   mutation tool (seed, import, migration, deployment config) was run. Keep the
   session's own network captures in access-controlled local evidence storage;
   redact authorization headers, cookies and credentials before retention or
   sharing, and do not commit customer payloads. Do not reconstruct a payload from the API
   docs. This evidence feeds PB-01/PB-04 (rows, later pages and sort are
   answered as "not implemented", not as "verified").
9. **Pass / refuse.** PASS only when: the visited scope is populated with
   entitled (non-simulated) rows; every displayed identity check in step 3
   holds; as-of, gas day, product, tenor, unit/currency and source are
   consistent per steps 4-5; every unreadable/empty/denied condition met was
   declared as such; and the evidence of step 8 is retained against the exact
   deployment SHA. A truncated result cannot pass full-coverage acceptance;
   any limited-scope acceptance must explicitly name the excluded scope.
   REFUSE (and record as a workflow gap, not an acceptance
   pass) when data was expected but the projection, a card or the underlying
   read is empty/stale/denied/unreachable; when any displayed value cannot be
   tied to the row it names; when only simulated rows are served; or when the
   evidence cannot be reproduced from the recorded payloads.

#### WF-1 offline capture comparator (read-only engineering aid)

The first, bounded slice of populated comparison is offline and operator-run.
`node scripts/uat/compareCapturedBoard.mjs <capture.json>` compares one
operator-supplied capture locally and performs no browser navigation,
networking, credential use, database access, seeding, subprocess or provider
call. It writes nothing: the summary goes to stdout, and no capture is copied,
uploaded or retained by the tool. The comparison itself is the harness's own
board evaluator (`scripts/uat/readToRender.mjs`
`marketBoardRows`/`evaluateQuotedBoard`, the rule the browser sweep applies),
never a second implementation.

The capture is one JSON object under the explicit schema version
`eurogas-nexus.captured-market-board/v1`:

```json
{
  "schema_version": "eurogas-nexus.captured-market-board/v1",
  "source": { "commit": "<deployment commit SHA>", "deployment": "<operator label>" },
  "hub_scope": ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV"],
  "projection": { "status": 200, "body": "<the exact market-context response body>" },
  "board": {
    "boardTenor": "day-ahead",
    "activeTenorTab": "day-ahead",
    "asOf": "<the payload's data.as_of_utc>",
    "asOfText": "<the displayed projection as-of text>",
    "cells": ["<one entry per visible card, as collectQuotedBoard returns it>"]
  }
}
```

An unknown capture-envelope or board key, an unsupported or absent schema
version or an absent critical field is invalid (exit 2), rather than guessed.
The comparator refuses (exit 1) a
well-formed capture that cannot substantiate a comparison: a non-200 or empty
response; an empty card set; no comparable served price
for the displayed scope and tenor, or no card that actually prices one; a price
slice a card depends on that is unavailable, truncated (`limits.truncated` -
which cannot be paged through these projection routes) or not `FRESH`; simulated
rows for the displayed scope (all-simulated and mixed reported separately;
`_sim` case-insensitively, the quote payload's `simulated` flag, or simulated
metadata); a board captured at a different instant than the response; or any
failure from the shared evaluator (a price, unit, source, hub, tenor or
card-to-row identity that does not match). An unreadable, non-JSON or malformed
capture is invalid (exit 2), as is an invalid invocation. Stdout carries only
status, counts and fixed reason codes - never row values, source strings, ids,
URLs, headers, cookies or the evaluator's diagnostic strings - because a capture
is sensitive local operator evidence.

What a pass is: the captured board's cards match the captured response for the
displayed hub scope and tenor, and nothing else. The `source.commit` /
`source.deployment` strings are operator labels, not attested identity, and the
summary states `capture_authenticity`, `customer_acceptance`,
`live_capture_automation`, `portfolio_workflow`, `other_hubs_and_tenors`,
`non_price_slices`, `pagination_beyond_captured_slice` and
`intended_context_selection` as unverified on every run. The live capture runner
below now automates capturing the response and the board - this tool remains for
operator-made captures, including deployments where the live runner's read-only
constraints cannot be met. The portfolio half of WF-1 (the portfolio projection
and the orders workspace) is still not covered. A pass is bounded
captured-board comparison only, never customer acceptance.

Keep captures in access-controlled local evidence storage, redact credentials
before retention and never commit customer payloads (step 8). The comparator
reads only the file it is given and never writes or uploads one.

#### WF-1 live browser capture runner (read-only engineering aid)

`node scripts/uat/captureLiveBoard.mjs` is the bounded live half of the same
comparison, and the reason `live_capture_automation` is dropped from the
summary's `unverified` list when *it* forms the capture. One real browser
session opens against a deployment the operator names, navigates the minimal
existing market/curves route (`/?workspace=market&task=curves`, the numeric
landing task that mounts the hub board,
`clients/web/src/components/MarketCockpit.tsx`,
`app/model/marketCockpitModel.ts`), captures the board the surface displayed
(`collectQuotedBoard`) and the *exact* `GET /api/projections/market-context`
response that session consumed - recorded from the page's own response events,
never re-issued by the tool - then compares the two through
`scripts/uat/compareCapturedBoard.mjs` (`marketBoardRows`/`evaluateQuotedBoard`,
the rule the browser sweep applies). The board's stated as-of must equal a
recorded response's own `data.as_of_utc`; the surface's 10-second projection
poll can race the capture, so the runner retries, bounded, and refuses
(`capture_race_unmatched`) rather than comparing a board with a response it did
not consume. Issuing a second read is not a code path this tool has.

Invocation takes no arguments (a credential or path on argv is refused
unread); the caller configures it through the environment:

- `EUROGAS_UAT_BASE_URL` (required, no default): `https://` anywhere, or
  `http://` on a loopback host; a URL carrying credentials, a query or a
  fragment is refused.
- `EUROGAS_UAT_STORAGE_STATE` (required): the file path of a *preauthenticated*
  Playwright storage state. The runner only checks that the file is readable and
  hands the path to Playwright; it never reads, echoes, copies or writes the
  session material. Keep it in access-controlled local storage and never commit
  it.
- `EUROGAS_UAT_CAPTURE_COMMIT` and `EUROGAS_UAT_CAPTURE_DEPLOYMENT` (required):
  the operator-supplied labels for the capture's `source` block. They are
  unattested, exactly as in the offline comparator, and never printed.
- `EUROGAS_UAT_CAPTURE_TIMEOUT_MS` (optional, 1000..600000, default 120000) and
  `EUROGAS_UAT_PLAYWRIGHT_PATH` (optional; the browser sweep's own convention -
  CI pins `playwright@1.55.0` and chromium outside the repository).

The session is held read-only in the order the guarantees are enforced: the
storage state is supplied, never obtained - there is no login, seed, import,
deployment, provider or mutation option; no init script is installed and no
application state is written; before navigation every request is classified and
only a same-origin `GET`/`HEAD` is continued, while everything else is aborted
and reported (`readonly_guard_blocked`, `external_request_blocked`) and service
workers are blocked, so a cached or synthetic response cannot stand in for the
session's own read. **Any** refused request refuses the attempt, even when the
board itself matched: a session the guard had to restrain is not the session the
operator runs. Off-origin requests are blocked by default and no static-resource
exception is offered yet, so a deployment that needs one refuses until such an
allowance is explicitly justified and reviewed. Request routing does not see
WebSocket channels, so they are guarded separately with Playwright's WebSocket
routing (`browserContext.routeWebSocket`, available since 1.48 - CI pins
1.55.0): every channel is closed before any server connection is made, a channel
refuses the attempt (`websocket_blocked`) exactly as a blocked request does, and
an installed Playwright without that API fails closed before navigation
(`websocket_guard_unavailable`) rather than running unguarded. The browser is
closed in `finally`; every navigation, evaluation, response-body parse, wait and
retry is bounded; and a whole-run watchdog over the entire capture (launch,
context, navigation, bodies, evaluation) closes the browser and refuses with the
fixed `capture_timeout` code when the budget expires. A body parse or evaluation
that never settles cannot be cancelled through any supported API, so the runner
does not claim to cancel one: it stops *waiting*, closes the browser, and
observes the abandoned operation's late settlement so it cannot surface as an
unhandled rejection or a raw error.

Prerequisites, and what their absence looks like: Playwright with a launchable
chromium (absent or unlaunchable: invalid, `playwright_unavailable` /
`capture_launch_failed`); a deployment that is up and reachable (a failed
navigation is refused, `navigation_failed`); and an identity in the storage
state that is already signed in and commercial-access-eligible for the market
projection. A deployment whose session cannot be represented as a Playwright
storage state - an interactive sign-in the tool deliberately does not perform,
or a desktop-shell token held only in memory - is unsupported and the run
refuses (`board_not_displayed`); that is a missing prerequisite to record, not a
data finding, and the offline comparator with an operator-made capture remains
the fallback. A degraded or unread projection refuses
(`projection_status_not_200`, `consumed_response_unusable`) exactly as the
offline comparator refuses it. A surface whose evaluation or response body
never answers within the operation bounds refuses (`capture_timeout`), as does
one that outlives the whole-run watchdog.

Stdout carries the comparator's redacted summary only - status, counts and
fixed reason codes; never a raw body, URL, header, cookie, storage state,
record id or screenshot - and nothing is written anywhere. Exit codes are the
comparator's (0 pass, 1 refused, 2 invalid). A live pass is a bounded
captured-board comparison for the displayed hub scope and tenor and nothing
else: `capture_authenticity` (storage state and source labels are
operator-supplied), `customer_acceptance`, `intended_context_selection`,
`other_hubs_and_tenors`, `non_price_slices`,
`pagination_beyond_captured_slice` and `portfolio_workflow` stay unverified.

### WF-2 - constrained alternative review

- Surfaces: route-cost what-if, resource-pool optimisation
  (`src/eurogas_nexus/application/resource_pool.py`,
  `tests/optimization/test_portfolio_network_optimizer.py`), review task over
  `GET /projections/review-context`, decision cases with evidence.
- Proven: exact min-cost flow with persisted run/snapshot identity; constraint
  and infeasibility disclosure; review task rejects superseded responses.
- Not proven: populated attribution rows, capacity joined-row coverage on
  filtered or later pages, populated storage/LNG views.
- Exercise: challenge one proposed allocation end to end, reproduce its evidence
  by re-reading recorded references, and confirm stale/restricted inputs block
  recommendations and the audit chain names an independent decision actor.

### WF-3 - reproducible strategy comparison

- Surfaces: Strategy Lab backtest with freeze/fork, analysis snapshots
  (`0034_analysis_snapshots`), snapshot citation verified before work and
  recorded on every run path.
- Proven: deterministic backtest contracts (`clients/web/tests/goldenWorkflow.test.ts`);
  citation verified before provider work and recorded durably.
- Not proven: populated strategy comparisons on customer data, walk-forward
  evaluation and leakage controls for a populated dataset.
- Exercise: compare two frozen versions on one populated dataset, re-read the
  recorded snapshot reference, and state uncertainty and costs, not PnL alone.

## Milestones

| # | Milestone | Entry dependency | Exit evidence | Reused gates |
| - | --------- | ---------------- | ------------- | ------------ |
| M1 | Scope freeze | this plan reviewed | recorded boundary + D-PILOT-1 decision | - |
| M2 | Three populated workflows | M1; populated deployment access | WF-1..WF-3 exercises recorded (EN/ZH), simulation labelled | G2, G3, G4, G14 + browser acceptance in `ci.yml` |
| M3 | Authority and security | M1; proceed alongside M2 | identity posture evidence, entitlement denials, elevation dual control, persisted MCP/service identity or backend-enforced disabling of affected capabilities | G8, G15, G18 |
| M4 | Artifact install/upgrade/restore + evidence binding | M1; briefs PILOT-A/B below | extracted-bundle preflight, immutable-image boot + migration, upgrade/rollback/restore drill, same-SHA/digest evidence | G1, G3, G5, G6, G7, G11, G12, G13, G17 |
| M5 | Coherent trader HMI | M2 | populated-persona sweep covering the audit's HMI contract items 1-5, including error and expiry paths | browser acceptance job |
| M6 | Customer assurance docs | M3-M5 evidence | handover pack: install/upgrade/DR runbooks, release notes and known issues, licences/notices, owner-reviewed applicability register | G9, G10, G16 + handover docs |

## Numerical reference cases

Each pilot workflow must reproduce these classes on the deployment before
numerical acceptance. Existing deterministic anchors:

| Case | Anchor today | Pilot must additionally reproduce |
| ---- | ------------ | --------------------------------- |
| FX conversion | `tests/unit/test_route_cost_fx_conversion.py`; no-currency-mixing invariant (mismatched pairs fail closed) | entitled FX rates on the deployment |
| Units and products | `tests/unit/test_route_cost_market_price_selection.py` (quote type/units) | displayed unit and quote type per populated hub/tenor |
| Gas day and DST | `tests/unit/test_gas_day.py`, `tests/unit/test_nomination_window_occurrence.py` (23/25-hour gas days, window wrapping UTC midnight) | the customer gas day boundary on the deployment calendar |
| Timezone normalization | `tests/ingestion/test_source_timezone_contract.py` (CET 06:00 to 05:00Z, CEST 06:00 to 04:00Z, DST switch days, refusal cases) | live source timestamps as delivered on the deployment |
| Cost | `tests/unit/test_route_cost_european_public_tariffs.py`, `tests/unit/test_route_cost_tariff_models.py` | populated tariff inputs and their stated basis |
| Capacity | `tests/unit/test_route_cost_capacity_requirement.py`; joined-row browser evidence from `873a9fa` | populated physical rows with both reads, filters and later pages |
| Point-in-time | `tests/api/test_research_data_api.py`, `tests/api/test_analysis_snapshot_citation_api.py`; immutable dataset snapshots | one populated dataset compared against a re-read snapshot reference |

## Blocker register

Reconciled against code at `42d8144` on 2026-09-28 by reading the cited files.
Severity: P1 blocks pilot, P2 important, P3 tracked. Accountable roles are
roles, not invented people. CA IDs are the audit's; PB IDs are pilot-specific.
CA-02/CA-03/CA-06 were re-checked in code at `308797e` by PILOT-B; the other
rows are the `42d8144` reconciliation. The duplicate CA-02 row was collapsed
to the PILOT-B2 text in the 2026-09-29 WF-1 reconciliation record; no blocker
state changed in that pass.

| ID | Sev | Accountable role | Evidence inspected now | Verification / exercise | Exit condition | Dependency | Status |
| -- | --- | ---------------- | ---------------------- | ----------------------- | -------------- | ---------- | ------ |
| CA-02 | P1 | Release engineering | PILOT-B replaced `load_evidence`: every gate evidence file must now be a schema-version 2 envelope (gate id, full 40-hex tested commit, typed subject with precise digest(s), producer workflow/job/run identity, environment, UTC timestamp) verified against the release context and the actual bundle, never against values declared in the same file; status-only/v1, non-object JSON, wrong gate id, foreign/short SHA, artifact relabelling, stale/future timestamps, unapproved producers and unapproved `NOT_APPLICABLE` fail closed, missing files stay PENDING_EXTERNAL. PILOT-B2 additionally re-derives G1's claimed CI run from the read-only GitHub API (`scripts/release/ci_run_verification.py`) | `python -m pytest tests/release -q` (196 passed, 3 Windows-symlink skips), including the PILOT-B2 matrix in `tests/release/test_ci_run_verification.py`; focused Ruff passed; one live read-only API verification of commit `4d30987` run `36345939410` observed (see the PILOT-B2 record) | Gate evidence carries a versioned envelope binding commit SHA, artifact/bundle digest and workflow identity; mismatches fail closed | PILOT-A (identity exists first); API binding for the other CI producers is still open | Partially fixed, engineering acceptance only: G1's claim is API-verified, but G2/G3/G4/G12/G19 producer run identity is still self-declared text (not cryptographic provenance) and external approval identities remain unconfigured |
| CA-03 | P1 | Release engineering | `release.yml` web job runs `npm test` before build and packaging and records a same-SHA G4 envelope. PILOT-B2 makes the `validate` job record G1 from the read-only GitHub API for the exact commit's `ci.yml` push run and makes `validate_stable_release.py` re-derive it: completed/successful run, matching attempt, and all five required jobs - including `Browser acceptance (EN/ZH, 3 viewports)` - successful, never skipped. PILOT-C runs that same validator in `publish-preview-rc` before its `gh release create` and makes G1 required for every published channel | `tests/release/test_ci_run_verification.py` (wrong repo/workflow/SHA, failed/incomplete/skipped/missing jobs, pagination, stale attempt, malformed/API error, forged copy, local-dry-run bypass, writer round trip); policy/workflow job-name contract test; live read-only verification of run `36345939410`; `tests/release/test_publication_gate_enforcement.py` (channel inheritance, parsed publish-step ordering and credentials, executed gate command fails without evidence, replayed step sequence never reaches the mocked release write) | Publication consumes browser/critical acceptance evidence for its own SHA, verified via authoritative GitHub run metadata | CA-02 envelope (done); release-run exercise of the writer/validator (not yet performed) | Partially fixed - same-SHA browser-acceptance binding exists, and PILOT-C makes every publish job consume the gate before writing a release; preview/RC now block on their mandatory evidence instead of publishing ungated; no release run has exercised the writer or gate |
| CA-05 | P1 | Platform security | `src/eurogas_nexus/mcp/server.py` builds principal/role/scopes from `EUROGAS_NEXUS_AGENT_*` environment values and its own docstring declares calls are not re-authorised per user; checkpoint still lists organisation/portfolio/market/region scope as unsupported. The pilot mitigation is now in code: the server resolves the deployment profile through the authoritative settings (`Settings.from_env`) and, in `trial`/`release` or the `release` API profile, refuses `initialize` tools capability, `tools/list` (empty) and `tools/call` (JSON-RPC `-32000`, `mcp_tools_disabled`) before audit/handler/runtime/SDK/provider, guards the exported `TOOLS`/`TOOLS_BY_NAME` handlers against direct invocation, fails closed on unknown/malformed profiles and ignores hostile `EUROGAS_NEXUS_AGENT_*` grants; development/test/internal keep the existing surface. For the headless worker (D7), `application/service_identity.py` resolves `EUROGAS_NEXUS_WORKER_PRINCIPAL` to a persisted ACTIVE SERVICE principal holding `analysis.query`, and `application/monitoring_service.py` re-reads it at the provider boundary before any credential load or provider call, refusing missing, unknown, inactive, human-type, downgraded and forged acting identities; the shipped `deploy/runtime/compose.yaml` does not pass that variable to the worker container yet | Read module + `GET /api/me` scope report; pilot decision record; `tests/unit/test_mcp_deployment_gate.py` (profile matrix dev/test vs trial/release/unset/invalid, hostile role/scopes, legacy + registry tools via JSON-RPC and direct handler, no audit/SDK/runtime side effects, stdio subprocess refusal and the CI handshake shape); `tests/security/test_worker_service_identity.py` (D7 boundary: missing, forged, revoked, downgraded and human-type identities refuse with zero credential/provider calls; a provisioned least-privilege run grants and audits its attribution) | Pilot is single-customer, MCP is disabled or recorded as not offered; persisted MCP service identity (D6) implemented or explicitly deferred; D7's worker identity provisioned in the pilot deployment with a revocation exercise recorded | Pilot decision; ADR for service identity | Mitigated - backend/adapter enforced disabling in customer-facing profiles; D7's worker identity resolution and provider-boundary enforcement exist in code with focused tests, while production provisioning/revocation deployment evidence and the persisted MCP service identity (D6) remain open; not closed, no security approval claimed |
| CA-06 | P1 | Release engineering | `container-acceptance` inspects the immutable digest and platforms and now writes a G19 envelope binding that image digest; the validator recomputes it against `image-metadata.json` and `release-manifest.json`, and `assemble` waits for the job so the evidence is inside the bundle | Read jobs at `release.yml` assemble/container-acceptance plus the new envelope tests; boot/migration/smoke exercise still absent | Immutable digest boots, Alembic upgrades to head, authenticated read smoke passes, evidence assembled end to end in CI | PILOT-A identity; populated tenant not required | Partially fixed - digest inspection and binding done (G19 required for RC/stable); boot/migration/smoke acceptance depth open |
| CA-10 | P1 | Deployment engineering | Literal TAB removed in PILOT-A at both entry points (and the same defect in the maintainer `build_release.ps1`); the operator ZIP policy (schema 2) ships eleven members: the ten reviewed files plus one generated `release-identity.json` (schema version, app/release version, channel, full commit SHA, API image `repository@sha256:` digest); the `deployment` workflow job now needs the `runtime-image` job and packages the ZIP from the resolved `release-context.json` plus the validated image-metadata digest | `python -m pytest tests/release -q` (108 passed, 3 Windows-symlink skips): real archive identity fields, fail-closed missing/malformed/conflicting identity and digest, no literal TAB, PowerShell parse of both entry points, extracted-bundle `Preflight` on a real temporary ZIP (identity resolves, `release_identity_source=bundle`, honest host blockers) | Bundle carries explicit release identity (version, channel, commit SHA, API image digest); the final ZIP SHA-256 stays external in `SHA256SUMS`/`release-manifest.json`, never inside the archive; extracted preflight resolves it with no source checkout or manual env var | None | Fixed in code, engineering acceptance only: extracted preflight resolves identity and reports host blockers; the runtime primitive's *complete* positive preflight is unverified in this sandbox (WMI access denied, docker engine pipe unreachable - pre-existing host-probe behaviour outside PILOT-A); no installation, upgrade or production-release acceptance claimed |
| PB-01 | P1 | Engineering + data operator | Checkpoint records that capacity and market acceptance ran on empty/seeded CI fixtures and do not cover populated rows, later pages or live acceptance | WF-1..WF-3 exercises on the populated deployment, read-only, no invented runtime observations | Populated exercises recorded with both underlying reads and row identity | Customer deployment access | Open - blocked on populated environment |
| PB-02 | P1 | Owner + legal (via customer contract) | Research/data-foundation code distinguishes entitlement but no contract decision exists in-repo | Owner-reviewed per-source rights decision | View/derive/export/LLM/training rights recorded per source family | Customer contract | External decision required - no legal claim made here |
| PB-03 | P1 | Security owner + customer IT | `GET /api/health` reports enforced authentication; OIDC/JIT paths exist; no real issuer acceptance exists | Real-IdP sign-in, revocation drill, external security review on the deployment | G15/G18-style evidence produced against the customer environment | Customer IdP and environment | External - not started |
| PB-04 | P2 | HMI owner + engineering | Browser sweep is CI-honest but seeded; populated read-to-render assertions remain open | Populated-persona sweep per audit HMI contract items 1-5 | Populated walkthrough at 1440x900 and 1920x1080, EN and Mandarin, with error/expiry paths | PB-01 | Open |
| PB-05 | P2 | Release owner | Code signing is explicitly `unsigned_pending_external`; G17 stays PENDING_EXTERNAL | Supply organization signing credential and verify Authenticode | Signed installer evidence for the pilot artifact | Organization certificate | External - operator-owned |
| PB-06 | P2 | Owner + legal | Audit records CRA/GDPR/DORA/NIS2/AI Act questions as applicability-dependent | Owner-reviewed applicability register for this customer and deployment model | Register recorded; no certification or conformity claim made | Customer entity, deployment model | External decision required |
| PB-07 | P3 | Engineering | No Rust toolchain in this environment; Wave 10 native features unimplemented | Native evidence only if D-PILOT-1 chooses desktop | Desktop evidence exists, or desktop is explicitly out of pilot scope | D-PILOT-1 | Tracked |

## Next two implementation briefs (bounded; parent reviews the schema)

### PILOT-A - extracted deployment bundle identity and preflight (do first)

- Why first: every later evidence record needs a stable artifact identity, and
  CA-10 is reproducible today on this Windows machine.
- Objective: the operator ZIP carries one machine-readable release identity
  (version, channel, commit SHA, API image digest). The final ZIP SHA-256 lives in
  an external checksum/provenance record; it cannot hash itself inside the ZIP.
  Both Windows
  entry points resolve the package version from that identity, fail closed with
  a clear message when it is missing or inconsistent, and never read a
  source-checkout-only path. Remove the literal TAB defect. Extracted-bundle
  `Preflight` must resolve identity with no source checkout and no manually set
  `EUROGAS_NEXUS_VERSION`, then report its real remaining blockers.
- Files: `scripts/install/windows/Deploy-EurogasNexus.ps1`,
  `scripts/install/windows/Install-EurogasNexusServerRuntime.ps1`,
  `scripts/release/package_deployment_bundle.policy.json`,
  `scripts/release/package_deployment_bundle.py` (identity entry validation and
  generation), `scripts/release/package_deployment_bundle.START-HERE.txt`,
  the ZIP assembly in `.github/workflows/release.yml` and the already-resolved
  context from `scripts/release/resolve_release_context.py`.
- Focused tests: extend `tests/release/test_deployment_bundle_policy.py`
  (identity file present in the real archive with exact fields; no literal TAB;
  every shipped path resolves inside the bundle) and
  `tests/release/test_deployment_roles.py` (version resolution), then
  `python -m pytest tests/release -q`, a PowerShell parse check of both scripts
  and one real preflight run over the extracted archive as a manual exercise.
- Non-goals: no new infrastructure, no silent Docker installation, no secrets in
  the bundle, no installer behaviour change beyond identity resolution, no
  claim that the ZIP is installation-approved.

### PILOT-B - same-SHA/digest gate evidence binding (do second)

- Why second: it binds evidence to the identity PILOT-A creates; it is the
  enabler for CA-02, the CA-03 remainder, CA-06 depth and every M4 gate record.
- Objective: versioned evidence envelopes for gate evidence files, carrying at
  least: schema version, gate id, commit SHA, artifact/bundle digest, workflow
  run identity (id/URL where available), producing environment and produced-at
  time. `load_evidence` validates the envelope against the release context:
  missing, malformed, old-format or mismatched SHA/digest evidence can never
  read as PASS (external gates stay PENDING_EXTERNAL). Evidence writers emit v2
  envelopes; web build evidence ties to the same-SHA CI/browser result.
- Files: `scripts/release/validate_stable_release.py`,
  `scripts/release/policy/stable_gate_policy.json` (declare required envelope
  fields per gate type), `.github/workflows/release.yml` (writers near the
  postgres/performance, vulnerability and container-acceptance steps, and the
  assembly call), `.github/workflows/ci.yml` only if a same-SHA artifact must be
  consumed by the release run.
- Focused tests: new `tests/release/test_evidence_envelope.py` covering
  present/absent/mismatched SHA, missing digest, malformed and old-format
  envelopes, and a valid envelope; keep `tests/release` green.
- Non-goals: never fabricate PASS, do not flip any external gate, do not change
  channel inheritance (CA-01 behaviour), no new infrastructure or datastore.

## PILOT-B implementation record (engineering evidence only, 2026-09-28)

Baseline `308797e`. Bounded change; no release, tag, publish, deployment,
database migration, credential, commit or push. What the code now does:

- `scripts/release/evidence_envelope.py` defines the schema-version 2 envelope:
  gate id, status, full tested commit SHA, typed subject (`source` / `artifact`
  / `image`) with precise digests, producer workflow/job/environment/run
  identity, `produced_at_utc`, and an optional approval block.
- `scripts/release/validate_stable_release.py` verifies each envelope against
  the trusted release context and the actual bundle: commit SHA equality,
  subject kind matching the policy declaration, artifact digests recomputed
  from the shipped files, image digest compared with `image-metadata.json` and
  `release-manifest.json`, producer profile allowlist, GitHub run identity for
  CI producers, and a 30-day freshness window with 15-minute future skew.
  Missing files stay PENDING_EXTERNAL; old-format/status-only and non-object
  JSON, wrong gate id, foreign or short SHA, source/artifact relabelling,
  unapproved `NOT_APPLICABLE`, unapproved producers and unauthorised external
  PASS all fail closed.
- `scripts/release/policy/stable_gate_policy.json` (schema 2) declares the
  subject kind, producer profiles and `not_applicable_allowed: false` for every
  gate, adds G19 (image-digest-bound container acceptance, RC/stable), and
  keeps `authorized_external_approvals` empty, so no external gate can pass
  until the organisation configures a real approval identity.
- `scripts/release/write_gate_evidence.py` is the single CI writer.
  `release.yml` writers (validate, reliability, dependency-scan, web, assemble,
  container-acceptance) all emit envelopes bound to `$GITHUB_SHA`; `assemble`
  now waits for `container-acceptance` so the bound evidence is inside the
  assembled bundle; the stable gate invocation does not pass the local-only
  flag (contract-tested).
- `scripts/release/run_release_dry_run.py` writes local-only envelopes
  (`run_release_dry_run.py`, environment `local-dry-run`) that strict
  validation rejects, so local evidence can never authorise publication. The
  dry run no longer records PASS for checks it does not perform: the Python
  suite and the PostgreSQL migration drill are PENDING_EXTERNAL locally, and
  the security-tests status now comes from actually running
  `scripts/security/run_security_acceptance.py`.

Focused validation: `python -m pytest tests/release -q` -> 149 passed, 3
Windows-symlink skips (including the new `tests/release/test_evidence_envelope.py`
matrix: malformed/non-object JSON, wrong gate/SHA/digest, missing metadata,
expired/future timestamps, unapproved producer and external approval,
NOT_APPLICABLE bypass, valid scoped evidence, missing files); focused
`ruff check scripts/release tests/release tests/contract` passed. No CI run,
release publication, installation or deployment was performed, so this is code
and focused-test evidence only - the first RC/release run must be observed
before CI-level acceptance is claimed.

Trust boundary and residual work (not claimed as solved):

- Envelope producer/approval fields are self-declared text. The validator binds
  them to policy-declared profiles and to a run-URL shape for this repository,
  but an actor who can write into the evidence directory could still copy an
  authorised identity string. Signed attestation and authoritative GitHub-run
  metadata verification remain open.
- CA-03's same-SHA browser result is deliberately not integrated as a file
  check: publication must not infer CI success from an arbitrary artifact.
  Consuming the `ci.yml` browser-acceptance result for the tagged SHA requires
  GitHub API run metadata and is recorded as the separate submilestone
  PILOT-B2. Publication stays blocked meanwhile (G1/G6/G7/G13 have no CI
  evidence source yet and every external gate is PENDING_EXTERNAL).
- Configuring a real approval identity in `authorized_external_approvals` is an
  owner/legal decision (PB-03/PB-05); this change invents neither an identity
  nor a credential.
- Local dry-run evidence cannot authorise release and the local gate report
  therefore stays red until the corresponding CI evidence exists.

## PILOT-B2 implementation record (engineering evidence only, 2026-09-28)

Baseline `75e98a5`. Bounded change; no release, tag, publish, deployment,
database migration, credential, commit or push. What the code now does:

- `scripts/release/ci_run_verification.py` is the single read-only GitHub API
  verification. It contacts only `api.github.com`, only under
  `/repos/<owner>/<repo>/`, only for the policy's trusted repository, workflow
  path, event and required-job list, with a request timeout, a bounded retry
  count for transient/5xx/429 responses, bounded pagination and no credential
  echoed into output or errors. It discovers the `ci.yml` push runs for the
  exact release commit, requires every one of them to be `completed`/`success`
  (so a pending or failed re-run blocks), and reads the verified attempt's jobs
  from the attempt-specific jobs endpoint - never `filter=latest`, which can
  switch attempt between the run read and the jobs read. After the jobs read it
  re-reads the run and refuses any change to attempt, status, conclusion or
  head SHA, so a re-run that lands mid-verification is rejected rather than
  half-accepted. Each required job must be present exactly once with
  `completed`/`success` - skipped, missing or failed jobs never count. A
  declared run id, attempt or URL that disagrees with the API is refused, so a
  stale attempt or a copied/forged envelope cannot pass. HTTP redirects are
  refused by a custom no-redirect opener (any 3xx fails closed), because
  urllib's default redirect handling re-sends the `Authorization` header to the
  `Location` target, which is not limited to `api.github.com`; tests prove no
  second request is issued for cross-host or same-host redirects.
- The claim itself is never authoritative. The envelope's `detail`, URL and
  metadata are inputs to compare against the API response, never the source of
  truth; a missing, pending, failed, malformed or unreachable result stays
  blocked and there is no offline-success fallback (test fixtures are injected
  only in unit tests).
- `scripts/release/write_ci_run_evidence.py` is the writer used by the release
  `validate` job: it records what the API reports for `$GITHUB_SHA`, writing
  `PASS` only with the verified run identity under `report.ci_run`, and
  `FAIL`/`PENDING_EXTERNAL` otherwise. `validate` (the writer) and
  `publish-stable` (the strict gate re-derivation below) are the only jobs that
  carry `actions: read`, and only their CI-verification steps receive
  `GH_TOKEN`; every other job keeps its existing permissions and channel
  inheritance.
- `validate_stable_release.py` re-derives G1 from the API whenever the evidence
  claims PASS - including under `--allow-local-dry-run-evidence`, so the local
  exception cannot bypass strict release verification. The reported
  repository/context binding is also checked: a policy or `--repo` outside the
  trusted repository fails closed.
- `scripts/release/policy/stable_gate_policy.json` (schema 2) declares the
  `ci_acceptance` contract (repository, host, workflow path, event, required
  jobs, bounds) and the `ci-verification` producer profile; `G1` keeps
  `required_for: rc` and `authorized_external_approvals` stays empty.
  Desktop packaging is deliberately not a required job: the main-branch run
  reports it as skipped and native packaging is not pilot acceptance.

Focused validation: `python -m pytest tests/release -q` -> 196 passed, 3
Windows-symlink skips, including the new `tests/release/test_ci_run_verification.py`
matrix (wrong repository/workflow/SHA; failed, incomplete, skipped and missing
jobs; multiple pages of runs and jobs; stale run attempt; the re-run race
between the run read and the attempt-pinned jobs read; malformed payload and
HTTP failures; a forged copy of a valid envelope; a policy/workflow job-name
contract that fails on drift; the writer round trip; transport host/credential/
retry bounds and redirect refusal with no second request) and the preserved
negative envelope tests. Focused
`ruff check scripts/release tests/release .github` passed. One read-only live
API verification was performed with the production transport for commit
`4d30987` (CI run `36345939410`, attempt 1): the verdict recorded the five
required jobs, including `Browser acceptance (EN/ZH, 3 viewports)`, as
successful; an unknown-SHA check and a tampered `report.ci_run.run_id` were
both refused. The redirect-refusal and attempt-pinning corrections in this pass
were validated with fixture transports only (including a real `urllib` opener
with a stubbed network leg); no new live API call was made. No release
workflow, publication or deployment was executed, so this remains code,
focused-test and read-only API evidence - the first RC/release run must be
observed before CI-level acceptance is claimed.

Residual and limits (not claimed as solved):

- The other release-run envelopes (G2/G3/G4/G12/G19) still carry self-declared
  producer run identity; only G1's subject is re-derived from the API. CA-02 is
  not claimed closed.
- This verifies the *source commit's* CI run - including browser acceptance on
  the exact commit - not acceptance of the packaged artifact, image or
  installed bundle, and not populated, provider, live-market or native-desktop
  acceptance.
- No release run has exercised the writer or the strict gate; release
  publication was not attempted. The preview/RC publish job still does not
  consult the gate policy, so CA-03's publication-time consumption is enforced
  for the stable path only.
- Required job names are the exact names the Actions API reports; renaming a
  `ci.yml` job requires a reviewed policy update, and the contract test fails
  until they agree.
- External approval identities remain unconfigured (`authorized_external_approvals`
  is empty), so every external gate stays PENDING_EXTERNAL and stable
  publication stays blocked.

## PILOT-C implementation record (engineering evidence only, 2026-09-28)

Baseline `efa7514`. Bounded change; no release, tag, publish, deployment,
database write, credential use, workflow dispatch, commit or push. What the
code now does:

- `publish-preview-rc` runs the same gate as `publish-stable` before its
  `gh release create`: `scripts/release/validate_stable_release.py` against the
  assembled `release-final` bundle. The job gains only `actions: read` (for
  G1's read-only API re-derivation) and the step-scoped `github.token`; there
  is no `--allow-missing-platform-artifacts`, no
  `--allow-local-dry-run-evidence`, no `continue-on-error` and no conditional
  `if:` on the gate or the publish step, so a failing gate stops the job before
  any release write.
- The gate is an exact-SHA and exact-bundle check: the envelope commit must be
  the release commit, artifact gates re-hash the shipped files, the image gate
  must match `image-metadata.json`/`release-manifest.json`, and G1's same-SHA
  CI claim is re-derived from the read-only Actions API. Preview/RC use the
  same validator and policy as stable - no parallel or weaker approval path.
- `stable_gate_policy.json` now declares `G1` with `required_for: all`, so
  preview, RC and stable each require the same-SHA browser/critical acceptance
  evidence for their own commit. Channel inheritance is unchanged: stable-only
  external gates (G15-G18) are still not demanded of preview or RC, stable
  still inherits every RC gate, and the signing policy is untouched.
- Consequence, recorded rather than worked around: preview/RC publication now
  blocks until its mandatory evidence exists. No CI job produced G5 (desktop
  packaging), G8 (security tests) or G10 (SBOM) at this baseline, and G11
  (provenance) has no RC producer, so a preview/RC run fails the gate and
  publishes nothing. That is the intended fail-closed behaviour; the missing
  producers are follow-on work, and nothing was marked PASS or exempted to
  avoid it. G8 has since gained a real producer - see the G8 implementation
  record below; G5/G10 (and G11 for RC) are still open.

Focused validation: `python -m pytest tests/release -q` -> 203 passed, 3
Windows-symlink skips, including the new
`tests/release/test_publication_gate_enforcement.py`: policy inheritance across
all three channels (G1 required for each, stable-only externals not imposed on
preview/RC), parsed publish-step ordering and step credentials, no bypass flag
or `continue-on-error` anywhere in `release.yml`, the configured preview gate
argument vector executed for real against a fixture bundle with no evidence
(non-zero exit, G1 PENDING_EXTERNAL, mandatory-gates failure for preview), and a
replayed step sequence in which the failing gate stops the job before the
mocked `gh release create`. Required-job and permission contracts in
`tests/release/test_ci_run_verification.py` were updated for the new
`actions: read` holder. Focused `ruff check scripts/release tests/release .github`
passed. The release workflow itself was not dispatched or exercised.

Residual and limits (not claimed as solved):

- G5/G8/G10 (and G11 for RC) had no CI producer at this baseline, so preview
  and RC remained blocked in practice. This change enforces policy; it does not
  create the missing evidence and does not claim desktop, security-acceptance
  or SBOM acceptance. G8 now has its executed-suite producer (G8 record below);
  G5/G10/G11 producers are still missing.
- The `runtime-image` job still writes GHCR from `validate` alone, but only a
  run-attempt-unique staging candidate tag; the customer-facing channel tag is
  now written exclusively by the gate-first, repository-serialized promotion
  jobs after a successful publish and post-publication verification, and a
  conflicting existing tag is refused untouched. The bounded slice is
  implemented in code and focused tests
  ([Container promotion plan](CONTAINER_PROMOTION_PLAN.md) §9); it has not
  been exercised against a live registry or a real release run, exact
  index-digest preservation by `imagetools create` on GHCR remains
  unverified, and exclusive registry writers remain an operational
  prerequisite. Candidate exposure is staging, not approval.
- G2/G3/G4/G12/G19 envelopes still carry self-declared producer run identity;
  only G1's claim is re-derived from the API.
- No release run has exercised the writer, the gate or the publish path, so
  CA-03's publication-time consumption is enforced in code and focused tests
  only.

## G8 security-tests producer implementation record (engineering evidence only, 2026-09-28)

Baseline `7f36b37`. Bounded change; no release, tag, publish, deployment,
database write, secret, credential use, workflow dispatch, commit or push. What
the code now does:

- `scripts/release/run_security_evidence.py` records the G8 envelope only from
  an actual execution of the fixed `tests/security` suite: it launches
  `sys.executable -m pytest tests/security` with a JUnit XML report in an
  owner-only scratch workspace, derives the status from that executed report
  and from the structured selection evidence written by its minimal pytest
  plugin, and keeps the executed counts, selection counts,
  failing/erroring/skipped case identifiers and the report SHA-256 in the
  schema-version 2 envelope. There is no `--status` argument, no parameter that
  accepts a pre-existing report and no test-selection filter, so no caller can
  declare the result - status-only `--status PASS` evidence for this gate is
  refused by `write_gate_evidence.py`, which now rejects any gate that declares
  an `evidence_runner`.
- The executed suite cannot be silently filtered: a non-empty
  `PYTEST_ADDOPTS`/`PYTEST_PLUGINS` is refused before anything runs, the fixed
  command pins `-o addopts=` (plus `--import-mode=importlib`) so repository or
  suite pytest configuration cannot reduce the suite, and the plugin records
  the collected/selected/deselected counts plus any cases removed by collection
  hooks. Any deselection, any hook-removed case, missing or malformed selection
  evidence and any count drift against the JUnit report fail the gate: a
  partial suite is not an executed suite.
- It fails closed with explicit `FAIL` evidence and a non-zero exit on a
  non-zero pytest exit, an empty suite, any failure/error/skip (a skipped
  security case is not an executed case), any deselection, a missing, malformed
  or count-inconsistent JUnit report (declared testsuite counts must equal the
  `testcase` elements and their outcomes), a missing selection report, a
  checked-out HEAD that does not match `--commit-sha` before or after the run,
  a dirty tracked worktree in release context, a run that exceeds the bounded
  1800-second timeout, or any other tool error. Nothing is marked PASS on a
  tool error, and the generic writer can no longer produce G8 evidence at all.
- The requested commit is bound to the checkout: `git rev-parse HEAD` must
  equal `--commit-sha` before and after the execution and release-context runs
  refuse a dirty tracked worktree. `--local-dry-run` (used only by the local
  dry-run, which passes the local-only producer identity the strict validator
  rejects) records the dirty state, marks the evidence `release_eligible:
  false` and is not a status/report/selection bypass; the release workflow
  never passes it and the workflow contract test asserts its absence. This is
  checkout source identity, not cryptographic provenance or signed attestation.
- The release `validate` job runs the producer after the existing tests and
  before the `release-validate-evidence` upload, so `security-tests.json` now
  travels in the same uploaded evidence directory as `python-tests.json` and
  `ci-run.json`; the assembly job's `release-*` merge carries it into
  `release-assets/release-evidence/`, where the publication gate reads the
  policy-declared file. The executed JUnit XML is retained beside the envelope
  as the deterministic companion `security-tests.junit.xml`, uploaded with the
  same evidence artifact and hashed in the envelope, so the recorded digest
  stays auditable after the scratch workspace is removed. A failing or
  unevidenced suite stops the job before the upload, so no release path can
  consume a G8 PASS that was not executed.
- The evidence stays source-bound (`subject.kind = source`, no artifact
  digests): it is the executed source security suite, not packaged-artifact
  security acceptance, not an installation test and not a penetration test.
  G15 (external security acceptance), G16 (provider certification), G18 (UAT)
  and every other external gate are unchanged and still PENDING_EXTERNAL; the
  policy's `authorized_external_approvals` stays empty.
- The maintainer dry run now records G8 through the same runner:
  `run_release_dry_run.py` invokes `run_security_evidence.py` with the
  local-only producer identity and `--local-dry-run`, so the local dry-run
  executes the real suite instead of labelling an unrelated static
  security-acceptance report as G8. That static check
  (`scripts/security/run_security_acceptance.py`) is still executed as a local
  diagnostic and written to `security-acceptance-report.json` in the dry-run
  output root; it is not gate evidence and can never declare G8, and the
  dry-run's evidence-name-to-gate map no longer contains `security-tests`.

Focused validation (revised slice, 2026-09-28): `python -m pytest tests/release
-q` -> 327 passed, 3 Windows-symlink skips, including the rewritten
`tests/release/test_security_evidence.py` (34 tests) and the new dry-run wiring
test. The producer suite covers: injected-runner negatives for non-zero exit,
empty suite, failures/errors, skips, missing/malformed report, declared-count
mismatch, timeout and launch error; the environment guard (both variables,
including via the shipped CLI) and the `-o addopts=` override against a suite
`pytest.ini` that would otherwise run 1 of 3 cases; deselection refusal
(fabricated evidence and a real collection hook that silently drops cases) and
selection/`JUnit` count drift; wrong-SHA, dirty-worktree and HEAD-moved
refusals (each proving the suite is not executed on a mismatch); the local
dry-run mode (dirty state recorded, `release_eligible: false`, accepted only by
the local validator); the retained companion and its hash; the default command,
plugin environment and owner-only `mkdtemp` workspace helper; a tiny real
pytest subprocess suite; an independent end-to-end run of the actual
`tests/security` suite producing the PASS envelope (183 cases, zero
deselected); and the policy/writer/workflow contracts. `python -m pytest
tests/security -q` -> 183 passed as its own independent run. `ruff check .`
passed. The local Markdown link contract still passes except the pre-existing
sandbox-permission case that writes outside the workspace (unrelated to this
slice; it also failed before it). Sandbox note: this environment denies child
processes access to
owner-only (0o700) directories, so the in-process tests inject a sandbox
workspace factory for the child pytest run as the task brief allows, and the
shipped CLI could only be exercised here on its refusal paths and dry-run
wiring; the production `mkdtemp` path itself runs on developer machines and CI.
No release workflow was dispatched; the producer was exercised on this
worktree, not inside GitHub Actions.

Residual and limits (not claimed as solved):

- This is source-bound automated security-test evidence. It does not test a
  packaged artifact or image, does not perform an external review and cannot
  close G15/G16/G18 or the private-network/VPN-only posture switch.
- G5 (desktop packaging), G10 (SBOM) and G11 (provenance for RC) still have no
  CI producer, so preview/RC publication remains blocked by those gates.
- The envelope's producer fields remain self-declared text; only G1 is
  re-derived from authoritative GitHub API metadata.
- The producer's owner-only (`mkdtemp`) scratch workspace is not exercised
  end-to-end inside this sandboxed environment, which denies child processes
  access to 0o700 directories: the child-running tests inject a sandbox
  workspace factory, and the default path is exercised on developer machines
  and CI, not here.
- The release workflow has still not been dispatched, so the artifact
  upload/merge path is verified in code and contract tests, not by an observed
  run.

## What this plan does not claim

Not a pilot or production approval; not legal advice; no certification. No
populated, provider, live-market or native-desktop acceptance follows from any
green CI run or unit test. Reconciliation here is code reading at `42d8144`, not
a penetration test, full source audit or customer-environment execution.

## WF-1 plan-reconciliation record (documentation only, 2026-09-29)

Baseline `2c33699`. Bounded documentation change; no source behaviour, database,
credential, provider, release or deployment change. What was corrected, by
reading the implementation and tests:

- the duplicate CA-02 blocker row was collapsed into the later PILOT-B2 row -
  the one whose evidence already records G1's read-only GitHub API
  re-derivation - so the API-verified account is retained once, not superseded
  by the earlier text. Its remaining limits (G2/G3/G4/G12/G19 self-declared
  producer identity, empty `authorized_external_approvals`) are unchanged.
- WF-1's surface paths now carry the `/api` prefix the app actually mounts
  (`src/eurogas_nexus/api/route_registration.py` includes the router). Claims
  were re-scoped to what the inspected code and tests show: the browser
  harness's quoted-board comparison (`scripts/uat/readToRender.mjs`,
  `clients/web/tests/readToRender.test.ts`) and slice read-to-render groups
  (`scripts/uat/browser_workflow_smoke.mjs`) exist, while offset/cursor
  pagination and sort parameters do not exist anywhere in the projection
  routes; `limits.truncated` is conservative and cannot be paged past. The
  earlier "later pages" wording is therefore replaced by an explicit gap.
- the WF-1 exercise is now the compact read-only acceptance procedure above,
  reusing the existing harness where it applies and cleaving mutating fixture
  tooling (blocked outside development/test by
  `tests/uat/test_uat_fixture_gate.py`) from the read-only customer checks.

Read for this record (implementation and tests inspected): the projection
routes and application modules cited in WF-1; `projections/context.py`,
`projections/envelope.py`, `projections/market_reads.py`,
`projections/portfolio_reads.py`; `security/permissions.py`;
`api/dependencies/commercial_access.py`, `row_entitlement.py`;
`clients/web/src/api/client.ts`, `stores/api.ts`,
`app/model/marketContextModel.ts`, `app/model/portfolioSnapshotModel.ts`,
`components/MarketTerminal.tsx`, `components/MarketCockpit.tsx`;
`scripts/uat/browser_workflow_smoke.mjs`, `scripts/uat/readToRender.mjs`,
`scripts/uat/seed_uat_fixture.py`, `scripts/uat/seed_browser_identity.py`;
`tests/api/test_projections_api.py`, `tests/unit/test_projections_application.py`,
`tests/contract/test_browser_probe_paths.py`,
`clients/web/tests/marketContextProjection.test.ts`,
`clients/web/tests/portfolioSnapshotProjection.test.ts`,
`clients/web/tests/browserSmokeGates.test.ts`,
`clients/web/tests/readToRender.test.ts`,
`clients/web/tests/tradingContextProjections.test.ts`, `tests/uat/`.

Next narrow engineering task this review reveals: no automated acceptance
compares the market cockpit's rendered hub board with the projection on a
populated deployment (PB-04), and a truncated projection slice cannot be read
further through these projection routes. Next implement a read-only populated-
deployment comparison mode that reuses the existing board evaluator without
fixture writes, retains redacted local evidence and refuses full-coverage
acceptance when relevant slices are truncated. Pagination remains a separate
engineering gap; the comparison mode must not silently waive it.

## WF-1 live capture runner implementation record (engineering evidence only, 2026-09-29)

Baseline `0c3c7dd`. Bounded implementation; no application, API, database,
permission or deployment change. What was added:

- `scripts/uat/captureLiveBoard.mjs`: the live read-only capture runner described
  above. It imports the browser sweep's own `collectQuotedBoard` and the
  comparator's own `compareCapturedBoard`/`instantMs`, so there is one collector
  and one comparison rule, not a second implementation of either. It records the
  response the browser consumed through `page.on("response")`, matches the
  board's stated as-of to that response with the comparator's own instant rule,
  derives the capture's `hub_scope` from the displayed cards, and refuses
  (`capture_race_unmatched` and friends) rather than substituting a refetch. The
  route guard, the WebSocket guard (closed before any server connection; fails
  closed when the API is unavailable), the URL policy, service-worker blocking,
  the per-operation bounds on the response-body parse and `page.evaluate`, the
  whole-run watchdog (`capture_timeout`, browser closed on deadline) and the
  browser close are implemented as described above.
- `scripts/uat/compareCapturedBoard.mjs`: two small additions and no behaviour
  change for existing captures - `captureAttemptSummary` (the same redacted
  summary shape with no coverage for a live attempt that could not form a
  capture) and the export of the existing `instantMs` helper so the live match
  uses the comparator's own as-of rule.
- `clients/web/tests/liveBoardCaptureRunner.test.ts`: 24 focused cases. Twenty
  run deterministically here against a mocked Playwright surface and an injected
  clock: URL policy, request guard (mutation and off-origin refusals, allowed
  same-origin reads, abort codes), environment validation, card-derived hub
  scope, the response usability rule (query echo, status, projection identity),
  the as-of match and its bounded retry both ways, the four capture-failure
  classifications, the missing/unsettled board refusals, the deadline and
  always-close paths, a never-settling response body / evaluation / navigation
  (bounded return, fixed `capture_timeout`, browser closed, no capture timer
  left behind, no unhandled rejection from the abandoned operation), the
  WebSocket guard (channel closed and refused; fail-closed without the API),
  and no-leak assertions over a canary-bearing payload, storage path, argv
  token and base URL. Three synthetic loopback-fixture cases drive the real
  Playwright and chromium end to end (a served board that passes, a page whose
  POST is refused by the guard, and a page whose WebSocket channel is closed);
  one process-level case checks the CLI wrapper's exit code and redaction.

Verified in this environment, from `clients/web`: `node --test
--test-isolation=none tests/liveBoardCaptureRunner.test.ts` - 20 passed, 0
failed, 4 skipped with their reasons. `--test-isolation=none` was needed
because this implementation sandbox denies the runner's default per-file child
process; the CI invocation (`npm test`, `node --test "tests/*.test.ts"`) is
unchanged. The three browser integration cases and the process case skipped
because the sandbox also refuses to spawn a child process from Node (chromium
reports `spawn EPERM` even though `playwright@1.55.0` and `chromium-1187` are
present on disk), not because of a runner defect; the mocked cases above are
the evidence that ran here. The full web suite ran the same way: 724 tests, 716
passed, 4 skipped, and the four failures are the pre-existing comparator CLI
cases, which fail in this sandbox at `spawnSync` (`status: null`, `EPERM`)
before any comparator code runs - the comparator CLI itself was smoke-run from
the shell and behaved unchanged. No live capture was attempted against any
endpoint, no customer data exists in this repository, and the runner was not
pointed at the local development deployment.

Not verified, and not claimed: a live capture against the real application or a
customer deployment; that a given deployment's session can be represented as a
Playwright storage state; the behaviour running behind a subpath deployment;
and any customer acceptance. The parent is expected to exercise the runner
against the local fixture; if that run is blocked, the reason code it prints is
the honest account of which prerequisite was missing, and the offline
operator-capture path is unchanged and still the fallback.
