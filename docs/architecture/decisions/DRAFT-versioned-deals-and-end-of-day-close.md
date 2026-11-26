# DRAFT ADR: A versioned copy of the ETRM's trades, one exposure model, and an end-of-day close

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) sections 3.1 and 3.4. On acceptance it is
appended to [ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md). It keeps
Decision 11 (no trade capture, no official approvals, no accounting) and builds on Decision 28
(outbox) and the existing valuation snapshots.

**Context.** The ETRM import (`ingestion/etrm_trades.py`) keys trades by (system, trade id); a
re-sent trade replaces its earlier version and a cancelled one is removed. Its columns carry a
fixed price and a flat volume, no trader, legal entity, index or formula pricing, shape, optional
volume or regulatory identifier (UTI). Positions, mark-to-market and value-at-risk are computed
when a screen asks (`api/routes/public/portfolio.py`) and are not stored; prices are pruned; so
no past figure can be recomputed, and an index-priced purchase appears as flat-price risk. The
price resolver prefers the freshest price, including intraday ticks, over settlement. Today and
the ladder show different net positions for the same hub and day. The middle office, quant,
technology and operations reviews each name this as a blocker: control functions are built around
the question "what did we report at the close on a given date, and why did it differ?".
Foundations exist: `application/valuation_snapshot.py: freeze_snapshot` and `ReplayReader`,
`application/calculation_manifest.py`, revisions with `as_of` reads, and the job runner.

**Decision.**

1. **A versioned copy, not capture.** `deals`, `deal_versions` and `deal_legs` hold every version
   the ETRM sends: the ETRM's amendment time (when it became true) and the time Nexus recorded it
   (two times, "bitemporal"). Cancelled is a status; nothing is deleted. A version carries
   trader, legal entity, book, counterparty and UTI; a leg carries fixed, index or formula
   pricing (index, averaging period, differential, currency, unit), a quantity shape (per gas
   day, per hour where needed) and optional-volume terms. Nexus never edits a deal. Import
   contract `etrm.deals.v2` writes this; `v1` keeps working into the same tables with the
   missing fields empty.
2. **Bitemporal only where it matters**: deal versions; valuation-relevant reference data
   (limits, mandates, hedge bands, firm marks, entity and counterparty terms; extending the
   change-request table of Decision 32 with effective dating); settlement prices (which
   publishers revise). Observations keep their existing revisions.
3. **One exposure model.** One function turns deal legs into (a) physical volume by gas day and
   delivery point and (b) price exposure by risk factor (hub or index, by tenor), including basis
   and averaging exposure for index legs. Every screen, report and risk calculation reads it.
4. **Two price sets** (see the feed-handler draft): live and official. Recorded figures read only
   the official set.
5. **End-of-day close.** A `close_run` per business date and legal entity (and optionally per
   desk) runs as a job after the official settlements arrive. It freezes: the official curve
   (built from one snapshot of settlements or the firm's policy prices, with its quotes and
   construction), the deal versions known at the cut-off, positions, exposures, discounted
   mark-to-market with forward FX, risk, credit and limit use. Its manifest holds input hashes,
   model versions (from the model register) and the code fingerprint. A frozen run is immutable;
   a rerun creates a new run that supersedes it with a reason. Screens of record read close
   results; live screens add a labelled live overlay.
6. **Attestation, not sign-off.** Product control may attest that a frozen close matches the
   ETRM's official figures (imported); the attestation is a four-eyed record in Nexus. The official
   profit-and-loss sign-off stays in the ETRM or finance system (Decision 11).
7. **Reconciliation.** A daily report compares trade counts, volumes and (where imported)
   official values by book against the ETRM, with a breaks queue owned by the integration role.

**Alternatives.** (a) Full bitemporal storage on every table: doubles write and read cost where
no question needs it. (b) Event sourcing: a second model of truth beside the outbox and a rewrite
of every reader. (c) Importing the ETRM's positions and risk only: nothing could be explained,
stressed or decomposed. (d) Trade capture in Nexus: forbidden by Decision 11 and the positioning.
(e) Snapshots of screens instead of a close run: freezes presentation, not the inputs, so nothing
can be recomputed.

**Consequences.** Storage grows by the versions kept and the close results (small next to
observations). Official screens become fast (they read stored results). A close that cannot run
(settlements missing) is visible as such, rather than silently using a tick. The "day P&L change"
indication is replaced by the close's explanation.

**Migration.** (1) Tables and `etrm.deals.v2` (expand-only); `v1` imports write versions too.
(2) The exposure function, with the screens moved to it one by one and a test that Today and the
ladder agree. (3) `settlement_prices` and the official curve. (4) The close job reusing
`freeze_snapshot` and the manifest. (5) Readers of record move to close results. (6) The old
upsert-and-delete path is removed after one release.

**Tests that make it observable.** A close rerun from its manifest reproduces every stored figure
exactly; an amendment after the cut-off leaves the frozen close unchanged and appears in the next;
a cancelled deal remains readable as cancelled; an index-priced leg contributes basis exposure and
no flat-price exposure; one net-position definition on every screen.
