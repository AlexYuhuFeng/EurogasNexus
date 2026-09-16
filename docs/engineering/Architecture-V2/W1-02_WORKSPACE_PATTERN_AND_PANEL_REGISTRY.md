# W1-02 — Workspace Pattern and Panel Registry

Status: **delivered contract (Wave 1)**. Authority: Architecture V2
[04_PRODUCT_EXPERIENCE_ARCHITECTURE.md](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md) sections 2, 4, 5 and 8,
and [11_CURRENT_TO_TARGET_GAP_MATRIX.md](11_CURRENT_TO_TARGET_GAP_MATRIX.md) rows 24 and 26.

Machine-readable form: `clients/web/src/app/experience/workspacePatterns.ts`,
`clients/web/src/app/experience/panelTaxonomy.ts`.
Focused checks: `clients/web/tests/experienceArchitecture.test.ts`.
Current-state evidence: [W0-01_CLIENT_INVENTORY.md](W0-01_CLIENT_INVENTORY.md) sections 2 and 3.

## 1. Why a registry instead of page-by-page design

Architecture V2 forbids designing pages from features: a capability does not earn a page, and a
domain does not earn a bespoke interaction model. The registry answers "what is this surface?"
once, for the 16 technical page ids that exist today, so later work reuses a pattern rather than
inventing one.

## 2. Canonical patterns

| Pattern | Meaning |
|---|---|
| `MONITOR` | Continuous status, alerts, market or portfolio watch. |
| `EXPLORE` | Map, network or catalogue exploration. |
| `ANALYSE` | Detailed analytical workflow over one object or question. |
| `COMPARE` | Alternatives, routes, scenarios or strategy versions side by side. |
| `CONFIGURE` | Bounded setup or model input entry, ending in validate-then-run. |
| `REVIEW` | Evidence, challenge, sign-off and decision recording. |

No seventh pattern is added without an architecture review: a surface that does not fit one of
these is a signal that the task, not the pattern set, is wrong.

## 3. Page registry

Every page id declared in `clients/web/src/workspaceNavigation.ts` has exactly one composition
entry: primary owner, pattern, header mode, Inspector subjects and panels.

| Page | Primary | Pattern | Header mode |
|---|---|---|---|
| `network` | market | EXPLORE | consolidated |
| `market` | market | MONITOR | consolidated |
| `capacity` | market | ANALYSE | consolidated |
| `contracts` | portfolio | CONFIGURE | consolidated |
| `orders` | portfolio | ANALYSE | consolidated |
| `strategy` | strategy | ANALYSE | local-tabs |
| `scenario` | decision | CONFIGURE | consolidated |
| `review` | decision | REVIEW | consolidated |
| `sources` | system | MONITOR | local-tabs |
| `glossary` | system | EXPLORE | local-tabs |
| `runtime` | system | MONITOR | local-tabs |
| `settings` | system | CONFIGURE | local-tabs |
| `manual` | system | EXPLORE | local-tabs |
| `access` | system | CONFIGURE | local-tabs |
| `research` | system | EXPLORE | local-tabs |
| `agents` | system | REVIEW | local-tabs |

Rules:

1. The registry SHALL cover every declared page id exactly once; the focused test fails on a
   missing or duplicated page.
2. The primary owner SHALL agree with `productNavigation.ts`. `compositionOwner()` throws when the
   registry and the navigation registry disagree, so the two cannot drift silently.
3. `headerMode` records the composition the client renders today. It is read by
   `clients/web/src/app/workspaces/WorkspaceRenderer.tsx` instead of a local list of primary ids,
   which is the executable part of this contract:
   `const usesConsolidatedHeader = headerModeForPage(activeWorkspace) === "consolidated";`.
4. `headerMode` is a current-state seam, not the target design. Converging every work mode onto one
   shell composition is Wave 9 work
   ([12_MIGRATION_ROADMAP.md](12_MIGRATION_ROADMAP.md) Wave 9), and the V2 gap matrix marks the
   current functional navigation as REFACTOR.

## 4. Task patterns

Task-level patterns are declared for the primaries whose tasks are URL-addressable and resolved by
live code (`marketCockpitModel`, `commercialWorkflowModel`, `strategyLabModel`):

| Primary | Tasks |
|---|---|
| market | `overview` MONITOR, `curves` MONITOR, `network` EXPLORE, `capacity` ANALYSE |
| portfolio | `overview` MONITOR, `resources` ANALYSE, `routes` COMPARE, `exposure` ANALYSE |
| strategy | `design` CONFIGURE, `backtest` ANALYSE, `compare` COMPARE, `shadow` MONITOR |
| decision | `scenario` CONFIGURE, `optimize` ANALYSE, `review` REVIEW |
| system | none — its views are component-local until Wave 9 |

The focused test derives the task vocabulary from the live resolvers rather than a copied list, so a
resolver change that adds a task fails the check until the registry is updated.

## 5. Panel taxonomy

Twelve reusable panels replace per-surface invention. Each entry records its purpose, the shared
primitive that owns it today (or none), whether it is present, partial or absent, the patterns that
compose it, and the disclosures it owes.

| Panel | Implementation | Owner today |
|---|---|---|
| `context-summary` | absent | — |
| `metric-strip` | present | `components/ui/MetricStrip.tsx` |
| `time-series` | partial | `components/strategy/StrategyLabCharts.tsx` |
| `table` | partial | — (workspace-local table markup) |
| `map` | present | `components/GasNetworkMap.tsx` |
| `assumptions` | absent | — |
| `warnings` | partial | `app/warningLabel.ts`, `components/ui/StatusBadge.tsx` |
| `evidence` | partial | `components/agents/AgentArtifactChain.tsx`, `AgentReviewGate.tsx` |
| `run-result` | partial | — |
| `comparison` | partial | `components/strategy/StrategyCompareWorkspace.tsx` |
| `decision-history` | partial | `components/agents/AgentReviewGate.tsx` |
| `ai-explanation` | partial | `components/agents/AgentArtifactChain.tsx` |

Disclosure vocabulary: `as-of`, `time-basis`, `units`, `provenance`, `entitlement`, `assumption`,
`warning`, `correlation-id`.

Rules:

1. A panel that presents a material number SHALL carry the disclosures declared for its kind.
   `metric-strip`, `time-series` and `run-result` MUST carry `as-of`; numeric panels MUST carry
   `units`.
2. Every owner path declared in the taxonomy SHALL exist; the focused test checks the filesystem,
   so a taxonomy row cannot point at a deleted or imagined primitive.
3. `implementation: "present"` SHALL name an owner. A panel with no shared owner is recorded as
   `partial` or `absent`, never as implemented.
4. Composing a new surface SHALL start from this taxonomy; a panel kind that is missing is added
   here first, in the same change that needs it.

## 6. Verification

- `clients/web/tests/experienceArchitecture.test.ts` — registry completeness and uniqueness,
  primary agreement, header-mode consistency per primary, live task coverage, panel owner
  existence, disclosure presence, composition membership.
- `clients/web/tests/workspaceHeader.test.ts` and `clients/web/tests/productNavigation.test.ts`
  continue to pin the label and navigation behaviour the renderer produces from the registry.

## 7. Compatibility and non-goals

- No page id, route, deep link, header label, tab label or API call changes. The refactor moves the
  *source* of the header-mode decision, not the decision.
- The registry classifies the current 16 pages; it does not invent, merge or retire any page. Page
  consolidation is target work for Waves 3 and 9 with its own evidence.
- No new dependency, framework or styling system is introduced.
