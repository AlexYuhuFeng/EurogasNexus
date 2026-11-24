# 07 Risk and dependency register

| # | Risk or dependency | Likelihood | Impact | Mitigation | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | No access yet to ENTSO-E (token), Oracle Cloud, Aiven | Certain | Blocks M12 and live ENTSO-E data | Build on public sources and fixtures; M12 waits | User | Open |
| R2 | Outbox growth: `market_events` keeps every revision | Medium | Storage and query time over months | Indexes on subject and source; add a retention job alongside `application/retention.py` before production (M6) | Programme | Open |
| R3 | Two event paths (outbox and CP-13 class flags) disagree during transition | Medium | A change triggers both a targeted and a full evaluation | Acceptable: evaluation is idempotent and merges only its evaluators' records; CP-13 retires producer by producer in M5 | Programme | Accepted |
| R4 | `run_due` lost-change race and per-process debounce (pre-existing) | Medium | A change can be missed until the next change in its class | Fixed in M5: `run_due` deletes by condition in the store, tested on SQLite and PostgreSQL. The per-process debounce across replicas remains | Programme | Mitigated |
| R5 | LISTEN connection drops silently | Low | Slower reaction only | Polling is authoritative; `listen` drains on interval too | Programme | Mitigated |
| R6 | A consumer is slow or poisoned | Medium | Backlog behind it | Per-consumer rows, priority order, backoff, dead letter after 5, `status` shows oldest lag; alerting in M6 | Programme | Partly mitigated |
| R7 | Desk-private data leaking into events | Low | Confidential marks visible in logs or replays | Firm marks publish a digest only; payload rules reviewed per producer | Programme | Mitigated for M4 |
| R8 | Licence of new dependencies (rule 18) | Low | Cannot ship | M4 adds none; NumPy (M11) and any LP backend need review and an ADR | Programme | Open |
| R9 | Migration conflict with unpushed branches (`today-gas-day` uses 0076) | Medium | Two heads at merge time | 0077 chains from 0076 on `main`; whoever merges second renumbers | User at merge | Open |
| R10 | Shallow clone hides history | Low | Ancestry evidence limited to the baseline commit | Baseline SHA and remote refs recorded in 01 | Programme | Accepted |
| R11 | Legacy and new opportunity engines both alerting during M7 | Medium | Duplicate alerts | Switch alerts and stream in one change; remove legacy in the same milestone | Programme | Open |
| R12 | Capture reads a 4-day window each scheduler cycle | Medium | One extra read per cycle; cost grows with settlement volume | One query per 500 event keys for held content; only changed figures write. Add a watermark if the read becomes measurable | Programme | Accepted |
| R13 | A correction older than the capture window | Low | Not published automatically | `scripts/ops/market_events.py capture --since ... --commit` publishes it; the CP-13 full evaluation still runs | Programme | Accepted |
| R14 | Live quotes (`market_quotes`) are not captured | Medium | A quote-driven opportunity waits for the CP-13 full evaluation | Deliberate in M5 (volume); revisit in M5b | Programme | Open |
