# 07 Risk and dependency register

| # | Risk or dependency | Likelihood | Impact | Mitigation | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | No access yet to ENTSO-E (token), Oracle Cloud, Aiven | Certain | Blocks M12 and live ENTSO-E data | Build on public sources and fixtures; M12 waits | User | Open |
| R2 | Outbox growth: `market_events` keeps every revision | Medium | Storage and query time over months | Indexes on subject and source; add a retention job alongside `application/retention.py` before production (M6) | Programme | Open |
| R3 | Two event paths (outbox and CP-13 class flags) disagree during transition | Medium | A change triggers both a targeted and a full evaluation | Acceptable: evaluation is idempotent and merges only its evaluators' records; CP-13 retires producer by producer in M5 | Programme | Accepted |
| R4 | `run_due` lost-change race and per-process debounce (pre-existing) | Medium | A change can be missed until the next change in its class | Outbox deliveries are rows with status, so no change is lost on the new path; fix or retire `run_due` in M5 | Programme | Open |
| R5 | LISTEN connection drops silently | Low | Slower reaction only | Polling is authoritative; `listen` drains on interval too | Programme | Mitigated |
| R6 | A consumer is slow or poisoned | Medium | Backlog behind it | Per-consumer rows, priority order, backoff, dead letter after 5, `status` shows oldest lag; alerting in M6 | Programme | Partly mitigated |
| R7 | Desk-private data leaking into events | Low | Confidential marks visible in logs or replays | Firm marks publish a digest only; payload rules reviewed per producer | Programme | Mitigated for M4 |
| R8 | Licence of new dependencies (rule 18) | Low | Cannot ship | M4 adds none; NumPy (M11) and any LP backend need review and an ADR | Programme | Open |
| R9 | Migration conflict with unpushed branches (`today-gas-day` uses 0076) | Medium | Two heads at merge time | 0077 chains from 0076 on `main`; whoever merges second renumbers | User at merge | Open |
| R10 | Shallow clone hides history | Low | Ancestry evidence limited to the baseline commit | Baseline SHA and remote refs recorded in 01 | Programme | Accepted |
| R11 | Legacy and new opportunity engines both alerting during M7 | Medium | Duplicate alerts | Switch alerts and stream in one change; remove legacy in the same milestone | Programme | Open |
