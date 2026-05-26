# Governance Entitlement Contract

## Purpose

`src/eurogas_nexus/governance` owns future policy, entitlement, disclosure, and
controlled-action boundaries.

## Rules

- Entitlement checks must be visible in workflow contracts.
- User-facing analytics must distinguish exploratory analysis from official
  recommendations.
- Restricted actions require audit events and explicit authorization.
- Governance policy text belongs in `docs/policies` or `docs/compliance`.
- Vendor entitlement and export policy must fail closed for unknown commercial
  data.
- Research outputs must remain clearly marked as research-only when relevant.

## Forbidden In Bootstrap

- Legal advice.
- Official trading recommendations.
- Auto-trading authorization.
- Order or nomination submission authorization.
