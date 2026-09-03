# Data Science Function Catalog

This is the standard function-catalog contract for Eurogas Nexus. It maps
product-facing data-science/trading functions to their canonical REST paths,
SDK methods, MCP tools, and decision contexts.

Source of truth: `src/eurogas_nexus/api/function_catalog.py`.

## Function table

| Function | REST path | Method | SDK | MCP | Decision context |
| --- | --- | --- | --- | --- | --- |
| Route cost | `/api/route-cost/calculate` | POST | `eurogas_nexus_sdk.route_cost.calculate_route_cost` | `calculate_route_cost` | sandbox |
| Route optimization | `/api/optimization/route` | POST | `eurogas_nexus_sdk.optimization.optimize_route` | `optimize_route_sandbox` | sandbox |
| Resource-pool optimization | `/api/optimization/resource-pool` | POST | `eurogas_nexus_sdk.optimization.optimize_resource_pool` | `optimize_resource_pool_sandbox` | sandbox |
| Capacity optimization | `/api/optimization/capacity` | POST | `eurogas_nexus_sdk.optimization.optimize_capacity` | `optimize_capacity_sandbox` | sandbox |
| Contract optimization | `/api/optimization/contracts` | POST | `eurogas_nexus_sdk.optimization.optimize_contracts` | `optimize_contracts_sandbox` | sandbox |
| Storage dispatch | `/api/optimization/storage-dispatch` | POST | `eurogas_nexus_sdk.optimization.optimize_storage_dispatch` | `optimize_storage_dispatch_sandbox` | sandbox |
| Nomination window | `/api/optimization/nomination-window` | POST | `eurogas_nexus_sdk.optimization.optimize_nomination_window` | `optimize_nomination_window_sandbox` | sandbox |
| Portfolio network | `/api/optimization/portfolio-network` | POST | `eurogas_nexus_sdk.optimization.optimize_portfolio_network` | not exposed via MCP | runtime |
| Weather stations | `/api/weather/stations` | GET | `eurogas_nexus_sdk.weather.fetch_weather_stations` | `get_weather_stations` | runtime |
| Weather observations | `/api/weather/observations` | GET | `eurogas_nexus_sdk.weather.fetch_weather_observations` | `get_weather_observations` | runtime |
| HDD/CDD | `/api/weather/hdd-cdd` | GET | `eurogas_nexus_sdk.weather.fetch_hdd_cdd` | `get_hdd_cdd` | runtime |
| Optimization run evidence | `/api/optimization/runs/{run_id}` | GET | `eurogas_nexus_sdk.optimization.fetch_optimization_run` | `get_optimization_run` | runtime |
| Cost observation values | `/api/cost-observations/values` | GET | `eurogas_nexus_sdk.cost_observations.fetch_cost_observations` | `get_cost_observations` | runtime |
| Applicable cost resolution | `/api/cost-observations/applicable` | GET | `eurogas_nexus_sdk.cost_observations.resolve_cost_observation` | `get_applicable_cost` | runtime |

## Design rules

- MCP tools expose only sandbox/runtime read functions; `RUNTIME_DECISION`
  compute functions that create persisted runs are not exposed to MCP unless
  explicitly reviewed.
- REST paths remain the canonical API. SDK and MCP are generated/kept in parity
  with this catalog.
- Every output remains decision support and human-review-required.
- Weather and forecast data must not be fabricated. Empty results include a
  `WEATHER_SOURCE_NOT_CONFIGURED` warning until a real source is ingested.

## Missing future functions

- Weather forecast query
- Weather demand-sensitivity / nowcast
- Additional trading analytics functions

These should be added to this catalog when a real data source and domain model
are implemented.
