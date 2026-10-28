# EEX TTF NGP Source Contract

Status: **current** (bounded adapter delivered 2026-09-29). Implementation:
`src/eurogas_nexus/ingestion/eex_ngp.py`. Tests: `tests/ingestion/test_eex_ngp_csv.py`.
Timezone declaration: `SOURCE_TIMEZONE_CONTRACTS` entry `EEX` / `ttf-ngp-15min`
(`docs/data/SOURCE_TIMEZONE_CONTRACT.md`).

## 1. Source

| | |
| --- | --- |
| Official page | https://www.eex.com/en/markets/natural-gas/gas-market-transparency |
| File linked by the page | https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_15_Mins.csv |
| Refresh | the page describes the current file as refreshed every 15 minutes |
| Verified shape (bounded operator read, 2026-09-29) | UTF-8 CSV with BOM, `;` delimiter |

Verified header and row shape:

```text
Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let
DD/MM/YYYY;decimal;decimal;Final NGP | Temporary NGP;DD/MM/YYYY HH:MM
```

The verified file contained `Final NGP` and `Temporary NGP` rows, including a Temporary row whose
volume and value were both zero.

## 2. What the values are (and are not)

- `IndexValue` over `IndexVolume` is a **volume-weighted reference index** carrying a
  `Final NGP` / `Temporary NGP` revision status. It is **never an executable bid/ask quote** and
  never a tradable price.
- Canonical rows therefore carry `contract_type`/`price_type` `index`, `executable_quote` false
  and `research_only` true, with product `TTF NGP` — distinct from EEX futures, spot, screen and
  settlement datasets, and from the `EEX_Sim` simulator family (`simulated: false`).
- A zero or missing `IndexVolume`, or a missing `IndexValue`, makes the row **unavailable**: the
  parser records the reason (`zero_volume`, `missing_index_volume`, `missing_index_value`) and
  never fabricates a zero price from a missing or untraded value.
- Canonical rows carry `freshness` `unknown` — the repository's accepted unknown representation
  (`ObservationFreshness.UNKNOWN`), **not** `live`/`fresh` — and `quality_score` 0.0 with
  `quality_assessed: false` and `quality_score_basis: unassessed` in metadata: no source
  freshness or quality expectation is proven, so none is awarded, and an arbitrarily old payload
  is never advertised as live. A future adapter may compute these only against a proven source
  expectation.

## 3. Adapter rules (fail-closed)

Payload-level refusals (`EexNgpParseError`):

- `empty_payload` — nothing to read;
- `unexpected_header` — the five verified columns, their order and their count are required, after
  BOM removal, whitespace collapsing, case folding and `€`/`EUR` equivalence;
- `duplicate_observation_key` — the same `(gas day, timestamp, status)` appears twice, identical
  or conflicting; rows are refused rather than silently deduplicated, and `Final NGP` never
  overwrites `Temporary NGP` because the revision status is part of the natural key;
- `index_value_float_overflow` — an exact `Decimal` index value that cannot be represented by the
  canonical Float `price` column (e.g. a 1000-digit value) is refused; an `inf` is never written;
- `unproven_gas_day_calendar`, `unregistered_gas_day_calendar`, `unattested_gas_day_calendar` —
  the separately evidenced delivery-calendar contract is missing, names a calendar id this
  repository does not register, or carries no evidence (subsection 3.1);
- `naive_retrieval_timestamp`, `timezone_contract_source_mismatch`,
  `timezone_contract_dataset_mismatch`, `unattested_timezone_contract` — governed-contract and
  retrieval-clock misuse (section 4).

Row-level rejections are recorded with row number and reason code, and the payload is then **not
canonicalized as a whole**: `malformed_row`, `invalid_gas_day` (`DD/MM/YYYY`), `invalid_timestamp`
(`DD/MM/YYYY HH:MM`), `unknown_status`, `invalid_index_value`, `invalid_index_volume`,
`negative_index_volume`, plus the DST refusals `ambiguous_local_timestamp` and
`nonexistent_local_timestamp` (section 4). Values are parsed as `Decimal` and must be finite;
volume must be non-negative; a negative index value is kept as published (real indices can be
negative), and the exact decimal strings stay available in metadata (`index_value_exact`,
`index_volume_mwh_exact`). Only plain decimals are accepted: comma decimals, separator characters
and exponent notation are refused loudly rather than reinterpreted (the canonical `price` field
is a float because `market_observations.price` is a Float column; the exact decimal survives in
metadata).

Natural key and IDs: `observation_id = eex-ngp-ttf-<gas-day>-<timestamp>-<status>`, e.g.
`eex-ngp-ttf-2026-05-29-20260529T1430-final`. The gas day is mapped to a UTC interval only through
the separately evidenced delivery calendar the caller supplies (subsection 3.1); the resulting id
and the contract's evidence are recorded in row metadata.

### 3.1 Delivery calendar (`Gasday`) — second independent, unproven contract

The `Gasday` column is a *delivery-day* label, and this repository has **not** verified that EEX
labels NGP delivery days on the CAM convention (or any other). Canonical mapping therefore
requires its own evidence, separate from section 4:

- `eex_ttf_ngp_market_observations(...)` accepts a governed
  `EexNgpGasDayCalendarContract(calendar_id, evidence)` argument; `calendar_id` must be an
  existing id registered in `GAS_DAY_CALENDARS` (`EU-CAM-UTC-2025`, `EU-CAM-2025`,
  `UK-NBP-LEGACY`) — no new calendar framework is introduced — and `evidence` must not be blank;
- with no contract the payload is refused (`unproven_gas_day_calendar`); an unregistered id
  (`unregistered_gas_day_calendar`) or blank evidence (`unattested_gas_day_calendar`) is refused
  as well. There is no default calendar and no fallback to `EU-CAM-UTC-2025`;
- **publication-timezone evidence is not delivery-calendar proof**: the `Timestamp Let` contract
  may be proven while the canonical mapper still refuses for want of a gas-day contract, and vice
  versa. Supplying an evidence *string* does not certify official EEX approval; it records where
  the operator's claim comes from, which is exactly the gap a reviewer can check;
- synthetic tests always pass an explicit synthetic calendar + evidence; the successful rows
  record `gas_day_calendar`, `gas_day_calendar_evidence` and
  `period_basis: gas_day_declared_calendar` in metadata.

## 4. `Timestamp Let`: no verified provider zone (pending normalization)

No official EEX methodology defining the `Timestamp Let` column has been cited in this repository,
so **no provider zone is declared**. The adapter:

- keeps the raw field (record `timestamp_raw`, metadata `publication_timestamp_raw`) and the parsed
  local wall clock;
- returns every record as `normalization_status = pending_source_timezone` with
  `publication_time_utc = null`;
- **refuses canonical conversion** (`unproven_publication_timezone`) instead of reading the value
  on the host clock;
- accepts an explicitly **evidenced** governed `SourceTimezoneContract` argument as the only path
  to canonical rows; an unevidenced contract, or one for another source/dataset, is refused.
  Synthetic tests exercise that path for regular CET/CEST wall clocks (`06:00` → `05:00Z` /
  `04:00Z`).
- **DST folds and gaps are refused, not resolved.** No official EEX fold/gap rule for this column
  exists, so with a proven zone the adapter probes both folds of the naive wall clock
  (`fold=0`/`fold=1`) and round-trips each candidate back from UTC: a wall clock that lands on a
  different wall clock for both folds does not exist (`nonexistent_local_timestamp`, e.g.
  `29/03/2026 02:30` on the Europe/Berlin spring-forward night) and one that round-trips for both
  folds to *different* instants occurs twice (`ambiguous_local_timestamp`, e.g. `25/10/2026
  02:30`). Both are row-level refusals with those stable reasons; the row is never silently
  folded to `fold=0`, never shifted forward, and the shared timezone parser is not changed for
  other sources.

Ingestion timing is separate and explicit: `retrieved_at_utc` (the operator clock, which must be
timezone-aware) is never conflated with the source's publication stamp.

## 5. Rights, entitlement and certification

`src-eex` is registered as a licensed, export-restricted (`license-controlled`) source whose
certification stage is unverified: public download availability is not a redistribution right.
This adapter adds no network call, no scheduled write, no CLI default, no datastore and no
migration, and it does not grant, infer or record any certification. The existing fail-closed
entitlement/certification gate in `scripts/ops/ingest_public_sources.py` is untouched and must
stay in force for any future live ingestion of this file.

## 6. Integration next steps and remaining blockers

Two **independent** evidence blockers, neither of which stands in for the other. A contract
argument records the operator's claim and its source; it does not by itself certify official EEX
approval, and the adapter treats unevidenced, unregistered or mismatched claims as refusals.

1. `Timestamp Let` semantics: cite official EEX methodology (or a written operator confirmation)
   for the token's meaning and its zone, then record a governed, evidenced
   `SourceTimezoneContract` entry; until then every record stays `pending_source_timezone` and
   canonical conversion refuses (`unproven_publication_timezone`).
2. `Gasday` delivery calendar: record official evidence for how EEX labels NGP delivery days, then
   supply the evidenced `EexNgpGasDayCalendarContract` (an existing calendar id) at the canonical
   mapping boundary; until then canonical mapping refuses (`unproven_gas_day_calendar`), and a
   proven `Timestamp Let` zone changes nothing about this blocker.
3. Confirm that the deployment's entitlement covers persisted or redistributed index values and
   record a certification decision; no automatic certification is granted.
4. Wire the operator invocation through `ingest_public_sources.py` behind the existing gates
   (bounded windows, raw archive, idempotent upsert) and only then consider a schedule.
5. Confirm the file's granularity semantics (`Gasday` delivery day vs `Timestamp Let`, one row per
   gas day vs 15-minute buckets) so the canonical period basis can be stated with evidence.
6. Optional, and not part of this bounded task: register the `ttf-ngp-15min` dataset in the Source
   Center registry (`src/eurogas_nexus/domain/ingestion/source_registry.py`).

Until blockers 1–4 are closed the adapter is parse-and-test only: it writes nothing.

## 7. Related records

- `docs/data/SOURCE_TIMEZONE_CONTRACT.md` — the shared timestamp rule the EEX declaration joins.
- `docs/product/DATA_OPERATIONS_SPEC.md` — ingestion invocation model and fail-closed gates.

## 8. Bounded public acquisition transport and capture CLI

Status: **transport delivered; canonical consumer not delivered**. Implementation:
`src/eurogas_nexus/ingestion/eex_public_download.py` and
`scripts/ops/fetch_eex_public_capture.py`. Tests:
`tests/ingestion/test_eex_public_download.py`. This step is necessary transport work, not final
fulfilment: it does not resolve the timezone, delivery-calendar, granularity or rights blockers
in sections 3–6, and it does not make the EEX NGP file a ready data feed.

The transport makes one fixed request for the file URL in section 1. Callers cannot supply a
URL, host, path, query or local input path. Redirects are not followed by httpx; each hop is
validated manually, up to the bounded maximum, and must remain HTTPS on
`gasandregistry.eex.com` or `www.eex.com`, on the default port, with no credential userinfo. The
client has no cookie jar, auth header, browser state or stored session and ignores environment
proxy/netrc settings.

Responses are streamed and refused above the existing
`MAX_CAPTURE_BYTES` (5 MiB) inspection ceiling. A 200 response must declare `text/csv`,
`text/plain` or `application/octet-stream`; the body is also rejected when it begins with an
HTML/XML document, because a matching media type alone is not CSV proof. The bytes are kept
exactly as received (BOM and line endings included), and their SHA-256 and UTC receipt instant
are recorded. Content encoding other than identity is refused rather than hashed after decoding.

Retries are bounded to three attempts and are used only for timeouts, network failures, 429 and
the transient 5xx set `{500, 502, 503, 504}`. A numeric `Retry-After` is capped at five seconds;
malformed or absent values fall back to a bounded exponential delay. A 4xx, a media-type or HTML
refusal, an oversized body or a malformed CSV is never retried. Transport error codes are
stable, and error text contains neither a response body nor a request/redirect URL.

The operator CLI takes an explicit new `--output` file and writes the raw bytes unchanged plus a
sanitized JSON metadata sidecar (default `<output>.metadata.json`). Both paths must be new files,
must not be symlinks, and must have an existing parent directory; an explicit absolute path
outside the repository is permitted. The files are opened exclusively, so an existing file is
never overwritten. The CLI passes the exact bytes to the existing
`inspect_eex_ngp_capture(raw_bytes, retrieved_at_utc=...)` seam and writes nothing when the
transport or inspection refuses the capture. The metadata contains counts, hashes, source URLs
and contract blockers, but no CSV rows. Row-level inspection remains the explicit
`scripts/ops/inspect_eex_ngp_capture.py` command.

```text
python scripts/ops/fetch_eex_public_capture.py --output /path/to/TTF_NGP_15_Mins.csv
```

Exit code `0` means only that the bounded download and local capture inspection succeeded. It
does not mean canonicalization, freshness, executable pricing, redistribution rights,
certification or source activation were established. Exit code `1` is a transport or inspection
refusal and `2` is invalid arguments or an output-path refusal. The command performs no database
write, grant, scheduler change or source activation. Running the actual official download and
comparing it with the existing inspection/SDK remains an operator step for the root reviewer
after the canonical contract is verified; it is not claimed by the synthetic test suite.
