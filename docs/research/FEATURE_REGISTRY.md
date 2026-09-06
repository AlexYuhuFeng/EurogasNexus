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

## Seeded features

| Feature id | Dependencies | Unit |
|---|---|---|
| `NBP_TTF_DA_SPREAD` | `market.price.NBP.DAY_AHEAD`, `market.price.TTF.DAY_AHEAD` | EUR/MWh |
| `ROUTE_MARGIN` | `market.price.NBP.DAY_AHEAD` plus explicit route cost context | GBP/MWh |

## Safety rules

- Target ids are never feature ids; `build_dataset` rejects overlap before
  any row is produced.
- A feature cannot silently `ffill` without a bounded, versioned resampling
  policy.
- The registry is not a commercial feature store and does not train models.
