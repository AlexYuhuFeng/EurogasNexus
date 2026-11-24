# 14 AI by role, personal workspaces and the improvement loop

Status: design, 2026-11-24. Owner request of 2026-11-24: AI is not reliable at everything,
and trading actions are definitive, so decide for each role at which step AI takes part, how
reliable it is there and what keeps it reliable; let each role shape its own workspace,
possibly with AI help; and run a plan-do-check-act loop from a user's feedback to a reviewed
change. Related: [AI assistance](../../product/AI_ASSISTANCE.md),
[Architecture V2 section 4](../Architecture-V2/08_DECISION_APPLICATION_AI.md),
[11 quality standard](11_COMMERCIAL_QUALITY_STANDARD.md),
[13 persona review](13_PERSONA_AND_PRACTICE_REVIEW.md). Decisions are in
[08](08_DECISION_LOG.md); acceptance rows AIR-1 to AIR-14 are in
[06](06_ACCEPTANCE_CRITERIA.md).

## 1. Rules that hold for every role

The platform already follows the principle "detection is deterministic; the model explains,
summarises and drafts" ([AI assistance](../../product/AI_ASSISTANCE.md)). This document makes
it a rule per workflow step. The hard rules:

| # | Rule | How it is enforced today |
| --- | --- | --- |
| H1 | **AI never produces a number a decision rests on.** Every figure comes from canonical data through a deterministic calculation or read; the model may only repeat figures it was given, with their units. It does not add, subtract, convert, net or forecast. | `application/ai_style.py` refuses a text with any number not in the evidence; `application/grounding.py` refuses a hub, unit, direction, superlative, source or name the evidence lacks; the prompt forbids new figures (`DESK_NOTE_RULES`, `ANSWER_RULES`) |
| H2 | **AI never takes an action with an external effect.** No order, nomination, settlement, message sent, limit set, record saved or permission granted by a model. A model output is text or a proposed data document that a person accepts. | ADR Decision 11; AGENTS.md rule 8; the MCP server has no write tool (`mcp/server.py`); the agent evaluation suite asserts no execution or SQL tool exists (`tests/evals/test_agent_evals.py`) |
| H3 | **Detection is deterministic.** A rule decides that a limit is breached, a feed is stale, an outage moves supply or a cargo misses its slot; the model never decides that something happened. | Monitoring, limits and freshness services; the model only enriches an alert that already exists (`application/monitoring_service.py`) |
| H4 | **Entitlement before the model.** The model sees only what the caller may see, and runs with the caller's authority or a named service identity. | `api/dependencies/ai_authority.py` (`analysis.query`), entitlement filtering in `application/explain.py`, MCP refused in customer profiles until decision D6 |
| H5 | **The screen works without AI.** Every AI text has a deterministic fallback (the rule text); when the model is off, slow, refused by the checks or unsure, the reader gets the canonical facts and is told which one they see. | `checked_note` / `checked_answer` return `None` and the rule text stands; the response carries the basis (`model` or `rule`) |
| H6 | **No AI change ships without passing its evaluation set.** A prompt, a model id or a check change is gated by recorded cases with a pass threshold. | `tests/evals/` (110 recorded note cases for five uses, agent, analysis, editor and report-plan sets) run in CI without a model; `scripts/ai/run_note_eval.py` runs the same evidence against a provider on demand, demo or public data only |
| H7 | **No AI at the moment of commitment.** At the step where a person trades, confirms a nomination, sets a limit, approves an assumption set or grants access, AI is absent from the flow; "Why?" stays available on demand beside the figure. | Product rule from this document; today no AI surface sits in those forms |
| H8 | **Every AI call is attributable.** Who asked, for what subject, which basis was shown, under which correlation id. | `_audit` in `api/routes/public/explain.py`; enrichment under a named service identity (owner decision D7) |

Why H7: at a commitment step the person is under time pressure and the action cannot be
undone. A text that is right nineteen times in twenty is worse than no text, because the
twentieth reads exactly like the others. Explanation belongs before the decision and on
request, not in the confirmation path.

## 2. Where models are reliable, and where they are not

| Reliable enough with controls | Not reliable, so never given to a model here |
| --- | --- |
| Condensing and ordering facts it was given | Arithmetic, netting, unit and currency conversion |
| Writing those facts in EN or ZH desk language | Gas-day, time-zone and expiry-calendar reasoning |
| Classifying free text into a closed list (feedback kind, notice topic) | Deciding which contract, tariff or limit applies |
| Drafting prose a person edits (brief, hand-over, release note) | Forecasting prices, flows or ETAs |
| Proposing a structured document from a closed vocabulary (a view layout, a strategy spec) that a deterministic validator then checks | Anything whose error is silent: a plausible wrong number, hub or direction |

The right column is why the deterministic engines exist: the cargo plan, the ladder, the
gas-day balance, the limit service and the opportunity engine own their figures and are tested
against hand-worked examples ([06](06_ACCEPTANCE_CRITERIA.md)).

## 3. AI involvement map by role

Levels: **none**; **explain** (why a deterministic result is what it is, on request);
**summarise** (condense facts the platform computed); **retrieve** (retrieve with citations:
answer a question from entitled records, citing each); **classify** (put free text into a
closed list); **draft** (prose a person edits and sends); **propose** (a structured document
that a deterministic validator checks and a person approves before it takes effect).

Controls: **T** deterministic tool supplies every figure; **C** citation required, refused
without; **G** number and grounding checks with rule-text fallback; **E** evaluation set with
a pass threshold; **K** confidence or basis shown to the reader; **A** human approval before
effect; **U** audit record.

"Today" marks what exists; everything else is the target.

### Gas trader (composition `trader`)

| Step | AI | Why | Reliability risk | Controls | Today |
| --- | --- | --- | --- | --- | --- |
| Orientation: overnight prices, outages, alerts | summarise | Saves reading five panels; the facts are already computed | A wrong direction or an invented figure in the lead | T, G, E, K, U | Desk brief lead (`application/desk_brief.py`) |
| Read the board, change against close, freshness | none | Prices must be exact and current; text adds nothing | n/a | Freshness contract | Board, quote freshness |
| A price or spread moved: why? | explain | First question a trader asks, answered in place | A plausible but wrong cause | T, C, G, E, K | "Why?" (`POST /api/analysis/explain`) |
| Outage alert: what it means for my hub | explain | Turns a REMIT line into a share of supply and the position held | The model inventing the share | T (share computed by the rule), G, E, U | Alert enrichment under a service identity |
| Opportunity or spread evaluation | none for the figure; explain on request | The engine owns edge, cost and capacity | Model "improving" a number | T; "Challenge" lists assumptions only | Opportunity engine; Copilot Challenge |
| Ad hoc question ("what is my exposure to Norwegian outages?") | retrieve | One entry point, answers from Today facts | Answering beyond the evidence | T, C, G, E, K, U | Answer bar (`POST /api/analysis/ask`, `application/desk_ask.py`) |
| Decide and trade | **none** (H7) | Definitive; done on Trayport or exchange screens | n/a | Decision support only | No execution |
| Record a hedge or decision | none | A form with pickers from existing records (AGENTS.md rule 19) | n/a | Validation, audit | Hedge editor, decision cases |
| End-of-day note | draft | Every desk writes one | Tone or emphasis wrong; a figure dropped | T, G, A (the trader edits and sends) | `POST /api/analysis/brief` (kind `eod`) |

### Scheduler (role SCHEDULER, composition `operations`)

| Step | AI | Why | Reliability risk | Controls | Today |
| --- | --- | --- | --- | --- | --- |
| Gas-day clock, cut-offs, re-nomination cycles | none | Calendar arithmetic; a model gets cut-off times wrong | n/a | Deterministic calendar (QA-T-08 fixed) | Gas-day strip and checklist |
| Imbalance and cash-out | none for figures; explain on request | One gas-day definition, approved rates | Model restating a rate wrongly | T, G | Daily balance (QA-T-07) |
| TSO and REMIT notices that touch my points | classify, then summarise | Free-text notices arrive faster than they can be read | Mis-classifying a relevant notice as irrelevant | Deterministic match on point and asset ids first; the model only ranks the rest and never hides one; E with recall threshold; K | Not built |
| Record nomination status | **none** (H7) | `gas_day.record` is the scheduler's own act | n/a | Permission, audit | Built (F1-8) |
| Shift hand-over | draft | Open items, positions against nomination, acknowledged alerts | Dropping an open item | T (the open-item list is deterministic and always printed in full beside the draft), A | Not built (practice 17 in [13](13_PERSONA_AND_PRACTICE_REVIEW.md)) |

### LNG desk (composition `lng`)

| Step | AI | Why | Reliability risk | Controls | Today |
| --- | --- | --- | --- | --- | --- |
| Cargo board, slot status, next action | none | Plan figures reconcile to the import's energy | n/a | Cargo plan ([12](12_LNG_CARGO_IN_TRANSIT.md)) | Built (QA-L-05) |
| ETA changed: what moved in the hedge months | summarise | The plan diff is computed; a sentence helps | Wrong month or sign | T (plan before and after), G, E | Plan diff built; no model text yet |
| Roll and short-notice suggestions | none for the suggestion; explain on request | Due dates come from expiry calendars (QA-L-02) | Model moving a due date | T | Built with arithmetic shown |
| Read an MSPA or confirmation | propose | Extracting terms saves hours | A misread clause becomes a wrong plan input | Each extracted term cites page and clause; field-level confidence (K); nothing reaches a plan until each field is approved (A); E with field accuracy threshold; U | OCR intake only (`application/contract_intake.py`) |
| Market news on terminals and vessels | retrieve, summarise | Context, not figures | Mixing sources | C, K | Not built |
| Record hedges against a cargo | **none** | Recorded, never placed (ADR Decision 29) | n/a | Permission, audit | Built |

### Risk controller (composition `risk`)

| Step | AI | Why | Reliability risk | Controls | Today |
| --- | --- | --- | --- | --- | --- |
| Limit utilisation, breaches, stale marks | none | Controls must be exact and explainable to an auditor | n/a | Limits service, freshness | Built |
| Why is this line breached? | explain | Links breach, deals and marks in a sentence | Wrong attribution | T, C, G, E | "Why?" on credit and mandate |
| P&L and VaR explanation | explain | Narrative over a factor table | Inventing a factor | T (the factor table), G | P&L facts in `application/explain.py`; factor explain planned (practice 4) |
| "Too good to be true" review | explain (challenge) | Lists assumptions to check | False reassurance | T; the model lists checks, never clears an item | Copilot Challenge |
| Set limits, mandates, thresholds; approve assumption sets | **none** (H7) | Segregation of duties (REVIEWER) | n/a | Permission, audit | Built (F1-3) |
| What changed in limits and curves | summarise | The diff is computed and audited | Omitting a change | T (diff always listed in full), G | Audit diffs built; no model text |
| Risk report | draft | Periodic writing | Emphasis | T, G, A | Report plan and editor evals exist |

### Quant or analyst (composition `analyst`)

| Step | AI | Why | Reliability risk | Controls | Today |
| --- | --- | --- | --- | --- | --- |
| Find data, definitions and sources | retrieve | Catalogue, glossary and ontology answers | Naming a dataset that does not exist | C (catalogue ids), E | Capability search, glossary, ontology reads |
| Write code against the SDK | draft (in the analyst's own environment) | Faster first result | Wrong API use | Tested SDK examples (DOC-1); the model's code runs on the analyst's machine, never on the server | MCP read tools in development profiles |
| Draft a strategy spec | propose | Structured StrategyIR | An invalid or leaky spec | Deterministic validator (`POST /api/agent/strategy-ir/validate`), A | Built |
| Backtest | none for results; explain on request | The engine owns the numbers | n/a | T | Backtest engine |
| Research run | propose | Plans over registered capabilities | Wrong capability order | Review gate, replay, U | Agent research (`/api/agent/research`) |
| Fundamentals report | draft | Editorial standard | Figures out of evidence | T, G, E, A | Report plan and editor evals |

### Administrator (composition `platform`)

| Step | AI | Why | Reliability risk | Controls | Today |
| --- | --- | --- | --- | --- | --- |
| Feed, job and outbox health | none for state; summarise incidents | Status is deterministic (M6) | n/a | T | Built |
| Problem reports and feedback triage | classify | Kind, affected module, duplicates | A mis-routed item | Proposal only; the triager confirms (A); E with accuracy threshold | Not built (section 5) |
| Users, roles, keys, provider settings | **none** (H7) | Access changes are definitive and segregated | n/a | Permission, audit | Built (F1-9) |
| Release notes | draft | From confirmed specifications and the diff | Promising what did not ship | T (spec and merged commits), A | Not built |

### Team lead or desk head (composition `desk_head`)

| Step | AI | Why | Reliability risk | Controls | Today |
| --- | --- | --- | --- | --- | --- |
| What needs my decision | none for the queue; summarise on request | The queue is deterministic | Dropping an item | T (queue listed in full) | Today "needs me" |
| Approve a decision or hedge | **none** (H7); explain on request | Definitive | n/a | Permission, audit | Built |
| Desk P&L by book | explain | Narrative over figures | Wrong attribution | T, G | P&L facts |
| Shape a team view | propose | Section 4 | A view showing what a member may not read | Validator, entitlement at render, A (the lead publishes) | Not built |
| Read the team's feedback | summarise | Clusters by theme | Merging distinct asks | T (items linked), A | Not built |
| Weekly desk report | draft | Writing | Emphasis | T, G, A | Report drafts |

## 4. Personal workspaces

### What exists

- Preferences, a closed vocabulary per person with organisation defaults
  (`domain/settings/preferences.py`, `/api/me/preferences`): language, theme, board layout,
  time zone, reporting currency and unit, strip thresholds, focus hubs, hidden strip items.
- Role compositions in the client (`clients/web/src/app/experience/roleComposition.ts`):
  landing, a shortlist of four places, Today's row order, panel defaults (all `panels: {}`
  today), the strip audience. "View as" chooses among the person's own job functions.
  Composition never grants anything (`ROLE_COMPOSITION_GRANTS_AUTHORITY = false`).
- A panel vocabulary with disclosures (`app/experience/panelTaxonomy.ts`), a component census
  ([COMPONENT_CENSUS](../../ux/COMPONENT_CENSUS.md)), and one panel that remembers its fold
  in browser storage (`NetworkWorkspace.tsx`).

There is no saved view, no personal tab, no component catalogue a view can draw from, and no
way for a lead to share an arrangement.

### What each role may change

A **view** is a page a person arranges from catalogue components: one of their tabs. Everyone
may reorder their shortlist within the places their permissions open, reorder or fold Today's
rows, fold panels, and keep up to eight personal views. What nobody may change: how a figure
is computed, its units label, its freshness or provenance disclosure, what they are entitled
to read, and a role's **pinned** panels, which may move but not be hidden.

| Role | Typical personal views | Pinned (cannot be hidden) |
| --- | --- | --- |
| Gas trader | Two-hub spread board; my curves with my book's months | Freshness on every price row; critical alerts |
| Scheduler | One TSO's points with cut-offs; imbalance by hub | Next cut-off and overdue steps |
| LNG desk | Cargoes by terminal; hedge months by cargo | Missed and no-slot cargoes |
| Risk | Breaches and stale marks by book | Open breaches; stale-marks warning |
| Quant | Data catalogue and job status | none |
| Administrator | Feeds by region; keys expiring | Failing feeds; dead letters |
| Team lead | The team view they publish; approvals by book | Approvals waiting |

### The governed component catalogue

The catalogue extends the panel taxonomy into data, one entry per component the product
already renders:

| Field | Meaning |
| --- | --- |
| `component_id` | Stable id (`board.hub_quotes`, `cargo.board`, `limits.utilisation`) |
| `panel_kind` | From `panelTaxonomy.ts` |
| `reads` | The existing API operations it calls (no other) |
| `permission` | What the reader must hold; the component is not offered without it |
| `parameters` | A closed schema: hubs from the ontology, periods from `domain/valuation/periods.py`, books from the reader's scope, enumerations only |
| `disclosures` | What it must show (as-of, units, provenance) and cannot turn off |
| `sizes` | The slots it fits (strip, half, full) |
| `default_roles` | Compositions that show it by default; `pinned_roles` |

The catalogue lives in the client beside `roleComposition.ts`, with a parity test against the
server's permissions (as `tests/contract/test_role_composition_parity.py` does for
compositions). A new component reaches users only by being added to it in a reviewed change.

### A view is data

```json
{
  "view_id": "v-7f3a", "version": 3, "based_on": 2,
  "owner": "<principal>", "scope": "personal",
  "title": {"en": "NBP and TTF prompt", "zh": "NBP 与 TTF 近月"},
  "slots": [
    {"component_id": "board.hub_quotes", "size": "half", "parameters": {"hubs": ["NBP", "TTF"]}},
    {"component_id": "spreads.pair", "size": "half", "parameters": {"leg_a": "NBP", "leg_b": "TTF", "period": "MA"}}
  ],
  "created_with": "assistant", "validated_at_utc": "2026-11-24T09:12:00Z"
}
```

Stored in PostgreSQL in the runtime store, versioned (every save is a new version, earlier
versions kept), owned by its author. A lead publishes a view to a team scope; members see it
as an optional tab and may copy it, not edit it. **A shared view shares layout, never data:**
each component reads with the viewer's own authority at render time, and a component the
viewer may not read is shown as "not available to you" in its slot, never with the author's
data. Validation runs at save and again at render.

### "Make me a view" with AI help

1. The person types what they want ("NBP against TTF for the prompt, and my open hedges").
2. The server gives the model only the catalogue entries this person may use, with their
   parameter schemas, and asks for a view document as structured output.
3. A deterministic validator checks it: schema, every `component_id` in the catalogue, every
   parameter inside its enumeration, the person entitled to every read, slot limits, pinned
   panels kept, disclosures untouched. A failure is refused with its reason; there is no
   repair by the model behind the person's back.
4. The preview renders with live data, under the person's authority. The person accepts,
   edits or discards. Only acceptance saves version 1.
5. When the ask needs something the catalogue lacks ("show me the storage withdrawal
   forecast by site"), the assistant says so and offers to send it as a suggestion with the
   words prefilled (section 5). That is how a missing component becomes a planned change.

No code is generated or run at request time, no new endpoint is created, no formula is
accepted. The manual builder does the same without the model, so the feature works with AI
off (H5). The evaluation set holds intent-to-view cases with the expected components; the
validator is the real gate and must refuse every invalid case (100 %), while the model must
produce a valid view for at least 90 % of the in-catalogue intents.

Practice elsewhere supports this shape: terminal workspaces such as Bloomberg Launchpad are
arranged by users from a fixed set of monitors and shared with colleagues, and dashboards in
tools such as Grafana are stored and versioned as JSON documents. Nexus keeps the same idea
and adds the entitlement check per viewer.

## 5. The improvement loop (plan, do, check, act)

```text
 Plan:  capture ──► triage ──► clarify with the requester ──► change specification ──► impact analysis
                                                                                         │
 Do:    an AI coding agent implements the confirmed specification on a work branch ◄────┘
                                                                                         │
 Check: gates (tests, contract census, evals, browser sweep) ──► human review ──► requester checks a preview
                                                                                         │
 Act:   release ──► release note to the requester ──► metrics ──► standards and catalogue updated
```

### Capture

- **In product.** "Send feedback" in the account menu opens the existing report dialog in
  suggestion mode: the person's words, the page, their role composition, client and server
  versions. It is stored as a support report with category `suggestion`, priority P4, so it
  never pages the IT desk (stage 1, section 7).
- **From the product's own signals.** A "make me a view" ask the catalogue cannot meet; a
  recurring "How do I…" report (a documentation gap); a high refusal rate for one AI use
  (the evidence is too thin for that question); persona review findings in
  [13](13_PERSONA_AND_PRACTICE_REVIEW.md).

### Triage

The model proposes, a maintainer decides. Deterministic fields first (role, page, versions,
failing reads); the model then proposes the kind (defect, data, wrong figure, workflow, new
capability, documentation, configuration), the quality-standard ids from
[11](11_COMMERCIAL_QUALITY_STANDARD.md) it touches, candidate duplicates and the likely
modules from the repository map. The triager confirms or corrects; corrections are kept as
new evaluation cases for the classifier.

### Clarify with the requester

Feedback is rarely a specification. The maintainer sends at most three questions in the
person's language, in the same thread, drafted by the model and edited by the maintainer: what
they were doing, what they expected, an example with real hubs or cargoes. From the answers the
model drafts a user story and two or three acceptance examples in desk language, and **the
requester confirms them** ("yes, that is what I meant") before a specification is approved.
Their confirmation is recorded on the item.

### The change specification

Every change an AI coding agent builds starts from this template, kept at
`docs/engineering/CHANGE_SPEC_TEMPLATE.md` when stage 3 lands:

```markdown
# CS-<yyyy>-<nnn> <title>
Source: <feedback ids>; requester role: <composition>; confirmed by requester on <date>
## Goal                      one sentence, the outcome for the role
## User story                As a <role>, when <situation>, I want <capability>, so that <value>
## Current behaviour         what happens today, with page, request and evidence
## Acceptance tests          Given / When / Then, each naming the test file and test to write
## Affected modules          from the repository map: backend modules, client components, docs
## Contract impact           paths and operations added or changed; census numbers; SDK; client.ts
## Ontology impact           new concepts, dependency-key prefixes, units (or "none")
## Data impact               migration (expand only), DB_SCHEMA_REVISION, retention
## Permissions               new permission rows, segregation of duties
## AI involvement            level from section 3 and its controls (or "none")
## ADR needed?               yes when: new table group, new dependency, new service or datastore,
                             a change to a hard rule in section 1, or a cross-module contract
## Risk                      S1/S2/S3 per 11; figures a person decides on; who could be misled
## Rollback                  how to turn it off or revert, and what data remains
## Out of scope              what this change does not do
## Documentation             06, 08, 09, user docs EN and ZH, i18n keys
## Done when                 commands that must pass, and the requester's check
```

### Impact analysis

Deterministic first: the import graph (`tests/contract/test_import_boundaries.py`), module
ownership ([matrix](../../architecture/MODULE_OWNERSHIP_MATRIX.md)), the OpenAPI census
(`tests/contract/test_api_surface_stability.py`, `REVIEWED_PUBLIC_PATHS`), permissions
(`security/permissions.py`), client reachability, ontology gates and the migration contract.
A specification whose analysis touches contracts, the ontology, the schema, permissions or a
hard rule is **architectural**: it needs an ADR draft and an architecture review before any
build (AGENTS.md rule 3). Collateral improvements found on the way become their own
specifications, not part of this one.

### Do

The agent works from the specification, the repository map and AGENTS.md, in its own
worktree on a `wip/` branch, writes the acceptance tests first, and commits atomically. It may
not change a gate, a threshold, a pinned count or an evaluation case to make its change pass
(A14 in [06](06_ACCEPTANCE_CRITERIA.md)); such a change is a separate, reviewed specification.

### Check

The existing gates (`scripts/ci/pre_push_check.sh` before any push, contract and docs tests,
the evaluation sets when AI is involved, the browser acceptance sweep), then a human review of
the diff, with a second reviewer for anything in limits, valuation, the cargo plan or access.
The requester checks the change on a preview with the demo desk for their role and confirms or
reopens.

### Act

A person merges. A release note per role, in the requester's language, is drafted from the
specification and the merged commits and approved by the maintainer; the requester's item
moves to shipped and they see it under "My reports". The quality standard, the component
catalogue or the evaluation sets are updated when the change taught something general.

### Metrics that close the loop

| Metric | Why |
| --- | --- |
| Time to first response, to confirmed specification, to shipped | Lead time per stage |
| Share of items needing clarification; questions per item | Quality of capture |
| Share of specifications the requester confirms first time | Quality of clarification |
| Share of agent-built changes passing all gates first time; reopened within 30 days | Quality of build |
| Regressions traced to a specification | Escape rate |
| Use of a shipped change by the requester's role after 30 days (aggregate counts only) | Whether it helped |
| Refusal rate per AI use; "make me a view" asks the catalogue could not meet | Where AI or the catalogue falls short |

### Maintainer tooling

| Tool | What it does | State |
| --- | --- | --- |
| Feedback inbox | The support inbox with suggestion filters, kind, role, module, duplicate links, a thread with the requester and the lifecycle received, triaged, clarifying, specified, in build, in review, shipped, declined | Inbox exists for problem reports (`components/ReportProblemDialog.tsx`, `/api/support/reports`); lifecycle and thread missing |
| Specification generator | Fills the template from the item, the thread and the repository map; model prose optional | Missing |
| Repository map | A generated, machine-readable index: modules and owners, routes to handlers to domain, client components to the reads they call, ontology concepts, tests per module; a test fails when it is out of date (as `test_sdk_reference_current.py` does for the SDK) | Missing; ownership and census exist as documents |
| Evaluation harness | Recorded cases and thresholds per AI use; on-demand provider run | Exists (`tests/evals/`, `scripts/ai/`); classifier and view-composer sets missing |
| Contract census | One command printing paths, operations, permission rows and the documents that pin them, before and after a change | Spread across several tests and two release documents |
| Impact analyser | Changed files to affected contracts, roles (through the catalogue), documents and tests | Missing |
| Preview environment | The demo desk per role (demo accounts) for requester checks | Demo accounts exist |

## 6. Controls and the standards they come from

Stakes in energy trading are high, so every AI involvement is held to recognised practice. The
sources:

- NIST AI Risk Management Framework 1.0, NIST AI 100-1, 2023, functions Govern, Map, Measure,
  Manage: <https://doi.org/10.6028/NIST.AI.100-1>; and its Generative AI Profile, NIST AI 600-1,
  2024: <https://doi.org/10.6028/NIST.AI.600-1>.
- ISO/IEC 42001:2023, AI management systems (a plan-do-check-act management system with
  Annex A controls): <https://www.iso.org/standard/81230.html>.
- Regulation (EU) 2024/1689, the EU AI Act: <https://eur-lex.europa.eu/eli/reg/2024/1689/oj>.
- Federal Reserve and OCC SR 11-7, Supervisory Guidance on Model Risk Management, 2011:
  <https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm>; and the Bank of England
  PRA SS1/23, Model risk management principles for banks, 2023, which brings AI models into scope:
  <https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss>.
- OWASP Top 10 for LLM Applications (prompt injection, excessive agency, sensitive information
  disclosure): <https://genai.owasp.org/llm-top-10/>.

### Classification under the EU AI Act

Eurogas Nexus's AI uses are **not high-risk** under Article 6 and Annex III. Annex III point 2
covers AI used as a *safety component* in the management and operation of critical
infrastructure, including the supply of gas. Nexus is commercial decision support: the model
writes explanations, summaries and drafts over figures computed deterministically, and it
takes no part in operating the network, dispatching gas or confirming nominations (H2, H7).
None of the other Annex III areas (employment, credit scoring of natural persons, essential
services and the rest) applies. What does apply to the firm as a deployer: AI literacy for
staff (Article 4) and transparency that a reader is seeing AI-written text (Article 50 sets
this for specific cases; Nexus labels every model text as a matter of course). Obligations on
general-purpose models fall on their providers. The classification is to be revisited if AI is
ever placed in the nomination, dispatch or limit-setting path, or if a use profiles natural
persons. The Act's application dates are staged from 2025 to 2027 and the Commission has
proposed adjustments, so the dates are checked at each release review rather than restated here.

### Control map

| Control | Standard basis | Exists today (file) | Gap |
| --- | --- | --- | --- |
| Inventory of AI uses with owner, level, controls and evaluation set | SR 11-7 model inventory; NIST Govern 1.6; ISO 42001 A.4 resources and A.6 life cycle | Uses listed in `application/ai_eval.py` (`USES`) and in [AI assistance](../../product/AI_ASSISTANCE.md) | A single register (this document's section 3 plus a machine-readable file checked by a test) |
| Bounded tool permissions per role | OWASP excessive agency; NIST Manage 2.4; Architecture V2 section 4 | `analysis.query` gate (`api/dependencies/ai_authority.py`); read-only MCP (`mcp/server.py`); entitlement filtering (`application/explain.py`); no execution tools (`tests/evals/test_agent_evals.py`) | A per-role allowlist of the capabilities a model may call, declared beside the composition and tested |
| Deterministic calculation tools supply every figure | SR 11-7 conceptual soundness; NIST Measure 2.5 | Fact builders in `application/explain.py`, `desk_brief.py`, `desk_ask.py`; checks in `ai_style.py`, `grounding.py` | None for current uses; every new use must follow it |
| Pinned and versioned prompts and model ids | SR 11-7 change control; ISO 42001 A.6.2; NIST Manage 4.1 | Prompts are constants in `application/ai_style.py` (versioned by git only); the model id is installation configuration and a caller cannot override it (`llm/deepseek.py`, `llm/provider.py`) | A prompt version id and the model id recorded with every call and every evaluation report |
| Reproducible outputs on evaluation sets with pass thresholds gating any prompt or model change | SR 11-7 validation and outcomes analysis; NIST Measure 2.1 and 2.3; NIST AI 600-1 | Recorded sets in CI (`tests/evals/test_ai_note_evals.py`, every bad note refused, every faithful one passed); provider run on demand (`scripts/ai/run_note_eval.py`); low temperature (`NOTE_CALL`, `ANSWER_CALL`) | A recorded provider-run threshold per use that a prompt or model change must meet before merge; the run report committed as evidence |
| Independent validation | SR 11-7; PRA SS1/23 principle 4 | Evaluation cases are written apart from the prompts and reviewed | A second reviewer who did not write the prompt signs off each new use (departure recorded in [08](08_DECISION_LOG.md)) |
| Ongoing monitoring | SR 11-7 ongoing monitoring; NIST Manage 4.1 | LLM monitoring ([LLM_MONITORING](../../operations/LLM_MONITORING-EN.md)); basis recorded per call | Refusal rate and fallback rate per use as metrics with alert thresholds |
| Audit trail of inputs, tool calls, outputs and approvals | ISO 42001 A.6.2.8 event logs; NIST Measure 2.8; EU AI Act Article 12 (as good practice) | `_audit` in `api/routes/public/explain.py` records principal, subject, basis and correlation id; agent runs are replayable (`/api/agent/runs/{id}/replay`) | Evidence hash, prompt version, model id and output hash on each AI audit row; approvals of proposed documents |
| Human approval for consequential steps | NIST Manage 2.4; ISO 42001 A.9; EU AI Act Article 14 (as good practice) | No AI in commitment steps (H7); research runs and StrategyIR pass a review gate | Approval records for view documents, extracted contract terms and triage decisions as they are built |
| Kill switch per AI feature and per tenant | NIST Manage 2.4 (supersede, disengage or deactivate); SR 11-7 change control | One global switch: `EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED`, forced off in trial and release environments (`core/config.py`); per person through the `analysis.query` permission | A switch per use (explain, brief, answer, enrichment, report, view composer, triage) in organisation settings, audited; an installation is the tenant (one customer per installation), so the installation switch is the tenant switch |
| Graceful fallback when AI is unavailable, unsure or refused | NIST Measure 2.6 (fail safely) and Manage 2.4; NIST AI 600-1 | Rule text stands and the basis is shown (`checked_note`, `checked_answer`) | Keep for every new use; the view composer falls back to the manual builder |
| Transparency to the reader | EU AI Act Article 50; NIST Measure 2.8 | The panel says whether the reader sees model text or the rule | Same label on every new use and in exported reports |
| Data governance before the model | ISO 42001 A.7; NIST Map 4 | Entitlement filtering; identifiers removed (`application/ai_payloads.py`); provider run only on demo or public data | None for current uses |
| Management system (plan, do, check, act) | ISO 42001 clauses 4 to 10 | Programme documents 00 to 13 | Section 5 of this document |

## 7. Gaps against today, and the plan

| Gap | Where it shows today |
| --- | --- |
| No way to send a suggestion in product (closed by stage 1: category `suggestion`, "Send feedback") | `api/routes/public/support.py` categories; `components/ReportProblemDialog.tsx` |
| Feedback lifecycle stops at open, acknowledged, resolved; no thread with the requester | `SupportReportUpdate` in `support.py` |
| No change specification template, generator, repository map or impact analyser | `docs/engineering/` has RFC and ExecPlan templates for people, none for agents |
| Compositions are hard-coded in the client; panel defaults empty; no saved views or component catalogue | `roleComposition.ts` (`panels: {}`), `panelTaxonomy.ts` (descriptive only) |
| One global AI switch; no per-use switch | `core/config.py` |
| AI audit rows carry no prompt version, model id or evidence hash | `_audit` in `api/routes/public/explain.py` |
| No per-role model capability allowlist | `api/dependencies/ai_authority.py` checks one permission for all uses |
| No provider-run threshold gating prompt or model changes | `scripts/ai/run_note_eval.py` reports but does not gate |

### Stages, in build order

| Stage | Slice | Why this order |
| --- | --- | --- |
| 1 | Suggestions through the existing support reports: category `suggestion`, P4, no new path; "Send feedback" in the account menu; composition in the client diagnostics. **Built** (AIR-1, AIR-2) | Capture first, at no contract cost |
| 2 | AI register and controls: a machine-readable register of AI uses (level, roles, controls, evaluation set, threshold), a per-use switch in organisation settings, prompt version and model id on audit rows and evaluation reports | Makes every later AI use safe by construction |
| 3 | Feedback lifecycle and thread (statuses clarifying, specified, in build, shipped, declined; requester confirmation), the change specification template, the repository map with its currency test, the contract census command | The loop needs states and an executable specification before agents build from it |
| 4 | Component catalogue as data with its parity test; saved views (manual builder), versions, team publishing by a lead | Personalisation without AI first |
| 5 | "Make me a view" with structured output, validator and evaluation set; catalogue misses become suggestions | AI only on top of a validated manual path |
| 6 | Triage classifier and release-note drafter with evaluation sets; loop metrics in the maintainer inbox | AI in the loop once its records exist to learn from |

Stage 2 needs an ADR entry only if the register adds a table; stages 3 and 4 add tables and
paths, so each carries its contract census updates and an ADR entry for the new table group.
No stage adds a service or a datastore.
