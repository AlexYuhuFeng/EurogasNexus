# Storage And Nomination Assessment Runbook

Chinese companion: [STORAGE_NOMINATION_ASSESSMENT-CN.md](STORAGE_NOMINATION_ASSESSMENT-CN.md)

## Purpose

R34 exposes the validated storage-dispatch and nomination-window engines as
trader-reviewed assessment workflows. These endpoints never submit a storage
booking, nomination, or renomination.

```text
POST /api/optimization/storage-dispatch
POST /api/optimization/nomination-window
```

## Contract

Both endpoints accept `decision_context=SANDBOX_SCENARIO` only.
`RUNTIME_DECISION` returns 422 until DB-owned storage facilities and nomination
window masters are delivered in a later increment.

- Storage dispatch inputs are explicit facility parameters and price periods.
- Nomination inputs are explicit windows and chronological instructions.
- Results carry `human_review_required=True` and persist as
  `optimization_runs` evidence when the runtime DB is configured.

## Example: storage dispatch

```json
{
  "facility": {
    "initial_inventory_mwh": 100,
    "minimum_inventory_mwh": 0,
    "maximum_inventory_mwh": 200,
    "maximum_injection_mwh": 50,
    "maximum_withdrawal_mwh": 50,
    "terminal_inventory_mwh": 100
  },
  "periods": [
    {"period_id": "p1", "market_price_gbp_mwh": 10},
    {"period_id": "p2", "market_price_gbp_mwh": 30}
  ],
  "inventory_step_mwh": 50
}
```

## Example: nomination assessment

```json
{
  "initial_quantity_mwh": 100,
  "windows": [
    {
      "window_id": "within-day",
      "opens_at": "00:00",
      "closes_at": "06:00",
      "maximum_change_mwh": 10
    }
  ],
  "instructions": [
    {
      "submitted_at": "2026-01-01T01:00:00+00:00",
      "requested_quantity_mwh": 115
    }
  ]
}
```

The response contains accepted/adjusted quantities and reason codes
(`ACCEPTED`, `RENOMINATION_CHANGE_LIMIT_APPLIED`,
`OUTSIDE_NOMINATION_WINDOW`). It is an assessment only.

## Runtime decision (R34A)

Both endpoints now accept RUNTIME_DECISION when PostgreSQL masters exist:

- storage: `facility_id` + `gas_day` compose the facility master, latest
  inventory observation, market periods, and as-of FX;
- nomination: `gas_day` composes active window masters; instructions remain
  explicit assessment inputs.

Client-supplied facility/window facts are rejected in RUNTIME_DECISION.
Tables: `storage_facility_masters`, `storage_inventory_observations`,
`nomination_window_masters` (migration `0023`).

## Security acceptance

`scripts/security/run_security_acceptance.py --json` emits automated evidence.
External deployment review remains BLOCKED until penetration test, OIDC TLS
review, backup/restore drill, and owner sign-off are complete. No client
submission action will ever be added by this repository.
