# ECMWF Forecast Operations

Status: bounded operator procedure for the explicit ECMWF IFS 0p25 `oper` 2t
point-forecast CLI. This is not a production-readiness, source-certification,
model-accuracy or regional-demand claim.

The command is
`scripts/ops/ingest_ecmwf_forecasts.py`. It retrieves only the exact requested
run/cycle/step fields from ECMWF's official open-data origin, preserves the exact
GRIB2 bytes and decoder/transport metadata, and then append-persists the decoded
points through the existing `append_ecmwf_forecast` repository. It never fetches
"latest", never substitutes a different run, and never infers geography, series,
canonical entity, source mapping or certification.

## Root verification — 2026-10-29

The operator CLI captured the authentic 2026-10-29/00 UTC run at steps27 and30
for an explicit London grid request (51.5,-0.1). Linux canonical Python3.11.12
with isolated ecCodes2.50 decoded and archived both fields. Dry-run reported no
database attempt. A separate persistence run inserted two rows in the dedicated
PostgreSQL acceptance database; a later capture inserted zero rows and verified
two duplicates. A subsequent repository read and strict projection matched both
archived GRIB SHA-256 values and the original receipt timestamps, demonstrating
first-receipt preservation across the replay.

| Step hours | GRIB SHA-256 | Projected temperature degC |
| --- | --- | --- |
|27|`36c9d11e8216c51bde5996321f99a0e5e85472e7aa955250b31d75803f2bfcf9`|8.294549560546898|
|30|`93174eb8efda4c5535aea5888719800b8bae31dca098bd8f14515af88af2efe8`|7.90766296386721|

Identity rows were explicit local test fixtures, not production regional mapping
approval. No provider certification, entitlement or source activation was added.
The two instants do not constitute a complete gas-day weather feature or prove
regional demand accuracy. Raw captures and the verification JSON remain in the
ignored local runtime evidence directory. The new CLI tests plus existing capture,
transport, decoder and repository regression tests passed94. They include a real
SQLite repository transaction with one commit and all-row rollback on conflict;
network/decoder fixtures in unit tests are synthetic and separate from this live
capture. The full Python regression and hosted CI remain separate requirements.

## Scope and non-claims

- The product is an instantaneous 2-metre temperature forecast on the IFS 0.25
  degree grid. A decoded value is a nearest-grid-cell forecast value for an
  explicitly supplied location; it is **not** an observing-station reading.
- The command makes no HDD/CDD, demand-model, regional-weight, regional-aggregate
  or predictive-accuracy claim.
- The command does not activate a source, create provider/dataset certification,
  grant entitlements, create schema, create series/entities/mappings, or read
  provider credentials. ECMWF Open Data is keyless; database access uses the
  configured runtime URL only.
- A successful persistence run proves that these exact fields were captured,
  decoded, archived and appended under the existing repository's identity rules.
  It does not by itself certify the source, the mapping evidence or a production
  deployment.

## Prerequisites

### Runtime and decoder

- Python 3.11+ with the repository's normal runtime dependencies, including
  `httpx`.
- The optional `ecCodes` Python binding with GRIB2 definitions. The current
  reviewed baseline is ecCodes 2.50.0 or newer. The CLI adds no dependency and
  does not install or repair ecCodes.
- Outbound HTTPS access to `data.ecmwf.int` (the CLI is fixed to the official
  ECMWF origin; the AWS replica is not an option of this command).
- The decoder is loaded lazily at the ecCodes boundary; a missing or
  incompatible binding fails with `ecmwf_decoder_unavailable` or
  `ecmwf_decoder_version_unsupported` rather than falling back to synthetic
  values.

The Linux Python 3.11 / ecCodes 2.50 decoder has been verified against an
authentic ECMWF IFS 0p25 `oper` 2t capture. Windows ecCodes embedded-definition
operation failed in the isolated probe and remains **unverified/open**; do not
claim Windows CLI decode support until a separate review verifies it. Running the
CLI through a Linux backend is a separate operational decision from decoder
support on Windows.

### Schema and approved identities (0043)

The database must already be at the repository's reviewed Alembic baseline
including schema `0043`, with the existing `forecast_observations` table and the
existing research identity tables. The CLI performs no migration and no
schema creation.

Before persistence, the following reviewed rows must already exist. The
repository validates them inside the caller transaction; the CLI does not create
or repair them.

- A `CanonicalEntityRecord` with `canonical_entity_id` equal to the binding's
  `entity_id`.
- A `SeriesDefinitionRecord` with `series_id` equal to the binding's `series_id`
  and `entity_id` equal to the binding's `entity_id`. Its `native_unit` must be
  `degC` (the canonical degree-C symbol is also accepted), its `temporal_type`
  must be instantaneous, and it must not be declared as legacy licensed weather
  (`WEATHER`, `LICENSED`, `LICENSED_WEATHER`, `COMMERCIAL_WEATHER`).
- Exactly one approved active `SourceEntityMappingRecord` for
  `source_id = ECMWF_OPEN_DATA`, `source_identifier = point_id`, and
  `canonical_entity_id = entity_id`. `mapping_status` must be `ACTIVE`,
  `valid_from_utc` must be at or before the forecast validity instant,
  `valid_to_utc` must be null or after that instant, and
  `source_entity_type` must be `GRID_POINT` or `POINT`. Zero mappings or more
  than one active mapping is a refusal, not a deduction.

Provisioning these identities is a separate reviewed data-governance action.
This runbook deliberately contains no DDL or identity-insert recipe. If
`0043` (or the required research identities) is absent, stop and resolve the
deployment prerequisite outside this CLI.

### Database URL precedence

`--database-url` is optional. A non-blank explicit value wins. Otherwise the
existing `resolve_database_url()` order applies:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN`

Blank values are skipped and the selected value is stripped. There is no
built-in fallback URL. `--dry-run` never resolves or opens the database, even if
`--database-url` is present. The resolved URL is never printed; prefer supplying
it through the environment rather than shell history or process arguments.

## Bindings JSON

`--bindings` is a path to a UTF-8 JSON array. It must contain **1 to 64**
objects. Every object must contain **exactly** these five keys:

```json
[
  {
    "point_id": "example-london",
    "latitude": 51.5074,
    "longitude": -0.1278,
    "series_id": "example-series-london-2t",
    "entity_id": "example-entity-london"
  },
  {
    "point_id": "example-manchester",
    "latitude": 53.4808,
    "longitude": -2.2426,
    "series_id": "example-series-manchester-2t",
    "entity_id": "example-entity-manchester"
  }
]
```

Rules enforced before any network call or artifact-directory creation:

- `point_id`, `series_id` and `entity_id` are non-empty trimmed strings.
  `point_id` is at most 64 characters; duplicate `point_id` values are refused.
- `latitude` is a finite JSON number in `[-90, 90]`; `longitude` is a finite
  JSON number in `[-180, 180]`. Booleans and numeric strings are refused.
- Extra keys (for example a station, region, country or inferred geography key)
  are refused. Missing keys are refused. There is no coordinate default,
  geocoding, centroid or point-id parsing.
- `point_id` is the explicit `ECMWF_OPEN_DATA` `source_identifier` for the
  existing mapping. `series_id` and `entity_id` are existing reviewed
  identities, not values this command creates.

The same binding set is used for every requested step.

## Command surface

All of the following are required except `--database-url` and `--dry-run`:

| Argument | Meaning |
| --- | --- |
| `--run-date YYYY-MM-DD` | Explicit UTC run date, from `2023-01-18` through today; no future date. |
| `--cycle-hour` | Explicit ECMWF cycle: `0`, `6`, `12` or `18` (zero-padded `00`, `06`, `12`, `18` also accepted). |
| `--steps` | One to twelve unique comma-separated steps in hours, from `0` to `360` in 3-hour increments. |
| `--bindings JSON` | Explicit 1-64 row bindings array described above. |
| `--output-dir DIR` | A **new, non-existing** artifact directory. |
| `--database-url` | Optional explicit SQLAlchemy URL; otherwise the env precedence above. |
| `--dry-run` | Capture/decode/archive only; no DB resolution or touch. |

There is no `--source`, no "latest" option, and no run/step substitution. The
source is fixed to the official ECMWF open-data origin. The requested run is
echoed in the success JSON and checked against every returned field before its
bytes are archived.

## Dry run

Use an explicit new directory for every attempt:

```bash
python scripts/ops/ingest_ecmwf_forecasts.py \
  --run-date 2026-10-28 \
  --cycle-hour 0 \
  --steps 0,3,6,9 \
  --bindings /srv/eurogas/ecmwf/bindings.json \
  --output-dir /srv/eurogas/ecmwf/20261028T00Z-dryrun \
  --dry-run
```

Dry-run still validates the arguments, bindings and request bounds, creates the
new output directory exclusively, fetches each exact field, decodes it, and
writes the GRIB2 and metadata JSON artifacts. It does **not** import the database
repository/session path, resolve a database URL, open a session, or write rows.
If `--database-url` is supplied it is ignored. No ingestion clock value is
claimed in dry-run output.

## Persistence transaction

Use a different new output directory from the dry run. The database URL can come
from the environment:

```bash
export RUNTIME_STORE_DATABASE_URL='postgresql+psycopg://operator@db.example/eurogas'
python scripts/ops/ingest_ecmwf_forecasts.py \
  --run-date 2026-10-28 \
  --cycle-hour 0 \
  --steps 0,3,6,9 \
  --bindings /srv/eurogas/ecmwf/bindings.json \
  --output-dir /srv/eurogas/ecmwf/20261028T00Z-persist
```

Or supply the URL explicitly:

```bash
python scripts/ops/ingest_ecmwf_forecasts.py \
  --run-date 2026-10-28 \
  --cycle-hour 0 \
  --steps 0,3,6,9 \
  --bindings /srv/eurogas/ecmwf/bindings.json \
  --output-dir /srv/eurogas/ecmwf/20261028T00Z-persist-2 \
  --database-url "$RUNTIME_STORE_DATABASE_URL"
```

The order is deliberate:

1. Parse and validate every argument, binding, coordinate, run bound and step
   bound; construct all typed requests.
2. Create the output directory exclusively; fail if it already exists or appears
   during the run.
3. Retrieve, validate and decode every requested field from the official source,
   and archive every GRIB2 and metadata JSON pair. A later request cannot start
   before an earlier pair is archived.
4. Sample `ingested_at_utc = datetime.now(UTC)` only after all requested fields
   have been received and archived. If that clock is earlier than any actual
   transport receipt (clock rollback), fail before DB access.
5. Resolve the database URL only at this point.
6. Open **one caller-owned transaction** and call `append_ecmwf_forecast` once
   for every requested step, passing the explicit
   `EcmwfForecastPointBinding` values and the same post-receipt ingestion clock.
   Commit once after all steps succeed.

Any argument/identity/conflict/database failure raises before the single
commit, so the transaction rolls back all database rows from this run. Artifacts
already written are not deleted: they are an explicit partial capture. A failed
persistence can therefore leave a complete artifact set with zero committed DB
rows; the error JSON distinguishes `artifacts_complete`, `partial_artifacts` and
`database`.

The repository, not the CLI, performs approved-identity resolution. It rejects
missing/ambiguous mappings, wrong entity/series relationships, non-`degC`
series, legacy licensed series, non-active or out-of-validity mappings, and
semantic conflicts. Replaying an identical capture is idempotent: existing
observations are counted as duplicates, not inserted again. Changed content
under the same identity is a conflict and rolls back the whole transaction.

Receipt timestamps are the actual local transport receipt times. The provider
`Last-Modified` value, when present, is retained only as provider metadata; it is
never converted into a historical local receipt or used to reconstruct a past
availability time.

## Artifacts and stdout

For each requested step the CLI creates, exclusively and without overwriting:

- `step_NNN.grib2` - the exact GRIB2 message bytes selected by the official
  index and fetched by HTTP range.
- `step_NNN.json` - capture metadata.

The metadata JSON contains the schema/source/research basis, run/cycle/step,
validity, exact GRIB file name and size, request/GRIB/index/selected-row hashes,
the actual `receipt_completed_at_utc`, the full transport `asdict` (with
`grib_bytes` removed) and the full decoder `asdict`. Dates and datetimes are
serialized as ISO strings. It contains **no** GRIB bytes, database URL,
credentials or bindings identities beyond the point IDs/coordinates already in
the transport request.

No run-level manifest or report file is written. The capture is the per-step
GRIB/metadata pair; operational evidence is the JSON on stdout (success) or
stderr (failure).

Success prints one sorted JSON object to stdout and exits `0`. Stable top-level
keys include:

```json
{
  "status": "ok",
  "dry_run": false,
  "persisted": true,
  "source": "ecmwf",
  "research_basis": "explicit_point_bindings_instantaneous_2t_no_demand_or_regional_aggregate",
  "run_date": "2026-10-28",
  "cycle_hour": 0,
  "steps": [0, 3, 6, 9],
  "bindings": 2,
  "fields_requested": 4,
  "fields_received": 4,
  "fields_decoded": 4,
  "fields_archived": 4,
  "fields_persisted": 4,
  "rows_seen": 8,
  "inserted": 8,
  "duplicates": 0,
  "hashes": [
    {
      "step_hours": 0,
      "request_sha256": "…",
      "grib_sha256": "…",
      "index_sha256": "…",
      "index_row_sha256": "…",
      "receipt_completed_at_utc": "…"
    }
  ],
  "output_dir": "/srv/eurogas/ecmwf/20261028T00Z-persist",
  "artifacts_complete": true,
  "partial_artifacts": false,
  "database": "committed",
  "ingested_at_utc": "…"
}
```

Dry-run uses the same shape with `dry_run: true`, `persisted: false`,
`fields_persisted: 0`, zero row counts, `database: "not_attempted"`, and
`ingested_at_utc: null`.

Failure prints one sorted JSON object to **stderr** and exits `2` (the National
Gas operator CLI convention). It includes `status: "error"`, a stable `code`, a
safe exception `type`, the requested run/steps and counts, any hashes of already
archived steps, `output_dir`, `artifacts_complete`, `partial_artifacts`,
`database`, and `ingested_at_utc`. It never prints a raw exception message,
traceback, database URL, credentials, provider payload or manifest.

Common codes include:

- `INVALID_ARGUMENTS`, `INVALID_RUN_DATE`, `RUN_DATE_OUT_OF_BOUNDS`,
  `INVALID_CYCLE_HOUR`, `INVALID_STEPS`
- `BINDINGS_NOT_FILE`, `BINDINGS_TOO_LARGE`, `BINDINGS_JSON_INVALID`,
  `BINDINGS_COUNT_INVALID`, `BINDING_KEYS_INVALID`,
  `BINDING_POINT_ID_INVALID`, `BINDING_POINT_ID_DUPLICATE`,
  `BINDING_COORDINATES_INVALID`, `BINDING_SERIES_INVALID`,
  `BINDING_ENTITY_INVALID`
- `OUTPUT_DIR_EXISTS`, `OUTPUT_DIR_CREATE_FAILED`, `ARTIFACT_EXISTS`,
  `ARTIFACT_WRITE_FAILED`, `ARTIFACT_METADATA_INVALID`
- `ECMWF_SOURCE_MISMATCH`, `ECMWF_RUN_MISMATCH`,
  `ECMWF_GRIB_HASH_MISMATCH`, `ecmwf_decoder_unavailable`,
  `ecmwf_decoder_version_unsupported`
- `DATABASE_URL_REQUIRED`, `INGESTION_CLOCK_BEFORE_RECEIPT`
- `ECMWF_FORECAST_VALIDATION_ERROR`, `ECMWF_FORECAST_SERIES_INVALID`,
  `ECMWF_FORECAST_CONFLICT`

## Failure and retry rules

- Never reuse an `--output-dir`. The directory is created with exclusive
  semantics and every artifact uses exclusive file creation. A failed run may
  contain a partial GRIB or metadata set; leave it for inspection and start a
  new timestamped directory.
- On failure, inspect `fields_received`, `fields_decoded`, `fields_archived`,
  `partial_artifacts` and `database` in the error JSON. Do not infer committed
  rows from archived files; a rolled-back transaction has no new rows.
- A capture failure before all requested fields is a partial artifact set. A DB
  failure after a complete capture has complete artifacts but no committed
  transaction (unless the error occurred after the single commit; the
  `database` field distinguishes this).
- Do not retry into the same directory and do not overwrite an existing GRIB or
  metadata file. Do not silently change the run date, cycle or steps to make a
  failed request succeed.

## Verification status

Root separately reviews and tests the repository; this runbook does not claim
that its command has passed the full suite. The Linux Python 3.11 / ecCodes 2.50
decoder has been verified on an authentic ECMWF capture. Windows ecCodes
operation remains open as described above. The optional decoder dependency,
license/native-binary closure, public-source rights review and installed
deployment acceptance remain separate gates.

Running this command does not auto-certify the source, activate it, create
provider/dataset certification, promote a demand model, or make the repository
production-ready.

## Related documents

- [ECMWF open-data source contract](ECMWF_OPEN_DATA_SOURCE_CONTRACT.md)
- [ECMWF forecast persistence](ECMWF_FORECAST_PERSISTENCE.md)
