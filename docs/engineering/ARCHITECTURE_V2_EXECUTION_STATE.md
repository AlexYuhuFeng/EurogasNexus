# Architecture V2 Execution State

Last updated: 2026-10-06
Audit baseline: `e911fae`, equal to `origin/main` at audit start. Historical slice records below do not constitute current production approval.

## Current work

### Delivered notice integrity acceptance (2026-10-06)

Previous turn made progress: cc16f55 delivered Python texts in the API image.
DeepSeek added a read-only verifier using the shared lock inventory and path
helpers. It checks exact package coverage, lock digest, complete status,
counts, safe recorded paths, file hashes/sizes and unrecorded files. Release
container acceptance executes it in IMAGE@DIGEST with network disabled on
amd64 before writing G19 PASS. Evidence explicitly distinguishes arm64 manifest
presence from executed amd64 validation; no arm64 execution is claimed.

Parent reviewed code/workflow and independently ran 16 focused tests (one
Windows privilege skip), Ruff and diff checks. Rebuilt the local image and
executed its verifier as the image's default user with --network none:
30 locked packages and 34 files verified. Local image manifest list digest:
sha256:f12a2b819f896459f59c67f8536fc323b07065938f3e5c7b9b11bc5c9a543a28.
No image was published and no running service changed. Remote release-job
execution is pending. This does not waive r-efi findings or establish legal
clearance; non-Python notices, native/multi-platform delivery and business/HMI
acceptance remain incomplete.

### Python notices delivered in API image (2026-10-06)

Previous turn made progress by verifying runner collection. DeepSeek now wired
the existing collector into the final API image stage, after runtime dependency
and project installation. Incomplete collection fails the build. Original texts
and their lock-bound manifest ship at
/usr/share/licenses/eurogas-nexus/python-license-texts. Operator EN/CN and
supply-chain documentation describe scope and remaining obligations.

Parent verification: 45 focused tests passed, two Windows privilege skips;
Ruff passed. Unlike the worker sandbox, parent Docker access succeeded.
Built eurogas-nexus:notice-verification locally, without publishing or altering
running services. Image manifest list digest:
sha256:d2a645661fd901062fa45c9a913f778727ad807c39d784346ea2bbc2ede3710f.
A network-disabled temporary container running as default UID 999 read all
34 files for 30/30 packages; every hash/size and the shipped runtime lock digest
matched. No unresolved collection entries. The verification container exited
and was removed. This is local single-platform evidence, not multi-arch release
acceptance or legal clearance. Rust/Node/native/OS notices, r-efi review,
customer-artifact redistribution review and business/HMI acceptance remain open.

### Runtime notice collection verified on runner (2026-10-06)

Previous goal turn made progress: fab7c38 added isolated CI collection.
Run 37400746982, job 112067149706, now succeeded on that exact commit.
Downloaded eurogas-nexus-python-license-texts to ignored local evidence path
output/runtime/ci-license-evidence-37400746982. Manifest reports 30/30 locked
packages, 34 files, zero unresolved/incomplete packages and no global problems.
Parent independently verified all 34 copied-file SHA256 hashes and byte sizes.
The runtime-lock digest agrees with the current repository:
aa8d28434e737bef37fc31bea3e9b46d1d0174cd6a15c32d7731a1800c7a6058.

This closes runner collection verification only, not legal clearance or
artifact-level notice delivery. Web and PostgreSQL jobs passed; validate and
browser jobs were still running at inspection; dependency audit failed.
Do not infer whole-run success. Next implementation should bind complete
notice evidence to the exact customer build and include it in delivered
artifacts with tamper/mismatch tests. The r-efi review and non-Python/native
license coverage remain open, as do business and visual acceptance gates.

### Isolated runtime license evidence in CI (2026-10-06)

Verified baseline 68b3365 and fetched origin. CI 37396728223 passed validate,
browser acceptance, PostgreSQL integration and web build. Dependency audit
failed only on the existing r-efi 5.3.0/6.0.0 declared-license findings; no
waiver or legal determination was made.

DeepSeek added an independent main-push CI evidence job: hash-install the
runtime lock in a throwaway venv, collect texts against its exact purelib,
and upload even incomplete reports without masking failure. Existing pinned
actions are reused. Release publishing and required acceptance jobs are
unchanged; evidence collection is not redistribution clearance.

Parent reviewed workflow, tests and docs; 38 focused tests passed with two
Windows symlink-privilege skips, and focused Ruff passed. Live runner evidence
for this new job remains pending. Next: inspect its uploaded manifest, review
remaining license findings, then integrate verified notice evidence into
customer artifacts. Business, populated-screen and native-delivery gates
remain open; no commercial approval is asserted.

### Live Rust findings and Python notice evidence (2026-10-06)

Previous turn was progress plus a verified wait. Run `37363927598` has now
executed dependency job `111944603619`: toolchain setup succeeded and all 434
third-party lock identities were audited. 432 passed declared-term checks;
r-efi 5.3.0 and 6.0.0 failed the existing conservative policy because their
expressions are `MIT OR Apache-2.0 OR LGPL-2.1-or-later`. This is a review
finding, not proof that LGPL obligations necessarily apply under every choice.
Do not waive the gate or choose a licensing alternative without documented
review of actual terms/artifacts. No exception was added. The same run's
validate job found an import-order error in the Rust test; parent fixed it.

DeepSeek added an optional Python license-text collector using exact runtime
lock identities, installed METADATA/RECORD, recorded License-File declarations
and bounded legacy basenames. It copies original bytes with hashes, refuses
path escapes/reparse points and existing output directories, and preserves
explicitly incomplete reports. Parent excluded code/executable suffixes from
legacy basename matching. No publishing integration or legal approval claimed.

Independent tests: 103 passed, two Windows symlink-privilege skips; Ruff passed.
Actual local collection at `output/runtime/python-license-review-20261006`
collected 30 files for 27/30 locked packages and returned incomplete. Installed
greenlet 3.5.6, SQLAlchemy 2.0.54 and uvicorn 0.53.0 differ from lock versions
3.5.5, 2.0.52 and 0.52.4 respectively; no substitution was accepted. Existing
runtime environment was not modified. Next: collect in a freshly locked release
environment, independently review licensing alternatives for both r-efi versions,
then integrate complete notice evidence into actual customer artifacts. Keep
all unresolved business/visual/native delivery gates open.

### Live Rust CI setup repair; runner queued (2026-10-06)

Previous turn made progress by implementing the Rust gate but had no live
Cargo evidence. `706f721` now runs that same locked metadata check in ordinary
CI dependency-audit, without publishing a release. Actual run `37363241489`
revealed the pinned dtolnay action failed because its required toolchain input
was missing. The license command was skipped: this was not a license verdict.

Parent repaired all four Rust setup sites in CI/release, supplying the existing
1.94.0 repository pin explicitly. `69a49a0` includes a structural regression
ensuring action inputs and rust-toolchain.toml agree. Independent focused Rust
gate/release-engineering tests: 92 passed. No dependencies, lock versions or
license policy relaxed. This small workflow repair was implemented directly.

Replacement run `37363927598`, tested SHA
`69a49a09fe90e2f7c8479254298b65c80ff451e1`, is verified queued after two
four-minute waits. Dependency job `111944603619` has not run; preserve this
handle and inspect it next rather than dispatching a duplicate. Local Cargo
remains unavailable. Live Rust licence coverage is still unverified, as are
native installation, full notices and populated payment-screen acceptance.
No overall commercial approval is asserted.

### Rust metadata license gate; live collection pending (2026-10-06)

Baseline `3065dfd` passed CI run `37359921913`; previous turn made progress
on client lock enforcement. DeepSeek added a release dependency-scan gate using
Cargo metadata with --locked, format version 1 and --all-features, matching the
existing structured lock inventory by exact name/version/source. Missing tools,
timeouts, failed/malformed/incomplete collection, duplicate/mismatched identities
and missing/restricted license declarations fail. No dependency or lock changed.

Parent required a second worker pass: only the root package matching the audited
Cargo.toml name/version and exact resolved manifest path may be excluded;
workspace membership or a familiar project name cannot exempt a third party.
Raw Cargo failure output is withheld to avoid disclosing private source details.
Parent also made unreviewed git/path/alternate-registry provenance a failure,
not a warning-only successful exit. No licensing exception was granted.

Independent verification: 185 focused Python/npm/Rust audit and SBOM tests
passed; Ruff, diff check and Markdown links passed. Actual local Cargo gate
returned failure because Cargo is not installed, as designed. No live Rust
license audit, native build or artifact notice acceptance is claimed. Release
runner execution must supply that evidence; full license texts, bundled/native
and container components and artifact-specific redistribution review remain
open. Populated business-workflow visual gates also remain open. The overall
commercial-delivery objective is not complete.

### Client lock license gate (2026-10-06)

Baseline `e7a0d2f` passed CI run `37358375534`; prior turn made progress on
Python license metadata detection. DeepSeek added repeatable `--npm-lock`
mode to the existing audit, reusing the SBOM npm inventory reader and restricted
term policy. Both exact client locks are now audited in CI dependency-audit
and release dependency-scan before its evidence upload; release assembly already
requires that job. Missing/malformed locks, missing or non-string declarations,
restricted terms and file-only references fail. Parent additionally rejected
unknown placeholders and custom LicenseRef references, with six regressions.
No licence exceptions, dependencies or application behavior changed.

Independent verification: 115 audit/SBOM tests passed; Ruff and actual both-lock
command passed (98 third-party entries, two project roots excluded). Coverage
includes dev/optional lock entries and is not shipped-artifact proof. Python
unknown-license behavior is unchanged. Rust, vendored/native/container packages,
full license texts and customer-artifact notice review remain open. Do not
interpret a clean metadata gate as commercial or redistribution clearance.
Populated-payment browser acceptance remains open under the earlier launch
restriction. Next: artifact-specific Rust/license-text evidence and release
notice delivery, while preserving all business acceptance gates.

### Python license-audit metadata coverage (2026-10-06)

Baseline `69d1b2d` passed CI run `37356928297`; previous turn made progress
through fixture safety repairs. With isolated browser startup still blocked,
parent inspected an independent delivery gate. The Python license scanner
ignored License-Expression and could report success for an empty scan. DeepSeek
replaced line parsing with the standard-library email parser, applied modern
expression precedence, included all License classifiers and rejected empty,
missing, unreadable or structurally malformed metadata. Existing restricted-term
and unknown-license review policies were preserved; no legal exception or
dependency was approved. Parent checked against the linked PyPA specification.

Independent validation: 26 dependency-audit tests and 45 SBOM tests passed;
Ruff passed. Local scan inspected 63 installed Python distributions without
detecting restricted terms. This is not the locked Linux release environment
or an artifact-specific legal review. Worker also reported 234 security tests
passing; parent did not rerun that entire suite. No runtime/DB/UI change.

Remaining delivery gaps: scanner does not cover Node/Rust or full license texts,
vendored/native/container dependencies. Generated THIRD_PARTY_NOTICES is only
a lock inventory, explicitly without license texts; unknown licenses remain
review-required, not approved. Next independent release work should close
artifact-specific license/notice coverage without fabricating clearance or
changing licensing terms. Populated-schedule visual acceptance remains open.

### Fixture safeguards and readiness-claim correction (2026-10-06)

Baseline `c0a8397` passed CI run `37355393169`. Previous turn was progress:
populated fixtures were seeded and verified in isolated PostgreSQL. This turn's
attempt to start a separate authenticated API/web instance was rejected by
execution policy before command execution. Ports 8001/3001 have no listeners;
do not assume an isolated identity or server exists. No alternate launch path
was attempted. Populated EN/ZH browser acceptance remains open.

Independent review found the fixture's environment blacklist did not enforce
its development/test-only claim. DeepSeek replaced it with an explicit allowlist
(unset/blank also refused), tightened ownership to the two exact IDs and added
sanitized missing/invalid-driver handling. Refusal tests prove no engine/session
creation, known driver failures redact secrets, and programming defects remain
visible. Runbook cleanup now uses exact IDs, not broad prefix deletion. Parent
corrected stale exit-code wording and the commercial backlog's claim that all
internal work was complete; historical implementation labels are not customer
acceptance evidence.

Independent selected tests: 133 passed, three skipped; Ruff, diff check and
all 270 Markdown link checks passed. No product runtime or DB mutation this
turn. Retain the isolated fixture database for authorized visual QA when the
launch restriction is resolved; do not bypass that restriction. Meanwhile the
business acceptance matrix and pilot blocker register contain independent
implementation/release work, so this does not block the overall programme.

### Isolated populated-payment fixtures (2026-10-06)

Previous turn made evidence progress by calibrating responsive viewports, but
did not complete populated-schedule acceptance. DeepSeek now added opt-in
`scripts/uat/seed_declared_payment_uat_fixture.py`, focused tests and the linked
`docs/uat/DECLARED_PAYMENT_VISUAL_ACCEPTANCE.md` runbook. Two clearly synthetic
contracts cover explicit dates, unresolved anchors, mixed directions and long
evidence using the canonical domain and existing repository fixture path.
No application UI/API, authority, numerical calculation or dependency changed.
Dedicated PostgreSQL naming, explicit URL, acknowledgement, schema and existing
contract guards prevent ordinary runtime seeding; customer bundle excludes UAT
scripts. Parent removed argument echo and corrected post-commit failure claims.

Independent checks: 89 fixture/packaging tests passed, three skipped; Ruff and
diff checks passed. Created disposable `eurogas_uat_payment_visual_20261006`,
migrated through 0038, seeded twice and verified two rows with two declarations.
Existing `eurogas_nexus` remains one contract with zero declared schedules.
Initial driver attempts failed before connecting; use the installed `pg8000`
driver for local execution. The isolated database is retained for visual QA;
no isolated API/browser identity has yet been started/created. Next: run the
normal authenticated app against that isolated database on separate ports,
verify both schedules in EN/ZH at measured desktop/mobile widths, then remove
the disposable environment. Seeding is not UI or commercial acceptance.

### Responsive viewport calibration and mobile empty-state check (2026-10-05)

Baseline `31c7889` remains equal to fetched origin/main and passed CI run
`37287258664`; no active DeepSeek worker or autonomous supervisor was found.
The authenticated browser session still renders the existing stored contract.
Calibrated this browser's viewport override against actual `innerWidth` and
`innerHeight`: requested 2808x1950 yields 1440x1000 CSS pixels; requested
761x1646 yields 390x844. This factor is session-specific, not an application
breakpoint rule. Always measure actual dimensions before asserting acceptance.

At measured 390x844, visually inspected the persisted-null payment panel,
estimate disclaimer and validation list: text wraps without overlap; root
scroll width is 382 pixels, within the viewport. Desktop DOM measurement at
1440x1000 places the payment panel within the viewport, but its screenshot did
not expose the lower panel, so desktop visual acceptance remains open. Reset
the temporary override. No application code, runtime records or permissions
changed. Next bounded task: isolated populated-schedule fixtures and EN/ZH
visual checks, including desktop panel capture; retain all existing open gates.

### Payment-panel browser inspection recovered (2026-10-05)

Baseline `a5bc752` passed CI run `37261964065`. A fresh authenticated browser
session successfully displayed the new panel in Portfolio > Resources >
Settlement and cash. Confirmed distinct unsaved-draft and persisted-null
messages by loading the existing preview contract from Library. The stored
view explicitly separates declared schedules from legacy lag-based estimates;
no payment schedule was inferred and no business record was changed.

Screenshot inspection confirmed the persisted-null panel and its estimate
disclosure were readable without overlap at the observed 738 CSS-pixel width.
Requested viewport overrides did not match browser-reported dimensions
(1440x1000 reported 738x513; 390x844 reported 200x433), so these observations
do not constitute desktop/mobile breakpoint acceptance. Override was reset.
Populated schedules, EN/ZH visual parity and intended responsive breakpoints
remain open. Use isolated fixtures for declared schedules; do not add invented
terms to the existing preview contract. Earlier monitoring timeouts remain an
unresolved investigation, not a demonstrated backend outage. Next: establish
reliable CSS viewport sizing and complete that isolated visual acceptance.

### Payment-rule presentation labels (2026-10-05)

Baseline `898c2f2` passed CI run `37224098361`. DeepSeek replaced raw category,
anchor, day-kind and roll-convention codes in the read-only payment panel with
exhaustive EN/ZH label mappings and removed the duplicate direction fact row.
Decoder and presentation share the reviewed client vocabulary. Stored values
and evidence remain verbatim; no API, math, permission or database change.

Independent full web suite: 861 passed, three skipped. Production build passed
with the existing dynamic-import warning. Parent reviewed the mapping and
decoder changes; unsupported values never borrow another known label. Real
browser populated-schedule and responsive acceptance remain open, as recorded
below. Next work must prioritize that visual gate and recurring browser/read
timeouts rather than treating unit/build success as commercial readiness.

### Read-only payment-term UI implementation; visual gate open (2026-10-05)

Baseline `4a42df1` passed CI run `37204497285`. Parent restored the stopped
Vite preview at port 3000 and authenticated with the existing local UAT vault.
Inspected Portfolio > Resources > Library and Settlement and cash. The original
screen showed legacy lag/financing inputs without declared schedules. Existing
monitoring-alert, monitoring-summary and pipeline-health timeout banners also
appeared; their cause remains unresolved.

DeepSeek added read-only payment-term presentation within the existing settlement
section, EN/ZH labels, strict transport validation, distinct missing/null/malformed
states and reset handling for record/draft/identity changes. Existing save payloads
omit payment_terms and therefore preserve the server declaration. No date/cash
calculation, edit/clear control, backend change or new page was introduced.
Parent review required repair of permissive enum/field/date/bounds validation;
DeepSeek added exact shape and reviewed-value checks plus focused regressions.

Independent final web suite: 856 passed, three skipped; production build passed
with the existing dynamic-import warning. Before the validation-only repair,
59 documentation/client-surface/browser-path contract checks passed. Diff check
passed. No business records were mutated. Runtime remains PostgreSQL schema 0038.

Visual acceptance is NOT complete: browser interaction worked for the original
screen, but reload timed out before the newly implemented panel could be
confirmed. Do not claim desktop/mobile or populated-schedule screenshots passed.
Next: recover browser inspection, confirm the actual new panel in EN/ZH at
desktop/mobile widths, exercise declared and absent schedules in an isolated
fixture environment, and investigate recurring monitoring read timeouts.
Raw transport enum labels in the detail list also warrant trader-facing copy
review. This milestone is implemented and automated-tested, not release-approved.

### Authenticated PostgreSQL payment-term acceptance (2026-10-04)

Baseline `94f2180` passed CI run `37187187784`. DeepSeek added three opt-in
PostgreSQL-backed HTTP/TestClient tests and wired them into the existing
PostgreSQL CI job. Real database-backed identity keys exercise ANALYST/OPERATOR
set/preserve/clear, v1/v2 history, actor attribution, stale conflicts,
VIEWER/ADMIN-only denial and sanitized malformed-term refusals. No production
code or permission changed. Parent strengthened refusal comparisons to include
every persisted contract column.

Independent verification: initialized a separate disposable PostgreSQL database
through Alembic head; all three acceptance tests passed, including a rerun after
the assertion improvement. Initial teardown verification found zero contract,
revision, principal, key and audit rows. Removed the disposable database after
testing; the application's database was not used. Thirteen documentation/link
checks passed, as did focused Ruff. Same-commit CI remains pending.

These are authenticated in-process HTTP tests backed by real PostgreSQL, not a
live-network browser/persona walkthrough. Next: inspect the running contract UI
and implement coherent payment-term presentation there, preserving field-presence
semantics and explicit unresolved-date warnings. Date resolution, cash valuation,
revision lifecycle and full commercial trading journeys remain open.

### Backup restore and PostgreSQL revision rehearsal (2026-10-04)

Baseline `2ee5096` passed CI run `37172384085`. Parent restored the pre-0038
custom-format backup into a newly created isolated PostgreSQL database
`eurogas_restore_0037_20261004`, using `pg_restore --exit-on-error`. Restore
succeeded. Verified schema 0037, one contract, zero revisions and absence of
the new payment-terms column, matching the recorded backup baseline.

Applied Alembic 0038 to that restored copy, then independently ran all seven
opt-in tests in `test_contract_revision_capture_postgres.py`: seven passed,
with two existing deprecation warnings. This includes real PostgreSQL declared
term capture as v2 with prior v1 evidence preserved, alongside existing revision
idempotency/concurrency checks. Removed the isolated rehearsal database after
completion. The application's database remains at 0038 with one contract, no
declared terms and zero revisions; no synthetic contracts entered its resource
pool. The ignored local backup remains available.

This is a successful local restore-and-upgrade rehearsal, not a measured RTO/RPO
certification or a full customer disaster-recovery exercise. Authenticated live
set/preserve/clear and browser persona acceptance remain pending. Next: exercise
those workflows against an isolated authenticated test instance before adding
payment-term presentation to the existing contract workspace.

### Local schema 0038 rollout and persona reads (2026-10-04)

Commit `9de6b4d` passed CI run `37158444065`: PostgreSQL integration,
backend validation, dependency audit, web build and EN/ZH browser acceptance
at three viewports succeeded. Native desktop packaging was skipped.

Parent created a custom-format PostgreSQL backup in ignored local runtime
storage (`.automation/runtime/eurogas-before-0038-20261004.dump`); the archive
catalogue is readable (429 entries), but no restore rehearsal is claimed.
Applied the exact Alembic 0038 revision with a five-second database lock timeout.
The first command failed before connecting because the source import path was
missing; after setting the project source path the migration succeeded.
Verified schema 0038, one existing contract, zero declared payment terms and
zero captured revisions, matching pre-upgrade counts with no backfill.

No API listener was present on port 8000. Started the existing hidden local
launcher against the upgraded PostgreSQL store. All six local UAT identities
returned HTTP 200 from `/api/me`; contract reads admitted the multi-role,
ANALYST and OPERATOR accounts and refused VIEWER, REVIEWER and ADMIN-only
with 403. Permitted responses include `payment_terms`. Credentials remained
in the local encrypted vault. Authentication can update key-use metadata;
these checks performed no business-record mutations.

Next: authenticated live set/preserve/clear acceptance using explicitly labelled
test contracts, then payment-term presentation in the existing contract workflow.
No live mutation acceptance, local browser walkthrough, backup restore, payment
date resolution or cash valuation integration is asserted by this checkpoint.

### Payment-term persistence backend (2026-10-04)

Baseline `b8a875c` passed CI run `37139274490`. DeepSeek implemented nullable
canonical-text storage through expand-only migration 0038, field-specific
set/preserve/clear request handling, decoded contract reads and governed revision
capture. Terms produce v2 economic snapshots; NULL produces v1, including after
an explicit clear. Existing v1 evidence is never rewritten, and untouched legacy
rows gain no schema-only revision. Edit-token schema v2 covers the new carrier:
open drafts must reload after deployment; no old-token fallback is permitted.

Parent review found and closed an internal-helper corruption bypass: stored
terms must validate before either public or internal updates, even when clearing.
The regression test verifies corrupt evidence remains unchanged. Independent
validation: full backend suite 2813 passed, 30 skipped, two existing deprecation
warnings; focused payment integration 13 passed; web suite 842 passed, three
skipped; production web build passed with the existing dynamic-import warning.
Ruff and diff checks passed. No runtime migration or business mutation occurred.

Deployment remains gated on same-commit CI, especially the opt-in PostgreSQL
migration/capture suite. Local runtime is still on schema 0037: do not restart
the new backend against it before a reviewed backup and migration. The new DDL
unit test uses the repository's disposable SQLite test pattern, not a runtime
store and not evidence of PostgreSQL acceptance. No UI editing, date resolution,
cash valuation composition or lifecycle approval is claimed. Next: verify CI,
apply the reviewed runtime upgrade with backup, and validate authenticated
set/preserve/clear behavior before exposing payment terms in the existing UI.

### Revision v2 domain compatibility (2026-10-04)

Baseline `02c378e` passed CI run `37121199581`. DeepSeek added explicit v2
snapshot construction and strict version-dispatched decoding using the shared
payment-term model. Default construction and legacy mapping remain v1; pinned
v1 canonical bytes/hash are unchanged. Both versions require the complete field
set. V2 accepts validated terms or null, never omitted terms, inferred dates or
parent inheritance. Nested invalid terms and unknown versions have sanitized
refusals. No duplicate economic model or new dependency was introduced.

Parent review corrected the payment-term docstring's misleading additional-field
wording: v2 uses the existing required field. Independent validation: 1211 unit
and contract tests and 42 focused revision integration tests passed, with two
existing deprecation warnings per suite. These tests do not establish live
PostgreSQL v2 persistence, which is not implemented. Runtime PostgreSQL accepts
connections; no runtime schema or business record was changed.

Next: implement the additive storage carrier, edit-token coverage and governed
write/read integration with field-specific preserve/set/clear semantics. Resolve
the documented legacy-conversion policy before capture wiring. No current writer
emits v2. Date resolution, lifecycle, valuation composition, UI/persona acceptance
and commercial delivery remain pending; this is only the domain compatibility
step, not a usable payment workflow.

### Payment persistence compatibility specification (2026-10-03)

Specification only; no implementation, migration, runtime, schema, test or
client change. DeepSeek replaced the ambiguous S2b transition sketch in
[CONTRACT_PAYMENT_INTEGRATION_PLAN.md](CONTRACT_PAYMENT_INTEGRATION_PLAN.md)
section 15 with a precise implementation contract grounded in the current code:
omission of the new payment-terms field preserves stored terms while explicit
`null` clears them (inspect `model_fields_set`; do not globally change existing
fields' replacement semantics or apply `exclude_unset` to the whole request); canonical
revision documents always include `payment_terms` — v1 stays strictly null with
its pinned bytes/hash and version-dispatched v2 accepts only a strict S2a
document or null, with no parent inference during decode; additive nullable
storage with no backfill; and the existing edit-token-before-capture, atomic
capture/audit ordering extended to cover the terms carrier. Two integration
decisions remain open for the implementing slice: the terms carrier and its
edit-token version, and whether untouched legacy rows keep v1 encoding or
accept a disclosed conversion revision (today's capture idempotency compares
content hashes, so schema conversion alone must not silently allocate a
revision). Integration pending. Focused gates: `git diff --check` clean, the repo-wide
markdown link check and the docs-alignment contract tests passed (one
negative sandbox fixture test cannot write outside the workspace; that
failure is environment-limited, not a link failure).
Parent review narrowed omission handling to the new field only and retained
authorization ordering. Independent docs/architecture alignment checks:
18 passed (two existing deprecation warnings); diff check passed. Runtime
PostgreSQL accepts connections. Baseline `d9a7363` CI run `37097891754` passed.

### Explicit payment-term domain foundation S2a (2026-10-03)

Baseline `a04f99a` passed GitHub CI run `37087566428`. DeepSeek implemented the
reviewed S2a declared-term model and ontology vocabulary/concepts. Each ordered
schedule item records evidence, cash-flow category, explicit INFLOW/OUTFLOW
direction and either a final payable date or an unresolved anchored rule.
Offsets, day kind and roll conventions are explicit; calendars are required
when used. No anchor date, amount, annual-rate convention or cash value is inferred.

Parent review required explicit direction independent of category, sanitized
refusals, and shorter implementation commentary. DeepSeek repaired those issues;
parent added rejection of invalid Unicode surrogates before UTF-8 serialization.
Independent validation: 108 focused model/ontology/revision tests, then 1202
unit and contract tests passed; focused Ruff and diff checks passed. Existing
revision v1 canonical bytes/hash are pinned unchanged by a golden test.

This is a domain foundation, NOT an integrated payment workflow. No database,
migration, contract write, valuation math or client change was made. The new
ontology concepts are deliberately not bound to nonexistent storage tables.
S2b still needs additive revision-schema handling, explicit write/preserve/clear
semantics and governed read/write integration; older clients omitting terms must
not erase them. S3 citation/composition still requires an explicit lifecycle
decision and reviewed date resolution. Keep browser/persona/commercial release
gates open; do not promote these tests into end-to-end acceptance evidence.

### Business acceptance reconciliation (2026-10-03)

Commit `15c81cd` passed GitHub CI run `37033382839`. DeepSeek reconciled all
eight required business journeys against current code, corrected stale contract
concurrency claims, and retained missing integration and commercial-release
gates. No journey is claimed end-to-end verified. The API-key runbook now
distinguishes deployment credentials from per-principal identity headers.
Parent documentation-link/alignment and permission-registry checks: 29 passed.

Parent live read probes authenticated all six existing test identities with
their expected roles. Contract reads admitted ANALYST/OPERATOR and the multi-role
test account; VIEWER, REVIEWER and ADMIN-only were refused. Resource-pool reads
admitted the commercial roles and refused ADMIN-only. This corrects the earlier
probe's misplaced identity key in the deployment Bearer header; no key rotation
or permission expansion was needed. These are narrow authentication/read checks,
not full persona or mutation acceptance. Browser inspection remains unverified.

Next business integration unit follows the existing contract-payment plan S2:
review explicit payment vocabulary, then preserve caller-declared terms without
invented anchors/calendars. S3 must connect captured contract evidence to the
shared dated-cash engine, with lifecycle prerequisites resolved explicitly.
Do not treat current primitives as an integrated tender/LNG/cash workflow.

### Bounded decision waits and stream disposal (2026-10-03)

Baseline `c11a2cb` passed GitHub CI run `37030801017`: backend validation,
PostgreSQL integration, EN/ZH browser acceptance at three viewports, web build
and dependency audit passed; native desktop build was skipped.

DeepSeek implemented a 30-second client wait bound for Compare/Optimize using
the existing abort helper and optional transport signal. Timeout releases the
action, preserves prior result/provenance, suppresses late answers and never
automatically retries. A parent-requested repair added typed timeout vocabulary
and bilingual explanation of uncertain server completion. Vite module disposal
now closes its owned decision streams. Strategy persisted-run timeout handling
is still open because completion must be reconciled rather than blindly retried.

Independent parent evidence: 842 web tests passed, 3 skipped; production build
passed with the existing dynamic-import warning. Python contract suite: 499
passed and one old call-shape assertion failed. The assertion was updated to
include the cancellation signal without removing the legacy-payload check;
all eight tests in that file then passed. `git diff --check` passed.

Runtime diagnosis: authenticated development-login probes through the local
Vite proxy returned HTTP 200 for identity (48ms), monitoring summary (42ms), and
pipeline health (1095ms). PostgreSQL/API availability is therefore not the same
as the observed browser problem. Existing role-key probes initially returned 403
because they used the wrong header; the later reconciliation above verifies the
correct dual-header flow without changing credentials.
The existing browser tab and one fresh tab both timed out during browser
inspection/navigation/screenshot operations. No successful local visual
acceptance is claimed, and neither HMR nor connection saturation is proven as
the cause. No runtime contracts, market rows or schema were changed.

Next: verify this commit's CI, recover browser inspection and retest Compare /
Optimize success, timeout, changed-input freshness and reconnect at desktop/mobile
widths; then continue the documented integrated trading-workflow programme.
Commercial delivery remains unproven; do not substitute this reliability slice
for LNG/tender/cash/strategy/persona and release/legal acceptance.

### Decision result input freshness (2026-10-02)

DeepSeek implemented this bounded slice on `3351ee1`, followed by a parent-requested
session-safety repair. Compare and Optimize results now carry canonical identities
of their caller-known request inputs, saved-contract tokens and exposed market
observations. Shared selectors withhold mismatched results from current economics
across Scenario, Portfolio, Network and Review. Unknown values remain unavailable,
not zero. Strategy evaluation responses are discarded after identity invalidation,
including errors and follow-up reads; real-store deferred tests cover this boundary.

Independent parent validation: standard web suite 830 passed, 3 skipped; production
build passed (existing ineffective-dynamic-import warning); Python contract suite
500 passed. `git diff --check` passed. The two assertion/comment failures in the
previous `3351ee1` CI run are repaired here; that previous run was not green.

Limits: identities describe client-known inputs, not immutable server snapshots.
Strategy overrides are conservatively stale against the default payload, and no
current surface calls that evaluation helper. Raw strategy provenance in the
persisted-run detail still needs explicit freshness treatment before wiring it to
a new evaluation surface. No backend API/schema or runtime contract writes.

Live acceptance remains OPEN: PostgreSQL accepts connections, but the authenticated
browser reported monitoring/pipeline/nomination read timeouts. Compare Options
remained pending for several minutes without a final result. The API process was
reachable (an unmatched route promptly returned 404), which is not proof that
authenticated computations are healthy. Local evidence:
`output/runtime/decision-freshness-pending.png`. Next bounded task: diagnose the
browser-to-API request lifecycle, restore bounded completion/failure, then verify
changed-input freshness through the real UI at desktop and mobile widths. Do not
treat these automated checks as completed live trading-workflow acceptance.

### Unknown contract numeric terms (2026-10-02)

DeepSeek implemented nullable numeric draft terms on baseline `56337f6`.
Stored hydration no longer borrows template rates, costs, quantities or lags;
clearing a numeric control produces unknown rather than zero. Validation follows
the existing backend numeric bounds; the save hook checks payload readiness
before transport. Pool optimization refuses an unknown financing rate rather
than substituting zero. Optional capacity/allowance null semantics remain those
of the existing API; server-side allowance-null-to-zero remains an explicit gap.

Parent reviewed mapping, payload boundary and scenario consumers. Independent
standard web suite: 817 passed, 3 skipped; production build passed with the
existing ineffective-dynamic-import warning. Local services were down and were
restarted against existing PostgreSQL without migration. Authenticated browser
inspection of the saved preview contract showed missing variable/regas costs
blank. Clearing its price kept the control blank, added a validation issue and
left Save disabled. No contract write was performed. Screenshot evidence is
local `output/runtime/contract-unknown-numeric-desktop.png`; this verifies the
numeric state, not complete responsive or conflict/reconciliation acceptance.

Prior commit `56337f6` passed GitHub run `36997296510`. Remaining commercial
gaps include stale simulated market inputs, negative-price/currency policy,
dated payment integration, full persona workflows and release/legal clearance.

### Post-save authentication denial (2026-10-02)

Baseline `f23292a` passed GitHub CI run `36970264979`. Parent found and
reproduced an uncovered case: a 401 from the contract-library refresh alone
left the session open and returned the saved commercial record to the editor.
Applied the existing identity-denial reset to this path, after verifying its
request identity is still current. The regression now passes, clears cached
contract/pool data and suppresses the returned record. Updated the exact
identity-invalidation inventory from eight to nine sites; reset assertions
remain intact. Independent focused client suite: 20 passed; TypeScript passed.
No schema, API, permission widening or runtime database write. This narrow
security fix was implemented directly because delegation overhead exceeded it.
Interactive conflict/reconciliation acceptance and commercial blockers remain open.

### Contract library read ordering (2026-10-02)

DeepSeek completed the bounded read-ordering repair on baseline `83bcc59`.
Parent reviewed all changed store paths. Workspace loads, endpoint retries and
post-save reads now share contract-library request ownership. Committed writes
invalidate earlier reads; superseded responses cannot replace rows or endpoint
records. Failed latest reads retain last-good rows with a recorded error rather
than reporting an empty library. The save refresh uses the existing portfolio
projection for pooled resources, preserving its context and identity guards.
Parent additionally guarded the obsolete refresh-error notice.

Independent validation: standard web suite 806 passed, 3 skipped; production
build passed with the existing ineffective-dynamic-import warning. Seven new
behavioral tests cover cross-path ordering, latest-read failure, retry, identity
invalidation and context change. No runtime DB write or schema/API change.
Previous commit `83bcc59` passed GitHub run `36958604057`. Authenticated visual
conflict/reconciliation acceptance remains outstanding; shared loading ownership
is still not universally action-scoped. Commercial readiness remains open.

### Draft-scoped save feedback (2026-10-02)

Same-commit GitHub CI for `1672872` passed in run `36956647438`, including
PostgreSQL integration, browser acceptance, validation, web build and dependency
audit; native builds were skipped. This does not cover the complete interactive
conflict/reconciliation journey. Parent attempted local inspection: the existing
tab stalled at Checking session; after restarting the owned development API
(PostgreSQL unchanged), existing-tab evaluation and fresh-tab navigation both
timed out. API startup completed successfully. No visual acceptance claimed.

Code review found that clearing feedback on draft replacement did not prevent
an older pending save from publishing its conflict/success against the replacement.
DeepSeek added separate feedback and save-attempt sequence guards; parent
reviewed the diff and independently passed 29 focused client tests. Identity
invalidation still drops commercial results entirely. A committed write can
refresh the library without publishing a notice on the wrong draft.

Remaining: authenticated conflict/reconciliation visual QA; the save-driven
library refresh is still unsequenced against other reads, and the shared loading
flag is not universally action-scoped. These are not covered by the feedback
guard. Continue toward full commercial acceptance, not only test completion.

### Contract stale-edit protection (2026-10-02)

DeepSeek implemented the reviewed state-token precondition on baseline
`6b5258d`, then repaired parent findings in normal Node import resolution,
same-identity draft replacement, and committed-write/failed-refresh handling.
Parent additionally corrected an expired-identity refresh returning commercial
data to the editor. Existing public updates now require the read token;
missing/null means create-only, including concurrent creates. The row lock
guards comparison before capture, audit or mutation. The token covers all
persisted columns, including metadata and timestamps; it is not a signature
or monotonic lifecycle version. No schema change or runtime database write.

Independent evidence: 40 token/API tests passed; standard `npm test` passed
794 with 3 skipped; production build passed (existing ineffective dynamic-import
warning); after the parent identity correction, 21 targeted client tests passed.
PostgreSQL concurrency and browser acceptance require same-commit CI; the new
conflict notice has not yet received authenticated visual acceptance. The broader
security/client-release suite passed 246 tests; focused Ruff passed. Earlier notes-preservation commit
`6b5258d` passed GitHub CI run `36953137737`.

Next: verify the conflict journey in the running application, including safe
reload/reconciliation and feedback scope while switching drafts. Numeric missing
values, revision-history presentation and full commercial acceptance remain open.

### Contract notes preservation (2026-10-02)

DeepSeek implemented a bounded repair on baseline `35091c9`; parent reviewed
the diff and independently passed 37 focused web tests and `npx tsc --noEmit`.
Saved-row hydration carries its own notes object into the draft; payload
construction preserves unknown nested fields and recorded source while overlaying
editor-owned fields. Contract switches replace the base; new drafts and file
imports clear it. Non-object notes are retained under `operator_notes`.
No API/schema change or runtime database write was performed for this slice.
This is mapper/payload evidence, not a new end-to-end browser-save acceptance.
Still open: stale-edit conflict protection, missing numeric-field semantics,
import preservation beyond known fields, and refreshing the notes base after save
to avoid metadata-only changes caused by serialization order. Commercial
readiness remains open; continue with bounded contract integrity work.

Completion standard (latest user direction): commercial delivery to a
professional client, not only a controlled pilot. Require clear customer and
operator documentation, maintainable architecture, tested clients and deployment
settings, and evidence-backed licensing/legal claims. Review actual distributed
dependencies and their obligations; unknown licence metadata is not clearance.
The current third-party notices contain unresolved `NOASSERTION` entries and
are not a completed legal/commercial-distribution review. Preserve the release
blocker register and fail-closed publication gates.

User acceptance must include end-to-end trader, researcher, risk/reviewer and
administrator journeys across the supported gas business models. Check happy
paths, missing/stale data, invalid inputs, changing context, permission denial,
source provenance and numerical results. Professional UI/UX is a release
requirement: consistent components and units, efficient action placement,
keyboard access, responsive layout and truthful loading/error/result states.
DeepSeek remains the implementation worker; parent review owns integration and
acceptance. Neither passing component tests nor attractive screenshots prove
commercial readiness.

## Governing Product Goal (User Direction, September 30)

Deliver Eurogas Nexus as a coherent, commercial, professional European gas
trading decision-support solution. Controlled first-customer pilot readiness
is an intermediate acceptance milestone, not the ultimate product boundary.
Assess functional design, ontology, data, shared analytical capabilities,
persona workflows, backend authority, visual UI/UX, existing features and
installation/operations together. A collection of isolated calculators or
passing component tests is not completion of this goal.

Common calculations belong to shared, versioned domain capabilities: dated
cash flows, currency conversion, discounting/cash value, energy conversion,
cost allocation and valuation provenance. LNG/regas, pipeline supply,
storage and portfolio strategies compose those capabilities through explicit
business contracts rather than duplicating the mathematics. Reconcile with
the existing ontology and canonical identifiers before introducing new types:
cash-flow leg, money/currency, valuation date, delivery period, energy basis,
contract, cargo, terminal, transport capacity, portfolio and resource pool.
Persona or work mode affects workflow presentation, never backend authority.

The shared valuation extraction is implemented at `79100cf`:
`research/cash_valuation.py` owns the arithmetic and the LNG adapter delegates
to it. The sandbox research API followed at `8b91293`, retaining exact decimal
strings and explicitly unresolved business-context references. The fractional
cost regression is corrected by rounding each cost before aggregation, matching
the cash primitive. These are engineering foundations, not an integrated trader
workflow or production valuation approval.

The typed web client transport is now connected to this contract. Next:
integrate an explicit dated cash schedule into the existing decision/scenario workflow.
Inspect the authenticated application before visual changes. Existing scenario
prices and daily volumes do not establish payment dates, FX provenance or
discount curves; never infer those missing inputs or duplicate the server math.
Keep source assumptions, unresolved references and research status visible;
invalidate results when their input or business context changes.

Acceptance requires integrated trader journeys, coherent shared components and
HMI, consistent data/time/unit semantics, lawful real-source provenance,
numerically reproducible decisions, permission-aware persona testing and
verified customer artifacts/operations. Continue to delegate routine work to
DeepSeek and independently verify results. Preserve existing release/security
gates: no execution, nomination submission or settlement; no unsupported
production approval, fabricated live data or silent expansion into Power.
The existing pilot blocker register remains binding and must be reconciled
with this broader product goal, not replaced by component-level success.

## Milestone History

October 2 saved-contract hydration correction (baseline `9e0b26e`): live
inspection found absent saved counterparty/agreement fields inherited template
facts. DeepSeek separated saved-record text hydration from draft/import
overlay; absent saved text now stays blank. Parent: nine mapping tests and
TypeScript check passed; authenticated browser confirmed blank counterparty
and agreement, with the required-counterparty save blocker. No contract was
saved. Numeric fallback semantics, unknown-note preservation, stale-edit
protection and visible revision history remain separate open work.
Local runtime was backed up and upgraded from 0036 to 0037 before this
inspection; read-only validation passed and API/web servers were restarted.
The backup remains gitignored under `.automation/runtime`. Startup-fix CI
`36884303474` passed on Python 3.11, including both load-smoke modes.

October 1 cold-start initialization repair (baseline `109fe24`): DeepSeek
added import-only, single-threaded dependency initialization in application
lifespan and made the in-process load smoke execute that lifespan before its
unchanged concurrent workload. No request warm-up, retry or relaxed threshold.
Parent review and verification: 42 focused startup/import-safety/load-smoke/link
tests passed; whole-repo Ruff passed. Fresh-process tests cover initialization
ordering and concurrent requests. Local Python is 3.14: the exact Python 3.11
import deadlock was not locally reproduced; same-SHA CI remains required.
No database connection, migration or runtime data change was introduced.
Harnesses that bypass ASGI lifespan remain outside this initialization contract.

October 1 CI cold-start failure at `58afd8a`: run `36878083383` failed
the validate job's in-process API load smoke. The traceback ends in Python
3.11 `_ModuleLock('sqlalchemy.exc')` deadlock during concurrent first-request
imports from `sources._runtime_source_counts` through `db.session`/`db.base`.
Browser, web build, PostgreSQL and dependency checks passed. The earlier full
suite and `90e68c9` CI pass remain historical evidence, not proof this race is
resolved. Runtime PostgreSQL container is healthy. Next priority: reproduce
in isolated cold processes and review application initialization versus ASGI
lifespan handling in the smoke; do not hide the failure with arbitrary retries,
serial requests or relaxed error thresholds. No code fix is claimed yet.

October 1 full regression verification at `90e68c9`: parent executed the full
Python suite without deselection: 2,681 passed, 28 skipped, two dependency
deprecation warnings, no failures (569 seconds). Same-SHA CI `36876647980`
passed validation, PostgreSQL integration, EN/ZH browser acceptance at three
viewports, web build and dependency license/CVE checks. Native desktop build
was skipped. Skipped local tests and external production acceptance remain
unproven; this is regression evidence, not commercial approval. Next work
remains stale-edit protection and visible contract revision inspection.

October 1 combined contract regression review (baseline `8bc0fcf`): parent ran
API, security, integration, snapshot/migration and Markdown checks together:
775 passed, 24 environment-dependent tests skipped, two security-acceptance
tests failed because the deliberate route-count pin still said 180. The exact
API inventory diff contains only the two reviewed GOVERNED revision reads.
Updated that pin to 182 without relaxing equality or permission checks; all
12 targeted security acceptance/revision authority/API-surface tests then
passed. The whole combined suite was not rerun after this count-only repair.
External security review remains blocked as documented; automated acceptance
is not customer deployment approval.

October 1 captured-revision reads (baseline `9160188`, CI `36873870921`
passed including PostgreSQL): DeepSeek added contract-scoped list/detail reads
with the existing GOVERNED commercial floor, bounded pagination, verified
snapshot evidence and typed client transport. Missing contract, empty history
and cross-contract revision IDs have distinct appropriate outcomes; integrity
failure refuses evidence. Parent corrected the empty-history warning on an
out-of-range page. Parent tests: 26 backend/security/API/link tests and three
client transport tests passed; whole-repo Ruff passed. Reads never capture or
mutate rows. No visual history panel, expected-version precondition or local
database migration was added. Next: stale-edit protection integrated with the
existing editor, and visible revision inspection/citation, before extending
payment schedules or claiming a complete contract lifecycle.

October 1 governed contract-write integration (baseline `9271500`, CI
`36869874054` passed including PostgreSQL): DeepSeek connected the existing
upsert API to authenticated attribution, row locking, before/after economic
capture and transactional mutation audits. Malformed stored terms refuse
overwrite; metadata-only edits are audited; already-captured replays do not
duplicate revisions. An unchanged uncaptured legacy row still gains its first
capture, not a reconstructed historical revision. Parent: 67 focused tests
passed and whole-repo Ruff passed. PostgreSQL concurrency cases await same-SHA
CI. No local runtime migration/write occurred. Next: expected-version conflict
protection and governed revision reads, then client history/citation; payment
terms, complete lifecycle and commercial acceptance remain open. Direct legacy
repository writes remain outside this API capture path.

October 1 revision persistence foundation (baseline `f396492`, whose CI
`36865510283` passed): DeepSeek added expand-only migration
`0037_contract_revisions`, explicit repository capture/read, per-contract row
locking, idempotent repeat capture, canonical integrity checks and transactional
audit. Parent review required rejection of mapping warnings, refresh of stale
ORM instances before capture, audit-failure rollback coverage and qualified
migration deployment claims. Parent verification: 81 focused tests passed,
three PostgreSQL tests skipped locally; whole-repo Ruff passed. Disposable CI
now includes revision repeat/change, concurrency and stale-instance tests.
No local runtime migration or capture was performed. Existing contract writes
still overwrite their legacy row; this is explicit captured evidence, not yet
automatic revision history or lifecycle. Next: verify same-SHA PostgreSQL CI,
then integrate governed contract writes with captured revisions and actor
attribution, preserving API compatibility and fail-closed audit behavior.

October 1 contract economic snapshot foundation (baseline `1676b98`):
DeepSeek implemented `domain/route_cost/contract_revision.py` with an immutable
economic payload, strict legacy mapping, explicit missing payment terms,
null-versus-zero preservation, numeric provenance and deterministic versioned
JSON/hash. Parent review required bounded decimal serialization and strict
canonical decoding; DeepSeek added both with regression tests. Parent ran
48 focused snapshot/cash/API/repository/link tests successfully and whole-repo
Ruff passed. No runtime API, UI, optimizer arithmetic, database or migration
changed. This foundation is not yet consumed by persisted contract revisions.
Next: additive revision persistence and legacy capture with upgrade tests,
followed by atomic guarded writes/audit; never reconstruct historical terms
from current rows or treat a hash alone as revision history.

October 1 contract/payment integration preparation (baseline `509e703`):
DeepSeek inspected contract CRUD, ontology and shared cash capabilities and
produced [a proposed integration design](CONTRACT_PAYMENT_INTEGRATION_PLAN.md).
Parent review corrected draft concurrency (separate edit counter), immutable
retirement semantics, funding/discounting policy and incremental migration
scope. Existing cash-engine and Markdown-link tests: 14 passed. This is design
evidence only: no API, UI, migration, database write or payment convention was
implemented. Next bounded task: review the immutable economic payload and
legacy compatibility mapping before an additive revision migration; do not
infer historic revisions or payment dates from the existing lag fields.

October 1 alert acknowledgement authority (baseline `14cc3ce`, parent lint
correction `da560bb`): DeepSeek added an explicit GOVERNED monitoring write
permission and authenticated-principal attribution for monitoring and shadow
acknowledgements. Shadow body.actor remains accepted but ignored. Conditional
updates prevent repeat acknowledgements from replacing the original timestamp
or actor; successful transitions and audit_events insertion share a transaction.
No schema migration or new datastore. Parent reviewed both paths and added an
explicit PostgreSQL-test opt-in so local test runs cannot accidentally commit
test alerts to the configured desk database. Parent verification: 47 focused
security/API/link tests passed; 3 PostgreSQL tests skipped locally, to run in the
disposable CI PostgreSQL job. Whole-repository Ruff passed. CI `36803887280`
for `da560bb` passed. Same-SHA CI `36805439885` for `4e04c3c` subsequently
passed validation, EN/ZH browser acceptance at three viewports, dependency
license/CVE audit, web build and PostgreSQL integration. The disposable
PostgreSQL job executed 11 tests successfully, including the three new
acknowledgement tests; these were not skipped. The desktop build was skipped,
so this run is not native installation or desktop release acceptance.
No live alert was acknowledged and no local database was migrated. Remaining:
show acknowledger in the client, complete assignment/escalation lifecycle,
and verify populated persona flows. Shared payment semantics, contract revision
history, lawful market data and broader commercial acceptance remain open.

October 1 decision-run integrity and business coverage (baseline `7ce64b0`,
with UAT disclosure correction `f65423b`): DeepSeek inventoried the eight
business journeys and implemented separate compare/optimise action states,
capability-aware presentation, duplicate prevention and successful-result
context provenance. Parent tests: 754 web tests passed, 3 skipped; production
build passed; 55 focused API/security/contract/link tests passed. Parent browser
verified visible origin refusal with correlation ID, successful comparison
after correcting the local launcher's explicit loopback origin, and stale-result
notice plus withheld scenario economics after changing hub context.
Important correction: the local ADMIN-labelled account has multiple persisted
roles and `optimization.run`; its 403 was `origin_not_allowed`, not role denial.
Admin-only denial remains fixture-test evidence, not a populated persona test.
No backend permission was weakened; local API remains loopback-only with CSRF
enabled. PostgreSQL revision 0036 was verified without migration.

CI `36760762221` for `f65423b` passed, including the updated keyboard-disclosure
browser journey. New action changes still require same-SHA CI. Coverage inventory
is in `docs/product/TRADING_BUSINESS_ACCEPTANCE.md`; parent did not approve its
proposed inferred payment dates/rate conventions. Next priorities: monitoring
acknowledgement write permission and actor attribution; shadow acknowledgement
must not trust body.actor; then explicit contract/payment semantics and retained
input lineage for integrated dated cash. Strategy run provenance still stamps
at request start and needs the same lifecycle review. Broader commercial data,
persona, responsive, licensing and deployment acceptance remain open.

October 1 professional workflow/HMI follow-through (baseline `cc7a36a`):
DeepSeek compacted the day board into an unframed native disclosure with urgent
status retained in its summary. Parent inspected the authenticated application,
verified EN/ZH and keyboard toggle, and corrected missing-deadline wording.
739 web tests passed, 3 skipped; production build passed. Browser viewport
override was ineffective; observed 738x461 only, not full responsive acceptance.
Expanded business acceptance is now recorded in
[`TRADING_BUSINESS_ACCEPTANCE.md`](../product/TRADING_BUSINESS_ACCEPTANCE.md):
tender economics, daily awarded-supply optimisation, LNG/regas, contract/rights
lifecycle, financing/clearing, exchange arbitrage, shadow strategies and alerts.
These are required journeys, not implemented coverage claims or extra pages.
Next: inventory actual end-to-end support against this matrix and close the
largest commercial gaps using shared ontology-backed capabilities. Cash schedule
integration remains open. No execution or external contract mutation is added.
Security-fix CI `36757155495` for `cc7a36a` completed successfully, including the
dependency license/CVE audit; this closes the preceding CI regression only.

October 1 dependency security correction (baseline `5223256`): DeepSeek
updated only the build-lock urllib3 pin from 2.7.0 to 2.8.0 for the three
vulnerabilities reported by CI (CVE-2026-97687/97688/97689). Parent independently
matched both distribution hashes against PyPI and found no direct urllib3 or
affected proxy-configuration references in application/build code. Dependency
policy and SBOM tests: 52 passed. No runtime dependency or security-gate change.
The worker's isolated full-lock installation did not finish within the bounded
review window and was stopped; no completed local CVE audit is claimed.
Same-SHA CI dependency audit remains required. No commercial approval follows.
Next user-facing work remains authenticated, populated trader workflow review:
retain only necessary controls, explicit units/provenance and effective inputs;
prioritize decision efficiency over additional panels or decorative content.

October 1 shared ingestion-status consumers (baseline `cd7c46c`): DeepSeek
moved the compatibility rule into `domain/dataops/run_status.py`, reusing the
canonical enum. Source reads, monitoring alerts, pipeline health and metrics
now classify canonical/legacy failures consistently; raw statuses are retained.
Parent review confirmed application consumers import domain, not API, and
unknown/pending/cancelled statuses do not become failures. Parent verification:
220 focused unit/API/architecture/documentation tests passed; focused Ruff
passed. No DB writes, migration, provider calls or permission changes.
This is not full operational acceptance. Remaining defects: historical writers
can omit source_id while source reads group by ID and monitors by name; monitor
and pipeline streaks sample 500 runs globally; metrics load all run history.
Resolve identity/coverage and bounded aggregation before claiming reliable
per-source health across a long-running customer deployment. Persona workflow
and UI review remain required alongside these backend foundations.

October 1 source status vocabulary (baseline `7bda19d`): DeepSeek reconciled
source-read classification with the canonical ingestion lifecycle and the four
declared legacy spellings. Canonical failures now affect connectivity and
diagnostics; warning-qualified successes retain qualification. Pending,
cancelled and unknown statuses are not success/failure outcomes. Stored status
remains unchanged. Last-success/failure selection uses completion time with
start-time fallback and deterministic ties; per-source materialization remains
bounded. Parent review: 54 focused API/security/link tests passed. Read-only
PostgreSQL execution matched the distinct source count and processed the local
80,545 legacy-success rows without loading history into the read model. That
store contains no canonical-status fixtures, so canonical cases are proven by
focused tests, not live customer ingestion. No schema or business-data write.
Remaining: monitoring_service, pipeline_health and dataops_observability still
have inconsistent legacy/canonical matching. Move the compatibility rule into
a shared domain-owned boundary when aligning those consumers; do not duplicate
it or declare system-wide status consistency from this endpoint fix alone.

September 30 source-status read performance (baseline `f3b89bc`): DeepSeek
replaced full ingestion-history ORM loading with per-source latest-run ranking,
combined observation counts into grouped reads, and pushed history filtering
and limits into SQL. Parent tests: 45 focused API/security/link checks passed;
focused Ruff passed. Authenticated reads against existing PostgreSQL returned
24 sources: before 6.539s; after API restart 1.327s, 0.363s and 0.351s. These
are local observations, not controlled load or customer SLO acceptance. No DB
migration or business-data write. Worker scratch SQLite diagnostics are test
evidence only; PostgreSQL remains the sole runtime store. Startup/concurrent
load verification remains open. Separate correctness gap: source-status reads
recognise lowercase succeeded/failed but the scheduler emits uppercase states.
Reconcile that vocabulary next with tests rather than mixing it into this fix.

September 30 scenario-input integrity (baseline `22b9a42`): authenticated
browser inspection found EUR labels on GBP-named draft fields. DeepSeek traced
both request builders and found seven of eight visible draft controls affected
neither Compare Options nor Optimize. Those misleading controls are removed,
while shared contract fields remain compatible. Both actions use persisted
resource-pool inputs; the optimizer alone consumes the draft financing rate
when the first saved upstream contract has no rate. A shared resolver now
drives the request and source disclosure. Parent review made a saved rate
read-only and displayed its actual value, and shortened EN/ZH disclosures.
Full frontend suite: 732 passed / 3 skipped; TypeScript and production build
passed; 37 focused documentation/surface/trader checks passed. Live local
browser verification at the actual 738px viewport showed the saved 6% rate,
read-only source and absence of the seven controls. Desktop/mobile overrides
were not established by that browser, so this is not multi-viewport acceptance.
No calculation was executed or business data changed during this verification.
The data-source endpoint timed out after 10 seconds; investigate separately.
Screenshot retained locally at `output/runtime/scenario-input-integrity.jpg`.
Next: complete persona workflow and responsive checks, then the dated cash
schedule integration. Financing-rate selection still uses the first saved
contract, not a reviewed multi-contract funding policy; that limitation must
be addressed before claiming portfolio-wide valuation accuracy.

September 30 cash-valuation client foundation (baseline `8b91293`): DeepSeek
added exact-string request/result DTOs and `api.cashValuation` through the
existing authenticated transport. The request carries no decision-context or
authority claim; the backend labels the response sandbox-only. No UI, browser
storage, numerical duplication or new API route was introduced. Parent review
checked the metadata against the actual response, narrowed an overbroad comment
about other research routes, and identified the precision fixture explicitly as
a transport stress case rather than an engine reference result. Parent validation:
full frontend suite 727 passed / 3 skipped, TypeScript and production build passed;
49 API/surface/markdown tests passed. Worker sandbox process-launch failures did
not reproduce in the parent environment. The production build retains the
existing mixed static/dynamic client-import warning. Authenticated UI inspection,
dated-input editing, context invalidation and populated workflow acceptance
remain outstanding. The preceding API commit's CI `36650976591` passed.

September 30 shared valuation research API (baseline `79100cf`): DeepSeek
added POST `/api/research/cash-valuation` through the existing research router
and sandbox dependency. It calls the shared engine, uses bounded exact decimal
string inputs/outputs, and explicitly identifies caller-supplied unresolved
business references. Runtime-decision mode refuses; no entity lookup, valuation
persistence, source ingestion or authority inferred from persona/context IDs.
Parent verification: 240 API/security/surface/link tests passed; focused Ruff
and whitespace clean. Surface inventory and EN/ZH error taxonomy updated.
This is not persisted portfolio valuation or customer acceptance. Next wire
the existing scenario workflow to this API with shared result presentation,
without adding duplicate arithmetic or a disconnected calculator page.

September 30 shared cash valuation (baseline `d8644bb`): DeepSeek extracted
one `research/cash_valuation.py` engine; LNG validates its context then delegates
through a compatibility adapter. Generic business context uses existing ontology
`CanonicalId`; pipeline/portfolio/storage tests require no cargo/terminal IDs.
Existing cash/refusal safeguards and deterministic Decimal arithmetic retained.
Parent verification: 367 research/readiness/architecture/ontology/docstring/link
tests passed, one optional test skipped; focused Ruff clean. Shared category and
input aliases preserve import names but class repr/module identity changes.
Money/PriceBasis/FxConversionRef remain float-based in the semantic kernel and
are not used for exact cash arithmetic; that reconciliation and controlled cargo
entity vocabulary remain open, documented in CASH_VALUATION_CAPABILITY.md.
No API/UI/security authority or persistence added. Next expose the capability
through existing audited application workflows with ontology/permission checks,
then integrate the shared result presentation rather than another calculator.

September 30 cargo economics (baseline `bc099b2`): DeepSeek's pure composition
reuses existing regas readiness and cash valuation, exposes purchased/delivered
energy, explicit loss, cost inclusion checks, netback per purchased MWh, cargo
margin and NPV. Parent fixed the red fractional-cost reconciliation regression;
256 focused cash/cargo/readiness/domain-contract/Markdown tests passed, Ruff
clean. Synthetic reference: purchased100/delivered90 MWh, purchase20/sale30
EUR/MWh and costs150 EUR -> netback25.5 EUR/purchased-MWh, margin550 EUR,
NPV550 EUR with unit discount factors. EUR-only, no API/UI/persistence or
customer-input acceptance. The generic cash valuation extraction is next;
do not copy this calculation into another business model.

September 30 LNG dated-cash valuation (baseline `53500ec`): DeepSeek added a
pure versioned research-domain calculation with signed, uniquely identified
cash-flow legs, explicit cross-currency FX and dated discount-factor provenance,
contract/cargo/terminal/resource references and deterministic Decimal rounding.
Outputs distinguish undiscounted cash from NPV, not netback/MTM/accounting.
Parent reproduced and fixed ambient Decimal precision affecting the amount
limit (`abs` -> context-free `copy_abs`), with a red-to-green regression.
Parent verification: 171 focused/domain-contract/Markdown tests passed, Ruff
and whitespace clean. Hand-computable synthetic case produces cash EUR10 and
NPV EUR4.50. This does not certify commercial inputs or prevent economically
duplicated costs with different IDs. Currency validation is code-shape only,
not an authoritative ISO currency registry. No API/UI/persistence/live trades.
Next compose delivered energy/losses and cargo cost/netback reconciliation with
existing regas readiness, then expose via existing application/API workflows.
Real-data and pilot acceptance blockers remain; no production approval claimed.

September 29 live capture engineering milestone (baseline `28df41e`): reviewed
DeepSeek's pending capture runner. It observes the browser's market projection
response and matches its as-of to the rendered board, without refetching, fixture
writes or raw-output persistence. Same-origin GET/HEAD requests only; WebSockets
blocked before navigation, service workers disabled; unsupported guards refuse.
Review added a whole-run watchdog for hung response bodies/evaluations and
browser-close cleanup (not a claim of OS-level cancellation of a hung browser
shutdown). Parent verification: full frontend Node suite passed; 18 Python
browser/Markdown contracts passed. Installed pinned Playwright 1.55.0 in ignored
local tools, then ran all 24 runner tests with Chromium: 24 passed, zero skipped,
including synthetic HTTP and WebSocket refusal. No actual customer deployment
capture or portfolio acceptance performed. EEX commit `28df41e` CI run
`36578514601` completed successfully. Next business priority is LNG/regas
valuation gap reconciliation and a bounded deterministic reference case; real
source rights/time contracts and three populated workflows remain open.

September 29 EEX NGP parser engineering milestone (baseline `4d0e0cd`):
DeepSeek implemented raw-preserving CSV parsing and guarded canonical mapping.
Parent review rejected guessed DST fold/gap handling, unearned live freshness,
an implicit gas-day calendar and unchecked Decimal-to-float overflow. Follow-up
now refuses these cases, with explicit separate publication-zone and delivery-
calendar evidence requirements. Parent verification: 64 ingestion/public-source/
gate/Markdown tests passed; focused Ruff and whitespace clean. Worker final
report wrapper classified its follow-up as fatal despite a structured report;
actual files and independent tests, not that classification, were reviewed.
No network/scheduler/DB write integration enabled. Default raw parsing remains
possible, canonical mapping refuses unproven temporal semantics; rights and
certification still unverified. Distinct provisional/final identities prevent
same-key overwrite, but cross-poll revision selection is still an integration
requirement. Live-capture changes remain separately uncommitted and under review.

September 29 user scope addition: European gas decision support must include
LNG regasification business economics, netback and cash-value calculations.
Existing `domain/route_cost/lng_regas.py` covers scenario/access/readiness inputs;
`domain/research/netback.py` currently implements only market price minus route
cost with optional FX multiplication. These do not prove complete cargo
economics or cash-flow valuation. Reconcile and extend existing services, not
a duplicate calculator/page: cargo purchase basis (FOB/DES), shipping and port
costs, demurrage assumptions, boil-off/fuel and delivered energy, terminal
regas/storage/send-out charges, downstream transport and hub sales, dated
receipts/payments, FX basis, discounting/NPV and financing sensitivities.
Distinguish netback per energy unit, total cargo margin, cash flow, discounted
value and mark-to-market; prevent cost/loss double counting and require explicit
valuation date, currency, energy basis, calendars, contract/terminal/resource
references, source lineage and missing-input refusal. Include deterministic
reference cases and alternative destination/supply comparisons. No execution,
nomination submission or settlement authority is added. Next delegate a gap
analysis and bounded implementation sequence after official-source adapter
review; this is scope recorded, not functionality claimed complete.

EEX parser worker completed; report:
`.automation/runtime/worker_runs/eex-ngp-official-parser-20260929-213111.final.json`.
Its parser/source-contract/test changes remain uncommitted pending independent
review, alongside previously recorded live-capture changes. No worker active.

September 29 user-directed real-source priority: prefer official real data to
simulation. Existing `scripts/ops/ingest_public_sources.py` already implements
live ENTSOG flow/capacity/reference ingestion with entitlement/certification
gates; connector-shell classes are not the complete ingestion inventory.
Official EEX gas transparency page links
`https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_15_Mins.csv`; a bounded read
succeeded. Semicolon CSV columns: Gasday, IndexValue (EUR/MWh), IndexVolume
(MWh), Status, Timestamp Let. Observed Final NGP and Temporary NGP statuses,
including a temporary zero-volume/zero-value row. Do not treat that row as a
tradable zero or this index as bid/ask. Timestamp timezone must be verified
against official methodology before normalization; never infer it from host.
Official source: https://www.eex.com/en/markets/natural-gas/gas-market-transparency
describes current NGP downloads updated every 15 minutes. Commercial reuse
rights remain distinct from public download availability.
ENTSOG operationaldatas bounded probe returned HTTP 200 (no ingestion yet).
Platform-specific terms, linked from ENTSOG's current terms page, expressly
permit API automation subject to conditions and attribution/download date:
https://transparency.entsog.eu/pdf/TRA0394_20161115_ENTSOG_TP_Privacy_TC_of_Use_Rev_3.pdf
Next priority: DeepSeek implement a bounded EEX NGP adapter through existing
ingestion, preserving status, gas day, units, volume, lineage and revision
semantics; verify timezone and rights before enabling scheduled writes. Review
existing ENTSOG certification and bounded date/filter coverage, do not bypass
gates or regenerate simulations to fill missing real data.

Pending local live-capture worker changes are preserved, not yet committed:
report `.automation/runtime/worker_runs/live-market-capture-20260929-210840.final.json`.
Parent fixed a process-test expected reason list (missing source label was
correctly refused); focused comparator/live-runner/read-to-render suite passes.
Full review and real-browser integration remain outstanding; do not claim the
live capture runner accepted. No worker remains active.

September 29 live local read-only assessment (commit `dae6efe`): GitHub run
`36566569503` succeeded in all five active jobs; native packaging skipped.
The API and frontend were not listening. Existing local launcher verified
PostgreSQL revision `0036_job_records` without migration and started the
development API on loopback port 8000. Health reports authentication enforced.
Using the existing encrypted local ANALYST credential, authenticated projection
reads at approximately 13:06 UTC returned 500 rows each for market observations,
normalized quotes and quotes; each slice was STALE and truncated, and all 500
rows in each were marked simulated. This describes returned slices, not a full
database inventory. Portfolio screen orders and PnL snapshots returned zero
rows/MISSING; contracts returned one row/UNKNOWN, resources two rows/STALE.
No fixture ingestion, migration or business-data writes were requested; ordinary
request auditing may write operational records. Only aggregate findings retained,
no credentials or response bodies. The frontend remains stopped.
Consequently this local fixture deployment cannot close PB-01/PB-04. Continue
engineering live capture/portfolio checks, but do not refresh simulations or
invent portfolio records to turn customer acceptance green. Obtain entitled
populated pilot inputs through the governed ingestion path for final acceptance.

September 29 offline market capture comparison (baseline `d88bf05`): DeepSeek
implemented `scripts/uat/compareCapturedBoard.mjs`, reusing the existing board
evaluator. It reads operator-supplied evidence only, emits whitelisted counts
and reason codes, and refuses simulated, truncated, stale or mismatched relevant
evidence. No network, database, seeding or provider calls. Parent review found
non-object source metadata could pass; a regression reproduced it, then required
object validation fixed it. Focused comparator/read-to-render tests, full frontend
Node suite and three Markdown contract tests passed; whitespace clean. No live
customer capture was tested. Supplied deployment/SHA labels are not attested;
PASS means only a bounded captured-board comparison, never pilot approval.
Next: live read-only capture integration and the portfolio half of WF-1; retain
PB-01/PB-04 and pagination gaps. GitHub CI for this change is not yet verified.

September 29 WF-1 acceptance reconciliation (baseline `2c33699`): DeepSeek
reviewed the market-to-portfolio projection/client/test paths, removed the
duplicate CA-02 blocker and documented the read-only customer acceptance
procedure in FIRST_CUSTOMER_PILOT_PLAN.md. Parent review narrowed pagination
claims to the projection routes, corrected simulation detection, prohibited
credential/customer-payload commits and made truncation refuse full-coverage
acceptance. Parent verification: 44 projection API/application/Markdown tests
passed; whitespace clean. PostgreSQL container observed healthy; no runtime
data, provider, deployment or application behaviour changed. PB-01/PB-04 stay
open. Next bounded task: add a read-only populated-deployment comparison mode
reusing the existing board evaluator without fixture writes, with redacted
local evidence and explicit truncation refusal. Pagination remains a separate
gap; no customer or production approval follows from this documentation pass.

September 29 D7 provider-boundary authority (baseline `59ca893`): existing
persisted worker identity resolution was already implemented; older descriptions
of D7 as wholly unbuilt were stale. DeepSeek closed the actual gap: enrichment
itself now re-reads an ACTIVE SERVICE principal with analysis.query, matches the
supplied actor to that configured identity, refuses before credential/provider
use and records attribution. Parent verification: 198 security/monitoring/API/
Markdown tests passed; Ruff and whitespace clean. Commit `09f985a` passed CI
`36502276994`, all five active jobs; native packaging skipped. This is a trusted
worker-process authority check, not authentication against a malicious host
operator. Live PostgreSQL revocation/deployment evidence remains open; default
compose does not pass the principal setting, so enrichment remains disabled.
No provider calls, runtime DB writes or deployment changes were performed.

September 29 MCP pilot containment (baseline `0154806`): DeepSeek added
authoritative-settings checks to JSON-RPC discovery/calls and exported tool
handlers. Trial/release environments or release API profile refuse tools before
handler/audit/network paths; malformed configuration refuses too. Developer/test
defaults remain, with no additional role/scope override of the protected profile.
Operator compose explicitly sets both release variables. Parent verification:
227 MCP/security/Markdown tests passed, focused Ruff and whitespace clean.
Commit `1b1d9ee` passed CI `36499995691`, all five active jobs; native packaging
skipped. CA-05 is mitigated for correctly configured customer deployments, not
closed: persisted service identity, headless worker authority and host-operator
configuration controls remain outstanding. No security approval or runtime
deployment change is claimed.

September 29 route-state badge accessibility (baseline `9b0efb2`): DeepSeek
separated allocated/candidate/blocked text badge tokens from unchanged map-dot
colours in light/dark themes. The browser sweep now renders a clearly test-only
three-state fixture with production CSS and actual EN/ZH labels on the Network
page, checks axe/contrast/text fit/overlap at all three viewports, captures it and
removes it before normal application screenshots. No market state or data changed.
Parent verification: 683 frontend tests, production web build, 47 Python
UAT/browser/Markdown contracts passed; whitespace clean. Build retains the existing
ineffective dynamic import warning. Commit `a834146` passed CI `36484351318`,
all five active jobs; native packaging skipped. Downloaded browser evidence has
zero failures and six EN/ZH desktop/mobile fixture screenshots; parent inspected
English desktop and Chinese mobile images. Measured allocated/candidate/blocked
ratios are 5.47/5.93/7.09. This fixture is component evidence, not proof of every
populated workflow or theme combination; dark tokens have unit contrast checks,
not a separately rendered dark-theme sweep.

September 28 G10 inventory prerequisite (baseline `bb0ad4c`): DeepSeek corrected
the existing lock-derived SBOM generator: nested/scoped npm identity, exact Cargo
registry provenance with TOML parsing, strict supported hash-pinned Python input,
ecosystem-specific purls, unique document namespaces, UTC timestamps and input
hashes. Review required malformed-entry refusal, explicit workspace-link
exclusions and no crates.io identities for lookalike registries. Parent checks:
69 focused release/Markdown tests passed, real-lock CLI generated four component
documents, focused Ruff and whitespace clean. Commit `bb06836` passed CI
`36431395000`, all five active jobs; native packaging skipped. No G10 PASS producer
was added: per-artifact mapping, container OS/native inventory and license-text
completeness remain open. Unsupported future lock syntax fails explicitly.
Next close artifact mapping and source inventory validation before declaring any
SBOM gate satisfied; do not substitute lock inventory for binary inspection.

New HMI follow-up from prior checkpoint CI `36428725740` (`bb0ad4c`): browser
acceptance reported serious color-contrast failure for the Chinese candidate
route pill (`.resource-route-state-pill.candidate` nested in `.allocated`), white
on `#0ea5e9`, ratio 2.77 versus required 4.5. Latest CI passed without a UI change;
that does not resolve this state-dependent defect. Next bounded HMI task: isolate
inherited allocated-state styling, fix badge contrast and add rendered regression
coverage without disabling axe or changing acceptance thresholds.

September 28 G8 executed security evidence (baseline `7f36b37`): DeepSeek
implemented the fixed security-suite producer and release validate-job wiring.
Generic status-based G8 writing is refused; local dry runs use the same suite
but cannot authorize release. Review added selection checks, pre/post checkout
identity and tracked-cleanliness checks, secure scratch space and retained JUnit
evidence. Parent verification: initial release/security/Markdown run 513 passed,
3 skipped; final focused run 221 passed after the post-run dirty-tree fix.
Overlapping test processes caused two temporary-directory collection failures;
the isolated rerun passed. Do not overlap pytest sessions in this workspace.
Actual default CLI execution: 183 security tests passed, zero skips/deselections,
retained XML, local-only evidence under ignored .automation/runtime. Ruff and
whitespace clean. Commit `c5a7f2b` passed CI `36428138195`, all five active
jobs on the first attempt; native packaging skipped. Release workflow itself
was not dispatched. G8 remains
source security evidence, not packaged-artifact or external pentest acceptance.
Next: G10 SBOM evidence producer and remaining artifact/operational acceptance.

September 28 gated container promotion (baseline `46b277c`): DeepSeek implemented
run-attempt-unique candidate tags and post-publication, gate-first channel-tag
promotion. Both promotion jobs share repository-wide serialization; stable keeps
the production environment. Integration review required explicit missing-manifest
classification, full error inspection, structured original-byte index validation,
finite timeouts and truthful unknown-state reporting. Parent verification:
295 release/Markdown tests passed, 3 Windows symlink cases skipped; focused Ruff
and whitespace clean. Commit `6e745cc` passed CI `36420360992`, attempt 2:
all five active jobs, native packaging skipped. Attempt 1's dependency audit
failed on PyPI HTTP 503; rerunning that job passed without code or gate changes.
This CI does not execute release promotion. Read-only public-registry inspection failed
with network EOF; no registry writes or release dispatch occurred. Live GHCR
copy/digest/idempotency rehearsal, package visibility and exclusive-writer controls
remain unverified. Missing gate producers and external approvals remain blockers.
Next supply real evidence producers and rehearse exact artifacts; no production
approval follows from the tooling tests.

September 28 container-promotion assessment (baseline `3bf13a6`): latest CI
`36384507864` passed; repository synchronized and PostgreSQL container healthy.
DeepSeek traced the early GHCR tag writes and their consumers. Reviewed proposal:
[Container promotion plan](../release/CONTAINER_PROMOTION_PLAN.md). Integration
review requires run-attempt-unique candidates, no pre-gate SHA alias updates,
serialized promotion and explicit external-writer controls. No workflow or
registry changes were made. Next implement the bounded promotion change with
negative tests and verify registry semantics before release acceptance. Existing
evidence-producer and external approval blockers remain; production not approved.

September 28 CI fixture recovery (baseline `2d42cc1`): CI `36360322601`
failed browser acceptance when the agent research interaction crossed UTC
midnight after job-start seeding. All four other active jobs passed. DeepSeek
revised the fixture to refresh only its labelled agent observations immediately
before the interaction, through the gated fixture process, with bounded day
rollover checks. No production history rules or clocks changed; future-dated
sample workarounds were rejected. Independently verified 67 UAT, orchestrator,
API and browser/Markdown contract tests, focused Ruff, Node syntax and whitespace.
Recovery commit `b9afd99` passed CI `36383999271`: all five active jobs,
including PostgreSQL integration and EN/ZH browser acceptance at three viewports.
Native packaging was skipped. Remaining release blockers below are unchanged;
this is not customer or production acceptance.

PILOT-C publication gates (baseline `efa7514`, September 28): preview/RC now
invoke the existing promotion validator before GitHub Release writes; G1 is
required for all published channels. Stable-only external/signing requirements
remain channel-specific. Independent verification: 237 release/client-surface/
Markdown tests passed, 3 symlink cases skipped; focused Ruff/whitespace passed.
Tests execute the real validator on missing evidence and check configured step
ordering; they are not execution of GitHub's publication runner. CI pending.
Missing G5/G8/G10 (and RC G11) producers now intentionally block publication.
Important open scope: runtime-image still pushes to GHCR before final bundle
gates. Next assess candidate-image versus promoted-image lifecycle and add real
missing evidence producers; do not exempt gates or fabricate PASS to publish.
CA-03 is code-enforced for GitHub Releases, not end-to-end release acceptance.

PILOT-B2 G1 verification (baseline `75e98a5`, September 28): same-SHA CI
evidence is now re-derived from GitHub run/job metadata, including all five
required jobs. Integration review required redirect refusal, attempt-specific
job reads with a post-read rerun check, and actions:read/token wiring on the
stable gate itself. Independent tests: 199 release/Markdown passed, 3 symlink
cases skipped; focused Ruff and whitespace passed. The hardened transport also
verified real run `36346322788`, attempt 1, for the baseline SHA with all required
jobs successful. Implementation commit `e506ff8` passed CI `36359433427`, all
five active jobs; native packaging skipped. No release was dispatched and the
publication workflow itself remains unexercised.
Remaining: preview/RC publication does not yet consult these gates; other gate
producers remain self-declared; external approvals are unconfigured. G1 verifies
source CI, not artifact installation or customer workflow acceptance. Next:
close publication-path enforcement before calling CA-03 complete.

PILOT-B1, September 28 (baseline `308797e`): DeepSeek added schema-v2 gate
envelopes, subject-aware SHA/digest checks, freshness limits, producer policy and
fail-closed handling of old evidence and NOT_APPLICABLE. Source tests remain
source-bound; they are not relabelled as artifact installation tests. Independently
ran release plus Markdown contracts: 152 passed, 3 Windows symlink cases skipped;
focused Ruff and whitespace checks passed. Commit `4d30987` passed CI
`36345939410`, all five active jobs; native packaging skipped. Normal main CI
does not exercise the release publication workflow.
This is identity-consistency validation, NOT authenticated evidence provenance:
producer and approver fields are self-declared. No external approver is configured.
PILOT-B2 must verify authoritative same-SHA GitHub run/job metadata and protect
external approval provenance; CA-02/03 are not fully closed. Release writers have
not been exercised in an actual publication workflow. No release was published.

PILOT-A implementation, September 28 (baseline `b5caa87`): operator ZIP now
contains validated release identity; both Windows entrypoints resolve it without
a checkout, pin the API image and reject conflicting bundle inputs. Review caught
and corrected config-image-ID versus registry-digest confusion in dry-run tooling,
version-prefix acceptance and tagged repository inputs. ZIP checksum stays outside
the ZIP. Independent verification: 129 release/Markdown tests passed, 3 Windows
symlink cases skipped; focused Ruff and whitespace checks passed. Tests include
actual temporary ZIP extraction and PowerShell preflight/negative identity cases.
Preflight host blockers are not installation acceptance. Commit `f018849` passed
CI `36341497382` (all five active jobs; native packaging skipped). This is normal
main CI, not execution of the release publication workflow. Release publication,
actual install/upgrade/restore and provenance binding
remain open. Next implementation: PILOT-B same-SHA/digest evidence validation.

First-customer pilot readiness (baseline `42d8144`, 2026-09-28): the single
current scope, acceptance and blocker register is
[the first-customer pilot plan](../release/FIRST_CUSTOMER_PILOT_PLAN.md). It is
a planning and read-only reconciliation document; it does not approve a pilot
or production release. CA-02/03/05/06/10 were re-checked against the code on
that date, and the pilot plan records what is fixed, what is partially fixed
and what remains open. The dated records below are historical evidence slices
kept for provenance; where a dated record and the pilot plan disagree, the
pilot plan's dated reconciliation wins.

## Commercial acceptance records (historical; not current disposition)

September 28 capacity joined-row evidence (baseline `99e56cb`): DeepSeek replaced
the whole-page capacity exemption with a two-read union comparison. Integration
review added negative controls requiring exactly one flows and one capacity read,
and changed count collection to visible text rather than a data attribute. Those
controls failed before repair; all 674 frontend tests now pass. Production build
and 17 probe/Markdown contracts passed independently. No calculation, API, schema,
permissions or stored data changed. Commit `873a9fa` passed CI `36337374074`:
all five active jobs, including bilingual browser acceptance at three viewports
and PostgreSQL integration. Native desktop packaging was skipped by main policy.
The check covers an unfiltered first page, union membership/count and empty-read
provenance, not sort correctness, later-page identity or populated live acceptance.
An empty CI fixture is explicitly reported as such, not populated-data acceptance.
Next: obtain read-only populated physical-data evidence without invented runtime
observations, or address the remaining access/research/agents acceptance gaps.

September 27 capacity disclosure implementation (baseline `d9a3971`): DeepSeek
added operating-board read states and bilingual notices using existing store facts.
Required-read failures no longer display measured-zero KPIs or a false filter-empty
claim; partial rows retain an incomplete-read notice and the existing retry path.
Integration review also hid the aggregate row count for incomplete reads. Arithmetic,
API, PostgreSQL and authority rules are unchanged. Independent verification: 668
frontend tests, production build and 17 focused Python contracts passed before the
final count-display adjustment; all 668 frontend tests also passed after it.
Commit `0956367` passed CI `36328163664` (all five active jobs), including the
injected capacity GET failure and retry recovery. Downloaded evidence reviewed:
English 1440px capacity screen shows the measured-empty disclosure; Chinese 390px
viewport has no visible overlap but its board is below the captured viewport, so
that screenshot is not visual proof of the narrow board. Native packaging skipped.
The old
capacity exemption remains until joined-row acceptance covers both input reads;
populated physical-data, storage/LNG and native desktop acceptance remain open.

September 27 capacity diagnosis (baseline `acb48c8`, CI `36296989246` passed):
PostgreSQL connectivity and revision `0036_job_records` verified. DeepSeek performed
a read-only trace; integration review confirmed that CapacityWorkspace joins flows
and capacity by point/direction, while the browser probe reads capacity alone.
The operating board renders zero KPIs and a filter-empty sentence without its own
read-lifecycle distinction. This is a confirmed disclosure gap, not proof that
populated runtime rows fail to render. Existing CI artifacts do not capture the
payload needed to prove populated capacity acceptance; seed inspection suggests
that this case is unexercised. Keep the exemption until a scoped replacement exists.
Next bounded task: disclose unread/pending/failed/partial/measured-empty states for
the operating board using existing endpoint facts; suppress misleading zero KPIs
when either required read fails. Preserve calculations, classification, thresholds,
permissions and routes. Then compare visible joined keys against both reads, with
filter/pagination-aware tests and injected GET failure/recovery coverage. Do not
infer complete capacity coverage from an empty CI fixture. Storage/LNG views and
populated live-browser verification remain separate acceptance work.

September 27 market evidence (baseline `6810b31`): DeepSeek replaced the obsolete
whole-page market n/a exemption with scoped hub-board price evidence from the
authenticated market-context projection, using the displayed gas day/product/hub.
Cards now disclose bid/ask units. Independent review corrected the as-of comparison
to use the surface's own held instant, not require two polling reads to coincide;
a regression case covers different valid read timestamps. Independent verification:
656 frontend tests, production build, and 16 probe/Markdown contract tests passed.
Commit `0ec65c4` passed CI `36296652435`: all five active jobs, including English/
Chinese browser acceptance at three viewports and PostgreSQL integration. Native
desktop packaging was skipped by the normal main-branch policy. Scope is six declared hubs and the displayed
tenor; delivery periods, newest-row selection, FX/curve tables and native desktop
remain unverified. This is not whole-market or production acceptance.

**NOT APPROVED FOR CUSTOMER PRODUCTION.** See [commercial acceptance audit](Architecture-V2/19_COMMERCIAL_ACCEPTANCE_AUDIT.md).
This bounded audit fixes release-channel inheritance, frontend release checks,
mandatory image-digest collection and customer deployment payload selection.
The local `.automation` harness is retained on disk, excluded from tracked source,
Docker context and source exports; its pre-existing local changes are preserved.
Verification: 71 release/packaging contract tests passed, three Windows symlink
tests skipped; 551 frontend tests passed, frontend build and bilingual key coverage
passed. Focused Python lint passed and the actual ZIP contains ten allowlisted files.
No new GitHub release, production deployment or full backend acceptance was run.
Worker full-suite result: 1,906 passed, 20 skipped, one sandbox-permission failure;
independent rerun of that Markdown-link module passed all three tests.
Next: bind release evidence to SHA/digest, verify immutable-image installation and
PostgreSQL migration, address service-authority gaps, then run authenticated HMI
acceptance. Supplied UAT access succeeded on September 23; see
[authenticated HMI audit](Architecture-V2/20_AUTHENTICATED_HMI_AUDIT.md).
The first pass reached Portfolio, Strategy, Decision, Research, Glossary,
Administration and numeric Market. It reproduced a blank initial Network view,
literal interpolation tokens, conflicting gas-day context and readiness labels.
Whole-product UI acceptance remains open; access itself is no longer blocked.
September 23 HMI repair: DeepSeek implementation independently reviewed. Network
layout now follows the shared resolved market task; the hidden page, conditional
shell hooks and bilingual interpolation tokens are repaired. Browser smoke no
longer exempts blank Network or React internal errors. Fresh UAT sign-in and
numeric/Network switching passed in the in-app browser. Verification: 571 web
tests, production build, locale parity and 78 focused Python contracts passed.
Desktop/mobile full-sweep acceptance is still unverified. Next priority is the
selected gas-day/projection mismatch and misleading readiness semantics.

September 24 context repair (baseline `42e4be2`): DeepSeek implemented the
projection request mapping and request-lifecycle changes; the integration review
required executable deferred-response tests and closed remaining legacy-row
overwrite paths. Market, portfolio and review requests now carry the selected
context, bind retries to one query, reject superseded responses and clear old
readings on context changes. The time-basis strip reads the backend's `basis`
field and calendar. Successful market projections replace their scoped row set;
unfiltered quote/opportunity streams do not widen it. Those rows use the existing
10-second market projection poll, not tick-by-tick stream updates.
Independent verification: 585 frontend tests, normal production build, 91 focused
Python contracts, and 42 backend projection/context tests passed (the Python
groups overlap in the trader-context module). No database writes or deployments.
Live acceptance remains open: this session has no configured PostgreSQL URL and
no local API listener; database health/schema were not inspected. The runtime
configuration/launcher path has been requested. No new screenshots or live UAT
claim applies to this repair. Backend gas day remains declared context, not a
historical valuation filter; portfolio/review do not apply hub/product filters.
Next: restore the existing test runtime, verify date/product/hub changes in the
authenticated app, then address misleading readiness and per-slice filter
disclosure. Global monitoring streams remain operational feeds, not scoped
projection evidence. Keep commercial release disposition NOT APPROVED.

September 24 continuity follow-up (baseline `796b734`, current with origin/main):
DeepSeek repaired the runtime-availability wording across Market Overview,
the header and Settings. Runtime provenance now says "Runtime data available"
or its partial/delayed/unavailable/unknown equivalent, not overall "Ready".
Per-row freshness, projection degradation, permissions and backend behaviour
are unchanged. Independent checks: 589 frontend tests, production build, 28
focused Python contracts passed; locale parity passed. Longer badge labels still
need live responsive verification. No PostgreSQL URL is configured in this run.

GitHub CI for `796b734` was inspected, not assumed green: run `35888959943`
passed web build/tests, PostgreSQL integration and dependency audit, but failed
browser acceptance. Its evidence covers 96 checks (16 surfaces, EN/ZH, three
viewports), with 33 failure entries. The network rail is not keyboard-focusable;
the harness also reports lingering loading states and missing rendered rows,
and `/api/contracts/upstream?limit=5` returns 404. Distinguish real application
failures from stale probe assumptions before fixing either; do not add exemptions.
Next bounded milestone: diagnose these browser-acceptance failures from the
downloaded evidence (`output/ci-35888959943`, ignored local files), repair the
smallest coherent group, and rerun the same gates. The previous local-runtime
blocker does not imply GitHub's PostgreSQL service failed. Production remains
NOT APPROVED. No release or deployment was performed.

September 24 local PostgreSQL recovery: the existing Docker PostgreSQL service
is healthy and the API connection has been restored. The earlier missing URL
was a missing application-process configuration, not a failed database. Read-only
validation confirms connectivity, no missing required tables and revision
`0036_job_records`, equal to Alembic head. No migration or market-data write was
performed. A machine-local, Git-ignored launcher at
`.automation/runtime/start-local-api.ps1` obtains the existing container settings
in memory, validates the database and starts the development API on loopback;
`-ValidateOnly` checks the connection without starting another API. No credentials
are stored in the launcher or this checkpoint. `/api/health` now returns healthy
with authentication enforced. The previously supplied UAT username is not
provisioned in this database; a different active analyst identity exists. Await
the user's choice of that existing identity versus explicit UAT administrator
provisioning. Do not silently create roles, widen scopes or disable authentication.
This resolves the database connectivity blocker, not authenticated UAT acceptance.

September 24 local UAT identity milestone (baseline `0e3a84c`): on the user's
explicit request, six test principals were provisioned in the existing local
PostgreSQL database. One combined-role account covers all five work modes;
five separate role accounts exercise VIEWER, ANALYST, REVIEWER, OPERATOR and
ADMIN boundaries. This supersedes the preceding awaiting-user account decision.
Credentials are encrypted with Windows DPAPI outside Git at
`%LOCALAPPDATA%\EurogasNexus\uat\credentials.clixml`; usage instructions are in
the adjacent local README. Role API keys expire after 30 days. No secrets are
tracked and no market data or schema was changed.

Provisioning exposed a real persistence defect: generated API-key display
prefixes were 24 characters, exceeding PostgreSQL's 16-character column.
The generator now respects that limit; bearer identity, secret hashing and
authentication semantics are unchanged. A regression test checks the mapped
column constraint and confirms the resulting bearer still parses and verifies.
Focused identity tests: 17 passed. Real HTTP checks verified browser sign-in,
all six experience profiles, connected runtime database at revision
`0036_job_records`, ADMIN-only denial of commercial market reads, ANALYST denial
of user administration and ADMIN-only access to user administration.

These are identity checks, not whole-product persona acceptance. A combined-role
market projection exceeded a 30-second request timeout with 853,376 stored quotes;
investigate query performance without weakening entitlement or freshness rules.
Next: resolve the recorded browser-acceptance failures and reproduce this slow
market read. Production remains NOT APPROVED. No customer release was performed.

September 24 browser-acceptance repair (baseline `bbb6499`): DeepSeek repaired
two confirmed defects; the integration review preserved all acceptance gates.
The scrollable network tabpanel is now keyboard-focusable with a token-based
focus ring. The contracts probe now calls the existing client upstream-terms
route, `/api/route-cost/upstream-contracts`, instead of causing its own 404 at
an undeclared path. A new contract test checks every probe against served GET
routes and the workspace inventory. No loading exemptions, security changes,
database changes or market semantics changes were made.
Independent verification: 591 frontend tests, production build and six focused
Python probe/link tests passed. Worker verification additionally passed 480
contract tests; its one sandbox file-permission failure passed on independent
rerun. Latest baseline CI `35944266857` passes validation, PostgreSQL integration,
dependency audit and web build, but browser acceptance still fails. A fresh
browser run is required for this repair; unit tests are not visual acceptance.
Remaining: loading/read-to-render failures and market projection latency. The
orders probe still reads legacy live-summary rather than the portfolio projection;
whole-page empty-state matching may confuse partial data with no rendered rows.
Resolve these by measuring the actual surface, not exempting missing content.

Post-push browser verification at `af8884d`, CI run `35966584093`: all 96
EN/ZH desktop/mobile checks executed. Zero axe violations and zero horizontal
overflow; the network focus defect and probe-generated contracts 404 are absent.
Validation, PostgreSQL integration, dependency audit and web build jobs pass.
Browser acceptance remains FAILED with 27 functional failure entries: lingering
loading checks on network/capacity and read-to-render checks on contracts,
orders, runtime and settings. Correcting the contracts endpoint exposed that
surface's previously unmeasured read-to-render check; this is not a full pass.
The deterministic agent-research fixture completed its evidence chain. Artifacts
are saved locally under `output/ci-35966584093`; the network desktop screenshot
was independently inspected and still shows contradictory runtime-disconnection
copy alongside PostgreSQL-backed data. Next task must reconcile actual loader
state and scoped render assertions with these screenshots. Release remains blocked.

September 24 runtime-loader repair (baseline `ea8c9a4`): DeepSeek traced the
contradictory Network disconnection copy to an unanswered nullable status slice,
and workspace-loading copy to a shared flag also raised by optimiser actions.
Runtime status now distinguishes unknown from confirmed unavailable. The workspace
batch has separate in-flight/committed state, cleared on identity reset; Network
and Glossary use that lifecycle instead of unrelated action activity. Diagnostics
also uses committed reads rather than inferring completion from availability.
Panel loading copy names its own read. The browser gate waits at most 20 seconds
for the workspace batch to settle and records a failure if it never settles;
no acceptance exemptions were added or removed.

Integration review required actual-store deferred-response tests, not only source
assertions: pending/commit, failed status read, unavailable/healthy answers,
unrelated action activity, supersession and revoked identity are covered.
Independent verification: 605 frontend tests, production build and 39 focused
Python contracts/link tests passed. No API, database, permission or calculation
changes. Fresh CI/browser verification remains pending at this checkpoint.
Known limits: other runtime-status cells still collapse unread into unavailable;
the batch retains its existing multi-read commit barrier; market projection
latency and page-wide read-to-render assertions remain open. Production is NOT
APPROVED, and test progress does not authorize customer release.

Fresh verification at `2c05f14`, CI run `35996627042`: 96 browser checks ran
with zero axe violations and zero horizontal overflow. Functional failure entries
fell from 27 to 9: contracts (three) and orders (six), all read-to-render checks.
No workspace-settlement timeout or lingering-loading failure was reported.
Validation, PostgreSQL integration, dependency audit and web build all passed;
browser acceptance remains FAILED. The downloaded Network desktop screenshot
was independently inspected: resource paths now show 2/2 with explicit indicative
corridor disclosure, replacing the false disconnected message. This does not
certify map geometry or every page's usability. Evidence:
`output/ci-35996627042` (local ignored artifacts). Next bounded task: inspect the
actual Portfolio/Orders rows and replace demonstrably stale whole-page probes
with scoped assertions and negative tests, fixing any confirmed rendering defect.
Market projection latency and remaining unread-status cells remain open.

September 25 portfolio acceptance measurement (baseline `f5d6455`): DeepSeek
replaced the contracts/orders whole-page empty-copy heuristic with scoped record
comparison. The old orders probe read an aggregate rather than the projection;
legitimate unavailable fields were mistaken for absent rows. The probe now reads
the actual portfolio projection, and existing rows carry nonvisual record-ID
attributes. Integration review rejected substring matching and generic empty
selectors: comparisons now use exact IDs within each declared row group, explicit
empty markers, deduplicated visible DOM evidence, and failures for malformed or
unidentifiable returned rows. Negative tests cover wrong/missing/hidden/duplicate
rows, overlapping selectors, stale rows on empty reads and legitimate n/a fields.
No data was fabricated, no permissions changed and no exemptions were added.
Independent checks: 625 frontend tests, production build and 13 focused Python
probe/link/UAT tests passed. Fresh browser verification is pending. Empty CI
orders/PnL fixtures cannot prove populated-row browser workflows; that limitation
remains explicit. Market latency and other commercial-release gaps remain open.

Post-push verification: browser run `36032330807` at `69dd695` completed all
96 checks with zero failures/axe violations; six declared functional gaps remain.
Its validation job caught an integration packaging omission: ContractWorkbench's
record/empty-state markers were left unstaged. They were included in `c8c260f`,
and CI run `36033183882` then passed all five active jobs, including browser
acceptance, PostgreSQL integration, validation, dependency audit and web build.
Desktop packaging was skipped by the normal main workflow; no release was built.
The green browser gate covers the seeded workload, not populated Orders/PnL
acceptance or closure of declared gaps. Next: investigate the local market-read
latency and strengthen populated-persona workflows without inventing market data.
Commercial production approval remains blocked by the audit's open requirements.

September 25 market latency repair (baseline `5919d81`): independently reproduced
an authenticated local market-context timeout at 45 seconds. DeepSeek replaced
the projection's unbounded observation materialization with a SQL-entitled,
ordered, bounded read plus aggregate counts, preserving the existing response
contract. Restricted sources are excluded before the row limit; raw totals retain
their existing meaning. FX normalization builds its latest-rate graph once per
view, while single-row helpers retain invalid/same-currency fast paths. Tests
compare payloads and numerical results with the reference behaviour. No shared
cache, schema change, migration, new datastore or runtime price write was added.

The new read-only measurement harness isolates every statement in its own
transaction, bounds server/driver timeouts and does not print the database URL.
Its initial failed-query recovery bug was caught on real PostgreSQL and repaired
with regression tests. Independent verification: 56 focused tests and repository
lint pass; all 14 PostgreSQL plan probes completed. On this machine, the original
unbounded observation plan read 856,534 rows in 3,360 ms; the bounded plan read
500 in 0.363 ms (SQL plan times, excluding Python transfer/shaping). After restarting
the local API with the repair, three authenticated HTTP reads succeeded in
5.910, 4.736 and 5.094 seconds. A follow-up read confirmed 500 observation,
500 normalized and 500 quote rows, plus other populated slices. These are warm,
single-client measurements, not production load acceptance. Only six FX rows
exist locally, so FX graph reuse is not the primary explanation here.

Remaining cost includes the source-coverage window (~3,336 ms), gas-source count
(~786 ms) and opportunity read (~751 ms) in this measurement. Future optimization
must preserve coverage/entitlement/time semantics and measure concurrency. Fresh
CI is pending; commercial production approval remains blocked.

September 25 source-coverage performance (baseline `8e5059a`, verified green
CI `36066122675`): DeepSeek implemented bounded per-source reads using the existing
source/time index. Daily-source reservations, entitlement-before-limit and global
caps remain. Integration review rejected a new tie-break and newest-reservation
selection rule; the original window algorithm is retained when candidate sources
exceed the payload bound. Existing full-key tie ambiguity remains explicit rather
than claimed as deterministic equivalence. No schema, permission or data changes.
The per-source approach trades whole-history ranking for one query per source;
many-source and non-gas-source cases require deployment-specific measurement.

Independent checks: 67 focused repository/projection/entitlement/API/harness tests
and repository lint passed. Real PostgreSQL plan comparison on five sources:
old count/window statements total 4,035.359 ms; new per-source statements total
0.601 ms. These are server plan times, excluding network and application work.
Four authenticated market-context requests at concurrency two took 7.103, 7.105,
5.556 and 5.596 seconds before this change; after restarting the same local API,
they took 1.838, 1.838, 0.939 and 0.927 seconds, each with 500 observations and
500 normalized rows. Cache warmth and the small sample preclude a production SLA
claim. No live prices were fabricated. See the indexed operational note
`docs/operations/SOURCE_COVERAGE_READ.md` for limits and fallback semantics.
Fresh CI remains pending. Next: verify this commit's CI, exercise populated persona
workflows and close the declared functional gaps. Production approval remains open.

September 25 glossary acceptance (baseline `7573161`, CI `36090533294` passed):
DeepSeek replaced the stale glossary loading exemptions with exact visible term-ID
checks and a browser interaction that selects a different term, verifies its wiki
definition, and exercises search. The earlier loader repair had removed the
recorded loading symptom; this task strengthens evidence rather than claiming a
new rendering fix. The component gains nonvisual record/empty-state markers only.
Independent checks: 630 frontend tests, production build and 17 focused Python
probe/link/glossary tests passed. Fresh browser verification is pending. Index
checks cover both languages and three viewports; the definition/search interaction
currently covers English desktop only. Other declared gaps remain unchanged.

Post-push verification at `01210a0`: CI `36110246148` passed all five active jobs,
including the EN/ZH three-viewport sweep and new glossary term-selection/search
interaction. Glossary loading is no longer exempted. Desktop packaging remains
skipped on this main run; no release or production approval is implied. Next:
inspect and replace the remaining market/source acceptance heuristics with real
row evidence, then continue populated persona workflows and release audit gaps.

September 25 Source Center acceptance (baseline `5285a11`, CI `36110841498`
passed): DeepSeek replaced the sources copy-based exemption with exact registry
record comparison. The default priority queue is a filtered view, so acceptance
switches to the catalog for the unfiltered comparison and restores the prior task.
New negative tests reject missing, hidden, foreign and stale rows. A read-only
browser interaction verifies source selection/detail and reversible category
filtering. Product changes are nonvisual data attributes only; no provider action,
credential update or ingestion write is exercised. Independent checks: 636 frontend
tests, production build and 12 focused Python probe/link tests passed. Fresh CI
browser evidence is pending. A failed source registry read still lacks dedicated
surface error copy; do not treat a seeded acceptance pass as that error-path test.

September 27 continuity verification: resumed the unfinished CI verification,
not a second implementation worker. Run `36137985501` at `3786690` passed all
five active jobs, including the Source Center catalog comparison and selection/
category interaction in browser acceptance. Desktop packaging was skipped by the
main workflow. Fetched origin and confirmed local HEAD matched main; the local
API still answers healthy with authentication enforced. No intervening heartbeat
is claimed as completed development. This closes the Source Center measurement
milestone, not its registry-failure UX or production approval. Next bounded task:
expose source-read failure distinctly from an empty registry, with retry and
permission-preserving tests; then strengthen the remaining market acceptance
checks and populated persona workflows. Commercial release remains NOT APPROVED.

September 27 source-read failure UX (baseline `a98d32a`): DeepSeek added distinct
unread/pending/failed/measured-empty states to Source Center using existing store
facts and retry infrastructure. Unknown reads no longer print zero-source KPIs.
Retained rows on a failed refresh carry a last-reading disclosure. Integration
review separated an empty filtered queue from an empty registry and labelled the
existing retry accurately: it retries failed workspace reads, not only sources.
No backend, permission, database or ingestion behaviour changed.
Independent checks: 646 frontend tests, production build and 13 focused Python
probe/link tests passed. The new browser test injects a GET-only registry failure
and requires the surface to recover through its retry after interception is removed.
Fresh CI/browser verification is pending; error-path interaction is English desktop,
while normal acceptance retains both languages and three viewports. Production
release remains NOT APPROVED.

Post-push verification: CI `36281436601` at `4cdb695` passed all five active
jobs, including the injected registry failure and successful retry interaction.
The normal catalog/selection/filter and glossary checks continue to pass.
Desktop packaging was skipped; no release was produced. Next bounded task:
replace the remaining market copy-based acceptance exemption with actual quote
and price-basis evidence, retaining honest missing-data and entitlement states.

## Historical programme state
V2 pack version: 2026-09 autonomous runner
Current wave: Waves 0-10 have delivered slices. Wave 11 (RC/GA readiness) has not started.
Wave status: DELIVERED_AND_VALIDATED for every slice listed under "Completed tasks"; the open halves are named under "Deferred / known gaps".

## Accepted architecture decisions

- V2 documents under `docs/engineering/Architecture-V2/` define target direction; repository truth defines current implemented behaviour.
- Modular monolith + worker runtime remains the default product architecture.
- **ADR-0016 (Decision 15)**: Architecture V2 is the binding target architecture and the product-experience interaction authority; the Professional UI Constitution keeps visual authority. RFC-0001 and Decision 14 history preserved.
- Functional assignment and work mode never grant backend authority; composition is not permission.
- Platform administration is not commercial-data access: `ROLE_PERMISSIONS[ADMIN]` is the platform bundle and `api/dependencies/commercial_access.py` enforces the boundary per request.
- **AI runs under the caller's own authority** (rule 22): `api/dependencies/ai_authority.py` re-authorises every direct provider invocation, and the capability runtime keeps re-authorising registry invocations.
- A projection is never wider than the endpoint it composes, and a client reads one projection instead of joining endpoints.

## Completed tasks

- [x] **Wave 0** — client inventory (accepted after repair), backend access inventory, conflict register, Wave 0 gate (passed), ADR-0016, architecture fitness tests.
- [x] **Wave 1** — shell, Active Context, workspace-pattern and panel registries, action geography, canonical AI actions, Inspector contract, command model, HostCapabilities; machine-readable under `clients/web/src/app/experience/` and `clients/web/src/app/host/`.
- [x] **Wave 2** — capability catalogue and `ExperienceProfile` (`security/capabilities.py`, served in `GET /api/me`), platform-administration/commercial-data separation, client composition parsing (`W2-01`).
- [x] **Wave 3** — capability-gated Administration surface, restricted control-plane notice, preserved deep links (`W3-01`).
- [x] **Wave 4** — Data Product catalogue, Analysis Snapshot v1 (`0034_analysis_snapshots`), and the snapshot citation carried by the route-cost recommendation (`W4-01`); the citation now reaches every run path a client surface actually runs — the resource-pool optimisation, the strategy backtest, and (this stretch) the analysis query and the portfolio report, each verifying the reference before it does any work, echoing it only when one was supplied, and recording it durably (the analysis record's own output snapshot, the tracked `REPORT` job). The analysis path verifies before loading its snapshot and before any provider call, so an unverifiable citation cannot be paid for with an external request. The client half followed: the review task lists the deployment's recorded snapshots, **records one** from the Active Context it is showing (only the context keys the backend accepts, refused without a runtime database or anything to freeze, and the list re-read from the backend rather than appended to optimistically), and cites the chosen reference on the report run - rendering the citation from the response and composing no reference of its own. The Data Product catalogue also has the consumer it lacked - a Data Products view on the research surface that keeps the contract's three provenance states apart (measured / restricted / unmeasured), never prints a zero in place of a withheld block, and shows an unrecognised state as its own code. The source surface no longer recommends an action it cannot perform: where the platform's own recommendation is the ingestion run, the control that queues it (`POST /api/sources/{id}/run`) is beside that recommendation, blockers limited to the states where there is nothing to ask for and the platform's guards (credential state, an open circuit, workflow readiness) disclosed rather than used to hide the act.
- [x] **Wave 5** — application projections: MarketContext, PortfolioSnapshot, ReviewContext, ScenarioContext under `/api/projections/*`, with the market and portfolio read layers extracted so routes and projections call one implementation (`W5-01`).
- [x] **Wave 5, client half** — the market lane reads `GET /projections/market-context`, the workspace batch reads `GET /projections/portfolio-snapshot` once (filling `portfolioSummary`, `screenOrders`, `pnlSnapshots` and `resourcePoolOptions` from its slices), and the review task reads `GET /projections/review-context` on demand through a dedicated, identity-gated and coalesced review lane. `app/model/projectionModel.ts` owns one definition of a slice reading; `ProjectionContextStrip` renders it for all three surfaces. Retried projections re-derive every field they feed through `PROJECTION_LANE_APPLIERS`, and market query parameters are sent with the snake_case names the routes declare. `ScenarioContext` is deliberately available but unconsumed (its read inputs already arrive in the batch, and the scenario surface is driven by the deterministic run endpoints).
- [x] **Wave 5, resource-pool follow-up** — the pool composition moved to `application/resource_pool.py`; the route and the `resources` slice call it, byte-identity was measured against the pre-change module, and the slice filters entitlement before composing so it stays strictly narrower than the route.
- [x] **Wave 6** — Decision Case domain, persistence (`0035_decision_cases`), API, client contract and product surface; a case cannot be decided without evidence and the actor is the authenticated identity. The chain's `AI Findings/Challenge` stage is citable too: `DecisionEvidenceKind.AI_ANALYSIS` holds a Copilot run by reference, offered from the run the identity just completed (`W6-01`).
- [x] **Wave 7, first slice** — the five canonical AI actions (Ask, Explain, Compare, Challenge, Draft) became real product surface: a Copilot reachable from the mounted command palette, gated by `aiActionIsAvailable`, carrying its posture, evidence references and the decision-support markers, running over the existing analysis route, and recorded as an observable run with no hidden-reasoning field. Every competing AI affordance was converged onto that contract: the alert drawer's ad-hoc question is the `ask` action, the market cockpit offers the five in its rail, and the review task's own analysis panel lost its question box and provider switch, leaving the deterministic report run beside the canonical five (`W7-01`).
- [x] **Wave 8** — product error taxonomy with the additive API error envelope, now covering **unexpected** failures too (the `internal` SYSTEM code, an always-present correlation id, the exception's own message never exposed and the traceback still logged); the unified Job model (`0036_job_records`) now tracks **every run family V2 names**: ingestion runs, dataset builds, resource-pool optimisation, strategy backtests, portfolio reports, governed agent research and snapshots - the ingestion path needed one addition to the seam, since work that reports failure in its return value rather than by raising can state the outcome on the handle (`W8-01`, `W8-02`).
- [x] **Wave 9, first and second slices** — the canonical Inspector region and the mounted command palette, then real Inspector detail: `app/model/inspectorDetail.ts` resolves facts and provenance from data the identity already received, presents rather than computes, treats absence honestly, and refuses a hand-over the page's composition does not declare. Every hand-over goes through one composition-checked builder (`inspectorSubjectFor`). Six surfaces are migrated: the market cockpit hands over its focused observation, the contract workbench a saved contract, the network map a clicked node, the strategy backtest the selected run, the review decision history the evidence behind a decision (including evidence the backend withheld, which stays inspectable with its reason) and the capacity point panel the point's observation record. The shell also stopped intercepting a page: every page now composes through the workspace renderer, and the legacy `orders` deep link opens the view it names (`W9-01`).
- [x] **Wave 10, contract slice** — the desktop workstation contract: window profiles that are layouts rather than authorities, capability-gated windows with a documented fallback plan, a notification payload that structurally cannot carry a commercial value, deep links that refuse authority parameters, an unambiguous shortcut model and an allowlisted diagnostics bundle (`W10-01`).
- [x] **Wave 10, diagnostics consumer slice** — the bundle contract now has the consumer it lacked: `app/host/diagnosticsBundle.ts` composes it from facts the client already holds (through `buildDiagnosticsBundle`, never around it) and reports a declared field it had no fact for as **unavailable** rather than as a zero; the file name reads only an ISO-8601 instant; the handover is a download in both hosts, with the desktop host's declared-but-unimplemented native export said out loud instead of offered; and the panel beside the activity timeline shows every field that would leave before it leaves (`W10-01`).
- **Wave 7, second slice** — the governed research run converged onto the same rules the five canonical actions follow, without becoming a sixth AI entry point: the action is now the research workspace's primary action (a `compute` consequence, disabled by a rule that mirrors the route - objective 8..4000 characters and a reachable runtime PostgreSQL, which the run needs because it persists its own rows), the request no longer names a profile the client has no basis to choose, and the surface states before the run what strategy generation does (freezing a StrategyVersion and backtesting are human acts, so such a run stops for human confirmation) plus what holds for every run (planned analyses are validated against the caller's own data scopes, and the profile is recorded by the runtime). Still open: the capability-invoke surface and the profile catalogue have no client consumer (`W7-01` section 14).
- **Wave 7, fourth slice** — the run's profile became a truthful label or it is not accepted. The route took any string up to 32 characters and recorded it on the run *and* in its job's scope while the published catalogue validated nothing, so a run could be filed under a profile the runtime does not have; it is now refused with `422 agent_profile_unknown` against that same catalogue. And a run could carry a profile whose declared stages it never entered, which reads as evidence of a pipeline that did not run: the outcome records the stages it reached and warns `PROFILE_STAGES_NOT_REACHED:<stage,…>` for every declared stage it did not - reported rather than refused, because stopping short is often the honest outcome. The same audit found two more accepted-but-ignored inputs: a supplied `strategy_ir` was dropped by the orchestrator while the pipeline drafted its own candidate, so it is now refused (`422 strategy_ir_not_accepted`) with the strategy registry named as the path that owns a specification; and a *deferred* backtest was recorded as a reached stage, so `BACKTESTED` is now recorded only when the backtest produced a run (`W7-01` section 15).
- **Wave 7, fifth slice** — the analysis and report requests stopped declaring selections the pipeline cannot apply. Six fields were accepted and never read: `selected_terms`, `selected_assets`, `selected_contracts` and `include_sections` on `POST /api/analysis/query`, and `portfolio_id`, `selected_resources`, `selected_contracts` and `selected_strategies` on `POST /api/reports/portfolio`. A caller naming a portfolio therefore received a report over the whole entitled snapshot, and a caller naming sections received the task's full section set, with nothing saying so. Both routes now refuse a non-empty selection with `422 analysis_selection_not_supported`, naming every offending field and pointing at `question` as the place a reference travels - raised before the snapshot is loaded, before the run is tracked and before any provider call, so a refused selection costs nothing. The client followed: the report payload no longer invents three glossary terms and two assets the analyst never chose, the Copilot no longer mirrors its evidence references into a selection field (they are already inside the composed question, which is the prompt the platform records), the tracked `REPORT` job records the scope it really had instead of `scope_refs` from a field that never scoped it, and `AnalysisRequestDTO` declares only fields the platform accepts (`W7-01` section 16, both contract-evolution policies). The refusal is catalogued in the product error taxonomy (`analysis_selection_not_supported`, VALIDATION, `after_user_action`), so a client classifies it instead of reading a raw 422.
- **Claim audit of the wave records (W0-04)** — every normative claim in `W0-01`…`W0-10` was checked against the code by three auditors working claim by claim (roughly 320 claims, about 295 verified as written). Eleven findings were real and are fixed: the product error taxonomy never reached a client surface (the transport kept only `detail`, so a 403 `entitlement_denied` read as a generic SYSTEM fault and the correlation id could never be quoted) and 46 catalogued error codes reached users as raw `errors.…` keys, both closed by carrying the whole envelope on `ApiError`/`ApiFailureDTO`, reassembling it in `describeFailure`, resolving presentation keys through `presentError` (never a raw key), and defining the 92 per-code entries in both locales; the data-product `unmeasured` state was unreachable because an entitled product always received a provenance block, so a deployment with no runtime database printed `0` for a product nobody counted (the catalogue now distinguishes *could not measure* from *measured zero*); a blocked research run carried its profile with no `PROFILE_STAGES_NOT_REACHED` note because the note ran on the happy path only (now derived where the run state is written, so every exit carries it); deep links refused an authority parameter in the query but never inspected the fragment; the `SNAPSHOT` job family was declared but never tracked (`POST /api/analysis-snapshots` now opens one); the prune script carried the oldest represented instant without printing it; two of `COPILOT_BOUNDARY`'s eight entries were literals rather than derived from `AI_INVARIANTS`; the Decision Case migration's "applied on SQLite" verification did not exist (it does now); and two register entries overstated their state (C8's "every direct provider invocation", C11's "no unmounted component" and its stale 131/21/52 census, which is 134/20/51 and still lists a method the Wave 7 slice now calls). The stale-but-true-when-written claims were corrected where they are read as current state (C3's hold, the Wave 0 gate's "5 primaries", `W4-01`'s ten products/citation row/client-unchanged line, `W5-01`'s path bound and test count, `W6-01`'s schema revision, `W9-01`'s "no deep link changed" and palette bullet, `W10-01`'s panel location and notification-copy bullet). Two findings are recorded rather than resolved, because both need the owner: `StrategyShadowRunTerminal` is still unmounted, and the headless `monitoring-worker` invokes the provider with no authority binding (**D7**). See `W0-04` for the method, the full list and what was deliberately left as written.
- **Live PostgreSQL verification, and a suite that no longer depends on the machine** — the environment had a Docker daemon and a running PostgreSQL 16 container all along, so four items this checkpoint listed as *not run* were run. The migration chain was applied to the live database for real: `python -m alembic upgrade head` moved `0033_market_obs_order_indexes` → `0036_job_records` in one transaction on PostgreSQL, and `python scripts/ops/validate_runtime_db.py` then reported all 93 required tables present and none missing. The whole suite was run against a scratch database at head: **1807 passed, 1 skipped, 0 failed**, including the 16 store-gated integration tests that only run when a database is configured (the migration's own up/down round trip, the required-table contract, DB-backed API reads, audit and raw-archive write/read-back, enterprise identity and sessions, research row entitlement and export denial, and the dataops scheduler's claim/finalize with its unique index). The automated backup/restore drill ran end to end: a 52.5 MB custom-format dump of the live database restored into an isolated database, verified at revision `0036_job_records` with every required table present, 80,545 ingestion runs and the audit rows restored, and a DB-backed API smoke answering 200. Running the suite that way exposed three defects that reading could not: `tests/conftest.py` now removes the ambient runtime-store variables for every test outside `tests/integration` (about twenty suites assert what the platform does with the store *they* configure, and a workstation pointing at a live deployment made them fail for the wrong reason - the policy `docs/operations/LIVE_POSTGRESQL.md` already stated, now enforced); one integration test wrote a fixed archive id and so failed on its second run against a persistent database (the archive is append-only, so it writes a fresh id per run now); and the migration preflight script crashed on the current tree (see `W0-04`). **Lint is out of the "not run" list too**: `ruff check .` is clean, which it was not - the tree had drifted ~409 findings away from the gate `docs/engineering/CODING_STANDARDS.md` and `.github/workflows/ci.yml` both declare.
- **Browser/accessibility acceptance, run for the first time in this environment** — the whole-product sweep (`scripts/uat/browser_workflow_smoke.mjs`) needs a seeded UAT runtime, a dev API on `:8000`, Vite on `:3000` and Playwright, and none of it had ever been run here; the CI `browser-acceptance` job that runs exactly this was therefore unverified, and it turned out to be **red**. Two defects, both found by running it and neither visible to any source-text test: the sweep clicked `button.button.primary` inside the agents view for the research run, a class the run button never had (Wave 9 moved every primary action into the workspace header's primary slot), so the run could not be started at all and the sweep died on a 30-second timeout racing another - it now targets the slot's `[data-primary-action]` mark, waits for the action to be usable and reports the blocker the button shows; and **strategy, research and agents each rendered two top-level headings**, because Wave 9 gave those three workspaces a header of their own while their pages stayed declared `local-tabs` (the shell also renders the page heading there). The registry stays the single owner of that rule: `workspaceHeaderTitleLevel(page)` returns 2 for a `local-tabs` page, `WorkspaceHeader` renders the workspace title at that level, and the three surfaces now render a section heading under the shell's page title. After the fix the sweep passes: **96 checks (16 workspaces × EN/zh-CN × 3 viewports), 0 failures, 0 axe violations, 0 horizontal overflow**, plus the agent-research end-to-end interaction (a governed run reaching `READY_FOR_HUMAN_REVIEW`, its artefact chain complete, the review pack confirmed through the API, and the run re-read from `/api/agent/runs`).
- **CI on `main` had been red for 95 consecutive runs, and is green again** — checked against the GitHub API rather than assumed: the last successful run before this stretch was **351** (`7a07b965`, 2026-09-16), and runs **352–446** all failed. Two jobs were persistently red, and each was a gate the programme's own documents declare green: **`validate`** (which runs `ruff check .` — the ~409 lint findings, fixed in this stretch) and **`Browser acceptance`** (the stale primary-action selector and the duplicate page heading, also fixed here). Run **447** at `0c34959` is the first green run since: `validate`, dependency audit, PostgreSQL integration, Web build/tests and browser acceptance all succeeded together. The `docs/ux/UI_DEBT_REGISTER.md` entry that recorded a passing current-ref browser run was true when written (at `b2c46c0`, before the Wave 9 header migration) and stayed in the register while the job failed on every commit after it.
- **Security finding C13, resolved on discovery** — a trader review decision took its actor from a **request body field** and used it both as the persisted actor and as the audit event's principal, so a caller could attribute a governance act - and its audit trail - to somebody who never made it, while the Decision Case path already resolved its actor from the authenticated identity. The rule now has one home (`api/dependencies/acting_actor.py`) that both paths call: the stored decision and every audit row name the authenticated identity, the request's `actor` is accepted only for compatibility and never used, a disagreeing claim returns an `ACTOR_CLAIM_IGNORED:<claim>` envelope warning instead of being believed, and a deployment with no verified identity records its own public-API principal. The client half followed: the review workspace offers no actor field and sends none, and the agent review gate sends none either. See the reconciliation register for the full record.
- **Wave 7, third slice** — the capability-invoke path was repaired at the seam: the public route accepted `human_confirmation`/`confirmation_note` and dropped them, so `CapabilityRuntime.invoke` always saw an unconfirmed caller - every `HUMAN_CONFIRMATION` capability was permanently uncallable through the route while the caller was told to confirm. The values now reach the invocation context, `HUMAN_ONLY` stays refused even when confirmed, and the invoke body has no field in which a caller could claim a principal, role or scope. The builtin catalogue declares no capability under either policy today, which is why the dead end went unnoticed; the tests exercise both through capabilities registered for the test. The **surface** followed: the agents workspace's capabilities view now offers invocation - target, arguments, the confirmation its policy requires, the blockers it faces, and the runtime's own result including a `BLOCKED` one with its stable code - gated by the same rule the panel lists and run from that view's primary action in the workspace header. Still open: the profile catalogue has no consumer, and a client-chosen profile would be a label rather than a capability until the runtime executes what it declares.
- **Security finding C8, direct-LLM half and MCP posture** — every direct provider invocation is re-authorised against the caller's own `analysis.query` capability (403 `ai_authority_not_granted`), the alert-analysis path is policy-gated rather than READ, the analysis provider path fails closed with an audit record, the alert run is attributed to the identity it ran under, and MCP's pseudo-principal no longer defaults to a wildcard data scope. Every MCP tool now declares and publishes its authorisation posture, and a call that runs outside the capability runtime is audited rather than silent. The agent documentation states the limits it used to overstate: MCP runs as a deployment-configured service identity, not the calling user, and the legacy MCP tools are not re-authorised per user.
- **Security finding C5, runtime posture, and owner decision D1 delivered** — `GET /api/health` and `/api/health/live` report `authentication: enforced | anonymous_allowed`, and the value is no longer derived from a profile's own opt-out but from the deployment's: every profile identifies its callers, and the one way to trust the network is `EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS`, which the payload then states out loud. The delivery is recorded in full in `W0-03` D1: one exemption list consumed by both gates (`api/dependencies/exempt_paths.py`), a `require_identity` that never overwrites an identity another layer resolved (which is what made the earlier attempt widen a governed read), the twelve undeclared internal paths declared at the floor their routes already enforced, and the harnesses updated to present a credential. Evidence: `pytest -q` **1848 passed / 17 skipped** (no store), the projections parity test unchanged and green, `tests/security/` green including the new exemption, opt-in, backstop and acting-operator tests, and the browser acceptance sweep green under the new posture (`ok: true`, 96 checks, 0 failures, 0 axe violations, 0 overflow) whose API log holds exactly one refusal - the pre-login `GET /api/me`. That sweep is also what caught the delivery's second behaviour change: demanding the operator-principal header from an *authenticated* caller made the browser's administration reads 401, so an authenticated caller is now the acting operator (its own name is the actor) and only the compatibility deployment-token caller must name one.
- **Owner decision D3's follow-on: the two optimisation families (C14) and the desk engines the product could not reach** — the owner agreed to converge the optimiser surface, and the record is `W0-03` D8. The finding was measured, not assumed: `/api/optimization/*` (seven engines, the platform's only `RUNTIME_DECISION` context and its only optimisation run-evidence read) had **no client method and no path literal anywhere in `clients/web/src`**, while the product runs the older `/api/route-cost/*` family, which uniquely carries Wave 4's Analysis-Snapshot citation and Wave 8's job tracking. The first reading of that - "the same engine behind both" - was wrong and is corrected in the record: they share one *operation* (pool optimisation) and each side holds a capability the other lacks. The ruling is per operation: the newer family owns runs that need runtime context or run evidence; the older pair stays canonical **until** the newer one carries the same two invariants, which is the condition for collapsing the overlap; reads and the contract write stay where they are; and the four twin-less engines are the surface gap. `tests/contract/test_surface_reachability.py` now runs the census that only ever ran one way (public path → reached by the web client, declared a machine surface, or declared deliberate with its reason), so the 36 unreached paths are a declared state rather than an accident, and both fields of the overlap name each other in their docstrings. **Then the desk slice:** nomination windows and storage dispatch - the two engines with no twin, and the two a gas desk decides with - are now the Decision workspace's `Nomination` and `Storage dispatch` tasks, each the primary act of its own task, each rendering the engine's own answer (per-instruction window and reason; per-period inject/withdraw/inventory/cashflow), each wired to the run-evidence read so a run can be re-read, and each saying "No run record" with its reason when the deployment has no runtime database. They are assessments and say so: neither submits a nomination, a booking or a trade.
- **Owner decision D1 (C5) delivered: every profile identifies its callers** — the owner chose to install authentication in every profile so that "private network" becomes a deployment statement rather than the code default. The first attempt was reverted because it is not the bounded change the estimate suggested; the second pass landed it, and both halves are recorded in `W0-03` D1. What it took: **one exemption list** (`api/dependencies/exempt_paths.py`) consumed by *both* gates, because the earlier defect was two lists - the deployment-token gate had one and the identity gate none, so a login could not be reached and an orchestrator's health probe would have answered 401; **a `require_identity` that never overwrites** an identity another layer already resolved, which is exactly what widened a governed read in the attempt (`test_projections_are_never_wider_than_the_underlying_routes` now passes unchanged, and that is the parity evidence); **the twelve internal paths that had no declared permission**, unmasked the moment the gate that reads the registry was installed in the `internal` profile - each declared at the floor its own route already enforced (`validate_internal_operator_headers`) rather than at a second, different one; and **the harnesses**, which is where the estimate went: the test suite presents the deployment token centrally for development- and internal-profile clients unless a test asks for anonymity (the documented SDK/CLI caller, changing no principal, scope or row filter), the two load harnesses present it and refuse to run without one rather than reporting 401s as healthy latency, and the acceptance sweep already logs in through the exempt development login. The deployment's opt-in is the only way back to the pre-D1 posture and both gates honour it - a *presented* credential is still verified, so the opt-in buys anonymity, never a skipped check. Also fixed here: the identity gate's own `401 authentication_required` is documented and tested as a **backstop**, because with the deployment-token gate installed everywhere the refusal an anonymous caller actually meets is that gate's (`401 public_api_token_missing`, or `503` fail-closed when no token is configured).
- **The unmounted shadow terminal, on the owner's call** — `StrategyShadowRunTerminal.tsx` (838 lines) and its five section components were rendered by nothing while the Shadow task was served by monitor management alone. The owner chose to **keep the content and retire the parallel shell**, which is what happened: the derivations moved to `app/model/shadowRunPresentation.ts` as pure functions over the reads the client already holds (the price tape, FX, the pool's resources, the strategy runs and the last evaluated result), the panels - price-basis board, market tape, pooled PnL curve, basis exposure ladder, contract attribution, allocation ladder, paper state, run provenance with its warning stack - render from `StrategyShadowRunDetail.tsx` inside the shadow task beside the monitor management, and the terminal's own tab set, risk-override form and fifteen dead props are gone. Two of its four views were redundant by construction (the task owns Monitor, and Run History is the Performance panel), so the design spec's "four task-led views" claim was updated with it. Two things are recorded rather than fixed: **bar size has no operator control** (the scenario builder declares 5; the contract test that asserted a selector was asserting a control in an unreachable component and now states the gap), and the retired surfaces' vocabulary remains in the locale files with the unreferenced-key analysis in `W0-04` finding 13. Five contract tests were repointed at the new homes rather than deleted, and the design spec with them.
- **D3 (C11) owner decision, slices A–F: the client methods with no caller got their surfaces** — the owner chose to build every missing surface rather than retire the routes, and the work is sliced by family so each slice carries its own rule, tests, bilingual vocabulary and record. **A: strategy lifecycle** — a backtest-experiment panel in the Strategy Lab's Backtest task (create, list, open, and read a grouped run the bounded history has not loaded) and a strategy-identity metadata editor in the Design task. **B: shadow runtime** — the Shadow task opens one evaluation, the only read that carries its **risk checks**, so a blocked candidate's controls are finally visible, and re-reads the monitor it belongs to. **C: access administration** — a Roles-and-scopes tab in Access & Identity (the role → permission catalogue the backend enforces and the declared scope families) and an issue-key form, so issuing a key no longer means calling the API. **D: reference and data reads** — the **reference register** (facilities and market hubs) on the market network task beside the map it is the register for, with the type and country filters the route itself accepts; the **declared capacity profile book** on the capacity task; and the **route-cost and indicative-netback what-if** in the Portfolio Routes task, where the `compute` occupies that task's primary slot per the action geography. `api.portfolioLiveSummary` was **retired rather than built**: the Wave 5 projection's `summary` slice is the same `summarize_portfolio` result, narrowed by the caller's entitlement and on one as-of with the orders it summarises, so a second client read would answer the same question from a different instant (the route stays for the SDK and the CLI, and the reason is recorded where the projection is declared). **E: agent and capability reads** — the agents workspace gained the run/profile/search reads and the research surface now renders the capability catalogue: `GET /api/research/capabilities` declares what the research domain can do and the posture each capability carries (read/write class, determinism, side-effect class, permission, provenance behaviour), which is what makes a research figure checkable against the capability that produced it. The panel reads and invokes nothing — invocation stays the capability runtime's own surface under the caller's authority — a posture the deployment names but this build does not know is rendered as the deployment's own token rather than blanked or guessed at, an unread catalogue is a stated failure rather than an empty one, and a still-loading read is not stated as empty. **F: decision outcome** — the Decision Case panel records its decision through the `apiOutcome` variant, so a 409 `case_not_decidable` renders its blockers as a governed answer instead of a thrown failure; the unused throwing twin of the same route was deleted rather than left as a second way to handle one refusal. The never-mentioned set moved 20 → 15 → 13 → 10 → 9 → 5 → **0**: every declared client call now has a surface, re-measured after each slice, and 30 methods remain reachable only through the loader seam (checked one by one against the store that owns it). No slice creates a page (V2 rule 9 — each surface completes a task that already exists) and no slice changes a route, permission or payload. The unmounted `StrategyShadowRunTerminal` question was decided by the owner in this stretch and its outcome is the bullet above.

## Validation evidence (combined tree)

- `python -m pytest -q` — **1844 passed, 17 skipped, 0 failed** with no runtime store configured (the default CI path; the 17 skips are the store-gated integration tests).
- `python -m pytest -q` with a live PostgreSQL 16 configured (migrated to head `0036_job_records`, `postgresql+pg8000` — the scheme the project's driver requires) — **1860 passed, 1 skipped, 0 failed**, so the 16 store-gated integration tests ran for real rather than skipping.
- `ruff check .` — **clean** (0 findings on the configured `E`, `F`, `I`, `B`, `UP` set; `.automation/` is excluded as the earlier harness rather than product code, and FastAPI's parameter functions are declared immutable calls so `B008` stops mis-reading the framework idiom). The tree had drifted ~409 findings from this gate before this stretch.
- `python -m alembic upgrade head` on live PostgreSQL — `0033` → `0034` → `0035` → `0036` in one transaction, no downgrade path taken; `python scripts/ops/validate_runtime_db.py` reports `Alembic revision: 0036_job_records`, every required table present, none missing.
- `python scripts/ops/backup_restore_drill.py` — PASS: 52,535,660-byte custom-format dump from the live database restored into an isolated one, revision `0036_job_records` on the target, no missing tables, 80,545 `ingestion_runs` and the audit rows restored, and the DB-backed API smoke answering 200.
- `clients/web`: `node --test "tests/*.test.ts"` — **532 passed**; `npx tsc --noEmit` exit 0; `npm run build` exit 0.
- CI (`github.com/AlexYuhuFeng/EurogasNexus`, workflow `CI`): runs **447** (`0c34959`) and **448** (`efcbddb`) — **both success, every job green together** (`validate`, dependency licence/CVE audit, PostgreSQL integration, Web build/tests, browser acceptance; the desktop-bundle job is skipped for pushes). The preceding 95 runs (352–446) failed on `validate` (the lint gate) and/or `Browser acceptance`. Of the D3 slice runs: **455** (`f03c403`) failed `Browser acceptance` alone while every other job passed (the header preferences focus assertion, whose outcome the menu produced a frame later than the sweep read it); **456** (`fa38e2b`) was green; **457** (`e1b494d`) and **458** (`51026f4`) failed the **`Test Web client`** step, and the job log names the cause: `workspaceHeader.test.ts` still asserted the previous focus implementation (`requestAnimationFrame(() => triggerRef.current?.focus())`) that the same commit had replaced with a synchronous move - the *product* change was right and the test that pinned the old shape was not updated in the same pass, because the client suite had been run before that edit and not after it; **459** (`4828983`) is **green on every job**, with that assertion corrected and the sweep's own check made deterministic. The stretch's last runs, read the same way: **460** (`861bc24`) green; **461** (`658c39a`) failed `validate` alone, and the log named the cause - five `E501` lines in the docstring of the new `tests/security/test_acting_actor.py`, which the local lint had not seen because it was run before that file existed rather than after it (the same slip as 457, in the same stretch); **462** (`60be5ee`) is **green on every job** after the wrap, on its second attempt - the first attempt failed `Browser acceptance` because the API server never answered inside the job's readiness loop (`Failed to connect to 127.0.0.1 port 8000`), an infrastructure flake the re-run cleared with no code change; **463** (`460881a`) and **464** (`befac8a`) are **green on the first attempt**; and **465** (`1a1ee1e`, the desk slice) repeated the flake - `Browser acceptance` alone failed at the same server-start step while `validate`, `web-client-build`, the PostgreSQL integration job and the dependency audit all passed - and its **second attempt is green**. So the same commit is proven in the place that enforces it, and the acceptance job's server-start step has now failed twice in six runs on unchanged code: the job proves it could not start the API, but captures no diagnostic for that step, which is worth fixing in the harness rather than re-running past it.
- Dependency audit (`scripts/release/scan_vulnerabilities.py --channel preview` → `release-assets/release-evidence/vulnerability-scan.json`): **status PASS, no blocking component** — `python-runtime` PASS, `web-node` PASS, `desktop-node` PASS, `desktop-rust` TOOL_UNAVAILABLE (no toolchain here), container scan deferred to release CI by policy. The web client's `maplibre-gl` was upgraded from 5.24.0 to 6.10.0 in this stretch because 5.24.0 carried a **critical** advisory ([GHSA-jrc7-96c5-q579](https://github.com/advisories/GHSA-jrc7-96c5-q579) / CVE-2026-85061, zero-click XSS through `DOM.sanitize()` when rendering a third-party attribution string, fixed in 6.4.1); `npm audit --omit=dev` reports zero findings, and the two remaining dev-only advisories were cleared by `npm audit fix`.
- Licence policy (`scripts/ci/audit_dependencies.py`) — **OK (no forbidden licenses)**.
- Release engineering dry run (`scripts/release/run_release_dry_run.py --channel preview --build-container`): release context, version consistency, Web package, deployment bundle, **container image built** (`sha256:f6f5d6bfe60f3cb95577186f798ee0945d5da2f3c8548bad2fcbb2ae6e4219be`), SBOM (SPDX 2.3), signing state recorded as unsigned/pending-external, **vulnerability scan PASS**, release notes and checksums/manifest all OK. The two steps that cannot pass here are honest ones: `package-windows` needs the desktop bundle (no Rust toolchain) and the release gate reports its external items (`G18` user acceptance and the platform artifacts) as `PENDING_EXTERNAL`.
- Performance budget (`scripts/ops/performance_baseline.py --requests 200 --concurrency 10`, live PostgreSQL) — 0 errors, p50 39.6 ms, **p95 1295 ms ≤ 1500 ms target**, **p99 2313 ms ≤ 2500 ms target** (budgets in `docs/operations/PERFORMANCE_BUDGET.md`). In-process load smoke: 200 requests, 0 errors, p95 10.6 ms ≤ 1000 ms.
- Other CI steps run locally: `python scripts/ci/check_markdown_links.py`, the MCP handshake (`initialize` answers `protocolVersion 2024-11-05`), and the app import (179 public paths).
- `python scripts/security/run_security_acceptance.py` — all automated checks PASS (`api_import_safe`, `public_surface_bounded` 179, `permission_registry_complete` 179, token/identity/OIDC fail-closed, posture retained); external review items remain BLOCKED as before. The bound moved from 178 to 179 with the desk clock read, and the same change declares the path in the pin, both contract-evolution policies and `docs/operations/STORAGE_NOMINATION_ASSESSMENT.md`.
- Documentation gates: `tests/contract/test_markdown_links.py` and `tests/contract/test_docstring_policy.py` pass, including the new wave records.
- Bilingual parity: `clients/web/src/i18n/{en,zh}.json` hold the same 2731 keys, no key is declared twice (the raw text is checked, because `JSON.parse` would silently keep the last), no value carries a question mark or a replacement character, and every value is translated in both locales — held by `clients/web/tests/localeDistinctness.test.ts`, which fails on any value identical in both locales unless it is declared with its reason (the 13 that are: `SSO`, `AI`, `LLM`, `KPI`, `LNG`, `GIE LNG`, `UTC`, `Alembic`, the product name, the two language names and one identifier shape). That gate exists because the parity checks did not ask whether a value had been translated, and 24 `agents.*` keys were the English text in Chinese until the D3 slice that touches that workspace found them (finding 8 of `W0-04`). The 96 keys added by the claim audit are the per-code error texts (`errors.<code>.message` / `.action` for all 48 catalogued codes), held to the backend catalogue by `tests/contract/test_error_vocabulary_coverage.py`; the D3 surface slices added their own vocabulary on the same terms.
- `node scripts/uat/browser_workflow_smoke.mjs` (seeded UAT runtime, dev API on `:8000`, Vite on `:3000`, Playwright 1.55.0 + axe-core 4.10.3 + Chromium) — **`ok: true`, 96 checks, 0 failures, 0 axe violations, 0 horizontal overflow, one `h1` per page**, and the agent-research interaction reached `READY_FOR_HUMAN_REVIEW` with its artefact chain complete and its review pack confirmed through the API. Three defects were found and fixed by running it (see the two slice bullets above): the sweep's stale primary-action selector, a duplicate page heading on three workspaces, and — found by this stretch's re-run after the D3 surfaces landed — the header preferences menu returning focus to its trigger only on the next animation frame, which the sweep reads immediately after `Escape`. The focus move is synchronous now (the trigger is always mounted, so it can be focused before the menu closes, and closing afterwards cannot drop focus into the body), the sweep waits for the outcome within a bounded time instead of assuming it happens in the same tick, and `preferencesAndStatus.test.ts` holds the close handler to that shape so it cannot regress. The day view added one more check to the same sweep, and it is the one that changed the product: it reads the day board on the Decision workspace and requires each clock row to carry the API's resolved UTC instant, a countdown labelled with the clock it was measured against, and — when the window has closed — the next occurrence. On its first run at 14:56 UTC both declared windows read `overdue 511 min` with nothing forward-looking, which is honest and useless to a desk; the next-occurrence fields were added because the sweep asked the question a trader would. A geometry pass over the rendered board (a screenshot read as data, since this environment's model cannot view images) confirms both viewports: four-column rows at 1440px degrading to two at 390px, two rows with the fixture's declarations, no clipped element, no collapsed section and no dead space.
- Runtime-DB validation (`python scripts/ops/validate_runtime_db.py --json`, live PostgreSQL 16): `connectivity.ok=true`, `alembic_revision=0036_job_records`, 91 required tables, `missing_tables=0`, `table_inspection=performed`, no warnings. The same command with a bare `postgresql://` URL (which selects psycopg2, a driver this project does not depend on) now reports `table_inspection=not-performed` with `missing_tables=null` and names both the selected driver and the `postgresql+pg8000` scheme, instead of listing all 91 tables as missing (finding 11 of `W0-04`; `docs/operations/LIVE_POSTGRESQL.md` states the scheme).
- The two desk engines, exercised over real HTTP against the running API rather than only read: `POST /api/optimization/nomination-window` accepted exactly the shape the panel composes and answered with one decision per instruction - the window's cap applied (`RENOMINATION_CHANGE_LIMIT_APPLIED` inside `W1`) and an instruction outside every window reported with `window_id: null` and reason `OUTSIDE_NOMINATION_WINDOW`; `POST /api/optimization/storage-dispatch` answered `optimal` with objective 14,250 and a per-period withdraw plan (150 MWh each period, ending inventory 850/700/550 MWh, cashflow 4,500/6,750/3,000 GBP); and `GET /api/optimization/runs/{run_id}` re-read the persisted run (`storage_dispatch`, `SUCCESS`). Both envelopes carried `meta.run_id`, which is what the panels offer to re-read.
- Not run and not claimed: any Tauri/Rust build or desktop bundle (no Rust toolchain here: `cargo`, `rustc` and `rustup` are absent, so `main.rs` cannot even be type-checked), packaging/installer evidence beyond the CI job that builds bundles elsewhere, provider and licence validation, and every external sign-off. The PostgreSQL and browser evidence above comes from a **local container and a local dev server**, not the production deployment: the production restore drill, the IdP acceptance against a real issuer and the penetration test stay with the operator.

## Deferred / known gaps

- **M1-P0 delivered — the source timezone contract** — the one P0 still `ready` in the product ledger is closed, and it was the audience review's first-ranked next step. The parser behind the public-source normalizers read any timestamp without an offset as UTC (`value.replace(tzinfo=UTC)`), so an ENTSOG gas day published as `06:00` on the Central European clock became `06:00Z` — an hour early in winter, two hours early in summer, on every flow and capacity period. `domain/ingestion/source_timezone.py` now declares each source's timestamp semantics once (ENTSOG: the platform's CET/CEST clock, which is the convention the frozen `EU-CAM-UTC-2025` calendar encodes as 05:00Z/04:00Z; GIE: unproven, because the gas-day dates go through the CAM calendar and the freshness stamp has no cited zone), and the parser obeys it: an explicit offset is trusted and never reinterpreted, a bare value is read in the declared zone (or a payload-declared zone the contract supports), and an unprovable or unsupported zone is **refused** rather than assumed — a payload that declares a zone the contract does not support fails whole, because every instant in it would be mislabelled. `tests/ingestion/test_source_timezone_contract.py` asserts eleven exact-UTC cases (CET winter 06:00→05:00Z, CEST summer 06:00→04:00Z, stated `+01:00`/`+02:00`/`+00:00`/`Z`, the 2026 DST switch days, the spring-forward gap and the ambiguous autumn hour) and both refusals, and the flow and capacity normalizers are held to the same answer for one gas day. No historical rows are rewritten, following M0-P0's policy. Evidence and the one integration-time check (confirming the platform's default response zone and whether GIE's stamp always carries an offset) are in `docs/data/SOURCE_TIMEZONE_CONTRACT.md`; the ledger row is `complete`.
- **A harness false-green found while verifying D4, and the product defect it was hiding** — the browser acceptance sweep's per-workspace checks were **vacuous for the `network` workspace**: `?workspace=network` mounts the market primary's map page and leaves it `display: none` (the same navigation shows "Portfolio" for `?workspace=contracts` and "Agent Research" for `?workspace=agents`, and the page's own API reads answer 200), while every check the sweep makes there — document language, `main h1` count, horizontal overflow, the axe sweep — is either measured on a hidden subtree or counted from the DOM regardless of visibility. So that workspace passed three viewports and two languages of checks while measuring nothing, and the map page cannot be reached by its own deep link. `inspectWorkspace` now requires a workspace page to be *displayed*; a workspace known not to render is declared in `KNOWN_NON_RENDERING_WORKSPACES` with its reason, so a new occurrence fails the run and the declared one is reported in `summary.json` under `observations` rather than passing silently. The finding also corrects an earlier note in this session that blamed the map column for collapsing, which was wrong: the column has no height because its ancestor page is hidden.
- **The day view delivered — the desk's clock has a surface, and the read exposed D9** — the audience review's second-ranked next step (its table row 3). The clock was the one thing the product could not show: `nomination_window_masters` was read by the engine and by nobody else, so no surface could state the deadline being traded against. `GET /api/optimization/nomination-windows` now serves the declared masters for one gas day at the **READ floor** (running an assessment stays GOVERNED) — the first public path added since the 178-path bound, so the bound, the pin, both contract-evolution policies (path row and additive-field row, English and Chinese) and the operations record moved in the same change. The clock is resolved on the gas-day calendar in `domain/market/nomination_windows.py`, mirroring `_find_window` rather than inventing a rule, and `tests/unit/test_nomination_window_occurrence.py` asserts the two agree instant by instant (including the 23/25-hour gas days and a window wrapping UTC midnight). The read distinguishes what it established: an unconfigured runtime database is an unread input (`meta.missing_inputs`), a configured deployment declaring no active master is a **measured** zero carrying `NOMINATION_WINDOWS_MISSING`, and each row also carries the **next** day's occurrence because a master is a daily rule. The surface is a **day board above every Decision task** (no new page, rule 9) carrying the deadlines, the actionable opportunities with no recorded decision, and a measured pointer into the alert centre that already exists in the top bar — the board deliberately does not render a second alert list. Evidence: 12 API tests + 14 domain tests (`tests/api/test_nomination_windows_api.py`, `tests/unit/test_nomination_window_occurrence.py`), 20 client tests, the reachability census re-measured at **34 of 179 public paths unreached** (16 by nobody), and the read exercised over real HTTP against PostgreSQL 16 with the UAT fixture's own declarations (`2026-09-19` gas day: 04:00Z–04:00Z boundary, two windows resolved to 06:00Z/12:00Z, `next_opens_at_utc` 2026-09-20T06:00Z). The acceptance sweep now asserts the chain end to end — fixture declaration, route, resolution and panel: `ok: true, 96 checks, 0 failures, 0 axe violations, 0 overflow`. **It is also what produced the day's second finding**: at 14:56 UTC both windows read `overdue 511 min`, which is honest and useless, so the next occurrence was added; and the engine's own field documentation claimed a *local* gas-day clock while the matcher compares UTC clock times, now **D9** in the reconciliation register with the read stating the basis it assumed rather than the ambiguity staying silent.
- **The decision pack delivered — the case a reviewer signs, in one artefact** — the audience review's fourth-ranked next step, for the reviewer/compliance audience: the platform recorded everything a decision needs and none of it in a form a human could sign. `GET /api/decision-cases/{case_id}` now carries a `pack` beside the case: its context and reproducibility, its evidence with **each cited snapshot's resolvability measured** (`true` / `false` / `null`, the last meaning the reference cites none - a hole is reported, never dropped), its assumptions, alternatives, AI findings and warnings, the recorded decision with its actor, the case's audit trail (its acts are recorded under `decision_case:<case_id>`, so the trail is cited rather than guessed at), the pack's own blockers beside the case's, `signable`, and a **canonical `content_hash`** whose basis travels in the payload so a printed copy can be matched to the platform's record and a later edit cannot go unnoticed. It rides on the existing case read rather than a new path - it *is* that resource, not a second answer about it - so no surface bound, permission entry or reachability rule moved. The composition is a deterministic engine (`application/decision_pack.py`) whose hash rule is stated as "everything except `content_hash`", and the pack says plainly that the platform holds no signature: the signature is the human act the pack exists for. Evidence: 10 unit tests (`tests/unit/test_decision_pack.py`, including hash stability, hash sensitivity to every packed field, and the three-valued resolvability) and 5 API tests over a real store.
- **Professional audience review** — the programme had reviewed itself against its own architecture many times and never against the people it is for.
 [PROFESSIONAL_AUDIENCE_REVIEW](../product/PROFESSIONAL_AUDIENCE_REVIEW.md) does that audience by audience (desk trader, portfolio manager, reviewer/compliance, quant researcher, data operator, platform administrator, deployment IT, machine callers), states what each has today with pointers, where each stumbles, and ranks ten next steps. Its three cross-audience findings: the day's clock has no surface (deadlines, unactioned decisions and alerts live in different workspaces); **`M1-P0` (ENTSOG timezone normalization) is the one P0 still `ready` in the project's own ledger** — delivered since, see the bullet above; and the deployment's identity posture (**D1**) is decided but unbuilt. It also corrected two records it found stale — the information-architecture tables still described five primary workspaces where the registry has six, and this backlog's own "current run" pointer named one CR after all fifteen had landed.
- **Wave 5** — complete for the market, portfolio and review lanes; `ScenarioContext` is deliberately available but unconsumed (documented in `W5-01` section 8).
- **Wave 7** — every surface now reaches the Copilot through the canonical contract (the palette, the market cockpit and the review task), a completed run is citable as `AI_ANALYSIS` evidence on a Decision Case, the governed research run is converged onto the same governance rules (gated primary action, honest disclosures, no client-chosen profile), and the analysis/report request surface stopped declaring selections the pipeline cannot apply (refused rather than ignored); all five actions deliberately run the same backend task kind; the capability catalogue is now invocable from the surface that reads it, and the profile catalogue remains without a consumer; the `/agent/*` read surfaces were already converged.
- **Wave 8** — every run family V2 names is tracked - including `SNAPSHOT`, which the claim audit found declared but never created, and which `POST /api/analysis-snapshots` now opens in the same session as the snapshot it describes; job **retention** is delivered as a bounded, operator-controlled mechanism (`application/job_retention.py` + `scripts/ops/prune_job_records.py`: dry-run by default, no invented default window, terminal rows only, active rows counted and reported rather than pruned, and the work a job referenced untouched), and the **replay question is answered** rather than deferred: `JOB_RERUN_CONTRACTS` declares per kind that no job can be re-issued from its row (the row keeps a hash of the inputs, which a fitness test holds against the table), where a re-run's inputs actually live, and which public path issues it as a *new* run - with recording a snapshot the one act that is never repeated (`W8-02` section 7).
- **Wave 9** — the panel taxonomy's disclosure column is now audited (each panel kind's owed disclosures are either carried by a named slot in its owning primitive, matched live, or recorded as the caller's duty) and the shared metric strip carries as-of, time-basis and unit slots, used by the agents replay strip; the action geography now has seven applications and its enforcement also catches a primary action copied rather than moved (across surfaces, not only inside a file), and the surfaces that deliberately declare **no** primary action (the review task, whose act is a three-outcome decision; the read-mostly market cockpit; the operator runtime surface; the administrative surfaces) are recorded with their reasons rather than left to read as unfinished. The Optimize task put its optimiser run (a `compute` consequence) in the workspace primary slot; the Portfolio `resources` task followed with the contract save (a `persist` consequence), which required the rule behind it to move out of the panel first (`app/model/contractDraftModel.ts`, with the workspace owning the resource sub-view); the agent research surface put its governed run there (`app/model/agentRunModel.ts`, mirroring the route's bounds and the runtime-database precondition); and the Strategy Lab's backtest task put its run there, which required the *draft* to move as well as the rule (`app/model/strategyBacktestModel.ts`, with the workspace owning the period and economic assumptions the panel used to hold), and the research surface put building a dataset snapshot there (`researchBuildGate` already lived above the panel, so the lift removed a second build control and moved the gate's sentence into `researchBuildGateLockKey`); the Scenario task then put the route comparison in the slot, so both `compute` acts the Decision workspace owns now have their own task-scoped primary action, and the cross-surface guard covers both; the Strategy Lab's Design task then put saving the draft there, which was the largest lift of the set because the *draft itself* lived in the panel - it now lives in `app/model/useStrategyDesignDraft.ts` with the rule in `app/model/strategyDraftModel.ts`, while freezing and forking stay bounded as `lifecycle` consequences next to the version they change. A cross-surface duplication was then found and removed: the same pool-optimiser run was reachable from three buttons - the Optimize task's primary action, the Scenario panel and the network panel over the map - so the two panel copies are gone (one hands over to the Decision workspace, the other points at the workspace's primary action), and the enforcement gained a **cross-surface** guard, because a per-file uniqueness check cannot see that failure mode. The remaining surfaces still keep their validity model (`canSave`, blockers, assembled payload) inside the panel that owns the form, so applying the geography there stays a per-surface lift - the one surface left is the review task, whose slot is deliberately empty because its act is a three-outcome decision; each lift records why the rule is extracted rather than copied into a header; six surfaces hand subjects to the Inspector (the market cockpit, the contract workbench, the network map, the strategy backtest, the review decision history and the capacity point panel), and five more joined them - the activity timeline's tracked operation, the Source Center's provider connection, the Data Products catalogue entry, the agents surface's governed run and the strategy navigator's version - so **all thirteen subject kinds a page may declare are kinds the build can show**, and a test asserts that set equality rather than a pending list, because a registry entry can no longer promise a kind nobody implemented; the shell composes every page through the workspace renderer, so C9 and C10 are closed; C11 was re-measured with the method stated (no component is unmounted; of 131 client API methods, 21 are never mentioned anywhere outside the client and 52 are never called directly) and C12 stays deferred.
- **Wave 10** — the native implementation is deferred and unverified: no Rust toolchain exists in this environment, so window creation, multi-monitor restore, notification delivery, protocol registration, tray and file dialogs are unimplemented; auto-update and signing belong to Wave 11; the diagnostics bundle now has a consumer surface, but the desktop host's native save is still only declared (its command would need a `HOST_COMMANDS` entry with a capability class first).
- **Security** — C5 is **closed by decision and now built**: every route profile identifies its callers (owner decision **D1**, delivered — see the security section below), so "the network is the trust boundary" is a deployment's own statement (`EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS`) rather than a code default, and the posture is **reported at runtime** by `GET /api/health` and `/api/health/live` (`authentication: enforced | anonymous_allowed`); C6b's self-service half is closed (a principal cannot change its own roles or data scopes; a second-approver policy for grants remains the ADR question); C7 is **decided** (the route-level `require_entitlement` stays unwired because the per-row, per-family filter is the correct control; the decision travels in the dependency's docstring and its fail-closed behaviour is tested); the C8 remainder is now three recorded things rather than one overstated claim: MCP's inability to inherit the calling user across its transport, the legacy MCP tools that are not re-authorised per user, and - found by the claim audit - the headless `monitoring-worker`, which invokes the provider with no authority binding at all because it has no caller identity to inherit (**D7** in the reconciliation register: a service-identity posture for headless provider use, with options and a recommendation). All three are declared and audited rather than implicit, and none is patched silently.
- Organisation, portfolio, market and region scope still do not exist; `ExperienceProfile.unsupported_scope_kinds` reports that honestly.
- `W0-01`…`W10-01` wave records are registered in `docs/README.md`, `docs/README-CN.md` and the pack's `00_README.md`, as is `W0-04` (the claim audit).

## Compatibility

- API: additive only, with deliberate semantic narrowings. One new public path in this stretch — `GET /api/optimization/nomination-windows`, the READ-floor desk clock read delivered by the day view (declared in `tests/contract/test_api_surface_stability.py`, both contract-evolution policies, the security-acceptance bound and `docs/operations/STORAGE_NOMINATION_ASSESSMENT.md`); the earlier record of "no new public path" described the state before it. Five optional request fields with a conditional echo (`analysis_snapshot_id` on the analysis-query and portfolio-report paths, plus the three recorded earlier), and eight field positions across the two analysis/report routes that the pipeline never read are now **refused when non-empty** (`422 analysis_selection_not_supported`, catalogued in the product error taxonomy as a VALIDATION failure the caller can repair) instead of silently ignored - the fields stay declared, so a caller that still sends one learns why rather than having it dropped. `POST /api/analysis-snapshots` now also registers a tracked `SNAPSHOT` job in the session that writes the snapshot, which adds a row to `/api/jobs` and changes no payload. Both categories are declared in the English and Chinese contract-evolution policy.
- DB: no new migration; the Alembic head remains `0036_job_records` and the release-metadata test still pins it. (`tests/unit/test_decision_case_migration.py` now applies revision `0035` for real, which is test coverage rather than a schema change.)
- Client: projections replace client-side joins; the market lane reads the projection through the same bounded loader, and the portfolio lane derives its pool block from the projection instead of a second route call. Failures are now explained through the product error taxonomy on every surface that renders one (`ApiError`/`ApiFailureDTO` carry the whole envelope, `describeFailure` reassembles it, `presentError` resolves the text), and the locales gained the 92 per-code error entries.
- Security: one deliberate narrowing (AI invocation now requires the caller's own analysis capability), one refusal added (a deep link carrying an authority parameter in its fragment now opens nothing, as the query half already did) and no widening; the compatibility deployment token keeps its posture.
- Numerics/release/DR: unchanged.

## Risks / STOP CONDITIONS

- No STOP condition from `CODEX_ENTRYPOINT.md` was triggered: no commercial-data access broadened, no security control weakened, no destructive migration, no new infrastructure, no Web/Desktop divergence, and no scope crossing into execution, nomination or settlement.
- The Wave 1 interaction contracts, the Wave 2 capability model, the Wave 3 control-plane boundary and the new AI-authority dependency are normative. Work that contradicts them (a new top-level page for an object, a second global context owner, an AI button outside the five canonical actions, a client-side reconstruction of commercial state, an AI invocation without the caller's authority) is an architecture violation, not a style preference.
- Concurrency note: this stretch was developed by three workstreams in one working tree (client Wave 5/9/10, client Wave 7, backend Wave 4/8). The integrator verified the combined tree — full Python suite, client suite, type check, production build, security acceptance and the documentation gates — rather than each stream's isolated claim, and reconciled the pinned gates the earlier slices had left red.

## Resume instruction

Read `CODEX_ENTRYPOINT.md`, the wave records `W0-01`…`W10-01`, the reconciliation register's conflict table (`W0-03`) and this checkpoint; verify the tree is clean and the suites are green.
Continue with the highest-value open item. What is actually open, in the order the programme would take it:

1. **Wave 9** — the remaining action-geography lifts (each is a per-surface extraction of a panel's validity model into a shared rule, with the surface that hosts the action owning the state) and any panel kind whose owed disclosures its caller has not yet carried. The surfaces that *deliberately* declare no primary action are recorded in `W9-01` section 6, so an empty slot is not read as unfinished work.
2. **Wave 7** — complete. The capability catalogue is invocable from the surface that reads it, the capability-invoke seam carries the caller's confirmation, the run's profile is a validated, self-qualifying label (`422 agent_profile_unknown` for an undeclared one, `PROFILE_STAGES_NOT_REACHED` when declared stages did not run), and the analysis/report request models no longer offer a selection the pipeline cannot apply (refused with `422 analysis_selection_not_supported`, with the client sending none). The one deliberate non-feature is recorded: the surface does not offer a profile *choice*, because choosing a label that does not change the pipeline would imply a capability that does not exist.
3. **Wave 4** — complete on the client side: the product records a snapshot, cites it, reads the Data Product catalogue and queues a manual ingestion run. The `researchCapabilities` read is the only Wave 4 read still without a consumer.
4. **Wave 8** — job retention and the replay question are delivered; what remains is operational (choosing a retention window per deployment, and reading the re-run contracts when a surface wants to offer one).
5. **Wave 10 / 11** — the native desktop half needs a machine with the Rust toolchain (none here: `cargo`, `rustc` and `rustup` are all absent, so `main.rs` cannot even be type-checked), and RC/GA readiness needs the external items: IdP acceptance against a real issuer, provider certification, the browser/accessibility UAT run on a machine with Playwright, the **production** restore drill, and signing/notarisation. What this environment *could* do about the restore drill is done: the automated drill ran against a real PostgreSQL 16 container with real data and passed (see the evidence above), so the procedure and the tooling are proven and only the production target remains.
6. **Owner decisions** — written up as decidable options in `W0-03` section 9: D1 C5's profile authentication, D2 C6b's second-approver policy, D3 C11's uncalled client methods, D4 C12's map tiles, D5 where the native host and RC/GA work can proceed, D6 what the MCP surface should do about the calling user, D7 the authority a headless `monitoring-worker` invokes the provider under, and **D9 the clock basis the declared nomination-window masters are read on** (raised by the day view: the engine matches window times against the UTC clock while its own field documentation claimed the local gas-day clock). **Two have been decided by the owner in this stretch and are recorded in full there:** D3 (build every missing surface) — **delivered**, all six slices, with the census closing at zero and the unmounted terminal retired with its content kept on the shadow task; and D1 (install authentication in every profile) — **delivered** on the second pass, after the first attempt was reverted as larger than the estimate suggested: one exemption list shared by both gates, a `require_identity` that never overwrites an identity another layer already resolved (the widening the attempt exposed), twelve internal paths that had no declared permission declared at the floor their routes already enforced, and every harness that relied on the compatibility principal updated to present a credential. The attempt also surfaced a live defect, fixed here with its own test: the compatibility principal's id is not a valid actor, so every deployment-token caller reaching a job-tracking route raised. **The remaining six were then decided on the owner's instruction to take them from each audience's seat, and are recorded in full there:** D2 (dual control for privilege *elevation* only, with a *verified* second ADMIN identity and self-approval refused), D4 (no third-party basemap is a default; the operator brings a licensed source) - **delivered**, with the two endpoints whose terms exclude commercial use declared as evaluation-only on the control that selects them; D5 (the native host is deferred to a machine with the Rust toolchain and RC/GA stays with the operator, neither simulated); D6 (MCP runs as a named, least-privilege service identity and never implies the caller's); D7 (the headless `monitoring-worker` authenticates as a deployment-named service principal or refuses to call the provider at all); D9 (the window master declares its clock basis, the engine reads it, and an undeclared basis stays UTC). D2, D6 and D7 are decided-not-built with their implementation stated, so no worker invents a weaker rule in the meantime; D9's read already states the basis it assumed, so nothing is silently mis-dated while the migration lands. In D9's case the read surface **states the basis it assumed** rather than leaving the ambiguity in the numbers, so no deployment is silently mis-dated while the decision waits.

**Commercial readiness remains open.** The 2026-09-22 audit identified additional
release-engineering and evidence gaps, alongside the decided-but-unbuilt controls
listed above. See [commercial acceptance audit](Architecture-V2/19_COMMERCIAL_ACCEPTANCE_AUDIT.md).
Earlier delivered-wave records are historical evidence, not production approval.

## Where the migration stands

Every wave that can be finished in this environment is finished, and the ones that cannot are stated
as such rather than implied:

| Wave | State |
| --- | --- |
| W0/W1 foundations | Delivered: contracts, registries, fitness functions, host capabilities |
| W2 capabilities and scopes | Delivered |
| W3 control-plane boundary | Delivered (C9/C10 closed) |
| W4 unified data platform | Delivered including the client half: catalogue, snapshots, citations, manual ingestion queue |
| W5 projection lanes | Delivered (market, portfolio, review; scenario context deliberately unconsumed) |
| W6 Decision Case | Delivered |
| W7 AI convergence | Delivered: five canonical actions, alert/review/market convergence, the governed research run, the capability-invoke seam and surface, a profile that is validated and self-qualifying, and an analysis/report request surface that refuses the selections it cannot apply |
| W8 error taxonomy and job model | Delivered: taxonomy, unified jobs for every run family, retention, and the replay question answered per kind |
| W9 workspace migration | Seven geography applications, the Inspector handover on eleven surfaces covering all thirteen declared subject kinds, panel disclosures audited. Left: the review task, whose primary slot is deliberately empty (a three-outcome decision must not be promoted) |
| W10 desktop workstation | Contract, capability model, diagnostics consumer delivered; the **native half is blocked** on a Rust toolchain and is not claimed |
| W11 RC/GA | **Partly verified here, blocked on external items.** Verified in this environment: the migration chain applied to a live PostgreSQL 16, the whole suite green against it (1807 passed), and the automated backup/restore drill passed with real data. Still external: IdP acceptance against a real issuer, provider certification, the browser/accessibility UAT run, the *production* restore drill, signing/notarisation and every sign-off |
