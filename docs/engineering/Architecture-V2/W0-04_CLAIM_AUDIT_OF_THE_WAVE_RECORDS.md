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
- Findings 8-11, added as the D3 surface slices were built, each have a gate rather than only a fix:
  `clients/web/tests/localeDistinctness.test.ts` (no value may be identical in both locales unless it
  is declared with its reason), `clients/web/tests/referenceNetwork.test.ts` (an unconfigured runtime
  database is not an empty register, a bound is not a total, and a row that declares no capacity is
  not a zero), `clients/web/tests/routeCostWhatIf.test.ts` (the client sums nothing and the netback
  carries the engine's own cost) and `tests/unit/test_runtime_db_validation.py` (an unreachable
  database is reported as not inspected, with the driver the URL selected named).

## 6. What running, rather than reading, then found

The audit above reads code against claims. Four further findings came from *executing* what the
checkpoint had recorded as unrunnable, after noticing that this environment does have a Docker daemon
and a running PostgreSQL 16 container:

1. **The migration preflight crashed on the current tree.** `scripts/ops/migration_preflight.py`
   carried a second, private copy of the migration-scan logic that
   `scripts/release/release_metadata.py` had already fixed, and it kept the bug that copy had fixed: a
   wrapped docstring line beginning with the word `revision` was read as the identifier assignment, so
   `alembic_head()` raised `IndexError` on the tree containing `0035_decision_cases` (whose docstring
   wraps exactly there). An operator running the preflight - the script whose entire purpose is to run
   before a migration - got a traceback instead of a report. There is one implementation now, it
   resolves the head by the `down_revision` chain rather than by sorting identifiers, it refuses a
   branched history instead of silently picking a leaf, and `tests/unit/test_migration_preflight.py`
   holds it (including the prose pitfall, in the shape the real tree has).
2. **The suite depended on the machine it ran on.** Roughly twenty suites assert what the platform does
   with the store *they* configure (a SQLite fixture, or none), and they read the ambient environment:
   with `RUNTIME_STORE_DATABASE_URL` pointing at a deployment, a route that must answer
   `runtime_db_not_configured` answered from the live store, and a degradation test asserted a warning
   that never appeared. `tests/conftest.py` now removes the ambient runtime-store variables for every
   test outside `tests/integration` (through `monkeypatch`, so the live suite still gets them), which
   is the policy `docs/operations/LIVE_POSTGRESQL.md` already stated - "default validation remains
   DB-free" - enforced rather than assumed.
3. **The integration suite could not be run twice.** One test archived a row under a fixed
   `raw-smoke-0001` id, so a second run against a persistent database failed with a duplicate key and
   read as a broken archive; CI's throw-away service container hid it. The archive is append-only, so
   the test writes a fresh id per run instead of deleting anything.
4. **The repository's own gate was red.** `ruff check .` is declared in
   `docs/engineering/CODING_STANDARDS.md`, `docs/operations/VALIDATION.md` and
   `.github/workflows/ci.yml`, and reported ~409 findings on this tree: the style bulk in the earlier
   `.automation/` harness, and real ones in product code - an undefined name in a type annotation that
   `from __future__ import annotations` made invisible at runtime (`analysis.py`), an unused variable,
   an unused import, a `zip()` without `strict=`, and a test whose completeness assertion was a bare
   comparison (`set(grouped) == set(ErrorFamily)`) that could never fail. All are fixed;
   `.automation/` is excluded with that reason written in `pyproject.toml`, FastAPI's parameter
   functions are declared immutable calls so `B008` stops mis-reading the framework idiom, and
   `ruff check .` is clean.

What that execution bought, beyond the fixes: the migration chain applied to a real PostgreSQL 16
(`0033` → `0036`), the whole suite green against a scratch database at head (1807 passed, 1 skipped,
including the 16 store-gated tests), and the automated backup/restore drill passing with real data
(52.5 MB dump, restored at head `0036_job_records`, 80,545 ingestion runs, API smoke 200).

Two more findings came out of the browser sweep, which needs a seeded runtime, a dev API, Vite and
Playwright and had never been run here either:

5. **The sweep could not start a research run, so the CI browser job was red.** It clicked
   `button.button.primary` inside the agents view - a class that button never had, because Wave 9
   moved every primary action into the workspace header's primary slot. The click found nothing (or
   a disabled button) while a second 30-second timeout on the expected response raced it, so the run
   failed as a timeout with no explanation. The slot now marks what it renders (`data-primary-action`,
   applied by the component that owns the slot rather than by each call site), the sweep waits for
   the action to be usable and reports the blocker the button shows if it never is.
6. **Three workspaces rendered two top-level headings.** `strategy`, `research` and `agents` are
   declared `local-tabs` (the shell renders the page heading) *and* render a `WorkspaceHeader` of
   their own, which also rendered one - so every page in those three workspaces had two `h1`
   elements in every language and at every viewport. No source-text test could see it; the sweep
   counts headings per rendered page. The registry stays the one owner of the rule:
   `workspaceHeaderTitleLevel(page)` decides the level, and a workspace heading on a `local-tabs`
   page is a section heading under the shell's page title.

With both fixed, the sweep passes end to end (`ok: true`, 96 checks, 0 axe violations, 0 horizontal
overflow) including the agent-research interaction.

7. **The gates the programme records as green were red on `main`.** Checked against the GitHub API
   rather than assumed: the last successful `CI` run before this stretch was **351** (`7a07b965`,
   2026-09-16) and runs **352–446** all failed - two jobs, `validate` (the `ruff check .` gate, ~409
   findings) and `Browser acceptance` (the stale primary-action selector and the duplicate heading
   above). Every slice in that window was recorded as "gates green"; the record was describing the
   author's local run of a *subset* of the job, and nothing reconciled it with CI. Run **447** at
   `0c34959` is the first green run since: `validate`, dependency audit, PostgreSQL integration, Web
   build/tests and browser acceptance succeeded together. The lesson is not "run the tests" - they
   were run - it is that a gate is green only in the place it is enforced, and a document that says
   otherwise is a claim like any other.

8. **A declared locale was, in part, the English text.** Found while finishing the D3 slice that
   touches the agents workspace: 24 `agents.*` keys carried their English value as the Chinese
   value, so a Chinese user read the entire agents workspace - its title, tabs, boundary statement,
   objective field and every run column - in English. Every existing locale check passed, because
   they assert key *parity* and duplicate keys, and none of them asked whether a value had been
   translated; the execution checkpoint's own line that "the vocabulary is distinct per locale" was
   therefore overstated for those keys (it held for the vocabulary each stretch added, which is what
   it was written about, and not for the file as a whole). The 23 prose keys are translated now, and
   the 12 values still identical across locales - `SSO`, `AI`, `LLM`, `KPI`, `LNG`, `GIE LNG`,
   `UTC`, `Alembic`, `Eurogas Nexus`, `English`, `中文` and one identifier shape - are acronyms,
   proper nouns and language names, i.e. the same words in both locales. `localeDistinctness.test.ts`
   now fails on *any* value that is the same in both locales unless it is declared with its reason,
   so this cannot arrive silently again. The lesson repeats this audit's other one: the checks that
   existed were about the shape of the file, and nobody had asserted the property that mattered.

9. **The census that found the uncalled methods was itself fooled by an unrelated identifier.**
   Found while finishing slice D: the measurement behind C11/D3 counts a method as "mentioned" when
   its name appears anywhere outside `client.ts`, and `netback` appears twice without any caller -
   once as a `RouteRecommendationDTO` field and once as a UI string in the scenario workspace. So
   `api.netback`, which had no more of a surface than `api.routeCost` beside it, was never in the
   never-mentioned set at all; the audit's own instrument was measuring a substring, not a call. The
   same weakness made the "mentioned but never invoked by name" list the more honest of the two
   numbers, which is why both are reported. With slice D delivered the never-mentioned set is empty
   and the count that matters is 30 methods reached only through the loader seam - and each of those
   was checked by eye against the store that owns the seam.

10. **The client's envelope type asserted more than the backend sends.** `ApiMeta` declared
   `source_references` and `warnings` as **required**, while the research compute routes return a
   meta of `{research_only, human_review_required, decision_context}` - so a surface reading
   `meta.source_references` was reading a field the response did not contain, and TypeScript could
   not say so. The same envelopes put the engine's own `source_references` inside `data`, which is
   where the route-cost panel now reads provenance from. Four route modules send
   `meta.missing_inputs` (the reference-network reads, the optimiser, the research computes, the
   sources read) and the client declared nothing, so the one signal that separates *nothing was
   measured* from *measured and empty* was invisible to every surface. All three fields are now
   declared honestly (the first two optional) and the two call sites that assumed them were fixed.
   A related record rather than a fix: `GET /api/contracts/capacity` maps the column
   `capacity_mwh_per_day` into a payload field named `capacity_boe_d` while the row's own `unit`
   says `MWh/d`. The unit is the explicit statement and the surface renders it verbatim; renaming a
   pinned payload field is a contract change, so the wart is recorded here instead of being fixed
   quietly.

11. **The runtime-DB validator reported an unreachable database as 93 missing tables.** Found by
   running the documented live-validation command with a bare `postgresql://` URL - the scheme most
   operators would type, and one that makes SQLAlchemy select psycopg2, a driver this project does
   not depend on. The connectivity check failed with `ModuleNotFoundError`, and the report then
   printed every required table as missing, because `missing_tables` was initialised to the full
   required set and never cleared. Nothing had been inspected, so nothing had been shown to be
   missing; it is the same defect the platform refuses to make about data (*unmeasured* rendered as
   *zero*), in the operator's own diagnostics. The report now carries
   `table_inspection: "not-performed"` with `missing_tables: null` when the database does not
   answer, names the driver the URL selected and the `postgresql+pg8000` scheme this project uses,
   and `docs/operations/LIVE_POSTGRESQL.md` states the scheme where it previously named no driver
   at all. The stale evidence block in that document (`alembic_revision=0013…`,
   `required_tables=33`) was also refreshed from a real run: `0036_job_records`, 91 tables, none
   missing, no warnings.

12. **A slice of the D3 decision went red on CI while every local gate was green, and the cause was
   a race this audit's own acceptance check had.** Run **455** (`f03c403`, the agents/research
   catalogue slice) failed `Browser acceptance` alone - `validate`, the dependency audit, the
   PostgreSQL integration job and the web-client build all passed - and the check that failed was
   the header preferences assertion, which reads `document.activeElement` immediately after
   `Escape` while the menu moved focus back to its trigger on the next animation frame. On the
   machine used here the same check failed twice in a row; on CI it failed once and passed on the
   next commit, which is what a race looks like. Both halves are fixed: the menu focuses the
   trigger synchronously before closing (the trigger is always mounted, so closing afterwards
   cannot drop focus into the body), and the sweep waits for the outcome within a bounded time
   instead of assuming it happened in the same tick, so a legitimate frame-deferred focus no longer
   reads as a defect. **The fix then broke two more runs, for a reason worth recording:** the same
   commit changed the behaviour that `workspaceHeader.test.ts` pinned
   (`requestAnimationFrame(() => triggerRef.current?.focus())`), the client suite had been run
   *before* that edit rather than after it, and runs **457** and **458** failed the `Test Web
   client` step on an assertion about a shape the product no longer had - the product change was
   right and the test that pinned the old shape was not updated in the same pass. Run **459**
   (`4828983`) is green on every job. This is finding 7's lesson arriving twice in one stretch: the
   local run and the enforced gate disagreed, and only the API could say so; and a local run is
   evidence for the tree it ran on and no other.

13. **A contract test can outlive the surface it describes, and keep passing.** Five contract tests
   read `StrategyShadowRunTerminal.tsx` as their subject, and one of them -
   `test_strategy_bar_minutes_is_operator_selectable` - asserted that an operator can choose a bar
   size of 1, 5 or 15 minutes. Nothing rendered that component, so the claim was never true of the
   product: the scenario builder declares 5 for every request and no mounted surface changes it. The
   tests were green for as long as the file existed, which is the failure mode this audit keeps
   finding in a new shape - not a stale document, but a *passing gate* whose subject nobody could
   reach. When the owner retired the terminal, the five were repointed at where the behaviour now
   lives (`app/model/shadowRunPresentation.ts`, `StrategyShadowRunDetail.tsx`, the design spec) and
   the bar-size contract was rewritten to assert what the product does, with the missing operator
   control recorded as a gap in `W0-03` rather than implied by a test. The same sweep found that
   roughly 140 locale keys are now unreferenced - about forty of them the retired terminal's, the
   rest older (`sources.*` 41, `glossary.*` 10, `panel.*` 9) - measured by literal references plus
   the template bases that build keys dynamically. They are recorded rather than deleted: a locale
   file is a vocabulary rather than a claim, and a mass deletion needs that same dynamic-key audit
   applied to every family first.

## 7. Limits of this audit

- The verdicts are the auditors' and the integrator's reading of the code, not a proof; each finding
  above names the file it rests on, so a reader can disagree with any of them.
- Only the records listed in section 2 were audited. The V2 pack's numbered specification documents
  (`02_ARCHITECTURE_CONSTITUTION.md` and the rest) were read for context, not audited claim by claim.
- Nothing was verified against the **production** deployment, a packaged desktop build or an external
  identity provider: the PostgreSQL evidence above comes from a local container, the browser UAT job
  needs Playwright, and the desktop bundle needs a Rust toolchain. Claims that depend on those remain
  verified only as far as the fixtures and the local services go, which is what the execution
  checkpoint's "not run and not claimed" list says.
