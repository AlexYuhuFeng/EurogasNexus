# RFC-0007: Bounded ECMWF archive availability for research OOS

- Status: **Accepted staged research architecture by root, 2026-10-30**. Implementation and delivery acceptance remain pending.
- Scope: architecture/design only. This file is the only proposed change; no code, dependency, schema, API, source-activation or default-read change.
- Decision owner: root integrator. Root may approve, modify or reject this proposal.
- Goal: allow an explicit research/backtest caller to use real historical ECMWF IFS open-data bytes without manufacturing a receipt, forecast vintage, issue-plus-latency claim or prospective OOS claim.
- Preserved: immutable `ForecastObservationRecord.available_at_utc` as the actual response receipt; existing v3 provenance; default live/API reads on actual receipts only; existing identities and `SeriesDefinitionRecord` records.

## 1. Accepted bounded decision

1. Accept a new, opt-in **research** validation basis named `ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION`, separate from `GENUINE_FORECAST_VINTAGE_OOS`.
2. Accept reconstructed availability as `max(index LastModified, selected GRIB LastModified)` for the exact official keys, labelled `ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION`.
3. Accept the stated public-read/ACL continuity assumption only as a research limitation, not as rights, entitlement or publication proof.
4. Keep every default reader, API page, SDK default, source activation and canonical receipt column unchanged. Add no datastore, table, page or dependency.
5. Require the validation stages in section 8 before any claim of fitness for historical model evaluation.

## 2. Observed evidence supplied by root

Source: `.local-runtime/delivery-20261030-ecmwf-history/history-prefix-report.json`, captured `2026-10-29T23:16:16.900170+00:00`; raw XML listing responses are retained in the same delivery directory. The report basis is `ACTUAL_OFFICIAL_ECMWF_AWS_BOUNDED_PREFIX_LISTINGS_NOT_HISTORICAL_AVAILABILITY_APPROVAL`. The original proposal did not re-fetch or decode the objects; root subsequently verified the historical sample below.

All four exact prefixes `YYYYMMDD/00z/ifs/0p25/oper/` returned HTTP 200 and listed actual `.grib2` and `.index` objects:

| Cycle | Index / 0 h LastModified (UTC) | 102 h GRIB LastModified (UTC) |
|---|---|---|
| 2025-01-15 00z | 2025-01-15T08:34:01Z | 2025-01-15T08:34:29Z |
| 2026-01-15 00z | 2026-01-15T07:34:01Z | 2026-01-15T07:34:16Z |
| 2026-10-01 00z | 2026-10-01T07:34:01Z | 2026-10-01T07:34:19Z |
| 2026-10-29 00z | 2026-10-29T07:34:01Z | 2026-10-29T07:34:12Z |

The evidence proves bounded, anonymous S3 listing access and observed object metadata at capture. Each key list is marked truncated, so it is discovery evidence, not a complete manifest. It does not prove object GET/decode, first public publication, HTML/publication-time semantics, ACL history, continuity, licence clearance, model accuracy or a genuine forecast vintage. No first receipt or genuine-OOS claim may be derived from it.

## 3. Availability rule

For the exact selected message, with exact official bucket/key and current object validators:

`effective_archive_available_at_utc = max(index_object_last_modified_utc, grib_object_last_modified_utc)`

- Never derive availability from nominal cycle time, model issue time, a fixed publication latency, `Date`, `Last-Modified` arithmetic, campaign knowledge or caller input.
- `LastModified` comes from the S3 listing/HEAD response. HTTP `Last-Modified`, `ETag`, `x-amz-version-id`, `Content-Range`, `Content-Length` and `Date` are retained and cross-checked, but HTTP headers do not replace the two S3 object times.
- The result is an **observed current-object availability reconstruction**. It is not a promise of first publication, continuous availability, prospective availability, local receipt or trading availability.
- Use is conservative only where object timestamps are truthful. It may be optimistic if public readability began after `LastModified`; that assumption is explicit in section 6.

## 4. Evidence contract

The existing JSON provenance/evidence payload carries one archive block with at least:

- `availability_basis = ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION`;
- bucket, exact `.index` key and exact `.grib2` key; cycle, step, parameter, level and grid identity;
- index SHA-256; selected GRIB byte range offset/length and message SHA-256; decoded identity checks;
- `ETag`, `versionId` (or explicit null) and `LastModified` for each object, plus observed HTTP validators and `Content-Range`;
- `effective_archive_available_at_utc`, server `captured_at_utc`, request id and `archive_policy_hash`;
- `archive_method_hash`, covering policy, index parser, range reader, decoder version and bounds.

`ETag` is not treated as a content hash. A missing `versionId` is recorded as null, never invented. The evidence is rejected if the index and GRIB keys cannot be tied to the same exact official object pair and selected message.

## 5. Current seams and bounded changes

| Seam | Current owner / symbol | Proposed change |
|---|---|---|
| Discovery, index, range, decoder | Existing official allowlist and `ECMWFOpenDataClient` | Reuse unchanged; no host, prefix or key pattern added. Add only the opt-in evidence wrapper. |
| Evidence reconstruction | New pure application helper | Validate metadata, hashes, ranges, decoded identity and the `max(...)` rule; return typed evidence or typed refusal. |
| Persistence | `ForecastObservationRecord` in `src/eurogas_nexus/db/models/research.py`; existing forecast repository | Append-or-verify through the existing path; preserve first receipt and v3 provenance; no migration. |
| Historical read | Existing research repository/eligibility query | Add a separate explicit archive-mode predicate. Default SQL and default call sites stay unchanged. |
| Projection bridge | Existing forecast-to-degree-day bridge | Accept evidence only with an explicit archive basis; no implicit fallback. |
| Model / results | Existing `ValidationBasis` and demand-result evidence | New enum member; propagate the full basis set and hashes through existing result metadata. |
| API / SDK / Web | Existing weather forecast read and SDK | No new page, route, method or default field. Archive mode is not exposed by default. |
| CI | Existing Python, PostgreSQL and optional ecCodes jobs; `.github/workflows/ci.yml` | Focused tests only; no lock/dependency change. Exact implementation paths must be cited in the code review diff. |

`SeriesDefinitionRecord`, canonical entity, source mapping and existing point identities are reused. An archive reconstruction does not create a new source, series namespace, entitlement, certification or activation.

## 6. Access, mutability and limitations

- **Public-read assumption:** the keyless client used no AWS credential, but current anonymous readability does not prove that the bucket or object was publicly readable at `LastModified`. Bucket policy/ACL history is not evidenced. Archive mode therefore assumes public-read continuity for research only; it cannot support a genuine prospective OOS, publication-time or rights claim.
- **Object mutability:** without S3 versioning, the same key may be replaced and `LastModified` describes the current object, not its first creation. `versionId` is pinned only where available. A replay with changed `ETag`, version, size, `LastModified`, index hash or message hash is a typed refusal, never a silent refresh or a cache-only success.
- **No first-publication proof:** archive timestamps are object metadata, not proof that the forecast was first public, locally received or usable at that instant. The label `ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION` must remain attached.
- **No promotion:** presence in the archive grants no identity, commercial right, source approval, certification or entitlement. ECMWF terms and the existing source/rights controls still govern.

## 7. Persistence and default eligibility

- `available_at_utc` remains the actual response receipt of the capture and remains immutable. It is not overwritten with `effective_archive_available_at_utc`.
- Existing canonical receipt columns, first-receipt append-or-verify behaviour and provenance schema version 3 remain unchanged. The archive block is additive evidence metadata; no v3 field changes meaning or is removed.
- The default read remains genuine-receipt eligibility: existing validation basis and `available_at_utc <= as_of_utc`, with no archive rows admitted. Default SQL is not relaxed and no existing caller silently receives reconstructed rows.
- Archive mode requires all of: existing caller research scope/entitlement; an explicit opt-in; a committed policy hash and method hash; validated evidence; and `effective_archive_available_at_utc <= as_of_utc`.
- New `ValidationBasis.ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION` is distinct from `GENUINE_FORECAST_VINTAGE_OOS`. If the persisted column has a database enum/check that would require a migration, implementation stops for a separate schema decision; this RFC does not authorize one.
- The archive query is a separate branch. It must not widen, truncate or reorder default results. No partial result is returned on evidence failure.

## 8. Robustness and exact bounded stages

Archive input is untrusted even when it came from an official host. The reader must:

- bound JSON depth/size, reject duplicate keys and non-finite values, and parse only strict aware UTC RFC 3339 timestamps;
- reject naive, future, out-of-range and overflowed timestamps, byte offsets, lengths, sizes, counts and date arithmetic;
- reject an index/GRIB mismatch, range mismatch, decoded parameter/level/step mismatch, and any missing or extra selected-message bytes;
- reject truncated listings as completeness proof, truncated bodies/ranges, inconsistent `Content-Range`/length, and decoder failure; write no canonical rows and return no partial series;
- use server-captured time for evidence validity, cap any caller `as_of` at server time, reject future/naive caller clocks, and record the requested as-of separately;
- key any revision cache by bucket/key plus full validator tuple; a stale, expired or missing cache entry never extends availability; changed-on-replay is `ARCHIVE_OBJECT_CHANGED`, a typed refusal.

Stages, each independently reviewable:

1. **S0** — this proposal only; root decides.
2. **S1** — pure evidence validator/reconstructor; no network, DB or caller exposure.
3. **S2** — bounded keyless list/index/range retrieval through the existing client; no persistence.
4. **S3** — existing-repository append-or-verify with actual first receipt; no migration, API or activation.
5. **S4** — opt-in archive read and typed refusals; default path proven byte-for-byte ineligible for archive rows.
6. **S5** — model/backtest/result/portfolio basis and hash propagation; no basis loss or uplift.
7. **S6** — focused tests and CI; optional dependency delivery remains separately open.

## 9. Required test plan (not yet executed)

1. Real keyless bounded listings for the four supplied dates, real `.index` fetch plus byte ranges for a few selected messages, and ecCodes decode of 2 m temperature at explicit steps/grid points. Assert exact keys, ranges, hashes and decoded identities.
2. Actual PostgreSQL: capture the same archive vintage twice; first capture inserts with actual immutable first receipt, replay inserts zero/unchanged and preserves `available_at_utc` and v3 provenance. Assert the archive availability is evidence-only.
3. Default historical path: a past `as_of` before the capture excludes archive rows and remains genuine-receipt-only. Explicit archive path at `as_of` after `effective_archive_available_at_utc` admits only validated rows; before it remains ineligible.
4. Causality: an origin before `max(index, GRIB)` cannot use the message; an origin after it can only under the explicit archive label. Mixed genuine/archive result sets are labelled mixed and never promote the archive rows.
5. Revision/cache: same validators replay idempotently; changed `ETag`, `versionId`, `LastModified`, size, index SHA or message SHA returns `ARCHIVE_OBJECT_CHANGED`; stale cache cannot authorize.
6. Adversarial reader cases: malformed/duplicate/oversized JSON, naive/future/overflow timestamps, forged same-key index/GRIB pair, truncated index or range, caller future clock, and decoder failure; no partial rows or series are returned.
7. Backtest/result/portfolio: basis set, policy hash and method hash survive every hop; a portfolio or result that drops the basis is refused, and no archive input is relabelled genuine.
8. Regional closure remains separate: actual regional source weights and historical target observations are still mandatory. A single-point sample is not London-wide, national or regional accuracy evidence.
9. Optional ecCodes deployment, licensing, Windows support and redistribution remain open and must not be claimed by this RFC or by default CI.

## 10. Acceptance boundary

Root acceptance authorises only an opt-in research reconstruction path after the above evidence and tests are reviewed. It would not authorise source activation, public API exposure, production use, genuine prospective OOS, commercial rights, model accuracy, regional weights, dependency delivery or full delivery completion. The full goal and all other deliverables remain open.

## Root implementation ruling and additional actual evidence

Root accepts staged S1-S6 work under the autonomous execution policy, with the
research-only ACL/public-read assumption explicitly retained. This is not a
public API mode, prospective validation, rights grant or dependency approval.
S1 must be a pure application helper: reuse existing transport/index/decoded
identities; do not introduce a domain-to-ingestion dependency. S2 is server-owned
capture through the existing fixed-origin client. A caller-supplied JSON block
alone never proves remote origin or authorises archive eligibility. S3/S4 remain
separate reviewed changes; no canonical receipt is rewritten.

Root fetched and decoded the actual20250115/00z/ifs/0p25/oper24h 2t message via
bounded AWS index/range transport with ecCodes2.50.0. It returned valid UTC
2025-01-16T00:00Z and four explicitly requested grid readings (London, Edinburgh,
Cardiff, Manchester). GRIB message SHA256:
7f7e40c92f5375d4af52f68428c02820105bafa10ad29cf2404ad0c37e7a5f30.
Index SHA256:67bd79565b0e018e2f0aa82c7e769655e1f2a45fd11d14522ef71b5732415521.
Evidence is ignored ecmwf-history-sample/report.json (directory name in source:
.local-runtime/delivery-20261027/ecmwf-history-sample). This proves one real
historical message/decoder path, not full seasonal coverage, regional weights,
archive eligibility, historical receipts or OOS accuracy. The original discovery
limitations and remaining test plan continue to apply.
