# DRAFT ADR (a question, not an answer): Should Nexus support sub-daily periods for power trading?

**Status:** DRAFT, awaiting owner review (2026-11-26). Raised by the front-office and quant reviews
and by [ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) section 8, decision 10. This record
asks the question and states what each answer would commit the product to. It recommends an
answer but decides nothing until the owner does.

**Context.** The gas day (06:00 to 06:00 local time on the continent, 05:00 to 05:00 UK time,
with 23- and 25-hour days at the clock changes) is the atomic period of the data model,
positions, nominations and the ladder. That is right for gas operations, and the reviewers
praised it. Power is traded in hours and, since the move to 15-minute products in European
day-ahead and intraday markets, in quarter-hours; its products are base, peak and off-peak blocks,
day-ahead auctions and continuous intraday trading; its constraints are cross-border capacity
and flow-based market coupling; its assets have ramp and start costs. Decisions 25 and 26 already
allow power as a commodity in the market model, and `domain/power/gas_for_power.py` computes
clean spark and dark spreads, fuel-switch prices and residual load from ENTSO-E data, with
publication times kept. No power position, product or period model exists.

**The question.** Will Nexus become a decision-support tool for power traders, and if so, when?

**What "yes" would require (architectural, not page-level).**

1. A period model below the day: an interval type (start, end, resolution) for quantities,
   positions and prices, with hours and quarter-hours, DST days of 92 and 100 quarter-hours,
   and aggregation to blocks; the gas day becomes one calendar among several.
2. Power products and calendars: base, peak, off-peak; EPEX and exchange calendars; shaped
   positions per hour or quarter-hour; hourly price forward curves (shaping a monthly curve into
   hours).
3. Data: hourly and quarter-hourly prices (licensed EPEX and EEX under the customer's
   entitlement), cross-border capacity (JAO), plant availability; tens of times the rows of
   today's daily data (an ADR on the partitioned and possibly separate time-series store would
   follow).
4. Models: dispatch and tolling with ramp and start costs, spark-spread options, PPA valuation
   with capture and profile risk.
5. Latency: intraday power decisions are made in minutes; the live path of the feed-handler
   draft would be needed for power venues.

Rough size: 40 to 70 engineer-weeks before a power desk would find it useful, plus licensed
data.

**What "no, not now" means.** Gas-for-power stays as fundamentals inside gas research: spark and
dark spreads explain gas burn and the balance. No power desk feature is built. The data model
does not block a later "yes": new tables would carry intervals; gas tables keep the gas day.

**Recommendation.** Answer "not in the next 12 months". The gas product still lacks its own
foundations (close, versioned trades, live prices, control workspaces); a power extension now
would split a small team across two data models. Revisit when a paying customer with a power desk
asks for it and phases 1 to 4 of the plan are done. Whatever the answer, the product must not be
described as a power trading tool until this record is accepted with "yes".

**Alternatives considered for a later "yes".** (a) Hourly granularity everywhere, including gas:
simpler model, but gas would carry 24 times the rows with no use. (b) A separate power product on
the same platform: duplicates reference data, identity and operations. (c) Intervals as an added
dimension where needed (recommended for a later "yes"): gas keeps the gas day, power gets
intervals, and they meet in the market model and the exposure model.
