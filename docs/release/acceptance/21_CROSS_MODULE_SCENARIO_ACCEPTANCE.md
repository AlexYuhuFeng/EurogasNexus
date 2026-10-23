# Synthetic cross-module scenario acceptance — 2026-10-23

This bounded Linux test uses actual PostgreSQL, source API on port 8000, Vite on
3000, and named test accounts. It establishes a contract-to-strategy-to-historical
backtest-to-review path. It does not establish production readiness or provider
certification. No permissions, original fixtures, security controls, or production
configuration were changed. No push or deployment occurred.

## Actual API evidence

Evidence is retained in ignored `.local-runtime/cross-module/` (`results.json`,
`state.json`, `run.json`, `run-events.json`, `run-series.json`,
`run-attribution.json`, `review.json`, and the executable local harnesses).
Harness paths are `.local-runtime/cross-module/check.py`, `finish.py`,
`browser.cjs` and `backtest-browser.cjs`. The first harness is a one-time fixture
creator; resume with retained state instead of rerunning it to avoid duplicate
synthetic records. There are 24 successful checks. One initial harness call used uppercase review
enums and received 422; the documented lowercase request succeeded and its
persisted review was re-read. This was a harness correction, not a product fix.

The trader-persona account created resource `cross-module-1792764650`, a synthetic
NBP pipeline resource with 123 MWh/day. Existing contract payloads were compared
and preserved. Both persona accounts report authoritative backend role ANALYST;
this run does not claim a distinct TRADER backend-role acceptance.

The analyst saved an owner-private strategy, edited and reloaded its draft,
verified the exact carried contract ID and quantity, then froze version
`strategy-version-157b45e9c15f44688558`. A subsequent draft update returned 409.
The other persona received 404 for the private strategy and run.

Four exclusively prefixed synthetic historical records were added for July 1–2,
2026: NBP, GBP/MWh, explicit day-ahead/within-day names, DELIVERY_PRICE, MID,
matching EU-CAM current-gas-day intervals and observations before decisions.
Their source is honestly recorded as EEX_Sim under the existing EEX entitlement;
these are simulated NBP marks, not certified EEX products. No entitlement was
broadened. Unique explicit names isolate this scenario from earlier fixtures.

Run `strategy-run-4939bcbeb76f40369473e639` executed backtest-engine/2, admitting
four price references across two decisions. It persisted two events, two series
points and six attribution rows. Manifest provenance pins the exact frozen
content hash and contract identity. Frozen definition content hash:
`sha256:dd2c723480b7d69ed203e79cb2cc521736ec4278e4bb69c1c41c0920514291bc`. A `needs_attention` review references this
genuine run and was re-read from the review API.

Results remain qualified: COMPLETED_WITH_WARNINGS, temporal integrity APPROXIMATE,
SOURCE_ENTITLEMENT_SIMULATED and LATEST_INTRADAY_OUTSIDE_CONFIGURED_WINDOW.
Gross indicative PnL is GBP 2337, modeled costs GBP 123, and net GBP 2214;
coverage is 1.0. These numbers are synthetic research outputs, not execution or
production financial evidence. The warning was not suppressed.

## Actual Chromium handoff and save

The authenticated analyst opened Resources → Library → the exact saved contract
→ Open in Strategy Lab → Start new unsaved draft. Assertions verified the exact
resource ID, quantity 123 and blank all-in cost. The user flow then explicitly
selected NBP and both synthetic series, entered cost 20, and saved through the
real version POST (200). A full browser reload retained the exact resource.
The new strategy remained Private — owner only. No page errors were observed.

`browser-results.json` records three workflow assertions; `handoff-offer.png`
(despite its historical filename) captures the reloaded persisted browser draft.
The screenshot was visually inspected. API historical execution used a separate
strategy version with explicit target declarations; the browser-created draft
was deliberately left unfrozen and is not claimed as that historical run.

A separate authenticated browser selected the API-created frozen version and opened
the persisted run from Backtest history. Its actual result panel displayed exact
net/gross/cost values, engine/2, APPROXIMATE, four distinct admitted references,
two simulated-evidence events, six attribution rows and both warning-qualified
decisions. `backtest-dom.txt` and `backtest-review.png` retain this evidence.
This is browser read/render acceptance of the API-executed historical run.

Focused handoff, draft-save, experiments, decision-pack and golden-workflow Web
selection: 35 passed, zero skipped. Log: `focused-tests.log`.

## Remaining delivery boundaries

The synthetic historical scenario proves the supported OCM-versus-day-ahead
component with explicit compatible evidence. Source-specific binding, certified
historical/provider economics, unsupported single-index or arbitrary-basket
strategies, production SSO, signed platform installers and production recovery
remain separate gates. Review here is a persisted owner governance decision;
it does not demonstrate an independent reviewer approval of a shared strategy.
