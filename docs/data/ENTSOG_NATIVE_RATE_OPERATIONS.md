# ENTSOG native-rate operations

RFC0005 uses native energy/volume rates. It does not convert kWh to mcm with an
assumed calorific value. Schema0044 preserves legacy records and adds native
evidence to the existing observation tables; production databases must be
migrated before running the new ingestor. No source is automatically enabled or
certified by this code. The public ingestion command retains its operator and
provider certification gates.

## Select an explicit public point direction

Use the existing public-source operator command with an explicit date window,
record/page budgets and a known operator-point-direction scope. Repeated
`--entsog-point-direction` values are canonicalized and forwarded to both flow
and capacity queries. Reference/topology queries remain separate. Do not replace
source certification or scope review with a successful HTTP response.

```sh
python scripts/ops/ingest_public_sources.py --source entsog --source entsog-capacity \
  --entsog-from 2026-10-28 --entsog-to 2026-10-29 \
  --entsog-point-direction de-tso-0009itp-00126entry \
  --limit 100 --entsog-page-size 100 --entsog-max-pages 1 --json
```

The same explicit, repeatable (or comma-separated) flag is accepted by both
recurring runners. They canonicalize lowercased, stripped, deduplicated values
and pass them as repeated child flags only to ENTSOG flow/capacity work. The
scheduler forwards them only for its `src-entsog` job; ECB and GIE jobs are
unchanged. Validation happens before the child subprocess, so an invalid scope
refuses clearly before any runner or network work.

```sh
python scripts/ops/run_public_ingestion_worker.py --source entsog \
  --interval-seconds 300 --max-iterations 1 \
  --entsog-from 2026-10-28 --entsog-to 2026-10-29 \
  --entsog-point-direction de-tso-0009itp-00126entry

python scripts/ops/run_dataops_scheduler.py --once \
  --entsog-from 2026-10-28 --entsog-to 2026-10-29 \
  --entsog-point-direction de-tso-0009itp-00126entry
```

Omitting the flag preserves the existing unscoped query behaviour. An unscoped
result is not complete point-direction coverage and may encounter N/A exemption
records; neither setting the flag nor a successful response activates a source.

This example identifies one published direction, not European coverage. The DB
URL and credentials use the existing secure runtime configuration; never put them
in shared command history. The command's raw archive retains exact provider
bytes, request and receipt. Numeric source tokens are parsed directly from those
bytes; legacy binary Floats cannot be recovered as original source text.

The provider can return N/A exemptions with empty values. Such rows remain
missing and may lead to a zero-usable-row refusal; they are never numeric zero.
A bounded unscoped query can encounter exemption records before published data.
The [official API manual, section2.4.8](https://transparency.entsog.eu/api/archiveDirectories/8/api-manual/ENTSOG_TP_API_UserManual_v3.0.pdf)
describes these records. Inspect the actual point-direction scope and remarks.
No incomplete sample is a regional total or a consistent provider snapshot.

## Read exact native rates

Read `/api/physical/flows?quantity_basis=native&point_id=ITP-00126` and the
corresponding capacity path using the normal authenticated client. Limit overflow
is a refusal, so narrow the point or period scope rather than assuming a truncated
set is complete. Both native reads also accept optional `from_utc` and `to_utc`
aware ISO-8601 instants. Supply both or neither; naive instants, a reversed or
equal pair, and a window with `quantity_basis=volume` are refused as 422
`native_window_invalid` without echoing the input. Each instant is normalized to
UTC, and an observation is selected when its half-open period overlaps the
half-open request window: `period_start_utc < to_utc` and
`period_end_utc > from_utc`. This is overlap, not containment, so a longer
technical-capacity row covering a requested daily-flow window remains in scope.
The predicates apply before the native order and `limit + 1` probe; a window that
still exceeds the limit is the existing 400 `native_query_overflow` refusal, never
a silent truncation. When comparing flows with capacity, send the same explicit
`from_utc`/`to_utc` pair to both paths. The window is a captured-observation
selection, not a complete history or provider revision ledger, and it makes no
calorific-value (CV) conversion. No clock time is defaulted when an instant is
omitted.
Use SDK `native_physical.fetch_native_flows_result` and
`fetch_native_capacity_result` to preserve envelope metadata and exact strings.
The existing volume methods withhold native energy and unverified legacy volumes.

A native energy row has null volume. Comparisons require compatible operator,
point, direction, dimension and validity periods. A technical capacity rate is
not a booked right or an execution instruction. No nomination or settlement path
is added. Regional demand/supply models require separately admitted, compatible
units and point-in-time evidence; these observations do not prove model accuracy.

## Verified bounded capture — 2026-10-29

Root captured the declared direction for2026-10-28..29, preserving two flow rows
and one technical capacity row in a dedicated PostgreSQL acceptance database.
Both queries exhausted their offset traversal; neither proves an atomic snapshot
or coverage beyond that direction. Both source units were kWh/d.

| Capture | Exact raw SHA-256 | Rows |
| --- | --- | --- |
|Flow|`0ebb2eeb5eb74a37ed72e8eb676dabc9753c2d122ff7fd61024887576a80928f`|2|
|Technical capacity|`0eee8e3b7ca5842d6ed385067425932de8e29da4204e440789d59d3489d25816`|1|

First persistence inserted2flows/1capacity. A real later recapture inserted zero
and verified2/1unchanged rows; the original receipts and complete projected rows
were preserved. A real loopback HTTP server plus source SDK read the actual PG
rows, preserving flow rates92954921 and738726002.1 kWh/day and capacity416592000
kWh/day as strings. All volume fields remained null; default volume reads had no
rows, and an anonymous native request returned401. The owned server was stopped.
This proves the bounded capture/store/read/SDK path, not installed-wheel or SSO
acceptance, production source activation, regional completeness or predictive
performance. Local raw/probe evidence is in the ignored runtime evidence folder.

PostgreSQL-specific tests exercise real schema, append/replay and transactional
conflict handling in owned test schemas. SQLite fixture tests are fast mechanics
only and do not substitute for those tests. See the execution checkpoint for
current pipeline results and outstanding shared-client adoption.
