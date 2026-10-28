# National Gas NTS Actual Demand — Source Contract

Status: accepted source contract for the actual-demand target stage (RFC 0003,
`e0dd7a0`). This is not a production activation, a forecast-accuracy claim, or a
grant of source entitlement. The public page and download are keyless.

## Official source

- Public page: <https://www.nationalgas.com/our-businesses/operational-data/gas-data-portal>
- Fixed download endpoint: <https://data.nationalgas.com/api/find-gas-data-download>
- Method: `GET`, no authentication, official HTTPS origin only, no redirects.
- Approved items only:
  - `PUBOB637` — `Demand Actual, NTS, D+1`; unit `mscm`; provisional initial.
  - `PUBOB652` — `Demand Actual, NTS, D+6`; unit `mscm`; not automatically final.
- Query contract:
  `applicableFor=Y&dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD&dateType=GASDAY&latestFlag=N&ids=<PUBOB637|PUBOB652>&type=CSV`
- An explicit window is required, inclusive, and at most 31 calendar days.
  At most the two approved item ids are accepted. The response is capped at
  2 MiB. Empty responses, header drift, unknown items/units, malformed rows,
  rows outside the window, NaN/infinity, and excess size are refused.
- `PUBOBJ1030` (energy) is not ingested: its native unit is not proven for this
  target. No energy conversion is fabricated.

The `Demand Actual, NTS` role is the official NTS aggregate throughput domain
(NTS Direct Loads + LDZ offtakes + shrinkage + interconnector exports), not pure
household demand or European final consumption. It must not be relabelled as
market price, flow-point, or household consumption.

## CSV contract

Exact header and order:

```text
Applicable At,Applicable For,Data Item,Value,Generated Time,Quality Indicator
```

Each row is preserved as a revision. Native value spellings are stored as text
(for example `176.590`, `0`); values are never converted through binary floats,
rounded, overwritten, or zero-filled. A blank source value is refused. A zero
is a real published value and is not treated as missing or as proof of a ceased
system.

Quality indicators are source labels, not an actuality test:

| Code | Official label |
| --- | --- |
| `L` | Late |
| `A` | Amended |
| `C` | Corrected |
| `E` | Expired |
| `S` | Substituted |
| blank | Unknown |

`A` does not mean “actual”; the item name already carries the actual-demand
role. Unknown non-blank codes are preserved rather than silently remapped.

## Time semantics

- `Applicable At` and `Generated Time` are retained as raw wall-clock strings
  and as parsed timezone-naive values. The CSV timezone is not yet proven.
- `published_at_utc` is nullable and currently unresolved (`NULL`) unless a
  later reviewed contract supplies timezone evidence. Do not infer UTC from
  unrelated REST documentation.
- `received_at_utc` is the actual HTTP receipt. `available_at_utc` uses the
  conservative `LOCAL_RECEIPT_ONLY` basis (equal to receipt for this stage).
- `ingested_at_utc` records the same bounded receipt in this stage.
- The gas-day physical period uses `EU_CAM_UTC_CALENDAR`, expressed as
  05:00–05:00 GB local time (`Europe/London`, including DST), and is stored as
  timezone-aware UTC start/end instants. Historical calendar identifiers are
  not used for new data.

## Identity and append-only persistence

`source_publication_id` is a SHA-256 over the publication identity: source,
approved item, label/term, gas day, and the two raw wall clocks. `record_id`
adds the native value text, unit, quality indicator, provisional status, and
hash schema. Both are stable digests; neither depends on the fetch window URL
or batch.

- Same publication identity and same canonical row: idempotent duplicate.
- Different generated time: a new revision; append it.
- Same publication identity with changed value/quality: refuse atomically with
  the stable code `DEMAND_PUBLICATION_CONFLICT`; never overwrite the prior row.
- Rows are never updated or deleted by the repository.
- The table indexes `(series_key, gas_day)` and `published_at_utc`, and enforces
  `region=GB_NTS`, `unit=mscm`, `term in (D+1, D+6)`, and bounded value/quality
  lengths. `is_provisional` is true for D+1 initial and `NULL` for D+6 because
  D+6 is not automatically final.

The raw CSV SHA-256 and source URL are stored on every row. The existing
governed raw-archive facility may retain the bounded payload text; no new
artifact root is introduced here.

## Operator command

After the additive `0042_national_gas_actual_demand` migration (parent
`0041_job_owner_identity`) is applied to the configured database:

```bash
python scripts/ops/ingest_national_gas_demand.py \
  --database-url "$DATABASE_URL" \
  --date-from 2026-10-01 --date-to 2026-10-31 \
  --ids PUBOB637 PUBOB652
```

The command does not create schema, grant permissions, activate a scheduler, or
expose raw provider errors. It prints only counts and stable status codes. A
successful ingestion is evidence of stored source rows, not forecast accuracy
or production source activation.

## Root verification, 2026-10-28

The focused demand adapter/repository tests passed (18 tests). A separate live
probe downloaded the two approved items for 2026-10-20 through 2026-10-21 and
applied the full Alembic migration chain through revision 0042 to an isolated
PostgreSQL database. It inserted nine D+1 revisions and two D+6 rows. Replaying
both downloads inserted zero rows and classified all eleven as duplicates.
Native units remained `mscm`; publication UTC remained unresolved and
availability used local receipt. This proves this bounded capture and database
replay, without claiming historical forecast accuracy or production activation.

## 2026-10-29 REST publication-time evidence

Root independently queried the official keyless REST publication-time endpoint:
`https://api.nationalgas.com/operationaldata/v1/publications/publishedtime`.
The two-day PUBOB637 request with `latestValue=N` returned HTTP200 and17 revisions,
including exact decimal strings and offset-bearing `applicableAt`,
`generatedTimeStamp` and `createdDate`. Captured response SHA256:
`11f52e0e9d61d740a5d412a8abb5068d2ba7d4f41f65fe88f66855db9c50a5d2`.
This supports a separate REST adapter; it does not retroactively establish the
CSV wall-clock timezone or historic local receipt. Provider-declared publication
and actual receipt must remain distinct evidence bases.

The [official REST documentation](https://data.nationalgas.com/apis/rest-apis)
states SOAP was decommissioned in June2026. Do not invest in the older SOAP
endpoint as the historical-data recovery path. The
[official transition guide](https://www.nationalgas.com/sites/default/files/documents/Gas%20Data%20Portal%20SOAP%20to%20REST%20API%20-%20Transition%20Guide.pdf)
documents publication-time and gas-day queries with explicit date-time offsets.
REST implementation, persistence reconciliation and historical training admission
remain pending; this capture alone does not validate a demand model.
