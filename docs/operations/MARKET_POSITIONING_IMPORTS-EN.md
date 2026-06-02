# Market Positioning Imports

## Purpose

Eurogas Nexus V1 can display imported screen-order observations and indicative
portfolio PnL snapshots in the cockpit. R19 adds the governed internal import
path that loads those observations into PostgreSQL.

This is not order entry, order routing, trade capture, settlement, accounting,
nomination, or auto-trading. Imported records are read-only decision-support
observations of external systems.

## Route

Internal profile only:

```text
POST /api/internal/portfolio/import-observations
```

Required headers:

```text
X-Eurogas-Internal-Token: <operator-managed-token>
X-Eurogas-Principal: <operator-or-job-id>
```

`EUROGAS_NEXUS_INTERNAL_API_TOKEN` must be configured in the backend runtime
environment. The route fails closed before DB access when the token is missing
from the environment, missing from the request, invalid, or when
`X-Eurogas-Principal` is blank. This is a V1 internal operator token gate, not
company SSO/OIDC. The token must never be logged, returned, committed, or stored
in Web, Windows, SDK, or CLI clients.

Release clients must continue to read:

```text
GET /api/v1/portfolio/screen-orders
GET /api/v1/portfolio/pnl-snapshots
GET /api/v1/portfolio/live-summary
```

## Entitlement Requirement

The import route fails closed. Before importing observations, PostgreSQL must
contain granted `entitlement_decisions` rows for each source/dataset pair:

| Observation type | Dataset |
| --- | --- |
| screen orders | `screen-orders` |
| portfolio PnL snapshots | `portfolio-pnl` |

Example entitled pairs:

```text
ICE_OCM / screen-orders
INTERNAL_PNL / portfolio-pnl
```

If entitlement is missing, the whole batch is denied. No observation rows are
written.

## Audit And Run Evidence

Every accepted or denied batch writes:

- one `ingestion_runs` row;
- one `audit_events` row.

Denied batches record `status=failed` and `outcome=denied`. Accepted batches
record `status=succeeded` and `outcome=succeeded`.

## Payload Rules

Each batch must include:

- `batch_id`;
- `source_reference`;
- `screen_orders`;
- `pnl_snapshots`;
- `research_only=true`;
- `human_review_required=true`.

Screen-order observations must include source, venue, side, product, delivery
window, price, quantity, filled quantity, remaining quantity, status, observed
time, source reference, and guardrail flags.

PnL snapshots must include portfolio, valuation time, realized/unrealized/
indicative PnL, early cash value, market value, quantity, valuation basis,
source reference, warning list, and guardrail flags.

## Customer Deployment Rule

Customer-specific EEX, ICE OCM, Trayport, broker, Kpler, Platts, or internal
PnL adapters should normalize into this payload shape, then call the internal
route or repository from a governed backend job. Web, Windows, SDK, and CLI
release clients must not write these tables directly.
