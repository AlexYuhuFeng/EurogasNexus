# W1-05 — Canonical Experience Specifications

Status: **delivered specifications (Wave 1)**. Authority: Architecture V2
[04_PRODUCT_EXPERIENCE_ARCHITECTURE.md](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md) sections 2, 3, 9, 13 and 15,
[03_TARGET_PLATFORM_ARCHITECTURE.md](03_TARGET_PLATFORM_ARCHITECTURE.md) sections 3-5, and
[08_DECISION_APPLICATION_AI.md](08_DECISION_APPLICATION_AI.md) section 1.

These are the five representative experiences Architecture V2 names: **Trading Analysis**,
**Portfolio Oversight**, **Research**, **Decision Case** and **Administration**. They are the
acceptance surface for the Wave 1 contracts: every element below is expressed through the shipped
vocabulary (`workModes.ts`, `workspacePatterns.ts`, `panelTaxonomy.ts`, `inspectorContract.ts`,
`actionGeography.ts`, `aiActions.ts`, `commandPalette.ts`).

No design tooling was used and no structure was invented: each specification maps onto pages and
capabilities that already exist (evidence in [W0-01_CLIENT_INVENTORY.md](W0-01_CLIENT_INVENTORY.md))
or names the wave that will deliver the missing part.

The shell in every specification is the canonical shell
([W1-01](W1-01_SHELL_AND_ACTIVE_CONTEXT_CONTRACT.md)):

```text
┌──────────────────────────────────────────────────────────────────┐
│ Global context: gas day · product · hub · search · status · user │
├──────────┬────────────────────────────────────────┬──────────────┤
│ Nav      │ Primary workspace                      │ Inspector    │
│ (domains)│ (pattern composition)                  │ (planned)    │
├──────────┴────────────────────────────────────────┴──────────────┤
│ Activity / jobs / evidence / notifications  (partial: Wave 8)    │
└──────────────────────────────────────────────────────────────────┘
```

## 1. Trading Analysis

**User question:** "Where should this gas day's resource go, and what does the physical system
actually allow?"

| Element | Specification |
|---|---|
| Work mode | `trading-analysis` (emphasis: market → portfolio → decision) |
| Entry | Market primary, `network` page — pattern `EXPLORE` (map-first) |
| Secondary | `market` `MONITOR` (curves/overview), `capacity` `ANALYSE`, `portfolio` `CONFIGURE` (contracts), `decision` `CONFIGURE` (scenario) |
| Panels | `map`, `context-summary`, `metric-strip`, `run-result`, `warnings`, `evidence` |
| Inspector subjects | `network-node`, `route`, `capacity` |
| Primary action | run the pool/scenario computation (`compute` → workspace-primary) |
| Local actions | map layers, search, capacity filters (`read` → surface-local) |
| Guarded actions | none: this mode has no lifecycle or destructive action |
| AI actions | `explain` (why this route), `compare` (alternatives), `challenge` (assumption check) |
| Minimum navigation | 1 route change: land on `network`, work the pool there; contract entry and scenario remain reachable without leaving the domain |

Flow: **context** (global row) → **evidence** (map + capacity + market marks on one gas day) →
**action** (run) → **result** (allocation, warnings) → **persisted artefact** (review evidence,
Wave 6 Decision Case).

States that must exist: loading (map geometry, market marks), empty (no portfolio resources → the
run action is gated, with the reason shown), degraded (stale market marks with time basis shown),
restricted (a source family the identity is not entitled to shows a restricted state, never a silent
zero).

Reproducibility: the result panel MUST show the Active Context key and MUST NOT claim reproducibility
while the Analysis Snapshot gap is open (Wave 4).

Desktop value: persistent workspace and native notifications on a completed run
([W1-04](W1-04_HOST_CAPABILITIES_CONTRACT.md)); no business logic on the host.

## 2. Portfolio Oversight

**User question:** "What is the portfolio exposed to, what is stale, and what needs a decision?"

| Element | Specification |
|---|---|
| Work mode | `portfolio-oversight` (emphasis: portfolio → decision → market) |
| Entry | Portfolio primary, `contracts` page — pattern `CONFIGURE` for entry; `orders` (`ANALYSE`) for read-only positioning |
| Secondary | `decision` `REVIEW` for the decision queue |
| Panels | `metric-strip` (headline exposure), `table` (positions/contracts), `time-series` (PnL), `warnings` |
| Inspector subjects | `contract`, `resource`, `market-observation` |
| Primary action | save/validate the reviewed contract draft (`persist` → workspace-primary) |
| Local actions | task tabs (overview/resources/routes/exposure), table filters and sorting |
| Guarded actions | none in this mode today; contract retirement, when it exists, is `lifecycle` → object-overflow |
| AI actions | `explain` (exposure drivers), `challenge` (assumption review before saving) |
| Minimum navigation | 1 route change: land on the portfolio domain; exposure, resources and routes are task tabs, not separate pages |

Flow: **context** (portfolio scope is a Wave 5 gap; today the gas day/hub context stands in) →
**evidence** (position table + PnL series with as-of) → **action** (validate/save or escalate to
review) → **result** → **artefact** (review evidence).

States: stale portfolio (freshness must be visible per slice), incomplete contract (validation
blockers shown before save), restricted (a licensed source family renders as restricted).

Known current-state risk to keep visible: the `orders` page id resolves to the Overview task on a
bare `?workspace=orders` deep link ([W0-01](W0-01_CLIENT_INVENTORY.md) section 2.4). The target
model removes the ambiguity by making task, not page id, select content; the fix itself is a Wave 9
navigation migration with its own evidence, not a Wave 1 change.

## 3. Research

**User question:** "Does this hypothesis survive contact with point-in-time data and a backtest?"

| Element | Specification |
|---|---|
| Work mode | `research` (emphasis: strategy → system) |
| Entry | Strategy primary, `strategy` page — pattern `ANALYSE`, tasks `design` (`CONFIGURE`), `backtest` (`ANALYSE`), `compare` (`COMPARE`), `shadow` (`MONITOR`) |
| Secondary | `research` (`EXPLORE`) for the dataset/feature/target catalogue |
| Panels | `context-summary`, `time-series`, `comparison`, `run-result`, `evidence`, `warnings` |
| Inspector subjects | `strategy-version`, `strategy-run`, `data-product` |
| Primary action | run the backtest/evaluation (`compute` → workspace-primary) |
| Local actions | dataset/feature/target filters, run selection, comparison windows |
| Guarded actions | freeze a strategy version, retire shadow monitoring (`lifecycle` → object-overflow) |
| AI actions | `draft` (research plan, StrategyIR candidate), `challenge`, `explain` |
| Minimum navigation | 1 route change: the strategy lifecycle stays inside one domain; catalogue detail opens in the Inspector |

Flow: **question** → **dataset** (point-in-time, entitlement shown) → **hypothesis** → **backtest** →
**robustness** → **comparison** → **freeze** → **shadow** → **review**.

Rules that must hold: a draft produced by AI is marked unverified until a named human accepts or
edits it; a frozen strategy version is immutable; export stays subject to entitlement; the run
records its dataset/feature versions so the result is explainable
([08_DECISION_APPLICATION_AI.md](08_DECISION_APPLICATION_AI.md) section 3).

States: no dataset built yet (empty, with the next action named), restricted dataset (export
unavailable with the policy reason), failed run (blockers and warnings, no fabricated metric).

## 4. Decision Case

**User question:** "Is the evidence sufficient for a human to accept, reject or reopen this
result?"

| Element | Specification |
|---|---|
| Work mode | `review` (emphasis: decision → strategy) |
| Entry | Decision primary, `review` page — pattern `REVIEW` |
| Secondary | `scenario` (`CONFIGURE`) and `optimize` (`ANALYSE`) supply alternatives and economics |
| Panels | `evidence`, `decision-history`, `warnings`, `ai-explanation` |
| Inspector subjects | `decision-evidence`, `strategy-run` |
| Primary action | record the human decision (`persist` → workspace-primary), which is evidence, never execution approval |
| Local actions | select run/artifact, expand lineage, filter evidence |
| Guarded actions | reopen a decided case (`lifecycle` → object-overflow) |
| AI actions | `challenge`, `explain`, `compare` |
| Minimum navigation | 1 route change: evidence, alternatives and the decision live together |

Target container (Wave 6): objective, Active Context, Analysis Snapshot, assumptions, alternatives,
scenarios, economics, risk/constraints, evidence, AI findings, human review, Decision Record.

Rules that must hold: a Decision Record is rationale and evidence, not an execution instruction; a
recorded decision names reviewer, time and note; no execution, order, nomination or settlement
semantics may appear anywhere in the flow.

## 5. Administration

**User question:** "Are connections, access, entitlements and runtime healthy — without exposing
commercial data?"

| Element | Specification |
|---|---|
| Work mode | `administration` (emphasis: system only) |
| Entry | System primary, `sources` page — pattern `MONITOR` |
| Secondary | `access` (`CONFIGURE`), `runtime` (`MONITOR`), `settings` (`CONFIGURE`) |
| Panels | `metric-strip`, `table`, `warnings`, `evidence` |
| Inspector subjects | `provider-connection`, `data-product`, `job` |
| Primary action | operate a connection (test/refresh) (`compute` → workspace-primary) |
| Local actions | source category filters, credential metadata, runtime detail |
| Guarded actions | rotate/revoke a credential (`lifecycle` → object-overflow) |
| AI actions | none offered by default: this surface shows no commercial evidence to reason over |
| Minimum navigation | 1 route change into the control plane; business pages must not contain operator controls |

Rules that must hold (V2 doc 06 sections 7-8, and
[W0-02_BACKEND_ACCESS_INVENTORY.md](W0-02_BACKEND_ACCESS_INVENTORY.md) for current behaviour):

1. Platform administration MUST NOT imply commercial-data access. The Wave 2 capability/scope work
   owns closing the current gap where the admin role holds every capability.
2. Secret values MUST NOT be rendered: only credential metadata, expiry and connection state.
3. The control plane MUST NOT be reachable from ordinary business navigation once Wave 3 separates
   the surfaces; until then `sources`, `runtime` and `access` remain reachable and this specification
   records the debt rather than pretending it is solved.
4. Business-facing health (market data healthy/delayed) and technical health (pool, worker,
   migrations) MUST stay separate.

## 6. Cross-cutting acceptance checks

For each specification above, review:

- [ ] the user task is answered without traversing unrelated pages;
- [ ] the entry context is the canonical Active Context, and the surface states which context it is
      showing;
- [ ] actions are where the action geography puts them, and there is at most one primary action;
- [ ] the same object behaves the same way in another mode (same identity, selector, provenance and
      status language);
- [ ] loading, empty, degraded, restricted and failed states are defined;
- [ ] evidence and provenance are discoverable from the result, not from a detached toast;
- [ ] the result states what it cannot reproduce while the Analysis Snapshot gap is open;
- [ ] AI is helpful, evidence-linked and non-authoritative, with the five canonical actions only;
- [ ] no execution, order entry, nomination or settlement behaviour appears;
- [ ] desktop adds workstation value only through HostCapabilities, never a second business logic.

## 7. Implementation status and non-goals

These specifications are **target compositions**, not claims about the current client. Wave 1
delivers the vocabulary, registries and seams; Wave 9 migrates workspaces onto them. Where a
specification needs something that does not exist yet, the owning wave is named:

| Need | Wave |
|---|---|
| Analysis Snapshot (reproducibility) | 4 |
| Projections (`MarketContext`, `PortfolioSnapshot`, `ReviewContext`) | 5 |
| Decision Case container, Decision Record | 6 |
| Research-question-led Studio, cross-workspace Copilot | 7 |
| Unified Job, error taxonomy, business health, diagnostics | 8 |
| Control-plane separation and capability/scope/entitlement model | 2-3 |
| Workspace migration onto shell, patterns, Inspector, palette | 9 |
| Desktop workstation capability (multi-window, layout, native notifications) | 10 |

No page is created, merged or retired by these specifications. No API, schema, permission or
numerical behaviour changes.
