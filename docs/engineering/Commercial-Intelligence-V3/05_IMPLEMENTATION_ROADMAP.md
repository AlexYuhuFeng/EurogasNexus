# 05 Implementation roadmap

Vertical slices, each shippable and tested on its own, in priority order. M1 to M3 are the
Phase 0 work (baseline, audit, these documents). Status is kept in
[10_PROGRAMME_STATE.md](10_PROGRAMME_STATE.md).

| Milestone | Slice | Capabilities | Needs access? | Status |
| --- | --- | --- | --- | --- |
| M1 | Baseline: branch, SHA, ancestry, test results | all | No | Done |
| M2 | Capability audit and gap matrix | all | No | Done |
| M3 | Target architecture, domain design, criteria, risks, decisions | all | No | Done |
| M4 | Canonical market events, PostgreSQL outbox, targeted re-evaluation, replay, staleness, timeline | 1, 7, 10 | No | **Built, tested** |
| M5 | Settlements, FX fixings and REMIT messages publish events through change capture (scheduler window, importers in their own transaction); FX reaches cross pairs; the CP-13 lost-change race fixed | 1, 2, 7 | No (public sources and fixtures) | **Built, tested** |
| M5b | Contract and assumption-set edits publish `contract.changed` / `assumption.changed` next to their `note_input_changed` calls; capture over live quotes if their volume allows | 1, 7 | No | Next |
| M6 | Staleness and dead-letter alerting: monitoring reads `staleness()` and `status()` and raises alerts through the existing notification outbox; one freshness rule replaces the five | 10 | No | Planned |
| M7 | New-engine opportunities to alerts and `/api/stream/opportunities`; retire the legacy intraday engine; notification row lock | 7 | No | Planned |
| M8 | Take-or-pay: ACQ, make-up, carry-forward and shortfall exposure on contracts, with events on change | 5 | No | Planned |
| M9 | Outcome ledger: recommendation -> decision -> trade reference -> realised value; one P&L definition | 12 | No (client trade data stays in the installation) | Planned, ADR first |
| M10 | Ontology consolidation; counterparty concept | 2 | No | Planned |
| M11 | Forecast ranges: NumPy in the runtime lock (ADR, licence review), quantile output, CRPS | 4 | No | Planned |
| M12 | Hosted pilot on Oracle Cloud with Aiven PostgreSQL; ENTSO-E with a token | 11, 1 | **Yes** (ENTSO-E token, Oracle Cloud, Aiven) | Blocked on access |
| M13 | Optimiser consolidation: one flow kernel, bounded storage DP, outage-net capacity, hedge optimiser | 3, 6 | No | Later |

## Order and reasoning

M5 follows M4 because the outbox only pays off when the most frequent and most valuable
changes (settlement corrections, FX, outages) travel through it. M6 and M7 then turn what
the platform notices into something a person sees. M8 and M9 add the commercial depth that
proves value. M12 waits on access the user has to arrange.

## Working rules for every slice

- One branch: `innovation/continuous-commercial-intelligence`. Atomic commits naming the
  milestone (`M5: ...`). No merge to `main`, no tag, no release package.
- Expand-only migrations, `DB_SCHEMA_REVISION` and the pinned test literals bumped together.
- `scripts/ci/pre_push_check.sh` before every push; PostgreSQL tests on a real server.
- Update 09 and 10 in the same commit as the code they describe.
