# Data Status and Provenance

Eurogas Nexus separates research state from current market state.

## Where evidence is shown

- Source and freshness columns on market/route/strategy cards.
- Warnings and missing-input lists on every analytical result.
- Evidence packs in Review.
- Source Center for credential/certification/runtime state per source.

A surface that reads a shared or on-demand slice states its own read, too: the Source Center says
whether its registry read is pending, failed (with the read's own retry), or answered - and only a
read that answered may present a count. A failed or not-yet-answered read is never shown as a
measured zero, and rows that are held from an earlier read are labelled as the last committed
reading.

The capacity operating board reads two slices, not one (physical flows and technical capacity), so
it states which of them answered: counts, the row total and the filter sentence appear only when
both did. A read that did not answer is named in the board itself with the read's own retry; the
rows the other read holds may stay on screen, marked as an incomplete board, and a board whose two
reads answered with no row says so as a measured empty result rather than as a filter that matched
nothing.

## Status vocabulary

- `FRESH/LATE/STALE/MISSING/NOT_EXPECTED`: backend-owned freshness evaluation.
- `BLOCKED`: a required input is missing or unknown; the calculation did not
  proceed.
- `UNAVAILABLE`: the data or service cannot currently provide evidence.
- `_Sim`: simulated preview data; never live licensed evidence.
- `research_only` / `human_review_required`: decision-support guardrails.

If a value looks surprising, check the gas day/product context, the source,
the freshness timestamp, and the warning register before interpreting it.
