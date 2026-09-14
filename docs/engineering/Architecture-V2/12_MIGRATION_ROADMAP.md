# Architecture V2 Migration Roadmap

Do not perform a big-bang rewrite.

## Wave 0 — Baseline and architecture freeze
Goal: map current implementation to V2.

Deliver:
- current-to-target code map;
- conflicts with accepted ADRs;
- route/workspace/API/permission/provider/admin inventory;
- architecture fitness tests;
- implementation plan.

No broad feature/UI redesign yet.

## Wave 1 — Product Experience Architecture foundation
Goal: stop further UX divergence before deeper refactor.

Deliver:
- canonical shell contract;
- Active Context UI contract;
- workspace-pattern registry;
- panel taxonomy;
- Inspector contract;
- action geography;
- canonical AI actions;
- command palette/navigation model;
- HostCapabilities contract;
- high-fidelity prototype/spec for:
  - Trading Analysis
  - Portfolio Oversight
  - Research
  - Decision Case
  - Administration

Important:
Do not mass-convert every page yet.
Establish the design/interaction authority first.

## Wave 2 — Identity / Effective Access / Experience
Deliver:
- Functional Assignments;
- Work Modes;
- Effective Access;
- ExperienceProfile;
- navigation/panel composition;
- current roles retained as compatibility bundles.

## Wave 3 — Control Plane separation
Deliver:
- Administration surface boundary;
- user prefs vs system config separation;
- provider/credential/runtime/access operations moved out of business navigation;
- platform admin separated from commercial access.

## Wave 4 — Unified Data Platform surface
Deliver:
- Data Product abstraction;
- Provider Connection vs Entitlement;
- unified status/provenance;
- Analysis Snapshot v1.

No new datastore without evidence.

## Wave 5 — Application projections / Active Context
Deliver:
- MarketContext;
- PortfolioSnapshot;
- ScenarioContext;
- ReviewContext;
- frontend migration away from multi-endpoint business-state reconstruction.

## Wave 6 — Decision Platform
Deliver:
- Decision Case;
- assumptions/alternatives/evidence;
- Decision Record;
- timeline/replay;
- snapshot linkage.

## Wave 7 — Research and AI convergence
Deliver:
- research-question-led Research Studio;
- strategy lifecycle convergence;
- cross-workspace Copilot;
- structured AI/research artefacts.

## Wave 8 — Product Operations convergence
Deliver:
- Unified Job;
- error taxonomy;
- correlation/tracing;
- business service health;
- diagnostics bundle;
- deployment profiles;
- capacity planning template;
- validate DR/backup/SLO against target deployment.

## Wave 9 — UI implementation convergence
Now apply the shell/pattern/design system systematically:
- migrate pages;
- remove inconsistent local patterns;
- test task flows;
- preserve domain/API behaviour.

## Wave 10 — Desktop Terminal enhancement
Deliver where justified:
- multi-window;
- multi-monitor persistence;
- workspace profiles;
- native notifications;
- file integration;
- deep links;
- desktop diagnostics;
- shortcut model.

Do not fork business logic.

## Wave 11 — RC / GA readiness
- enterprise IdP acceptance;
- provider certification;
- security acceptance;
- platform-specific package/install testing;
- real trader/HQ/research UAT;
- production restore drill;
- signing/notarisation;
- commercial deployment guide;
- GA gate.

## Stop gate after every wave

Report:
1. changed files;
2. architecture decisions;
3. compatibility impact;
4. tests/evidence;
5. UX screenshots/prototypes if applicable;
6. deferred gaps;
7. risks;
8. recommendation.

Then STOP.
