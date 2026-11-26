# Commercial Intelligence V3: executive summary

Programme branch `innovation/continuous-commercial-intelligence`, cut from `main` at
`6d21b898661d6466418b3aaeab505a7bc4fb4013` on 2026-11-24. Nothing here changes `main`, a
release tag or a release package. Current position: [10_PROGRAMME_STATE.md](10_PROGRAMME_STATE.md).

## What the programme is for

Eurogas Nexus is a gas trading decision-support workstation. The programme turns it into a
platform that keeps a commercial view of the market current on its own: it notices a market
change, works out which positions, contracts and opportunities the change touches,
recalculates only those, and tells the right person, with the evidence. It stays decision
support (ADR Decision 11): outputs are proposals and handoff packages, never orders,
nominations or settlements. Kraken is a benchmark for what "continuously operating" means,
not a product to copy.

## What the audit found

The base is stronger than the brief assumes in analytics and governance, and weaker in the
one thing a continuous platform needs first: a way for a market change to travel.

1. **Events (the gap that blocks the rest).** A change reached the opportunity engine only
   as a class-level flag (`opportunity_pending_inputs`, CP-13) that triggers a debounced full
   evaluation. There was no event identity, no revision chain, no replay, no per-dependency
   fan-out and no outbox. `affected_by` and the `outbox` trigger existed in code and were
   never called. Prices and FX are overwritten in place.
2. **Two opportunity engines.** The new, well-tested engine (`domain/opportunities`) raises
   no alert; the legacy `intraday_opportunities` still feeds the stream and alerts.
3. **Resilience.** Health, readiness, retries and circuit breakers are good. There is no
   stale-source alerting, backups are manual without point-in-time recovery, and
   `data_quality` is a shell. Five freshness implementations disagree at the edges.
4. **Contracts and optimisation.** Contract kinds, price terms, revisions and LNG economics
   exist; take-or-pay (ACQ, make-up, carry-forward) does not. Optimisers are in-house
   pure-Python solvers; the joint optimiser is experimental and there is no hedge optimiser.
5. **Value attribution.** The backtest engine is good. Nothing links a recommendation to a
   trade to its realised value, and at least five P&L engines exist.

Full classification: [02_CAPABILITY_GAP_MATRIX.md](02_CAPABILITY_GAP_MATRIX.md).

## What was built first, and why

Milestone M4, workstream A: a **PostgreSQL transactional outbox for canonical market
events** with targeted re-evaluation. It was chosen because every later capability
(alerting on staleness, realised value, event-driven decisions, the digital twin) needs a
change to have an identity, a history and a route; it needs no credential (the ENTSO-E,
Oracle Cloud and Aiven access is not set up); and the design already had the hooks.

It gives each change an identity, five timestamps, revisions, idempotent publication,
priority, retries with backoff, dead letters, replay, staleness and a per-event timeline,
and the first consumer re-evaluates only the evaluators whose opportunities depend on the
change. Firm marks and every successful ingestion run now publish events. ADR
[Decision 28](../../architecture/ARCHITECTURE_DECISION_RECORD.md) records the choice of
the outbox over a broker. Evidence: [09_VALIDATION_EVIDENCE.md](09_VALIDATION_EVIDENCE.md).

## What comes next

M5, M5b, M6 and LNG-1 are built. Settlements, FX fixings, REMIT messages and desk edits
publish events, so a change re-runs only the results that use it; stale feeds, dead letters
and lag raise alerts; and an LNG cargo in transit is followed as one plan from its ETA to
the hedge months, so a schedule change says which months gained or lost gas and what to
roll ([12](12_LNG_CARGO_IN_TRANSIT.md)).

On 2026-11-24 the user asked for a written commercial standard and hands-on testing per
role. [11](11_COMMERCIAL_QUALITY_STANDARD.md) is that standard;
[13](13_PERSONA_AND_PRACTICE_REVIEW.md) holds the review findings against it. The same day the user asked where AI
should and should not take part in each role's work, how people shape their own workspace, and
how feedback becomes a reviewed change: [14](14_AI_ROLES_PERSONALISATION_AND_IMPROVEMENT_LOOP.md).
[16](16_COMPETITIVE_STUDY.md) compares the platform with market data vendors, ETRMs, LNG
shipping tools and Kraken, and with best practice in client design, and records what we
take from each and when.
On 2026-11-25 the user asked for the portfolio to be re-optimised when a cargo or a
pipeline supply is disrupted: [17](17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md) is the design
(LNG-3), with its sources, the worked example and its limits. The engine proposes and values;
a person chooses; nothing is booked.
The same day the user asked for a review of Codex's assessments on agents and on data storage
and processing: [18](18_CODEX_ASSESSMENT_REVIEW.md) gives each proposal a verdict, records what
was built (CODEX-1: capability runtime controls, a versioned change envelope) and lists what
waits for the owner (a broker, new datastores, live model routing).

1. Review every surface against the standard in a real browser, per role (Q1).
2. Fix the control and data blockers the review found (F1).
3. Desk polish, SDK documentation, public tariffs, news and the map.
4. Route the new engine's opportunities to alerts and the page (M7, built): a price change
   reaches the Opportunities page in about 7 s instead of 30 s and a reload; each alert names
   its owner and escalation. Budgets per data class and the case against a separate streaming
   platform are in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md). Retiring the legacy engine
   waits on its dependents (R19).

Roadmap: [05_IMPLEMENTATION_ROADMAP.md](05_IMPLEMENTATION_ROADMAP.md).
