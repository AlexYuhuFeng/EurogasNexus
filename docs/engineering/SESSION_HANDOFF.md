# Session handoff (2026-11-26)

This file hands the work from the cloud session that ran until 2026-11-26 to a session
running on the owner's own computer. Read it fully before doing anything, then read the files
it names, in the order given.

## 1. Where the product stands

Eurogas Nexus is a decision-support second screen for a European gas trading desk, beside the
trading screens and the trading and risk system of record (the ETRM). It never places orders,
submits nominations, settles or books.

- `main` holds everything described below. The beta pre-release is created by the release
  workflow (see section 8); the cloud session could not push tags.
- The demo server (https://8080-agq6hf7a5l6f4ybvl7s2z7xpuq.instabox.tech) runs the released
  `main` of 2026-11-27. The owner decided it stays on that version: do not deploy to it again
  unless he asks.
- Seven professional reviews were run on 2026-11-26 (front office, middle and back office,
  technology, multinational, security, operations and governance, quant models). They are in
  `docs/assessments/professional-review-2026-11-26/`.
- The owner approved the architecture plan and all twelve of its recommended decisions on
  2026-11-26: `docs/architecture/ARCHITECTURE_V3_PLAN.md`. Section 8.1 lists the decisions.
  Draft decision records are in `docs/architecture/decisions/` (some are now accepted).

## 2. Read these, in this order

1. `AGENTS.md` (the standing rules; rules 7, 8, 15, 16, 17, 18 and 19 matter most).
2. `docs/architecture/ARCHITECTURE_V3_PLAN.md` sections 1, 5, 6, 7 and 8, then the layer
   sections of section 3 as each work package needs them.
3. `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md`, the newest entries at the top: what
   each merged package built and the decisions it recorded.
4. `docs/security/SECURITY_REVIEW_REMEDIATION_2026-11.md` and
   `docs/release/notes/SECURITY_HARDENING_2026-11.md`: what the security work changed and what
   an existing deployment will notice.
5. `docs/operations/` runbooks added in phase 1: `MONITORING.md`, `ALERT_RESPONSES.md`,
   `DATABASE_UPGRADE.md`, `BACKUP_RESTORE.md`, `DISASTER_RECOVERY.md`,
   `DB_RUNTIME_HARDENING.md` (the one table of database timeouts), the serving runbook with
   the measured load numbers, and the retention schedule.
6. `docs/product/UX_REFERENCE.md` before any client work.

## 3. What is done

Phase 0 of the plan (all merged):

- Wrong risk and valuation figures fixed (VaR inputs and rolls, index-priced exposure, the
  forward curve from one snapshot, marginal transport cost, mark-to-market with forward FX and
  discounting, one net position for Today and the ladder).
- Security review remediated: book and entity isolation on by default and enforced in one
  place; decision cases inside the commercial boundary; the deployment token scoped; venue
  labels only from connector identities; a hash-chained audit trail with separate database
  roles; an authenticator-app second factor; dual control on privileged changes; method-aware
  route permissions; export neutralisation; security headers; rate limits.

Phase 1 of the plan, "safe to run" (merged):

- Serving: one live-update poller per process, no database call on the server's event loop,
  several API processes with a shared cache (Valkey), a load-test script.
- Monitoring: a scrapeable `/metrics`, alert rules, structured logs, a scheduler lock and
  heartbeat, gated database upgrades with a reversibility declaration on every migration.
- Recovery and retention: a primary and hot standby with continuous backup (pgBackRest) and
  restore to a chosen minute, failover behaviour in the application, retention by data class
  with a 7-year floor for trading records and audit, raw pages stored once.
- The 5-second driver socket timeout that cut off every long statement is fixed: connecting is
  bounded at 5 s, statements by the database's own statement timeout.

Also merged earlier: the live map rework (flat, decluttered, cargo routes and arrival times,
import corridors), the three page reviews in English and Chinese, the backend audit (one error
shape, paging, one rule for "simulated"), the Europe-wide topology, the single identity for the
Danish hub, the berth rule, the optional TimescaleDB extension, the portfolio report, and a
housekeeping job for the demo server.

## 4. What is next, in order

First, before any feature work: **make hosted CI fast** (owner approved, 2026-11-27). A run
takes 45 to 60 minutes, almost all of it in two jobs that run their tests one after another:
`validate` (the whole Python suite in one process) and `browser-acceptance` (every page sweep
in one job). Target: about 15 minutes for a full run. In `.github/workflows/ci.yml`:

- split `validate` into four parallel shards (contract; unit, security, release and evals;
  api; db and ingestion), keeping one required summary job so branch protection needs no change;
- split the browser sweep into parallel jobs by page group, sharing one built client artefact;
- pushes to `main` are grouped by commit, so a superseded run is never cancelled: group by
  branch and cancel the older run (keep the newest commit's run, which rule 16 judges);
- skip the heavy jobs when a push changes only `docs/**` or `*.md`;
- then, if still slow, `pytest-xdist` inside each shard and a seed-once database fixture for
  the API tests (most of the API suite's time is re-seeding the same store per test).

Keep `scripts/ci/pre_push_check.sh` running the same tests as hosted CI, and do not skip,
quarantine or weaken any test to gain time. Measure before and after and record both here.

Also from the last CI failure: about 40 tests in 22 files under `tests/api` and `tests/unit`
seed their fixtures from today's date and could not be checked for calendar dependence (one,
the LNG disruption ranking, failed from 27 November because a delivery window crossed a month
end; it is now pinned to a stated instant with `tests/support/clock.py`). When touching one of
those files, seed from a stated instant the same way. The largest groups are in
`test_map_situation_api`, `test_nwe_balance_api`, `test_remit_outages_api`,
`test_opportunity_stream`, `test_gas_for_power_api` and `test_position_ladder_cargoes`.

Phase 1 items not yet built:

1. **Removals** (plan section 5, approved): the strategy laboratory's "backtest", strategy
   tracks and the shadow runtime; the second LNG cargo-economics engine and the second LNG
   workspace; alerts and breach banners computed on simulated prices, and the credit banner on
   the trader's landing page; the Linux desktop build as a supported product; two-thirds of
   the documentation files moved to an archive.
2. **Role model and segregation of duties**
   (`decisions/DRAFT-role-model-and-segregation-of-duties.md`): separate roles for risk,
   credit, compliance, product control and the head of desk; compliance reads the audit trail;
   an approval screen in the client for dual control (today approval is an API call); alerts
   routed to the right role.
3. **Environments**: test and training environments with masked data.
4. **Support model**, desk fallback card, onboarding path.
5. **Phase 1 exit checks that need real hardware**: the load test at 50 users with three tabs
   each, a restore to a chosen minute on a store of at least 50 GB, a failover drill with the
   real standby image. See section 6.

Then phase 2, "numbers you can sign" (plan section 6): legal entities and calendars, exact
money and currency, the versioned trade copy with ETRM reconciliation, settlement history,
the end-of-day close, one exposure model, the numerical library stack.

Known open items from the merged work (do not lose these):

- Per-person heavy reads take 2 to 5 s of processor time each when cold, so 50 users arriving
  at once still wait 20 s or more. The plan's one-second target needs the phase 2 work
  (recorded results instead of computing on demand) and the production hardware. The plan's
  phase 1 exit criterion should be corrected to say so.
- The primary and standby image could not be built in the cloud container (no route to the
  package mirrors); the full failover drill has to be rerun where the image builds.
- The desk brief's fallback day change still compares closes across contract rolls.
- Background jobs that run inside the API share its 30 s statement limit.
- The security work left: no approval screen for dual control; PostgreSQL row-level security
  as a second layer; per-day budgets for AI calls; a KMS or Vault integration.
- The Review page sends 145 to 389 read requests on a cold load; they are not rate-limited,
  but it is a load concern.
- The sign-in throttle is still counted per client address, so people behind one gateway
  share it.
- `application/ai_gate.py`, `application/ai_eval.py` and `core/config.py` still find the
  repository root from their own file location, which is wrong in an installed image (the
  same cause that broke the upgrade command on 2026-11-26). Check each in the image.
- An external penetration test is to be commissioned at the end of phase 1 (owner's action).

## 5. The archived research branch

The tag `archive/research-agentic-decision-architecture` holds Codex's experiment on using AI
agents inside the product (its documents are already on `main` under `docs/research/` and
`docs/architecture/`). Its code was deliberately not merged. Look at it at two points, and
reuse what fits instead of merging it wholesale:

- when building the phase 2 end-of-day close: its "refuse to answer unless the evidence is
  complete and in date" gate (`src/eurogas_nexus/application/agents/decision_research.py`);
- when designing the phase 3 feed handler: its typed "this data changed, recalculate" message
  (`src/eurogas_nexus/streaming/contracts.py` and the scheduler consumer).

Its measured result stands: for known cases a model added seconds of delay and chose no better
than a fixed order, while a plain rule got every case right. Keep models out of calculations.

## 6. How to work

Roles, as the owner set them:

- **Orchestration and planning: Fable 5.2 at medium effort.** That session plans, writes
  briefs, reviews every change, runs the gates and merges. It does not implement large changes
  itself.
- **Implementation**, by one of:
  - the Claude Console key, Opus 5.5 at medium effort, through
    `scripts/dev/claude_implementer.sh <worktree> <task-file> [max-turns]`
    (`IMPLEMENTER_ENV_FILE` points at the keys file). At handoff this key had run out of
    credit; use it only if the owner has topped it up;
  - DeepSeek through `scripts/dev/deepseek_implementer.sh <worktree> <task-file> [max-turns]`
    (`DEEPSEEK_ENV_FILE` points at the keys file), for bounded, well-specified jobs;
  - Opus 5.5 sub-agents at medium effort.
- **Notify the owner only when a decision is needed.** Otherwise keep working.

Method that worked:

- One git worktree and one branch per work package; a written brief per package that names the
  plan sections and decision record, the environment, the gates and the report format.
- Root causes, not symptoms: for each defect, how it arose and where else the same cause
  exists; fix every instance.
- When two packages touch the same files, give the merge itself to an implementer as its own
  task. Never drop a security control to resolve a conflict.
- Before every push run `scripts/ci/pre_push_check.sh` (rule 15). It stops at the first
  failure, so run the suites without `-x` first:
  `python -m pytest -q -p no:cacheprovider tests/contract tests/unit tests/security tests/release tests/evals tests/api tests/db tests/ingestion`,
  and in `clients/web`: `npx tsc --noEmit && npm test && npm run lint:css`.
- A push to `main` is done only when the hosted CI run for that commit is green (rule 16).
- A human reviews every change to `main` that touches security, the data model or calculations
  (approved decision 12): open a pull request for those and ask the owner.

Keys: a file outside the repository, with `export NAME=value` lines for `GIE_API_KEY`,
`EIA_API_KEY`, `ENTSOE_SECURITY_TOKEN`, `DEEPSEEK_API_KEY` and `ANTHROPIC_CONSOLE_API_KEY`. The
owner has it. Never commit or print a key. The demo server's key was injected by the cloud
environment and is not in that file.

Local machine: Windows, 8 cores, 32 GB. Use Docker Desktop with WSL 2 for PostgreSQL, Valkey
and the stacks in `deploy/`. With this machine the phase 1 exit checks in section 4, item 5
can be run at full size, except that a primary and a standby on one machine prove the
mechanism, not a real standby.

Outside actions the owner will take after the development work: licence procurement for the
end-of-day EEX and ICE settlement files and for Trayport; a second human maintainer and
source-code escrow; the external penetration test; the production hardware.

## 7. Owner's standing positions recorded on 2026-11-26

- Data sources, components and services are acceptable when their terms grant free commercial
  use; the product is treated as an internal commercial service the owner hosts. Sources whose
  terms exclude commercial use stay out, and licensed market data comes only through the
  customer's own entitlement (rule 18). If the product is later sold to other firms, the
  redistribution terms of each source need a second look.
- The map uses OpenStreetMap data through OpenFreeMap only, with the bundled outline as the
  offline fallback. There is no 3D view: intensity is shown with flat encodings.
- The Danish hub is one hub, coded ETF, with GTF as its alias.
- No new polish or feature work on areas the plan marks for removal or redesign.

## 8. Repository housekeeping the cloud session could not do

The cloud session's access allowed pushing commits to `main` and its working branch only; tag
pushes and branch deletions were refused. Do these with the owner's own git credentials:

1. Check that the hosted CI run for the newest commit on `main` is green (rule 16); fix what
   is red before anything else. See `docs/engineering/CI_AND_BRANCH_PROTECTION.md` for what
   only hosted CI verifies and how to reproduce each job.
2. Release: the product version is `1.0.0-beta.1`. Either run the "Build and Release" workflow
   on `main` with `release_channel: beta` (it creates the tag and the pre-release), or push
   the tag `v1.0.0-beta`, which the workflow accepts as the alias of `v1.0.0-beta.1`.
3. Archive the research branch, then delete it:
   `git tag -a archive/research-agentic-decision-architecture origin/research/agentic-decision-architecture -m "Archived research branch"`
   and push the tag.
4. Delete the remote branches that are fully merged into `main` (verify each with
   `git merge-base --is-ancestor origin/<branch> origin/main` first):
   `innovation/continuous-commercial-intelligence`, every `fix/*-on-innovation` branch,
   `fix/demo-review`, `fix/portfolio-report-main`, `fix/portfolio-report-on-innovation`,
   `wip/berth-rule-on-innovation`, `wip/timescale-on-innovation`, and, after step 3,
   `research/agentic-decision-architecture`. Keep `main`. The cloud session's working branch
   `claude/gas-trading-tool-review-08bgpo` equals `main` and can go too.
