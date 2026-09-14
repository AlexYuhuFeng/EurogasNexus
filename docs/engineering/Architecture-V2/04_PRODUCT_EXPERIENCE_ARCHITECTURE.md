# Product Experience Architecture

This is a first-class Architecture V2 domain, not a visual-polish appendix.

## 1. Problem statement

The current client has many capabilities but weak coherence.
The main problem is not colour, typography or component quality.
It is the lack of a consistent **usage model**.

The target is:

**Same interaction language, different information composition.**

Trader, HQ, Research and Reviewer experiences should feel like the same professional product.

## 2. User-task-first design

Do not design pages from features.

Wrong:

`Market feature -> Market page`
`Capacity feature -> Capacity page`
`Agent feature -> Agent page`

Correct:

`User question -> Context -> Evidence -> Action -> Result -> Persisted decision/research artefact`

Example:

“Where should tomorrow's NBP resource go?”

The user should not manually traverse five unrelated pages.
The system should compose market, portfolio, physical, capacity, route economics and risk in one
task-oriented context.

## 3. Canonical Experience Shell

All business modes use the same shell:

```text
┌─────────────────────────────────────────────────────────┐
│ Global Context / Gas Day / Portfolio / Search / Status  │
├───────────┬───────────────────────────────┬─────────────┤
│ Navigation│ Primary Workspace             │ Inspector   │
│           │                               │             │
│           │                               │             │
├───────────┴───────────────────────────────┴─────────────┤
│ Activity / Jobs / Evidence / Notifications / Timeline  │
└─────────────────────────────────────────────────────────┘
```

Persistent cross-product elements:
- Global Context
- Navigation
- Primary Workspace
- Inspector
- Activity/Jobs
- Notifications
- Command Palette
- Copilot

## 4. Workspace patterns

Most screens should use a small number of canonical patterns:

- **Monitor** — continuous status, alerts, market/portfolio watch.
- **Explore** — map/network/data exploration.
- **Analyse** — detailed analytical workflow.
- **Compare** — alternatives/routes/scenarios side by side.
- **Configure** — bounded setup or model inputs.
- **Review** — evidence, challenge, sign-off/recording workflow.

Do not invent a unique interaction model for every domain.

## 5. Panel taxonomy

Use reusable panel types:
- context summary;
- metric strip;
- time series;
- table/grid;
- map;
- assumptions;
- warnings;
- evidence/provenance;
- run result;
- comparison;
- decision history;
- AI explanation/challenge.

New product capability should first ask:
“Which existing pattern and panel does this belong to?”

## 6. Inspector rule

Object detail should normally appear in a common Inspector rather than opening a new top-level page.

Examples:
- route;
- contract/resource;
- capacity;
- market observation;
- strategy version;
- decision evidence;
- source/data product metadata.

## 7. Interaction Grammar

Define once and reuse everywhere.

### Selection
Same selector/search behaviour across product.

### Object detail
Open Inspector.

### Configure calculation
`Configure -> Validate -> Run -> Progress -> Result`

### Compare
Standard side-by-side comparison frame.

### Evidence
Always discoverable from one consistent location.

### Errors
Always answer:
- what happened;
- impact;
- likely cause;
- recovery/action.

### AI
Canonical actions:
- Ask
- Explain
- Compare
- Challenge
- Draft

Do not scatter inconsistent “magic AI buttons”.

## 8. Navigation model

Primary navigation should represent durable work domains, not implementation modules.

Recommended logical groups:
- Home / Overview
- Market & Physical
- Portfolio
- Decisions
- Research & Strategy
- Reports
- Administration (capability-gated)

Avoid one top-level entry per backend capability.

## 9. Work modes

A multi-function user selects an active work mode.

Examples:

### Trading Analysis
Focus:
market, position, capacity, route opportunity, scenario.

### Portfolio Oversight
Focus:
portfolio summary, exposure, performance, exceptions, decision queue.

### Research
Focus:
question, dataset, strategy, backtest, robustness, shadow.

### Review
Focus:
evidence, exceptions, decision/research review.

### Administration
Focus:
access, data connections, runtime, audit.

Work mode changes composition only, not authority.

## 10. Persona consistency

The same object must behave consistently across work modes.

Example:
a Portfolio selected in Trading Analysis and Portfolio Oversight uses the same:
- identity;
- context selector;
- inspector pattern;
- provenance pattern;
- status language.

## 11. Professional information density

The target is a professional workstation, not a consumer dashboard.

Principles:
- compact but readable;
- high information density;
- strong alignment;
- predictable action geography;
- minimal decorative cards;
- avoid excessive nested panels;
- avoid oversized whitespace;
- stable typography scale;
- clear primary/secondary action hierarchy.

## 12. Responsive strategy

Do not make the professional workstation “mobile-first” in a way that damages desktop density.

Support:
- large desktop / multi-monitor as primary professional environment;
- normal laptop layout;
- browser access on smaller screens with reduced composition;
- no requirement that every dense analytical view be equally powerful on mobile.

## 13. Prototype-before-implementation rule

Before large UI refactoring:
1. define canonical flows;
2. design the shell and patterns;
3. produce high-fidelity prototypes for representative experiences;
4. test user-flow coherence;
5. only then implement at scale.

Recommended canonical prototype set:
- Trading Analysis workspace
- HQ / Portfolio Oversight workspace
- Research workspace
- Decision Case
- Administration

## 14. Design tooling

Figma, OpenDesign-like tools or AI design tooling may be used to accelerate:
- design system;
- canonical shell;
- prototypes;
- component specification.

They SHALL NOT independently define information architecture.

The architecture/workflow specification remains the source of truth.

## 15. UX acceptance metrics

Do not accept UI solely because build/tests pass.

Review:
- click depth;
- task completion flow;
- cross-page consistency;
- navigation predictability;
- context persistence;
- action placement;
- information density;
- state handling;
- keyboard accessibility;
- work-mode switching;
- Web/Desktop parity;
- multi-window behaviour where supported.
