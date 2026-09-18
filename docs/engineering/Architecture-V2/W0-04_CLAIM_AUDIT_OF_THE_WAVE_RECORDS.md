# W0-04 Claim audit of the wave records

Status: Wave 0 governance evidence. Documentation only; it changes no runtime behaviour by itself.
Recorded 2026-09 against the tree at `main` after Waves 0-10 had delivered their slices.

## 1. Why this exists

Every wave record in this pack asserts what the platform does. Those assertions are the programme's
memory: the execution checkpoint points a resuming engineer at them, and the reconciliation register
turns them into statuses and owner decisions. A record that overstates what the code does is
therefore not a documentation wart - it is a false status, and it is worse than a missing record,
because it is *read as evidence*.

This slice is a claim-by-claim audit of the wave records against the code. It was run because the
programme had just found three separate instances of the same failure mode by accident (a profile
string that changed nothing, a `strategy_ir` that was dropped, a `BACKTESTED` stage recorded before
the backtest), and an accident is not a method.

## 2. Method

Three auditors each took a set of records and, for every **normative** claim - a sentence asserting
that the platform, the client or a test *does* something - had to reach one of three verdicts:

- **verified**, naming the implementing file and, where one exists, the test that holds it;
- **not found**, naming the searches run and the absence of implementing code;
- **contradicted**, quoting both the claim and what the code does instead.

Aspirational, deferred and "what this does not claim" statements were out of scope, as was prose that
only describes intent. Each auditor was told that a false alarm costs more than a missed minor claim,
and that "the code has a function with a similar name" is not verification.

Coverage: `W0-01`, `W0-02`, `W0-03`, `W4-01`, `W5-01`, `W6-01`, `W7-01`, `W8-01`, `W8-02`, `W9-01`,
`W10-01` - roughly 320 normative claims, of which about 295 were verified as written.

## 3. What the audit found

Twelve claims were contradicted by the code, one was not implemented at all, and - the most useful
category - five were true when written and had gone stale as later waves moved the ground under them.

**Real defects in delivered behaviour** (fixed in the same stretch):

1. *The product error taxonomy never reached a surface.* `api/error_handlers.py` writes the code,
   family, severity, recoverability, message key, action key and correlation id at the top level of
   the body; the transport kept only `detail`, so every failure - a 403 `entitlement_denied` included
   - was presented as a generic SYSTEM fault and the correlation id a user is told to quote could
   never appear. (`W8-01` section 2, section 3 rule 1; `W7-01` section 5.)
2. *46 catalogued error codes reached users as raw keys.* The catalogue emits
   `errors.<code>.message` / `errors.<code>.action` for every catalogued code and neither locale
   defined one, so `t("errors.entitlement_denied.message")` rendered the literal key - exactly what
   `W8-01` promises never happens. (`W8-01` section 2, section 3 rule 4.)
3. *The `unmeasured` data-product state was unreachable.* The client could classify "entitled but not
   measured", but the catalogue gave every entitled product a provenance block even with no runtime
   database to measure with, so a row printed `0` for a product nobody had counted - the
   zero-that-reads-as-empty the same section forbids. (`W4-01`, catalogue client-consumer section.)
4. *A blocked research run carried its profile unqualified.* `PROFILE_STAGES_NOT_REACHED` was applied
   on the happy-path exit only, so the three early `BLOCKED` returns said nothing about the pipeline
   they never entered - the label was least trustworthy exactly where it was most load-bearing.
   (`W7-01` section 15.)
5. *Deep links refused an authority parameter in the query but never looked at the fragment*, so
   `eurogas://market#role=ADMIN` opened with the claim silently dropped.
   (`W10-01` section 4.)

Two further failure paths were found while auditing the envelope's reach, and are fixed with it
(they are the same defect: a failure a user meets, answering with less than the product promises):

- *The framework's own 422* for a body that did not match the model answered with a bare
  `{"detail": [...]}`, so the caller's input error read as an unclassified SYSTEM fault; a
  `RequestValidationError` handler now adds `validation_failed` beside the unchanged list.
- *The origin/CSRF guard's refusal* carried no correlation id and no taxonomy at all, because that
  middleware sits outside the request-id layer; it now builds the envelope, generates an id when the
  request never got one, echoes it on `X-Request-Id`, and its two codes are catalogued as AUTH.
- The job re-run fitness test asserted a hard-coded property back to itself and so could never fail;
  it now holds the *derivation* (the answer is a property of the record, not a per-kind field), which
  is the assertion with teeth, and the schema test beside it remains the real gate.

**Claims that overstated what is guarded or delivered** (corrected in the record, one carried to the
owner):

6. *"Every direct provider invocation" is re-authorised.* The caller-driven routes are; the deployed
   `monitoring-worker` is not, and has no caller identity to bind to. This is a design question about
   service identities, so it is recorded as **D7** rather than patched silently. (`W0-03` C8.)
7. *The `SNAPSHOT` job family was tracked.* The `JobKind` member and its re-run contract existed;
   no path created such a row. `POST /api/analysis-snapshots` now does. (`W8-02` section 7.)
8. *The prune script printed the oldest instant still represented.* The summary carried it; nothing
   printed it, so "0 rows deleted" could not be told apart from "this table is empty".
   (`W8-02` section 6.)
9. *`COPILOT_BOUNDARY` is derived from `AI_INVARIANTS` rather than restated.* Six of eight entries
   were; two were literals. All eight are derived now, and a test fails if one stops being.
   (`W7-01` section 6.)
10. *The migration "actually applying on SQLite" was verified.* No test read revision `0035` at all;
    the endpoint suite builds its schema with `Base.metadata.create_all`. `W6-01` now names the real
    test, which exists. (`W6-01` section 5.)
11. *"No unmounted component" closes the terminal half of C11.* The scan passed; the conclusion did
    not, because two of the references are tests reading the file's text.
    `StrategyShadowRunTerminal.tsx` (838 lines) still has no mount site. (`W0-03` C11.)
12. *The client API census (131 / 21 / 52).* Re-measured at 134 / 20 / 51, and its list still named
    `invokeCapability` as surfaceless after the Wave 7 slice had called it from the agents workspace.
    (`W0-03` C11, D3.)

**Claims that had simply gone stale** (corrected where they are read as current state): the register's
C3 ("Wave 2 was not entered - HELD", contradicted by its own C6 row); the Wave 0 gate row's
"5 primaries" (six since Wave 3); `W4-01`'s "ten declared products" (nine), its strategy-run citation
row (the run row has no citation column - the job carries it) and its "client: unchanged" line;
`W5-01`'s 175-path bound (178 today) and a test count; `W6-01`'s `DB_SCHEMA_REVISION` value (the head
moved to `0036_job_records`); `W9-01`'s "no deep link changed" (C10 changed one resolution) and its
palette bullet (the AI actions it says are withheld are offered, deliberately, since Wave 7);
`W10-01`'s diagnostics-panel location (the runtime page's governance view, not its readiness view) and
its notification-copy bullet, which is contract rather than delivered behaviour and now says so.

## 4. What was *not* changed, and why

- **`W0-01` and `W0-03` section 2 are historical records pinned to a HEAD.** They are left as written;
  a note at the top of the inventory says to read it as a baseline, and the corrections live in the
  register (which is the current-state document). Rewriting a pinned review record to match today's
  tree would destroy the evidence it exists to be.
- **`W0-03` section 10's counts** are likewise kept as the Wave 0/1 delivery evidence, with a sentence
  saying they are historical, because a count is evidence only of the tree it was measured on.
- **The two findings that need a decision** - the unmounted terminal and the client methods without a
  caller (C11/D3), and the headless worker's provider authority (D7) - are recorded with their options
  rather than resolved. Nothing here presumes an answer.

## 5. Verification

- The gates that would have caught the two largest findings are new and run with the suite:
  `tests/contract/test_error_vocabulary_coverage.py` (every catalogued code has text in both locales,
  the locales differ, the checked keys are the ones `error_payload()` emits, and the client's
  `ApiErrorBody` reads the field names the envelope writes) and the envelope assertions in
  `clients/web/tests/errorPresentation.test.ts`.
- `tests/unit/test_decision_case_migration.py` applies revision `0035` for real, closing the gap the
  audit found in `W6-01`'s verification list.
- `tests/integration/test_agent_orchestrator.py::test_a_blocked_run_also_qualifies_the_profile_it_carries`
  drives the plan-validation block and asserts the warning is reported *and* persisted.
- `tests/unit/test_job_retention.py` asserts the prune script prints what the window still represents.
- `clients/web/tests/copilotActions.test.ts` reads the `COPILOT_BOUNDARY` declaration and fails if any
  entry stops deriving from `AI_INVARIANTS`.
- `clients/web/tests/workstation.test.ts` refuses every declared authority parameter in the query, in
  the fragment, and in both at once.
- `tests/api/test_data_platform_api.py` pins both provenance shapes (no block when unmeasurable, a
  real `0` when measured) and the `SNAPSHOT` job row.

## 6. Limits of this audit

- The verdicts are the auditors' and the integrator's reading of the code, not a proof; each finding
  above names the file it rests on, so a reader can disagree with any of them.
- Only the records listed in section 2 were audited. The V2 pack's numbered specification documents
  (`02_ARCHITECTURE_CONSTITUTION.md` and the rest) were read for context, not audited claim by claim.
- Nothing was verified against a live PostgreSQL deployment, a packaged desktop build, an external
  identity provider or a real UAT, because none exists in this environment. Claims that depend on
  those remain verified only as far as the fixtures go, which is what the execution checkpoint's
  "not run and not claimed" list already says.
