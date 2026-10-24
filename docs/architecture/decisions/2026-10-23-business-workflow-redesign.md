# Business workflow redesign: decision objects before screens

Status: candidate design under capability and workflow validation, responding to
the owner's 2026-10-23 redesign instruction. The owner explicitly requires preserving
the existing project's rigor and considering changes before implementation. This
is not an approval to replace validated architecture or numerical contracts.
It refines Architecture V2's user-task-first and shared-context contracts. Existing
business scope, numerical versions, privacy, licensing and release gates remain.

## Why the current foundation must change

The owner rejected incremental screen repair as the primary development method.
The product must be evaluated by completed professional decisions, not component
count, successful API calls, absence of overflow, or the number of passing tests.

Current source evidence:

1. `app/navigation/productNavigation.ts` makes the network map the Market landing
   task. A trader's first question may instead concern a deadline, exposure, price
   move, blocked resource or pending decision. A static feature default is not a
   work queue.
2. `domain/strategy_lab/evaluation.py` scores the intraday/day-ahead spread with a
   fixed five-GBP scale and produces paper allocations to ICE_OCM and DAY_AHEAD.
   This is a specific model. It must not acquire general index/spread-strategy
   claims through changes to labels, enum values or controls.
3. `app/model/strategyResourceHandoff.ts` deliberately carries identity/quantity,
   not inferred all-in cost. This is correct economically, but the user still has
   to reconstruct analysis inputs. The redesign needs explicit versioned bindings
   and a cost-stack owner, not another copy of a contract form.
4. `app/experience/activeContext.ts` still declares organization, portfolio,
   decision-case and analysis-snapshot as context gaps. Existing backend objects
   must be mapped before expanding client context; no parallel frontend ledger.
5. Actual acceptance21 proves one synthetic contract/research/review path. It
   does not prove tender, position-ledger, independent approval, generic strategy,
   or production trading support. Navigation must not imply those capabilities.

## Product and decision boundary

Eurogas Nexus is a gas commercial decision-support and research workstation.
Users prepare, compare, challenge and record decisions. The application does not
execute trades, amend counterparty agreements, submit nominations, settle payments
or claim a live position book without a reconciled ledger. Research results remain
research results until an explicitly supported commercial model consumes them.

A business question owns its workflow. A technical module never earns a new page
merely because it exists. Existing routes remain compatibility entry points while
task composition changes.

## Personas, responsibility and completion

| Work context | Trigger and question | Main workspace content | Completion artifact |
| --- | --- | --- | --- |
| Trader / commercial operator | A market move, delivery deadline or resource decision: what can I do, by when, with which constraints? | Prioritized work queue; selected resource/exposure; feasible alternatives with incremental economics; blockers and deadline | Saved decision case with selected alternative, rationale, exact inputs and review state; no execution claim |
| Portfolio manager / structurer | How do obligations and scenarios affect available energy and cash? | Versioned resource/obligation register, valuation scenario, dated cash and stress comparison | Versioned commercial scenario and evidence-backed comparison; no inferred remaining position |
| Analyst / quant | Does a stated hypothesis hold on admissible data under declared assumptions? | Instrument/series discovery, expression and signal specification, datasets, experiments and comparable runs | Frozen research definition plus reproducible run and limitations; PRIVATE by default |
| Risk / reviewer | Is this proposed decision supported, within constraints, and independently reviewable? | Assigned cases; proposed action and material differences; frozen evidence, sensitivity, policy exceptions | Actor-bound review referencing exact case/run version; own assessment distinct from independent approval |
| Data operator | Which data failure invalidates which decisions? | Freshness/quality/coverage incidents, affected series/cases, ingestion lineage and recovery actions | Resolved or acknowledged incident with impact and audit evidence |
| Administrator | Who may access which objects and data, and is the deployment healthy? | Identity/group/entitlement management, deployment health and audit | Authorized configuration change with audit; no implied commercial entitlement |

Persona changes presentation, never authority. One user may hold multiple
assignments. Mode switching must retain drafts and explicitly ask whether the
working decision should change; it cannot silently reset the business context.

## End-to-end work contracts

### Commercial decision

1. Open a queue item or choose a business question, resource and delivery period.
2. Bind exact resource/contract versions and admissible market observations.
3. Review missing inputs and explicit assumptions. Missing is never zero.
4. Compare feasible alternatives on the same valuation instant, quantity,
   currency and cost treatment; blocked alternatives retain their reasons.
5. Inspect economic margin, dated cash, financing and sensitivity separately.
6. Save a decision case. Submission for review freezes the material evidence.
7. A reviewer challenges, returns or records an assessment. Material input
   changes create a new revision; historical evidence is not overwritten.

### Research strategy

1. State the hypothesis and choose a supported research model.
2. Bind typed instruments/series; define each leg's sign, weight, unit, delivery
   period, source constraints and availability. A display name is not an ID.
3. Define a signal separately from sizing/allocation and risk constraints.
4. Choose historical coverage and validation split; declare costs, fill policy,
   time conventions and data quality. Show refusals before starting a run.
5. Freeze the definition and run; compare only compatible experiments.
6. Explain results, warnings and attribution; fork to iterate.
7. Owner explicitly chooses private, public-read or group-read sharing.
   Publication never grants underlying market-data rights.

Single-price signals, two-leg location/time/basis spreads and multi-leg weighted
expressions are separate model capabilities. A price expression is not a trading
strategy. A trading strategy is not a physical allocation model. Unsupported
models must remain unavailable until domain semantics and numerical acceptance
exist; the legacy OCM model remains versioned and readable.

### Review and operations

Review starts with the proposed decision and what changed, not a raw list of
runs. Data operations starts with affected business work, not connector settings.
Administration is a separate control plane. No reviewer or admin bypasses an
owner's strategy privacy or data licensing through an inspector, export or job.

## Domain ownership and data contracts

| Domain owner | Owns | Must not own |
| --- | --- | --- |
| Market/reference data | Stable instrument/series identity, venue/product specifications, observations, quote side, availability/delivery times, provenance and entitlements | User strategy, positions or executable-liquidity claims from indices |
| Commercial resources | Versioned agreements, resource declarations and rights/obligations | Invented remaining inventory or inferred binding legal changes |
| Economics | Units/FX, cost-stack treatment, dated cash, valuation and feasible alternatives | Frontend-calculated commercial totals or hidden defaults |
| Research | Typed hypothesis/expression/signal/model definitions and immutable versions | Rebranding legacy allocations as arbitrary strategies |
| Evaluation | Explicit model-version execution against frozen point-in-time inputs; attribution | Mutating source records or retroactive outcome changes |
| Decision/review | Case revisions, evidence links, responsibility, assessment history | Permission grants or implied external execution |
| Identity/governance | Effective authority, owner/group visibility, audit and data rights | Persona-driven privileges |
| Client application | Task composition, selection, drafts, presentation and host capabilities | A second business engine or parallel authoritative domain objects |

Within the current modular monolith, application services orchestrate these
owners. Retain PostgreSQL/Alembic, FastAPI, React and Tauri unless evidence supports
a specific replacement. No speculative distributed infrastructure is required.

Every run must bind model/version, typed input snapshot, explicit assumptions,
valuation instant and delivery basis, data references and authorization boundary.
Every result exposes status/limitations, attributable quantities, units and economic
meaning. Every review binds an immutable subject. Canonical services calculate;
API, SDK and UI consume the same contracts. Regional exchange remains disabled.

## Information architecture and interaction design

- A persistent workstation frame provides work mode, task navigation, active
  decision/research context, search/commands, activity and identity.
- The primary work area follows the task: queue, compare, investigate, design or
  review. Maps are investigation views, not a universal starting point.
- A shared inspector shows selected object terms, provenance and relationships;
  opening it does not change the underlying task or working snapshot.
- Active context states what changes all linked panels and what is a local filter.
  Changing it invalidates or visibly marks prior results; completed runs stay fixed.
- Progressive disclosure follows business dependencies: required decision inputs
  first; model assumptions, data mapping and advanced controls beside their impact.
- Matched selectors show identity, coverage and compatibility; free text is reserved
  for rationale, notes and genuine user-defined names, not canonical instruments.
- Comparison tables use common units/periods and comparable columns. No decorative
  metrics, unexplained scores or panels that look complete when input is absent.
- Windows/Linux keyboard conventions are primary. Commands share availability
  rules with visible actions. Focus, drafts and selection survive task navigation.
- Accessibility is part of acceptance: keyboard-only completion, explicit labels,
  visible focus, non-color statuses, readable density and responsive reflow.

Visual references open-Claude-ui and diip3sh inform restraint, hierarchy and
interaction consistency. They do not supply gas economics or regulatory design.
Previously recorded vendor benchmark notes are dated research; no current vendor
certification or claim of industry consensus is inferred from them.

## Migration and acceptance

This is a coherent redesign implemented through vertical workflows, not a
big-bang deletion of validated behavior or a sequence of unrelated cosmetic fixes.

1. Reconcile current capabilities with the business journey matrix. Record actual
   implementation, verified behavior, limitations and unsupported business claims.
2. Establish canonical decision/research context and object lineage. Reuse existing
   snapshot, case, strategy and resource versions; resolve stale adapters/gaps.
3. Implement the new shell and trader decision workflow, with existing routes as
   adapters. Validate one whole workflow against both API and SDK.
4. Implement research design against explicit supported model contracts, then
   reviewer/operations compositions. No fake enabled model choice.
5. Apply the shared interaction/component system to remaining workflows; retire
   redundant surfaces only after their supported tasks have a verified home.
6. Run representative populated and empty/stale/denied workflows for each persona
   in EN/ZH, Windows/Linux key conventions, browser and native Linux. Verify data
   consistency, numerical examples, privacy, draft safety and meaningful review.

Completion requires outcome-based acceptance, not just a visual redesign. Existing
release gates still govern published delivery. Changes to model economics require
new versions and independent expected-value cases; historical results remain
reproducible. A fixed feature navigation or map-first landing is a hypothesis to assess against
actual tasks, not grounds by itself to discard the existing architecture. Any
accepted-architecture change needs explicit rationale, compatibility mapping and
verified outcome before it is adopted.

## Preservation and change control

Classify every finding before choosing a remedy: (1) implemented but poorly
presented, (2) implemented services with incomplete workflow integration,
(3) unsupported capability, or (4) evidenced semantic/architectural defect.
Do not treat an old inventory or missing UI as proof of a missing backend.

For each proposed change record business evidence, current implementation,
smallest coherent remedy, reused capabilities, affected contracts and stored data,
permission/entitlement impact, numerical-version implications, migration/rollback
and positive/negative acceptance cases. Prefer no schema change when composition
solves the problem. Preserve immutable historical definitions and results.
Security, temporal integrity, numerical correctness, source licensing and audit
are acceptance gates, not tradeoffs for a cleaner interface. User caution does
not introduce a new blanket permission request for ordinary reversible work.
