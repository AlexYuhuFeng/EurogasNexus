# Provider revisions and open gas days

ENTSOG, GIE, National Gas, ENTSO-E and Elexon publish provisional figures and correct them later. This
page says what the store does when a figure changes, where the earlier figure goes, and how
a read "as of" an earlier time behaves. Schema: migrations `0062_observation_revisions` and
`0063_resplit_power_revisions` (power history, the `range_resplit` reason).

## What a revision is

A revision is a later receipt of the **same observation** (same source system and natural
key) with a **different value**. Only value fields may differ:

| Table | Revisable | Everything else is identity |
|---|---|---|
| `flow_observations` (ENTSOG) | `original_value`, `flow_mcm_d`, `native_rate_json`, `point_name`, metadata `flowStatus` | source, point, direction, period, kind, unit, normalizer version, research flag, `operatorKey`, `periodType` |
| `capacity_observations` (ENTSOG) | `original_value`, `capacity_mcm_d`, `native_rate_json`, `point_name`, metadata `flowStatus` | as above, with capacity type |
| `storage_observations` (GIE AGSI) | inventory, working capacity, fill, injection, withdrawal, facility name | source, dataset, facility, country, period |
| `lng_observations` (GIE ALSI) | inventory, send-out, DTMI, terminal name | source, dataset, terminal, country, period |
| `storage_observations`, `lng_observations` (National Gas, GB) | as GIE, plus metadata `basis` and `provisional` | as GIE |
| `power_observations` (ENTSO-E, Elexon) | `value` | source, zone, metric, process type, period, unit |

National Gas (since 2026-11-14): a nomination-based value replaced by the D+2 allocation, and
a stock published after the first run, are revisions (`value_changed`); the record's
`changed_fields` says which (for example `withdrawal_twh_d`, `inventory_twh`,
`metadata_json.provisional`). A basis change alone (an allocation equal to its nomination)
is still recorded, so the history shows when the figure became final. Before this date the
script overwrote rows in place, so GB rows firmed up before 14 November have no history.

A revision is accepted only when it was received after the version it replaces. Refused,
with the whole batch rolled back and the stored rows untouched:

- a different identity field under an existing key: `entsog_revision_identity_conflict` /
  `gie_revision_identity_conflict` (for example another source or operator under the key);
- a changed value received no later than the stored one (an old capture replayed):
  `entsog_revision_not_newer` / `gie_revision_not_newer`.

EEX and every other source keep the earlier rule: any change is refused
(`*_revision_requires_history`).

**Power** (since 2026-11-14, migration `0063`). `db/repositories/power.py` appends the
replaced value to `observation_revisions` (`value_changed`, `changed_fields: ["value"]`) and
the row keeps its first `published_at_utc` and `ingested_at_utc`; `revised_at_utc` is the
receipt of the current value. A migration was needed after all: `observation_revisions`
had check constraints naming the four gas tables and the two reasons. Power's first version
is available from `published_at_utc` (the provider's publication, capped at the regulatory
deadline); a revision from its receipt by this store. The parser caps the publication time
at the deadline, so the first and the revised publication of an actual carry the same time
and cannot order versions; before this change the in-place update therefore made a revised
actual readable from the deadline, a look-ahead. Refused, nothing of the batch kept: a stored
id with another zone, metric, process type, period, unit or source
(`power_revision_identity_conflict`). Values replaced before 14 November have no history
(the soak run of 14 November replaced 44 ENTSO-E values in two runs). First live run with
history (14 Nov 06:54 UTC, `src-entsoe`, two days): 175 revised values recorded.

## ENTSOG capacity ranges re-split between reads

ENTSOG publishes capacity over validity ranges and re-splits them between reads (12 Nov
read: UGS-00397 firm technical entry 13 Nov - 1 Dec 64.37 GWh/d; 13 Nov read: 13-14 Nov
28.13 GWh/d and 14 Nov - 1 Dec 64.37 GWh/d). The provider's record id contains the period
end, so each range is its own observation and all are kept: each was the provider's
statement when received, and an as-of read needs it. On 14 Nov 2026 the store held 539
(point, direction, type, operator, start) keys two or three times, 168 with different
values; 1,431 of 12,647 rows overlap another range of their series.

Readers resolve the overlap (`application/capacity_resolution.py`,
`CAPACITY_RESOLUTION_RULE`): per point, direction, capacity type and instant, the covering
range whose value was received last (ties: later start, then shorter range), from one
operator per point (the flow rule). As of `T`, only versions received by `T` compete
(`resolve_capacity_as_of`). The physical capacity API and the agent bridge read through it;
each returned row's period is the part of its published range where it holds.

That order needs one thing from ingestion: an unchanged re-receipt keeps its first receipt,
so if the provider goes back to a range it had re-split, the stale split would keep
winning. When a stored range is re-published and a stored range of the same series that
overlaps it was received later (and is not in this read), the range takes this receipt:
its version goes to `observation_revisions` with reason `range_resplit` (no field changed)
and `revised_at_utc` moves (`db/repositories/capacity_ranges.py`). The ENTSOG capacity ingest
report counts these as `resplit` (inside `updated`). `scripts/ops/capacity_range_resplits.py`
counts overlaps and replays the archived raw pages with this rule (dry run by default).

The data-quality report keys capacity by range (start and end) and reports overlapping
ranges as a fact (`overlapping_rows`), not as duplicates.

## Where it is recorded

In one transaction:

1. the version being replaced is appended to `observation_revisions`: every column of the
   old row (`prior_row_json`), the changed field names, when it was received
   (`prior_received_at_utc`), when it was superseded (`superseded_at_utc`), the receipt
   references of both versions, and the reason (`value_changed`, `period_closed` or
   `range_resplit`);
2. the observation row takes the provider's latest value and lineage. `observed_at_utc`
   keeps the **first** receipt (power: `published_at_utc`/`ingested_at_utc`);
   `revised_at_utc` is the receipt of the current value.

`observation_revisions` is append-only: no code updates or deletes it, and a schema
downgrade refuses to drop it while it holds rows.

The ingest report counts `inserted`, `updated` (current rows replaced, each with one
history record), `unchanged` and `revised` (those of the updated rows whose value changed).
`scripts/ops/data_quality_report.py` shows revised rows per dataset over the last 7 days
(`rev 7d`, power included; the JSON form also has `closed_snapshots` and `resplit_ranges`).

## Freshness reads "last received"

A source that only revises rows is still delivering. Freshness and monitoring take the later
of `observed_at_utc` and `revised_at_utc` (`observation_revisions.last_received_column`):
the Sources page (`_runtime_source_latest_observed`), the data-ops freshness evaluation
(`dataops_runtime._latest_observation_for`) and the data-platform provenance summary.
"First seen" stays where point-in-time availability is meant: as-of reads, research
availability and the data-quality report's lateness. The data-quality report's age is the
age of the newest *period*, which a revision does not change.

## Reading as of an earlier time

A version was the known value from its own receipt until the next one. A read as of `T`:

- leaves out rows first received after `T`;
- for a row whose current value was received after `T`, uses the revision record whose
  interval contains `T`.

`db/repositories/observation_revisions.py` does this (`versions_as_of`, `all_versions`;
for power the first receipt is `published_at_utc`). The north-west Europe balance's history
(`landed_supply`, `_daily_sum`) reads through it, and capacity through
`resolve_capacity_as_of`. Research datasets (power, storage, LNG, flows) get one evidence
record per version, each available from its own receipt;
the builder takes, per series and period, the latest version available at each origin, so a
backtest never sees a revision before it was received.

## Open gas days (ENTSOG flows)

ENTSOG publishes the running gas day; a flow row received before its period ended is a
partial-day snapshot (live: Dornum 157.8 GWh at 11:56 UTC on 12 November against 756.7 GWh
for the closed day).

- **Stored, not dropped**, so a reader that asks for within-day data can have it.
- **Replaced at close**: the first receipt after the period end replaces it, even with an
  equal value, and the snapshot goes to `observation_revisions` with reason `period_closed`.
- **Never read as a closed day**: the rule is `pipeline_supply.CLOSED_DAY_RULE` /
  `published_after_close` (value received at or after the period end;
  `closed_day_clause` in SQL). The balance, the map, the analysis snapshot, research series
  and the agent bridge apply it. The agent bridge's `flow_rows(include_open_day=True)`
  returns open-day rows with `open_gas_day: true`.

Capacity is published ahead of its period by nature; the open-day rule does not apply (its
overlapping ranges are resolved instead, see above).

## Operator checks

```sql
-- Revisions in the last day, by table and reason
SELECT observation_table, reason, COUNT(*) FROM observation_revisions
WHERE recorded_at_utc > now() - interval '1 day' GROUP BY 1, 2;

-- The history of one observation
SELECT prior_row_json->>'original_value', prior_received_at_utc, superseded_at_utc, reason
FROM observation_revisions WHERE observation_id = :id ORDER BY superseded_at_utc;
```
