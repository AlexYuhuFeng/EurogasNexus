# ECMWF Open Data forecast persistence

Bounded Phase B persistence for the accepted RFC0003 weather-to-demand vertical.
It reuses the existing `forecast_observations`, `series_definitions`,
`canonical_entities` and optional `source_entity_mappings` tables. There are no
migrations, new models, source activations, grants, stations, sites, regions, or
consumer claims.

## Entry point

`append_ecmwf_forecast(session, bindings=..., transport=..., decoded=...,
ingested_at_utc=...)` appends one decoded 2t field to **existing** typed series.
The caller supplies one frozen `EcmwfForecastPointBinding(point_id, series_id,
entity_id)` per decoded point. There is no field-wide series/entity argument and
no default or inferred binding.

The bindings must exactly match the decoded point id set, once each. A missing,
duplicate, extra or mismatched binding is refused before any row is written. The
caller owns the outer transaction. The repository opens a nested savepoint (with
the existing SQLite `BEGIN` helper pattern) so a conflicting batch cannot leave a
partial append; PostgreSQL uses the same savepoint path.

`transport` must be the original `EcmwfField`, not just `decoded.reference`. The
repository checks:

- byte hash against transport and reference;
- request fingerprint against transport/reference/decoder;
- exact run date, cycle, step, validity and reference;
- GRIB2 `2t`/167/K/instant decoder metadata and the reviewed 0p25 grid;
- one decoded point per requested point, in order, with matching point reference;
- finite requested/nearest coordinates, non-negative distances, positive physical
  kelvin and Celsius = kelvin - 273.15 within `1e-9`.

`ingested_at_utc` must be an explicitly aware UTC datetime not earlier than the
actual local receipt completion. Non-UTC offsets and naive values are refused.

## Identity resolution

Series, canonical entities and mappings are read with bounded, batched SELECTs,
not one query per point. For every bound point the repository requires:

- the bound series exists and its `entity_id` exactly matches the binding;
- the series is `degC`, instantaneous, and not declared as legacy licensed
  weather;
- the bound canonical entity exists;
- exactly one approved `ECMWF_OPEN_DATA` point mapping exists for the decoded
  point id and is valid at the forecast validity instant;
- that mapping resolves to the explicitly bound canonical entity, with no missing,
  inactive, unapproved or ambiguous mapping accepted.

The repository never creates a mapping, canonical entity, series or source
certificate internally. A missing mapping therefore refuses the append rather
than manufacturing provenance from the requested point id.

## Rows and provenance

Each point becomes one append-only `ForecastObservationRecord` carrying its own
explicitly bound `series_id` and `entity_id`:

- `source_system = ECMWF_OPEN_DATA` (never legacy licensed `WEATHER`);
- `model_provider = ECMWF`, `unit = degC`, `quality_state = FORECAST`;
- `forecast_issued_at` = model run issue time, `forecast_valid_start` = validity
  instant, `horizon = "<step>h"`;
- `available_at_utc` = the **actual local receipt completion** time;
- `ingested_at_utc` = the caller's explicit ingestion time;
- `provenance` preserves transport/reference/index/GRIB/request hashes, the stable
  source field version, decoder, run and listing references, requested and nearest
  coordinates, receipt, provider `Last-Modified`, availability basis, the explicit
  binding, the series and canonical-entity identities, the one matching mapping
  identity, and the content/batch identities.

Each row records only its own point's `identity_mapping_ids`; it never inherits a
mapping from another point. The batch identity covers the requested location set,
every explicit binding and mapping snapshot, and the capture hashes, so it is a
useful **first-capture audit context**. It is not the point identity: a wider or
narrower request must not make an already persisted point look conflicting.

The per-row content hash binds the immutable point identity, the semantic series,
canonical-entity and mapping snapshots, the decoder/method version, the
coordinates, the unit, and the stored kelvin/Celsius values. It excludes volatile
capture receipt/ingestion times, provider `Last-Modified`, the whole-batch request
or location set, the index hash/row, and the batch identity, so repeating the same
point inside a different request scope is still a duplicate. On a duplicate the
first row's receipt and provenance references are retained; nothing is updated.

Provider `Last-Modified` remains separate metadata. It is not used as historical
first-available proof, and a later receipt never rewrites an already appended row.

The existing `forecast_valid_end` column is non-null. An instantaneous field is
therefore stored as a zero-length interval (`end = start`) while provenance records
`forecast_valid_end: null`, `scope: "instant"` and the schema reason. No model or
migration is changed to fabricate a nullable column.

## Identity and duplicate semantics

The deterministic observation id hashes only the immutable point identity:

- the stable source field version: GRIB SHA-256, run date/cycle, step, validity,
  parameter id/units, and grid type/`ni`/`nj`;
- point id, requested coordinates, and actual nearest grid coordinates;
- the explicit series, canonical entity, and mapping identity;
- the decoder library/version and the point method version.

It deliberately excludes the stored temperature, the whole-batch request
fingerprint and requested location set, the index hash/row, capture receipt and
ingestion times, provider `Last-Modified`, and the batch identity. A forged
temperature value therefore cannot manufacture a fresh observation id: the same
canonical identity, GRIB SHA and decoder/mapping/method version reuse the id, and
different content then refuses the batch atomically.

The same raw GRIB field and point target repeated inside a wider request must
duplicate the existing point rows (first receipt and provenance retained) while
appending the newly requested points. A changed raw GRIB SHA-256 for the same run,
step and validity is a **new source field version**: all of its point observations
are appended as new rows, with the prior rows, receipts and provenance retained and
never updated. Replaying that new version duplicates its rows.

An existing id with different semantic content, including a changed temperature,
canonical-entity content, or the same unversioned mapping with changed semantics,
refuses the whole batch atomically. A material mapping revision is represented by
an explicit new mapping id; that new identity can append its point observations.
There is no run-wide batch-family query forbidding legitimate provider corrections
or mapping revisions. Existing rows are never updated or deleted. A missing
series, missing canonical entity, non-`degC` native unit, non-instant series,
explicit legacy licensed series, or missing/inactive/unapproved/ambiguous
`ECMWF_OPEN_DATA` point mapping is refused before insert.

Temperatures are stored as binary floats and are explicitly approximate physical
values, not financial amounts. The repository does not import NumPy or ecCodes at
module import time.

## Independent root verification

Root ran 24 SQLite repository tests successfully, then replayed 17 complete
session-only invariants against a dedicated PostgreSQL database migrated through
0042. Both checks use explicitly synthetic typed transport/decoder fixtures;
authentic ECMWF decoding is separately evidenced in the source contract.

Coverage includes two points with distinct governed identities, provider
corrections that append new versions, wider requests that reuse existing points,
same-identity content conflicts, retained first receipt, missing/unapproved
mappings, and full outer rollback. A regression compares one point with 64:
lookup SELECT count stays constant and at most six on both databases. This proves
bounded lookup behavior at the transport's point limit, not production throughput.
Ruff passed. Source activation, model fitting and API/SDK/Web consumers remain open.
