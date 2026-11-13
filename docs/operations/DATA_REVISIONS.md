# Provider revisions and open gas days

ENTSOG and GIE publish provisional figures and correct them later. This page says what the
store does when a figure changes, where the earlier figure goes, and how a read "as of" an
earlier time behaves. Schema: migration `0062_observation_revisions`.

## What a revision is

A revision is a later receipt of the **same observation** (same source system and natural
key) with a **different value**. Only value fields may differ:

| Table | Revisable | Everything else is identity |
|---|---|---|
| `flow_observations` (ENTSOG) | `original_value`, `flow_mcm_d`, `native_rate_json`, `point_name`, metadata `flowStatus` | source, point, direction, period, kind, unit, normalizer version, research flag, `operatorKey`, `periodType` |
| `capacity_observations` (ENTSOG) | `original_value`, `capacity_mcm_d`, `native_rate_json`, `point_name`, metadata `flowStatus` | as above, with capacity type |
| `storage_observations` (GIE AGSI) | inventory, working capacity, fill, injection, withdrawal, facility name | source, dataset, facility, country, period |
| `lng_observations` (GIE ALSI) | inventory, send-out, DTMI, terminal name | source, dataset, terminal, country, period |

A revision is accepted only when it was received after the version it replaces. Refused,
with the whole batch rolled back and the stored rows untouched:

- a different identity field under an existing key: `entsog_revision_identity_conflict` /
  `gie_revision_identity_conflict` (for example another source or operator under the key);
- a changed value received no later than the stored one (an old capture replayed):
  `entsog_revision_not_newer` / `gie_revision_not_newer`.

EEX and every other source keep the earlier rule: any change is refused
(`*_revision_requires_history`).

## Where it is recorded

In one transaction:

1. the version being replaced is appended to `observation_revisions`: every column of the
   old row (`prior_row_json`), the changed field names, when it was received
   (`prior_received_at_utc`), when it was superseded (`superseded_at_utc`), the receipt
   references of both versions, and the reason (`value_changed` or `period_closed`);
2. the observation row takes the provider's latest value and lineage. `observed_at_utc`
   keeps the **first** receipt; `revised_at_utc` is the receipt of the current value.

`observation_revisions` is append-only: no code updates or deletes it, and a schema
downgrade refuses to drop it while it holds rows.

The ingest report counts `inserted`, `updated` (current rows replaced, each with one
history record), `unchanged` and `revised` (those of the updated rows whose value changed).
`scripts/ops/data_quality_report.py` shows revised rows per dataset over the last 7 days
(`rev 7d`; the JSON form also has `closed_snapshots`).

## Reading as of an earlier time

A version was the known value from its own receipt until the next one. A read as of `T`:

- leaves out rows first received after `T`;
- for a row whose current value was received after `T`, uses the revision record whose
  interval contains `T`.

`db/repositories/observation_revisions.py` does this (`versions_as_of`, `all_versions`).
The north-west Europe balance's history (`landed_supply`, `_daily_sum`) reads through it.
Research datasets get one evidence record per version, each available from its own receipt;
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

Capacity is published ahead of its period by nature; the open-day rule does not apply.

## Operator checks

```sql
-- Revisions in the last day, by table and reason
SELECT observation_table, reason, COUNT(*) FROM observation_revisions
WHERE recorded_at_utc > now() - interval '1 day' GROUP BY 1, 2;

-- The history of one observation
SELECT prior_row_json->>'original_value', prior_received_at_utc, superseded_at_utc, reason
FROM observation_revisions WHERE observation_id = :id ORDER BY superseded_at_utc;
```
