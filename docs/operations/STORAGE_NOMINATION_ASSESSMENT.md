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

## Reading the declared windows: `GET /api/optimization/nomination-windows`

The window masters are the desk's clock, and until this route existed only the
engine read them: a desk could not see the deadline it was trading against.
`GET /api/optimization/nomination-windows?gas_day=YYYY-MM-DD` answers, at the
READ floor, what the deployment declares for one gas day. It exposes a
declaration, not an assessment - no market material, no schedule, no submission.

The route answers three different states, and a surface must not collapse them:

| State | `data.windows` | `meta` |
|---|---|---|
| Runtime DB not configured | `[]` | `source_references: ["runtime-db-not-configured"]`, `missing_inputs: ["RUNTIME_STORE_DATABASE_URL", "nomination_window_masters"]` |
| Configured, no active master | `[]` (with `window_masters_declared: 0`) | `source_references: ["nomination_window_masters"]`, `missing_inputs: []`, `warnings: ["NOMINATION_WINDOWS_MISSING"]` |
| Declared windows | the rows | `source_references: ["nomination_window_masters"]`, `warnings: []` |

An empty list is therefore never self-explanatory: the first row is an *unread*
input and the second is a *measured* zero. Validity is assessed at noon UTC on
the requested gas day, the same basis the RUNTIME_DECISION path uses.

### The clock basis, and its limit

A master declares a **clock**, not an instant: `opens_at` and `closes_at` are
times of day. The engine matches them against the UTC clock time of the
submitting instant (`optimization/nomination.py::_find_window`), so the read
resolves the same basis and states it in `data.time_basis`
(`utc-clock-on-gas-day`). Resolution lives in
`domain/market/nomination_windows.py`, on the gas-day calendar, for two reasons:

- the gas day is 23/24/25 hours long, so the same declared clock resolves an
  hour earlier in summer and the boundary cannot be computed as "now + 24h";
- a master loaded with **local** market times (06:00 CET) rather than UTC clock
  times would be matched one to two hours away from the intended deadline by the
  engine as it stands. The read states the basis it assumed; it does not rewrite
  a deployment's declaration. Recorded as an open question in
  `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md` rather than changed
  silently here.

Two further limits are stated because they are real: a 25-hour gas day can
contain two occurrences of the same clock time and the read returns the first
one, and a window that wraps UTC midnight (`opens_at > closes_at`) is resolved to
the next UTC date, which is how the engine reads it.

Each row also carries the same daily rule's occurrence on the **following** gas
day (`next_gas_day`, `next_opens_at_utc`, `next_closes_at_utc`). A master is a
daily rule, so once the requested day's window has closed the actionable instant
is the next one - and the route resolves it on the calendar rather than leaving a
surface to add 24 hours to a clock, which is wrong across the DST boundaries and
on the 23/25-hour gas days.

## Security acceptance

`scripts/security/run_security_acceptance.py --json` emits automated evidence.
External deployment review remains BLOCKED until penetration test, OIDC TLS
review, backup/restore drill, and owner sign-off are complete. No client
submission action will ever be added by this repository.
