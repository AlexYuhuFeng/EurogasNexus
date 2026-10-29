# Architecture V2 Execution State

## 2026-10-29 — EEX receipt-bound price mapping with actual capture evidence

Root rechecked the official EEX index page and current methodology25/spec0105a.
Accepted RFC0006/Decision20 separates actual receipt availability from unproved
Timestamp Let publication semantics, with a separately evidenced delivery calendar.
The additive mapper retains null publication time and exact raw price/volume,
source statuses and receipt; old publication-based mapping remains strict. A new
stable namespace separates timing interpretations; no receipt enters its identity.
No source rights, certification or runtime activation is granted by this change.

Root fetched the actual linked TTF NGP CSV,293bytes, SHA256
1944c540ddccd5b870214889ca7c83ebf733baf7095e1d3291c71be6ee8933d2,
received2026-10-29T14:54:05.623743Z. Four usable records mapped at that receipt,
with oneFinal/threeTemporary statuses and no asserted publication instant. All
four passed the existing exact source-price authority. Raw capture and reports
are retained locally; no market payload or credential is committed.
Pure new/old EEX suites87passed/1existingoptionalskip; Ruff and347-file Markdown
link validation passed. Persistence/append-replay/raw archival is being implemented
separately, followed by gated operator and business-consumer integration. This
bounded mapping is not end-to-end delivery or historical availability evidence.


## 2026-10-29 — full hosted quality-guard regression fixture correction

Hosted020ae60/run40895895337 passed ten jobs, including actual PostgreSQL,
browser and all native/SDK platforms. Validate reported3failed/4966passed/
116skipped: three old native-ingestion test doubles lacked the new explicit
semantic_metadata_keys argument. Root updated those signatures and asserted the
exact operatorKey/flowStatus/periodType allowlist; no catch-all kwargs, skips or
assertion removal. Native-ingestion plus upsert tests26passed; Ruff passed.
Same-SHA full CI remains required. EEX RFC0006 receipt mapping/persistence is
being implemented separately and is not included in this corrective checkpoint.


## 2026-10-29 — provider quality changes refused and Web harness isolated

ENTSOG append-or-verify now includes exact presence/type/value for operatorKey,
flowStatus and periodType inside the existing locked comparison, including the
concurrent-winner reread. Same-id same-quantity metadata changes are typed
revision refusals, never unchanged confirmations or overwrites. Mixed batches
roll back canonical writes while raw archives survive. Receipt/archive/run/hash
churn remains ignored. Missing, explicit null and concrete values differ; malformed
metadata is refused without echo. GIE defaults retain an empty metadata allowlist.
Root added permanent boundary tests after reviewing the worker's real PG cases.
Final complete isolated PostgreSQL CI migrated from empty through0044 and passed
57tests without skips; earlier intermediate55pass evidence is retained. Unit
upsert/GIE regressions21passed, metadata boundary probes8passed, Ruff passed.
This preserves evidence but does not implement full append-only provider revision
history or promote status labels into model authority.

The local Windows full Web process was confirmed live with a stalled Vite SSR
load in capacityBillingTransport.test.ts. Root stopped only that owned run after
reviewing the changed harness. DeepSeek isolated per-process test caches, disabled
unused discovery/watchers, and bounded loads with explicit failing diagnostics.
Actual SSR, fresh store module identity and real HTTP transport remain exercised.
A new focused freshness test passed; the whole Web suite then completed in5.5s:
1049passed,3skipped, no force-exit/skip/threshold weakening. The precise cause of
the earlier intermittent stall remains an inference, not a proved Vite defect.
No recursive cache cleanup was added. Same-SHA hosted results remain required.
Latest fully green hosted checkpoints include cc44fea and d650b1f.081a938 has
passed PostgreSQL/browser/client/SDK/native jobs; validate still running at check.
Broader delivery gaps listed below remain open.


## 2026-10-29 — shared native history inputs and exact temporal comparison

Web client and capacity panel now pass paired aware ISO instants to both native
reads. Blank pairs preserve existing behavior; partial pairs refuse without
changing a previous result's accepted label. Loaded point/window labels are
independent of editable inputs. Client comparison uses integer microseconds,
matching Python truncation beyond six fraction digits and avoiding epoch-number
rounding that falsely rejected valid one-microsecond windows. Exact rate strings
remain unchanged. SDK history102tests and three real PG HTTP windows were already
verified in d650b1f. Web focused client/panel/locale23passed; console gates15passed;
backend client-contract/security/installed-SDK pipeline39passed; build passed.

The deliberately induced native503 is attributed by exact request URL AND status.
Native errors cannot fall through to an older default-volume path-only fixture.
Behavioral tests cover another point, default mode, missing URL, wrong status and
legacy attribution. Root fixed the worker test's omitted extracted function braces
and its reused consumed Response fixture; translated the two new Chinese hints.
Headless synthetic browser checks passed both original pagination/recovery and
new shared positive-offset windows/accepted-label immutability. No UI control
of the user's desktop occurred. Hosted cc44fea/run40892448821 completed11jobs green.
A fresh complete local Web run is still live in capacityBillingTransport.test.ts
without final output; do not claim a full post-window green run from focused tests.
Same-SHA hosted verification and broader delivery gaps remain outstanding.


## 2026-10-29 — native SDK history window verified over actual PG HTTP

All four native SDK fetch methods now accept paired aware datetime bounds,
normalize UTC and forward the same half-open overlap window. Partial, naive,
equal or reversed inputs refuse before transport; existing metadata/auth and
exact strings remain intact. SDK plus actual-projector wire contracts102passed.
Root ran three real PostgreSQL-backed HTTP windows through both API and source
SDK: each daily boundary selected one flow, the adjacent empty day selected none,
and the longer covering technical capacity remained present in all three. The
owned HTTP server stopped. This is source SDK proof, not installed-wheel proof.
Web history controls and microsecond comparison review are in progress; the
new browser test's deliberately induced503 also needs exact-URL attribution so
its controlled refusal cannot mask a real unrelated read error.


## 2026-10-29 — shared native capacity context and bounded history reads

The existing capacity network workspace now queries native flow/capacity together
for an explicit point, preserves exact canonical strings and both response meta,
and displays approximate same-operator/dimension/covering-period comparisons.
Missing, negative, ambiguous or incompatible evidence cannot become zero or a
comparison. Ratios above100 remain visible; no rights/headroom inference exists.
Review corrected the initial model's mistaken rejection of supported MWh/hour
and m3 units: the backend owns conversion, the UI uses its canonical daily field.
Root generated all eight actual backend unit payloads and verified the Web model.
Only50 evidence cards render per page, with visible totals and deterministic
navigation; new reads reset the page and loaded query identity survives edits.

Native API reads additionally accept paired aware from_utc/to_utc instants with
half-open overlap, including covering technical capacity; naive/reversed/partial
or volume-mode windows refuse422. Root removed a worker shortcut guessing an
unescaped positive offset; callers must URL-encode it normally. No path added.
SDK/Web query window controls are the next integration step, still outstanding.

Root validation: Web1040passed/3skipped and production build passed; focused
API27passed, combined API/client contract/wire47passed before the offset cleanup.
Real headless browser interaction passed51-row pagination, exact long decimals,
200% indication, evidence expansion, error/empty clearing, superseded reads and
loaded-point identity.390px viewport had no document horizontal overflow.
The browser transport fixture is explicitly synthetic and separate from the
real PostgreSQL/HTTP-to-Web-model verification already recorded. This interaction
is now included in hosted browser acceptance; same-SHA results remain required.
Hosted d76c829/run40866724770 and5ed06fc/run40865762328 completed all11jobs green.
The long local Linux run overlapped edits and ended4930passed/96skipped with
five failures/three build errors; it is not a clean same-SHA completion claim.
Delivery gaps below remain open; do not infer customer readiness from these gates.


## 2026-10-29 — recurring ENTSOG explicit point scope

Both existing recurring runners now accept the same repeatable/comma point
scope as the direct ingestor, using one extracted validator. Canonical immutable
scope reaches each retry alongside its frozen time window. Non-ENTSOG scheduled
jobs receive no point flag; invalid scope refuses before subprocess. Empty scope
retains compatibility and proves no coverage. No source activation is performed.
Root reviewed the command paths and tests: runner/scheduler/CLI47passed;
window/architecture53passed; Ruff passed. Same-SHA hosted PG integration for the
preceding5ed06fc correction passed; full hosted run40865762328 is still running.
Web native client/model/panel work has1036passed/3skipped and production build
passed before pagination follow-up. Real PG HTTP envelopes reached actual Web
model with exact92954921/738726002.1/416592000 strings; backend-parser-to-Web
verification passed all eight native-unit shapes. This is bounded evidence,
not European coverage, customer authentication or delivery completion.


## 2026-10-29 — hosted native integration regression corrections

Hosted run40863573034 on2dff9d4 passed ten jobs but validate failed six tests.
Moved the exact native payload codec below application so DB and ingestion no
longer import application; application reexports preserve the same error type
and public helpers. No architecture gate exception or quantity-rule weakening.
Updated positive ENTSOG security/glossary fixtures to genuine explicit native
volume payloads; licensed negative fixtures and scope assertions remain. CLI
mock now explicitly accepts and checks the actual empty point-scope tuple.
Root verification: native projection/API/SDK-wire/CLI81passed; architecture,
security entitlement and glossary33passed; Ruff import ordering corrected.
Full hosted regression and nested security evidence still require same-SHA CI.
Shared Web native client/model/panel implementation is in progress separately;
remaining delivery gaps listed below remain open.


## 2026-10-29 — native ENTSOG ingestion, guarded reads and source SDK connected

Replaced the fixed-CV flow/capacity normalizers with explicit receipt-bound native
rates. Exact raw JSON number tokens reach the shared Decimal parser; energy has
no volume, real volume rates use only same-dimension scaling. New deterministic
namespaces retain original provider ids; append/replay and semantic-conflict
refusal preserve legacy rows and first receipts. Physical API opt-in native mode,
volume-only compatibility reads, agent DB bridges and analysis/report snapshot
admission now share the guard. Unverified legacy volumes and native energy are
not reported as mcm. Bad native payloads are typed refusals, not empty readings.
Native query overflow refuses; default volume reads are not silently truncated.

New typed native SDK methods preserve exact strings and metadata. Review caught
invented SDK field names despite green synthetic fixtures: fixed them to actual
backend fields and added actual-projector-to-SDK contract tests. Source status,
period type and operator key are carried when captured, without inferring quality
or physical authority. Explicit CLI point-direction scope now reaches both flow
and capacity, retaining date/budget/source-certification gates and leaving
reference queries untouched. Generic unscoped samples encountered N/A exemptions;
they were correctly refused as zero usable rows, never converted to zero.

Root captured a published DE-TSO-0009/ITP-00126/entry direction forOct28..29:
two populated energy flow rows and one technical capacity. Dedicated PostgreSQL
first inserted2/1, then real recapture inserted0/0 and verified2/1unchanged rows;
first receipts and full projections were preserved. A real loopback HTTP server
plus source SDK read actual PG quantities92954921,738726002.1 and416592000kWh/day
as strings, with no volume, and anonymous access401. This is not installed-wheel,
SSO, regional completeness or model accuracy proof. Raw hashes and limitations
are in docs/data/ENTSOG_NATIVE_RATE_OPERATIONS.md.

Validation: new integration delta151passed; core/projection/SDK/wire149passed;
existing analysis/agent/contracts68passed; physical API/context30passed; native
persistence10passed on realPG; data-product contracts15passed; product-boundary
checks3passed; Ruff passed. Extended complete PostgreSQL CI ran from an empty
owned database through0044 plus authenticated/anonymous smoke and49tests, all
passed without skips. Root corrected local shell CRLF after a failed attempt;
the successful rerun used LF. An obsolete test imported the removed CV constant:
replaced its import smoke with the actual normalizer. Full canonical Linux
regression is running; its first collection failure is retained separately.
Latest fully green hosted checkpoints:8108fb8/run40855865853 and
d49d32a/run40856477170. This new integration still needs same-SHA hosted results.

Remaining: shared Web/desktop native-rate business consumption, native-read
history/window ergonomics, scheduled point-scope configuration/source activation,
full provider quality/revision semantics, real regional weather-demand/portfolio
vertical, optional numerical/decoder dependency delivery and redistribution,
public market-price consumers, snapshot replay and customer SSO/native UAT.
Do not mark delivery ready from this bounded native-source integration.

## 2026-10-29 — RFC0005 native-rate schema and exact raw numeric tokens

Root accepted RFC0005/Decision19 for coordinated native-unit migration. Existing
volume clients keep numeric contracts; opt-in native representation, agent guards,
raw-lexeme normalization, immutable namespaced rows and shared clients follow in
stages. The fixed-CV source normalizer remains a known defect until connected.

StageA0044 adds nullable native version/payload and gated nullable volume on the
existing flow/capacity tables. Real PostgreSQL schema suites passed18, including
old REST evidence and new native upgrade/downgrade/refusal cases. An actual full
Alembic0043-to0044 upgrade on the dedicated weather acceptance database passed;
all three existing forecast rows retained their content digest, and authentic
ECMWF query/hash/first-receipt verification still passed. Root fixed the SQLite
copy's lost kind=actual server default and a test fixture that accidentally
supplied a non-null volume for its intended null-volume rejection. The earlier
0043 test now checks its preserved ancestry; the0044 suite pins the current head.
This does not migrate customer databases or create production source approval.

A separate EntsogPage.numeric_lexeme_payload view preserves numeric source tokens
straight from exact raw bytes; protocol pagination/default payload are unchanged.
Lexer plus transport tests103passed; architecture alignment8passed; existing
API stability/reachability9passed; legacy ingestion/upsert/API regression27passed.
Strict native read projection now passed49focused tests; combined native-core/
projection/pipeline wiring suite101passed. Review removed a metadata-only shortcut,
requires the actual version/payload columns, rejects forged native quantities and
unknown/partial versions, and requires exact aware timestamp cross-checks before
accepting naive fixture instants. Legacy case variants cannot bypass admission.
No route or ingestion consumes this helper yet; those changes remain pending.

The existing PostgreSQL CI script now explicitly runs both schema modules with
the actual test DSN. Root executed the complete script in a newly created isolated
PostgreSQL database using canonical LinuxPython3.11: all migrations to0044,
required tables, authenticated/anonymous HTTP smoke and39tests passed with no
skips. This includes the real PostgreSQL schema branches, separately from the
fast SQLite mechanics. Ruff passed. Do not claim native business consumption or
ENTSOG defect closure from these foundation checks. Latest fully verified hosted checkpoint
remains c171dc8/run40853172800 (all eleven jobs passed).

## 2026-10-29 — operator ECMWF ingestion and native-unit foundation

Pushed a67460c adds an explicit operator ECMWF capture/archive/append CLI and
runbook. Root ran real Linux Python3.11/ecCodes2.50 against the2026-10-29/00run,
steps27/30, London51.5,-0.1. Both raw fields were archived and two rows inserted
in the dedicated PostgreSQL acceptance database using explicit local test
identities. A later capture inserted zero rows/two duplicates; strict query and
projection matched hashes and original receipt timestamps. This verifies the
operator path, not production mapping/certification or regional demand accuracy.
New CLI plus existing transport/decoder/repository/capture suite94passed; Ruff
passed. Root fixed a worker import of the decoded type from the wrong module.
No decoder dependency was added to delivered requirements. Windows nativeecCodes
and optional-dependency redistribution remain open. See the runbook for hashes.

Pushed9729c0e adds the precise ENTSOG native-rate core:51tests passed. It preserves
explicit numeric text and exact Decimal rates, converts only within energy or
volume dimensions, and refuses unsupported units/floats instead of assuming a
calorific value. This core is not connected to public_sources.py yet: its old
fixed-CV conversion is still a known delivery defect. Next requires coordinated
schema/persistence/read/API/SDK/Web consumer migration, preserving legacy rows
and forbidding legacy Float values from masquerading as exact provider tokens.
Do not claim that the staged parser alone fixes ENTSOG ingestion or closes supply
and capacity integration. Full Python regression exposed the security acceptance
script's stale189-path pin. Updated it to the declared191 (strict equality
retained); independent script returned automated PASS. The original full run
finished4688passed/80skipped/3failed, with all three failures from that stale pin.
Fresh-process replay of all three affected tests passed3, including the actual
nested security suite (270.70seconds). The full run collected before the new
native-unit/CLI tests were added; those are separately covered by51 and94 focused
passes above. Full-worktree Ruff passed. All eleven hostedCI jobs for c171dc8,
run40853172800, completed successfully: full validation, PostgreSQL, EN/ZH browser,
Web build, dependency/CVE and Python notice checks, three native builds and two
installed-wheel SDK jobs. This is a verified staged checkpoint, not full delivery
acceptance or evidence that isolated model/decoder dependencies are shipped.

## 2026-10-29 — governed weather API/SDK and shared client evidence panel

Pushed weather GET forecast reads and POST caller-weighted degree-day computation,
typed SDK requests/responses and the shared Web/desktop Source Center forecast
evidence panel. Both routes retain identity, commercial entitlement, persisted
provider certification and row filtering. Point-in-time issue/receipt selection,
explicit region weights and coverage remain mandatory; no source is automatically
activated. Missing daily coverage is null, not zero. This is staged integration,
not completion of the regional demand or portfolio consumer vertical.

Root validated six focused panel tests and the full Web suite:1005 passed,
three skipped. Production build passed with existing bundle warnings. The first
panel harness failed to intercept Vite-resolved API aliases; corrected and rerun
without weakening stale-response/abort/unmount/empty-state assertions. HDD/CDD
SDK plus reachability tests passed13; API stability/architecture/reachability
checks passed17 after registering both additive paths in the exact contract.
Full Python regression is running; no fresh all-green CI claim yet. Pushed
checkpoint f36983a includes the declarations; ec40aae includes the panel,
bb2ee4f the degree-day SDK. Older 1ee800b CI failed on missing declarations and
reachability, including nested security evidence. Those causes were reproduced
and corrected; a new same-SHA hosted result must prove closure.

DeepSeek is implementing a bounded operator ECMWF capture/archive/append CLI;
it is not yet accepted or tested. Optional decoder/numerical dependency delivery,
real regional weighting/history/OOS model evidence, forecast-to-demand-to-business
consumers, ENTSOG native-unit correction, public price integration, snapshot replay
and authenticated customer UAT remain open. Isolated NumPy/ecCodes probes do not
establish delivered runtime dependencies or redistribution clearance.

## 2026-10-29 — REST demand persistence verified, consumer integration pending

Current pushed implementation checkpoint919a0a3 includes keyless National Gas
REST capture, explicit provider-clock evidence, additive0043 schema and immutable
REST revision persistence. Root fetched17 authentic revisions and persisted them
in dedicated PostgreSQL:17 inserted initially, zero inserted/17 duplicates on
later-receipt replay. Default availability remains actual receipt; the maximum
of three provider clocks is explicitly derived evidence and does not authorize
historical model admission. CSV/REST identities remain separate.

Real PostgreSQL0043 upgrade succeeded, seventeen existing forecast repository
invariants passed, and the dedicated schema suite passed all ten tests including
upgrade/downgrade. The first PG attempt exposed BatchOperations/module-operation
API mismatch; fixed. A second attempt exposed pg8000's unsupported options
argument in the test fixture; fixed using an owned-schema connection event.
Parser/persistence/CSV regression suite37passed; Ruff passed. Weather ontology
review0188f65 passed49 focused tests, preserving enum values and imports.

Model-input admission and operator REST CLI implementation are in progress.
Do not promote receipt-limited historic data to forecast OOS evidence, aggregate
CSV and REST copies, treat blanks as zero, or claim D+6 finality. Latest hosted
runs for0188f65/8df0765/ce04801 are still running;919a0a3 is queued. Thus no new
complete hosted-green checkpoint is claimed. Dependency redistribution closure,
regional weights, historical calibration, API/SDK/Web/portfolio consumers and
the other source/snapshot acceptance gaps remain open.

## 2026-10-29 — staged weather feature and demand inference implementation

Accepted the pure weather domain core and persisted forecast projection bridge
as staged RFC0003 implementation. Explicit weighted degree days preserve DST,
coverage gaps, forecast vintages and feature-policy identities. SQLite integration
uses actual repository-persisted rows: changed temperatures change HDD and later
receipts do not leak into an earlier prediction origin. Future inference applies
frozen coefficients and rejects model-selection evidence before its validation
cutoff. Selection identity binds fold results, metrics and residual intervals;
inconsistent result/evidence combinations are refused, not silently reused.

Root validation:47 focused tests passed on both Windows and Linux canonical
Python3.11 with isolated NumPy2.3.5; Ruff passed. Default runtime without NumPy:
31passed/16skipped, so default CI alone does not prove fitting functionality.
No dependency lock or source activation changed. Optional backend dependency
delivery, authentic multi-step capture, real target/history calibration and
API/SDK/Web/portfolio consumers remain required before acceptance. Synthetic
model fixtures are not evidence of real predictive accuracy. Last hosted CI
checkpoint8cc3418/run40724318398 succeeded; this staged change needs a fresh run.

## 2026-10-29 — weather integration review in progress

Verified source checkpoint `61dfc3bbcbae64f792e33f1f3d3d05a3fb520dd2`:
GitHub CI `40721172633` completed successfully. Canonical Linux Python3.11
isolated ecCodes2.50 decoder also decoded the authentic ECMWF capture recorded
below. Exact installed license/native inventories were collected separately for
Linux3.11; this is evidence collection, not dependency redistribution approval.

Draft weather core and instant-to-interval bridge passed36 focused tests in the
isolated canonical Windows3.11 NumPy environment. They remain uncommitted pending
integration and dependency review. The bridge filters by issue and receipt time,
uses explicitly bounded left-hold approximation, and refuses extrapolation or
mixed field revisions. Direct persisted-row projection/integration tests are in
progress. Root also identified the missing public future-demand inference entry:
implementation must bind selection evidence availability to validation cutoff,
so later OOS evidence cannot authorize an earlier historical prediction.

ENTSOG native-unit correction remains open: an assumed calorific value must not
turn provider energy into factual volume. A first proposal lacked actual schema
and consumer inspection and was rejected for implementation; reconciliation is
in progress. Preserve immutable vintages and do not infer exact source decimals
from legacy binary floats. No source activation, production model promotion or
overall delivery acceptance is claimed by these checks.

## 2026-10-28 — unified access pipelines and authentic weather capture

Latest verified code checkpoint: `bde28a8f0d68914ff192839f120a6395009cf60e`,
GitHub CI run `40716183139`, completed success. All eleven hosted jobs succeeded:
full validation, dependency/CVE audit, Python notice evidence, PostgreSQL,
bilingual browser acceptance, Web build, Windows/Linux installed SDK, and native
Windows x64/Linux x64/Linux ARM64 builds. This supersedes the older checkpoint
and pending-launch statements below; those sections remain historical evidence.

RFC0004/Decision18 governs shared native/SDK pipelines and stronger G1 leaf-job
requirements. CI/main/PR/manual share the native workflow and SDK workflow.
Release G1 now requires the actual three native and two SDK hosted leaf jobs in
addition to its original jobs; no publication/signing/external gate is waived.
Developer entry: `docs/engineering/MULTI_SURFACE_DEVELOPMENT.md`, linked in README.
Local focused pipeline/bootstrap suite65passed; gate/source/Rust contracts185passed;
the independent security-suite evidence replay passed (236 seconds). Local
locked Web build passed, 996tests passed/3skipped. A separate canonical Python
3.11.12 Linux installed-wheel run at bde28a8 imported29SDK modules and passed all
six real loopback economics HTTP cases; no source SDK import was used.

The previous portable native workflow overwrote Tauri's embedded production
binary with plain Cargo output. Fixed6fb6b18; new three-platform build succeeded,
and verified Windows portable artifact0344b2eb0700cc77ea42c4eb81871ee64ddbeb4cc689f26e5a737afb6ad98e62
loaded its bundled `tauri.localhost` sign-in page. The user stopped computer use
with physical Escape before credentials or login submission. UI input remains
stopped pending explicit resumption; logged-in native business UAT is still open.
Linux DEB installation does not prove logged-in native business UAT either.

National Gas actual-demand adapter/repository/migration0042 shipped9eaf657;
schema declaration advanced a76aac9. Root18focusedtests passed, and a real
public download plus isolated full PostgreSQL migration/replay stored nineD+1
revisions and twoD+6 rows with zero duplicate inserts on replay. Units remain
mscm; publication timezone remains unresolved and availability is receipt-only.

Authentic ECMWF IFS00z +24h temperature GRIB2 capture/decode shipped5cbfa31;
root54focusedtests passed. Exact selected message316916bytes, SHA256
b5f2d7539233af58073c3c92abb6b1b672d4506558bab5226756c4ac370f5ba0.
Linux ecCodes2.50 validated parameter167/K/grid/run/validity and mapped the
explicit London location to9.177087402343773C. This is a forecast grid value,
not observed weather or regional model accuracy. Windows ecCodes' embedded
definitions failed in the isolated probe; client operation via Linux backend is
separate. Optional dependency/license/native-binary closure remains open.

Point-bound append-only forecast persistence now reuses the existing forecast
table, with explicit per-point series/entity/mapping identities, no broadcast,
and independent source-field revisions. Root24SQLite tests passed; 17 synthetic
repository invariants also passed on migrated PostgreSQL. One-point versus
64-point lookup count remains constant (at most six SELECTs). Actual provider
corrections append; widening a point request retains existing point rows and
appends only new points. No data source is activated by the repository.

Current unaccepted work: pure weather-demand core with explicit region/bases/weights/calendar/
temporal policy fingerprints (18isolatedNumPy tests pass, still under review);
dependency and public-source gap drafts. No API/SDK/Web model-consumer completion
or real OOS accuracy is claimed. Source audit also found implicit ENTSOG kWh/day
toMCM/day conversion via fixed10.55kWh/m3 and unsupported-unit fallthrough;
review and correct unit truth before using those numbers as certified inputs.

Full delivery remains open: actual source-to-business consumption, model/OOS
validation, canonical public price ingestion, snapshot row/revision replay,
source capability/queue truth, installed native UAT, and security/release/signing/
customer gates. Use the full owner objective; green pipelines are not completion.

## 2026-10-28 — public-data and demand-model direction

Owner confirmed market data acquisition should use official Data-page downloads
when no API subscription is supplied; paid API credentials are not a prerequisite.
Owner explicitly chooses keyless ECMWF Open Data, and requires weather to be used
in regional supply/demand predictions (HDD/CDD and measured better models), not
merely collected. RFC0003/Decision17 accepted e0dd7a0; the generated vertical plan
remains a proposal where it conflicts, especially future-valid forecast features
and unnecessary parallel storage. Existing ForecastObservationRecord and dataset
point-in-time foundations are reused.

Current main9bae9ce has same-commit remote CI success40557768170 and three-platform
native build-only success40557820701. Local full suite4334pass62skip. Root downloaded
all three archives and verified GitHub digests, package/binary hashes, source SHA,
tracked-source cleanliness and actual canonical Python/Node/Rust. Linuxx64 DEB
installed in Ubuntu24.04; UI launch/business acceptance remains open. Windows
verified acceptance copies are under outputs/EurogasNexus-9bae9ce-Windows-x64-acceptance.
The computer-use policy requires action-time confirmation before launching newly
downloaded Windows software; an async owner question is pending. No need to stop
source/model work while waiting.

Owner provided a temporary GIE credential: stored only with Windows CurrentUser
DPAPI encryption outside Git. Root actualAGSI/ALSI connection probes200,2rows each
normalize successfully, one page only, not a history/commercial-certification claim.
A current owned loopback API runs with that credential supplied only in process
environment; never expose the value or commit it. Existing runtime/certification
controls are retained.

Reviewed EEX public downloader and capture tests77pass1skip; actual officialCSV
fetch200,286bytes,fourrows,zero row rejects, rawhash6d0b9da4ff997a57d97fb2053aefd96af6e617cdf3551bd9db3ec2310c9668aa.
Canonical publication/calendar/granularity remain unresolved; no fabricated UTC,
tradable quote or source activation. Root continues official methodology research.
ECB main entry omitted its existing runtime stop gate; bounded DeepSeek fix adds
ECB to the actual main gate loop. Root17gate tests and Ruff pass.

Actual public National Gas CSV works without a key. Captured catalogue names
PUBOB652 actualNTS D+6 and PUBOB637 D+1 native mscm, with revised/provisional data;
blank quality is unknown and A meansAmended, notActual. PUBOB4422 energy candidate
returns empty; no inferred CV conversion. PUBOBJ1030 energy samples require a
separate verified unit/scope before use. CSV publication zone is not yet proven;
keep wall clocks and conservative receipt availability. Official Ofgem evidence
supports05:00GBlocal gas day; use existing EU_CAM_UTC for new data, notUK_LEGACY.

Live DeepSeek tasks: ECMWF bounded index/range transport and authentic ecCodes
adapter; National Gas actual-target append-only ingestion/storage (0042 reserved).
Root retains numerical/source/architecture review. Snapshot binding design and
source audit drafts remain unaccepted implementation. All actual consumer/model,
provider/installed/security/signing/customer gates remain to be proved.

## 2026-10-28 — connected costs and durable workflow verification

Tariff business-date propagation and missing-cost refusal pushed5216b69. Actual
portfolio gas_day flows into tariff selection/resource-pool/recommendation and
intraday scanning; missing input stays null, explicit zero stays zero, canonical
GBP/MWh is carried without EUR substitution. Caller references remain unverified.
Connected bridge Python82pass; complete API/SDK618pass. Full Web996pass/3existing
skips, TypeScript and production build pass. Known chunk-size/dynamic-import
warnings remain visible.

Durable economics acceptance pushed02593cd: actual PostgreSQL-backed Chromium
203checks, EN/zh-CN1440/390px, eight axe runs with zero violations; installed
checkpoint SDK six actual HTTP checks. Root script tests9Python/7Nodepass.
Keyboard-focusable LNG scroll regions fix a real mobile axe failure. Vite ignores
only atomic-editor hidden .tmpdir staging paths; an actual exclusive file-lock
probe leaves Vite serving200. Final source-bound artifact rebuild remains open.

Remote09e8ac9 CI: browser/PG/Web/Python CVE locks and environment pass; validate
three failures identified (stale Review probe contract and wrong-principal test
fixture), Rust license gate refuses two r-efi triple-license declarations. These
remain failures until corrected/reviewed and CI reruns; no gate disabled. Bounded
DeepSeek workers implement review test corrections, native build-only evidence,
and draft a reviewed-license-choice proposal. Root reviews and tests each.

Decision case/pack batching root selection30pass with actual SQL query counters,
Ruffpass. Analysis snapshot row binding/history/access/replay remains an explicit
architecture gap; drafts are not accepted implementation or customer evidence.

## 2026-10-27 — fresh Windows recovery and acceptance continuation

CI recovery checkpoint: GitHub a8af2b7 revealed five build-tool vulnerabilities;
reviewed patched floors and universal hashes pushed8ba6045, with only filelock/
msgpack/setuptools version changes. Isolated hash install, installed-environment
and fully pinned direct-lock CVE audits: no known vulnerabilities.69-package
metadata license detection passes. Patched setuptools builds the unified
backend/SDK wheel; isolated installed imports expose189paths and installed SDK
example passes six actual synthetic HTTP checks. Resolver-enabled shipped-lock
CI3.11 audits and final artifact binding remain required.

Fresh full API/SDK regression617pass. Browser CI also exposed relative configured
Playwright entry being treated as a package name; resolve it against cwd. Review
history now declares record ids and is compared with its actual ReviewContext
projection, replacing a whole-page n/a heuristic (no exemption or disabled
checks). Fresh-source API session28829 and Web38053; same relative dependency
configuration now completes96browser checks/16workspaces/EN+zh-CN/threeviewports,
zero failures. Review-focused Web31pass. An earlier rerun500 came from an old
API process mixing lazily imported updated repository code with an old dataclass;
it is recorded as failed, not ignored. Restarting our owned API from consistent
current source resolved it. Final immutable artifacts need their own verification.

2026-10-28 integration update: reviewed tariff-date selection pushed8b1edad;
cost JSON missing/zero/atomicity fix9b3a893; retained EEX decimal consumption
0b73bed; GIE SDK payload parity and ALSI explicit-energy-unit fix9c006ac;
central LNG semantic vocabulary/control-code ownership676796c. Each is a
replacement implementation, not recovered original cloud source.

Independent new evidence: exact-price/parser/cost selection147pass; GIE source/
transport/SDK selection117pass; tariff/SDK combined38pass including strict date
coercion refusal; LNG ontology/new+legacy/reference selection215pass. Full
contract rerun571pass after centralizing semantic enums and making the markdown
escape fixture use a simulated repository inside its own scratch directory.
Ruff passes on reviewed changed Python modules.

Capacity and LNG API/typed SDK plus actual existing-workspace Web forms are now
implemented. Root real HTTP: capacity9checks and LNG8checks, distinct synthetic
ANALYST/VIEWER/anonymous identities, no added commercial grants. Actual browser
LNG EN/zh-CN golden550EUR margin/482.5EUR NPV and7consumed/3loss/10reduction,
Ctrl+Enter, success focus,390/1440px overflow, draft invalidation and conservation
refusal pass. Capacity browser23h golden/refusal/edit invalidation, shortcut,
success focus and390px overflow pass. Visual inspection found and fixed bare
capacity form wrapping and ensured LNG success scroll reveals the monetary
summary. Full Web988pass/3existing skips; TypeScript/production build pass
(build will be refreshed for final source). Measured public surface189paths/
203operations; both endpoints have real Web reachability, no gap exemption.

Linux native preparation: Ubuntu24.04 dependencies installed; pinnedRust1.94.0
locked cargo check passes. Node24.13.1 archive SHA checked; desktop CLI2.11.2
installed from committed lockfile in separate dependency cache with zero audit
findings. These are prerequisites, not final bundle/installed acceptance.
Next: continue actual tariff-date consumer propagation (bounded DeepSeek worker
active), source/strategy/context adoption, durable acceptance scripts, full
API/SDK and final committed-source backend/SDK/native artifacts. All production
provider rights/certification, issuer/security/signing/customer gates stay open.

Latest independently verified checkpoint: DeepSeek reconstructed LNG economics-only
and explicit energy-stage accounting, preserving the strict legacy readiness path
and sharing one monetary/cash composer. Root reviewed conservation precision,
separate consumed/loss totals, no extra energy monetization and shared cash
valuation. LNG legacy/new economics/energy/terminal/regas selection:192pass;
changed Python files Ruffpass. Official terminal manifest now contains five
captured sources/seven CANDIDATE facts, retaining exact bytes' hashes, literal
units and unresolved Grain645/654GWh/d bases. No reviewed facts/effective dates
or source-to-operational-system identity binding are inferred.

Capacity domain/API/SDK/portfolio selection:86pass, Ruffpass. Dedicated synthetic
PostgreSQL real HTTP: anonymous401, separate VIEWER403, ANALYST23h/25h/pence
calculations200 with exact expected decimal strings; numeric JSON/inconsistent
billing/runtime-context requests422. Source SDK real HTTP200; installed artifact
verification remains open. OpenAPI188paths/202operations census:6pass. Web
capacity workflow is being implemented, so surface-reachability gate is still
pending; no exemption was added to hide it. API was restarted from current source
in our managed loopback session53759; Web session27879 remains in use.

Existing synthetic browser sweep completed:96checks,16workspaces, EN/zh-CN,
three viewports, zero failures in that bounded read/render workflow. This does
not close distinct-persona business workflows, real providers, production SSO,
performance or final Windows/Linux artifact gates. DeepSeek Harness shell calls
hit a temp-lock ACL failure; root runs actual tests and does not treat workers'
static review as passing evidence. Owner-authorized Flash1017/max workers now
implement capacity Web and LNG API/SDK; a separate read-only source census runs.

Accepted replacement slice: official local Harness workers completed the missing
EEX byte-preserving local capture inspector/CLI and LNG terminal-reference
contract/offline comparison. Root reviewed the actual implementations and ran
combined capture/parser/terminal/regas selection:97pass, Ruffpass. EEX worker also
reported306ingestion/import-boundary passes; terminal worker43focused/adjacent
passes and repository-local markdown link pass. No live source integration or
browser delivery acceptance is inferred. Current empty official manifest is a
contract starting point; researched candidates still need structured insertion
and applicability review. Source activation and canonical EEX publication remain
prohibited without their existing independent gates. Core/CLI files are new
implementations, not restored original cloud files.

Foreground loopback API(:8000, managed handle21508) and Web(:3000, handle27879)
now run; readiness and Web HTTP both200. This safer managed launch succeeded
after the background launch was rejected. PostgreSQL-backed synthetic browser
fixtures are ready, Chromium installation completed. Actual workflow sweep and
distinct-role acceptance remain next. Capacity API/SDK worker is still active;
its writes are separate from this accepted capture/reference checkpoint.

Latest integration checkpoint: local installed DeepSeek Harness0.2.1-rc.2 is
verified with headless Flash1017/max. Owner explicitly authorizes multiple
DeepSeek workers; disjoint EEX capture, terminal-reference and capacity API/SDK
tasks now run through separate Harness sessions and perform their own focused
checks. Earlier one-shot generations hit reasoning/output limits; incomplete
files were not treated as accepted output. Root still reviews actual diffs/tests.

Fresh browser bootstrap found a real UAT seeder defect: repeated synthetic ICIS
day-ahead IDs across autumn DST queued duplicate INSERTs with autoflush=False.
DeepSeek's bounded fix flushes once per chronological simulated day, preserving
one transaction and existing generator/calendar/identity semantics. Regression
invoking the actual60-day seeder fails before the fix (duplicate primary key),
passes after it including a repeated run and unrelated-row preservation; Ruff
passes. Actual same isolated PostgreSQL browser DB now seeds2350 labeled
synthetic observations and the existing test-identity helper succeeds. No reset,
source activation, commercial grants or production AI enablement performed.

Reconstructed capacity core independently reviewed: exact Fraction billing-basis
comparison and half-even money rounding, explicit UTC duration, shared cash bound,
strict Decimal inputs, NOT_ASSESSED physical readiness.44focused tests pass.
It remains uncommitted pending complete legacy-guard/API/typed-SDK integration.
Root supplied an additional exact rounded-equality counterexample to the worker;
passing the easier near-coefficient test alone does not close that precision gate.

Acceptance infrastructure: WSL2/Ubuntu24.04 and isolated PostgreSQL remain healthy.
Browser fixtures are in distinct nexus_browser_20261027; the integration DB is
nexus_verify. Source API/Web background startup was rejected by automatic policy
review before execution; managed foreground service acceptance remains to run.
No browser workflow or native artifact acceptance is claimed from fixture setup.

Current source baseline was `35a587b`; recovery audit checkpoint `c5e0672` is
pushed to main. The previous cloud workspace is unavailable here; reported local
checkpoints and unpublished LNG/EEX files are absent. Original **Set up
EurogasNexus** conversation was read for development requirements; missing work
extends to earlier tariff/capacity, route, context and key-rotation slices.
No recovery of original commits or files is claimed. See
`docs/release/acceptance/23_DELIVERY_RECOVERY_AND_GATES.md` for current evidence
and the full gate register. Historical entries below retain their original scope.

Owner now explicitly requires DeepSeek implementation (superseding the older
task-specific Sol-only routing), max reasoning on subsequent tasks, reconstruction
of missing work, user acceptance readiness, data-source integrations and periodic
reviewed non-force pushes. Keep one worktree and existing rigorous foundations.

Secure local DeepSeek binding and authenticated connection verified; first bounded
DeepSeek edits correct two import-order failures and Vite dependency floor.
Reviewed final locks resolve Vite8.1.6/source-map-js1.2.2. Clean npm12 install:
zero known vulnerabilities; Web950pass3skip, build pass, Ruff pass, affected
backend33pass. Fresh baseline API/SDK/contracts1102pass; LNG/EEX174pass.
No commercial readiness inference from these counts.

WSL installed, Ubuntu24.04 runs under WSL2, Docker linux/x86_64 available.
Distinct fresh PostgreSQL16 acceptance container is healthy at loopback55432;
generated secret is ignored, old environments/containers/data remain untouched.
Next: migrate/verify isolated DB, map all unpublished slices against current source,
then reconstruct capacity/route and LNG prerequisites with DeepSeek max before
Web/SDK/source-to-consumer acceptance and final-source artifact rebuilds.

Full delivery goal remains active; customer/provider/signing/production gates
remain unproven. Regional exchange remains disabled and deferred.

Follow-up: fresh PostgreSQL migration through0041 succeeded; the five existing
PostgreSQL integration modules passed21tests. DeepSeek max reconstructed missing
key-rotation scope/default-expiry preservation and validated-operator attribution;
repository/API/security regression30pass, Ruffpass. Capacity billing reconstruction
is in progress with DeepSeek max; no capacity patch accepted yet. All missing
checkpoint IDs also fail GitHub commit lookup. Continue reconstruction rather
than claiming historical source or acceptance restored.

Owner model selection: use **DeepSeek-V4.1-Flash-1017**, max effort. Official
DeepSeek October17 changelog maps that version to API id `deepseek-flash`;
authenticated model discovery confirms max effort support. The local development
harness now pins that API id (product provider settings remain untouched). A Pro
review request issued before this steering was canceled, and the capacity review
was reissued on the specified Flash model. Initial Flash capacity output required
JSON-container repair for inspection; it is a candidate only, not installed code.
Independent review identified precision/bounds and fractional-hour consistency
concerns; corrected implementation/test output is pending. Separate Flash max
EEX local capture-inspection reconstruction is pending; no production source
activation or download permission is inferred.

Official terminal publications are now reachable from this machine. Five raw
page captures were hashed and preserved in ignored local evidence. Reviewed
research candidates in `docs/data/LNG_TERMINAL_RESEARCH_CANDIDATES_20261027.md`
preserve original units, the Gate evaporation denominator, Grain's two distinct
capacity claims and unknown effective dates. No official fuel retention rate or
physical readiness was invented; these candidates are not automatic model inputs.

Last updated: 2026-10-13
Audit baseline: `e911fae`, equal to `origin/main` at audit start. Historical slice records below do not constitute current production approval.

## Current work
### Independent customer initialization run found two failing cases (2026-10-13)

Parent ran tests/release/test_customer_initialization.py during implementation:
16 passed,2 failed (complete OIDC and allow_http cases). Synthetic client-secret
comparison sees doubled dollar signs in Compose config serialization. This is not yet
proof of actual container credential corruption: delivery agent must verify effective
runtime value with synthetic credentials in an isolated existing image, without database
or mounts, before correcting implementation or serialization expectations. No customer
initialization pass claimed from this invocation; final rerun remains required.

### Actual persisted strategy recovery evidence arrived (2026-10-13)

Parent inspected save-retry-recheck.json: same owned strategy now has real DRAFT
version strategy-version-d3425ca270a84a698437, reload hash
sha256:91e44ea4b654ee6309ac5603ad0faa00b27309f960329127051061f37b7dabff.
Persisted resource is exact owned LNG UAT id, quantity987 and explicit synthetic
all-in cost31.125 GBP/MWh. This proves recorded save/reload, not market compatibility
or backtest readiness. Worker deliberately lost the successful version response and
reconciled the stored version. Final correction still must refuse an ambiguous earlier
POST followed by empty read and preserve uncertainty across reload; backend durable
idempotency/cross-client reliability remains open. Final original-row comparison pending.

### Response-loss race remains a strategy-save gate (2026-10-13)

Parent reviewed new strategyDraftSave helper and focused tests. Stable client identity
and exact-version recovery address acknowledged/lost-after-commit cases, but an empty
GET after an ambiguous POST does not prove the original transaction cannot still commit.
Agent must handle this race without a blind second version POST; the current fixture's
"aborted before server" label is not evidence a browser can distinguish that outcome.
Durable idempotency or an explicit unresolved-outcome recovery path is required before
claiming robust retry. The36 reported focused passes do not close this uncovered case.

ENTSOG agent acknowledged replay review: remove memory fallback, require persisted
scheduled anchor, pass frozen rolling anchor to child and persist open-day qualification
with warning status in ingestion-run evidence. Await implementation/integrated checks.

### Rolling-window independent tests and replay review (2026-10-13)

Parent independently ran tests/ingestion/test_entsog_window.py:25 passed. This proves
the bounded date/calendar helper cases only. Review found scheduler fallback anchors
stored in a128-entry memory cache cannot establish restart-safe replay (eviction and
object-id reuse also matter). Existing ENTSOG agent was instructed to require persisted
scheduled time or persist the chosen anchor, rather than claim durability from this cache.
Parent also requested open-current-day qualification in persisted ingestion evidence:
stdout-only warnings while the child receives explicit dates are not sufficient provenance.
Integrated worker/scheduler acceptance remains pending these corrections and tests.

### Duplicate strategy retry reproduced in actual browser (2026-10-13)

Contract agent reproduced the pre-fix failure and parent located save-retry-baseline.json:
first create succeeded with owned DEV UAT identity strategy-d82b5a9a7a09403a;
controlled version-request abort followed by Save retry attempted a second strategy POST.
The guard aborted that second request, preventing a duplicate database identity. Exactly
one new owned identity without a version is retained for completing the corrected workflow;
do not recreate it. db-save-before.json now also covers original strategies alongside the
prior six groups. Correction and persisted reload verification remain in progress.

### Strategy retry review expanded to unknown server outcomes (2026-10-13)

Parent traced selectedStrategy to cached strategies.find(id), so an acknowledged create
followed by a failed version POST can also leave selectedStrategy null and duplicate
identity creation on retry. Existing API permits explicit strategy_id and refuses duplicates;
version creation instead allocates a fresh UUID/number on every call, without idempotency.
Contract agent received these findings: preserve acknowledged identity independently of
list hydration, test lagging reads, and reconcile or explicitly block ambiguous version
responses rather than blindly retrying. No exactly-once claim is supported yet.

### Installer regression confirmed; bounded rolling policy defined (2026-10-13)

Parent confirmed customer Windows Install-OrRepairRuntime still invokes removed
preview-seed/simulated-prices services, including default stop of the absent service
after migration/API startup. Delivery agent owns correction across wrapper/installer
and command-plan checks, including rejecting obsolete simulation requests before side
effects. Artifact exclusion alone did not prove customer installation works.

ENTSOG continuation proposes opt-in1..30 prior gas days plus open current day using
existing EU-CAM calendar, fixed per iteration/retry and scheduler scheduled_for_utc.
Parent requires actual worker/scheduler option propagation, refusal of invalid/naive
scheduled timestamps, DST/rollover tests and explicit distinction between provider date
envelopes and canonical UTC intervals. No source enable, silent revision replacement or
snapshot consistency claim. Implementation and tests remain pending.

### Independent handoff mapping checks and customer initialization audit (2026-10-13)

Parent independently ran strategyResourceHandoff.test.ts:3 passed, including no fabricated
resource defaults, exact native mapping and incompatible EUR/therm/daily-unit refusal.
Compared all eight current ENTSOG production file hashes with the verified image evidence:
all match at this check; upcoming rolling-policy changes will require revalidation.
Existing delivery agent now audits customer initialization/provenance paths for accidental
development seeding, without touching or cleaning the existing database. Contract-save
retry/persistence and rolling-policy agents remain running; no duplicate workers started.

### Current image and bounded handoff reviewed; persisted-save gap next (2026-10-13)

Parent inspected current image verification evidence and independently inspected immutable
image03aba6f566ff07e59822669bd669da56f2f14cd3f9e51c46ab3586afc56ae8c1:
amd64, user eurogas. Worker recorded both isolated actual image verifiers exit0, eight
ENTSOG production hashes matching handoff and zero drift across479 captured inputs.
This supersedes the pre-integration image limitation for that captured source only.

Report15 and final-validation evidence now record38 actual handoff checks passing and
all six DB groups unchanged including UAT additions. Parent inspected draft ownership,
deliberate handoff and native-unit mapping code. Persisted strategy save is still unproven:
the previous browser mapping used an intercepted create reply and aborted version write.
Code review identifies a possible retry trap after createStrategy succeeds but createVersion
fails: selected strategy has no version and retry reports frozen-version error. Existing
contract agent owns reproducing/fixing retry and actual owned-UAT persisted save/reload,
with originals preserved and no backtest/execution. Existing ENTSOG agent owns bounded
rolling-window/replay policy continuation. No final supplier or Astra sign-off/push.

### Existing execution handles resumed (2026-10-13 17:27 +08)

After the reported reset hint, resumed only the existing delivery and contract Sol
handles; both now report running. No matching DeepSeek/supervisor process was found.
Same PostgreSQL container49881d31b917 remains healthy. Delivery owns the final-source
image rebuild and immutable-ID checks; contract agent owns safe selected-resource
binding and browser rechecks against existing UAT records. These are pending tasks,
not newly passed gates. No new installation, data cleanup, duplicate supervisor or push.

### Heartbeat checkpoint: confirmed binding failure and execution quota (2026-10-13 14:23 +08)

Read entrypoint/state and actual agent status. ENTSOG agent completed its handoff;
delivery and contract agents ended with usage-limit errors (reported retry hint 16:22),
not active work. No new workers or supervisors started. Parent inspected final contract
evidence:149 workflow checks, three generic resource journeys, all three strategy handoffs
still showing res-1 despite selected contract URLs. Final six-group preservation JSON
has no missing/changed original rows. Report15 now distinguishes this current failed
binding gate from the historical Docker interruption. Safe draft binding remains unfixed.

Post-ENTSOG artifact test log records16 passed. No rebuilt-image verification has been
delivered; previously verified image remains pre-integration and is not final acceptance.
Resume existing agent handles when available, inspect partial files before edits/builds,
and complete binding correction plus current-source image verification. No push, release,
old-data deletion, source enable or full acceptance claimed. Astra review remains open.

### ENTSOG follow-up independently checked (2026-10-13)

Agent reports9real PostgreSQL tests passed after recovery (2.84s),38focused dispatch/scheduler checks after the final error-shape and worker-exit fixes. Parent inspected the new failed-iteration counter/nonzero return and independently reran public-worker/dataops-scheduler tests: **21 PASS**. Delivery agent now owns rebuilding the same local acceptance tag from a fresh explicit-input context after final ENTSOG hash coordination, with immutable-ID verification and no database mounts.

Parent opened contract `HUB-POOL-09-binding-failure.png`: actual form still shows res-1/Resource1/100MWh-d/20GBP-MWh. This verifies the binding failure visually. Contract agent was instructed that a correction must not copy EUR costs into GBP fields or invent FX; currency/unit mismatches require explicit handling before a new unsaved draft is valid. Existing saved/frozen drafts must not be retargeted silently.

### PostgreSQL evidence recovered; routing clarified (2026-10-13)

Parent inspected new `entsog-transport-20261013/postgresql-verification.json`: configured target127.0.0.1:51356/nexus_verify, pytest exit0, public-table fingerprints unchanged, no new test schemas remaining. This supersedes the earlier unavailable-DB evidence for that invocation; await agent's final test-count and worker-exit correction handoff before accepting the combined slice. Parent also added the owner's Sol routing amendment to CODEX_ENTRYPOINT itself, so its historical DeepSeek prose no longer misdirects a future resume. No change to STOP/security/architecture gates.

### Integration review follow-up (2026-10-13)

Parent inspected ENTSOG archival/savepoint/semantic-field integration and scheduler propagation. Found a remaining worker observability defect: `run_public_ingestion_worker.run_worker` logs exhausted retries but returns0 for a bounded invocation when no configuration block exists. Sent the existing integration agent a focused correction/regression request; preserve continuous supervision while bounded failure must return nonzero. Do not count it closed until tests pass.

Contract agent reports post-recovery exact original-ID/hash comparison passed across all six baseline groups; the same HUB record resumed without repeat writes, and Pipeline terms created/edited/reloaded. LNG and final handoff assertions still in progress; no full business acceptance inferred.

### Shared Docker recovery and interrupted acceptance (2026-10-13)

Docker Desktop stopped during contract testing and ENTSOG transaction verification. Parent used the official `docker desktop restart --timeout 45` (exit0), then verified same container49881d31b917 healthy on51356 and `Start-LocalAcceptance.ps1 -CheckOnly` PASS: API23180/Web16436 reused, ready, container ID unchanged. No volume/data reset, fallback database or cleanup. Both existing agents resumed only interrupted work.

Contract report15 records45checks and two completed writes to its sole Hub CONTRACT_POOL surrogate `DNX-UAT-BIZ-20261013-20261013T032343560Z-HUB-POOL`; Pipeline/LNG writes were zero at interruption. Resume existing checkpoint, compare originals first, never duplicate saves. ENTSOG integrated mocked/unit suites199PASS; nine PG-only tests were skipped while DB unavailable and now must actually run. GIE hashes preserved. Fixed-window scheduling is implemented; rolling policy, reference snapshot semantics, rebuild and Astra review remain open.

### Actual local image verification passed (2026-10-13 11:22 +08)

Materialized-context Docker build completed despite agent quota interruption; parent verified no build process remained and the image existed. Local immutable image ID `sha256:9a0d90a205aefe07d01b497e041667e735646b65f12c9d388a4f5c601a6ca9b2`, amd64, default user eurogas. Parent executed both verifiers by this ID with `--rm --network none --read-only`, no mounts/credentials: customer artifact PASS; notice verifier confirmed30locked packages/34textfiles and runtime lock SHA256 `aa8d28434e737bef37fc31bea3e9b46d1d0174cd6a15c32d7731a1800c7a6058`. Evidence build log/context manifest plus `customer-artifact-20261013/parent-image-verification.json`. Local image ID is not a published registry release or legal clearance. Image captures pre-ENTSOG-integration source; rebuild after integration remains necessary. No database change.

ENTSOG integration and contract UI agents resumed their existing handles after terminal quota errors and reported reset time; no DeepSeek/new supervisor. Inspect partial work before repeating actions. Astra final review, customer DB provenance and complete business workflows remain open.

### Next coordinated business and ingestion gates (2026-10-13)

Sol GIE agent moves to actual Hub/Pipeline Tender/LNG contract workflow acceptance under existing UI capabilities and the contract/payment plan. Explicitly labelled UAT records may be created/edited; original contracts and cited history must be fingerprint-preserved. Missing business fields/retirement remain failures, not inferred equivalents. No execution/nomination/settlement, role grants or destructive delete. Contract UI/report ownership is separate from ENTSOG and release work.

ENTSOG integration proposes mandatory explicit from/to windows. Parent inspected both current worker and dataops scheduler: neither currently passes them. Agent must address pass-through/preflight and disclose any remaining rolling-window scheduling gap; a repeatedly failing worker must not be represented as working ingestion. No historical full-backfill claim. Docker delivery agent continues materialized-context image verification concurrently with source-hash evidence.

### Actual Docker artifact build started, context compatibility failure (2026-10-13)

Parent attempted `docker build --progress=plain -f deploy/runtime/Dockerfile.api -t eurogas-nexus-acceptance:20261013 .` after checking `.dnx*` context exclusions. BuildKit failed before reading the Dockerfile: `invalid file request Dockerfile.api`; the file is a Windows reparse point. No image was built and no DB/container changed. Log `customer-artifact-20261013/docker-build.log`. Sol delivery agent now owns a materialized explicit-input build context, image build and network-disabled/non-root verifiers, with captured source hashes because ENTSOG integration is concurrently changing the shared ingestor. No broad repository/secret/data copy or second database; no image push. This is an execution compatibility issue, not permission to retry policy-rejected data deletion.

### Independent review of Sol deliverables (2026-10-13)

GIE bounded actual UI slice delivered: parent opened `gie-ui-20261013/external-after-connection.png`, confirming readable separate AGSI/ALSI results, disabled credential form, Connected alongside Unverified certification and bounded-page disclosure. Worker recorded15postfix browser checks,112backend/11frontend checks and six GIE-table fingerprints unchanged. This closes only the recorded connectivity/read-only UI slice; certification, ingestion and broad supplier acceptance remain open.

Parent independently reran ENTSOG transport **88 tests PASS**. Same agent now owns coordinated ingestor integration, preserving GIE behavior and gates, exact page archives/receipt lineage, explicit partial results and no partial reference replacement; no live ingestion authorized.

Parent independently verified delivered401-member wheel policy and SHA256 `1bb66ca347a1df0f1a765cf199b2b1ee3db500d40f479637394b2cee241ce413`. Initial artifact test attempts under DSH Python failed because setuptools is absent there, not because wheel checks passed. Rerun using existing `C:/Users/qqshu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` (installed setuptools84/wheel0.48 matching lock), PYTHONPATH `.dnx-deps;src;packages/python-sdk/src;.`: **16 artifact tests PASS**, including actual wheel build/offline import. No new install. Docker image execution, customer DB provenance and Astra final integration remain open.

### Sol work resumed with concrete findings (2026-10-13 05:19 +08)

All three previous Sol handles were terminal usage-limit errors; parent resumed the same handles after the reported reset hint, with no DeepSeek/supervisor process found. New tool-backed progress: ENTSOG bounded official probes show `total=count=2` on distinct limit2 pages, so total cannot be treated as global row count; transport must disclose absent snapshot consistency. Delivery review found snapshot metadata imports SIMULATOR_VERSION from the generator; parent authorized constant extraction preserving the exact value before artifact exclusion, rather than shipping broken imports. GIE verified API24120/Web16436 ready; external GIE key path is absent from ignored runtime config, so record missing state then configure path-only/restart verified API through the single launcher for actual UI evidence. No source enable, ingestion, certification or push.

Parent completed pending frontend error-presentation/locale checks after the deployment-token taxonomy correction: **13 passed**, zero skipped. Browser acceptance remains distinct and pending.

### Deployment-token error classification corrected (2026-10-12)

The live unauthenticated probe exposed a real presentation defect: missing deployment token correctly refused401 but emitted top-level UNCLASSIFIED_ERROR/SYSTEM. Added the existing missing/invalid token codes to AUTH/after_user_action, with EN/ZH recovery guidance. API regression verifies missing401/invalid403, preserved detail code, correlation and no supplied-token echo; focused envelope/taxonomy suites **18 passed**. No authentication policy changed. Running API was not restarted during GIE UI work; post-restart live classification remains to verify.

ENTSOG Sol agent terminated with model-capacity error before delivering changes; it is not running. GIE Sol confirmed successful reads and active UI preparation after its retry. Preserve this distinction from earlier agent-status snapshots.

### Live unauthenticated source-boundary probe (2026-10-12)

Parent tested the running loopback API without deployment token, identity key or session: GET `/api/me`, `/api/sources`, `/api/credentials/providers` and POST `/api/credentials/GIE/connection-test` all returned **401**. Evidence `.dnx-out/unauth-source-boundaries-20261012.json`. This proves only unauthenticated refusal for these four requests; it does not prove authenticated role separation, absence of downstream side effects, secret-safe success payloads or browser workflow acceptance. No credential was supplied and no data/source setting was changed.

### Previously skipped browser-harness checks executed (2026-10-12)

The full frontend suite's three skips were dependency resolution, not unavailable browser installation: `liveBoardCaptureRunner.test.ts` could not resolve Playwright from the web package. Parent supplied its supported `EUROGAS_UAT_PLAYWRIGHT_PATH` pointing to the existing `scripts/ci/browser-acceptance/node_modules/playwright/index.js`, without installing anything. Focused host run: **24 passed, zero skipped**, including real Chromium local synthetic-fixture response comparison, mutation refusal and WebSocket closure. Evidence `.dnx-out/frontend-browser-harness-20261012.log`. Together with the prior full run this exercises all 921 collected tests, but does not claim one zero-skip full invocation or actual customer/persona UI acceptance. These three are development harness fixtures only.

### Host frontend suite and customer-artifact follow-up (2026-10-12)

After repairing the Windows reparse-point scanner, parent ran the full existing web test command with the installed Node runtime: **921 tests, 918 passed, 3 skipped, 0 failed**, exit0. Evidence `.dnx-out/frontend-host-20261012.log`; this is automated frontend evidence, not browser/persona completion. Future edits require relevant rechecks.

Direct inspection confirmed customer Compose still declares preview-seed/simulated-prices, Dockerfile copies every script, and Docker context exclusions omit local `.dnx-*` artifacts. Sol `/root/sol_delivery` owns a bounded release/build remediation and artifact-content tests, preserving explicit dev-only simulation and runtime dependencies. No deletion of local data, no Docker cleanup retry, no source enable or customer-release approval. Other Sol ownership remains GIE actual UI and isolated ENTSOG transport respectively.

### Existing acceptance runtime restored (2026-10-12)

Initial Docker Desktop Linux named-pipe read failed while Desktop reported running; subsequent bounded inspection found the existing database healthy without any restart/install. Root ran the tracked `Start-LocalAcceptance.ps1`: same container `49881d31b917`, PostgreSQL loopback51356 healthy, API8000 ready, Web3000 HTTP200, `container_id_unchanged=true`. No old data deletion or new database. CheckOnly had correctly refused the absent API beforehand. GIE Sol agent received one follow-up retry after its terminal capacity error, with the live runtime handoff; actual browser result remains unproven. ENTSOG Sol agent was confirmed running separately, with isolated module/test ownership.

### Frontend hook-order evidence repaired (2026-10-12)

Host reproduced the reported `shellHookOrder.test.ts` failure: AppShell count was zero, while the general scan passed. Actual Node Dirent inspection of `src/app/shell/AppShell.tsx` returned isFile=false/isSymbolicLink=true on this Windows reparse-point file. The scanner now resolves link metadata with statSync, walks directories explicitly and guards realpath cycles; both existing tests pass (2/2), preserving the hook/identity assertions. No application behavior changed. This repairs a false-negative coverage gap and the failing assertion, not full frontend acceptance.

Sol GIE agent `/root/sol_gie_workflow` terminated with model capacity error before delivering browser evidence. Do not describe it as actively testing. Separate Sol `/root/sol_entsog` was assigned the already planned ENTSOG transport gaps in isolated new module/tests, without shared ingestor edits or live ingestion; poll its actual status before continuation. No DeepSeek restart.

### Owner routing update and real GIE UI continuation (2026-10-12)

The human explicitly replaced DeepSeek implementation with GPT-6.1 Sol in this chat. This supersedes the older DeepSeek-primary routing for this task; do not launch further DeepSeek workers. Astra retains architecture/final integration review when available. Existing work and all acceptance/security gates remain in scope.

GPT-6.1 Sol agent `/root/sol_gie_workflow` now owns the bounded continuation of the existing GIE plan: inspect the delivered corrections, exercise the actual SourceCenter external-credential and per-product connectivity workflow, fix defects and preserve browser evidence. No live DB ingestion, source enable, certification change or push is authorized by this slice. Prior runtime census showed no headless worker/supervisor or API/Vite process; revalidate before starting the existing single local launcher. The primary checkpoint remains parent-owned. This is execution progress, not Astra integration sign-off or supplier acceptance.

### REAL-SOURCES-02 correction delivered; final integration review pending (2026-10-11)

Supersedes the active-worker statements below. DeepSeek correction worker exec25327/PID4008 is terminal with `workflow-review-final.txt` and `result-workflow-review.md` in `.dnx-out/real-sources-20261010/`; process census found no active headless worker or supervisor. Astra identified runtime operator-disable bypass, editable external credentials and zero-normalization false success; the worker reports these corrected. Parent host verification on 2026-10-11 reran six focused Python suites (transport, credential status, connection API, ingestion credential gate, upsert and revision-safe ingestion): **126 passed**, plus both focused frontend suites: **11 passed**. These are automated checks, not actual browser workflow acceptance.

Astra integration reviewer hit its usage limit (reported next availability Oct15 21:51); no quota bypass or alternate-model sign-off is claimed. Preserve the completed corrections for its review. Next: inspect corrected runtime authorization and normalization boundaries, run actual SourceCenter external-key/per-product connection workflow against the reviewed local runtime, then legitimate certification and ingestion gates. No live ingestion, source enable, certification, commit or push in this continuation. Existing shellHookOrder failure and full supplier acceptance remain open. Docker cleanup remains policy-blocked and must not be retried through another tool.

### REAL-SOURCES-02 safe GIE workflow active (2026-10-10)

Prior reviewer-fix worker44126/PID10872 is terminal exit0. Corrected GIE fetch transport accepted for its bounded fetch-only scope: reviewer host140tests PASS including4actual PostgreSQL isolated-schema persistence tests, config/env/diff gates PASS. Reviewer read-only live probe through corrected transport returned30records each AGSI/ALSI, explicit complete=false; evidence `.dnx-out/real-sources-20261010/reviewer-provider-probe.json`. No actual live ingestion/certification. Existing generic upsert's revised-value overwrite with old first-seen is confirmed, not accepted as temporal safety.

Sole active next DeepSeek worker exec58574/PID22396 (started11:08:30 +08) runs `.dnx-out/real-sources-20261010/workflow-brief.md`; stdout `workflow-final.txt`, stderr `workflow-diagnostic.log`. Scope: GIE-specific insert/unchanged-row preservation/revision refusal with atomicity, exact archive lineage, external credential-safe status and existing SourceCenter real per-product connection-test. No schema change, businessDB ingestion, certification/entitlement changes, source enable or service restart by worker. Follow-up actual UI and legitimate certification/ingestion gates remain reviewer work. Parent researches official attribution/reference and EEX transport. Docker cleanup remains blocked independently below.

### REAL-SOURCES-01 reviewer corrections active (2026-10-10)

Worker `71050` / PID `2412` is terminal. Its source census and initial GIE transport are delivered but not accepted: reviewer host 96 focused tests pass, while review found redirect/plain-HTTP credential leakage risk, untrusted error-body echo, record-budget and pagination validation gaps, and aggregate receipt backdating. Sole follow-up worker exec `44126` / PID `10872` (started 10:53:37 +08), DSH `session-b871c124-6143-4bbe-8b62-3120610db3e9`, runs `.dnx-out/real-sources-20261010/review-fix-brief.md`; outputs `review-fix-final.txt` and `review-fix-diagnostic.log`. It must prove credential boundaries before further live probes and test actual upsert first-seen/revision semantics. No live ingestion/certification or customer-ready claim. The prior active-worker paragraph below is historical and superseded by this follow-up.

The sole active DeepSeek implementation worker is exec session `71050`, Windows PID `2412` (started 2026-10-10 06:38:17 +08), DSH session `session-bd596bbb-0dec-4c97-ab46-f154ac16d860`. PID was verified live after launch. Brief: `.dnx-out/real-sources-20261010/brief.md`; final and diagnostic files are in the same directory. DSH buffers final output, so zero-byte final output alone is not failure. Verify process/session before starting another worker.

Bounded scope: complete source census, real AGSI/ALSI fetch transport integrated with existing public-source ingestion, external credential-file support, documented pagination/truncation handling, actual receipt timestamps, and focused tests. Preserve entitlement/certification gates; live validation is bounded read-only provider probing, not DB ingestion or production certification. GIE keys stay outside the repository and must never appear in output. Parent is independently reviewing official EEX Hub transport/terms; worker does not edit the commercial protocol gap document. Customer simulation exclusion and remaining source implementations stay explicit outstanding gates. Docker cleanup remains blocked below and must not be bypassed.

### Docker migration accepted; cleanup blocked by tool policy (2026-10-10)

Authoritative current state superseding earlier pending-cutover notes:all9 databases are restored and verified; final source/Docker gate passed2026-10-09T14:36:50Z and cutover93418 succeeded. Root Compose/tracked `scripts/ops/Start-LocalAcceptance.ps1` is the single local entry. Container49881d31b917 on127.0.0.1:51356 is healthy, API21664/Web21744 are ready and reused by repeated startup. Old Windows PG is stopped and not a fallback. DeepSeek3511/PID21508 is terminal; no active worker at this checkpoint.

Final actual UI31085 passed, with viewed contract Library2 rows, saved run history and dataset catalogue4 rows, plus authenticated exact2contracts/3versions/7runs/4snapshots and unchanged IDs after reload. Automatic optimization POSTs are explicitly permitted/recorded after equivalence; this is not a read-only UI run. All92 original main-table records verified after UI:89 complete table hashes unchanged, original422audit/214job/69session rows individually preserved by in-memory comparison to the dump, only14audit/10automatic jobs/4sessions added. Other8 databases have0 unexpected differences. Host19 focused tests/config-contract/Compose/Markdown/diff checks pass. Current-data actual repository selection/numerical parity passes at9 limits; locale differences and future tie risks remain bounded and disclosed. Report11 contains full final evidence.

The explicitly authorized cleanup is **BLOCKED_TOOL_POLICY**, not awaiting user approval. All18 resolved repository-contained targets (423754945bytes) remain:old data, cold copy,14dumps and2obsolete backups. Automatic review rejected both the native PowerShell batch and a narrowed exact literal old-data path, before execution, stating only `blocked by policy`. Do not bypass that refusal using another tool/agent. Current volume/live secrets and non-data evidence remain excluded; container temporary dump count0. Evidence: `.dnx-out/docker-postgres-cluster-20261008/evidence/cleanup-{manifest,result}.json`. Continue independent all-source/default/fallback and broader product acceptance work while this execution-layer cleanup blocker is unresolved. No push/merge or production certification.

### Resume observation 2026-10-10T04:48+08:00

This supersedes the stale pre-cutover status below. Docker PostgreSQL is healthy
on loopback51356 after the reviewed cutover; the embedded source was stopped.
DeepSeek3511 completed the root Compose/tracked `Start-LocalAcceptance.ps1`
implementation. Host cutover93418 succeeded, and the reviewer reported a second
startup reusing the same container/processes. Actual browser evidence at
`.dnx-out/docker-postgres-cluster-20261008/evidence/` records the first attempt
blocking automatic optimization POSTs and the second attempt passing after
explicitly permitting those existing computations. The latter correctly records
`read_only_after_login=false`: login/session and automatic job side effects must
not be described as a purely read-only run. Original business-record hash
verification after that run, final screenshot review, authorized deletion of old
embedded data/all project migration backups, and final migration report remain
to be confirmed. Do not delete the active Docker volume or live credentials.
Astra resumed after its quota reset; do not start a second worker/supervisor.

### Docker cluster restore review in progress (2026-10-09)

**Host execution update 2026-10-09T10:46Z:** prior DeepSeek34961/PID10844 is terminal. Host38464 actually restored all7 additional project databases, exit0; host90941 actually collected container inventories and compared all9 databases: every stable structural/data line matched (2070 per project DB;14 for `postgres`). Its sole false gate was rejecting the approved read-only Compose file-secret bind. Reviewer precisely allowlisted the resolved secret source, destination `/run/secrets/pg_superuser_password` and `RW=false`, retaining all other bind rejection, and added real container ID/structured mount provenance. Source `default_text_search_config=pg_catalog.simple` is now explicitly preserved via the Docker postgres command. Host61419 recreated only the same review container/volume on51357, recollected actual inventories, and canonical gate **PASS match=true/failure_count0 at10:45:55Z**. Remaining three explicit platform differences: Windows/Alpine collation+ctype, lc_messages, and PG16.2→16.15. No API/Web restart, cutover or deletion yet. Sole new DeepSeek3511/PID21508 started10:44:44Z for root Compose/tracked local startup/docs plus actual locale semantic probes, from `single-start-brief.md`; it must not execute cutover or modify the reviewed cluster scripts. Locale semantic review and actual API/UI cutover checks remain before cleanup.

Reviewer successfully restored the final `nexus_browser` dump into the existing Docker Desktop official PostgreSQL16-alpine container `eurogas-nexus-postgres`, named volume `eurogas-nexus-postgres-data`, isolated loopback port51357. The final dump is607443 bytes, SHA256 `b7bb35880206a06a12fdef35e32845da94deb0edeb130172703ffde3589124b9`; the older ce2b hash below is superseded. All92 table counts and whole-row fingerprints match, as do the preserved version/run/snapshot hashes. Initial full inventory gate is **not yet passed**: the only discrepancy is the constraint fingerprint, whose worker SQL hashes `conrelid::text` (an internal OID). Stable qualified-name/definition comparison must replace that invalid cross-restore check; it must not simply be ignored.

The existing source cluster was found stopped and recovered with its existing PG16.2 binaries for read-only final verification; source143-line inventory still exactly equals the snapshot. A cluster census discovered7 additional project databases (`nexus_diag`, `nexus_ops_drill_fixed`, `nexus_ops_drill_restore`, `nexus_ops_migdrill`, `nexus_ops_restore`, `nexus_test`, `nexus_verify`) besides `nexus_browser` and `postgres`. These must also migrate and verify before the old cluster is deleted; inspect `postgres` for user objects too. Sole DeepSeek worker session34961/PID10844, harness session `session-ef2dfed0-c8ca-4e35-af83-17562a79a123`, is preparing complete cluster backup/restore/structural verification and hardened cutover/UI checks from `.dnx-out/docker-postgres-20261008/cluster-review-brief.md`. Worker25938/PID17652 is no longer active. API/Web remain stopped; no cutover or cleanup has occurred.

Normal startup still needs consolidation: root `docker-compose.yml` currently describes a separate development database/container on5432 and old docs recommend that command. After the verified migration, align the local root entry and launcher with the retained Docker database; preserve the separate production release deployment contract. Do not claim Docker startup is unified merely because an ignored UAT launcher was changed.

### User priority: Docker PostgreSQL and all-source fallback scope (2026-10-08)
Live migration progress: DeepSeek25938 generated a snapshot-consistent607443-byte custom dump (SHA256 ce2b0e3da6bc730965e6ae42d0edad832aa96d4424072b442aa2ae2dd35569fb),92-table inventory A/B equal and440-line pg_restore catalog; catalog success is not restore success. Reviewer extra inventory confirms only public user schema,198 indexes,plpgsql1.0,no sequences/large objects. DS sandbox cannot write Docker named pipe, but reviewer host session46059 executed the reviewed same script successfully: official postgres:16-alpine pulled first attempt42s, digest sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea. This supersedes older TLS/network blocker and sandbox-only diagnostic. Container restore/cutover still pending; embedded source remains authoritative. Existing nexus superuser privilege is a separate least-privilege delivery gate, not certified safe by preservation.

Additional user scope for following data-source work: European TSO connectors where they provide material live/unique flow, capacity, maintenance, outage or inventory data beyond existing ENTSOG coverage; read-only data only, no nomination/execution. User supplied GIE credential is stored outside repository at C:/Users/qqshu/.eurogas-nexus/secrets/gie-api-key.txt with current-user ACL. Read value only into memory, x-key header, no values in briefs/logs/artifacts. Verify IIP, AGSI and ALSI entitlements individually; do not infer a key works across products. Reuse existing scripts/ops/ingest_public_sources.py and its scheduler path instead of duplicating ECB/ENTSOG/GIE pipelines.
User later explicitly instructs: after successful full restore verification, API/UI cutover and confirmed old PostgreSQL shutdown, delete the old project embedded data and project migration backups/cold copies/dumps; retain no rollback data copy. This supersedes the earlier post-success cold-backup retention plan only. Before cleanup, inventory and resolve exact absolute paths under this repository, verify each intended old-data/backup target; exclude the new Docker volume, unrelated files and non-data migration evidence. Until success, preserve the source DB and backups. No repeat confirmation is required. Current prepare worker25938/PID17652 is instructed not to delete or cut over; the reviewed next phase will perform the authorized cleanup only after its success gates. Also review all non-system schemas, extensions, large objects, sequences, roles/ACLs rather than claim all-data verification solely from public-table fingerprints.

Latest user request prioritizes moving the existing Windows embedded database into the existing Docker Desktop, with a single normal runtime startup path. Docker contexts default/desktop-linux are connections to the same engine, not duplicate installations. Preserve embedded data/binaries and fresh logical backups until official PG16 container restore and all-table evidence are reviewed; no destructive reset. Current bounded worker brief `.dnx-out/docker-postgres-20261008/brief.md` prepares backup, bounded official-image pull, isolated loopback restore and reversible cutover plan. It must NOT cut over or restart the API before review. Engine2 report10 is complete for its bounded scope; business writes are paused during migration preparation.

The user also extends the data-source policy to every registered and active source: healthy authorized high-frequency API first, genuine compatible lawful default/fallback where one exists, and explicit unavailability where none exists. Never synthetic substitution or cross-product/unit/measurement substitution. Preserve origin, delays, receipt/availability and point-in-time lineage. EEX Market Data Hub is requested as a default/API fallback; official FAQ intraday delay is15 minutes (60-second polling does not mean minute market latency), other daily update timings/product-code distinctions and redistribution rights must be verified. The full registry census and first EEX adapter/fallback task follow this higher-priority DB request, using COMMERCIAL_CONNECTOR_PROTOCOL_GAPS.md without claiming public access establishes customer redistribution rights.

### Engine replacement requirement (user instruction, 2026-10-08)

After engine/2 passes the required acceptance gates, replace engine/1 as the sole production backtest execution path. Do not leave two permanent selectable production backtest engines. Preserve historical run records, original engine identifiers and provenance; any legacy verification code must be isolated from new production run entrypoints and justified by an explicit historical-replay requirement. Before replacement, inventory API, agent, experiment, scheduled and client entrypoints, verify engine/2 parity within the approved product scope, expected numerical deltas, no stale-product reuse, rollback/release evidence and old-record immutability. Do not switch merely because a focused test subset passes. This direction does not authorize rewriting old records or silently changing separately defined scenario/EVALUATION semantics. The customer delivery ban on simulated fixtures remains mandatory.


### Customer delivery requirement and engine2 integration (latest 2026-10-08)

User explicitly added: commercial data adapters must support actual provider interface modes, ready for valid credentials; simulation is ONLY for development/testing and is NOT customer deliverable. Mandatory remaining gate: official provider protocol mappings and auth/entitlements/pagination/incremental/rate-limit/error/revision/unit/timezone/provenance verification, plus fixture/mock exclusion from customer artifacts, Compose defaults, profiles, seeds and data exports. Do not guess private APIs or claim credential-free live certification. Parent coordinates provider gap discovery; no scope reduction.

Both engine2 workers44267/37937 are terminal and reviewed. Final host104 Python +36 frontend tests, tsc and focused diff pass (initial130 overlaps, not an additive count). Fill policy now applies to primary/fallback, carry age uses exact timedelta, ambiguous multi-component/name mappings fail closed, release metadata identifies public2/legacy1. Independent HEAD/current legacy control remains identical except new diagnostics (3 events/net2850). **Actual UI19 assertions PASS:** v2 unchanged produced engine2 BLOCKED run87cca8dc3e0848cebec1f607; one explicitly developer-only SIMULATED day-ahead cross-source v3 `strategy-version-3453edffca7a470281e9` saved/reloaded/frozen and produced COMPLETED_WITH_WARNINGS run6e1740d44c8c4ec8a5b8688e. Two existing simulated MID quotes matched the canonical target and availability; no market data inserted. Screenshots viewed. DB full-row hashes of old2 versions/5 runs unchanged; counts3 versions/7 runs, two new referenced snapshots and manifest hashes verified. Report10 gives exact evidence/limits. The temporary total refusal is ended for supported declarations, NOT full engine/customer acceptance.

### Target-aware engine/2 first slice (2026-10-08, implementation history)

Worker44267 executed `.dnx-out/target-engine2-20261008/brief.md`, then reviewer corrections were delegated to37937; both ended. Report10 is now the authoritative bounded result. Supported first targets are fixed intervals and explicit canonical GAS_DAY current/next offsets; rolling month/quarter, full hourly workflows, older-forward retrieval and reference-source mapping remain open. Original v2 `GBP/MWh` was retained and blocked honestly, not corrected in place. Next work: complete applicable product/engine gates and production-entrypoint replacement audit, customer simulation exclusion and real-provider adapters using `docs/release/acceptance/COMMERCIAL_CONNECTOR_PROTOCOL_GAPS.md`, alongside the original contract retirement, personas, Hub/Pipeline/LNG, dataset/OOS and release scope. No active worker or push at this checkpoint. Root/user architecture approval remains in force.

### Target declaration phase 1 (2026-10-08, bounded verification complete)

DeepSeek worker65374 ended exit0. Typed fixed-interval declarations and transitional guard are reviewed, with small reviewer fixes for serializer projections, duplicate name case, exact server-side fork copy and unsafe form projections. Host82 Python focused tests + 2 additional regressions (schema rerun30), frontend26, tsc and focused Ruff/diff pass. Actual UI12 final assertions prove legacy422, one fork v2 (`strategy-version-8ac5841afb524165b38f`), declaration save/reload/freeze and declared422 unavailable; two selector-related attempts are disclosed in report09, not product failures. Read-only hashes show original frozen version and5 runs unchanged; versions1→2, runs5. Screenshots reviewed. Engine still1; all new historical runs temporarily refused. Ten old service-success tests conflict with this development state, so this is NOT stable-release acceptance or a push point. Immediate next work is approved product-aware selector/engine2/provenance restoring valid declared runs, then rolling/day-ahead/hour/month support and the complete remaining vendor scope. No repeat architecture approval required.

### CR-04 approved direction and independent API-key UAT (2026-10-08)

User explicitly approved `docs/product/BACKTEST_TEMPORAL_AMENDMENT_PROPOSAL.md` with “同意架构修改提案”, first recorded `2026-10-07T23:49:57Z`, confirmed by root. This satisfies the material CR-04 amendment STOP for this direction only: per-leg backend target ownership, legacy frozen new-run refusal and fork-to-declare, product-aware selection, engine/2 provenance, old record preservation and explicit bounded reuse. No repeat approval is needed; unrelated security, numerical-surprise and Golden tolerance STOPs remain. Future-window guard is delivered. No engine/2 claim until actual selection and provenance are implemented and reviewed.

**API-key lifecycle completed:** report08 now records both actual UI attempts. First attempt used an incomplete header combination, correctly failed 401 and was UI-revoked. Corrected second attempt passed 30 assertions using deployment plus identity headers; authentication resolved the intended principal, UI revoke persisted, and the same correct headers subsequently returned **403 identity_key_revoked with no principal**. Read-only DB confirms both owned keys revoked. Roles/principal scopes unchanged, no active test key or saved bearer. Inspected safe issued/revoked screenshots; targeted artifact scan zero full-bearer matches. Owner-column payload gap and key-scope attenuation/negative persona verification remain open; this is lifecycle acceptance only. Evidence `.dnx-out/uat-access-20261008/`, including separate first-attempt artifacts. No worker active at this checkpoint.

**Local recovery:** reused the existing embedded PostgreSQL and launcher after processes stopped; no initialization or installation. Corrected launcher Windows pg_ctl waiting to wait for the control process only, avoiding `Start-Process -Wait` waiting indefinitely on the PostgreSQL descendant. Recovered existing data, API ready/Web200 verified. This is a local acceptance stack, not a Docker database or production deployment. No commit/push. Contract retirement and the complete remaining vendor-acceptance scope remain active.

### Historical backtest boundary slice (2026-10-08, verified)

Report07 records accepted CR-04 authority and the unresolved delivery-product mapping. A proposed universal delivery-window-contains-decision filter was withdrawn before product changes because it would incorrectly reject legitimate day-ahead/forward quotes. The first worker was stopped; one replacement worker implements only historical BACKTEST end <= application request clock, structured UI refusal and focused tests. No numerical price-selection changes authorized by this slice. Future-window rejection does not close stale evidence reuse inside historical periods; that remains the next architecture decision. No full acceptance, old-run rewrite, install or push.

**Completed host recheck 04:51 local:** replacement worker ended. Reviewed API source loaded by restarting only recognized local uvicorn through existing launcher (API20524, Web5052, PG5400). Actual UI future POST422 with clear alert and unchanged four run IDs; one historical control POST200 created `strategy-run-1330aed95b0d4b7483d878e8`, persisted/reopened after reload. READ ONLY DB hashes show all old run rows unchanged, run/snapshot counts each4→5. Host48 Python+10 frontend tests and tsc pass; screenshots viewed. API/agent callers cannot pass client-selected request clock. Report07 gives concrete per-leg target-delivery proposal; ambiguous missing target declarations/tenor rolls require reviewed CR-04 design amendment before numerical implementation. Historical stale reuse and misleading effective-coverage interpretation remain open, alongside all original retirement/Hub-LNG/research/API/permissions/delivery scope.

### Research workflow host execution (2026-10-07, current)

**Final slice update 2026-10-08:** Both actual UI workflows completed; business verdict remains PARTIAL/blocked. Dataset qualification remediation is implemented/reviewed and same-snapshot read-only screenshots show Training unavailable alongside materialized COMPLETE. Host 24 focused tests + tsc pass. No server-side training gate is claimed because there is no research-snapshot training consumer. Strategy second run over the future year reports 100% coverage and constant GBP872.1812/event; independent READ ONLY DB trace proves 365 events share one price-reference set, with matched observations ending 2026-10-06 before the future window. Coverage is completed/all events, not effective fresh market coverage. No strategy numerical change made; next architecture slice must resolve temporal eligibility vs explicit scenario projection. The worker's initial SKIP-policy explanation was rejected/corrected. Two sequential DeepSeek workers have exited. Existing launcher restored Vite after atomic-edit watcher EBUSY; API ready and Web200. Details/files/evidence/limits in report06. No commit/push. Remaining retirement/Hub-LNG/API/permission/full-delivery scope persists.

See `docs/release/acceptance/06_RESEARCH_FLOW_RECHECK.md`. Actual UI dataset validation/build/rebuild/reload succeeded with one new named spec and one immutable snapshot; repeated build is idempotent and old snapshots unchanged. Training fitness fails: COMPLETE materialization, build_blocked=true, 0% coverage, 100% missing, 365 leakage issues. Simulated indicator is present. Split UI and actual OOS separation remain unverified. Strategy first UI run persisted (16.2% coverage, warnings); two script defects were corrected without duplicating that run, and the second-window check completed as described above. Evidence lives in `.dnx-out/uat-research-20261007/`. The materialization/training-readiness qualification was subsequently delivered; the remaining priority is strategy temporal eligibility, as described above. This is partial workflow evidence, not production acceptance; fixture privileges are ADMIN+ANALYST only.

### Authenticated contract create/update recheck (2026-10-07)

DeepSeek's bounded script was reviewed and actually executed on the host at
10:33 UTC against the recovered local runtime. Fresh Chromium login, UI create,
authenticated GET, full reload, UI edit/save, second GET/reload and pool rendering
passed 35 assertions. Actual contract POSTs were two HTTP 200 writes: created
revision 1 and economics_updated revision 2. Read-only PostgreSQL independently
confirmed quantity 1234, edited cost 31.4 and both captured revisions. The sole
pre-existing contract remained unchanged by nonsecret field fingerprint.
The clearly named `DNX-UAT-20261007-20261007T103302Z` record remains in the pool.

All six fresh PNGs were inspected. Evidence and exact limits are recorded in
`docs/release/acceptance/05_CONTRACT_FLOW_RECHECK.md`; local machine evidence is
`.dnx-out/uat-contract-20261007/`. Verdict remains PARTIAL: no UI/API retirement
or removal exists, and screenshots exposed materially misaligned library
headers/values (P2, subsequently repaired below). Existing integration plan section 2.3 prohibits hard delete;
follow-up lifecycle work must retain audit, concurrency and historical references.
The worker's alleged served-i18n drift was disproved by explicit overrides in
`clients/web/src/i18n/index.ts`. No new installation, reseed, migration, hard
delete or commit/push occurred.

DeepSeek corrected the header/row layout in ContractWorkbench.tsx and app.css.
The integration reviewer caught a remaining Actions placement error in an actual
browser capture and made the small desktop grid-span correction. Final host
read-only captures at 1440 and 390 were both inspected; desktop four data columns
and Actions align within 1px, with no document horizontal overflow at either
width. Independent 60 frontend tests, TypeScript noEmit and focused diff checks
passed. Full-tree diff checking still flags a pre-existing EOF blank line in
dataops_observability.py. A Vite watch EBUSY on a worker temporary edit directory
required restarting the existing server, not a new installation. The same test
record was reused without additional business writes.

The interim 00_REEVALUATION_VERDICT now distinguishes historical rendering
coverage from full workflow acceptance, retains engineering gaps, and no longer
infers absence of a contracting entity/agreement from a personal GitHub account.
Current next bounded task: DeepSeek prepares a real strategy run/dataset build
workflow script; host executes, checks persisted artifacts and inspects screenshots.
Retirement, other domain workflows and release acceptance remain active work;
a scope/page sweep cannot close these gates. No headless worker remains running.

### Local database recovery and next acceptance boundary (2026-10-07)

HEAD remains `b9977bc35cad2f89f9a9363fd001a6cc825f533d`. The large
pre-existing uncommitted remediation set is preserved and is not yet accepted
as a whole. No commit or push was made in this bounded environment task.

Docker Desktop is reachable, but two bounded official PostgreSQL image pulls
failed at the Docker CDN with TLS handshake timeouts. No Docker database was
created. Reused the existing Windows embedded PostgreSQL 16.2 binaries and
`.dnx-pgdata`; copied the stopped data directory to the ignored
`.dnx-out/pg-cold-backup-20261007` before recovery (7182 files, 207607354 bytes).
PostgreSQL completed automatic WAL recovery and accepts connections only on
127.0.0.1:51356. Existing `nexus_browser` was already at
`0039_identity_api_key_hash_width`; key_hash width is 80. Read-only counts show
one upstream contract and zero contract revisions. No migration, reset, seed,
business mutation or new installation was performed.

A custom-format logical backup is also retained at
`.dnx-out/recovery-20261007/nexus-browser-recovered.dump` (480446 bytes;
SHA256 ff401b044fbb2af3bb1b52fdf4558cbda54c83b29474091bdd9c5b63b4f28649).
Its 440-line pg_restore catalogue is readable; no restore drill is claimed.
Both backups are local recovery evidence, never source/distribution artifacts.

The single reviewed local startup entry is
`.dnx-out/recovery-20261007/start-reviewed.ps1`: reuse existing data and installed
PG/Python/Node, start only absent listeners, require database/API readiness,
and expose API 127.0.0.1:8000 plus Web 127.0.0.1:3000. The API reuses the prior
ignored UAT environment without changing credentials or grants. Independent
checks returned /api/health HTTP 200 with authentication enforced and
/api/health/ready HTTP 200 with runtime_db and required_tables both ok;
Web returned HTTP 200. This is a local acceptance environment, not production
or Docker deployment acceptance and not an authenticated workflow verdict.

DeepSeek Harness headless execution was verified using the installed dsh.cmd
and deepseek-flash. Its bounded worker created local launcher attempts, but
its sandbox child-process/lifetime behavior was unsuitable for persistent
servers. The worker was stopped; the proposed Vite process shim was rejected
and removed. Servers now run from the permitted host execution environment.
No second supervisor was created. For subsequent bounded DeepSeek tasks, keep
implementation in the worker and persistent server control in the host.

Next: inspect the existing remediation diff and run current authenticated
Playwright user journeys against this recovered environment, including
contracts, strategy runs, API credential management and datasets. Preserve
all original Architecture V2 hard STOP conditions. Old acceptance reports
remain historical evidence; no full UX, commercial or release approval is
inferred from this recovery. Docker image networking, existing licensing
findings and all unverified user journeys remain open.

### Explicit optimiser payment timing (2026-10-06)

Previous turn fixed the financing rate. CI 37406836127 passed application,
browser, PostgreSQL, web and Python evidence jobs; dependency audit still failed.
DeepSeek removed optimiser 20-day upstream and 1-day sale-lag defaults. Upstream
lag is now required; option lag must be explicitly declared as integer or null.
Strict nonnegative integer validation preserves zero and refuses coercion.
Unknown effective sale timing excludes the pair with missing-input evidence;
an explicit resource override still works. Application composition returns null
instead of inventing one day, and ignores invalid lag candidates.

Parent independently ran 100 focused domain/composition/API tests, all passed.
Parent aligned the web DTO to permit the nullable response. No visual behavior
was changed. This remains lag-based research valuation, not a resolved contract
cash schedule or NPV. Stored-contract defaults, cross-contract minimum-lag
aggregation, unknown cost inputs and populated persona acceptance still need
review; no commercial approval is claimed.

### Explicit optimiser financing rate (2026-10-06)

Previous turn identified an undeclared 6% financing default. DeepSeek removed
that default at the resource-pool scenario boundary and added strict finite
numeric validation. Omitted/null/boolean/string/nonfinite inputs are refused;
explicit zero remains valid. API error serialization now renders nonfinite
echoed values safely so rejection returns 422 rather than a serialization error.
SDK/API docs and compatibility notes describe the tightening; known test
scenarios supply their rates explicitly. No financing assumption was inserted
in a production caller and no lag/cost semantics were changed.

Parent independently ran the resource-pool unit, adjacent API and persisted-run
API tests: 50 passed. Focused Ruff passed. This fixes an input-integrity defect,
not the missing dated cash schedule/NPV integration. Next inspect implicit
payment lags and unknown-to-zero resource costs before composing more financial
results. Full business/persona acceptance and unresolved licensing gates remain
open; commercial readiness is not established.

### Trader cash-workflow audit and next defect (2026-10-06)

Previous turn made progress on delivered-notice acceptance. CI 37404138721
passed validate, web, browser, PostgreSQL and Python notice evidence; dependency
audit remains failed. Commercial readiness is not established.

DeepSeek traced current tender/contract cash paths at 8606581; detailed ignored
report: .automation/runtime/tender-cash-current-audit.md. Parent independently
confirmed a material semantic mismatch: PortfolioOptimizationInput defaults
annual_financing_rate_pct to 6.0, and the early-cash formula uses it to credit
margin. The web request builder instead refuses an unknown financing rate.
Thus direct API callers can obtain a result based on an undeclared assumption.
Next bounded implementation: require an explicit finite financing rate at the
optimiser boundary, preserve explicit zero, reconcile internal callers/tests,
and prove omission/null/nonfinite inputs cannot create a financing credit.
Also review implicit payment-lag assumptions before extending composition.

The broader audit confirms declared payment terms remain read-only declarations:
no persisted-contract-to-cash-engine composition or frontend cash engine caller.
Unknown-to-zero resource cost composition and the scalar cash-credit label
need separate correction. Do not adopt the worker's suggested new endpoint
without resolving these semantics and the existing integration-plan decisions.
Its suggested SQLite fixture is not authorised; retain PostgreSQL-only runtime
and use existing domain fixtures or PostgreSQL for new integration coverage.
Worker reports 247 relevant tests passed; parent has reviewed code evidence,
not independently rerun that suite. No complete trader journey is claimed.

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


## 2026-10-22 — Linux role/privacy and regional contract checkpoint

Current working tree is based on `c4ff4a9`; earlier environment-snapshot evidence
must not be treated as validation of this tree. Owner-private strategy sharing,
active group membership, child/capability/projection ACLs, identity-key attenuation,
LLM egress enforcement, Web/SDK support and the offline EU/CN/CA/SG exchange contract
are implemented. No new infrastructure or automatic cross-region transfer is enabled.

Current evidence and remaining gates are recorded in
[Linux role/privacy acceptance](../release/acceptance/16_LINUX_ROLE_PRIVACY_ACCEPTANCE.md).
PostgreSQL HTTP sharing: 25 checks; Chromium strategy: 7; Chromium ADMIN: 8;
backend regression: 506 passed; web: 935 passed, 3 skipped. Native installer,
production/provider/SSO/release evidence and broader UI refinement remain open.
No push, merge or customer deployment was performed. Routine integration work used
GPT-6.1 Sol as instructed; final results still require integration review.

Owner follow-up: Canada (`CA`) replaces the provisional North America region.
Functional acceptance takes priority; regional exchange implementation is deferred.
Before enabling any exchange, validate applicable privacy, residency, transfer and
provider-licensing requirements and select proven infrastructure/control mechanisms.
The offline envelope is provisional and supplies no legal-compliance assurance.

Functional follow-up: migration 0041 introduces a separate stable job-owner FK;
legacy name-only jobs remain quarantined. Review-pack ACL now resolves the actual
pack-to-run relationship. Full security/contract regression: 952 passed; real
PostgreSQL role workflows77, trader contracts15, sharing25, job isolation7;
installed API6 and installed SDK6 checks passed. All-repository Ruff passes.
The database validates95 required tables at0041 with no warnings. Backend wheel
build succeeds; native installer and customer release gates remain unverified.
Reusable install_script/start_skill were saved as a draft; publication/restoration
has not been verified. Canada CA is the deferred regional scope.

## 2026-10-22 — backend runtime gate closure

See [backend runtime acceptance](../release/acceptance/17_BACKEND_RUNTIME_ACCEPTANCE.md).
Fixed Compose ready-status mismatch, migration-revision readiness, named-identity
release smoke and restore-target readiness. Local fresh restore passed at0041.
Actual pinned Alpine amd64 image8cacf6d651fb… passed HIGH/CRITICAL gate after
certifi2026.10.19 remediation and removing unnecessary base setuptools/wheel.
Python/Web runtime audits found zero known vulnerabilities. Final image smoke8
checks and non-root/CA-absence checks passed. API/SDK552, security/contract952,
release/readiness450passed35skipped; subsequent affected tests recorded in report.
Local60-request/concurrency4 baseline all200, p95<=155.56ms for measured reads;
no production SLO claim. No publish/push/signing occurred. External customer
SSO/provider/production acceptance and native/UI work remain outstanding.

## 2026-10-23 — owner-authorized simulated integration acceptance

See [simulated integration acceptance](../release/acceptance/18_SIMULATED_INTEGRATION_ACCEPTANCE.md).
Real Linux release-container HTTP workflows passed again: roles77, sharing25,
trader15. Refreshed synthetic browser sessions and restarted local Vite after
fixture/service failures; strategy7 and ADMIN8 browser checks then passed.
New loopback OIDC14 and provider9 cases exercise actual HTTP transport, signed
tokens, application PKCE/session/replay, pagination/retry/timeouts and refusals.
Combined OIDC35, provider regression236 and identity/deployment selection133
passed17skipped (overlapping selections). No production controls changed.
Synthetic acceptance is complete for this bounded scope; customer issuer/provider,
native signing, production recovery and broader UI remain distinct work. Regional
transport stays disabled/deferred. No publication or push occurred.

## 2026-10-23 — UI and native workstation work in progress

Responsive strategy and ADMIN actions fixed; real Chromium sharing7 and admin8
passed. Current/other screenshot matrices cover12+27 viewport cases with no
page-width overflow; local table/navigation scrolling is intentional. Root rejected
initial loading screenshots and reran other captures waiting for runtime+DOM.
MapLibre6 worker fixed using Vite worker URL; development and production worker
verified. ADMIN-only commercial reads now omitted without hiding genuine errors.
Settings compatibility label now uses authoritative messageKey.

Desktop efficiency: native Workspace/Edit/Window menus, windowed decorated startup,
F11 fullscreen, Ctrl+Shift1–6 workspace switching, Ctrl+K palette, focus trap/restore
and IME guards implemented. Keyboard browser8 passed; Web939passed3skipped before
last settings-label-only fix; production Web build passes. Native Rust1.94 plus
GTK/WebKit installed only in disposable Debian13 amd64 container. Release DEB
build passed; installation and same-version reinstall passed. Actual package name
is eurogas-nexus (uninstall docs corrected). Native graphical launch/offline login
and F11/menu observed in Xvfb/Openbox with test-only software rendering. Latest
native changes include nonblocking async login,300s timeout, valid HTTP CRLF,
HTTP(S)-only browser URLs and shell-free Windows browser launch; Rust4tests passed.
Evidence under ignored .local-runtime/{ux-audit,native-acceptance}. Final package
reinstall/remove and documentation report remain to finish; Ubuntu24/ARM64 and
Windows/macOS native validation not claimed. No publication/signing/push.

Latest owner steering: Windows/Linux Ctrl labels first (remove universal Cmd glyph
from help); use test accounts for native login; professionally redesign strategy
price selection and inter-module data use. Investigation found historical engine
supports exactly one OCM_VS_DAY_AHEAD component, so arbitrary index/single-price or
basket UI must not claim unsupported economics. Current free-text price names need
authorised catalogue selection, explicit spread direction, source/hub/tenor/unit/
delivery compatibility and proper handoffs. This strategy redesign is pending;
no catalogue/source-binding implementation yet. Existing draft retention and
source-entitlement/temporal restrictions must be preserved. Remaining Sol agents
hit usage limits; root continues integration/implementation fallback.

## 2026-10-23 — strategy catalogue bounded implementation

See acceptance/19_STRATEGY_PRICE_CATALOGUE_ACCEPTANCE.md. Replaced arbitrary price
name inputs with authorized loaded market choices; added hub selection and leg/hub
matching, preserved unavailable stored names, wrapped checkbox descriptions.
Shared canonical price-name and fallback tenor mapping across market discovery and
backtest repository; normalized API adds price_name. No source-binding claim,
new permission, numerical engine change or new supported strategy type.
Backend43pass, affected39pass after final mapping refactor; catalogue3pass;
Chromium analyst catalogue toggle/restore and1440/768/390 no page overflow; Ctrl
keyboard8pass. Full Web regression/build logs under .local-runtime/ux-audit.
Pending native authenticated acceptance/rebuild, source binding, expanded economic
semantics and cross-module scenario acceptance remain explicit. No delivery claim.

## 2026-10-23 — final local candidate and requested GitHub progress push

Native development-account login and authoritative /me passed in packaged Debian13
WebKit; Ctrl switching/palette and F11 passed. Final DEB rebuilt, installed and
reinstalled; see acceptance20. Cross-module actual PG/API24 and Chromium contract
handoff/save/reload/run-detail passed, with synthetic APPROXIMATE warnings retained;
see acceptance21. New strategies no longer invent NBP/SAP/ICE_OCM selections.
Final Web942pass3skip/build and affected backend/contract53pass; explicit price
selection38pass. Final wheel customer exclusion passed, SHA256
6f13119366c8def4e70c83c134073146db20d3ecbdb125ad7f7f314866844fea.
Final local API image e59d03ec9e6b047e8b9728f34dd4427cf73e6753100a6dc30780d179bab62d9f
built and HIGH/CRITICAL scan passed; Cargo lock scan also zero HIGH/CRITICAL.
These are local candidate results, not same-commit remote CI/signing/provider/real
customer acceptance. No live cross-region transport. User now expressly requested
GitHub progress push; commit/push authorized, merge/publish/signing not requested.

## 2026-10-23 — owner redirects to architectural/business workflow redesign

Owner explicitly rejects incremental UI repairs as the primary method; asks to
reassess potentially false foundations and redesign around personas/business
workflows. New target baseline:
docs/architecture/decisions/2026-10-23-business-workflow-redesign.md.
No claim that target is implemented. Current code2cc1010 pushed to origin/work;
local network min-height/overlay/tab-style corrections are tested work-in-progress,
not the redesign. Preserve these edits; do not continue treating patch count as
readiness. Current audit captures .local-runtime/business-redesign; read product
TRADING_BUSINESS_ACCEPTANCE and numerical engine implementation as source evidence.
Next: complete current persona capture inspection, reconcile capability/decision
contracts, then implement shared task/context shell and complete vertical journeys.
Retain security, numerical versioning, private-by-default owner sharing and Canada
regional boundary. No speculative cross-region deployment/transport.

Owner further clarified operating European pipeline gas business as design lens:
day-ahead/within-day trading, whole portfolio, LNG regas, researcher/trader/admin;
retain/add/remove data according to real business use (weather, network, EEX etc).
Target details recorded in docs/product/EUROPEAN_GAS_BUSINESS_WORKFLOWS.md and
DATA_TO_COMMERCIAL_DECISION_MAP.md. Current weather connector/API is explicitly
mock/empty; no demand/forecast capability may be claimed. Quantities/rights,
price-mark types, costs/cash and forecast vintages are foundational semantics.
Current audit reviewer session expired, refreshed only existing reviewer/admin
synthetic sessions without grant changes; controls capture resumed separately.

Owner preservation clarification: current project is generally rigorous; do not
break that premise or change before thinking through implications. The redesign
document is now explicitly a candidate under validation, not an automatically
accepted replacement architecture. Classify presentation/integration/capability/
semantic defects before changes; preserve proven security/numerical/temporal/audit
contracts. No new blanket approval requirement inferred. Fresh current audit
screens for trader portfolio, analyst strategy, reviewer and admin inspected;
reviewer upstream-resource403 is a concrete composition/permission mismatch to
investigate, not authority to broaden permissions. Sources weather mock/empty
verified from source; other alleged gaps require current-code reconciliation.

Fresh persona screenshots now inspected and source reconciliation recorded in
BUSINESS_REDESIGN_CURRENT_STATE_REVIEW.md. Confirmed many foundations already
exist (business data-product catalogue, cash valuation, constrained allocation,
regas readiness, case/snapshot services). Reuse before adding types/services.
Trader/analyst/admin capture plus reviewer role403 reflects task read composition;
do not broaden permission. Next whole-workflow design should put selected case/
resource/interval and resulting artifact ahead of module routes or technical forms.

## 2026-10-24 — case workflow, chart integrity and requested main consolidation

Owner explicitly requested push, merge work to main and retain one tree. One Git
worktree exists at /workspace/EurogasNexus; fetched main is ancestor of work.
Current validated scope: canonical case URL/reload context and logout scrub,
capability-based preparation/review composition, selection epoch race guards,
case-first review; preserve backend authority. ActiveContext's separate gap list
has not yet been integrated with this case selection and remains a follow-up.
Actual independent reviewer synthetic browser9 passed; case API5 passed. Source
mutation runtime tests cover A→B→A stale completion. Chart missing drawdown is no
longer zero; gaps and zero-baseline area are tested, units/table/categorical dates
and frozen comparison periods disclosed. Portfolio labels now distinguish scenario
quantities from reconciled obligations. No numerical engine changes.
Web950passed3skipped; production build passed (existing dynamic-import warning).
Actual analyst backtest and trader portfolio screenshots inspected; scope and
remaining gates in acceptance22. Native artifact not rebuilt for this revision.
Role analytics requirements added; VaR/clearing margin and broader business
redesign are not complete. No production readiness assertion accompanies merge.
