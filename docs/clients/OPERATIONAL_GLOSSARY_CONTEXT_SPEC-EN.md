# Operational Glossary Context Spec

## Purpose

The glossary is a trader cockpit surface, not static help text. Selecting a term
must explain what the term means and show the current runtime context that makes
the term operationally relevant.

## Required V1 Behavior

`GET /api/v1/glossary/{term}/context` is the canonical source for glossary
context. Clients must call this API through the SDK/API boundary and must not
open PostgreSQL directly.

The endpoint accepts:

- `lang=en|zh|zh-CN`;
- `duration_start_utc`;
- `duration_end_utc`.

For `Easington Entry Point`, the response must include, where available:

- definition and bilingual description;
- selected duration;
- capacity profile;
- capacity in use as absolute value and percentage;
- related NBP, ICE OCM, and ICIS Heren prices;
- live screen marks;
- route candidates;
- linked upstream resource contracts;
- warnings and data-quality metadata.

For `ICIS Heren`, the response must show price-assessment context and include
`ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA` unless the customer has provided
licensed runtime records.

## Data Sources

The backend builds context from existing runtime tables:

- `capacity_profiles`;
- `flow_observations`;
- `market_observations`;
- `live_market_marks`;
- `route_candidates`;
- `upstream_resource_contracts`.

If PostgreSQL is not configured, the API may return synthetic fallback context,
but the response must mark this through warnings and source references.

## Web Client Rules

The Web and Windows clients must show:

- quick context buttons for common terms such as `Easington Entry Point`,
  `ICIS Heren`, `NBP`, and `ICE OCM`;
- duration selectors before fetching context;
- metric cards for capacity, capacity usage, prices, live marks, and linked
  contracts;
- related routes and contracts as scan-friendly rows;
- warnings visible to the user.

This feature remains decision-support only. It must not create orders,
nominations, approvals, or official trading recommendations.
