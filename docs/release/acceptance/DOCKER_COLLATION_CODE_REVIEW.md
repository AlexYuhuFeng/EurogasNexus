# Database collation migration: bounded code review

Reviewed 2026-10-09. This is source inspection, not runtime parity certification.

- `db/repositories/backtest.py` loads market observations, quotes and FX by
  observation timestamps, costs by effective timestamps, decision events and
  series by numeric decision sequence. These queries do not explicitly sort
  text or call database lower/upper. Strategy registry versions sort by numeric
  version; run lists sort timestamps.
- Domain backtest name/hub/tenor normalization uses Python upper/lower; text
  sorting in temporal and duplicate selection code is also Python sorting,
  not PostgreSQL locale collation. Moving PostgreSQL alone does not change
  these Python operations.
- This does not prove deterministic parity: timestamp-only SQL order leaves
  ties unspecified. `temporal.fx_factor` chooses max observation time without
  a further tie breaker; equal-time differing rates can therefore depend on
  input order. Cost selection similarly needs equal-recency conflicts reviewed.
  These are existing deterministic-selection concerns, not proof of an actual
  migration-induced numerical difference. Do not change golden values silently.
- The wider market read path is locale-sensitive:
  `db/repositories/market_intelligence.py` ranks equal-time rows using textual
  venue/product fields and filters units with ILIKE. Route-cost reads also sort
  route names. A text-order change can change a limited result subset; the
  backtest repository finding must not be generalized to the whole application.
- Text unique constraints exist in identity, glossary, reference-network and
  research models. Successful restore is evidence that the current rows satisfy
  restored constraints, not evidence of all future Unicode comparison behavior.

Remaining gate: compare actual source/target text ordering, case mappings,
critical query selections and numerical controls; record Windows Chinese libc
versus Alpine en_US libc differences explicitly. Preserve source full-text
configuration. No data deletion is authorized by this source-only review.
