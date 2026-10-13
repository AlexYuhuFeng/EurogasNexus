# Multi-business resource-term workflow — 2026-10-13

Verdict: **PARTIAL BUSINESS ACCEPTANCE / BOUNDED HANDOFF CORRECTED.**

## Actual workflow baseline

Installed Chromium drove the real local UI with the existing development identity.
The retained `evidence.json` records 149 harness checks, three generic resource-term
create/read/edit/reload journeys and exactly six governed contract writes. These checks
do not mean three complete business workflows passed. The initial Strategy resource
fields remained `res-1` although the URLs carried the selected ids. Three baseline
`09-binding-failure.png` images and `binding-baseline.json` retain that failed gate.

| Scenario | Retained UAT record suffix | Observed terms | Missing business gate |
| --- | --- | --- | --- |
| Hub Trading pool surrogate | HUB-POOL | CONTRACT_POOL, TTF, 321 MWh/day, edited base price 25.50 GBP/MWh | No trade/confirmation object or market trade lifecycle; this pool is not Hub Trading acceptance |
| Pipeline Gas Tender terms | PIPELINE-TENDER | PIPELINE_IMPORT, TTF, 654 MWh/day, edited base price 27.25 GBP/MWh | No tender/offer/bid/award model, deadline, maximum-bid objective or delivery-period profile |
| LNG Cargo Regas terms | LNG-REGAS | LNG_REGAS, Bacton Beach, 987 MWh/day, edited base price 29.75 GBP/MWh | No cargo/vessel or terminal-slot identity, cargo energy, unloading/send-out window; readiness API has no client caller |

All three ids start `DNX-UAT-BIZ-20261013-20261013T032343560Z-`; names say
`DEV UAT ONLY`. Persisted numeric fields declare GBP/MWh and MWh/day, and the
synthetic test index basis explicitly says GBP. These are development assumptions,
not market quotes, actual agreements or an FX conversion. Base contract price is
not an all-in strategy cost.

Each exact id appears in the real resource-pool options response and Pool impact UI.
Payment disclosure/readiness screenshots were captured. Backtest remained disabled
because there was no frozen selected version. No optimization or run is claimed.
The interrupted harness resumed the same records without duplicate creation.

## Bounded correction and actual recheck

The Design draft now lives in the existing workspace renderer, so it survives visits
to Contracts. Contract handoff opens Design with a pending offer. Its deliberate
Start new unsaved draft action clears strategy/version/run selection and carries
exact persisted contract identity, name and compatible native daily quantity.
An offer alone does not retarget, fork or write an existing saved/frozen version.
A dirty draft blocks replacement; Keep current draft cancels the offer and retains
its edits. This is in-memory preservation across workspace visits, not a claim of
recovery after browser reload or closing the application.

No fabricated res-1/Resource 1/100/20 resource defaults remain. Missing stored resource
fields stay empty, validation blocks incomplete resources, and the request builder
refuses an incomplete resource instead of inserting synthetic values. Base contract
GBP/MWh price is shown separately. All-in cost and market hub/price-series choices
remain empty until explicitly supplied. Explicit incompatible currency/energy-unit
metadata blocks saving; no EUR-to-GBP, therm-to-MWh or other conversion is inferred.

`handoff-recheck.json` records PASS_BOUNDED_HANDOFF with 38/38 checks. Actual Chromium checked all three
retained records: visible exact id/name/quantity, empty all-in cost and market hub,
blocked Save, and absence of a selected saved strategy/version. It also verified
that a dirty name/resource survives Portfolio/Contracts navigation and a second offer,
that replacement is disabled and cancellation retains the draft. A real existing
frozen version remained selected with disabled fields during an offer; only deliberate
Start cleared its selection and opened an editable new unsaved form.

The Save request mapping was additionally exercised in the real rendered form with
an explicitly synthetic all-in cost 31.125 GBP/MWh and explicit NBP/SAP/ICE_OCM choices.
The browser intercepted the strategy-create reply with a nonpersisted fixture identity
and aborted the version request. Captured body contains the selected LNG record id,
987 MWh/day and explicitly entered 31.125 cost. This proves UI-to-request mapping only;
no successful persisted strategy save or business/market compatibility acceptance is
claimed. All non-login mutations in this recheck were intercepted or aborted.

## Preservation and permitted writes

Before/final read-only PostgreSQL evidence records exact ids and whole-row SHA256
hashes. No missing or changed original rows in all six groups: 2 contracts, 2 captured
revisions, 3 strategy versions, 7 runs, 4 dataset snapshots and 7 strategy-data snapshots.
Current totals are respectively 5, 8, 3, 7, 4 and 7. The contract increases are solely
the three retained UAT records and edited revisions. `db-post-handoff.json` and
`final-validation.json` additionally compare the complete final workflow snapshot,
including the new UAT records, with the post-correction state.

Baseline writes were restricted to development sign-in and the existing governed
contract route with the exact owned prefix. All other writes, including automatic
resource optimization, were aborted. Rechecking the correction creates no contracts
or database strategies/versions/runs/snapshots. No role grant, source enable,
certification, execution, nomination or settlement occurred. Test records are retained;
retirement is absent and hard deletion was not substituted.

## Validation and remaining gates

Focused frontend model/evidence/handoff tests: 30 passed. TypeScript noEmit passed.
Markdown link verification checked 292 files with no unresolved local links; diff whitespace checks passed.
Full frontend suite: 921 passed, 3 Playwright resolution skips, no failures; the
existing supported Playwright-path override then ran the 24-test browser-harness
suite with all 24 passed and no skips, including the three synthetic Chromium tests.
These harness tests remain distinct from the real application workflow above.

- Complete Hub trade/confirmation, Pipeline tender/bid/award and LNG cargo/slot
  business models remain missing gates. Generic resources are surrogate evidence.
- Retirement/effective-date/freeze/supersede lifecycle remains absent. Payment terms
  are read-only; generic lag inputs do not establish a cash schedule or dated valuation.
- Separate denied-action role walkthroughs remain untested: development login uses
  one configured provisioned identity and exposes no safe temporary-role fixture.
  No identity or grant was created.
- Selecting compatible market evidence and an explicit all-in cost remains necessary;
  contract handoff does not make a strategy ready for a backtest.
- Market/source context is stale/simulated development evidence. Full business,
  supplier, customer and final Astra integration approval remain open.

## Reproducibility and evidence

Local artifacts: `.dnx-out/contracts-business-20261013/`, including checkpointed
`workflow.mjs`, original `evidence.json`, `db_preservation.py`, before/final/preservation
JSON, `read-only-capture.mjs`, `binding-baseline.json`, `handoff-recheck.mjs` and its
JSON/log, focused/full/harness test logs, and scenario PNGs. Corrected resource scope
and native-term images are `12-binding-corrected.png` and `13-native-terms.png` for
all three scenarios; dirty/frozen preservation has separate captures. Material screenshots
are opened for visual inspection. Credential values are scanned only in memory;
the report contains no key/password value.

Historical runtime interruption: Docker stopped after the first two Hub writes.
The parent recovered the same existing container with the supported Desktop restart;
the same API/Web processes were reused and the checkpointed browser resumed. This
blocker is resolved and final preservation is complete. No reset, fallback DB,
cleanup retry, dependency installation, automatic push or release occurred.
