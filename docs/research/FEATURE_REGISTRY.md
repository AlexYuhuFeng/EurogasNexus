# Feature Registry (CR-14)

Source: `src/eurogas_nexus/domain/research/features.py`.

## Definition contract

`FeatureDefinition` is semantic metadata plus a deterministic implementation
reference:

- `feature_id`, `name`, `description`, `category`
- `input_dependencies`: canonical series ids (or other feature ids)
- `output_unit`, `frequency`
- `availability_class`
- `transformation` + `transformation_version`: deterministic implementation
  reference (for example `builtin:NBP_TTF_DA_SPREAD`)
- `lookback`, `missing_data_policy`, `point_in_time_policy`,
  `future_knowledge_policy`
- `owner`, `status`, `metadata`

## Availability classes

| Class | Meaning | Example |
|---|---|---|
| `PAST_ONLY` | Only realized historical values | settled daily price |
| `KNOWN_FUTURE` | Public calendar/schedule known in advance | gas-day calendar |
| `STATIC` | Infrastructure/entity property | interconnector capacity |
| `FORECAST` | A model/source forecast vintage | weather forecast |
| `DERIVED_AS_OF` | Deterministic function of point-in-time inputs | NBP-TTF spread |
| `TARGET_ONLY` | May only ever be a label, never a feature | D1 price |

## Versioning

- `content_hash()` covers the full definition, including metadata.
- `version()` is `feature_id@transformation_version@hash8`; any metadata edit
  changes the hash.
- `feature_dependency_closure()` resolves transitive dependencies
  deterministically.

## Declarative transforms (no code needed)

A feature whose `transformation` is one of the names below is computed from its
declaration alone (`domain/research/feature_transforms.py`), so an analyst adds a
lag or a rolling statistic by registering data, not by asking for a release.

| Transformation | Inputs | Metadata | Value at origin *t* |
|---|---|---|---|
| `identity` | 1 series | `step` | value as of *t* |
| `linear_combination` | 1+ series | `weights` (one per input) | Σ wᵢ·xᵢ as of *t* |
| `lag` | 1 series | `lag_steps`, `step` | value as of *t − k·step* |
| `difference` | 1 series | `lag_steps`, `step` | x(*t*) − x(*t − k·step*) |
| `rolling_mean` | 1 series | `window`, `step` | mean of the last *n* values |
| `rolling_std` | 1 series | `window` (≥ 2), `step` | sample standard deviation of the last *n* values |

Each value is resolved **as of its own cutoff** with the same point-in-time selection
the builder uses at the origin. A lag therefore returns what was known at *t − k*,
not a later revision of that day's value placed on the old date. A missing input at
any cutoff masks the value (no fill). `step` is `"1d"` or `"1h"` style; windows are
capped at 400.

## Seeded features

| Feature id | Transformation | Dependencies | Unit |
|---|---|---|---|
| `NBP_TTF_DA_SPREAD` | builtin | `market.price.NBP.DAY_AHEAD`, `market.price.TTF.DAY_AHEAD` | EUR/MWh |
| `ROUTE_MARGIN` | builtin | `market.price.NBP.DAY_AHEAD` plus explicit route cost context | GBP/MWh |
| `TTF_DA_LAG1` | `lag` 1d | `market.price.TTF.DAY_AHEAD` | EUR/MWh |
| `TTF_DA_CHG1`, `TTF_DA_CHG5` | `difference` 1d / 5d | `market.price.TTF.DAY_AHEAD` | EUR/MWh |
| `TTF_DA_MA20`, `TTF_DA_SD20` | `rolling_mean` / `rolling_std` 20d | `market.price.TTF.DAY_AHEAD` | EUR/MWh |
| `NBP_DA_MA5` | `rolling_mean` 5d | `market.price.NBP.DAY_AHEAD` | EUR/MWh |

## Safety rules

- Target ids are never feature ids; `build_dataset` rejects overlap before
  any row is produced.
- A feature cannot silently `ffill` without a bounded, versioned resampling
  policy.
- The registry is not a commercial feature store and does not train models.
