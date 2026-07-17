# Optimization Layer

Chinese companion: [PHASE_TWO_OPTIMIZATION-CN.md](PHASE_TWO_OPTIMIZATION-CN.md)

## Purpose

The optimization package provides deterministic, trader-reviewed natural-gas
decision support. It does not submit orders, nominations, capacity bookings,
contract amendments, or approvals. Every result carries
`human_review_required=True`.

Implementation:

```text
src/eurogas_nexus/optimization/
```

## Capability Status

| Capability | Module | Status | Public boundary |
|---|---|---|---|
| Capacity-feasible route | `route.py` | stable deterministic model | facade + API |
| Resource-pool allocation | `resource_pool.py` | stable heuristic for the documented separable model | facade + API |
| Capacity-product selection | `capacity.py` | stable exact subset model for curated product sets | facade + API |
| Daily contract dispatch | `contract.py` | stable deterministic one-market model | facade + API |
| Shared-capacity network flow | `network_flow.py` | validated residual-network model | direct Python module only |
| Multi-period storage dispatch | `storage.py` | validated grid-based prototype | direct Python module only |
| Nomination-window assessment | `nomination.py` | validated rules prototype | direct Python module only |

`PhaseTwoOptimizer` is the stable facade for the first four capabilities. The
last three modules are intentionally not exported through that facade or the
public API yet. They need DB-backed input composition, DTO contracts, source
lineage, and product workflow review before exposure.

## Public API

```text
POST /api/optimization/route
POST /api/optimization/resource-pool
POST /api/optimization/capacity
POST /api/optimization/contracts
```

The existing `/api/route-cost/*` endpoints remain available for the DB-backed
route-economics and resource-pool workflow. New optimization endpoints accept
explicit operator-supplied inputs and return the standard envelope:

```json
{
  "data": {
    "human_review_required": true
  },
  "meta": {
    "research_only": true,
    "human_review_required": true,
    "source_references": ["operator-input"],
    "warnings": []
  }
}
```

`meta.research_only` is retained only for shared-envelope compatibility. It is
not part of optimization business-data DTOs.

## Model Definitions

### Capacity-Feasible Route

The route model selects a minimum-tariff directed path after filtering disabled
edges, insufficient edge capacity, and inaccessible TSOs. It represents a
single requested quantity on one path; it does not allocate several resources
against shared edge capacities.

### Resource-Pool Allocation

The resource-pool model schedules minimum-take quantities before optional
positive-margin quantities and respects resource limits, sale-option limits,
and configured TSO-access requirements. It is deterministic, but the current
greedy implementation is not claimed to be a global optimizer for arbitrary
pair-specific eligibility graphs. Shared physical pipeline capacities belong
in the network-flow model.

### Capacity-Product Selection

The capacity model enumerates subsets and selects the lowest-cost combination
covering the requested capacity. This is exact for the supplied finite product
set. It is intended for a curated set, not a large auction universe.

### Contract Dispatch

The contract model applies minimum-take quantities and then dispatches
positive-margin flexibility against one market netback. It does not yet model
take-or-pay accumulation, make-up gas, price optionality, multiple destinations,
or multi-period contract constraints.

### Shared-Capacity Network Flow

The network-flow model is a deterministic, linear, directed,
single-natural-gas-commodity minimum-cost flow. It uses:

- a super source and super sink for multiple supplies and demands;
- supply acquisition costs, physical pipeline tariffs, and destination values;
- forward and reverse residual arcs;
- re-routing when an earlier augmentation blocks a better portfolio result;
- shared physical edge capacities and TSO-access filtering;
- final-flow conservation, capacity, cost, and objective validation.

Strictly negative-margin optional flow is not routed. Zero-margin flow is
routed deterministically. This is not a hydraulic simulation and does not model
pressure, linepack, compressor fuel curves, gas quality, or nominations.

### Storage Dispatch Prototype

The storage prototype uses inventory-grid dynamic programming across supplied
market-price periods. It preserves exact initial and required terminal
inventory levels and validates inventory, rate, efficiency, and cost bounds.
The result is grid-dependent and is not a continuous-storage proof of optimum.

### Nomination-Window Prototype

The nomination module evaluates instructions against supplied time windows and
change limits. It is a decision-support rules model only. It does not submit a
nomination and currently expects the caller to normalize timestamps into the
applicable operator time basis.

## Data And DB Boundary

- The optimization package performs no import-time DB or network access.
- The four public optimization endpoints currently use explicit request data
  and mark the source as `operator-input`.
- Production workflows must compose contracts, tariffs, capacities, TSO
  access, and market observations from PostgreSQL before calling a model.
- Missing DB facts must remain blockers; models must not fabricate them.

## Validation

Focused:

```bash
ruff check src/eurogas_nexus/optimization tests/optimization
pytest -q tests/optimization tests/api/test_optimization_routes.py
```

Repository acceptance:

```bash
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Next Approved Increment

Before exposing network flow, storage, or nomination through the public API:

1. define DB-backed input composition and source-lineage contracts;
2. define additive API DTOs and SDK methods;
3. add bilingual client workflow specifications;
4. add multi-period contract and route coupling where required;
5. evaluate an optional permissive-licensed solver adapter separately;
6. retain trader review and the no-execution boundary.
