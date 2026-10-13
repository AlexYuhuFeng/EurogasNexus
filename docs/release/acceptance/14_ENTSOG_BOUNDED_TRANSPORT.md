# 14 — ENTSOG bounded transport implementation and integration handoff

Date: 2026-10-13 (+08). Worker: GPT-6.1 Sol. Integration reviewer: Astra, pending.
Scope: bounded transport, coordinated ingestor/worker integration, protocol and
transaction fixtures, and a bounded public read-only probe.
This is not provider certification, production acceptance or evidence of live ingestion.

## Delivered files and current boundary

- `src/eurogas_nexus/ingestion/entsog_transport.py`: real synchronous public HTTP
  transport for operationaldatas, connectionpoints and operatorpointdirections.
- `src/eurogas_nexus/ingestion/entsog_ingestion.py`: exact raw archival and
  canonical savepoints using existing tables and repositories.
- `src/eurogas_nexus/db/repositories/entsog_observation_persistence.py`:
  ENTSOG append-or-verify safety wrapper, with stable revision refusal codes.
- `scripts/ops/ingest_public_sources.py`: coordinated ENTSOG integration.
- `scripts/ops/run_public_ingestion_worker.py` and `run_dataops_scheduler.py`:
  explicit date-window pass-through and truthful configuration/partial outcomes.
- `src/eurogas_nexus/ingestion/public_sources.py`: optional actual receipt for
  the two ENTSOG observation normalizers; provider update remains metadata.
- `src/eurogas_nexus/application/dataops_runtime.py`: warning-qualified successful
  runs register successful jobs, retaining the warning-qualified run status.
- `tests/ingestion/test_entsog_transport.py`, `tests/fixtures/entsog_protocol.py`,
  `tests/unit/test_ingest_entsog_bounded.py`,
  `tests/integration/test_entsog_bounded_persistence_postgres.py`, and focused
  additions to `test_dataops_scheduler_script.py`, `test_dataops_runtime.py` and
  `test_public_ingestion_worker.py`.
- This report. Local probe evidence: `.dnx-out/entsog-transport-20261013/probe.json`.

After parent authorization and release of shared ingestor ownership, the three
ENTSOG routes now consume the bounded module. GIE ingestion, persistence helpers
and normalizer text slices match their pre-integration SHA256 fingerprints exactly
(`.dnx-out/entsog-transport-20261013/gie-preservation.json`). The primary execution
checkpoint remains parent-owned. There were no live business database writes,
source enable/certification changes, credential changes, service restarts, Docker
actions, installs, commits or pushes. The initial guarded test-database attempt
and readiness probe timed out. After independently authorized parent runtime
recovery, nine isolated PostgreSQL fixture tests passed; test-database public
tables remained unchanged and no test schemas remained.

## Primary protocol evidence

[Official ENTSOG TP API manual v3.0, dated 2025-10-01](https://transparency.entsog.eu/api/archiveDirectories/8/api-manual/ENTSOG_TP_API_UserManual_v3.0.pdf)
was inspected through web browsing. Sections 2.1 and 2.4.3 describe JSON and limit
(default 100, unlimited -1), and show offset/count/total metadata. Section 2.4.6
documents ascending sorting by one field via `sorting`. The manual advises
filtered queries and controlled retries; queries have a 60-second execution limit.
It does not establish a snapshot token or a precise uniform meaning of total.

The following are **observations**, not promises inferred from that manual:

- Tiny initial offset0/2 probes returned distinct provider IDs across all three
  endpoints, with `limit=2` and `sort=id` acknowledged by `meta.sort=id`.
- The documented `sorting=id` was ignored in one-record probes on all three
  endpoints: `meta.sort` was empty. The implementation uses the observed `sort`
  parameter and refuses missing/wrong acknowledgement.
- `meta.total` was 2 on both distinct two-record operational/OPD pages. In the
  later connectionpoints probe, `extended=1` made total 789 on both pages.
  The transport preserves total but never treats it as a uniform grand total.

Exact public endpoint roots:

- [Operational data](https://transparency.entsog.eu/api/v1/operationaldatas)
- [Connection points](https://transparency.entsog.eu/api/v1/connectionpoints)
- [Operator point directions](https://transparency.entsog.eu/api/v1/operatorpointdirections)

Every exact query URL used by the final implementation probe is in the local
evidence JSON, alongside the post-body receipt and exact raw-body hash.

## Implemented behavior

Only the three fixed HTTPS endpoint paths are selectable. Query filters are
allowlisted; callers cannot inject limit, offset, sorting or credential parameters.
Every response is validated for the requested dataset array, object records,
nonempty provider IDs, integer metadata, exact limit/offset echo, count equal to
array length, count within requested limit and acknowledged id sort. Requested
indicators are checked exactly, including case. Repeated provider IDs within or
across pages fail the batch, including a repeated ID whose value changed.
Distinct provider IDs are preserved without inventing canonical deduplication.

Explicit offset advances by the number of returned records. Final requests can
lower limit to stay inside the record budget. Exhaustion requires a short/empty
page; reaching a full record/page budget is always partial, including a dataset
whose last record happens to align exactly with the budget. Result fields carry
complete, stop_reason, page/record counts, budget and a source reference.
`require_complete()` refuses partial results. Empty provider results remain an
honest zero-record transport result; an ingestor must not interpret them as
successful canonical ingestion without its own empty-data gate.

`complete=true` means **offset traversal exhausted for that query**. It never
means full history or an atomic provider snapshot. The result always declares
`snapshot_consistent=false` and
`completeness_basis=offset_exhaustion_not_snapshot`. Inserts/deletions between
pages can cause omissions that this API cannot prove absent. Sort acknowledgement
and overlap refusal are useful checks, not snapshot consistency proof.

Each immutable page retains exact decompressed UTF-8 response bytes and their
SHA256. A fresh decoded copy prevents normalizers from mutating archive bytes.
Receipt is taken after the entire body is read; aggregate receipt is the latest
page receipt. `raw_archive_values()` supplies the existing archive repository
arguments, including exact payload_text, decoded payload_json, actual page count
and receipt. A page reference hashes the exact request URL, so Physical Flow and
each capacity indicator have distinct lineage. `lineage_metadata(archive_id=...)`
is for stamping rows **after** the caller has actually persisted that page.
It does not itself prove or perform archival.

Application safety ceilings are 1000 records/page, 50 pages, 50,000 records and
2 MiB of decompressed response bytes/page; these are not claimed ENTSOG limits.
Requests have a configurable timeout up to 60 seconds, three attempts maximum,
and retry only network/timeouts or 429/500/502/503/504. Backoff/Retry-After is
bounded at 30 seconds. Redirects are refused per request even with an injected
client configured to follow them. Provider bodies and original transport
exceptions never appear in stable error messages or chained tracebacks.

## Validation evidence

Existing installed CPython 3.12 runtime and `.dnx-deps;src` were used; no install.

- `python -m pytest tests/ingestion/test_entsog_transport.py -q`: **88 passed**.
  Two existing Starlette/AnyIO dependency deprecation warnings; no failures.
- Ruff check of both new Python files: **PASS**.
- Public probe through the **new module**, 2026-10-12T21:24:37Z–21:24:42Z
  (2026-10-13 05:24 +08): four queries, two pages each, two records/page,
  eight successful HTTP 200 reads, no DB. Each returned four records and
  `complete=false`, `stop_reason=operator_record_budget`, snapshot false.

| Query | Filters | Observed total per page |
| --- | --- | --- |
| connectionpoints | extended=1 | 789 / 789 |
| operatorpointdirections | hasData=1 | 2 / 2 |
| operationaldatas | Physical Flow, 2026-10-10 to 2026-10-11, day | 2 / 2 |
| operationaldatas | Firm Technical, same one-day query | 2 / 2 |

The probe proves bounded transport/envelope behavior only. It did not prove
normalization, historical completeness, timezone semantics, rights, freshness,
persistence or supplier acceptance. Physical-flow IDs include distinct NA0/NA1
provider entries; returning them is not proof of four usable flow observations.

Negative tests cover invalid bounds/configuration before send, metadata/type
errors, wrong dataset/error envelope, malformed UTF-8/JSON, missing sort echo,
overlapping/revised IDs, wrong indicators, record/page truncation, exact receipt
after streaming completion, raw-byte/hash/copy preservation, distinct capacity
request lineage, HTTP/auth failures, redirects, bounded rate limits, retries,
timeouts/network failure, response byte ceiling and naive receipt clocks.

## Coordinated integration steps remaining

These initial handoff steps are now implemented in the coordinated source change:

- All completed query pages, including four capacity indicator queries, archive
  exact UTF-8 response text/digest and their own post-body receipts. A later query
  transport failure retains already completed queries and the failed query's
  successfully validated prefix pages without canonical writes. The prefix is
  explicitly partial with `transport_failed`; invalid/error response bodies are
  refused and never treated as validated pages or canonical data.
- Each canonical row carries its actual page archive ID/hash/request/receipt.
  Canonical availability is that receipt; provider `lastUpdateDateTime` is
  retained separately. No observed time is taken from run start.
- Each observation query must normalize at least one usable row. One empty
  capacity query refuses the entire canonical batch; raw evidence survives.
  Skipped records are counted. Bounded observation success is explicitly
  `SUCCEEDED_WITH_WARNINGS`, including the scheduler's quality issue.
- Reference queries must both exhaust and each yield usable rows. Any partial
  query refuses all replacement/deletion while retaining archives. Scoped
  replacement runs inside a savepoint, preserving other-source topology.
- Generic upsert still cannot represent revision history. ENTSOG now reuses its
  existing row-lock/ON CONFLICT append-or-verify algorithm with ENTSOG semantic
  fields. Unchanged polls preserve the entire original canonical row and lineage.
  Changed measurements/periods/directions/units/types refuse the whole canonical
  batch with `entsog_revision_requires_history`; no revision is silently backdated.
  No revision schema or migration was added. Provider metadata-only changes are
  excluded from semantic equality and retained in the newer raw archive.

Operational observations require explicit `--entsog-from YYYY-MM-DD` and
`--entsog-to YYYY-MM-DD`, with 0 < range <= 31 days (an application bound).
There is no inferred default historical interval. `--limit` is a record budget
**per query**; capacity can receive up to four times it across four indicators.
`--entsog-page-size` (default100) and `--entsog-max-pages` (default50) are separate
ingestor options. The existing entitlement/certification/operator-disable gates
still precede HTTP fetching.

Both worker and dataops scheduler pass explicit dates. Missing/invalid windows
fail ENTSOG preflight before subprocess. A mixed recurring worker continues
its independent selected sources and emits degraded status (bounded completion
exit2); ENTSOG-only misconfiguration fails before supervision. The scheduler
continues other sources and includes persistent `configuration_blocks` even on
iterations with no newly failed run; bounded completion exits2 when unconfigured.
Warning-qualified successful runs retain their warning status and successful job.
A bounded worker invocation returns1 if any iteration exhausts retries, while
continuing subsequent iterations; recovered retries and successful bounded partial
warnings return0. Missing-window mixed-source degradation retains exit2. The
scheduler rejects malformed report/source shapes, missing result sources,
false success flags and non-integer/negative counters as `BAD_RESPONSE`.

This supplies bounded **fixed-window** scheduling only. The fixed dates do not
roll forward, and scheduler-created window timestamps are not silently converted
to provider date filters. Parent owns the remaining rolling-date, overlap/replay,
expiry and backfill policy. Default customer Compose was not changed. A full
working current-feed scheduler or complete historical backfill is **not accepted**.

## Coordinated validation and remaining gates

Final focused invocation on the existing installed runtime:

```text
python -m pytest tests/ingestion/test_entsog_transport.py
  tests/unit/test_ingest_entsog_bounded.py tests/unit/test_dataops_scheduler_script.py
  tests/unit/test_public_ingestion_worker.py tests/ingestion/test_public_source_ingestion.py
  tests/ingestion/test_source_timezone_contract.py tests/unit/test_ingest_public_sources.py
  tests/unit/test_ingest_script_gates.py tests/unit/test_ingest_gie_revision_safe.py
  tests/unit/test_ingest_gie_credential_gate.py tests/unit/test_dataops_runtime.py
  tests/unit/test_dataops_observability.py tests/unit/test_public_ingestion_upsert.py
  tests/integration/test_entsog_bounded_persistence_postgres.py -q
```

**199 passed, 9 skipped, 2 existing dependency deprecation warnings, 15.32s.**
The nine skips are explicitly PostgreSQL-only tests without a configured test
URL in that invocation; they are not successful transaction evidence. Ruff check
of all changed Python files and transport tests: **PASS**.

The separate real PostgreSQL attempt was restricted to the existing loopback
51356 test database `nexus_verify`, using unique `entsogtest_<uuid>` schemas only.
It produced no test result because the stopped Docker runtime left PostgreSQL
unreachable. The owned hanging test process was stopped; the fixture now uses a
five-second connection timeout. A separate read-only `SELECT 1` connection probe
returned `TimeoutError` within that bound. This worker did not restart or replace
the database. The initial block is **superseded by the recovered-runtime results
below**, not retrospectively reclassified as a passing invocation.

On 2026-10-13T03:49:50Z–03:49:53Z (11:49 +08), after parent independently
recovered the same existing PostgreSQL container, the guarded `nexus_verify`
invocation ran:

```text
python -m pytest tests/integration/test_entsog_bounded_persistence_postgres.py -q
```

**9 passed, zero skipped, 2 existing dependency warnings, 2.84s.** Actual
PostgreSQL insert/unchanged verification, mixed revised/new batch rollback,
exact archives, empty capacity refusal, archive-group rollback, partial reference
preservation, scoped replacement and replacement-exception rollback all passed.
Connections are bounded to5s; test and cleanup transactions set statement timeout
10s / lock timeout5s. All writes use disposable UUID schemas with a local search
path. Before/after read-only catalog and full public-table row-count/SHA256 checks
show **zero new ENTSOG schemas remaining and public tables unchanged**. Evidence:
`.dnx-out/entsog-transport-20261013/postgresql-verification.json` (no credentials).
No live provider was fetched or business database modified by these tests.

Parent review then identified a bounded worker exit-code defect. The correction
and scheduler report-shape refusal were checked separately:

```text
python -m pytest tests/unit/test_public_ingestion_worker.py
  tests/unit/test_dataops_scheduler_script.py tests/unit/test_ingest_entsog_bounded.py -q
```

**38 passed, 2 existing dependency warnings, 1.06s.** This verifies exhausted
configured-worker retries exit1, continued supervision after failure, recovered
retry exit0, successful partial-warning exit0, configuration degradation exit2,
window pass-through, invalid scheduler reports/counters and unchanged dispatch
refusals. The199-test suite was not repeated after this narrow correction.
Ruff checks passed for the changed Python files. Final source hashes for the
customer image rebuild are in `integration-verification.json` in the same folder.

Next integration gates:

1. Parent independently reviews the nine now-passing PostgreSQL transaction
   results and cleanup provenance; this is fixture evidence, not live ingestion.
2. Astra reviews canonical semantic-field coverage, reference replacement based
   on non-snapshot traversal exhaustion, receipts and retained authorization gates.
3. Review and implement a rolling-window/replay policy before claiming the full
   scheduler works for current feeds. Choose any historical backfill separately.
4. Rebuild/reverify the customer image: the independently verified existing image
   predates this integration and does not contain these final source changes.
5. Complete source rights/certification, real normalization/freshness/timezone and
   customer workflow acceptance before any separately authorized live ingestion.

The primary execution checkpoint remains parent-owned. Astra integration review,
certification, source rights/attribution and customer acceptance remain open.
