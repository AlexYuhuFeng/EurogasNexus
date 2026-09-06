# Target Registry (CR-14)

Source: `src/eurogas_nexus/domain/research/targets.py`.

## Definition contract

`TargetDefinition` is a precise label a model is trained or evaluated
against:

- `target_id`, `name`, `description`
- `target_type`: `price`, `spread`, `return`, `flow`, `demand`, `regime`,
  `margin`
- `entity_type`, `entity_id`, `metric`
- `forecast_origin_semantics`, `horizon`, `target_window`
- `unit`, `aggregation`, `label_calculation`
- `availability_delay`, `quality_policy`, `version`

## Seeded targets

| Target id | Metric mapping | Horizon |
|---|---|---|
| `NBP_DA_PRICE_D1` | `market.price.NBP.DAY_AHEAD` | `D1` |
| `TTF_DA_PRICE_D1` | `market.price.TTF.DAY_AHEAD` | `D1` |
| `NBP_TTF_SPREAD_D1` | NBP day-ahead minus TTF day-ahead | `D1` |

Label calculation is the first actual observation at or after
`forecast_origin + horizon` (spread targets require both legs). Simulated
labels are permitted only when the point-in-time policy opts in and are
explicitly flagged `is_simulated=true`.

## Safety rules

- `feature_prohibited_ids()` always includes the target id; DatasetSpec
  validation rejects target/feature overlap.
- Targets are future realizations by design. They are never exposed to
  feature construction; leakage validation treats target rows separately.
- Versioning uses `target_id@version@content_hash8`; a changed label rule
  produces a new target version.
