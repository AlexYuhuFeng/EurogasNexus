# Trader UAT Script

Use this script with real professional users. It asks business questions, not
"click here" steps. Use the approved UAT fixture pack, never live licensed
data.

## UAT-A: Market investigation

Business question: European gas spreads have moved and you need a quick view
of hub state, the NBP/TTF spread, and whether an existing resource has a
market.

Starting context: Market, current gas day, day-ahead product, all hubs.

Task: determine the strongest hub move, inspect NBP vs TTF spread, look at the
network/capacity context for the relevant corridor, and carry the most
interesting route into Scenario.

Expected observable outcome: hub board shows bid/ask/mid, spread to TTF,
source and freshness; route candidates show source/assumptions; the Scenario
screen retains the carried route and explains why the route is or is not
economically attractive.

Feedback questions: What did you conclude? What was missing or ambiguous? Did
the source/freshness evidence change your trust? How many steps did the
handoff take?

## UAT-B: Portfolio route and optimizer

Business question: Your TTF supply resource can sell locally or through
BBL. Determine the best allocation, the binding constraint, and the PnL
attribution.

Starting context: Portfolio with the preview TTF resource.

Task: inspect resource terms, compare feasible and blocked routes, run the
optimizer, inspect allocations/unallocated volume/binding constraints, and
open the result in Review.

Expected observable outcome: allocations show route, volume, margin, PnL;
unallocated volume is zero or explained; warning/constraint text is
human-readable; Review shows immutable evidence and a decision recorder.

Feedback questions: Why did the allocation change? Could you explain the
constraint to a colleague? Was any number ambiguous or untrusted?

## UAT-C: Strategy research

Business question: Does an NBP OCM vs day-ahead window strategy survive a
one-month backtest?

Starting context: Strategy Lab.

Task: create a strategy, configure components/risk/economics, resolve
validation blockers, freeze, run a historical backtest, inspect PnL/drawdown/
events/attribution, create a second version, and compare runs.

Expected observable outcome: version lifecycle is explicit; backtest shows
provenance/data quality; comparison explains differences rather than only
numbers; no execution language appears.

Feedback questions: Could you defend the run to a reviewer? What assumptions
were missing? Did comparison make the difference understandable?

## UAT-D: Shadow monitoring

Business question: After a backtest, can the same strategy be monitored
without implying trading?

Starting context: frozen strategy + explicit baseline backtest.

Task: start shadow monitoring, verify schedule/prerequisites, observe a
normal evaluation, make a required source stale in the controlled fixture,
observe BLOCKED, restore, inspect drift and alerts, acknowledge, pause and
resume.

Expected observable outcome: blocked state appears without a fabricated
candidate; recovery is explicit; alert acknowledgement and pause/resume are
obvious; no execution instruction ever appears.

Feedback questions: Did the blocked state explain the cause? Was recovery
trustworthy? Was anything presented as a trade signal?

## UAT-E: Decision review

Business question: Can a manager understand and record a decision on a
persisted candidate?

Starting context: a persisted optimization/backtest/scenario candidate.

Task: inspect identity, scenario, economics, constraints, alternatives,
source evidence, data-quality warnings, provenance; record a review decision;
reopen it later and verify the original result is unchanged.

Expected observable outcome: evidence pack is complete and immutable; review
language is decision support only.

## UAT-F: Data/operations failure

Controlled failures: one source late, one stale, licensed source restricted,
scheduler failure, DB degraded/unavailable, source recovery.

For each, inspect Market, Strategy, Shadow, Portfolio, and Review. Expected:
only impacted surfaces degrade; unrelated valid data remains usable; the UI
names WHAT is affected, WHAT the last verified time was, and WHAT to do.

## UAT-G: Access/entitlement

Use VIEWER, ANALYST, REVIEWER, OPERATOR, ADMIN. Expected: allowed actions are
obvious, denied controls are unavailable/explained, restricted sources never
leak into derived results, and backend enforcement is authoritative.

## UAT-H: Desktop first-run

Install, launch, configure/authenticate server, reach first usable workspace,
understand connection state, visit Market/Portfolio/Strategy, restart, verify
preferences/context, inspect About/update state, and uninstall/upgrade where
relevant. No developer terminal required.
