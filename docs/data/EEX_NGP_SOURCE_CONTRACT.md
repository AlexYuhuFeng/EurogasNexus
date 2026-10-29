# EEX TTF NGP Source Contract

Status: **current** (bounded adapter delivered 2026-09-29; RFC0006 stage A receipt-bound mapper,
stage B persistence and stage C explicit operator CLI delivered 2026-10-29). Implementation:
`src/eurogas_nexus/ingestion/eex_ngp.py`, `src/eurogas_nexus/ingestion/eex_ngp_ingestion.py`,
`src/eurogas_nexus/ingestion/eex_public_download.py` and
`scripts/ops/ingest_public_sources.py`. Tests: `tests/ingestion/test_eex_ngp_csv.py`,
`tests/ingestion/test_eex_ngp_receipt.py`, `tests/ingestion/test_eex_public_download.py`,
`tests/unit/test_ingest_eex_receipt_cli.py` and
`tests/integration/test_eex_ngp_receipt_postgres.py`. RFC:
[RFC-0006](../engineering/RFC-0006-EEX-RECEIPT-PRICE-EVIDENCE.md). Timezone declaration:
`SOURCE_TIMEZONE_CONTRACTS` entry `EEX` / `ttf-ngp-15min`
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

Natural key and IDs: `source_record_id` is the original provider record identity
`<gas-day>-<timestamp>-<status>`, e.g. `2026-05-29-20260529T1430-final`, and is never changed by
normalization. The strict publication-bound mapper keeps
`observation_id = eex-ngp-ttf-<gas-day>-<timestamp>-<status>` (e.g.
`eex-ngp-ttf-2026-05-29-20260529T1430-final`). The RFC0006 receipt-bound mapper uses a separate
deterministic namespace, `observation_id = eex-ngp-r1-<sha48>`, hashed from the source reference and
`source_record_id` only — never from the receipt instant or price. The gas day is mapped to a UTC
interval only through the separately evidenced delivery calendar the caller supplies (subsection
3.1); the resulting ids and the contract's evidence are recorded in row metadata.

### 3.1 Delivery calendar (`Gasday`) — second independent, unproven contract

The `Gasday` column is a *delivery-day* label. RFC0006 records the accepted source interpretation
(EEX Index Description v25 sections 1 and 2.5; EEX Contract Specifications 0105a section 1.2.3) for
a 06:00 Europe/Berlin delivery day represented by `EU-CAM-UTC-2025`. Mapping still requires its own
caller-supplied evidence, separate from section 4; the RFC does not turn that interpretation into a
hardcoded default or rights certification:

- both mappers, `eex_ttf_ngp_market_observations(...)` and
  `eex_ttf_ngp_receipt_observations(...)`, require a governed
  `EexNgpGasDayCalendarContract(calendar_id, evidence)` argument; `calendar_id` must be an
  existing id registered in `GAS_DAY_CALENDARS` (`EU-CAM-UTC-2025`, `EU-CAM-2025`,
  `UK-NBP-LEGACY`) — no new calendar framework is introduced — and `evidence` must not be blank.
  The receipt-bound mapper accepts a pending publication timezone but never defaults this
  delivery-calendar contract;
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
- the **strict publication mapper refuses** (`unproven_publication_timezone`) instead of reading
  the value on the host clock;
- accepts an explicitly **evidenced** governed `SourceTimezoneContract` argument as the only path
  to strict publication-bound rows; an unevidenced contract, or one for another source/dataset, is
  refused. Synthetic tests exercise that path for regular CET/CEST wall clocks (`06:00` → `05:00Z`
  / `04:00Z`).
- **DST folds and gaps are refused, not resolved.** No official EEX fold/gap rule for this column
  exists, so with a proven zone the adapter probes both folds of the naive wall clock
  (`fold=0`/`fold=1`) and round-trips each candidate back from UTC: a wall clock that lands on a
  different wall clock for both folds does not exist (`nonexistent_local_timestamp`, e.g.
  `29/03/2026 02:30` on the Europe/Berlin spring-forward night) and one that round-trips for both
  folds to *different* instants occurs twice (`ambiguous_local_timestamp`, e.g. `25/10/2026
  02:30`). Both are row-level refusals with those stable reasons; the row is never silently
  folded to `fold=0`, never shifted forward, and the shared timezone parser is not changed for
  other sources.

The RFC0006 receipt-bound mapper does not need this blocker resolved: it accepts a record whose
`normalization_status` is `pending_source_timezone`. Availability there is the explicit response
receipt, not the provider clock. Even when the parser was given a governed timezone contract and
therefore has a mapped `record.publication_time_utc`, the receipt-bound row still records
`publication_time_utc: null` and `publication_time_basis: unknown`; no first-publication instant is
asserted. The raw `Timestamp Let` text and revision status remain visible.

Ingestion timing is separate and explicit: `received_at_utc` / `retrieved_at_utc` (the awareness
clock, which must be timezone-aware) is never conflated with the source's publication stamp. The
receipt-bound mapper has no default receipt and refuses a receipt that does not match the parser's
own recorded capture instant.

## 5. Rights, entitlement and certification

`src-eex` is registered as a licensed, export-restricted (`license-controlled`) source whose
certification stage is unverified: public download availability is not a redistribution right.
The explicit operator route in section 11 applies the existing fail-closed entitlement, runtime
and certification gates before any EEX download. `EEX` is in `CERTIFICATION_REQUIRED_SOURCES` and
the gate family resolves the runtime operation through `src-eex`; a missing/insufficient
certification is a structured failed run with a nonzero exit. The route never activates the
source, writes a certification/runtime override or substitutes synthetic/zero rows. A schedule
remains deliberately unimplemented.

## 6. Integration next steps and remaining blockers

Two **independent** evidence blockers, neither of which stands in for the other. A contract
argument records the operator's claim and its source; it does not by itself certify official EEX
approval, and the adapter treats unevidenced, unregistered or mismatched claims as refusals.

1. `Timestamp Let` first-publication semantics: cite official EEX methodology (or a written
   operator confirmation) for the token's meaning and its zone before a strict publication-bound
   claim is made. Until then strict mapping refuses (`unproven_publication_timezone`) when no
   governed zone is supplied. The RFC0006 receipt-bound mapper does not claim this meaning and
   keeps `publication_time_utc` null.
2. `Gasday` delivery calendar: RFC0006 records the accepted source chain (EEX Index Description v25
   sections 1 and 2.5; EEX Contract Specifications 0105a section 1.2.3) for the 06:00
   Europe/Berlin delivery day represented by `EU-CAM-UTC-2025`. The mapper still requires callers to
   supply the explicitly evidenced `EexNgpGasDayCalendarContract` at the mapping boundary; there is
   no hardcoded default, and this interpretation is not rights certification or source activation.
3. Confirm that the deployment's entitlement covers persisted or redistributed index values and
   record a certification decision; no automatic certification is granted.
4. The operator invocation is wired through `ingest_public_sources.py` behind the existing gates
   (bounded record limit, raw archive, idempotent upsert) as the **explicit** `eex-ngp` route only
   (section 11). No implicit `all` default or scheduler entry was added; a schedule remains
   unapproved and unimplemented.
5. Confirm the file's granularity semantics (`Gasday` delivery day vs `Timestamp Let`, one row per
   gas day vs 15-minute buckets) so the canonical period basis can be stated with evidence.
6. Optional, and not part of this bounded task: register the `ttf-ngp-15min` dataset in the Source
   Center registry (`src/eurogas_nexus/domain/ingestion/source_registry.py`).

Until the source-semantic, rights and certification blockers are closed, the operator route remains
gated and a blocked run writes no canonical row. Live invocation is not production activation.

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

## 9. RFC0006 stage A: receipt-bound reference-index evidence

Status: **stage A parser mapping delivered 2026-10-29; persistence, consumers and certification
remain separate**. Implementation:
`eex_ttf_ngp_receipt_observations(result, *, received_at_utc, gas_day_calendar_contract)` in
`src/eurogas_nexus/ingestion/eex_ngp.py`. Tests:
`tests/ingestion/test_eex_ngp_receipt.py`. RFC:
[RFC-0006](../engineering/RFC-0006-EEX-RECEIPT-PRICE-EVIDENCE.md), accepted by
[Decision20](../architecture/ARCHITECTURE_DECISION_RECORD.md#decision20-eex-receipt-bound-price-evidence).

This additive path exists because the accepted evidence establishes the delivery day but not the
meaning of the CSV `Timestamp Let` column. It records what the platform actually knows: the file was
available at the explicit response receipt. It does not convert the provider wall clock into an
asserted first publication instant.

### 9.1 Contract

- `received_at_utc` is required, must be an aware `datetime`, is normalized to UTC and must equal
  `result.retrieved_at_utc`, the receipt recorded by `parse_eex_ttf_ngp_csv`. There is no default,
  no `datetime.now()` fallback and no host-clock read. A naive receipt
  (`naive_receipt_timestamp`), a non-datetime (`receipt_timestamp_invalid`), a different instant
  (`receipt_timestamp_mismatch`) or a parse result without an aware capture receipt
  (`invalid_parse_result_receipt`) is refused.
- A pending publication timezone is accepted. Parse rejections are refused whole
  (`rejected_rows_present`), and a result with no usable priced row — including an all-zero or
  all-unavailable payload — is refused (`no_priced_rows`), never mapped as empty data. Unavailable
  rows stay visible on the parse result and are not mapped.
- The separately evidenced, registered `EexNgpGasDayCalendarContract` remains mandatory
  (`unproven_gas_day_calendar`, `unregistered_gas_day_calendar`,
  `unattested_gas_day_calendar`). No calendar is hardcoded or defaulted. Publication-timezone
  evidence is never accepted as delivery-calendar evidence.
- Exact `Decimal` parsing, the original raw price/volume/status/timestamp strings and the strict
  Float-overflow refusal (`index_value_float_overflow`) are shared with the strict mapper. A
  negative published index value is valid. A reference index is never an executable bid/ask.
- The accepted delivery-calendar source chain is EEX Index Description v25 sections 1 and 2.5 plus
  EEX Contract Specifications 0105a section 1.2.3, representing the 06:00 Europe/Berlin gas delivery
  day as `EU-CAM-UTC-2025`. Tests pass that explicit contract evidence; this does not certify
  rights, activate the source or prove the publication timezone.

### 9.2 Row semantics

| Field | Receipt-bound value |
| --- | --- |
| `observation_id` | `eex-ngp-r1-<sha48>`, deterministic from the source reference and original `source_record_id` only |
| `source_record_id` | unchanged original provider identity |
| `observed_at_utc` | `received_at_utc` (normalized UTC) |
| `metadata_json.available_at_utc` | same response receipt |
| `metadata_json.availability_basis` | `response_receipt` |
| `metadata_json.publication_time_utc` | always `null` |
| `metadata_json.publication_time_basis` | `unknown` |
| `metadata_json.normalizer_version` | `eex-ngp-receipt-v1` |
| `freshness`, `quality_score` | `unknown`, `0.0` with `quality_assessed: false` |
| `research_only`, price labels | `true`, `index` / `index`, `executable_quote: false` |

The deterministic id deliberately excludes the receipt and price: recapturing the same original
record under a new receipt, or a changed semantic value at that same original identity, keeps the
same id so append-or-verify persistence can preserve the first receipt and refuse a silent
overwrite. That persistence behaviour is not added by this stage. The old
`eex_ttf_ngp_market_observations` path and its `eex-ngp-ttf-...` ids are unchanged and remain strict
about a proven publication timezone.

### 9.3 Tests and non-goals

Focused tests cover explicit aware receipt causality, mismatch/naive/forged-result refusals, pending
and mapped parser clocks (publication always null), original raw fields, exact long decimals,
negative prices, zero/missing rows, all-unavailable/empty/rejection refusals, Float overflow, the
23-hour and 25-hour DST delivery windows, explicit calendar evidence, replay-stable receipt ids and
the unchanged strict refusal. This stage adds no network, database write, scheduler, CLI activation,
consumer, certification or rights claim; RFC0006's real PostgreSQL/HTTP persistence and consumer
acceptance remain outstanding. Rollback removes this additive mapper, its tests and this section;
the existing parser and strict mapper need no data migration.


## 10. Receipt persistence (RFC0006 stage B)

`persist_eex_ngp_capture` accepts the bounded official capture and an explicit
calendar contract. It archives exact UTF-8 bytes, including BOM and line endings,
then maps and append-verifies canonical rows in a separate savepoint. The caller
owns authorization, the ingestion run and commit. Mapping/revision refusals keep
already archived raw evidence; archive failure cannot create canonical lineage.
Same-key semantic revisions refuse, and recapture preserves the first receipt.
This internal helper performs no fetch, scheduler activation or certification.

The complete PostgreSQL CI now includes its dedicated disposable-schema tests.
Root verified two actual official downloads in an owned acceptance database:
first inserted4, second inserted0/verified4; exact bytes, hashes, null publication
times, exact price authority and first receipts were preserved. Raw SHA256 was
019f2286f8124be81c57d5b95e5df31497665f9ee877390122149b7842951707.
Gated operator invocation is added in section 11; business-consumer acceptance
and any schedule remain subsequent work.

## 11. Explicit operator invocation (RFC0006 stage C)

Status: **explicit operator CLI delivered; no schedule, activation or rights clearance**. The only
entry is the existing `scripts/ops/ingest_public_sources.py` command with the new explicit route:

```text
python scripts/ops/ingest_public_sources.py --source eex-ngp --limit 20 --json
```

`eex-ngp` is a `--source` choice but is **not** added to the implicit `all` set, the no-argument
default or any scheduler mapping. `--source all` alone therefore behaves exactly as before.
`--source all --source eex-ngp` keeps the explicit EEX route alongside the existing providers,
rather than letting the `all` expansion discard it.

### 11.1 Gate order and refusal semantics

The EEX family (`EEX`, runtime registry id `src-eex`) is evaluated in the same pre-download gate
session as the existing families. It uses the existing entitlement check, operator runtime state
and `CERTIFICATION_REQUIRED_SOURCES` certification gate. A blocked EEX run:

- is recorded as a failed `ingestion_runs` row with its audit event;
- appears as a structured entry in the report's `failures` and `sources` (code
  `eex_gate_blocked`);
- returns a nonzero exit;
- performs no HTTP request, source activation or certification/runtime override.

The route is separate from the shared ECB/ENTSOG/GIE session. EEX fetches and persists in its own
session after the independent providers commit, so an EEX refusal cannot roll back their work.
This ordering is covered by unit tests, not by a live provider call in CI.

### 11.2 Fetch, record bound and persistence

The route calls the existing bounded `fetch_eex_public_capture()` with no URL, key or caller
transport argument: it is the fixed official HTTPS file and the fixed no-API-key path. It then calls
`persist_eex_ngp_capture(...)` with an explicit delivery-calendar contract, the CLI `--limit`, and a
fresh run id.

The persistence helper now takes `max_records: int = 10000`, validates that it is a positive
integer (`bool` is refused) before any write, archives the exact bytes and performs receipt
mapping, then refuses `len(mapped_rows) > max_records` with the new typed stable code
`eex_ngp_record_limit` **before** any canonical write. The archived raw capture is retained. The CLI
passes `--limit`; an invalid EEX limit is rejected before database resolution or HTTP. The CLI
records the same run id in the success/failure `ingestion_runs` row and audit event, and commits a
retained raw archive when mapping, revision or record-limit refusal occurs. Report details include
the full helper counts and safe stable codes only; provider text, URLs and query secrets are not
echoed, and there is no zero/synthetic fallback.

### 11.3 Calendar contract and non-claims

The caller constructs the root-accepted contract explicitly:

- `calendar_id = EU-CAM-UTC-2025`;
- evidence cites EEX Index Description v25 sections 1 and 2.5
  (`https://www.eex.com/fileadmin/EEX/Downloads/Trading/Indices/Index_Description_v25_clean.pdf`)
  and EEX Contract Specifications 0105a section 1.2.3
  (`https://www.eex.com/fileadmin/EEX/Downloads/Rules/Contract_Specifications/20261002_EEX_Contract_Spezifications_0105a_E_FINAL.pdf`)
  for the 06:00 Europe/Berlin delivery day.

There is no guessed publication clock, no generic/default calendar and no caller flag that could
claim rights. The evidence string is a citation, not certification. Tests use only local stubs for
the CLI/transport and one actual PostgreSQL record-limit case; real EEX network capture and the
complete PostgreSQL CI were separately verified by root (76 passed in an empty owned database).

Rollback removes the `eex-ngp` choice and its explicit route, the EEX gate-family registration, the
`max_records` parameter/typed refusal, the CLI helper and tests, and this section. Existing
providers, the stage B helper without a bound, and already archived raw/canonical rows need no data
migration.


New CLI runs carry explicit registered source ids (including EEX-NGP to src-eex)
and the known EEX dataset. Unknown names retain blank ids; historical records are
unchanged. Refusals report raw retention only after commit confirms the exact
archive id. Failed commits leave retention unknown; pre-download failures report
zero. Root verified eight run aliases in actual PostgreSQL, plus a blocked actual
CLI invocation with zero fetches and unchanged raw/canonical counts. These are
owned acceptance probes, not production activation or provider certification.
