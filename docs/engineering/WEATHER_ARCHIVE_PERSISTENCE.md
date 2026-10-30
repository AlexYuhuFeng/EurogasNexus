# Weather archive persistence (RFC-0007 S3)

Status: bounded research implementation. This is not a public archive mode, source
activation, rights grant, prospective validation, customer feature or delivery
completion. S4 archive reads and default-read eligibility remain unimplemented.

## Scope

`application/research/weather_archive_persistence.py` accepts only the typed
server-owned S2 `EcmwfArchiveCapture`, the caller's explicit existing
`EcmwfForecastPointBinding` values and an explicit UTC `ingested_at_utc`. It:

1. refuses caller-pending ORM writes before any SQL or savepoint;
2. validates the capture through the existing lazy decoder and pure S1 evidence
   path (`validate_archive_capture`), including the explicit public-read continuity
   research assumption;
3. serializes the validated S1 facts (no raw index/GRIB megabytes) into one
   internal archive payload;
4. calls the existing `append_ecmwf_forecast` with an optional archive seam.

The caller owns the transaction. The helper never commits or rolls back.

## Repository seam and trust boundary

`append_ecmwf_forecast(..., archive_evidence=payload)` remains the only archive
repository entry point. Its default `None` path is byte-compatible with the
previous v3 append: same deterministic IDs, content/batch hashes, provenance
fields and receipt semantics.

The archive payload is an **internal trusted caller** seam, not remote-origin
authentication and not arbitrary JSON authorization. The pure canonical schema in
`ingestion/ecmwf_archive_evidence.py` has no application, database or network
dependency. Before any SQL, the repository revalidates the payload against the
exact typed transport and decoded pair:

- fixed reviewed ECMWF bucket and exact request-derived `.index`/`.grib2` keys and
  URLs;
- index and selected-message SHA-256, message offset/length, `Content-Range` and
  object total size;
- S3/HTTP ETag equality (kept opaque, never a content hash), versionId equality
  (`None` and literal `"null"` remain unpinned), size and `LastModified`;
- run date, cycle, step, validity, decoder library/version, parameter, units and
  grid identity;
- capture clocks bound to the actual transport receipt and explicit ingestion
  clock; conservative effective availability must be the exact max of the two
  object `LastModified` values;
- exact S1 policy, method and whole-evidence hashes and the complete mandatory
  limitation set are recomputed from the validated typed facts; carried 64-hex
  text or arbitrary limitation strings are never accepted by shape alone;
- explicit non-prospective and public-read-continuity research flags and
  limitations.

`available_at_utc` remains the **first actual local receipt**. It is not replaced
by `effective_archive_available_at_utc`, and the archive payload is inserted only
with new rows. Existing rows and their first v3 provenance/receipt are never
updated or backfilled.

## Replay and refusal rules

The repository performs a bounded actual-SQL lookup by fixed ECMWF source/origin,
exact index/GRIB keys, run/cycle/step/validity, series/entity and point binding,
with an explicit `limit + 1` refusal. It does not rely on the incoming canonical
observation id alone.

- Same stable object facts, validators, hashes, selected range, policy and method:
  replay inserts zero rows and preserves the first receipt, first v3 provenance
  and first archive block byte-for-byte. Later capture clocks and the later
  whole-evidence hash are expected to differ and are excluded from the stable
  comparison.
- A stored block is revalidated against its own facts before comparison: the S1
  policy/method/evidence hashes and mandatory limitations are recomputed, and its
  binding must match the immutable row's original v3 request, reference and
  binding. Tampering with the stored point/series/entity/mapping/object hashes/
  validity is `ARCHIVE_OBJECT_CHANGED` even when the stored `evidence_hash` is
  unchanged.
- Different request-location fingerprints for the same point/object do not by
  themselves claim a source change; the old binding's request hash is checked
  against the immutable row's original request, never against the incoming query,
  and query-specific request hashes are excluded from the stable comparator.
- A changed ETag/versionId/size/LastModified/index hash/message hash/range, even
  when the new raw message hash would produce a different canonical observation
  id, is `ARCHIVE_OBJECT_CHANGED`.
- An existing row with no archive block is `ECMWF_ARCHIVE_EVIDENCE_MISSING`; it is
  never silently converted into archive evidence.
- Caller-pending ORM state is refused before SQL rather than flushed by the
  existing nested savepoint.
- A batch is atomic: all binding, payload and object-identity checks precede the
  insert, so one refusal leaves zero rows from that call.

## Concurrency

On PostgreSQL the archive path takes deterministic transaction-scoped advisory
locks for the archive object identity before the candidate/id reads. Keys are
sorted for multi-row batches so two batches cannot acquire them in opposite
orders. Acquisition is non-blocking (`pg_try_advisory_xact_lock`) with short
sleeps under one monotonic, shared 5-second budget for the whole acquisition
sequence; a caller-configured `lock_timeout` is neither required nor changed. If
the budget expires, the helper raises the typed retryable
`ECMWF_ARCHIVE_BUSY` (`EcmwfForecastArchiveBusy`) before any archive insert, and
the caller decides whether and when to retry, normally after ending or rolling
back its transaction so any already-acquired keys are released. Acquired keys are
transaction-scoped and are never explicitly released by the helper. Within the
budget this serializes append-or-verify: a concurrent replay acquires after the
first transaction commits, reads the committed winner and returns `duplicates=1`
instead of a uniqueness conflict. The helper never commits, rolls back, changes
session settings or takes a session-wide/table lock, and adds no table or
constraint.

SQLite remains auxiliary sequential fixture support only. It has no equivalent
advisory lock, so these tests do not claim PostgreSQL concurrency on SQLite.

## Evidence limitations

Storage trust is the controlled writer/DB boundary, not cryptographic remote
authentication. The archive block records the exact S1 evidence and its binding to
the existing v3 request/reference/decoded fields, but future S4 readers must
separately validate canonical JSON, hashes, clocks and bindings. The block keeps
these limits explicit:

- the public-read/ACL continuity assumption is research-only, not rights or
  entitlement;
- current object `LastModified` is not first publication, local receipt,
  continuous availability or prospective OOS availability;
- ETag is opaque and is not content authentication;
- an unpinned/null versionId cannot prove object immutability;
- no raw GRIB/index bytes, API, default read, source activation, migration or
  dependency change is introduced.
