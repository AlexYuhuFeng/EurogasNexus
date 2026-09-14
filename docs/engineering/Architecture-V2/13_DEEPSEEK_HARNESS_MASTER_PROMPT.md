# DeepSeek Harness Master Prompt — Eurogas Nexus Architecture V2

You are implementing the reviewed Eurogas Nexus Architecture V2.

## Mission

Converge the existing repository toward the target product architecture without discarding proven
domain, data, security, release, deployment, research or AI capabilities.

You are not authorised to perform a big-bang rewrite or to add fashionable infrastructure without need.

## Mandatory reading order

Read every file in this V2 pack first.

Then read:
1. repository `README.md`
2. `PROJECT_DIRECTORY.md`
3. `docs/README.md`
4. `docs/architecture/ARCHITECTURE_DECISION_RECORD.md`
5. `docs/architecture/TARGET_PRODUCT_ARCHITECTURE.md`
6. `docs/release/RELEASE_READINESS.md`
7. `docs/release/RELEASE_ENGINEERING_SPEC.md`
8. existing client/UI architecture documents
9. existing deployment/operations/security contracts relevant to any file you plan to touch

Repository truth wins for **current implemented behaviour**.
V2 wins for **target direction**.

If V2 conflicts with an accepted ADR, do not silently override it.
Report the conflict and propose a superseding ADR/transition.

## First execution scope

Execute **Wave 0 and Wave 1 only**.

Do not proceed to Wave 2 without human review.

### Wave 0
- current-to-target code mapping;
- inventory current workspaces/routes/panels/navigation;
- inventory API dependencies by workspace;
- inventory role/permission/entitlement model;
- inventory provider/source/admin/runtime controls;
- identify architecture conflicts;
- add safe architecture fitness tests where appropriate.

### Wave 1
Establish Product Experience Architecture authority without mass-rewriting all pages.

Deliver:
- canonical shell specification/implementation seam;
- Active Context UI contract;
- Workspace Pattern registry;
- Panel taxonomy/registry;
- Inspector contract;
- navigation and action-geography contract;
- canonical AI interaction contract;
- command palette/keyboard interaction model;
- HostCapabilities abstraction contract;
- representative prototype/specification for:
  - Trading Analysis
  - Portfolio Oversight
  - Research
  - Decision Case
  - Administration

If design tooling/Figma/OpenDesign-like workflows are available, they may be used for prototypes.
They must not invent product structure independently of the V2 specifications.

## Hard prohibitions

- no big-bang rewrite;
- no microservice split;
- no Kubernetes/Kafka/service mesh for style;
- no new datastore without measured need and ADR;
- no FastAPI/React/Tauri replacement;
- no duplicate Trader/HQ/Research frontend applications;
- no direct client DB/vendor access;
- no client-stored provider credentials;
- no trade execution/order entry/nomination;
- no AI authority bypass;
- no UI-only permission enforcement;
- no `if role == ANALYST: render AnalystDashboard` architecture;
- no “ADMIN sees everything” shortcut;
- no mass UI conversion before canonical patterns are accepted;
- do not delete current release/security/DR machinery.

## Required access equation

Backend:
`identity + grants + scopes + entitlements + constraints -> effective access`

Experience:
`effective access + functional assignments + selected work mode + preferences -> composition`

Work mode never changes backend authority.

## UX rules

- A new capability does not automatically earn a new page.
- Reuse canonical shell, workspace patterns, Inspector and panels.
- Different work modes share one interaction language.
- Business user flows must be task-oriented.
- Desktop differentiates through workstation efficiency, not different business logic.
- OS differences are expressed through HostCapabilities.

## Implementation style

Prefer compatibility-safe seams and adapters.

Do not create empty placeholder packages.

Use repository conventions, existing ADR/RFC governance and focused tests.

During implementation run focused checks only.
Do not claim full-repository acceptance unless actually run.

## End-of-run report

Provide:
1. executive summary;
2. current-to-target mapping;
3. architecture/ADR conflicts;
4. UX findings;
5. changed files;
6. DB/API compatibility impact;
7. tests actually run;
8. screenshots/prototype artefacts produced;
9. deferred gaps;
10. risks;
11. exact recommendation for next wave.

Then STOP.
