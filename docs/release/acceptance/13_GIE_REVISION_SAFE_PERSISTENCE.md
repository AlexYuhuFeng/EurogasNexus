# 13 — GIE revision-safe persistence and external-credential connection workflow

Task: **REAL-SOURCES-02**. Date: 2026-10-10. Author: DeepSeek routine worker; reviewer: Astra.
Companion evidence: `.dnx-out/real-sources-20261010/result-workflow.md` (initial slice) and
`.dnx-out/real-sources-20261010/result-workflow-review.md` (bounded review corrections).

This report records only what is **implemented and validated** in this slice. It does not advance any
certification, entitlement, source-enabled or customer-ready status for GIE, and no live ingest ran.
GIE remains **0 customer-ready**.

## 1. Revision safety (lookahead prevention)

The generic `upsert_observation_rows` replaces revised values in place and preserves only
`observed_at_utc`; for a corrected provider measurement at the same natural key that projects the new
value back to the old observation instant. Rather than change every source, a **GIE-scoped** path was
added:

* `upsert_revision_safe_observation_rows` in
  `src/eurogas_nexus/db/repositories/public_ingestion_upsert.py`:
  * new key → insert with its own first-seen and archive lineage;
  * existing key with identical semantic content → row left **byte-for-byte unchanged**; the newer
    poll's run/receipt/archive metadata is not merged into it;
  * existing key with different semantic content → the whole batch is refused with
    `GieRevisionRequiresHistoryError` (`gie_revision_requires_history`), naming the table, key,
    dataset and the differing column **names** only.
* `GIE_SEMANTIC_FIELDS` is the explicit compared-column declaration for `storage_observations` and
  `lng_observations`; poll-owned metadata (provider `updatedAt`, receipt, run, archive, page) is
  excluded from the comparison, so per-poll churn is never mistaken for a revision.
* The canonical write runs in one PostgreSQL **SAVEPOINT** of the caller's transaction
  (`_persist_gie_product`). A refusal unwinds only that savepoint: originals survive, no partial
  canonical write persists, and the outer transaction records the real failed run + audit event.
  Atomicity under concurrency uses the existing unique key plus `ON CONFLICT DO NOTHING` and a
  `FOR UPDATE` re-read — no lock service or new store. The conflict/re-read fallback **verifies an
  affected row**: a second `DO NOTHING` that neither inserts nor re-reads the row fails closed with
  `gie_revision_race_unresolved` (`GieRevisionRaceError`) instead of counting a phantom insert.
  `observed_at_utc` and the poll-owned receipt/run/archive metadata are deliberately **excluded**
  from the compared fields, so an unchanged poll keeps the stored first-seen instant and lineage; a
  changed gas-day period or measurement is a semantic difference and is refused.

**Explicit limit:** append-only revision history and revision-aware selectors are **not designed or
implemented**. Until they are, revised GIE measurements are refused, never stored. The generic upsert
limitation for the other sources is unchanged and still documented (report 12 follow-up 9).

## 2. Raw lineage

`_archive_raw_payload` now returns the exact `{archive_id, payload_sha256}`; each page's rows are
stamped with that page's archive id/hash plus receipt, page, provider last page, total-on-page and
fetch reference, while the provider `updatedAt` is kept as a separate metadata value. A payload that
cannot be archived (size/policy) fails the product closed with `gie_archive_lineage_required` — no
canonical row claims lineage it does not have. Unchanged rows keep their original archive/first-seen;
new polls archive their own pages. No schema migration.

## 3. External credential status

`resolve_gie_credential_status` is the single resolver behind runtime and reported status
(env → file → encrypted store). It exposes only `configured`, `source_kind`, `blocked`, stable
diagnostic codes and support flags — never the value, a fragment, or the external path. A stored
credential the operator disabled is **authoritative**: env/file precedence cannot silently re-enable
it, and a disabled source runtime state blocks the status. `GET /api/credentials/providers` reports
the GIE source kind/diagnostics/support flags/connection-test capability and the unchanged
certification gate state; `GET /api/sources` uses the same resolver so an externally configured key
no longer reports `needs_credential`.

The operator disable is enforced at the **actual credential-fetch boundary**, not only on the status
surface: `resolve_gie_runtime_api_key` (used by `scripts/ops/ingest_public_sources.py` and the
credential API) refuses a disabled stored credential (`gie_credential_disabled`), a disabled GIE
source runtime operation (`gie_source_disabled`), an unreadable operator state
(`gie_credential_state_unreadable`) and an unreadable key file (`gie_key_file_unreadable`) even when
`GIE_API_KEY`/`GIE_API_KEY_FILE` is set. An **absent** state row (or no runtime store at all) is *no
override* and keeps the documented precedence; a read **failure** against a configured store is
reported blocked with `credential_state_unreadable`/`source_operation_state_unreadable` and is never
treated as a confirmed permit. `_gate_blockers` also fails closed on an explicitly disabled or
unreadable source runtime state before the fetch. The configured default scheduling of `src-gie`
stays disabled; nothing here enables a source.

## 4. Connection test

`POST /api/credentials/GIE/connection-test` probes AGSI and ALSI **independently**, one bounded page
each (size 30) through the corrected transport, and returns per-product connectivity plus
envelope/normalization shape. A successful result requires **full page normalization conformance**:
every fetched record must normalize into a canonical row and every required quantitative column must
be present. Otherwise that product fails with a stable shape code while retaining its HTTP status
and counts, and the other product's independent result is unaffected:

* `gie_normalization_failed` — the normalizer raised or produced no row for a non-empty page;
* `gie_normalization_incomplete` — some records were silently skipped (e.g. missing gas day/code);
* `gie_malformed_quantitative` — a required quantitative column is absent/unparseable.

The page's own `received_at_utc` is the normalization receipt fallback (never a freshly invented
`now`, so the probe reports the same availability basis a live fetch would). An HTTP 200
access-denied body is a failure. Certification is returned separately and never advanced; no market
data is persisted, no source/scheduler/credential row is changed, and no provider payload or key
reaches the response. The route keeps its existing `Permission.OPERATOR` authorization and audit
path. This is connectivity + shape only, **not** independent certification.

## 5. SourceCenter

The live-connection control is derived from the backend's `connection_test_supported` capability plus
the resolved `configured` state (the hardcoded `DEEPSEEK`/`LLM` list is removed). The external
owner-managed credential renders read-only with its source kind and diagnostics, **and its credential
entry is actually disabled**: for an active `env`/`file` key the label, key input and Save control are
disabled and the submit handler refuses the same case (`canSubmitCredential`), so the UI cannot offer
an ineffective rotation. Only `env`/`file` are labelled externally managed —
`missing`/`operator_disabled`/`file_unreadable`/`state_unreadable`/`credential_store` are not. The
displayed connection aggregate is scoped to the currently selected provider by `providerId`
(`credentialConnectionForProvider`), so a stale previous-provider (e.g. DeepSeek) result is never
shown. Live connection success renders per product separately from the certification stage, and en/zh
copy was added. Same page and credential workflow; no key in the browser.

## 6. Verification

Review status: the persistence behaviour was **accepted provisionally** by the reviewer on the
strength of 21 focused host tests, including the 12 real PostgreSQL isolated-schema tests in
`nexus_verify` plus atomicity and Markdown gates. The bounded review-correction worker then fixed the
four defects recorded in `.dnx-out/real-sources-20261010/result-workflow-review.md` and re-ran only
focused gates:

| Gate | Result |
| --- | --- |
| `tests/integration/test_gie_revision_safe_persistence_postgres.py` (real PostgreSQL, isolated `gierev_*` schemas in `nexus_verify`) | **12 passed** |
| combined focused Python suites (GIE transport/credential/persistence/gates, security connection API, sources API, ingestion contracts) | **201 passed** |
| `ruff check` on every changed Python file | clean |
| `tsc --noEmit` (clients/web) | clean |
| focused frontend tests (`credentialProviderModel`, `sourceCenterGieConnection`) | **11 passed** |
| `capturedBoardComparator.test.ts` | 13/17 in this sandbox (4 CLI `spawnSync` cases are sandbox `EPERM`); **17/17 on the reviewer host** |
| `shellHookOrder.test.ts` | 1/2 — the pre-existing, unrelated `AppShell is one component` assertion still fails on the host; `AppShell`/test unchanged here |
| PostgreSQL cleanup check | 0 leftover `gierev_*`/`gieupsert_*` schemas; `public` still 92 tables; **0 GIE rows in `public`** |

Negative coverage: external value absent from JSON/errors/status; unreadable key file → stable code
without path; one product fails while the other passes; an operator-disabled **stored credential is
refused at the runtime fetch boundary** with env/file/no-env; an explicitly disabled source runtime
operation is refused; an unreadable operator state fails closed with its own code and is not shown as
configured; the ordinary external key with no stored override still resolves and passes the bounded
connection test; endpoint authorization; missing gas-day/partial skipped-row and malformed
quantitative pages are explicit shape failures while the other product stays independent; unchanged
rows stable; revised content refused; archive link/receipt exact; missing archive fails closed;
mixed-batch rollback; conflicting concurrent identical/revision behaviour; and the conflict/re-read
fallback fails closed rather than counting an unconfirmed insert.

## 7. Remaining blockers

1. GIE certification (schema compatibility + independent `live_sample_validation`) and attribution
   review remain open; the fail-closed gate still blocks live ingestion. GIE stays 0 customer-ready.
2. Revision history/selectors are undesigned; revised values are refused by design.
3. The single-row-per-natural-key schema still cannot hold per-poll availability (report 12
   follow-up 9).
4. The connection test is connectivity/envelope/normalization shape only, never certification.

## 8. Actual SourceCenter workflow — 2026-10-13

GPT-6.1 Sol exercised the real local React/FastAPI/PostgreSQL runtime with the existing
Playwright/Chromium installation. Initial credential-missing workflow: **6 checks passed**.
The existing ignored local env was then configured with `GIE_API_KEY_FILE` pointing to the
owner-managed external secret, with no key value copied. Only the verified project API was
restarted through `Start-LocalAcceptance.ps1`; the same Docker container `49881d31b917`,
loopback PostgreSQL51356 and existing Web3000 listener were retained.

The actual external-key workflow passed **15 checks**, including disabled label/key/Save,
enabled connection test, independent AGSI/ALSI rendering, provider-switch isolation and
read-only controls after reload. Both official HTTPS products returned HTTP200, **30 records
and 30 normalized rows each**, independently. Each result explicitly reports `complete=false`
and bounded partial history. Certification stayed `unverified`, `allows_live=false`.

Screenshot review found and repaired two presentation defects: product results previously ran
together as inline text, and a successful transient connection result also showed `Not tested`.
`app.css` now gives the product results separate rows, and `SourceCenter.tsx` suppresses the
stored-status fallback while the selected provider has a current connection result. The actual
workflow was repeated and its screenshots viewed after both corrections.

Reproducible evidence is in `.dnx-out/gie-ui-20261013/`: `workflow.mjs`,
`initial-evidence.json`, `external-evidence.json` (before presentation corrections),
`external-after-evidence.json`, and corresponding credential/connection PNGs. No provider key
or external path appears in returned API evidence; the key is absent from the browser DOM and
an in-memory scan of the generated text artifacts found zero full-secret matches.

Before/after/final DB fingerprints prove no changes in the six GIE-scoped credential,
runtime-state, certification, storage, LNG and raw-archive tables; all remained **0 rows**.
Only fixture login and bounded GIE connection-test POSTs were permitted by the browser guard;
unrelated automatic resource optimization POSTs were blocked. Authentication/session/audit
side effects are outside that six-table comparison, so this is not a wholly read-only session.
Unauthenticated credential-provider access after restart returned HTTP401 with
`public_api_token_missing`, family `AUTH`.

Focused host rechecks: **112 Python tests passed**, **11 frontend tests passed**,
`tsc --noEmit` clean, and touched-file diff whitespace clean. No source enable, live ingestion,
certification advancement, cleanup, commit or push. This records execution evidence; final
Astra integration review and independent supplier certification remain pending.
