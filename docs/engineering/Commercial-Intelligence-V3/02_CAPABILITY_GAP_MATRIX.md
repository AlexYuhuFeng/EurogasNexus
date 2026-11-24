# 02 Capability gap matrix

Classification uses the programme's scale: fully implemented and validated, partially
integrated, insufficiently tested, experimental, deferred, connector shell, planned,
obsolete. A capability can hold parts in several classes; the main class comes first.
Evidence for each line is in [01_CURRENT_STATE_AUDIT.md](01_CURRENT_STATE_AUDIT.md);
acceptance criteria are in [06_ACCEPTANCE_CRITERIA.md](06_ACCEPTANCE_CRITERIA.md).

Priority: P0 blocks other capabilities, P1 high commercial value and unblocked, P2 valuable
once a P0/P1 lands, P3 later. Complexity: S (days), M (one to two weeks), L (several weeks).

| # | Capability | Classification (at baseline) | Commercial significance | Highest-value improvement | Depends on | Security / licensing | Complexity | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Continuous market intelligence | Partially integrated (ingestion validated; change propagation class-level only) | A desk sees a correction or an outage minutes, not hours, after it is published | Canonical events and outbox (**M4, built**); then price/FX revisions as events (M5) | PostgreSQL only | Public sources only; no credentials used | M | **P0** |
| 2 | Ontology | Fully implemented and validated (executable core); research and OWL copies partially integrated | Consistent identities let a change find every position it touches | Make the executable ontology the one authority; add counterparty | M5 dependency keys | None | M | P2 |
| 3 | Digital twin | Partially integrated (schematic network, balances); connector shells for licensed feeds | Explains why a flow or spread moves | Feed outage-net capacity into the optimisers; event-driven rebalance | M4, M5 | Licensed feeds need contracts | L | P2 |
| 4 | Probabilistic forecasting | Insufficiently tested in shipped form (NumPy missing from runtime lock); interval only on one model | Ranges, not points, drive hedge sizing | Ship NumPy in the runtime lock with an ADR; quantile output and CRPS | Dependency review (rule 18) | NumPy is BSD-3 (commercially usable) | M | P2 |
| 5 | Contract modelling | Fully implemented and validated for kinds, price terms, revisions; take-or-pay planned | Take-or-pay exposure is a large, under-watched liability | ACQ, make-up and carry-forward obligations (M8) | Contract revisions (exists) | None | M | P1 |
| 6 | Portfolio and asset optimisation | Experimental (joint optimiser); validated route and storage kernels | Better storage and routing decisions are direct margin | One flow kernel; bounded storage DP; hedge optimiser later | M5 for event triggers | An LP backend (HiGHS, MIT) would need an ADR | L | P3 |
| 7 | Event-driven decisions | Partially integrated (two engines; new one raises no alert) | The desk acts on what the platform finds | Targeted re-evaluation (**M4, built**); route new-engine opportunities to alerts and retire the legacy engine (M7) | M4 | None | M | **P1** |
| 8 | Interoperability | Fully implemented and validated (SDK, CLI); federation contract shell; licensed connectors are shells | Clients plug the platform into their ETRM and BI | Commit the OpenAPI document; more handoff tests | None | Vendor licences for Trayport, ICE, Platts, Argus, Kpler | S-M | P2 |
| 9 | Governed AI | Fully implemented and validated (grounded narrative, audit, RBAC); agent runtime deferred; MCP experimental | Trustworthy explanations of each proposal | Token metering; MCP with user identity before any production use | None | Provider terms; no client data to providers without consent | M | P3 |
| 10 | Resilience | Partially integrated (health, retries, circuits validated); no staleness alerting; data quality shell | A silent stale feed is the costliest failure on a desk | Staleness and dead-letter alerts from the outbox (M6); one freshness rule | M4 | None | S-M | **P1** |
| 11 | Deployment | Fully implemented and validated for single-tenant Docker and OIDC; multi-tenancy planned; infra placeholders | Hosted pilots (Oracle Cloud, Aiven) | Hosting runbook once access exists; portfolio isolation on by default | Access to Oracle Cloud and Aiven (not set up) | Cloud credentials are the user's to provide | M | P2 (blocked) |
| 12 | Value attribution | Partially integrated (backtest validated); realised value planned | Proves the platform pays for itself | Outcome ledger: recommendation, decision, trade reference, realised value (M9) | M4 events, M7 | Trade data stays in the client's installation | M | P1 |

## Obsolete or to retire

- Legacy `scan_and_persist_intraday_opportunities` path once M7 routes the new engine to
  alerts and the stream.
- Duplicated LNG economics and min-cost-flow kernels, consolidated as each is next touched.
- The class-level `run_due` read-then-delete, once every producer publishes events and the
  full evaluation reads the outbox (M5).
