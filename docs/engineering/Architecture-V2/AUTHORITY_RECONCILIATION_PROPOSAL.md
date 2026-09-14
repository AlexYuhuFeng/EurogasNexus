# Proposed UI authority reconciliation

Status: PROPOSED — human review required; no accepted authority changed.
Date: 2026-09-14
Baseline HEAD: 334c882d5de5fe7e4c955ee1d3cc2af1781f8829

## Conflict

[Accepted ADR Decision 14](../../architecture/ARCHITECTURE_DECISION_RECORD.md#decision-14-professional-workstation-ui-convergence-contract)
states: “The Professional UI Constitution is the sole visual and interaction authority”.

[V2 gap matrix](11_CURRENT_TO_TARGET_GAP_MATRIX.md) says the UI Constitution is
“Subordinate to Product Experience Architecture”. [V2 section 04](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md)
defines shell, navigation, workspace patterns and interaction grammar, overlapping
the accepted authority. This is a normative hierarchy conflict, not evidence of a
runtime defect.

The [entrypoint](CODEX_ENTRYPOINT.md) requires human review when an accepted ADR
must materially change and prohibits silently overriding accepted ADRs.

## Proposed decision for approval

Approve drafting a superseding ADR through the existing ADR/RFC process, with:

- V2 Product Experience Architecture governing task flows, shell composition,
  workspace patterns, navigation, Inspector and cross-workspace interaction grammar.
- The Professional UI Constitution retaining visual authority for typography,
  density, spacing, component styling and motion, subordinate to the approved
  product interaction contracts where they overlap.
- UI Content Standards retaining content, time basis, rights, provenance,
  entitlement and no-execution rules; domain/API/security contracts retaining
  their existing precedence and authority.
- Explicit reconciliation of RFC-0001 and its linked companions before any
  broad UI migration. Preserve the accepted decision history by supersession.

Approval would authorise preparing the ADR and resuming bounded Wave 0 mapping.
It would not accept an implementation, close outstanding visual/UAT gates, or
authorise mass UI conversion. Existing behavior remains the baseline.

## Pending bounded plan

1. W0-01: documentation-only route/workspace/panel/navigation and client API
   dependency inventory, with source references and existing fitness-test map.
2. W0-02: backend permission/entitlement/provider/control-plane inventory and
   current-to-target architecture mapping.
3. W0-03: architecture conflict reconciliation and focused fitness-test gaps;
   define and evaluate the Wave 0 gate before Wave 1.

Each task requires a separate DeepSeek brief and Astra evidence review. No task
has been dispatched. No API, schema, permissions, numerical behavior, release
or desktop behavior has changed.
