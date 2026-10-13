# Current authenticated contract workflow recheck — 2026-10-07

Verdict: **PARTIAL; not complete contract lifecycle or commercial acceptance.**
This current run supersedes any earlier claim that page/scope coverage alone
closed all functional workflows. The persisted resource-term create/update
path works in this fixture. Retirement/removal is absent. The library
column-alignment defect found in the initial capture was repaired and rechecked
below; this does not close the remaining lifecycle or full-product gates.

## Environment and evidence

- Existing Windows PostgreSQL 16.2, `nexus_browser`, schema 0039; existing
  authenticated development API on 127.0.0.1:8000 and Vite on :3000.
- DeepSeek wrote the Playwright script; Astra reviewed and ran it on the host.
  No installation, server replacement, API write substituted for UI, or reseed.
- Run: 2026-10-07T10:33:02.867Z–10:33:21.683Z; viewport 1440×900, English,
  fresh Chromium context and real development sign-in form.
- Local evidence: `.dnx-out/uat-contract-20261007/contract-flow.mjs`,
  `evidence.json`, `host-run.log`, six numbered PNG files. All six saved PNGs
  were opened and inspected by the integration reviewer in this run.
- Test identity: `DNX-UAT-20261007-20261007T103302Z`. The existing contract's
  nonsecret field fingerprint was unchanged after both writes. The new test
  resource remains stored; no hard deletion or cleanup through SQL was used.

## Observed steps

| Step | Interaction and result | Screenshot / evidence |
| --- | --- | --- |
| 1 | Sign in and open Portfolio → Resources. Missing daily quantity correctly disables Save to pool and explains why. | `01-preform.png` |
| 2 | Enter a uniquely named PIPELINE_IMPORT resource term through the actual clause controls, including quantity, costs, payment lags, financing and restrictions. Save becomes enabled. | `02-create-filled.png` |
| 3 | Click Save to pool: HTTP 200, `created`, revision 1. Authenticated GET matches entered values. Full reload displays 1234 MWh/d and 27.35 GBP/MWh in the library. | `03-persisted-after-create.png` |
| 4 | Select the persisted row, change its name, resource cost to 31.40 and variable cost to 1.25 through the editor. | `04-edited-form.png` |
| 5 | Save: HTTP 200, `economics_updated`, revision 2. GET and another full reload match the edited fields; Portfolio pool renders the resource. | `05-persisted-after-update.png` |
| 6 | Inspect row and workspace actions. No remove/retire control exists, so the removal leg is blocked. No destructive substitute was used. | `06-delete-blocked.png` |

All 35 script assertions passed. Independent read-only PostgreSQL queries
confirmed the edited name, PIPELINE_IMPORT, quantity 1234, cost 31.4, and
immutable captured revision numbers 1 and 2. The script records each save both
in a generic recorder and an outcome recorder: four log entries represent
**two** actual contract writes. Exit 0 does not mean full acceptance: its
explicit result is PARTIAL because removal is unavailable.

## Open findings and constrained remediation

1. **P1 — No retirement workflow for persisted resource terms.** Created test
   terms cannot be removed from ordinary pool participation through the UI.
   The existing integration plan section 2.3 prohibits hard deletion and calls
   for an auditable retirement event with effective/recorded dates and retained
   references. A follow-up slice must specify/implement retirement, optimistic
   concurrency, authorization, audit atomicity, exclusion from current pool
   eligibility and preserved revision/history reads. New draft merely resets
   a local unsaved draft; it is not persisted-record retirement.
2. **P2 — Library headers do not align with their values (repaired).** In screenshots 3,
   5 and 6, Volume begins around x638 but its values around x300; Resource cost
   begins around x882 but values around x443. Status values occupy the volume
   heading's vicinity. This makes commercial comparisons misleading. Fix the
   shared column layout, retaining keyboard row actions and mobile behavior;
   verify against the same existing test record without creating another.

## Layout repair and independent recheck

DeepSeek changed only `ContractWorkbench.tsx` and `app.css`: shared five-column
tracks for header/rows, four data columns in the edit/load button, and a separate
Actions cell containing the existing Strategy and Inspector buttons. Existing
EN/ZH Actions translations are reused; behavior and persistence are unchanged.
The reviewer's first real screenshot caught a residual worker defect: the load
button spanned all five columns, placing actions below column one. A bounded
desktop-only grid-span correction moved actions into column five; mobile keeps
the stacked layout. Static worker checks had not detected that visual defect.

The host reran the read-only check against the **same** persisted test record,
without another create or update. Both saved final screenshots were opened:
`layout-after-1440.png` and `layout-after-390.png`. Geometry evidence is in
`layout-geometry.json`; all four header/value x coordinates differ by at most
1px, and the Actions header/button by 0.563px. Actions occupy the data row rather
than a new row. Document scrollWidth equals viewport width (1440 and 390).
The narrow screenshot is stacked and readable. It still omits an explicit
Resource cost label when the table header is hidden, and the existing global
navigation clips horizontally; these are not certified closed by this slice.

Independent validation: 60 `contractLibraryReadOrder`/`readToRender` tests
passed; `tsc -p clients/web/tsconfig.json --noEmit` passed; focused diff check
passed. The whole working tree still has an unrelated pre-existing trailing
blank line finding in `application/dataops_observability.py:237`.
Worker-reported broader 113-test results are supplementary, not substituted
for this independent run.

During the first post-edit attempt Vite exited with Windows watch EBUSY on
the worker's temporary edit directory. The existing reviewed launcher restarted
the same installed Vite; no package or alternate server was installed. The final
screenshots and geometry were captured after restart and after the CSS correction.

The apparent `Agreement`/`Resource agreement` wording difference is **not
served-revision drift**: `clients/web/src/i18n/index.ts` deliberately overrides
the JSON label after importing it. The worker's earlier static report inferred
drift incorrectly. No positional field fallback was reported in the actual
run; persisted field comparisons independently verified all asserted values.

## Limits

The unauthenticated initial `/api/me` returned 401 before successful login.
The recorder also lists requests marked failed during navigation/reload;
it did not retain their failure reason, so this report does not certify them
as harmless cancellation or claim zero network failures. Contract writes and
their subsequent reads passed. Screenshot review does not establish complete
accessibility compliance; keyboard/screen-reader/mobile checks remain open.

This was one PIPELINE_IMPORT term at TTF, not separate Hub Trading, Pipeline
Tender and LNG Cargo/Regas lifecycle acceptance. The type selector also offers
BEACH_DELIVERY, LNG_REGAS, STORAGE and CONTRACT_POOL; seeing options is not
evidence that each business journey works. Payment declarations, LNG-specific
readiness, strategy/data-set workflows, API-key/provider administration,
authorization boundaries, retirement and release/operations gates remain open.
The displayed market fixture is stale/simulated; no commercial approval,
execution, nomination submission or settlement is claimed.
