# Operational Glossary Context Spec

## Purpose

The glossary is a trader cockpit surface, not static help text. Selecting a
term must show what the term means and the current runtime data that makes it
commercially relevant: capacity, capacity in use, prices, live marks, route
options, contracts, sources, warnings, and data quality.

## Canonical API

`GET /api/v1/glossary/{term}/context` is the only source for operational
glossary context. Web, Windows, CLI, and SDK callers must use the API or SDK.
No client may open PostgreSQL directly or read backend local data files.

Supported query parameters:

- `lang=en|zh|zh-CN`
- `duration_start_utc`
- `duration_end_utc`

## Required Response Shape

The response must preserve the legacy scalar fields and include the grouped V1
context fields:

- `description`, `description_en`, `description_zh_cn`
- `requested_duration`
- `entity_summary`
- `matched_entities`
- `capacity`
- `capacity_usage`
- `metrics`
- `related_prices`
- `live_market_marks`
- `related_routes`
- `related_contracts`
- `context_sections`
- `related_sources`
- `data_quality`
- `warnings`
- `research_only=true`
- `human_review_required=true`

`capacity_usage` must support selected-duration analysis. When multiple flow
records match the selected duration, the API must return average used capacity,
peak used capacity, utilization percentage, peak utilization percentage, source
references, and observation count. If flow is in `mcm/d` and capacity is in
`MWh/d`, V1 may use the documented assumption `1 mcm = 10,550 MWh` until
calorific-value-specific conversion is available.

## Matching Rules

The resolver must be deterministic and DB-first.

1. Start with the requested term.
2. Add matching glossary term names, aliases, related terms, and source refs.
3. Match runtime records in:
   - `capacity_profiles`
   - `flow_observations`
   - `market_observations`
   - `live_market_marks`
   - `route_candidates`
   - `upstream_resource_contracts`
4. Infer `context_type` from the term and runtime records:
   - `entry_point` for terms ending in or matching entry point records;
   - `exit_point` for exit point records;
   - `hub` for hub glossary records;
   - `venue` for venue glossary records;
   - `price_assessment` for price glossary records or matched price rows;
   - `capacity` for unmatched capacity/flow point context;
   - `generic` only when no stronger runtime or glossary signal exists.
5. Return `TERM_CONTEXT_MAPPING_PARTIAL` only when no dedicated profile and no
   runtime match exists.

Hard-coded examples such as `Easington Entry Point` may remain as profile hints,
but the feature must not be limited to Easington/Bacton. A customer-loaded point
such as `St Fergus Entry Point` must work when glossary, capacity, flow, price,
route, and contract records exist in PostgreSQL.

## Example Behavior

For `Easington Entry Point`, the context should show:

- UK NTS/beach delivery description;
- selected duration;
- capacity profile;
- capacity in use as MWh/d or mcm/d and percentage;
- related NBP, ICE OCM, and ICIS Heren prices;
- live bid/ask/last screen marks;
- route candidates;
- linked upstream contracts;
- warnings and data-quality metadata.

For `ICIS Heren`, the context should show:

- licensed price-assessment description;
- customer-licensed or operator-entered runtime price records where present;
- related screen marks such as ICE OCM/NBP where related terms link them;
- `ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA` unless entitlement and
  customer-loaded licensed data are explicitly present.

## Web And Windows UX Rules

The Web workspace is the single UI source; Windows wraps the built Web client.
The glossary panel must render:

- quick context buttons for high-value terms;
- duration selectors before fetching context;
- matched entity chips;
- metric cards;
- grouped sections for capacity, prices/live marks, routes, contracts, and data
  quality;
- visible warnings.

This feature remains decision-support only. It must not create orders,
nominations, approvals, legal advice, or official trading recommendations.
