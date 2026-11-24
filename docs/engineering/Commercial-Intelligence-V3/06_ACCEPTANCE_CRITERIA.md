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

## M5: price, FX and outage events (met)

| # | Criterion | Evidence |
| --- | --- | --- |
| B1 | A settlement row maps to the period label an opportunity stores; spans that are no canonical period give no event | `test_a_settlement_row_maps_to_the_period_an_opportunity_stores` (9 cases) |
| B2 | Builders give `hub:`, `fx:` and `outage:` keys; a same-day correction is the same event, the next trade day is not; REMIT versions share one identity | `test_builders_give_the_keys_opportunities_store` |
| B3 | Capturing the same store twice writes nothing the second time | `test_capture_publishes_once_then_a_correction_reaches_only_its_readers` |
| B4 | A new TTF day-ahead settlement, then its correction, each re-run only `sell_down` (trigger `outbox`); the correction is revision 2 superseding 1 | same test |
| B5 | The old figure sent again after the correction writes nothing | same test |
| B6 | REMIT versions 1 and 2 are revisions 1 and 2 of one event at priority 0; a stale copy of version 1 writes nothing | `test_remit_versions_are_revisions_of_one_event_and_late_versions_change_nothing` |
| B7 | A EUR fixing reaches the stored cross pairs that contain its other currency | `test_a_fixing_reaches_the_cross_pairs_that_contain_its_currency` |
| B8 | An importer's rows and their events commit or roll back together | `test_an_importer_captures_in_the_same_transaction` |
| B9 | The scheduler captures after each cycle, and a second cycle captures nothing new | `test_the_scheduler_captures_after_ingestion` |
| B10 | A change noted while the scheduled evaluation runs stays pending (fails on the old code) | `test_opportunity_schedule_race.py`, and on PostgreSQL `test_the_scheduled_evaluation_keeps_a_change_noted_while_it_runs` |
| B11 | Capture on PostgreSQL writes each figure once | `test_capture_on_postgres_writes_each_figure_once` |

## M5b (met)

| # | Criterion | Test |
| --- | --- | --- |
| C1 | A contract's event carries a digest of its terms, ignores who saved it and holds no term value | `tests/integration/test_desk_event_capture.py::test_a_contract_digest_ignores_who_saved_it_and_carries_no_term` |
| C2 | A contract edit re-runs only the evaluators that read it; going back to the old terms is a new revision | `test_a_contract_edit_reaches_only_its_readers_and_a_return_to_old_terms_is_news` |
| C3 | A hedge band and a retirement are contract changes | `test_a_hedge_band_and_a_retirement_are_contract_changes` |
| C4 | Approving an assumption version publishes only the keys whose value moved | `test_an_approved_version_publishes_only_the_keys_whose_value_moved` |
| C5 | Capturing the desk tables again repeats nothing | `test_the_desk_tables_captured_again_repeat_nothing` |
| C6 | A later publication returning to earlier content is a revision, not out of order | `tests/domain/test_market_events_model.py::test_the_publication_decision` |

## M6 (met)

| # | Criterion | Test |
| --- | --- | --- |
| D1 | A stale source raises one alert (not one per cycle) and clears it when fresh | `tests/integration/test_feed_and_outbox_alerts.py::test_a_stale_source_raises_one_alert_until_it_is_fresh` |
| D2 | A source never successful alerts only after its stale threshold; a disabled source raises nothing | `test_a_source_never_successful_alerts_only_after_its_stale_threshold`, `test_a_disabled_source_raises_nothing` |
| D3 | A dead letter raises an alert naming the consumer and event until replayed | `test_a_dead_letter_names_the_consumer_and_the_event_until_replayed` |
| D4 | Deliveries waiting past 15 min (warning) or 1 h (critical) raise a lag alert until drained | `test_deliveries_left_waiting_raise_a_lag_alert_until_drained` |

## LNG-1 cargo in transit (met)

| # | Criterion | Test |
| --- | --- | --- |
| E1 | The energy chain balances: loaded less boil-off to berth less gas in kind equals the send-out total | `tests/domain/test_lng_in_transit.py::test_energy_chain_balances_and_boil_off_runs_to_berth` |
| E2 | Send-out is allocated by gas day (06:00 CET), not calendar day | `test_send_out_is_allocated_by_gas_day_not_calendar_day` |
| E3 | An ETA slip across a month end suggests one roll due before the month stops trading, not two trades | `test_eta_slip_into_next_month_suggests_a_roll_not_two_trades` |
| E4 | A month whose contract has expired needs short-notice cover | `test_a_month_that_stopped_trading_needs_short_notice_cover` |
| E5 | A missed slot has no send-out and names the hedge left without gas | `test_missed_slot_has_no_send_out_and_flags_the_orphaned_hedge` |
| E6 | Early arrival waits for the window; berth delay past laytime costs demurrage | `test_early_arrival_waits_for_the_window_and_boils_off_meanwhile`, `test_berth_delay_past_laytime_costs_demurrage` |
| E7 | Recorded hedges close the months; a slipped ETA is explained against the plan before it | `tests/api/test_lng_cargo_plan_api.py::test_recorded_hedges_and_a_slipped_eta_show_what_changed` |
| E8 | A what-if stores nothing; a market cargo has no plan; a viewer cannot record hedges | `test_what_if_compares_without_storing`, `test_a_market_cargo_has_no_plan` |
| E9 | The Python SDK reads, tries and records against the real application | `tests/sdk/test_lng_cargo_plan_client.py` |

## F1 audit blockers (met)

| # | Criterion | Test |
| --- | --- | --- |
| F1-1 | Every permission category names a minimum role; the gas-day status write refuses or records, never fails | `tests/api/test_gas_day_status_api.py` |
| F1-2 | Daily strategy tracks are evaluated by the scheduler, and a failure is reported without stopping the loop | `tests/integration/test_strategy_tracking_schedule.py` |
| F1-3 | A trader who also holds REVIEWER cannot set credit lines, mandates, hedge bands or opportunity thresholds, or approve assumption sets | `tests/api/test_risk_segregation_api.py::test_a_trader_who_is_also_a_reviewer_cannot_set_limits` |
| F1-4 | A mandate cannot be one's own under the principal id, name or display name | `test_a_mandate_cannot_be_ones_own_under_any_name` |
| F1-5 | A credit-line change keeps the fields it leaves out; the audit shows each change before and after | `test_a_credit_line_change_keeps_what_it_leaves_out_and_audits_the_diff` |
| F1-6 | Implausible prices, forward prices below zero, future exchange times and jumps no market makes are refused and nothing of the batch is stored | `tests/unit/test_feed_plausibility.py` |
| F1-7 | Only a key whose scopes name a licensed family may deliver prices under its label | `test_a_licensed_label_needs_its_own_grant`, `tests/api/test_strategy_tracks_api.py::test_who_may_track_and_who_may_deliver_ticks` |
| F1-8 | A scheduler (SCHEDULER) records nomination status; a reviewer cannot, and a scheduler edits nothing else | `tests/api/test_gas_day_status_api.py::test_a_scheduler_records_status_and_nothing_else` |

Four-eyes on limit changes (P-01's second half) is left to the reference-data approval work
with P-17, so that limits, terminal terms and freight routes share one maker-checker flow.

## DOC documentation and SDK (met)

| # | Criterion | Test |
| --- | --- | --- |
| DOC-1 | Every SDK example in the docs runs against a demo server and prints what the docs say | `tests/docs/test_sdk_examples.py` (needs `EUROGAS_NEXUS_EXAMPLES_BASE_URL` and `EUROGAS_NEXUS_EXAMPLES_API_TOKEN`; 12 passed against a local demo server) |
| DOC-2 | The SDK reference is generated from the code and cannot fall behind it | `tests/contract/test_sdk_reference_current.py` |
| DOC-3 | A refusal raises `NexusAPIError` carrying the server's code, message, recoverability and correlation id, and stays an `httpx.HTTPStatusError` | `tests/sdk/test_sdk_errors_and_urls.py` |
| DOC-4 | A base URL with a trailing slash works | `test_a_base_url_may_end_with_a_slash` |
| DOC-5 | A `postgresql://` URL without a driver uses the runtime's driver; an explicit driver is kept | `tests/integration/test_db_config.py::test_a_url_without_a_driver_uses_the_runtime_driver` |
| DOC-6 | Every local Markdown link resolves | `scripts/ci/check_markdown_links.py` |

## M7 to M9 (to be met)

- **M7.** Every new-engine opportunity that crosses the alert threshold reaches the
  notification outbox exactly once; the stream serves the new engine; the legacy path is
  removed with its tests replaced.
- **M8.** For a contract with ACQ and make-up terms, the shortfall and make-up balance
  match a hand-worked example to the cent, and a nomination change publishes an event.
- **M9.** A recommendation can be followed to the decision taken and, where the client
  records a trade reference, to realised value; one P&L definition serves all views.
