# Market Cockpit Specification — CR-07

Status: accepted CR-07 architecture. This document owns the consolidated
European gas Market cockpit: information architecture, hub/product/spread
semantics, map layers, capacity, events, storage/LNG, route economics,
portfolio linkage, handoffs and degraded states.

## 1. User jobs

Professional users open Market to answer: what is happening at TTF/NBP/ZTP;
which spreads moved; is the move price, physical or both; what capacity/
outages matter; which routes are economically interesting; how is my portfolio
affected; what is the source/freshness of every value; and where can I hand
this context to Scenario/Strategy/Review.

## 2. Existing problems (audit)

Audit of `NetworkWorkspace`, `MarketTerminal`, `CapacityWorkspace`,
`GasNetworkMap`, `IntradayDecisionFeed` and the Market primary navigation:

- Market is split across three technical pages: `network`, `market`,
  `capacity`; users reconstruct gas day/hub/product context manually.
- `MarketTerminal` already contains a professional hub board, tenor tabs,
  curve lanes, source matrix and opportunities, but no map/physical/route
  linkage.
- `NetworkWorkspace` is portfolio-optimizer-centric and visually dominates
  the map; market context appears only as a small context strip.
- `CapacityWorkspace` is an isolated technical table with local country/
  operator/posture filters, disconnected from hub/route selection.
- Hub selection in Market sets trader context, but Network/Capacity do not
  react to it.
- Route candidates and route economics exist in NetworkWorkspace and
  Scenario, but no compact route economics rail is present in Market.
- Storage/LNG are only capacity sub-views; they are not contextual in the
  default market surface.
- Source freshness is present but inconsistent: some panels show timestamps,
  some only generic `live`.
- Market sparklines are real observations but no provenance appears on the
  sparkline itself.
- No spread matrix exists; `spread_to_ttf` is a single-column rail.
- Outage/event feed does not exist; ENTSOG/GIE event data are not normalized.
- Map search lives in the top bar, but local search in the cockpit is absent.
- Duplicated client-side calculations: quote mid, staleness, hub ranking and
  spread display are reimplemented in multiple components.
- Empty/degraded states are not designed as a partial cockpit; one missing
  feed often leaves a blank panel.

## 3. Information architecture

Market remains ONE primary workspace with local tasks:

- `OVERVIEW`
- `CURVES & SPREADS`
- `NETWORK`
- `CAPACITY & EVENTS`

Deep links: `?workspace=market&task=<overview|curves|network|capacity>`.
Legacy technical deep links `?workspace=network` and `?workspace=capacity`
continue to resolve to the same Market primary workspace and map to
NETWORK/CAPACITY tasks respectively.

All tasks share trader context (gas day, delivery product, hub), selected
route/resource, and source health.

## 4. Hub model

Hub is the central identity: TTF, NBP, ZTP, THE, PEG, PSV, CEGH, VTP where
supported. Each hub row shows only fields backed by observations: bid/ask
from L1 quotes when present, otherwise mid/assessment; no fabricated
bid/ask.

## 5. Product model

Supported tenors: within-day, day-ahead, weekend, month-ahead. Product is
shared trader context, not a per-panel dropdown. Unsupported products are
absent, never rendered as zeros.

## 6. Price provenance

Every hub/quote row exposes source system, venue, observed timestamp,
delivery period, currency/unit, source reference and freshness state
(`LIVE`, `DELAYED`, `ASSESSMENT`, `SIMULATED`, `STALE`, `RESTRICTED`,
`UNAVAILABLE`). Sparklines are built only from persisted observations and
include accessible labels.

## 7. Spread convention

Documented convention: `row hub price - column hub price`, expressed in
GBP/MWh where backend FX normalization exists. The Overview uses
`MarketSpreadDTO` from the backend where available and never computes a
spread when both legs are absent.

## 8. Network / map model

Map remains the central spatial surface. Layer groups: markets/hubs,
network, infrastructure (LNG/storage), operations (flows/capacity),
portfolio routes. Verified pipeline geometry is visually distinct from
indicative corridors with legend and text, not color alone. Selecting a hub
focuses map labels; selecting a corridor/route recedes unrelated geometry.

## 9. Capacity semantics

Technical, booked/nominated and available capacity are separate columns.
Unknown capacity is `n/a` and never means unlimited. Direction is explicit.
Capacity rows expose operator, point, timestamp and source reference.

## 10. TSO access

For any route/corridor, TSO access state is
`CONFIRMED`, `MISSING`, `UNKNOWN`, or `RESTRICTED`. Missing required access
is a visible blocker and fails closed in route logic.

## 11. Tariffs

Tariff rows show component, currency/unit, valid period, source and
effective date. Incompatible periods are not combined.

## 12. Outages / events

Current normalized feeds do not include a general outage table, so CR-07
does not fabricate an event model. ENTSOG/GIE operational observations that
indicate constraints (capacity zero, flow/capacity imbalance) are surfaced
as constraint rows with source/time. A future event feed can mount into the
same timeline/table contract.

## 13. Storage

Facility rows show inventory, fullness, injection/withdrawal, capacity and
observation time/source where present. Storage is contextual, not a default
full-page table.

## 14. LNG

Terminal rows show send-out, inventory, DTMI and observation time/source
where present. Missing licensed vessel data is shown as unavailable, never
invented.

## 15. Route economics

The Overview right rail surfaces existing route candidates and optimizer/
recommendation output: route id, origin/destination, quantity, tariff/FX/
balancing where backend provides it, access state, capacity, all-in cost,
destination value and indicative margin. All values come from persisted API
results; no authoritative margin is computed in React.

## 16. Portfolio linkage

The rail shows relevant portfolio resources for the focused hub and the
number of affected route candidates. Actions open Portfolio/Scenario with
identifiers only.

## 17. Trader-context behavior

Hub/product/gas-day selection is explicit and global within Market tasks.
Selecting a hub in Overview updates the map focus and rail; switching tasks
does not clear it.

## 18. Handoffs

- `Open in Scenario` sets route/resource selection and navigates.
- `Inspect in Strategy Lab` sets hub context and navigates.
- `Open in Portfolio` navigates to Resource Terms with resource context.
- Review continues to receive existing run/resource ids; Market does not
  introduce an “approve trade” action.

## 19. Degraded states

One failed source must not blank the cockpit. Each panel independently
shows unavailable/stale/restricted with a concrete next action. Partial
market/capacity/map data is labelled.

## 20. Accessibility

Keyboard hub selection, tab semantics, visible focus, accessible map
alternatives in tables, text+badge source states, labelled chart summaries.
A user unable to use the map can reach all capacity/route data through
tables.

## 21. Performance

Existing components are memoized around their inputs. Overview uses the
same map instance patterns and does not rebuild MapLibre for hub selection.
Hub board/spread rails cap rendered rows. Benchmark documented in
scheduled state.

## 22. Known limitations

- No normalized outage/event feed exists yet; CR-07 shows operational
  constraints inferred from existing data only.
- Spread matrix is limited to hubs present in `MarketSpreadDTO`.
- Licensed LNG vessel/arrival data remains unavailable by source posture.
- Map selection does not yet expose a full per-object context drawer in
  Overview; Network task remains the deep inspection surface.
