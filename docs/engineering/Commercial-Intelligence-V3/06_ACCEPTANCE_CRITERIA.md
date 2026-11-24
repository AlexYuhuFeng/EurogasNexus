# 06 Acceptance criteria

A criterion counts as met only when a named test or command shows it. Met criteria cite
[09_VALIDATION_EVIDENCE.md](09_VALIDATION_EVIDENCE.md).

## M4: market events and outbox (met)

| # | Criterion | Evidence |
| --- | --- | --- |
| A1 | Identity ignores publication and ingestion time; content ignores them too; a changed figure is a new revision | `test_identity_ignores_publication_and_ingestion_times_and_payload`, `test_the_publication_decision` |
| A2 | Publishing the same event twice writes once; a correction supersedes the previous revision's undelivered rows | `test_publish_is_idempotent_and_a_correction_supersedes` |
| A3 | An older figure arriving after a correction writes nothing | `test_the_publication_decision` |
| A4 | The five timestamps are stored, impossible orderings are named, latencies computed | `test_the_timeline_names_impossible_orderings_and_latencies`, `test_staleness_and_the_timeline` |
| A5 | Deliveries are taken by priority, then sequence | `test_delivery_is_by_priority_then_log_order` |
| A6 | A failing consumer retries with backoff 1, 2, 4, 8 min (cap 1 h), dead-letters after 5, and its writes roll back | `test_a_failing_consumer_is_retried_with_backoff_then_dead_lettered`, `test_backoff_doubles_and_is_capped`, `test_a_consumer_failure_leaves_none_of_its_writes` |
| A7 | Replay re-delivers the current revision; a new consumer can rebuild state; replaying twice gives the same result | `test_replay_reproduces_the_current_state_and_reaches_a_new_consumer` |
| A8 | A change to `hub:TTF:2026-11-18` re-runs only `sell_down`; to `contract:demo-haldor-24` only `hedge_gap`; trigger `outbox` | `test_an_event_re_evaluates_only_the_evaluators_that_read_its_key`, `test_events_without_keys_are_kept_but_not_sent_to_the_opportunity_consumer` |
| A9 | Staleness uses the one freshness rule; a subject without an expectation is never "live" | `test_staleness_uses_the_one_freshness_rule`, `test_staleness_and_the_timeline` |
| A10 | On PostgreSQL: notify only at commit; two workers never claim the same delivery; two racing publishers write once; the store refuses a second copy of a revision | `tests/integration/test_market_event_outbox_postgres.py` (4 tests) |
| A11 | Firm marks publish one event per cell carrying a digest, never the value | `test_a_firm_mark_write_publishes_one_event_per_cell` |
| A12 | A failing outbox never breaks the scheduler cycle | `test_the_scheduler_hook_records_and_drains_and_never_fails_the_loop` |
| A13 | Migration 0077 upgrades and downgrades; tables match the models | `tests/unit/test_market_event_outbox_migration.py`; downgrade -1 / upgrade on PostgreSQL |
| A14 | No existing test, lint or CI gate weakened | full suite and gates in 09 |

## M5 to M9 (to be met)

- **M5.** A settlement correction from a public source produces one `price.updated`
  revision with the hub-period key, and only dependent evaluators re-run; an unchanged
  re-download produces none. REMIT updates keep the message id as identity across moved
  start times.
- **M6.** A source past its expectation raises one alert (not one per cycle) and clears it
  when fresh; a dead letter raises an alert naming the consumer and event.
- **M7.** Every new-engine opportunity that crosses the alert threshold reaches the
  notification outbox exactly once; the stream serves the new engine; the legacy path is
  removed with its tests replaced.
- **M8.** For a contract with ACQ and make-up terms, the shortfall and make-up balance
  match a hand-worked example to the cent, and a nomination change publishes an event.
- **M9.** A recommendation can be followed to the decision taken and, where the client
  records a trade reference, to realised value; one P&L definition serves all views.
