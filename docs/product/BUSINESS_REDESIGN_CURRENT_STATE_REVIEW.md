# Current-state review for the business workflow redesign

Date: 2026-10-23. Baseline source: pushed commit2cc1010 plus local map-layout
corrections. Scope: task-entry and composition inspection using synthetic trader,
analyst, reviewer and administrator identities; source-level domain reconciliation.
This is not practitioner UAT, full accessibility certification or a full numerical
audit. Current captures are in ignored `.local-runtime/business-redesign/`.

## Findings from current captured screens

1. **Trader Market / Network — usable investigation, weak default daily entry.**
   `network-1440.png`: source/data state and resources are visible, but the view
   begins with a network canvas even when there is no network evidence. The
   current capture includes the separately validated map-height correction. It
   still does not organize the day by obligations, deadlines or proposed decisions.
   The map remains valuable when physical investigation is the actual task.
2. **Trader Portfolio — useful resource register, incomplete operating book.**
   `contracts-1440.png`: resource names, quantities, costs and access are legible;
   missing route evidence is explicit. Pool quantity and source cost are prominent,
   but the screen does not distinguish a reconciled position/remaining obligation
   from declared scenario resources. Existing handoff buttons expose navigation,
   not the full business question, expected inputs and resulting artifact.
3. **Analyst Strategy — rigor exposed as implementation form.**
   `strategy-1440.png`: explicit price choices, historical target declarations and
   cost treatments are strengths. The initial screen is a long configuration form
   with five blockers before the user has chosen a hypothesis/model. Backend
   concepts such as target basis and evidence role appear alongside commercial
   choices. Redesign should retain their semantics while guiding model → series →
   hypothesis/signal → resource/sizing → evaluation, with relevant advanced fields.
4. **Reviewer Review — wrong task composition, not proof of wrong permissions.**
   `review-1440.png`: the genuine REVIEWER session renders an upstream-resource
   read403 banner. It starts with empty optimizer output, manual entity-ID input
   and report generation; Decision Cases appears after these unrelated sections.
   The reviewer needs an assigned/available evidence-backed case first. Investigate
   capability-aware data composition and reuse backend case/evidence services;
   do not grant contract-read authority to silence a banner. The test account has
   no submitted review queue; populated independent-review acceptance remains open.
5. **Administrator Access — correct core task with unnecessary business context.**
   `access-1440.png`: persisted users/roles/data grants and bounded actions exist.
   Global gas-day, delivery product, hub and market-source warnings remain above
   identity administration even though ADMIN has no implicit commercial rights.
   Separate the control-plane shell composition while retaining existing APIs and
   authority. Multi-select control discoverability and keyboard operation need
   usability testing; no full accessibility compliance is claimed from screenshots.

The reviewer capture initially failed because its old synthetic session expired.
Only that existing session and the admin session were refreshed; no grants changed.
The accepted screenshots show authenticated, settled states. Their visible stale,
missing or denied data are genuine captured states, not hidden loading placeholders.

## Existing foundations to preserve, verified in current source

| Foundation | Source evidence | Consequence for redesign |
| --- | --- | --- |
| Business-facing data products with explicit availability and time basis | `domain/data_platform/products.py` | Extend/reuse this catalogue; do not invent another source/feature registry |
| Effective capabilities and separate control-plane access | `security/permissions.py`, client `experienceProfile.ts` | Compose tasks from actual authority; backend remains final gate |
| Shared explicit cash/FX valuation and bounded LNG adapter | `domain/research/cash_valuation.py`, `lng_cash_valuation.py` | Reuse numerical ownership; do not recompute cash or FX in React |
| Constrained resource-pool allocation | `domain/route_cost/resource_pool.py` | Preserve solver; distinguish single-scenario allocation from remaining-book accounting |
| Explicit regas readiness | `domain/route_cost/lng_regas.py` | Reuse access/slot/capacity checks before new LNG scheduling claims |
| Versioned strategy, point-in-time historical selection and owner privacy | strategy registry, backtest target selection and acceptance16/21 | Preserve historical versions, economic meaning and access boundaries |
| Existing snapshot and decision-case services | client `analysisSnapshotModel.ts`, `DecisionCasePanel.tsx`, server corresponding APIs | Connect existing canonical objects; local panel-selected state is an integration gap, not reason for a new duplicate case model |

## Verified limits versus unproven hypotheses

- Verified: Weather product is declared-only/mock/empty, not a demand forecast.
- Verified: legacy strategy evaluation is the bounded OCM/day-ahead paper model.
- Verified: current client Active Context lists case/snapshot/organization/portfolio
  gaps while other components separately consume some of those backend objects.
- Not yet proven: a new backend portfolio ledger is necessary for every near-term
  workflow. First map customer record/import boundaries and existing capabilities.
- Not yet proven: all users need new primary navigation or a new datastore. Task
  entry and composition can change without replacing the domain foundations.
- Not yet proven: the captured empty reviewer view represents the populated case
  lifecycle. Test a genuinely shared/submitted case without weakening privacy.

## Change decision protocol

A proposal proceeds only with its business scenario, current-source evidence,
classification (presentation/integration/capability/semantic defect), selected
remedy, reused services, compatibility impact, numerical/security invariants,
rollback and complete positive/negative workflow acceptance. Prefer composition
when the domain is already correct. Do not treat passing tests as business UAT,
or existing UI friction as proof that the whole architecture is wrong.

The three candidate design documents are a coherent hypothesis for validation:
`EUROPEAN_GAS_BUSINESS_WORKFLOWS.md`, `DATA_TO_COMMERCIAL_DECISION_MAP.md`, and
`../architecture/decisions/2026-10-23-business-workflow-redesign.md`. They do not
claim implemented coverage or supersede release acceptance.
