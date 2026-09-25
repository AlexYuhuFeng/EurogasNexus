# Source Coverage Read

## Scope

The normalized market view folds its observations through
`list_market_observations_with_source_coverage`
(`src/eurogas_nexus/db/repositories/market_intelligence.py`). The endpoint is
bounded, but a low-frequency source - a daily ICIS assessment - must not be
crowded out by hundreds of high-frequency simulated ticks. This note records the
read's contract and the cost it trades, not a new selection rule.

## Contract

- The payload is the globally newest `limit` rows merged with a bounded
  reservation for the gas sources (`unit ILIKE '%MWH%'`), deduplicated by
  `observation_id`, capped at `limit`, and ordered by the market observation
  route's own order: observed instant desc, venue, product.
- The reservation is read as one bounded page per candidate source
  (`min(per_source_limit, limit)` rows, in the shape
  `ix_market_observations_source_time` (migration 0010) serves), and the quota
  `min(per_source_limit, max(1, limit / gas_sources))` is applied after the
  reads, because the divisor is only known once every candidate source has
  answered. A source with no gas row reserves nothing and consumes no quota.
- Entitlement applies before any row is fetched when the caller supplies the
  entitled `source_systems` (the normalized route and the projections do): the
  candidate list is the filter. A caller that supplies none gets the source
  values present in the table from one `DISTINCT` read.
- The reservation is merged first, so a reserved row is never displaced by a
  newer global row, and rows tied on the read order keep the reservation ahead of
  the global read. Reserved rows are not re-ranked: the read has no ordering rule
  of its own beyond the route's order.

## Ambiguity that is deliberately not resolved

Rows tied on the whole order key (instant, venue, product) are cut by the
database. That was already true of the superseded ranking window, and this read
does not append an `observation_id` tie-break to redefine it.

## Fallback when the reservation cannot fit

If the candidate sources outnumber the payload bound the quota is one row per gas
source and the reservation may not fit inside `limit`; which rows survive would
then be decided by a page order - a choice this read has no mandate to make. The
candidate count is known before any row is read, so that rare case takes the
superseded shape directly: a `count(DISTINCT source_system)` aggregate plus the
`row_number() OVER (PARTITION BY source_system ...)` ranking window joined back to
`market_observations`. It is the algorithm that decided the case before, so the
selection is not silently redefined; its two full-history reads are the cost of
that fallback.

## Cost and how it is measured

- The reservation issues one statement per candidate source (plus the one
  `DISTINCT` enumeration when no source set is supplied), where the superseded
  shape issued two statements whatever the number of sources. A source with no gas
  row still costs one walk of its own rows to establish that there is none.
- A schema built from the ORM metadata (the SQLite unit-test database) does not
  declare `ix_market_observations_source_time`: the values are identical there,
  the cost shape is not.
- `python scripts/ops/measure_market_projection_latency.py --max-sources N`
  measures both shapes on the configured runtime store. The `comparison` block
  sums **server** plan times (`EXPLAIN (ANALYZE, BUFFERS)`) per shape, so it
  excludes network round trips: in production the superseded shape pays two round
  trips whatever the source count and the shipped shape one per source. The
  superseded statements are also the fallback's cost, which is why they stay in
  the report.

## References

- `docs/operations/PERFORMANCE_BASELINE.md` for the methodology rules every
  measurement follows.
- `tests/unit/test_market_intelligence_repository.py` for the equivalence and
  fallback regressions.
