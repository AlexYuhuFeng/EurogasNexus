# W7-01 — Canonical AI Actions as Product Surface

Status: **delivered (Wave 7, first slice)**. Authority:
[04_PRODUCT_EXPERIENCE_ARCHITECTURE.md](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md) sections 6 and 7,
[08_DECISION_APPLICATION_AI.md](08_DECISION_APPLICATION_AI.md) section 4, and the Wave 1 contracts
[W1-03](W1-03_INSPECTOR_AI_AND_COMMAND_CONTRACT.md),
[W1-05](W1-05_CANONICAL_EXPERIENCE_SPECS.md) and
[W9-01](W9-01_SHELL_SURFACES_INSPECTOR_AND_PALETTE.md).

## 1. What this slice does

Wave 1 declared Ask / Explain / Compare / Challenge / Draft and the boundary they inherit; Wave 9
mounted the command palette but deliberately kept the five actions out of it, "until their invocation
surface exists (Wave 7), so no command is offered that would do nothing". This slice is that
invocation surface.

| Element | Before | After |
|---|---|---|
| The five canonical actions | contract only (`aiActions.ts`), offered by no running surface | invoked from the Copilot surface, with posture, output and evidence shown before the run |
| AI command in the palette | derived but filtered out at runtime | offered, and it opens the Copilot instead of doing nothing |
| Evidence requirement | a guard with no caller | the gate: no evidence reference means no action, with the reason shown |
| Output | unqualified | labelled interpretation, `research_only` / `human_review_required` kept visible, no numeric authority |

No page, route, API, permission, schema or numerical behaviour changed.

## 2. Shape

- `clients/web/src/app/model/copilotModel.ts` — **pure model**. Availability gating
  (`copilotOffers`, `availableCopilotActions`), canonical context and evidence resolution,
  request composition (`composeCopilotRequest`), output qualification
  (`qualifyCopilotOutput`) and the run record (`copilotRunRecord`). No React, no fetch, no
  credential, and no arithmetic.
- `clients/web/src/app/hooks/useCopilot.ts` — **thin controller**. Run state for one action, and
  `useCopilotSources()` for the context the run would use. The transport is injected
  (`runAnalysis`), so the hook names no endpoint.
- `clients/web/src/components/CopilotPanel.tsx` — `CopilotPanel` (presentational: it renders the
  controller and calls back) and `CopilotHost` (the container a shell mounts: it resolves the
  context, runs one controller and passes `api.analysisQuery` as the transport).
- `clients/web/src/components/copilot-panel.css` — layout only, reusing the shipped surface tokens.

**Where it mounts.** V2 doc 08 section 4 fixes "AI is cross-workspace, not a separate island", and
the V2 rule "a new capability does not automatically earn a new page" forbids a navigation entry.
The Copilot is therefore a surface inside the Wave 9 command palette overlay — the shell element
that is already reachable, with Ctrl/Cmd+K, from every workspace. Escape dissolves the innermost
surface first: the Copilot returns to the command list, a second Escape closes the palette.

## 3. The five actions, and what is withheld

`copilotOffers` returns exactly `AI_ACTION_KINDS`, in contract order, and never a sixth action.
Each offer shows, before the user invokes it:

- the action label (the Wave 1 `experience.ai.*` vocabulary);
- its **posture** (`interpret-only`, `evidence-backed-draft`, `evidence-backed-review`);
- **what it produces**, taken from the Wave 1 contract wording — the English i18n value is asserted
  equal to `aiActionContract(action).produces`, so the surface and the contract cannot drift;
- the **evidence references it will carry** into the run.

An action is offered only when `aiActionIsAvailable(action, { activeContextComplete, evidenceRefCount })`
holds: the Active Context is complete **and** at least one evidence reference exists. Absence of
evidence is a reason to withhold, never a reason to let the model guess. Withholding is explained,
not silent: `experience.copilot.withheld_context` / `..._withheld_evidence`, and the same rule is
applied to the palette command (`PaletteAvailability.evidenceRefCount`, new reason key
`experience.palette.unavailable_evidence`).

## 4. The run

A run uses the backend capability that already exists: `POST /analysis/query`, exposed to the client
as `api.analysisQuery`. No endpoint, route, permission or provider call is added, and the client
never calls a vendor API or the database.

The question is composed in the model and is what the backend receives and persists as the run's
prompt snapshot:

```text
[EXPLAIN] <the user's question, or the action's contract framing>
Context: workspace network, gas day 2026-09-16, product day-ahead, hub NBP
Context key: network|2026-09-16|day-ahead|NBP|ROUTE-9|-|-|-|-
Evidence references: route:ROUTE-9, resource:RES-1
```

| Request field | Value | Why |
|---|---|---|
| `question` | composed as above | the run is observable: action, context, key and references travel with it |
| `task` | `DB_INQUIRY` | all five actions are questions over one governed snapshot; a task kind per action would be a backend contract change, and `DB_INQUIRY` fabricates no missing-input claim |
| `invoke_provider` | `true` | invocation is the deliberate step; the backend still re-authorises and fails closed before any provider call |
| `language` | `zh-CN` or `en` | the interface language decides the answer language |
| `selected_assets` / `selected_contracts` | the evidence references | identities only, never values; the backend re-authorises each one |
| `selected_terms` | empty | no glossary term is invented on the user's behalf |

The surface shows the route it will use, so the invocation is not a black box.

## 5. Output qualification

`qualifyCopilotOutput` turns the response into something a reviewer can trust:

- `interpretation: true` and `numericAuthority: "none"` — deterministic engines own calculations,
  optimisation and PnL truth; the surface adds no metric and restates no figure as authority;
- `researchOnly` / `humanReviewRequired` are the union of the response body and the response `meta`,
  so either one reporting the flag keeps it visible (fail closed);
- the provider status is shown, and a run where the provider was not invoked says that the text is
  the deterministic backend summary rather than a model interpretation;
- the analysis snapshot reference the run reports stays visible;
- citations, missing inputs and warnings are kept, including envelope warnings;
- failures are explained through the Wave 8 error taxonomy (what happened, impact, cause, recovery,
  correlation id), never as a raw status.

## 6. Boundary (non-negotiable)

`COPILOT_BOUNDARY` is derived from the Wave 1 `AI_INVARIANTS` rather than restated, so the two cannot
drift:

| Invariant | Value |
|---|---|
| interpretation only | `true` |
| numeric authority | `"none"` |
| inherits the invoking user's authority | `true` |
| may widen entitlement | `false` |
| may invent missing data | `false` |
| may execute or nominate | `false` |
| stores hidden reasoning | `false` |
| requires re-authorisation per call | `true` |

There is no trade execution, no order entry, no nomination and no settlement anywhere in the flow:
the run produces interpretation and draft text for a named human, and a run is recorded as an
observable action (what was asked, on which context, with which references, over which route) with
no field for a reasoning trace.

## 7. Context and evidence: canonical reads, never a second owner

`useCopilotSources()` resolves the Active Context and the evidence references for the surface. It
reads the same canonical sources the Active Context owner reads — the URL context keys and the
persisted trader preference, through `app/context/contextUrl.ts` and
`app/context/contextPersistence.ts` (pure resolvers; the persistence reader is passed in, so the
model stays testable without a browser). It is a *read* of the canonical context: a shell that
already holds the context passes its own `sources`, or mounts `CopilotPanel` with its own
`useCopilot` output, and no ambient read happens.

Context is not authority, and gaps are named rather than papered over: the surface prints the
context key and the open Active Context gaps (organisation, portfolio, decision case, analysis
snapshot), and it does not claim reproducibility from the context alone while the Analysis Snapshot
is not attached to it.

## 8. Palette changes (additive)

- `PaletteAvailability.evidenceRefCount` is **optional**: a caller that does not pass it keeps the
  previous gate (capability plus context), which is why the Wave 9 palette tests still hold.
- AI commands are offered by default (`includeAiActions !== false`) because their invocation surface
  now exists: either the Copilot this palette mounts, or a handler the host supplies through
  `onAiAction`. `false` remains the explicit opt-out, and the optional `aiSurface="host"` prop tells
  the palette to defer to a host-owned surface.
- The palette explains a withheld AI command with `experience.palette.unavailable_evidence` when the
  host cannot see evidence references.
- W9-01's statement that AI actions stay out of the runtime palette "until their invocation surface
  exists (Wave 7)" is now satisfied; that document is not edited by this slice, and the Wave 9
  palette test assertion that pinned the temporary condition was updated to pin the delivered one.

## 9. Compatibility

- No route, deep link, page id, navigation or workspace composition changed.
- No API, schema, permission, numerical, release or DR behaviour changed.
- New user-visible vocabulary is bilingual (`en`, `zh-CN`), and the surface adds no colour, type or
  motion family.
- `aiActions.ts`, `commandPalette.ts` and the experience barrel keep every existing export and its
  behaviour; the palette availability extension is optional.

## 10. Verification

- `clients/web/tests/copilotActions.test.ts` — nine cases: the five canonical actions with posture,
  output and evidence; withholding without a complete context or without evidence (and parity with
  `aiActionIsAvailable` for every combination); canonical context resolution and its precedence;
  request composition onto the existing route; output qualification including fail-closed flags and
  the not-invoked case; the run record as an observable action; the product boundary and the
  "client calls `/api` only" rule; palette reachability with no AI command that would do nothing; and
  bilingual vocabulary (including every literal `t("...")` key the surface renders).
- `clients/web`: `node --test "tests/*.test.ts"` — **331 passed, 0 failed**;
  `npx tsc --noEmit` — exit 0; `npm run build` — exit 0.
- Repository contracts: `tests/contract/test_markdown_links.py` and
  `tests/contract/test_docstring_policy.py` pass; the client release-surface and architecture fitness
  contracts were re-run because this slice touches their scan scope.

## 11. What this slice does not claim

- **No dedicated backend task kind per action.** That would be a backend contract change; the five
  actions run `DB_INQUIRY` today.
- **No convergence of the `/agent/*` research surfaces.** Those remain untouched here; converging
  them is follow-up work in the files that own them (the research run's own convergence is
  recorded in section 14).

## 12. Convergence follow-up delivered

`clients/web/src/components/AlertCenter.tsx` carried an ad-hoc provider-branded question button that
was not one of the five canonical actions and applied no gating at all - an alert with no evidence
reference could still be sent to a model. It now runs the declared **`ask`** action:

- the button is the action, labelled from `experience.ai.ask`, and it is **withheld** unless
  `aiActionIsAvailable("ask", ...)` holds for the alert's own `source_refs`, so an alert without
  evidence withholds the action (and the discussion surface with it) instead of letting the model
  guess;
- the surface shows the contract's posture and produces copy, and the evidence references it will
  carry into the run, before the question is asked;
- the client no longer names a vendor: the stored summary and the run result are labelled with the
  provider the backend reports (`llm_provider_id`, `provider_id`), and the answer is labelled as
  interpretation with no numeric authority, using the Copilot's vocabulary rather than a second one.

This pairs with the backend half of finding C8: the alert-analysis route now re-authorises the
invocation against the caller's own `analysis.query` capability, so the surface and the route agree
about whose authority an alert question runs under.

## 13. The Copilot gets a workspace home

The palette was the only entry point, which made the Copilot a shell facility rather than part of the
work. The market cockpit's context rail now carries the five canonical actions:

- they come from the one registry (`copilotOffers`), so no sixth action can appear and no label can
  drift from the contract;
- the context and evidence come from the canonical sources the palette uses
  (`useCopilotSources` with the selection the surface already holds), so a run started here carries
  what the panel shows rather than a second reading of the Active Context;
- each action is gated by the offer the contract produced, and a withheld action explains itself on
  the control instead of opening a panel that refuses it;
- choosing one mounts the hosted Copilot, which owns the transport; the cockpit names no endpoint.

A workspace that wants the surface inline follows the same pattern. The review task took it one step
further: its own analysis panel carried a free-text question box and an invoke-the-provider switch,
which made a sixth AI surface beside the canonical five. Those controls are gone - the five actions
live there instead, and what remains of the panel is the deterministic portfolio report, whose
question is no longer user-typed. AI-drafted output is the `draft` action's job, which is what the
panel's own copy now says.
- **No conversation, thread or history model.** A run is one action on one context; the backend
  persists the analysis it produced, and the surface shows the run record it composed.

## 14. The governed research run converged

The `/agent/*` research surface could always start a run, but it decided almost nothing about it,
and what it did decide it decided dishonestly:

- the run button was enabled for any non-empty objective while `POST /api/agent/research` requires
  an objective of 8 to 4000 characters, so a three-word objective was offered and then refused;
- the route answers 503 without a configured runtime PostgreSQL - the run persists its plan,
  findings and job record - and the surface did not check, so it offered a run that could only fail;
- the request named `STRATEGY_RESEARCHER` itself, making the client the author of a governance
  label that is recorded on the run and scopes its tracked job;
- asking for strategy generation said nothing about what it does: freezing a StrategyVersion and
  backtesting it are human acts, so such a run terminates at `READY_FOR_HUMAN_REVIEW` with
  `HUMAN_CONFIRMATION_REQUIRED` rather than reaching a backtest.

`clients/web/src/app/model/agentRunModel.ts` now holds the rule (objective bounds mirrored from the
route's own request model, the runtime-database precondition, the in-flight state, the request
composition and the disclosures), and the surface is wired to it:

- the action is the workspace's **primary** action - a `compute` consequence - disabled by the same
  readiness rule the panel lists, with the first blocker as its explanation;
- the panel keeps the objective, the strategy switch and the verdict: every unsettled precondition,
  plus what the run will do (`agents.strategy.*`) and the two things that hold for every run (the
  plan's analyses are validated against the caller's own data scopes, and the profile is recorded by
  the runtime rather than chosen here);
- the request no longer names a profile, and sends no `strategy_ir`, frozen version or period
  bounds: the route's declared default profile applies, and the surface shows the profile the run
  records. If profiles ever become behaviour-bearing rather than declarative, offering the choice
  becomes honest and this is the note that says so;
- the tracked run stays readable: the run is read back from `/api/agent/runs` after it starts, and
  the replay, artifact chain and review gate are unchanged.

This is convergence onto the same governance rules the five canonical actions follow, not a sixth
AI entry point: the run is a governed, deterministic research pipeline that invokes registered
capabilities under the caller's own authority, and the surface reports the provider and model the
run record carries rather than branding it.

Still open in the `/agent/*` family: the capability-invoke surface (`/api/capabilities/{id}/invoke`)
has no client surface, and the profile catalogue is fetched by nobody - a client-chosen profile
would be a label, not a capability, until the orchestrator executes the profile's declared stages.
