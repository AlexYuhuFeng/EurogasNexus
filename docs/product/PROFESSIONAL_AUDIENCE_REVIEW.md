# Professional Audience Review

Status: **review, current at `1a1ee1e`** (2026-09-19). Authority: the product's own audience
statements — [PRODUCT_INFORMATION_ARCHITECTURE](PRODUCT_INFORMATION_ARCHITECTURE.md) section 2,
[INDUSTRY_BENCHMARK](INDUSTRY_BENCHMARK.md), `04_PRODUCT_EXPERIENCE_ARCHITECTURE.md` sections 9-10,
and the functional assignments in `src/eurogas_nexus/security/capabilities.py`.

## 1. Why this exists, and how it was done

The programme has reviewed itself many times against **its own architecture** — the reconciliation
register, the claim audit, the fitness gates. Nothing had reviewed it against the people it is for.
This document asks, audience by audience: *what does this professional get today, where do they
stumble, and what should happen next?*

What was inspected, rather than recalled:

- the navigation and page registry (`clients/web/src/app/navigation/productNavigation.ts`),
  the work-mode registry (`app/experience/workModes.ts`) and the capability catalogue
  (`src/eurogas_nexus/security/capabilities.py`);
- the audience-facing documentation (`docs/user/*`: quick start, market, portfolio, decision review,
  strategy lab, shadow monitoring, data status and provenance), the UAT pack (`docs/uat/*`,
  including the trader script written as business questions) and the compliance boundary
  (`docs/compliance/RESEARCH_ONLY_COMPLIANCE.md`);
- the milestone ledger ([COMMERCIAL_READINESS_BACKLOG](COMMERCIAL_READINESS_BACKLOG.md)) and the
  execution checkpoint;
- the running product: the whole-product browser sweep (16 pages × EN/zh-CN × 3 viewports, axe,
  overflow, headings), the two desk engines exercised over real HTTP, and the CI runs to the current
  head.

Limits are stated in section 7. Nothing here is a certified user study; it is an inspection with
pointers, so a reader can disagree with any line of it.

## 2. Who the product is for

The information architecture names five jobs; the capability model names six overlapping functional
assignments; the client set reaches them through four surfaces. Read together:

| Audience | Functional assignment | Where they work (primary → pages) | Surface that fits them |
|---|---|---|---|
| **Gas trader / desk analyst** | `TRADER` | Market → network, market, capacity; Decision → scenario, optimize, nomination, dispatch | Web (universal) + Desktop workstation |
| **Portfolio manager / structurer** | `TRADER` + `HQ_BUSINESS_ANALYST` | Portfolio → contracts, orders; Decision → scenario | Web |
| **Reviewer / management (incl. compliance)** | `REVIEWER_MANAGEMENT` | Decision → review; Inspector for evidence behind a number | Web |
| **Quant / strategy researcher** | `QUANT_RESEARCHER` | Strategy → design, backtest, compare, shadow; System → research, agents | Web + SDK/CLI |
| **Data / runtime operator** | `DATA_OPERATOR` | Administration → sources, runtime (control plane) | Web + CLI |
| **Platform administrator** | `PLATFORM_ADMINISTRATOR` | Administration → access, runtime; System → settings | Web |
| **Automation and AI agents** | — (machine callers) | — | SDK, CLI, MCP |

Two structural facts hold for all of them: **work mode changes composition, never authority**
(`EXPERIENCE_PROFILE_GRANTS_AUTHORITY = False`), and the **administration surface is a control plane**
the shell refuses to an identity without an administration capability, with the backend authorising
every request independently.

## 3. Audience by audience

### 3.1 Gas trader / desk analyst

**Gets today.** A map-first market workspace that answers *what is happening physically and
financially* (network map with evidence stack, market terminal with curves/quotes/spreads, capacity
workspace with the operating board, storage and LNG views); an intraday decision feed on the market
surfaces; portfolio position and resource terms; a Decision workspace whose tasks each own one
compute — pool optimisation, route comparison, **nomination-window assessment** and **storage
dispatch** (the last two added this stretch); a governed research run for questions that need the
agent pipeline; and an Inspector that resolves detail, provenance and restrictions from state the
identity already received. Figures carry as-of, units and provenance, `unavailable` is never
rendered as `0`, and simulated or stale data is marked.

**Stumbles.** The day has no owner. Nomination windows, the intraday feed, the decision queue and the
optimisation results live in different workspaces, and nothing answers *"what must I decide before
the next window closes, and what is still unactioned"* in one place. The intraday feed is mounted on
three market surfaces rather than composed once. Bar size has no operator control (the scenario
builder declares 5 minutes), and the four remaining engines a desk uses for capacity booking,
contract preselection, portfolio-network and path optimisation are SDK-only.

**Next.** (a) One **day view** inside an existing task: the next windows, the unactioned decisions
and the alerts that moved, each with its deadline and evidence — no new page. (b) Surface
`optimization/capacity` and `optimization/contracts` where the capacity decision is taken.
(c) Give bar size an operator control in the Design task, where the scenario is built.

### 3.2 Portfolio manager / structurer

**Gets today.** Resource terms with an editable, reviewed contract draft and a single save action in
the workspace header; the projection-composed portfolio summary (summary, screen orders, PnL
snapshots, contracts, resources on one as-of) instead of a browser-side join; route economics through
the route-cost/netback what-if that names its own provenance as operator input; the declared capacity
profile book; exposure through market positioning.

**Stumbles.** The pool optimiser's *canonical* route is still the older `/route-cost` pair, so the
run is snapshot-cited and job-tracked but cannot use the runtime/DB-first decision context the newer
engine supports (register C14/D8). Attribution stops at contract level: nothing carries a position's
PnL back to the contracts that produced it beyond the attribution panel on the shadow task.

**Next.** (a) Give `/api/optimization/*` the two invariants the older family has (snapshot citation,
job tracking) — the stated *condition* for collapsing the overlap — then move the pool optimiser to
one route. (b) Extend attribution to the position book.

### 3.3 Reviewer / management, including compliance

**Gets today.** A Review workspace with the review projection, the analysis-snapshot picker and a
decision recorder; **Decision Cases** with their own records and a governed-outcome path (a 409
`case_not_decidable` renders its blockers as an answer rather than a failure); review packs from
agent runs with their artefact chain; the actor of every governance act resolved from the
authenticated identity, never from a typed name (C13), with audit rows naming that identity; an
Inspector that shows evidence the backend withheld *with the reason*; and a research-only
compliance statement that fixes the product boundary (no execution, no order entry, no nomination,
no settlement).

**Stumbles.** The evidence is strong but **not assembled for a human who has to sign something**. A
reviewer can reconstruct a decision from the Inspector, the review pack and the audit rows, but there
is no one artefact that says: this is what we saw, on which snapshot, under which engine version,
what we decided, who decided, and what it depended on. The compliance boundary is stated in a
document rather than carried on the surfaces that could breach it.

**Next.** (a) A **decision pack** built from what already exists (snapshot id, engine and application
version, inputs, warnings, actor, audit references), exportable and re-readable. (b) Carry the
no-execution boundary into the surfaces whose actions are closest to it (capacity booking,
nomination assessment) as a disclosure slot, not as copy only in a doc.

### 3.4 Quant / strategy researcher

**Gets today.** A Strategy Lab with Design (draft, identity metadata, freeze, fork), Backtest
(experiments, series, events, attribution), Compare and Shadow; reproducibility that binds runs to a
dataset snapshot, engine version, manifest hash and data cutoff; a governed agent research pipeline
with capability contracts, budgets, challenge reports and review packs; a data platform with
feature/target registries, validation and dataset snapshots; the shadow task's economics
(price-basis board, market tape, pooled PnL curve, exposure ladder, contract attribution, run
provenance); and the SDK for automation.

**Stumbles.** Two engines the researcher would use are SDK-only (`research/backtest`,
`research/shadow-run` variants, `research/nowcast`), so a research result can be produced by a
machine and land in a notebook without the platform's disclosures. The unmounted-terminal decision
retired the parallel shadow UI, but **bar size** and the risk-override form went with it.

**Next.** (a) State the disclosure contract for SDK-produced research results explicitly, so a
machine-run result is as checkable as a screen-run one. (b) Decide whether research benches belong
on a surface at all, or stay a machine surface with its own documented contract (a D8-style ruling).

### 3.5 Data / runtime operator

**Gets today.** A control-plane Administration workspace: sources with posture and certification,
ingestion runs with machine-readable issues, scheduler heartbeat and drift, provider credentials and
connection tests, runtime posture and dependencies, and the data-operations specification behind it.
The runtime-DB validator, migration preflight, backup/restore drill and the documented failure
vocabulary (`BLOCKED`/`PARTIAL`/`COMPLETE`) are operator-invoked and honest about what they did not
check.

**Stumbles.** Certification and its acts (`/api/source-certifications`, `.../certify`) are reachable
by nobody — no surface and no client method (the reachability gate records them as deliberate
control-plane gaps, which is honest but is still a capability without a caller). Operator documents
mix current and historical states in places, and the acceptance CI job's server-start step has failed
twice in six runs on unchanged code without capturing a diagnostic.

**Next.** (a) Give certification a bounded surface in Administration, or retire the routes
deliberately. (b) Capture diagnostics in the acceptance job's start step so a failed start is
readable rather than re-runnable.

### 3.6 Platform administrator

**Gets today.** Roles and scope catalogues that match what the backend enforces, API-key issuing with
a one-time bearer, identity administration over SQLite/PostgreSQL, OIDC and session paths, runtime
posture, and the capability catalogue that separates platform administration from commercial access
so an administrator holds no commercial-data permission by accident.

**Stumbles.** The identity posture is **undecided in practice**: every profile's code default trusts
its network, and the owner's decision to install authentication everywhere (D1) is recorded with a
plan but not built — so an administrator cannot yet choose "identify your callers" and rely on it.
The second-approver policy for grants (D2) is still an open owner decision.

**Next.** (a) Build D1 with the plan already recorded (exempt the public authentication routes and
probes, prove entitlement parity, rework the two suites whose premise is the old posture).
(b) Decide D2.

### 3.7 Deployment IT and commercial handover

**Gets today.** Deployment contract, roles, channels, update policy, installers' documentation,
supply-chain evidence (SBOM, checksums, provenance), a preview release dry run that builds the
container and records signing as pending-external, GA gates, and an environment that can be stood up
from a documented container plus migrations.

**Stumbles.** The desktop/workstation half cannot be verified here (no Rust toolchain), so the
"professional analytical workstation" value proposition is contract-only: window profiles,
multi-monitor restore, notifications, deep links, tray and file dialogs are designed and tested as
contracts, not shipped as a verified native build. External items (IdP acceptance against a real
issuer, provider certification, signing/notarisation, a production restore drill) remain the
operator's.

**Next.** (a) Keep the honest claim: workstation-grade behaviour is unverified until a machine with
the toolchain exists. (b) Put a **handover index** in place — one page listing what is deployed, what
is verifiable where, what is signed, and who owns each external item.

## 4. Three findings that cut across every audience

1. **The clock has no surface.** The product can now assess a nomination window and a storage
   dispatch, but nothing joins deadlines, unactioned decisions and alerts into the one question a
   desk asks first. This is the highest-value product gap and it needs no new page (rule 9).
   **Delivered 2026-09-19** (next steps, row 3): the day board above the Decision workspace's tasks,
   behind one new READ-floor read of the declared window masters. It exposed a third finding of its
   own, now **D9** in the reconciliation register: the engine matches window clock times against the
   *UTC* clock while its own field documentation claimed the local gas-day clock, so a deployment
   that loaded local market times would have been one to two hours out with nothing to show for it.
   The read states the basis it assumed; changing it is the owner's call.
2. **M1-P0 is still `ready` in the project's own ledger**, while `M0-P0` is complete: *"ENTSOG
   timezone normalization unproven; naive timestamps treated as UTC → ENTSOG flow/capacity periods
   can be shifted or mis-labelled"*. Every audience's trust in a period rests on it, and it is a
   correctness item rather than a feature. **It should be finished before more surface work.**
3. **The deployment's identity posture is decided but not built (D1).** Until it is, "the network is
   the trust boundary" remains a code default rather than a deployment statement, and the
   administrator audience cannot choose otherwise. **Delivered 2026-09-19** (next steps, row 2):
   every profile identifies its callers, the old posture is a deployment's own reported setting, and
   the delivery also closed a widening defect the first attempt had exposed and declared twelve
   internal paths that had never had a permission.

## 5. Records this review corrects

- `PRODUCT_INFORMATION_ARCHITECTURE.md` still described **five** primary workspaces with `sources`,
  `runtime`, `settings`, `manual` and `glossary` under `system`. The implemented registry has
  **six**: the control-plane split moved `sources` and `runtime` into a capability-gated
  `administration` primary beside `access`, and `system` holds `research`, `agents`, `settings`,
  `manual`, `glossary`. Nothing read that document in a test, so the stale claim sat unguarded. The
  tables are corrected in this change.
- `COMMERCIAL_READINESS_BACKLOG.md`'s "Current run" pointer still says the run implements *only*
  CR-15 / P14, while its own ledger marks CR-01…CR-15 complete. The pointer is corrected to name the
  Architecture V2 programme checkpoint as the current state.
- Two of the four client surfaces have no audience-facing documentation: `docs/clients` covers the
  SDK and CLI designs as *engineering* documents, but there is no "I am an operator, start here"
  path that maps an audience to the guides that exist (seven user guides across five audiences).

## 6. Next steps, ranked

| # | Step | Serves | Why now | Size | Decides |
|---|---|---|---|---|---|
| 1 | ~~Finish **M1-P0** (ENTSOG timezone normalization, naive-timestamp handling)~~ — **delivered 2026-09-19**: one declaration per source, exact-UTC fixtures for CET/CEST/stated offsets/DST, and refusal instead of assumption for an unsupported or unprovable zone ([source timezone contract](../data/SOURCE_TIMEZONE_CONTRACT.md)) | every audience | correctness of every period; was P0 in the ledger | M | done |
| 2 | ~~Build **D1** (authentication in every profile) with the recorded plan~~ — **delivered 2026-09-19**: every route profile identifies its callers, the one way back to the old posture is the deployment's own reported statement (`EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS`), one exemption list serves both gates, and the attempt's widening defect is closed by never overwriting an identity another layer resolved | administrator, IT | a code default that trusts the network is the posture the programme keeps publishing *because* it is surprising | L | done |
| 3 | ~~**The day view**: next windows, unactioned decisions, alerts that moved — inside an existing task~~ — **delivered 2026-09-19**: `GET /api/optimization/nomination-windows` (READ floor, the 179th public path) serves the declared window masters with the UTC deadlines the gas-day calendar resolves them to, and the day board above the Decision workspace's tasks shows the deadlines, the actionable opportunities with no decision recorded, and a measured pointer into the alert centre that already exists in the top bar | trader, portfolio | the clock is the one thing the product still cannot show; the engines now exist | M | done |
| 4 | ~~**Decision pack** from existing artefacts (snapshot, versions, inputs, warnings, actor, audit refs)~~ — **delivered 2026-09-19**: `GET /api/decision-cases/{case_id}` carries a `pack` — context, evidence with each cited snapshot's resolvability measured, assumptions, alternatives, AI findings, warnings, the recorded decision with its actor, the case's audit trail, its blockers and a canonical `content_hash` with its basis, so a printed copy can be matched to the record. It rides on the existing read (no new path), and it says plainly that the platform holds no signature: the signature is the human act the pack exists for | reviewer, compliance | a governance artefact a human can sign | M | done |
| 5 | Give `/api/optimization/*` snapshot citation + job tracking, then collapse the pool-optimiser overlap | portfolio, trader | the stated condition in D8; removes the last two-answers-to-one-question | M | worker (decided) |
| 6 | Surface `capacity` and `contracts` engines; give certification a surface or retire it | trader, data operator | closes the remaining reachability gaps deliberately rather than by accident | M | worker |
| 7 | SDK-produced research results inherit the platform's disclosures | quant, reviewer | a machine-run figure must be as checkable as a screen-run one | S-M | owner (policy) |
| 8 | Acceptance-job diagnostics on the server-start step | IT, reviewers of CI | two failures in six runs with no readable cause | S | worker |
| 9 | ~~Handover index for deployment IT (what is verifiable where, what is signed, who owns each external item)~~ — **delivered 2026-09-19**: [HANDOVER_INDEX](../deployment/HANDOVER_INDEX.md) states what a receiving team can verify without us (with the exact command and record for each), what this repository signs or supplies, the seven items only they can close, and what this repository does **not** verify | IT, commercial handover | the honest packaging of "not verified here" | S | done |
| 10 | Remaining Wave 9 action-geography lifts, then the structural splits (`client.ts` ~2.9k lines, 143 unreferenced locale keys) | every maintainer | what makes the next change expensive | M-L | worker |

Owner decisions still open, unchanged by this review: **D2** (second approver for grants), **D4**
(map tiles and their licence), **D5** (how far the native/RC work proceeds here), **D6** (what the MCP
surface does about the calling user), **D7** (the authority a headless `monitoring-worker` invokes the
provider under).

## 7. What this review could not verify

- **The desktop workstation**: no Rust toolchain exists in this environment, so no Tauri build,
  installer, notification, multi-monitor restore or file dialog was exercised. Its contract, its
  capability model and its diagnostics consumer are tested; the native behaviour is not.
- **Real users**: the trader UAT script exists and is written as business questions, but no session
  with a professional trader has been run here. Every "stumbles" line above is an inspection
  judgement, not observed behaviour.
- **Licensed data**: no EEX, ICE, ICIS, Argus, Platts or Kpler feed is called; the platform's own
  simulated/preview fixtures stand in, and they are marked as such.
- **Production**: the restore drill, performance baseline and browser sweep ran against a local
  container and a local dev server. No SLO has been demonstrated under production load.
- **External sign-offs**: IdP acceptance against a real issuer, provider certification, penetration
  testing, signing/notarisation and GA acceptance remain the operator's.
