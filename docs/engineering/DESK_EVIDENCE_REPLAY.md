# Desk evidence replay

Review proposal for issues #48, #49 and #50. The first slice replays one book,
hub and gas day from normalized, authorized evidence. Run it locally with
`python -m scripts.ops.replay_desk_evidence --input desk.json`.

Set `book_id`, `hub_id`, `gas_day`, `as_of` and the reporting `currency`.
Each row carries a stable `record_id`, numeric `revision`, `available_at`,
`source_ref` and the resource ID it belongs to. The caller maps and authorizes
the evidence before submitting it.

- `positions` contains one AVAILABLE row per resource and the confirmed
  COMMITMENT rows. Provide an evidenced zero when commitments are known to be
  absent. Use null for an unknown quantity. A quantity is total MWh for the day.
- `outages` contains UTC-aware start and end timestamps and unavailable MW.
  Supply is the baseline before the supplied outages. The calculation clips
  each interval to the gas day and rejects overlapping losses on one resource
  pending reconciliation.
- `alternatives` contains independently evaluated options with quantity,
  incremental unit cost, quote expiry, operational deadline and confirmed
  rights. Prices and credit use the declared currency. Optional credit per MWh
  is a caller-supplied linear assumption. The calculation caps each alternative
  at the remaining gap.

Save the output's `frozen_inputs` as a standalone input to replay the same
version. The output also includes the input fingerprint, delivery interval,
prior and revised gaps and blocked-response reasons. The prior gap uses the
declared pre-outage supply. The executable test in
`tests/unit/test_desk_replay.py` includes a 23-hour gas day and a later outage
revision.

Production integration requires scoped ETRM, TSO and quote adapters. The
prototype evaluates alternatives independently and uses caller-evidenced
capacity, pricing and costs. Comparing portfolios, writing a Decision Case,
valuing imbalance cash-out and desk validation against historical P&L are
follow-up work.
