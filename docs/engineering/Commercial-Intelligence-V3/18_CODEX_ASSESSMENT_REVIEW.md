# 18 Codex assessment review (CODEX-1)

The owner asked on 2026-11-25 for a review of the assessments Codex wrote on agents and on data
storage and processing: build each one that is valid and contained, and list the rest for a
decision. This document gives the verdict on each proposal, what was built and what is left.
Decisions are in [08](08_DECISION_LOG.md). Acceptance criteria are in [06](06_ACCEPTANCE_CRITERIA.md)
(CODEX1-1 to CODEX1-6). Evidence is in [09](09_VALIDATION_EVIDENCE.md).

Data volumes and the infrastructure staging they justify (backfill, ten years of running,
PostgreSQL, TimescaleDB, Kafka and Iceberg thresholds, industry benchmarks) are sized in doc 19,
written separately. This document does not project volumes. Where a verdict depends on size, it
says "sizing in doc 19".

## What was reviewed

**The Codex work.** Branch `research/agentic-decision-architecture`: five commits from 2026-11-25
(`a3d45af`, `994388a`, `0a174f4`, `7fd0983`, `515f3b9`) on `main@6d21b89`. The branch was read
through git only and was not changed. It holds:

- `docs/engineering/CODEX_TO_CLAUDE_HANDOFF.md`, the handoff;
- `docs/research/AGENTISATION_ARCHITECTURE_REVIEW.md`, a repository review and a suitability table
  per workflow;
- `docs/architecture/AGENTIC_DECISION_ARCHITECTURE_PROPOSAL.md`, a dispatch ladder, an evidence
  policy, an event design and an 18 to 36 month technology table;
- `docs/architecture/decisions/2026-11-25-governed-agent-research-boundary.md`, an ADR-style note;
- `docs/research/AGENTISATION_EVALUATION_RESULTS.md`, `ROUTE_FOLLOW_UP_LIVE_MODEL_EVALUATION.md` and
  `route_follow_up_live_results.csv`, the measurements;
- `application/agents/decision_research.py`, `application/agents/route_follow_up.py` and two
  scripts under `scripts/research/`, an offline synthetic experiment;
- `streaming/contracts.py` and `application/opportunities/schedule.py`, a typed
  `IngestionInvalidationV1` notice wired into the scheduler, with
  `tests/contract/test_ingestion_invalidation_contract.py`;
- an addition to `docs/architecture/STREAMING_KAFKA_CONTRACT.md`.

**What it was judged against.** The innovation branch at `85d59f1`, which is well ahead of the
`main` that Codex reviewed. `main` lacks the GOV-1 AI controls (register of uses, a switch per
use, licensed-data use, audit), the market event outbox (ADR Decision 28), P-17 maker-checker,
DATA-1, TAR-1, SCHED-1, NEWS-1 and LNG-3. Several Codex findings are therefore already met here.
Others still stand, and those are the ones built.

**Other assessments on storage and processing.** A search of `main` and the innovation branch
(for Codex, big data, storage, lakehouse, Parquet, DuckDB, TimescaleDB, Iceberg, partition,
retention, streaming and Kafka) finds four earlier documents with the same positions. They are
`docs/architecture/GLOBAL_DATA_DEPLOYMENT_ASSESSMENT.md` (regional installations; its one
low-cost change, the LLM egress check at both adapter entry points, is already on `main`),
`docs/engineering/Architecture-V2/07_DATA_PLATFORM.md` section 5 (PostgreSQL by default; object
storage and Parquet only on a concrete need), ADR Decision 24 (time series stay in PostgreSQL;
native partitioning at about 50 million rows or a missed latency budget; TimescaleDB rejected),
and `docs/research/DATASET_ARCHITECTURE.md` with `POINT_IN_TIME_DATASETS.md`. The repository
history before `6d21b89` is squashed, so these cannot be attributed to Codex from git. None
conflicts with the research branch. Its technology table agrees with ADR Decisions 24 and 28.

## Summary

| Assessment | Verdict | Built in CODEX-1 |
| --- | --- | --- |
| Agentisation architecture review | Valid. Most findings stand on the innovation branch | Runtime controls (traced refusals, output hash and shape, timeout overrun, honest quality, person-only confirmation, audit); the agents route fails closed; three AI-gate cases |
| Agentic decision architecture proposal | Partly valid. Its dispatch, portfolio and evidence principles match the programme. Its infrastructure items are already decided or not yet justified | A versioned, transport-neutral market change envelope (the one contract-level seam) |
| Governed agent research boundary (ADR-style note) | Valid as a principle | Recorded in [08](08_DECISION_LOG.md); no ADR number needed, since nothing new is stored |
| Ingestion invalidation contract and scheduler change | Not valid as written. The outbox already records the same fact | Not built; its intent is carried by the envelope above |
| Evidence-gated route research module and benchmark | Partly valid: the idea holds, the module does not belong in `src` | Not ported; kept on the research branch |
| Follow-up planner and live model evaluation | Not valid to build. The evidence says no | Not built |

## Agentisation architecture review

| Proposal | Verdict | Reason against the innovation branch | Built | Left for the owner |
| --- | --- | --- | --- | --- |
| Keep the market and portfolio control loop deterministic; plan dynamically only where the next step depends on earlier findings | Valid | Already the programme's posture. The LNG-3 engine is pure and deterministic (ADR Decision 36), M7 routing is rule-based, and the research orchestrator plans by rule (`rule-based-plan/v1`) | Nothing new | None |
| The runtime skips completion metadata on an early refusal | Valid | `CapabilityRuntime.invoke` stamped metadata only after a handler ran. A refusal carried no principal, version or argument hash | Every result, refusals included, names the capability, version, principal, agent run, argument hash, time and duration | None |
| The runtime does not validate result schemas | Valid | `output_schema` was declared and never read. `output_hash` existed and was never set | A success is refused (`INTERNAL_ERROR`) when its data breaks the declared type or required fields, or when the handler returns no result envelope. A success carries `output_hash` | Richer output schemas per capability (today nearly all declare `{"type": "object"}`) |
| The runtime applies no timeout | Partly valid | A synchronous handler cannot be cancelled in process. Cancelling needs a worker or process boundary, which is not contained | A call that overruns its declared `timeout_policy` gets a `TIMEOUT_OVERRUN` warning, so a late result is not shown as on time | Cancellable execution: decide only when a handler is measured to overrun |
| Handlers return generic quality defaults | Valid | `CapabilityResult.success` defaulted `quality_state` to `VERIFIED` for every capability, including those that only compute on the caller's own figures | The default is `NOT_ASSESSED`. A handler that checked its evidence says `VERIFIED` itself | `domain/agents/findings.py` still defaults research findings to `VERIFIED`. Change it in a follow-up with the orchestrator's evidence |
| `_principal` falls back to a synthetic analyst with wildcard scopes | Valid | Still present. The app-wide identity dependency makes it unreachable today, but it would fail open if the router were mounted without that dependency | `_principal` raises 401 when no identity is attached | None |
| Confirmations come from a request boolean; add actor-, action- and version-bound proof | Partly valid | Any caller that sent `human_confirmation: true` could confirm, including the deployment token (a service principal). A model is kept away from the four built-in confirmation capabilities (strategy freeze; shadow monitor start, pause and resume) only by the never-model list | A confirmation counts only from a signed-in person (`principal_type` `USER`; the default is `SERVICE`), never from a model acting for an AI use and never from a token or service account. Each confirmation, each refused confirmation and each call of a writing capability is audited (`governance.agent_capability`) with the qualified id (`capability@version`) and the argument and output hashes. A gate holds every human-gated capability on the never-model list | A token, issued when the capability is shown and sent back with the confirmation, that names the version the person saw; second-person approval through P-17 if research writes ever become consequential |
| MCP: persisted identity, delegated row scoping; legacy MCP tools bypass the runtime | Valid | Still open (C8 in `mcp/server.py`). Not contained: it needs a delegated identity across the MCP transport | Nothing | The next governance slice; see "For the owner" |
| The suitability table per workflow (deterministic, LLM-assisted, agent-orchestrated, deferred) | Valid as guidance | It agrees with [14](14_AI_ROLES_PERSONALISATION_AND_IMPROVEMENT_LOOP.md) and the GOV-1 register: NEWS-1 notes are LLM-assisted and grounded; risk, multi-cargo and execution coordination stay deterministic | Nothing | None |

## Agentic decision architecture proposal

| Proposal | Verdict | Reason against the innovation branch | Built | Left for the owner |
| --- | --- | --- | --- | --- |
| Dispatch ladder: pure function, then domain service, workflow, optimiser, a single LLM call, and a governed planner last | Valid | It matches how the branch is built. One finding follows: for a small candidate set, evaluate every candidate deterministically instead of letting a model choose. LNG-3 already enumerates and values every option | Nothing | None |
| Freeze an authorised portfolio snapshot; evaluate cargoes that share a resource together; never let concurrent analyses change live balances | Valid | LNG-3 values a disruption across the whole book against the plan with shared-slot constraints, and the choice records a decision without booking anything. This is also the owner's opportunity-cost point: a remedy is valued by what it costs the rest of the portfolio | Nothing | Cross-product options (pipeline or hub gas to cover a late cargo) build on LNG-3's pipeline-supply options, not on an agent |
| Evidence states VERIFIED, CONDITIONAL, INDICATIVE, UNKNOWN and CONFLICTED carried through outputs | Partly valid | Each domain grades evidence today: TAR-1 has `INDICATIVE` and `FINAL` versions, LNG inputs carry their source, the valuation snapshot keeps entitled quotes, settlements, firm marks and assumptions apart, and NEWS-1 cites lines. A shared vocabulary would sit on the source-precedence resolver that TAR-2 is building now | `NOT_ASSESSED` as the honest default for capability results | Adopt one vocabulary after TAR-2's resolver lands, so precedence and evidence state are defined once |
| Separate physical feasibility, commercial feasibility and execution confirmation | Valid | LNG-3 keeps hard constraints apart from cost, and every decision says `booked: false`. SCHED-1 keeps traded, confirmed, nominated and matched quantities apart | Nothing | None |
| Treat provider input as untrusted; server-side tool allowlists; reject model-supplied authority | Valid | Already GOV-1: tool allowlists per use and role, the never-model list, the grounding check on news notes. CODEX-1 adds that a model cannot confirm | Model confirmation refused in the runtime | None |
| Event design: pending keys first, a PostgreSQL outbox when recovery needs it, idempotent and coalesced jobs, rechecks before persisting | Valid, already built | ADR Decision 28 and M4 to M7: revisions, idempotency, replay, dead letters, LISTEN/NOTIFY wake-up, targeted re-evaluation, and five timestamps per event. Measured in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md): the worker claims an event about 0.2 s after commit; one process publishes about 230 events a second and delivers 1,300 to 1,900 | Nothing | None |
| Versioned event contracts; decode a named version and reject unknown versions; keep keys stable across transports | Partly valid | The outbox has identities and revisions, and the DATA-1 feed has a versioned cursor (`c1-`). No versioned wire form of a change existed for a later transport | `MarketChangeV1` (`streaming/contracts.py`): the feed's digest columns without the cursor, `kind` and `schema_version` in the value, `event_key` as the partition key, unknown versions and extra fields refused, and fields held equal to the feed's columns by a test | None |
| PostgreSQL 16 baseline (ADOPT_NOW) | Valid | ADR Decisions 2, 24 and 28 | Nothing | None |
| PostgreSQL declarative partitioning (DESIGN_INTERFACE_NOW) | Partly valid | ADR Decision 24 already sets the trigger: about 50 million rows in one observation table, or a time-range read over its budget after indexing. Partition keys change upserts and foreign keys, so the warning about unique constraints is right. `market_events` is append-only with no retention (DATA-1) | Nothing | Sizing in doc 19. Rehearse expand, backfill, checksum and switch on the first table that nears the trigger, not before |
| TimescaleDB (DEFER) | Valid | It agrees with ADR Decision 24 (a new extension and its licence terms; AGENTS.md rules 5 and 18) | Nothing | Sizing in doc 19 |
| pgvector (DESIGN_INTERFACE_NOW) | Not valid now | There is no retrieval consumer. NEWS-1 grounding is lexical and typed by design, and contract-clause retrieval is not built | Nothing | Revisit only when a retrieval use beats lexical search on entitled evidence, under a GOV-1 use with an evaluation set |
| DuckDB and Parquet research bundles (DESIGN_INTERFACE_NOW) | Partly valid | Plain Parquet with a manifest is a sound export format. It needs a customer or research consumer, and export entitlement (GOV-1 licensed use) applies to every copy | Nothing | Sizing in doc 19. Build an export manifest only when a consumer asks |
| Kafka-compatible contracts (DESIGN_INTERFACE_NOW) | Partly valid | The contract is right. A broker is not, today: [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 4 measured the transport far ahead of the desk's volume and set four revisit conditions (sustained outbox lag, tick-level evaluation, independent replay consumers, a hundred times today's volume) | `MarketChangeV1` keeps the key and version ready | Sizing in doc 19. A broker needs an ADR and a measured revisit condition |
| Iceberg-compatible analytical storage (DESIGN_INTERFACE_NOW) | Not valid now | It needs a catalog and object storage, and no consumer has asked for shared snapshot reads | Nothing | Sizing in doc 19 |
| Temporal or another durable workflow engine (DESIGN_INTERFACE_NOW) | Not valid now | The jobs table, the outbox's retries, backoff and dead letters, and P-17 for human approvals cover today's workflows. No long-running or resumable workflow has been measured to need more | Nothing | Revisit with an ADR if an approval workflow needs resumable state across days |
| Migration rules: expand, backfill, checksum, dual read, switch, contract; stable IDs outside partition layout | Valid | These are already the working rules (expand-only migrations, pinned schema heads) | Nothing | None |

## Governed agent research boundary (ADR-style note)

| Proposal | Verdict | Reason | Built | Left for the owner |
| --- | --- | --- | --- | --- |
| Keep deterministic calculations, portfolio constraints and event workflows; test dynamic planning only on novel investigations over a frozen snapshot; keep the prototype out of API, MCP and workers | Valid | It is consistent with ADR Decisions 28 and 36 and with GOV-1 | Recorded as a programme decision in [08](08_DECISION_LOG.md). No ADR Decision 39, because CODEX-1 adds no table or service | Whether to keep the research branch (recommended: keep it unmerged as the evidence record) |

## Ingestion invalidation contract (`IngestionInvalidationV1`)

| Proposal | Verdict | Reason | Built | Left for the owner |
| --- | --- | --- | --- | --- |
| A typed run-level notice (`opportunity.input.invalidated`, version 1, source, run, input class, scheduler time), built on the scheduler's ingestion path | Not valid as written | On the innovation branch, `market_events.ingestion_events` already publishes `source.ingested` for each run that wrote rows, with identity `run:<run_id>`, the source and the input class. It is stored durably with revisions, replay and dead letters, so the notice would repeat a weaker form of an event that already exists. It would also add a third definition of the input classes (the domain model and the scheduler already hold one each, kept equal by a test). The research diff was written against `main`'s scheduler, before M7's evaluation lock and one-minute debounce, so it would not apply as it stands | Not built. The transport-neutral idea is built as `MarketChangeV1` over the outbox | None |

## Evidence-gated route research (`decision_research.py`, benchmark)

| Proposal | Verdict | Reason | Built | Left for the owner |
| --- | --- | --- | --- | --- |
| Compose existing read-only route capabilities behind evidence gates (unknown, conflicted, not yet available, outside its validity window), synthetic and indicative only, unwired | Partly valid | The gates are right, and the measurement is useful: the governed path costs about 74 µs at the median over direct engine calls. But the module runs on fixture metadata, not on the branch's evidence (tariff versions, capacity, contracts). Codex's handoff says to keep it experimental. Real evidence for routes is the source-precedence resolver TAR-2 is building | Not ported. The runtime checks it had to do itself (unusable result, refusal trace) are now in the runtime | Reconsider a real evidence-gated route assessment after TAR-2, over its resolver |

## Follow-up planner and live model evaluation (`route_follow_up.py`)

| Proposal | Verdict | Reason | Built | Left for the owner |
| --- | --- | --- | --- | --- |
| A model picks one follow-up scenario after a baseline route check; tested on two local models | Not valid to build | Codex's own measurement: both models found a feasible follow-up in 3 of 9 cases, the same as fixed order; the deterministic purpose rule found 9 of 9. The models added 1.2 to 2.3 s at the median, and the larger one timed out. The planner also calls the provider adapter directly, outside `governed_model`: no register entry, no switch, no provenance on an audit row, no evaluation set. Live model routing is out of scope for this review | Not built | Keep model routing off. If it is ever reconsidered, it starts as a GOV-1 use with a held-out evaluation set, compared with evaluating every candidate deterministically |

## For the owner

Each item below is large, risky or already decided. A recommendation follows each one.

| Item | Recommendation |
| --- | --- |
| A broker (Kafka or similar) | Do not add one. Keep the outbox and LISTEN/NOTIFY (ADR Decision 28). Revisit with an ADR only when one of the four conditions in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 4 is measured; `MarketChangeV1` is ready for it. Sizing in doc 19 |
| TimescaleDB, Iceberg, a lakehouse | Not now (ADR Decision 24). Sizing in doc 19 |
| Native partitioning | At ADR Decision 24's trigger, with a migration rehearsal first. Sizing in doc 19 |
| pgvector | Not until a retrieval use beats lexical search on entitled evidence |
| Parquet or DuckDB research exports | When a customer or research consumer asks; the export manifest carries entitlement and snapshot |
| Temporal or another workflow engine | No; the jobs table, the outbox and P-17 cover today's workflows |
| Live model routing (follow-up planner) | No; the measured evidence says it adds latency and no feasible alternatives |
| Porting the research module into `src` | No; keep the research branch unmerged as the evidence record |
| MCP delegated identity and retiring the legacy MCP tools (C8) | Yes, as the next governance slice. It is the largest remaining agent risk the review names |
| Version-bound confirmation and second-person approval for agent writes | A confirmation token naming the capability version shown; route consequential agent writes through P-17 if any appear. Today's four confirmation capabilities are research writes (strategy freeze; shadow monitor start, pause and resume) |
| One evidence-state vocabulary | After TAR-2's source-precedence resolver, so that precedence (contracted over published, final over indicative, the clearing bank's FX over a public fixing) and evidence state are defined once |
| Cancellable capability execution | Only when a handler is measured to overrun; it needs a worker boundary |
