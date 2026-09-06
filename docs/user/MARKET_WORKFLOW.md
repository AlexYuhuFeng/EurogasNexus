# Market Workflow

Business question: what is happening, where, and what does it mean for a
resource?

1. Set gas day, delivery product, and hub focus in the top context bar.
2. Read the hub board: bid/ask, mid, spread to TTF, source, freshness.
3. Use Curves & Spreads for tenor context and Network/Capacity & Events for
   physical and capacity context.
4. Inspect route candidates. Each row shows source, freshness, assumptions,
   and whether it is blocked, unavailable, or feasible.
5. Use **Open in Scenario** to carry the selected route into Decision Center.
   The context bar must still match the decision you are making.

If a value is stale or simulated, the source column says `_Sim` or the warning
register says so. Do not interpret simulated evidence as live licensed data.
