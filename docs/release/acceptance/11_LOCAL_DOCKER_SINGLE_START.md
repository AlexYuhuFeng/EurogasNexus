# 11 — Local Docker single-start consolidation (DOCKER-PG-SINGLE-START-03)

Status: **Docker migration, single startup and local UI acceptance PASS; authorized old-data cleanup BLOCKED by tool policy.** Updated 2026-10-10 local time. Local UAT only; never customer production certification. The original worker preparation sections below are historical; section 6 records actual host execution and supersedes their pending gates.

Scope executed: root compose / tracked startup / documentation / read-only locale-semantics
evidence. Explicitly **not** executed: API/Web start, cutover, deletion, DB write/reset/migration/
seed, commit, push. The reviewer owns the ignored cluster verification/cutover scripts and the
execution checkpoint.

Evidence root (ignored): `.dnx-out/locale-semantics-20261009/`.

## 1. What changed (tracked)

| file | change |
| --- | --- |
| `docker-compose.yml` | replaced the competing dev database (`eurogas-nexus-db`/`eurogas_nexus` on public `5432`, literal `eurogas_dev`) with the canonical `eurogas-nexus-pg` project, container `eurogas-nexus-postgres`, official `docker.io/library/postgres:16-alpine`, **external** volume `eurogas-nexus-postgres-data`, `PGDATA=/var/lib/postgresql/data/pgdata`, loopback-only `127.0.0.1:51356`, file secret only, scram local/host, `-c default_text_search_config=pg_catalog.simple` |
| `scripts/ops/Start-LocalAcceptance.ps1` | new single local API+Web+Docker startup: fail-closed preflight (Docker reachable, external volume present, env/secret present), `docker compose up -d`, health wait, mount/secret/port assertion, project-owned-listener reuse check, API readiness and Web 200, JSONL evidence |
| `README.md`, `docs/operations/DB_MIGRATIONS.md`, `docs/operations/VALIDATION.md`, `docs/operations/LIVE_POSTGRESQL.md` | document the one entry; removed the `down -v` reset from the preserved-database path; destructive reset explicitly limited to disposable scratch |

Ignored local helpers (not tracked, preserved): `.dnx-out/recovery-20261007/start-reviewed.ps1` and
`.dnx-out/run_api_uat.cmd` are now thin forwarders to the tracked entry, with refreshed commentary.
The reviewed migration artefacts under `.dnx-out/docker-postgres-20261008/` were left untouched and
historical. `deploy/runtime/compose.yaml` was not touched.

## 2. Locale-semantics probe (required before cutover)

Read-only probe (`locale-semantics-probe.sql`), executed by `run-locale-probe.ps1` against
**source 51356** (embedded PG16.2, UTF8 + libc `Chinese (Simplified)_China.936`) and **target
51357** (Docker PG16.15, UTF8 + libc `en_US.utf8`). The source credential comes from the ignored
`user-uat.env`; the target credential from the ignored migration superuser secret, both in process
memory only. Output is hashes/counts only; no user string value is printed.

Exact commands:

```powershell
pwsh -NoProfile -File .dnx-out/locale-semantics-20261009/run-locale-probe.ps1 -Mode Both
python .dnx-out/locale-semantics-20261009/compare-locale-probe.py
```

Result: `semantic=0 collation=59 platform=54 presence=0` (comparator exit 0). All 9 databases
probed: 921 value-bearing text columns total (267 in `nexus_browser`, 0 in `postgres`).

- **Semantic invariants all matched**: encoding, equality/`distinct`/`uniq`, `COLLATE "C"` ordering,
  `min`/`max` under `COLLATE "C"`, `lower()`/`upper()` multisets, row counts, focused backtest
  numeric renderings, and the pure controls (ASCII case mapping, byte sort, float/numeric/timestamp
  rendering). Because `lower()`/`upper()` and equality match, the `ILIKE` TSO-tariff matching (which
  includes `Teréga`/`Enagás`) and uniqueness behaviour are unchanged.
- **Collation-dependent differences (59, recorded, bounded)**: default-collation ordering/extremes
  for `dataset_build_issues.detail`, `dataset_snapshots.dataset_spec_id`,
  `glossary_terms.{term,definition_en,definition_zh_cn}`, `market_observations.market_venue`,
  `series_definitions.entity_id`, `source_runtime_states.provider`, `tso_tariffs.{gas_year,
  source_point_name}`, `upstream_resource_contracts.notes`, and the whole-table repository ordering
  `ORD tso_tariffs` (`h` differs; `hc` matches). These are exactly the cross-OS libc collation
  effects expected from `Chinese (Simplified)_China.936 → en_US.utf8`; they are **not** declared
  equal and are not suppressed.
- **Platform differences (54, expected)**: `datcollate`/`datctype`/`lc_messages` and
  `server_version` 16.2 → 16.15. `default_text_search_config` currently matches
  (`pg_catalog.simple`; target source is `command line`), and the root compose now pins the same
  `-c default_text_search_config=pg_catalog.simple` so a recreate preserves it.

### Numerical consumers of textual ordering (for Astra)

1. **Route-cost tariff selection is the one live numerical consumer.** `list_tso_tariffs`
   (`src/eurogas_nexus/db/repositories/route_cost.py`) orders by text keys
   (`country, source_point_name, direction, gas_year`); the order is collation-sensitive
   (`ORD tso_tariffs h != hc`). `select_latest_tariff`
   (`src/eurogas_nexus/domain/route_cost/tariff_selection.py`) sorts exact matches by status
   priority and takes `[0]`; equal-status ties are broken by that input order and feed
   `_calculate_tariff_legs` → `total_cost`. **Bounded**: read-only check shows
   `DUPGROUPS=0` duplicate exact-match groups in the current `tso_tariffs` data, so no current
   number changes; the latent risk exists only if duplicate equal-status exact matches are inserted.
2. **Backtest engine textual tie-break is locale-independent.** `_dedupe_conflicting_observations`
   (`src/eurogas_nexus/domain/backtest/engine.py`) sorts `(received_at, source_reference)` in Python
   (code-point order, not libc). A pre-existing, locale-independent determinism gap is recorded
   separately: `market_observations` has 66 duplicate `observed_at_utc` groups and `market_quotes`
   has 1, while the repository orders by `observed_at_utc` alone; the engine's selection is still
   determined by its own sort key, so no numeric change is demonstrated. **Not a locale effect;
   flagged for Astra.**
3. **Ordering-only readers** (no numeric aggregation): `list_backtest_attribution`
   (`decision_time_utc, dimension, key`), `glossary_terms`, `provider_certifications`,
   `dataset_artifacts`, `company_tso_access`, `route_candidates`. Only `tso_tariffs` actually
   changes total order between the two clusters.

## 3. Tests executed in this worker session

| check | command | result |
| --- | --- | --- |
| PowerShell parser (AST) | `[Parser]::ParseFile` on the new launcher and probe runner | PASS, no BOM |
| Compose validity | `docker compose -f docker-compose.yml config --quiet` | exit 0 (interpolated config not printed) |
| Config contract | `python scripts/ci/check_config_contract.py` | exit 0 (no undeclared template variable; the root compose sets no product env name) |
| Markdown links | `python scripts/ci/check_markdown_links.py` | 284 files, all local links resolve |
| Tracked-path / workspace hygiene | `pytest -q tests/contract/test_tracked_path_hygiene.py tests/contract/test_local_workspace_hygiene.py tests/contract/test_env_file_bom.py` | 16 passed |
| Whole contract suite | `pytest -q tests/contract` | 544 passed, 1 failed — `test_relative_link_resolving_outside_repository_is_reported` writes a temp file **outside** the repository and the DSH workspace-write sandbox denies it (`PermissionError` on `...\eurogas-nexus-outside-target.md`). Environment artifact, unrelated to these changes |
| Locale probe (both clusters) | `run-locale-probe.ps1 -Mode Both` + comparator | semantic=0; 59 collation + 54 platform recorded |
| Launcher fail-closed preflight | `pwsh -File scripts/ops/Start-LocalAcceptance.ps1 -CheckOnly` | exit 1 with the explicit Docker-engine message; no fallback started |

## 4. Original worker handoff gates (historical; superseded by section 6)

1. **Cutover (reviewer/parent)** — only after the canonical cluster gate passes. The root compose
   must not be started on `51356` before the embedded source is stopped, or the port conflicts.
   The reviewer's canonical gate must stop rejecting the expected read-only secret bind; the root
   compose binds the same secret file (`...\.dnx-out\docker-postgres-20261008\secrets\
   postgres_superuser_password.txt`) to the same read-only container path the verified container
   already uses. **Coordination**: as written, the ignored `cutover-to-docker-cluster.ps1` still
   installs the historical `.dnx-out/docker-postgres-20261008/start-reviewed-docker.ps1` over
   `.dnx-out/recovery-20261007/start-reviewed.ps1` and drives the historical migration compose.
   Because `run_api_uat.cmd` now forwards to the tracked launcher, that path still converges on the
   root compose, but the reviewer should install/forward the tracked
   `scripts/ops/Start-LocalAcceptance.ps1` directly so there is exactly one launcher.
2. **Idempotent second startup with container/data hashes (host)** — the Docker engine named pipe is
   denied in this worker session, so this could not be executed here. Host commands:

   ```powershell
   powershell -File scripts/ops/Start-LocalAcceptance.ps1 -Fingerprint
   # capture .dnx-out/local-acceptance/startup-evidence.jsonl (container_id, started_at, restart_count, db_fingerprint)
   powershell -File scripts/ops/Start-LocalAcceptance.ps1 -Fingerprint   # second run must reuse the same container
   # the second line must carry container_id_unchanged=true; container_id and db_fingerprint must match
   # then re-run the reviewer's canonical cluster gate for the full data-hash comparison
   ```

3. **Browser read-only UAT (reviewer)** — existing ignored script; GET-only after login.
4. **Post-success cleanup (parent only)** — old embedded data/backups; the verified volume and the
   secret file are excluded.
5. **Least privilege** — `nexus` remains SUPERUSER in both clusters (observed contract, unchanged);
   separate customer delivery gate.
6. **Documentation follow-up** — `docs/operations/BACKUP_RESTORE.md` still names the removed
   `eurogas-nexus-db` container and its `5432` DSN in a runnable drill example. It was outside the
   four documents this task was authorised to edit; listed here rather than silently rewritten.
7. No customer production certification is asserted from local UAT.

## 5. Original worker limitations

- No Docker-side action was possible in this session (engine named pipe denied); container/volume
  facts were read over loopback TCP only.
- The target's `default_text_search_config` currently comes from the container command line; the
  root compose pins it so a recreate preserves it.
- The migration compose and its `_private` scripts were not edited (reviewer-owned).

## 6. Actual host migration and acceptance

All9 source databases were preserved:8 project databases, each with92 tables, plus empty-user-object `postgres`. Host restored7 additional project databases after the previously restored main database. Canonical verification actually collected Docker inventories and passed at2026-10-09T14:36:50Z; no synthetic self-test evidence was used for cutover. Every stable structural/data line matched:2070 per project database,14 for `postgres`. The initial constraint mismatch was the old verifier's use of relation OIDs; all149 constraints were subsequently compared by stable name, definition and flags. File-secret validation precisely allows only the resolved live secret source, its approved destination and read-only mount; data remains on the named Docker volume.

Host cutover93418 succeeded at14:37Z. The existing embedded PostgreSQL stopped cleanly. Root Compose recreated the same retained volume on `127.0.0.1:51356`; API login and authenticated `/api/me` passed. The tracked launcher verifies the configured API DSN and actual `/api/runtime/db` identity/connectivity, refuses unrelated listeners, disables automatic image pulling, and uses the single root Compose. Repeat startups reuse container `49881d31b9170027d9b68d46b4ccb7cec8f7d4edf5962b9959e087b357b93441`, API21664 and Web21744; PostgreSQL revision0039 and92 main tables remain. The Windows PostgreSQL server has no running process. Host19 focused contract tests, config-contract validation, Compose validation,286-file Markdown-link scan and focused diff checks passed. The worker's one filesystem-sandbox test failure passes on the host. `BACKUP_RESTORE.md` now documents the current container and the user's cleanup instruction.

Independent current-data repository parity additionally invoked actual market source-coverage and normalized-view reads at limits1,2,3,5,10,40,100,500,1000 against both clusters: every ordered selection and normalized result hash matched. Tariff duplicate exact-match groups=0; equal-time conflicting FX groups=0. This bounds acceptance to the current data. Locale-dependent text ordering remains explicitly different; future Unicode equivalence and all future tie behavior are not claimed. See `DOCKER_COLLATION_CODE_REVIEW.md` and `.dnx-out/locale-semantics-20261009/reviewer-selection-parity.json`.

Final actual Chromium UAT passed:2 contracts,3 versions,7 runs and4 dataset snapshots appear through authenticated API reads and preserve exact IDs after reload. The reviewer inspected screenshots of the actual two-row contract Library, saved strategy run history and four-row dataset catalogue. No manual contract/strategy/dataset mutation was performed. The first attempt deliberately blocked5 automatic optimization POSTs and failed that assertion; subsequent runs allowed only the existing automatic optimizer call, recorded its job side effects, and still blocked all other non-login mutations. The final evidence honestly says `read_only_after_login=false`; legacy artifact filenames containing `readonly` do not mean the final run was read-only.

After final UI and another idempotent startup, all9 database structural comparisons have no unexpected differences. In the main database,89 tables are completely unchanged by whole-row count/hash. The original custom dump's COPY rows for the three appendable tables were compared in memory against the live database: all422 original audit rows,214 original job rows and69 original session rows are unchanged and present. The only additions are14 audit records,10 automatic optimization jobs and4 login sessions. No original row loss or mutation was found. Evidence: `.dnx-out/docker-postgres-cluster-20261008/evidence/postcutover-original-records.json` and `postcutover-all-databases.json`.

**Cleanup has not executed.** The user already explicitly authorized deletion after these success gates. The reviewer resolved and checked18 exact repository-contained targets totaling423754945 bytes:old `.dnx-pgdata`, stopped cold copy,14 project PostgreSQL dumps and2 obsolete pre-cutover configuration/launcher backups. No reparse points were present. Current Docker volume, live credentials and non-data evidence are excluded; the recreated container has0 `/tmp/*.dump` files. Both the native PowerShell manifest deletion and the safer single literal-path deletion of `.dnx-pgdata` were rejected before process creation by automatic approval review, with the sole reason `blocked by policy`. All18 targets still exist. No alternate-tool bypass was attempted. This is a tool-policy blocker, not missing user authorization. Exact paths and outcomes are in `cleanup-manifest.json` and `cleanup-result.json` under the evidence folder.

Remaining:perform the authorized cleanup only through a permitted execution path; continue the full product/data-source acceptance programme. The preserved `nexus` SUPERUSER role remains a separate customer least-privilege gate. The frontend's automatic optimization jobs and legacy engine/tie-selection risks remain tracked product work; this migration does not certify those broader concerns.
