# Retention schedule

For: compliance officers, the data protection officer, internal audit and the operators who
run the product. Decision record:
[2026-11-26-standby-backup-object-storage-retention](../architecture/decisions/2026-11-26-standby-backup-object-storage-retention.md).
What the code does is in `src/eurogas_nexus/application/retention.py`; a test fails if this
document stops naming every data class and table listed there.

## The rules in one paragraph

Eurogas Nexus keeps every record a regulation may ask for. Trading records, decisions, approvals
and the audit trail are kept for at least seven years, and the product's own retention job never
removes them. Settlements, prices, marks and fundamentals are kept without limit. Only three
kinds of high-volume technical data are reduced, and each is first copied to the firm's object
storage, read back and checked, before anything leaves the database. Settings can lengthen a
period but never shorten it below the floor written in the code. Every retention run, scheduled
or by hand, is recorded and audited, and a dry run shows what a run would do without doing it.

Before 2026-11-26 the product deleted market quotes after 30 days and market observations
(including settlement prices) after 90 days, without an archive, when an operator ran the
pruning script. That script has been removed.

## Schedule

| Data class | What it is | Tables | Kept in the database | Then | Floor | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `trading_records` | The firm's trades as copied from the ETRM, books, trader mandates, credit lines, hedges and their approvals, LNG cargoes and slots, capacity bookings, contract deliveries, gas-day schedules and nominations, profit-and-loss snapshots, captured deals with their import files, unread rows, day closes, the daily packs sent and the physical or financial choices made by hand | `screen_order_observations`, `trading_books`, `trader_mandates`, `credit_lines`, `hedge_approvals`, `lng_cargo_hedges`, `lng_cargoes`, `regas_slots`, `capacity_bookings`, `contract_daily_deliveries`, `upstream_resource_contracts`, `upstream_contract_revisions`, `gas_day_schedule_lines`, `gas_day_nomination_events`, `portfolio_pnl_snapshots`, `captured_deals`, `deal_import_files`, `deal_import_problems`, `deal_day_closes`, `daily_packs`, `deal_position_kinds` | Always | Never removed by the product | 7 years | REMIT Art. 8 with Implementing Regulation 1348/2014 Art. 9 (5 years); MiFID II Art. 16(6)-(7) with Delegated Regulation 2017/565 Art. 72-76 (5 years, up to 7 on request); EMIR Art. 9(2) (5 years after termination). The longest, 7 years, is the floor. |
| `audit_and_decisions` | The audit trail, decision cases and their records, reviews, change requests, entitlement decisions, licensed-data use, disruption decisions, gas-day delegations | `audit_events`, `decision_cases`, `decision_case_records`, `review_decisions`, `change_requests`, `entitlement_decisions`, `licensed_data_use`, `lng_disruption_decisions`, `gas_day_delegations` | Always | Never removed by the retention job | 7 years | MiFID II Art. 16(6) and MAR Art. 16 (records of decisions and their evidence); the firm's control framework. The audit trail is append-only. |
| `settlements_curves_and_marks` | Exchange settlements, price assessments and indices, option settlements, the firm's marks, valuations, market reports | `market_observations`, `option_settlements`, `firm_marks`, `live_market_marks`, `valuation_snapshots`, `valuation_snapshot_inputs`, `market_reports` | Always | Never removed | none (kept) | Needed to recompute any past figure and for five years of history. |
| `fundamentals` | Flows, capacity, storage, LNG, power, weather forecasts, demand, FX, interest rates, outage messages (REMIT UMMs), costs, news, and every revision of them | `flow_observations`, `capacity_observations`, `storage_observations`, `storage_inventory_observations`, `lng_observations`, `power_observations`, `fx_observations`, `interest_rate_observations`, `forecast_observations`, `observation_revisions`, `observation_temporal_metadata`, `national_gas_actual_demand`, `remit_umm_messages`, `cost_observations`, `news_items` | Always | Never removed (later: older years move to Parquet files, still readable) | none (kept) | The product is the master for fundamentals; UMMs are inside-information evidence. |
| `exchange_trade_prints` | Trades printed by the customer's licensed feed | `market_trades` | Always | Never removed | none (kept) | Evidence of the market the desk saw. |
| `live_ticks` | Live quotes from a licensed feed or the demo simulator | `market_quotes` | 90 days in full | Each UTC day is copied in full to object storage, checked, then the database keeps the last quote of each minute for each instrument (one-minute bars) | 90 days | No duty to keep every tick; the full ticks stay available from the archive. Raise the period if surveillance needs ticks in the database for longer. |
| `raw_source_pages` | Each page exactly as a source sent it (the lineage behind every stored observation) | `raw_payload_contents`, `raw_payload_archives` | 28 days after the page was last received | The page moves to object storage; the receipt and the page's digest stay in the database and the page is read back on demand | 7 days | Lineage; kept per each source's terms ([DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md)). Each distinct page is stored once. |
| `intraday_opportunity_snapshots` | Intraday opportunity snapshots computed from quotes | `intraday_opportunities` | 90 days | Each UTC day is copied in full to object storage, checked, then removed from the database | 7 days | Derived from the archived quotes and reproducible. |

Tables not named above are reference data, configuration, identity and working state. The
retention job does not touch them. Three of them have their own operator-only tools, each
dry-run by default and audited: audit rows older than seven years, through the one audit
prune path (`POST /api/audit/prune`, or `scripts/ops/prune_audit_events.py` run as the schema
owner). It refuses any window below seven years (`EUROGAS_NEXUS_AUDIT_RETENTION_DAYS` cannot
lower it), deletes only after a second administrator approved the change (dual control), removes
only the oldest contiguous part of the hash chain and records a prune anchor, so
`GET /api/audit/verify` still verifies the rest, and audits the prune itself
(`docs/security/DATABASE_ROLES.md`); export the range first. The other two: finished job
records (`scripts/ops/prune_job_records.py`), and personal data on a data subject's request
(`scripts/ops/personal_data_export.py` and the processing register, `scripts/ops/processing_register.py`).

## What "archived" means, exactly

1. The rows for one whole UTC day are written to a compressed file (JSON lines, gzip) in the
   firm's object storage under `<data class>/<table>/<yyyy>/<mm>/<dd>.jsonl.gz`.
2. The file is read back and its SHA-256 digest and size are compared with what was written.
3. A manifest next to it (`.manifest.json`) records the table, the day, the row count, the
   columns, the digest and the rule applied afterwards; it is also read back and checked.
4. A row in `retention_archives` records the file, the manifest, the digest and the counts.
5. Only then are rows removed from the database, in the same transaction as step 4. If any
   check fails, nothing is removed and the run reports the failure.

Raw pages follow the same steps per page (`raw-pages/<digest>.gz`) with one manifest per batch.

Without configured object storage the job removes nothing and reports
`blocked_no_object_store`.

## Getting archived data back

- **Look at it without changing anything:**
  `python scripts/ops/retention.py show --archive-id <id>` (first 20 rows; `--limit` for more).
- **Put it back into the database:**
  `python scripts/ops/retention.py restore --archive-id <id> --principal <your id>`. Rows that are
  still in the database are left as they are; the restore is audited.
- **Find the archive for a day:** `python scripts/ops/retention.py archives --class live_ticks`.
- **Raw pages** are read back automatically when a lineage or replay tool asks for them.
- Without the product: each file is ordinary gzip-compressed JSON lines; the manifest states
  the digest to check it against (`sha256sum`).

## Changing the schedule

- Lengthen a period or switch a reduction off (both always allowed):
  `python scripts/ops/retention.py set-policy --class live_ticks --hot-days 365 --principal <id>
  --reason "<why>"`. The change is audited. A value below the floor is refused.
- Shorten below a floor, or remove anything in a class that is kept: not possible by setting.
  It needs a code change and a decision record.
- See the schedule in force: `python scripts/ops/retention.py schedule`.

## When it runs

The scheduler (`scripts/ops/run_dataops_scheduler.py`) runs one pass a day after 02:00 UTC
(`EUROGAS_NEXUS_RETENTION_HOUR_UTC`). `EUROGAS_NEXUS_RETENTION_MODE` is `enforce` (default),
`dry_run` (report only) or `off`. Each pass is bounded (seven days per class, a few thousand
pages) so it never holds up ingestion; a backlog is worked through over several nights or with
`python scripts/ops/retention.py run --until-done`. Each pass writes a `retention_runs` row and an
`audit_events` row (`retention.enforce` or `retention.dry_run`) with the counts per class.

## Backups are separate

Database backups (base backups and the write-ahead log, pgBackRest) are kept in the object
store's `backups` bucket for their own retention period (two weekly full backups and their
differentials by default), see [BACKUP_RESTORE.md](../operations/BACKUP_RESTORE.md). A row
removed from the database under this schedule stays in older backups until they expire; the
archive above is the long-term copy.
