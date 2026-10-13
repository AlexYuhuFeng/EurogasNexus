# Approved direction: product-aware historical evidence selection

Status: **APPROVED DIRECTION — implementation in bounded phases**. Owner: Astra architecture review, 2026-10-08. Amends accepted CR-04 `BACKTEST_ENGINE_SPEC.md` sections 6, 11, 15 and 20. Human authorization: user explicitly wrote “同意架构修改提案”, first recorded 2026-10-07T23:49:57Z and repeated in subsequent heartbeat messages; root confirmed this authorization. This satisfies the material-ADR STOP for this proposal only. No weakening of security, unrelated scope expansion, unexpected numerical movement or Golden Scenario tolerance override is authorized.

## Why human approval is required

Report06 proves a year of decisions reused one pre-window price-reference set and reported 100% Coverage. Report07 rejects future requests, but historical windows can still reuse expired products. Fixing selection requires a target-delivery declaration absent from existing frozen strategies, changes the evidence set and therefore deterministic PnL, and needs a new engine version. **This is a material accepted-contract change**, beyond the independent future-window guard. The user's hard STOP applies; the repository's autonomous override does not authorize it.

## Proposed decision (one coherent bounded direction)

1. **Field ownership.** Extend the versioned backend frozen `StrategyComponentSpec`, per required price leg, with `evidence_target`: role (`DELIVERY_PRICE` or `REFERENCE_LEVEL`), target basis, product/tenor, hub, price basis and the parameters needed to resolve a target interval. The domain owns validation/resolution; the existing Strategy UI edits the declaration and shows the resolved target. No React business calculation or new page/service/datastore.
2. **Explicit target, not quote self-approval.** At decision T, resolve each leg's target independently of available quotes, then require availability <= T and a matching product/target interval. A row is not valid merely because its tenor string or its own delivery window exists. Day-ahead and forward rows may begin delivery after T when they match the declared target.
3. **Existing frozen definitions fail closed for new historical runs.** Missing target declarations return a structured `target_delivery_not_declared` refusal. Do not infer a target from a name, rewrite a frozen version, or backfill economic history. The operator forks a draft, explicitly declares targets, then freezes it. Old stored runs remain readable with their original provenance and a legacy temporal-semantics disclosure.
4. **Version and replay.** New target-aware historical selection uses `backtest-engine/2` and includes the resolved target/selection reasons in event provenance and the manifest hash. Keep engine/1 evidence and records unchanged. Any legacy replay is an explicitly marked verification of old semantics, never a new engine/2 result or fresh historical-data claim. Exact replay is only claimed when referenced evidence remains verifiable; references alone do not prove immutable source values.
5. **Carry-forward and coverage.** Find admissible same-series/product evidence first. Only an explicitly declared existing bounded carry-forward/fallback policy may fill an absence; enforce its configured maximum age even when stale same-name rows exist. Preserve lineage and mark reused, simulated, unknown and observed evidence separately. No invented global TTL or silent 24-hour delivery window. Retain the legacy completed/evaluation ratio as a clearly described evaluation-completion measure; add independently defined observed-input sufficiency before presenting effective market coverage. Do not relabel completion as data quality.

## Target-resolution cases to implement and test

| Leg purpose | Target declaration and match |
| --- | --- |
| Same-gas-day valuation | Explicit gas-day basis plus canonical calendar; price rows must address that resolved delivery interval. |
| Day-ahead comparison | Declare current-delivery-day quoted earlier versus next-delivery-day target. These are distinct economics; the name `day-ahead` does not choose between them. |
| Hourly delivery | Explicit hour/interval and timezone-aware normalization; half-open interval matching, including repeated/missing DST hours. |
| Month/quarter/forward | Declared tenor, roll convention/calendar or explicit target interval; compare the resolved delivery interval, not just `month-ahead` text. |
| Assessment/reference | Explicit reference role, publication/availability and declared validity or bounded reuse rule. Reference reuse is not a fresh deliverable-price observation. |

Source normalization must preserve declared delivery periods and distinguish assessments from deliverable quotes. Unknown/invalid mappings block the affected leg with a concrete reason. Partial-period observation handling and aggregation across subintervals must be specified explicitly before implementation; no implicit averaging of unrelated delivery products.

## Compatibility, evidence and limits

- No destructive migration, historical rewrite, permission change, provider-license broadening, trade execution, nomination or settlement. Existing EVALUATION/scenario behavior stays unchanged until separately aligned.
- Tests must reproduce the 365-identical-reference case, fresh valid controls, per-leg interval mismatch, unknown target refusal, allowed future-delivery quotes, hourly boundaries, canonical 23/25-hour gas days, bounded carry-forward and fallback, and old-record immutability.
- Record expected evidence-selection and numerical deltas in a reviewer-readable comparison. Do not edit Golden Scenario expectations to make tests green. Unexpected numerical movement or an existing Golden Scenario outside tolerance triggers the user's STOP again.
- Implement in small slices: declaration/validation and explicit legacy refusal; product-aware selection/provenance; honest coverage presentation; actual UI/DB acceptance. Approval covers this direction; implementation and validation are separate gates. No numerical selection code was changed when the proposal was approved.

**Approved scope:** explicit target declarations, fail-closed new runs for undeclared frozen versions, and engine/2 provenance as described above. Implement and review in bounded phases; no repeat approval is needed for this same decision. Other vendor-remediation and UI acceptance work remains part of the full goal.
