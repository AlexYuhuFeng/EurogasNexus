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
| F1-9 | An administrator cannot issue a key for another person; a person issues, lists and revokes their own keys only from an interactive sign-in, within their own scopes and a 365-day limit | `tests/security/test_personal_api_keys.py`, `tests/security/test_enterprise_access_api.py` |
| F1-10 | Editing one field of a credit line keeps its deals; unlinking all needs confirmation; a cleared critical limit alert waits for acknowledgement | `tests/api/test_risk_limits_api.py::test_the_edit_form_reads_the_whole_line_and_an_empty_list_does_not_unlink`, `tests/unit/test_limit_monitoring.py::test_a_cleared_breach_waits_for_acknowledgement` |

Four-eyes on limit changes (P-01's second half) is met by P-17 below: limits, hedge bands,
firm marks, terminal terms and freight routes share one maker-checker flow.

## DOC documentation and SDK (met)

| # | Criterion | Test |
| --- | --- | --- |
| DOC-1 | Every SDK example in the docs runs against a demo server and prints what the docs say | `tests/docs/test_sdk_examples.py` (needs `EUROGAS_NEXUS_EXAMPLES_BASE_URL` and `EUROGAS_NEXUS_EXAMPLES_API_TOKEN`; 12 passed against a local demo server) |
| DOC-2 | The SDK reference is generated from the code and cannot fall behind it | `tests/contract/test_sdk_reference_current.py` |
| DOC-3 | A refusal raises `NexusAPIError` carrying the server's code, message, recoverability and correlation id, and stays an `httpx.HTTPStatusError` | `tests/sdk/test_sdk_errors_and_urls.py` |
| DOC-4 | A base URL with a trailing slash works | `test_a_base_url_may_end_with_a_slash` |
| DOC-5 | A `postgresql://` URL without a driver uses the runtime's driver; an explicit driver is kept | `tests/integration/test_db_config.py::test_a_url_without_a_driver_uses_the_runtime_driver` |
| DOC-6 | Every local Markdown link resolves | `scripts/ci/check_markdown_links.py` |

## AIR AI by role, personal workspaces and the improvement loop (AIR-1 to AIR-5 and AIR-7 met in GOV-1, AIR-6 partly met; the rest to be met)
## M7 live pipeline (met except M7-10)

Design and budgets: [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md).
| # | Criterion | Test |
| --- | --- | --- |
| M7-1 | The listen worker is deployed with the scheduler and runs the due full evaluation after each drain; a drain takes the whole backlog (no event cap) and hands back only when its time budget is spent; the debounce is one minute | `tests/integration/test_live_trigger.py` |
| M7-2 | A full sweep and a targeted re-evaluation never merge at once: a second sweep is told busy while one holds the lock (PostgreSQL) | `test_a_second_sweep_is_told_busy_while_one_holds_the_lock_on_postgres` |
| M7-3 | A listed new-engine opportunity raises one alert and one notification; the alert is resolved when the opportunity is withdrawn or its validity ends | `tests/integration/test_opportunity_alerts.py::test_a_listed_opportunity_raises_one_alert_and_notifies_once`, `::test_an_opportunity_that_stops_being_viable_is_withdrawn` |
| M7-4 | Only listed opportunities alert, and an opportunity alert is shown by the opportunity's own read rule | `::test_only_listed_opportunities_alert`, `::test_an_opportunity_alert_is_shown_by_the_opportunitys_own_rule` |
| M7-5 | Two workers cannot queue or send the same notification twice (PostgreSQL) | `::test_two_workers_queue_and_send_a_notification_once_on_postgres` |
| M7-6 | Each alert type has an owner and an escalation named in its notification; opportunities and nomination deadlines have their own categories, and a channel subscribed to `alert` keeps receiving them | `::test_alerts_are_routed_to_their_owner_and_an_alert_subscription_keeps_them`, `tests/unit/test_gas_day_checklist.py::test_deadlines_feed_what_needs_me_and_the_outbox_once` |
| M7-7 | `/api/stream/opportunities` pushes an opening, a withdrawal with its reason (including the end of the validity window before the engine runs again) and each finished evaluation, filtered by the opportunity's read rule | `tests/api/test_opportunity_stream.py`, `tests/security/test_stream_entitlement.py::test_an_opportunity_change_follows_the_opportunitys_own_read_rule` |
| M7-8 | The Opportunities page re-reads on a notice, says how old its data is and whether it is live or polling every minute, and names withdrawals until dismissed | `clients/web/tests/opportunitiesModel.test.ts` (the three stream tests) |
| M7-9 | End-to-end latency (price committed to the change on the stream) measured before and after on PostgreSQL | `scripts/ops/measure_live_latency.py`, figures in [09](09_VALIDATION_EVIDENCE.md) |
| M7-10 | The legacy intraday engine is removed | Not met: blocked by its dependents ([15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 9, R19) |
Not in M7: an alert on an LNG ETA or slot change, timed escalation when an owner has not
acknowledged, and quote capture for the opportunity engine (R14). See 15 sections 2 and 5.
## M8 and M9 (to be met)
## AIR AI by role, personal workspaces and the improvement loop (AIR-1 and AIR-2 met; the rest to be met)
Design: [14](14_AI_ROLES_PERSONALISATION_AND_IMPROVEMENT_LOOP.md). Stage in brackets.
| AIR-1 | (1) A signed-in person sends a suggestion through `/api/support/reports` with category `suggestion`; it is stored as P4 whatever urgency was sent and queues a low-severity notification; no OpenAPI path or operation is added | `tests/api/test_support_api.py::test_a_suggestion_is_stored_as_p4_and_never_pages_the_desk` |
| AIR-2 | (1) "Send feedback" in the account menu opens the report dialog in suggestion mode, without an urgency choice, and the client diagnostics carry the role composition | `clients/web/tests/supportReport.test.ts` (AIR-2 tests) |
| AIR-3 | (2) Every AI use is in a machine-readable register with its level, roles, controls, evaluation set and threshold; a model call from a use not in the register fails a test | `tests/unit/test_ai_register.py::test_every_use_is_described_completely`, `::test_only_pinned_modules_call_the_provider_and_each_binds_a_registered_use`, `::test_an_unregistered_use_cannot_be_called_or_switched` (register: `domain/ai/register.py`) |
| AIR-4 | (2) Each AI use can be switched off in organisation settings; a switched-off use returns the rule text with basis `rule`, and the switch is audited | `tests/api/test_ai_controls_api.py::test_a_switched_off_use_makes_no_provider_call_and_shows_the_rule_text`, `::test_invalid_switches_are_refused`; `tests/unit/test_ai_register.py::test_a_switched_off_use_may_call_no_tool` |
| AIR-5 | (2) Every AI audit row carries the prompt version, model id, evidence hash and output hash | `tests/api/test_ai_controls_api.py::test_the_audit_row_carries_prompt_version_model_id_and_hashes`, `tests/unit/test_ai_register.py::test_provenance_holds_versions_and_hashes_never_the_text` (the input hash is over the messages, which carry the evidence) |
| AIR-6 | (2) A change to a prompt, a check or the configured model fails CI unless the recorded evaluation set passes and the committed provider-run report for that version meets the use's threshold | Recorded-set half met: `tests/evals/test_ai_gate.py` (prompt text, prompt version, model id, evaluation-set hash and score; `scripts/ai/ai_gate.py --record`). The committed provider-run report is still to be written: it needs a networked run |
| AIR-7 | (2) A model can call only the capabilities its use and the caller's role allow; a call outside the allowlist is refused and audited | `tests/unit/test_ai_register.py::test_tool_refusal`, `::test_never_tools_are_refused_whatever_the_role`, `::test_the_runtime_refuses_a_model_tool_call_outside_the_allowlist`, `::test_mcp_and_research_run_as_their_registered_uses` |
| AIR-8 | (3) A feedback item moves received, triaged, clarifying, specified, in build, in review, shipped or declined; a specification cannot be approved without the requester's recorded confirmation | to be written |
| AIR-9 | (3) The repository map is generated from the code and a test fails when it is out of date | to be written |
| AIR-10 | (3) One command prints the OpenAPI paths and operations, permission rows and the documents that pin them, before and after a change | to be written |
| AIR-11 | (4) A saved view holds only catalogue components with parameters inside their schemas; every save is a new version; a pinned panel cannot be removed | to be written |
| AIR-12 | (4) A view a lead publishes renders each component with the viewer's own authority; a component the viewer may not read shows as not available, never with the author's data | to be written |
| AIR-13 | (5) "Make me a view": the validator refuses every invalid case in the evaluation set, the model produces a valid view for at least 90 % of in-catalogue intents, nothing is saved before the person accepts, and an out-of-catalogue ask offers a prefilled suggestion | to be written |
| AIR-14 | (6) The triage classifier's proposals meet the accuracy threshold on its evaluation set, and a triager's correction is kept as a new case | to be written |
## LNG-2 a delayed cargo reaches each role (met)

The owner's scenario (2026-11-24): a firm cargo due in three days is hedged forward; news
arrives that it will be late. The acceptance test drives it end to end on SQLite (import,
outbox, consumer, alerts, channels); a second test drives the same chain on PostgreSQL through
the listen worker running as its own process and measures it. Design and who hears what:
[12](12_LNG_CARGO_IN_TRANSIT.md) "Who hears about a change"; routing: [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 5.

| ID | Criterion | Evidence |
| --- | --- | --- |
| LNG2-1 | An ETA change from any source (import, vessel feed, manual edit) publishes one `cargo.changed` event and the plan is rebuilt from it within the published latency for cargo data (doc 15, the live pipeline and latency budget) | `tests/integration/test_lng_cargo_change_roles.py::test_a_late_cargo_reaches_each_role_with_its_own_message` (one event, plan rebuilt by the `cargo_roles` consumer); `tests/integration/test_lng_cargo_change_postgres.py::test_a_late_cargo_reaches_each_role_through_the_listen_worker` (commit to every role's notification queued: median about 0.66 s on the worker's first change, 0.11 s after; budget 15 minutes; figures in [09](09_VALIDATION_EVIDENCE.md)). A manual edit is a one-line import with its own source, as before; a hedge edit publishes through `PUT .../hedges` |
| LNG2-2 | The rebuilt plan names the hedge months that gained or lost gas, the mismatched forward sales and the roll or buy-back it proposes, with the arithmetic; nothing is executed | `tests/domain/test_lng_consequences.py::test_a_delay_across_the_month_end_proposes_a_roll_with_its_arithmetic`; `tests/integration/test_lng_cargo_change_roles.py::test_a_late_cargo_reaches_each_role_with_its_own_message` (Nov bought back at short notice, Dec sold, "physical + hedge = net" per month, due before Dec stops trading; the message says nothing is traded) |
| LNG2-3 | The trader who owns the book gets the hedge proposal; the scheduler gets the slot, berth and nomination consequences with the cut-offs they hit; risk gets the exposure and any limit it moves; the desk head gets it only when it is material by the configured threshold | `tests/integration/test_lng_cargo_change_roles.py::test_a_late_cargo_reaches_each_role_with_its_own_message` (each channel receives its own role's message and no other), `::test_an_energy_or_departure_change_below_the_threshold_skips_the_desk_head`, `::test_each_role_sees_its_own_item_on_today_and_the_cargo_board`; `tests/domain/test_lng_consequences.py::test_below_the_threshold_the_desk_head_hears_nothing`, `::test_a_mandate_newly_in_breach_is_material_and_critical_for_risk`; `clients/web/tests/cargoRoles.test.ts` |
| LNG2-4 | Each role's message is deduplicated, respects cooldown and materiality, says how current its inputs are, and is withdrawn when a later change makes it moot | `tests/integration/test_lng_cargo_change_roles.py::test_a_late_cargo_reaches_each_role_with_its_own_message` (the same event again notifies no one; a change ten minutes later waits for the 30-minute cooldown; every message carries its inputs' line; the ETA corrected back withdraws all four and tells each role); `tests/domain/test_lng_consequences.py::test_digest_is_stable_for_the_same_content`, `::test_a_plan_that_did_not_change_tells_nobody` |
| LNG2-5 | The same chain works for a departure, energy, slot or hedge change, not only an ETA delay | `tests/integration/test_lng_cargo_change_roles.py::test_a_slot_change_and_a_hedge_change_take_the_same_chain`, `::test_an_energy_or_departure_change_below_the_threshold_skips_the_desk_head` |

The ETA carries its basis and confidence (lesson P3): `tests/unit/test_lng_positions_import.py::test_an_eta_carries_its_basis_confidence_and_source_lesson_p3`, `::test_an_unknown_eta_basis_refuses_the_file`; migration `0080_lng_eta_basis` in `tests/unit/test_lng_eta_basis_migration.py`.

## GOV-1 governance: audit with the change, AI controls, licensed-data use (met)
Lessons P4 to P6 in [16](16_COMPETITIVE_STUDY.md); AI controls are AIR-3 to AIR-7 above.
| # | Criterion | Test |
| --- | --- | --- |
| GOV1-1 | Each governed write (credit lines, mandates, hedge bands, LNG terminal terms, opportunity thresholds, assumption sets and approvals, firm marks, users, roles, groups, data licences, API keys and provider credentials, hedges on cargoes) writes its audit row in its own transaction; when the audit row cannot be written the write answers 503 `audit_unavailable` and nothing of it is stored | `tests/api/test_governed_audit_api.py::test_a_governed_write_fails_and_leaves_nothing_when_its_audit_row_cannot_be_written`, `tests/unit/test_governed_audit.py` |
| GOV1-2 | The governed writes are one register (`GOVERNED_WRITES` in `application/audit_service.py`); every action in it is recorded by code, and none is recorded through the best-effort helper | `tests/unit/test_governed_audit.py::test_every_governed_action_is_recorded_somewhere_in_the_code`, `::test_no_governed_action_is_recorded_through_the_best_effort_helper` |
| GOV1-3 | Reads, list events, sign-in events and refusals stay best-effort: a read answers even when its audit row cannot be written, and a fault in the change itself is reported as that fault, not as an audit failure | `test_a_read_still_answers_when_its_audit_row_cannot_be_written`, `test_a_fault_in_the_change_itself_is_not_reported_as_an_audit_failure` |
| GOV1-4 | AI controls stage 2 (AIR-3 to AIR-7): the AI-use register, a switch per use honoured wherever the use runs (explain, brief, answer, alert analysis, alert enrichment, analysis query, report editor and plan, spreads, research and MCP tools), provenance on AI audit rows, per-role model tool allowlists and an offline evaluation gate; organisation settings, which hold the switches, are a governed write | rows AIR-3 to AIR-7 above; `tests/api/test_governed_audit_api.py` |
| GOV1-5 | (P6) Each licensed source family a person is allowed to read is counted once per request in one row per day, person, family and route (`licensed_data_use`, migration `0079_licensed_data_use`), never one row per request; public families, refused rows and the firm's own data are not counted; a read answers even when its usage cannot be recorded; the licence register shows each licence's 30-day use | `tests/api/test_licensed_use_api.py::test_a_licensed_read_is_counted_once_per_day_and_route`, `::test_a_read_of_public_data_writes_no_usage`, `::test_a_read_answers_when_its_usage_cannot_be_recorded`, `::test_the_licence_register_shows_thirty_days_of_use`; `tests/unit/test_licensed_use.py` |
| GOV1-6 | (P6) A CSV, XLSX or PDF report applies `ExportDecision` to the licensed families its rows were read from: no licensed data, or a licence that allows redistribution, is allowed; a registered licensed family marks the file internal use only (headers, and the file's own description in XLSX and PDF); a family with no registered export terms refuses the file with 403 `export_denied`; the file is counted as an export | `tests/api/test_licensed_use_api.py::test_a_file_of_licensed_rows_is_marked_for_internal_use_and_counted_as_an_export`, `::test_a_licence_that_allows_redistribution_allows_the_file`, `::test_a_file_of_data_whose_export_terms_are_not_registered_is_refused`, `::test_a_file_without_licensed_data_is_allowed`; `tests/unit/test_licensed_use.py::test_file_export_decision` |

## P-17 maker-checker on limits and reference data (met)

Finding P-17 (and P-01's second half) in [13](13_PERSONA_AND_PRACTICE_REVIEW.md); decisions in
[08](08_DECISION_LOG.md) and ADR Decision 32. API tests in `tests/api/test_maker_checker_api.py`
unless named otherwise.

| # | Criterion | Test |
| --- | --- | --- |
| P17-1 | A change to a credit line, trader mandate, deal hedge band, the firm's marks, LNG terminal terms or a freight route is proposed (202, `pending_approval`) and changes nothing until a different authorised person approves it; an unchanged save answers 200 and proposes nothing; one open proposal per record (409 `change_pending`) | `test_a_limit_change_waits_for_a_second_person_and_keeps_its_provenance`, `tests/api/test_risk_segregation_api.py::test_a_credit_line_change_keeps_what_it_leaves_out_and_audits_the_diff`, `tests/api/test_assumptions_api.py::test_firm_marks_are_labelled_and_audited_without_values`, `tests/integration/test_lng_cargo_economics_api.py` |
| P17-2 | The proposer cannot approve their own change (403 `four_eyes_required`, saying how a one-person installation proceeds); limits, bands and marks are approved by the risk function only (a trader who also holds REVIEWER is refused); a mandate is never approved by the trader it governs; terminal terms and freight routes by another person on the desk | `test_a_limit_change_waits_for_a_second_person_and_keeps_its_provenance`, `test_a_mandate_is_never_approved_by_the_trader_it_governs`, `test_terminal_terms_are_approved_by_another_person_on_the_desk`, `tests/api/test_risk_segregation_api.py::test_a_trader_who_is_also_a_reviewer_cannot_set_limits` |
| P17-3 | A pending change shows who proposed it, what it changes (each field before and after), why and since when, to its proposer and to whoever may decide it, and to nobody else | `test_a_limit_change_waits_for_a_second_person_and_keeps_its_provenance` |
| P17-4 | Proposal, approval, rejection (a reason required) and withdrawal (the proposer only) are governed writes audited with `record_governed_audit` in the same transaction; the applied write is audited under the approver and names both people; when the audit row cannot be written nothing is stored and the proposal stays pending | `test_rejection_and_withdrawal_are_audited_and_change_nothing`, `tests/api/test_governed_audit_api.py::test_a_governed_write_fails_and_leaves_nothing_when_its_audit_row_cannot_be_written`, `tests/unit/test_maker_checker.py::test_the_money_and_risk_writes_need_two_people_by_default` |
| P17-5 | An approval is refused when the stored figures moved since the proposal (409 `change_stale`) | `test_a_proposal_is_refused_when_the_figures_moved_since` |
| P17-6 | An approved figure keeps who proposed it, who approved it, when and why (`provenance` on credit lines, credit exposure, mandate usage, hedge bands, terminal terms, firm marks and freight routes); a figure set by one person says so | `test_a_limit_change_waits_for_a_second_person_and_keeps_its_provenance`, `tests/integration/test_maker_checker_postgres.py::test_a_credit_line_is_proposed_approved_and_keeps_its_provenance` |
| P17-7 | Which writes need two people is an organisation setting per write (`four_eyes`), default on for all six; only an administrator changes it, the change is the audited `settings.organisation.update`, and a bad stored value never switches the control off | `test_four_eyes_is_set_per_write_by_an_administrator_and_the_switch_is_audited`, `tests/unit/test_maker_checker.py::test_a_bad_stored_setting_never_switches_the_control_off`, `::test_the_setting_names_listed_writes_with_true_or_false` |
| P17-8 | Migration `0081_change_requests` (expand only) adds `change_requests` and a nullable `change_id` on the six governed tables; it upgrades, downgrades and matches the models, on SQLite and PostgreSQL | `tests/unit/test_maker_checker.py::test_migration_0081_chain_up_down_and_model_match`, `tests/integration/test_schema_matches_models_postgres.py::test_every_model_column_fits_the_migrated_schema` |
| P17-9 | Web: approvers see the changes awaiting approval (who, what before and after, why, since) and approve, reject with a reason, or withdraw their own; the limits and hedge-band screens say "proposed, awaiting approval", mark rows with an open proposal and show who set and approved each figure; the marks grid says the marks wait for the risk function | `clients/web/tests/makerCheckerModel.test.ts`, `clients/web/tests/locales.test.ts` |

## DATA-1 data integration: as-of reads, change feed, refreshable reads, import contracts (met)
Lessons P1, P2 and P7 in [16](16_COMPETITIVE_STUDY.md); ETRM integration from 16A section 2b.
| # | Criterion | Test |
| --- | --- | --- |
| DATA1-1 | (P1) A settlement, close, FX fixing and the monthly price strip can be read "as known at T" (`as_of`, ISO UTC): each figure is the revision current at T with its revision number, publication time and the time this store first held it; a figure first held after T is not returned; a tick counts from its receipt; without `as_of` the reads are unchanged; entitlement applies as on every market read; an unusable or future `as_of` is refused with its code. The history is the outbox's revision chain, so no table was added | `tests/api/test_data1_as_of_reads.py::test_a_settlement_reads_as_known_before_and_after_its_correction`, `::test_an_fx_fixing_reads_as_known_at_an_instant`, `::test_the_price_strip_reads_the_curve_as_known_at_an_instant`, `::test_a_correction_not_yet_captured_is_reported_as_pending`, `::test_a_tick_is_known_from_its_receipt`, `::test_entitlement_still_applies_to_as_of_reads`, `::test_an_unusable_as_of_is_refused` |
| DATA1-2 | (P2) A client syncs only what changed: `GET /api/market/changes` answers the market events after its cursor, oldest first, read-only, as digests (key, type, subject, revision, `insert`/`update`, times, source, content hash) and never values; a page ends with the next cursor and `has_more`; `after=latest` starts from now; `kinds` and `subject` narrow it; each caller sees only the events it may read (licensed families by the market reads' rule and metering, desk events only with `portfolio.read` over every book), withheld events still move the cursor and are not counted to the caller; on PostgreSQL an event whose transaction drew an earlier `seq` and committed later is never skipped, and a rolled-back writer releases the feed; retention documented (nothing is pruned) | `tests/api/test_data1_change_feed.py::test_a_client_pages_through_every_change_in_order_and_then_waits`, `::test_after_latest_starts_from_now_and_picks_up_the_next_change`, `::test_kinds_and_subject_narrow_the_feed`, `::test_each_caller_sees_only_what_it_may_read`, `::test_a_bad_cursor_or_kind_is_refused`; `tests/integration/test_change_feed_postgres.py::test_an_event_committed_late_with_an_early_seq_is_not_skipped`, `::test_a_rolled_back_writer_releases_the_feed`, `::test_the_writer_id_is_stamped_by_the_database`; migration 0082 in `tests/unit/test_market_event_outbox_migration.py` |
| DATA1-3 | (P7) Excel's Power Query can refresh the price strip, settlements and FX with an API key header: `format=csv` answers flat rows under a fixed header (the same with no rows and with or without `as_of`), UTF-8 with a byte-order mark; `as_of` works in the file; a licensed family's file carries the GOV-1 export decision (restricted for internal use, 403 `export_denied` when the terms are unregistered) and is metered as an export, public data is allowed and writes no usage; JSON stays the default; a how-to with an M query is in `docs/sdk/POWER_QUERY.md` | `tests/api/test_data1_refreshable_reads.py::test_the_price_strip_refreshes_as_flat_csv_with_a_fixed_header`, `::test_a_licensed_file_is_metered_as_an_export`, `::test_a_file_of_licensed_data_whose_terms_are_unknown_is_refused`, `::test_observations_and_fx_keep_their_header_with_or_without_rows_or_as_of`, `::test_json_stays_the_default_and_an_unknown_format_is_refused` |
| DATA1-4 | ETRM and ERP files have versioned, documented contracts: deals, the physical schedule per gas day, nomination statuses, the LNG cargo schedule, ERP counterparties and invoice references, each with its columns, key and target (`GET /api/imports/contracts`, `docs/integration/ETRM_ERP_IMPORT_CONTRACTS.md`); every row is checked on its own and a refused row is reported with its line, reason code and message; by default one refused row refuses the file and nothing is stored, `skip_rows` stores the rest; a file carrying bank or tax identifiers, or missing a required column, is refused whole; re-importing the same file changes nothing and publishes nothing; a dry run and `POST /api/imports/{contract_id}/validate` store nothing; nothing is booked, nominated, posted or paid; the existing parsers are reused and no vendor-specific connector is written | `tests/api/test_data1_import_contracts.py::test_each_bad_row_is_refused_with_its_line_and_reason_and_the_file_stores_nothing`, `::test_skip_rows_stores_the_good_rows_and_a_re_import_changes_nothing`, `::test_a_dry_run_says_what_storing_would_do_and_stores_nothing`, `::test_physical_positions_land_in_the_gas_day_schedule`, `::test_nomination_statuses_are_recorded_once_and_nothing_is_nominated`, `::test_the_cargo_schedule_lands_in_the_cargo_plan_and_a_re_import_publishes_nothing`, `::test_erp_counterparties_and_invoices_are_kept_as_references`, `::test_a_file_with_bank_or_tax_columns_or_missing_columns_is_refused_whole`, `::test_the_api_lists_the_contracts_and_checks_a_file_without_storing_it`, `::test_the_operator_script_dry_runs_then_commits`; table `erp_references` in `tests/unit/test_market_event_outbox_migration.py` |

## MAP-1 the map: terminals and storage, carriers, flows, motion (met; frame rate not yet measured)
Real or labelled data only: a figure the platform does not hold is absent, never estimated, and
every drawn estimate says it is one. One payload, `GET /api/portfolio/map-situation`, gained
fields; no route was added.

| # | Criterion | Test |
| --- | --- | --- |
| MAP1-1 | LNG terminals and storage sites are drawn from published capacity: ENTSOG's newest firm technical capacity at the point for the current gas day (never a later or superseded one), per direction, in energy; in 3D a column whose height is that capacity (square-root scale, said to be not to scale) filled by the same direction's latest closed-day flow, in 2D a circle; a site with no published capacity is a stub and its card says so; every figure on the card names its source, gas day and age, and an old one is marked stale; GIE inventory is labelled as the country's total unless GIE publishes the site under the point's own EIC | `tests/unit/test_map1_assets.py::test_sites_carry_published_capacity_flow_and_inventory_with_their_source`; `clients/web/tests/mapScene.test.ts` "a terminal's column is its published send-out capacity…", "columns scale by square root, a site with no published capacity is a stub said so", "cards name each figure's source and age; an estimate and a country total say what they are" |
| MAP1-2 | LNG carriers show their reported track and position as reported; a laden cargo with no position, or a report older than six hours, also gets an estimated position interpolated on the great circle from the last fix (else the departure port) to the destination at the ETA, drawn hollow on a dashed leg and labelled an estimate with what it starts from; no estimate without departure and ETA, after the ETA, or when not laden; a voyage with no track is a dotted origin-to-destination arc labelled as not the vessel's route; every ETA says what it rests on and how confident (LNG-2 basis; a contract cargo reads its delivery window); `position_basis` is `reported` only when the feed reported the position; markers move by easing from where they were | `tests/unit/test_map1_assets.py::test_a_cargo_says_what_its_eta_rests_on_and_that_no_position_was_reported`; `clients/web/tests/mapScene.test.ts` "with no reported position a laden cargo is estimated half way at half time, never reported", "a fresh report is drawn as reported; an old one gets an estimate beside it", "no estimate without both times, after the ETA, or when not laden", "great circle points and prefixes are exact", "a moved vessel eases from where it was; a new one appears in place" |
| MAP1-3 | Gas flows are animated lines at their points, width by GWh/d; an entry flows into the side whose operators the hub link lists and an exit out of it (an interconnector belongs to its pipeline's operator); where no side lists the operator no direction is drawn and the key counts such flows; a day scrubber shows any stored closed gas day, ending at "latest" (each point's newest), and keeps the chosen day when the window moves | `tests/unit/test_map1_assets.py::test_the_stored_flow_window_is_every_closed_day_oldest_first`; `clients/web/tests/mapScene.test.ts` "an entry flows into the operator's side, an exit out of it", "no direction is claimed when the operator is on no listed side", "the scrubber shows a stored day; latest is each point's newest", "the gas-day scrubber ends at latest and survives a day leaving the window" |
| MAP1-4 | Entitlement: a caller sees only the cargoes, contracts and slots of its book scope, and only the capacity, flows and inventory its data scopes allow; a field missing from an older server or an empty scope draws nothing | `tests/api/test_map_situation_api.py::test_map1_layers_follow_the_book_scope_and_say_what_each_position_rests_on`; `tests/unit/test_map1_assets.py::test_a_site_figure_the_caller_may_not_read_is_left_out`; `clients/web/tests/mapScene.test.ts` "no assets in the payload (older server or no scope) draws nothing" |
| MAP1-5 | Motion: 2D and 3D switch by an eased camera in the map duration token (`--ds-duration-map`, `--ds-ease-out`); with reduced motion the camera jumps, flows are static dashes with a direction chevron and the key opens without animation; the flow animation stops on a hidden page; frame intervals are summarised (median, p95, share over 33 ms) on the map element for measurement | `clients/web/tests/mapScene.test.ts` "flows move only when motion is allowed; reduced motion and a hidden page are static", "frame behaviour is summarised as median and p95 interval". Frame rate in a browser is not measured yet ([09](09_VALIDATION_EVIDENCE.md)) |
| MAP1-6 | Design system and access: controls from `components/ui` (Segmented, Button), styles in `@layer ds-components` with `--ds-*` tokens only; the map's colours are the series tokens the key's swatches use, terminals and storage told apart by hue and by shape; every visible string in EN and ZH; the 2D/3D control, the labelled day scrubber (with its value as text) and a key whose sites and estimates are buttons that fly there all work from the keyboard | `clients/web/tests/mapScene.test.ts` "the scene's map colours are the series tokens the key's swatches use"; `clients/web/tests/designTokens.test.ts`, `clients/web/tests/locales.test.ts`, `clients/web/tests/localeDistinctness.test.ts`, `node scripts/cssTokenLint.mjs` |

## TAR-1 public tariffs and capacity windows: versioned, indicative or final, ingested on publication (met)
Decision 34 in [ADR](../../architecture/ARCHITECTURE_DECISION_RECORD.md); publisher registry in [TARIFF_PUBLISHER_REGISTRY](../../data/TARIFF_PUBLISHER_REGISTRY.md).
| # | Criterion | Test |
| --- | --- | --- |
| TAR1-1 | One tariff model with versions: each version names its publisher, point or terminal or facility, product, direction, unit and currency, period, status (`INDICATIVE` or `FINAL`), publication time, source URL, retrieval time and a content hash of what it says (not when it was read); a newer read supersedes the current version, an older read never does, an unchanged read adds nothing, a row that leaves the register is withdrawn and can return; the history is readable as of any instant. The registers (`tso_tariffs`, `lng_terminal_tariff`) are unchanged; the history is table `tariff_versions` (migration 0083, expand only) | `tests/domain/test_tariff_book_domain.py::test_the_content_hash_ignores_when_it_was_read_and_follows_what_it_says`, `::test_a_spec_refuses_what_is_not_a_published_tariff`, `::test_a_terminal_tariff_by_cargo_class_needs_no_single_value`, `::test_version_decisions_first_unchanged_revised_status_change_out_of_order`; `tests/unit/test_tariff_book.py::test_a_register_row_becomes_version_one_with_its_status_and_source`, `::test_an_older_read_never_supersedes_a_newer_one`, `::test_a_row_that_leaves_the_register_is_withdrawn_and_can_return`; `tests/unit/test_tariff_book_migration.py` |
| TAR1-2 | Indicative never silently becomes final: a change of status is its own named version (`INDICATIVE->FINAL`, or back) with its own event at higher priority; every version carries the basis of its status (`operator_stated` where the operator's row says final or indicative, else `period_started` or `period_not_started` as ENTSOG's ingestion sets it, `figures_disagree` held indicative, `reviewed` or `awaiting_review` for a terminal document); the valuation snapshot names the tariff version, its status basis and its source; the API and the web view label every row indicative or final | `tests/domain/test_tariff_book_domain.py::test_a_status_change_is_named_never_silent`; `tests/unit/test_tariff_book.py::test_indicative_to_final_is_a_named_status_change_and_history_stays_readable`, `::test_status_bases_from_the_register`, `::test_a_terminal_document_is_indicative_until_reviewed_then_final`, `::test_the_valuation_snapshot_names_the_version_it_priced`; `tests/api/test_tariffs_api.py::test_current_tariffs_are_labelled_and_a_restricted_terminal_is_left_out`; `clients/web/tests/tariffBookModel.test.ts` |
| TAR1-3 | Publishers: ENTSOG's transparency platform is read as structured data; every other TSO, LNG terminal and storage operator is in the registry with its page, cadence, format, `manual` or `parsed` and the state of its terms, and no value is fabricated for any of them; a publisher whose terms restrict reuse is recorded and left out; a terminal whose terms need the operator's permission is left out of the reads until that permission is recorded; the registry document and the code list the same publishers | `tests/domain/test_tariff_book_domain.py::test_the_registry_is_consistent_and_fabricates_nothing`, `::test_every_publisher_is_in_the_registry_document`; `tests/unit/test_tariff_book.py::test_a_terminal_whose_terms_need_permission_is_excluded_until_recorded`; `tests/api/test_tariffs_api.py::test_publishers_and_notices` |
| TAR1-4 | Freshness: ENTSOG is polled hourly in the NC TAR publication weeks and daily otherwise; a change is detected by its hash, written with its `tariff.changed` event in the read's own transaction (a rolled-back read leaves neither) and reaches the opportunity consumer; the scheduler's capture picks up an operator's register edit; measured on PostgreSQL 16 (median 12.5 ms read to version and event committed, 5.5 ms commit to the consumer, 8 runs; row in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 8); a publisher read later than its cadence raises `tariff_publisher_stale`, and an operator without next-period prices 30 days before the yearly auction raises `tariff_publication_missed` | `tests/domain/test_tariff_book_domain.py::test_entsog_is_polled_hourly_in_publication_weeks_and_daily_otherwise`; `tests/unit/test_tariff_book.py::test_a_revision_publishes_one_tariff_event_with_the_snapshot_keys`, `::test_the_entsog_read_records_versions_in_its_own_transaction`, `::test_a_publisher_read_late_raises_a_staleness_alert`, `::test_an_operator_without_next_period_prices_after_the_nc_tar_deadline`; `tests/integration/test_tariff_book_postgres.py::test_a_tariff_change_is_a_version_and_an_event_committed_together`, `::test_a_rolled_back_read_leaves_no_version_and_no_event` |
| TAR1-5 | Slot windows and auction notices: the CAM NC standard auctions (yearly, quarterly, monthly; rolling day-ahead and within-day are not listed) are derived by rule, kept idempotently and checked both ways against a recorded published calendar; an operator's notice file (slot windows, open seasons) is imported all or nothing with each refused line reported; a window opening within three days raises `capacity_window_opening`, routed to Operations with escalation to the Trader (monthly auctions excluded, they are routine) | `tests/domain/test_tariff_book_domain.py::test_mondays_and_the_brussels_opening_hour`, `::test_the_rule_matches_a_published_calendar_both_ways`, `::test_each_window_says_what_it_offers`; `tests/unit/test_tariff_book.py::test_standard_auctions_are_kept_rule_derived_and_idempotent`, `::test_an_imported_notice_file_is_all_or_nothing`, `::test_windows_opening_within_three_days_alert_scheduling_but_monthly_auctions_do_not` |
| TAR1-6 | Reads are additive and entitled: `GET /api/tariffs` (filters, `as_of`, `history` only with a scope), `GET /api/tariffs/publishers`, `GET /api/capacity/notices`; each caller sees only the publisher families it may read; an unusable `as_of` or an unscoped history is refused with its code; without a runtime store the reads answer empty, degraded and say why; the census, the public paths and the reachability gate list the three routes; the web view (Sources) shows the book with EN and ZH text | `tests/api/test_tariffs_api.py::test_as_of_and_history`, `::test_without_a_runtime_store_the_reads_degrade_and_say_so`; `tests/contract` (census, permissions, reachability); `clients/web/tests/tariffBookModel.test.ts`, `clients/web/tests/localeDistinctness.test.ts` |

## SCHED-1 nominations: why trades, confirmations and nominations disagree (met)
Decision support only (AGENTS.md rule 8): the reconciliation reads what the ETRM and the
scheduling import hold and explains each break; nothing is nominated, confirmed or sent. One
read, `GET /api/desk/gas-day/{gas_day}/reconciliation`; migration `0085_sched1_nomination_matching`
(nullable columns on `gas_day_nomination_events`, no table).

| # | Criterion | Test |
| --- | --- | --- |
| SCHED1-1 | Per gas day (06:00 to 06:00 CET), per hub (point where held) and counterparty (its shipper codes where held): the bilateral deals delivering on the day (traded), the counterparty's confirmation where imported, the quantity nominated and the quantity the TSO matched, each signed (+ into the firm) in the hub's desk unit with MWh and kWh/h; a figure not imported is "not held", never zero; exchange trades are counted per hub and said to be cleared by the exchange, not reconciled | `tests/domain/test_nomination_reconciliation.py::test_matched_trade_and_nomination_have_no_break`; `tests/integration/test_gas_day_reconciliation.py::test_r1_day_shows_the_lesser_rule_with_its_arithmetic`, `::test_a_quiet_day_has_no_break` |
| SCHED1-2 | Each break is one of eleven kinds and is explained in plain words, EN and ZH, with its arithmetic and the next step: trade not nominated, nomination without a trade, quantity mismatch (delta in MWh and kWh/h), counterparty mismatch (one break, not two; the same company written differently is not one), shipper-code mismatch (against the code the TSO matched), wrong direction, lesser-rule cut (with the counterparty's quantity where imported), late (a deal booked after the last nomination; a nomination after the deadline), unit slip (kWh/h, therms, MW read as MWh/d), gas-day misalignment (nominated on the next day; a deal booked in calendar days, 19 of 24 hours) and an open confirmation | `tests/domain/test_nomination_reconciliation.py` (15 tests, one per kind with hand-worked figures, e.g. `::test_quantity_mismatch_in_mwh_and_kwh_per_hour`: -4,800 − (-6,000) = +1,200 MWh, +50,000 kWh/h; `::test_lesser_rule_with_the_counterpartys_quantity`; `::test_unit_slip_kwh_per_hour_read_as_mwh_per_day`) |
| SCHED1-3 | Ordered by the time to the hub's next cut-off (due soon within 3 hours, red within the hour, "no renomination left" once the last renomination has passed) and then the MWh at risk; each break with an indicative cash-out at the book's approved cash-out assumption, said to be indicative and that no published imbalance price is read, or said to be missing | `tests/domain/test_nomination_reconciliation.py::test_urgency_buckets`; `tests/integration/test_gas_day_reconciliation.py::test_r1_day_shows_the_lesser_rule_with_its_arithmetic` (1,200 MWh long at 1.20 GBP/MWh: 1,440 GBP) |
| SCHED1-4 | The scheduling import (`etrm.nominations.v1`) carries the matching fields as optional columns (counterparty, direction, point, shipper codes, the counterparty's quantity), the confirmation as step `trade_confirmation` and a trade's line as `trade:<deal>`; a file without them keeps its event ids; a bad direction is refused with its line and reason | `tests/integration/test_gas_day_reconciliation.py::test_imported_matching_fields_explain_counterparty_and_code_breaks`, `::test_an_old_file_without_the_new_columns_keeps_its_event_ids`; `tests/unit/test_gas_day_nominations_migration.py::test_0085_adds_the_matching_columns_and_drops_only_them` |
| SCHED1-5 | A break due soon or past the last renomination raises one alert in the `nomination` category (Operations, escalating to the trader), deduplicated, held back for 30 minutes unless it worsens (more MWh at risk or a higher severity), and withdrawn, with a "Withdrawn" notice, when it is fixed or the day ends; the alert mirror and the monitoring scan leave these alone; an alert pass takes about 0.03 s on PostgreSQL | `tests/integration/test_gas_day_reconciliation.py::test_alerts_dedupe_cool_down_worsen_and_withdraw`, `::test_the_mirror_and_the_scan_leave_break_alerts_alone`; `tests/integration/test_gas_day_reconciliation_postgres.py::test_the_r1_break_is_read_alerted_and_withdrawn_on_postgresql` |
| SCHED1-6 | Entitlement as the other gas-day reads: a mandated trader sees their books only and asking for another's is refused (404 `book_not_in_scope`); `portfolio.read` is required (a platform administrator is refused, 403); filters by hub, counterparty, kind, book and breaks only; an unknown kind or a day more than 31 days away is refused (422); `format=csv` answers one row per break under a fixed header with the GOV-1 export decision | `tests/integration/test_gas_day_reconciliation.py::test_filters_and_refusals`; `tests/api/test_gas_day_reconciliation_api.py::test_json_csv_and_refusals` |
| SCHED1-7 | Today: the scheduler's Reconciliation row (today and tomorrow; grouped by hub and counterparty with break chips, a countdown, filters, CSV, each group's breaks opened from the keyboard) and, for every role, a break near its cut-off in What needs me with its explanation; components from `components/ui`, styles in `@layer ds-components` with `--ds-*` tokens, EN and ZH | `tests/integration/test_gas_day_reconciliation.py::test_today_lists_the_break_only_near_the_cut_off`; `clients/web/tests/reconciliationModel.test.ts`; `clients/web/tests/roleComposition.test.ts`; `node scripts/cssTokenLint.mjs` |
| SCHED1-8 | The demo plants one explainable break on known days (R1, the 11th and 12th of each month: Aldermoor nominates 4,800 of the 6,000 MWh sold at NBP and the TSO confirms the lesser) and nothing on any other day; the other planted cases are unchanged | `tests/integration/test_demo_planted_cases.py::test_the_r1_break_is_in_the_reconciliation_on_its_day_only`, `::test_each_planted_case_is_found_on_its_day_and_nothing_else[R1]` |

## NEWS-1 news, policy and geopolitical events in the analysis (met; feed addresses for three sources await the owner)
Public sources whose terms permit reuse, every claim cited and grounded, under GOV-1's AI
controls. Sources and terms: [`docs/integration/NEWS_SOURCE_REGISTRY.md`](../../integration/NEWS_SOURCE_REGISTRY.md).
Decision support only: nothing is traded, nominated or sent.

| # | Criterion | Test |
| --- | --- | --- |
| NEWS1-1 | A source registry records each source's publisher, feed, language, poll interval, licence, quoted terms with their address and the day they were read, and attribution; a source is polled only when its terms permit reuse in a commercial product, its feed address is `https` on the publisher's own host, no credentials are needed and robots.txt allows it; licensed, forbidden and unread sources are recorded with the reason and never polled; REMIT items are made from the messages the platform holds, so nothing is fetched for them | `tests/unit/test_news_sources_feeds_tagging.py::test_every_polled_source_records_its_terms_and_an_excluded_one_is_never_polled`; `::test_remit_is_made_from_held_messages_and_only_a_recorded_feed_is_polled`; `::test_a_feed_address_must_be_https_on_the_publishers_own_host`; `tests/unit/test_news_ingest.py::test_robots_and_terms_are_respected_before_any_feed_is_read`; `::test_robots_rules_for_this_product_and_the_real_fetcher_refuse_plain_http` |
| NEWS1-2 | Each item is stored with source, URL, publisher, published and retrieved times, content hash, language and licence note; a feed is read safely (no DOCTYPE or entity, bounded size, scripts and markup removed, unsafe links dropped); polling keeps each source's interval and asks conditionally (ETag, Last-Modified); the same entry is stored once, an edited entry is a new revision, and a failed or refused poll is recorded with why | `tests/unit/test_news_sources_feeds_tagging.py::test_a_document_with_a_doctype_or_entity_is_refused_before_parsing`; `::test_rss_feed_drops_scripts_converts_times_and_refuses_unsafe_links`; `tests/unit/test_news_ingest.py::test_a_feed_poll_stores_tagged_items_once_and_skips_within_the_interval`; `::test_an_unchanged_feed_is_not_modified_and_an_edited_entry_is_a_revision`; `::test_a_failed_or_unreadable_feed_is_recorded_and_stores_nothing`; `::test_the_operator_script_stores_only_with_commit` |
| NEWS1-3 | Tagging is deterministic and works with AI off: hubs (codes as written), countries, terminals, pipelines, TSOs, fields and the vessels the firm holds; event types outage, sanction, policy or regulation, weather, strike and geopolitical; capacity changes | `tests/unit/test_news_sources_feeds_tagging.py::test_assets_operators_hubs_and_event_types_are_tagged_without_a_model`; `::test_hub_codes_match_only_as_written_and_vessels_only_when_held`; `::test_unrelated_text_carries_no_tags_and_zones_map_to_hubs` |
| NEWS1-4 | An item that names the asset of a held, open REMIT outage is linked to it and publishes `news.published` with that outage's dependency key, so opportunities depending on it are re-evaluated; an operator alone does not link; REMIT items do not repeat M5's outage event | `tests/unit/test_news_ingest.py::test_a_feed_item_on_a_held_open_outage_links_to_it_and_wakes_opportunities`; `::test_held_remit_messages_become_items_linked_to_their_outage` |
| NEWS1-5 | What an item touches is computed against contracts (delivery hub), open cargoes (vessel or destination terminal) and recent nominations (hub), each with its reason and the platform's own figure, only in the books the caller may see and only for a caller who may read the portfolio; the list puts those items first | `tests/unit/test_news_relevance_routing_note.py::test_an_item_matches_contracts_nominations_and_cargoes_with_reasons`; `::test_matches_stay_inside_the_books_a_caller_may_see`; `tests/api/test_news_api.py::test_the_list_puts_my_books_items_first_and_filters`; `::test_matches_stay_inside_the_callers_books` |
| NEWS1-6 | A relevant item reaches the role whose work it changes (trader, LNG, scheduler) through M7 routing, book-scoped; a notification only for a recent outage, sanction, strike, geopolitical event or capacity change; the same content is never sent twice, a role is not told again within 30 minutes unless something new touches it, and a second report of the same held outage within 30 minutes is one message; aged alerts resolve | `tests/unit/test_news_relevance_routing_note.py::test_a_recent_outage_item_tells_each_role_once_then_holds_back`; `::test_a_second_report_of_the_same_outage_within_the_cooldown_is_one_message`; `::test_policy_or_old_items_raise_an_in_app_alert_only`; `::test_the_outbox_delivers_news_events_to_the_routing_consumer`; `::test_news_categories_are_routed_book_scoped_and_notify_themselves` |
| NEWS1-7 | "What this means for my book": a rule note always, each sentence citing its evidence lines (the item, related items, the held outage's figures, each exposure touched); the AI note is the GOV-1 use `news_note` (switchable, provider and caller capability, prompt version and model on the audit row, no tools) and is shown only when every sentence cites known lines and passes the desk checks against only the lines it cites (numbers, hubs, units, direction, names, sources, superlatives, advice, language), labelled "AI-generated"; otherwise the rule note stands and the reader is told why | `tests/unit/test_news_relevance_routing_note.py::test_the_rule_note_cites_the_item_the_outage_and_each_exposure`; `::test_a_grounded_model_note_is_used_and_labelled`; `::test_an_unsupported_model_note_is_refused_and_the_rule_note_stands`; `tests/api/test_news_api.py::test_the_ai_note_is_shown_labelled_only_when_grounded_and_is_audited` |
| NEWS1-8 | The grounding validator has a recorded evaluation set in the evaluation gate (36 cases: faithful notes pass; uncited, wrongly cited, invented figure, foreign hub, wrong unit, reversed direction, advice to trade, invented source or name, superlative, wrong shape or language are refused by the named check); the register entry records prompt version, fingerprint and the set's hash | `tests/evals/test_news_note_evals.py`; `tests/evals/test_ai_gate.py`; `tests/unit/test_ai_register.py` |
| NEWS1-9 | Additive reads `GET /api/news` (filters hub, country, type, source, since, mine; my book first), `GET /api/news/{item_id}` (source and terms, linked exposures, related items, cited note) and `POST /api/news/{item_id}/note` (governed); census 295 paths / 330 operations | `tests/api/test_news_api.py`; `tests/contract/test_openapi_surface_claim.py`; `tests/contract/test_surface_reachability.py` |
| NEWS1-10 | Web: a news and events panel on Desk → Today with hub, country and type filters and "my book" first; an item opens with its source link and terms, the exposures it touches and the note with inline citations, the AI note labelled; shared `components/ui`, styles in `@layer ds-components` with `--ds-*` tokens, every string in EN and ZH | `clients/web/tests/newsModel.test.ts` |
| NEWS1-11 | Storage: one expand-only migration `0084_news_items` (tables `news_items`, `news_source_polls`), up and down on SQLite and PostgreSQL; ADR Decision 35 | `tests/unit/test_news_items_migration.py`; `tests/integration/test_news_postgres.py` |

## LNG-3 a disruption re-optimises the portfolio (met)

The owner's scenario (2026-11-25), judged on Wednesday 20 January 2027 at 09:00 UTC. Every
price, offer and term in it is illustrative. Design: [17](17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md).

**Market.** The January contract stopped trading on 30 December, February trades until
28 January, and gas days up to 21 January are already nominated. Month prices (EUR/MWh):

| Hub | Jan | Feb |
| --- | --- | --- |
| ZTP | 30.00 | 29.00 |
| TTF | 30.40 | 29.40 |
| PEG | 30.20 | 29.40 |
| PVB | 31.00 | 30.00 |

**The book.** Three cargoes of 1,000,000 MWh each (laytime 36 h, demurrage 70,000 EUR/day,
boil-off 1,000 MWh/day), a spare slot, a pipeline and a delivery obligation:

| Cargo | Slot | Where it stands |
| --- | --- | --- |
| ZEE-1 | Zeebrugge (ZTP) from 26 Jan: 10 days, 100,000 MWh/d send-out, 1,000,000 MWh storage declining linearly, release value 0.10 EUR/MWh | Now due **28 Jan**, medium confidence |
| GATE-1 | Gate (TTF) from 28 Jan | Arrives 26 Jan |
| HUE-1 | Huelva (PVB) from 24 Jan: 20 days at 50,000 MWh/d | On time. Huelva is three sailing days closer than the others |

- **Spare slot:** Dunkerque (PEG) from 30 Jan.
- **Pipeline:** 30,000 MWh/d at ZTP, at 28 EUR/MWh.
- **Obligation:** Cepsa takes a firm 50,000 MWh/d at Huelva from 24 Jan to 12 Feb.

**Offers at Zeebrugge (indicative):**

| Offer | Price | Limit | Days |
| --- | --- | --- | --- |
| Borrow in tank | 0.10 EUR/MWh | up to 100,000 MWh/d | 26 to 27 Jan |
| Extra send-out | 0.15 EUR/MWh | 50,000 MWh/d | |
| Extra storage | 0.02 EUR/MWh | 300,000 MWh | |
| Interruptible send-out | 0.05 EUR/MWh | 100,000 MWh/d | |
| Interruptible storage | 0.01 EUR/MWh per day | | |

**Two days late (28 Jan).** EUR against the plan:

| Option | Expected | Worst | Cost | Spare send-out MWh | Other supplies moved MWh | Standing |
| --- | --- | --- | --- | --- | --- | --- |
| Borrow in tank | -20,000 | -158,000 | 20,000 | 1,000,000 | 0 | **Default** (score -89,000) |
| Swap with GATE-1 | +95,800 | -330,200 | -35,000 | 1,000,000 | 1,000,000 | Frontier, but moves a cargo that was running to plan |
| Buy send-out | -36,000 | -249,000 | 36,000 | 1,000,000 | 0 | Dominated by borrow |
| Divert to Dunkerque | -247,400 | -347,600 | 247,000 | 0 | 0 | Dominated by borrow |
| Wait and absorb | -279,000 | -417,000 | 79,000 | 800,000 | 0 | Dominated by borrow |
| Swap with HUE-1 | | | | | | **Infeasible**: "breaks the firm delivery to Cepsa at Huelva: 50,000 MWh short on 24 Jan" |

How the figures are made up:

- **Borrow.** 200,000 MWh borrowed for 26 and 27 Jan at 0.10 = 20,000. The planned send-out
  is kept, so there is nothing to re-hedge.
- **Wait and absorb.** 200,000 MWh moves from ZTP January (30.00) to February (29.00), which
  is -200,000. The re-hedge costs 200,000 x 0.25 (January has stopped trading) plus
  200,000 x 0.01 (February), which is -52,000. Capacity costs -27,000.
- **Divert to Dunkerque:**

  | Component | EUR |
  | --- | --- |
  | Physical moved | -40,000 |
  | Re-hedge | -212,000 |
  | Demurrage | -35,000 |
  | Boil-off | -60,400 |
  | Release of the Zeebrugge slot | +100,000 |
  | **Total** | **-247,400** |

- **Swap with GATE-1.** Saves GATE-1's half day of demurrage (+35,000) and its waiting
  boil-off (+60,800). It is penalised 0.5 EUR per MWh of a supply that was running to plan,
  and its downside is weighted 0.5.

**Four days late (30 Jan).** The default flips to **borrow in tank and buy extra send-out**:

| Component | EUR |
| --- | --- |
| Physical moved | -100,000 |
| Re-hedge | -26,000 |
| Capacity fees | -56,000 |
| **Expected** | **-182,000** |

Its worst case is -395,000 and its score -288,500. The frontier is {borrow and buy, divert}.
Divert is -152,000 expected and -508,000 worst, with a score of -330,000. Borrow alone falls
to -295,000. The swap with GATE-1 becomes infeasible, because the tank would hold 200,000 MWh
over the storage right at Gate.

Through the outbox, the trader, the scheduler and the desk head are told once when the default
flips. Running again on the same inputs tells no one.

| ID | Criterion | Evidence |
| --- | --- | --- |
| LNG3-1 | The model holds the slot product (days, send-out, storage and its profile, release value), capacity offers, delivery obligations, voyage terms and pipeline supplies. It is one expand-only migration (`0086_lng_disruption`, ADR Decision 36), and the schema head pins moved with it | `tests/unit/test_lng_disruption_migration.py::test_up_down_and_model_match`; `tests/integration/test_schema_matches_models_postgres.py`; `DB_SCHEMA_REVISION` and the 10 pinned head literals |
| LNG3-2 | Each option (wait, borrow, buy, borrow and buy, divert, swap; for a pipeline, absorb or cover from a cargo) is valued against the plan across the whole book, under ETA and price scenarios, and the frontier matches the hand-worked numbers | `tests/domain/test_lng_disruption.py::test_two_day_delay_values_each_option_against_the_plan`, `::test_wait_and_absorb_breaks_down_as_worked_by_hand`, `::test_borrow_keeps_the_planned_send_out_and_returns_the_gas_after_berthing`, `::test_divert_arithmetic_releases_the_slot_and_re_hedges`, `::test_frontier_and_recommendation_for_a_two_day_delay`, `::test_pipeline_curtailment_absorbed_or_covered_from_a_cargo`, `::test_nominated_days_settle_at_cash_out`; through the store on SQLite and PostgreSQL: `tests/integration/test_lng_disruption_postgres.py::test_the_owner_scenario_is_valued_from_the_store_and_chosen` |
| LNG3-3 | Hard constraints are never traded off: the Spanish firm obligation makes the Huelva swap infeasible, with its reason. A diversion the contract forbids is infeasible. Energy that cannot be stored is stranded and infeasible. A soft obligation costs its penalty instead | `tests/domain/test_lng_disruption.py::test_swap_that_breaks_the_spanish_obligation_is_infeasible`, `::test_divert_is_infeasible_when_the_contract_forbids_it`, `::test_late_divert_strands_what_the_slot_cannot_hold`, `::test_a_soft_obligation_costs_its_penalty_instead`; `tests/api/test_lng_disruption_api.py::test_a_late_cargo_gets_valued_options_a_frontier_and_a_default` |
| LNG3-4 | Moving a cargo that was running to plan is counted (`disrupted_mwh`) and penalised in the default. Dominated options name what beats them and where. The default is configurable, deterministic and documented, with complexity limits | `tests/domain/test_lng_disruption.py::test_swap_with_the_normal_cargo_is_penalised_for_disturbing_it`, `::test_preference_weights_change_the_default_not_the_frontier`, `::test_same_inputs_same_answer`; [17](17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md) sections 3 and 4 |
| LNG3-5 | A later ETA flips the recommendation. The consumer re-optimises on input events and keeps a timeline. The trader, scheduler and desk head are told only on a material change, once, with dedupe and cooldown. Latency is within the cargo budget | `tests/domain/test_lng_disruption.py::test_a_later_eta_flips_the_recommendation`; `tests/integration/test_lng_disruption_postgres.py::test_a_later_eta_flips_the_default_and_the_roles_are_told_once` (SQLite and PostgreSQL); `tests/api/test_lng_disruption_api.py::test_the_consumer_keeps_a_timeline_and_notifies_once_per_change`; [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) sections 2 and 8 |
| LNG3-6 | Three reads and a choose action. The choice is governed and audited, an infeasible option is refused, and nothing is booked. The census, reachability and contract policy are updated | `tests/api/test_lng_disruption_api.py::test_choosing_records_the_decision_audited_and_books_nothing`, `::test_frontier_reads_the_book_and_a_pipeline_what_if`, `::test_a_cargo_running_normally_is_as_planned`; `tests/contract` (census 296 paths and 331 operations, surface reachability) |
| LNG3-7 | The web Options panel on the cargo plan has a Choose action, built from `components/ui` with tokens in `@layer ds-components`, in EN and ZH | `clients/web/tests/disruptionOptionsModel.test.ts`; `clients/web/tests/designTokens.test.ts`, `cssTokenLint.test.ts`, `locales.test.ts`; `npx tsc --noEmit -p .` |
| LNG3-8 | The demo plants the case: on the 24th of each month the demo LNG book holds a late cargo with options, and on other days it does not. The other planted cases are unchanged | `tests/integration/test_demo_planted_cases.py::test_d1_plants_a_late_cargo_whose_options_the_desk_can_read`, `::test_the_d1_day_lists_nothing_more_than_every_day`, `::test_each_planted_case_is_found_on_its_day_and_nothing_else` |

## CODEX-1 the Codex assessments reviewed; the valid, contained ones built (met)

Verdicts and what is left for the owner: [18](18_CODEX_ASSESSMENT_REVIEW.md). Nothing is
traded, nominated, booked or sent; no route, migration, service or dependency is added.

| # | Criterion | Test |
| --- | --- | --- |
| CODEX1-1 | Every capability result, refusals included, names the capability, its version, the principal, the agent run, an argument hash, the completion time and the duration; a success carries a reproducible output hash | `tests/unit/test_codex1_runtime_controls.py::test_a_refusal_is_traced_like_a_run`; `::test_a_success_carries_a_reproducible_output_hash`; `tests/api/test_capability_invocation_api.py::test_the_deployment_token_cannot_confirm` |
| CODEX1-2 | A success whose data breaks its declared output schema, or a handler that returns no result envelope, is refused with `INTERNAL_ERROR`; a call that overruns its declared `timeout_policy` is reported `TIMEOUT_OVERRUN`; a result states `NOT_ASSESSED` quality unless its handler checked its evidence | `tests/unit/test_codex1_runtime_controls.py::test_a_result_that_breaks_its_declared_shape_is_refused`; `::test_a_handler_that_returns_no_result_envelope_is_refused`; `::test_an_overrun_of_the_declared_timeout_is_reported`; `::test_a_result_states_no_quality_it_did_not_check` |
| CODEX1-3 | A `HUMAN_CONFIRMATION` capability runs only on a signed-in person's own confirmation: refused for a model acting for an AI use, for the deployment token and for a service account, with `HUMAN_CONFIRMATION_REQUIRED` and the reason | `tests/unit/test_codex1_runtime_controls.py::test_only_a_persons_own_confirmation_counts`; `tests/api/test_capability_invocation_api.py::test_the_callers_confirmation_reaches_the_runtime`; `::test_the_deployment_token_cannot_confirm`; `tests/api/test_agents_api.py::test_human_confirmation_gate_via_api` |
| CODEX1-4 | A confirmation, a refused confirmation and every call of a writing capability are audited (`governance.agent_capability`) with the qualified capability id and the argument and output hashes, never the arguments or the output; a read is not audited; a missing audit store never changes the result | `tests/unit/test_codex1_runtime_controls.py::test_a_persons_confirmation_runs_and_is_audited_with_the_version`; `::test_a_read_is_not_audited_and_a_write_is`; `::test_a_missing_audit_store_never_changes_the_result` |
| CODEX1-5 | The agents route refuses (401) a request with no identity instead of inventing an analyst with every data scope; the AI gate holds three new cases (a model never confirms, a service principal never confirms, an answer states no quality it did not check) and every human-gated capability on the never-model list | `tests/api/test_capability_invocation_api.py::test_a_request_without_an_identity_is_refused_not_given_an_analyst`; `tests/evals/test_agent_evals.py` (AGENT-EVAL-031 to 033, `::test_every_human_gated_capability_is_closed_to_models`); `tests/evals/test_ai_gate.py` |
| CODEX1-6 | `MarketChangeV1` is the versioned wire form of a change-feed digest: the feed's columns without its cursor, `kind` and `schema_version` in the value, `event_key` as the partition key across revisions; another version, kind or event type, an extra field or a naive time is refused; no broker dependency | `tests/streaming/test_market_change_contract.py`; `tests/streaming/test_streaming_contracts.py` |

## M7 to M9 (to be met)

- **M8.** For a contract with ACQ and make-up terms, the shortfall and make-up balance
  match a hand-worked example to the cent, and a nomination change publishes an event.
- **M9.** A recommendation can be followed to the decision taken and, where the client
  records a trade reference, to realised value; one P&L definition serves all views.
