# V1 R5 Context Observation Slices ExecPlan

## 1. Goal

Create narrow observation slices for market, physical flow/capacity/outage,
LNG/regas, storage, weather HDD/CDD, and capacity/contract context. Each slice
provides typed models and read-only API routes. All data is synthetic fixtures.
Observations preserve source, timestamp, unit, currency, quality, and freshness.

## Internet Requirement

Internet required: no

Reason: Synthetic fixtures only. No live source calls.

Fallback if offline: Not needed.

## 2. Non-goals

- No live market data, flow data, or weather data fetches.
- No route cost, netback, feasibility, or allocation workflows.
- No DB tables for observation data (fixtures only at this milestone).
- No frontend, desktop, Node, Rust work.

## 3. Files to create/modify

### Models
- `src/eurogas_nexus/observations/__init__.py`
- `src/eurogas_nexus/observations/market.py` — MarketObservation, FxObservation, UnitConversionRule
- `src/eurogas_nexus/observations/physical.py` — FlowObservation, CapacityObservation, OutageEvent
- `src/eurogas_nexus/observations/lng.py` — LngTerminal, LngObservation
- `src/eurogas_nexus/observations/storage.py` — StorageSite, StorageObservation
- `src/eurogas_nexus/observations/weather.py` — WeatherStation, WeatherObservation, HddCddMetric
- `src/eurogas_nexus/observations/contracts.py` — CapacityContract, RouteEligibility

### API routes
- `src/eurogas_nexus/api/routes/v1/market.py` — GET /market/observations, /market/fx, /market/spreads
- `src/eurogas_nexus/api/routes/v1/physical.py` — GET /physical/flows, /physical/capacity, /physical/outages
- `src/eurogas_nexus/api/routes/v1/lng.py` — GET /lng/terminals, /lng/observations
- `src/eurogas_nexus/api/routes/v1/storage.py` — GET /storage/sites, /storage/observations
- `src/eurogas_nexus/api/routes/v1/weather.py` — GET /weather/stations, /weather/hdd-cdd
- `src/eurogas_nexus/api/routes/v1/contracts.py` — GET /contracts/capacity, /contracts/routes

### Updated files
- `src/eurogas_nexus/api/route_registration.py` — register new routers

### Report
- `data/release_v1/r5_context_observations_report.md`

### Tests
- `tests/contract/test_observation_models.py`
- `tests/api/test_context_api.py`

## 5. API impact

~12 new read-only routes across 6 route groups.

## 6. DB impact

No new DB tables. Pure dataclass models served from in-memory fixtures.

## 7. Validation
```
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 8. Acceptance criteria

- Observation models exist for all 6 domain slices.
- Observations preserve source, timestamp, unit, currency, quality, freshness.
- API routes return synthetic fixture data with research metadata.
- No real vendor data committed.
- Default tests DB-free.
