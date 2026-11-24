# Python SDK examples

Task-oriented recipes, each backed by a script in [`examples/sdk`](../../examples/sdk) that
runs as it stands. The output shown comes from the local demo server of the
[Quickstart](QUICKSTART.md), so every price is simulated and the firm is invented. Against
your own server the same code returns your data.

Every script starts the same way:

```python
import os

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")
```

and needs `EUROGAS_NEXUS_PUBLIC_API_TOKEN` (and optionally `EUROGAS_NEXUS_IDENTITY_BEARER`)
in the environment; see [Authentication](AUTHENTICATION.md).

| Recipe | Role | Script |
|---|---|---|
| [Check the server and make a first call](#check-the-server-and-make-a-first-call) | Everyone | `01_first_call.py` |
| [Today's prices and book](#todays-prices-and-book) | Trader, risk | `02_trader_today.py` |
| [Bid/ask board for a hub](#bidask-board-for-a-hub) | Trader | `03_trader_hub_quotes.py` |
| [Convert a price](#convert-a-price) | Trader, analyst | `04_price_conversion.py` |
| [Storage against the EU target](#storage-against-the-eu-target) | Analyst | `05_analyst_storage_vs_target.py` |
| [Backtest a spread rule](#backtest-a-spread-rule) | Analyst, quant | `06_analyst_spread_backtest.py` |
| [Cost of a route between hubs](#cost-of-a-route-between-hubs) | Trader, analyst | `07_route_cost.py` |
| [Limits and outages](#limits-and-outages) | Risk | `08_risk_limits_and_outages.py` |
| [Keep provenance and warnings](#keep-provenance-and-warnings) | Everyone | `09_provenance_and_warnings.py` |
| [Handle errors and retry reads](#handle-errors-and-retry-reads) | Everyone | `10_errors_and_retries.py` |
| [Cargoes in transit](#cargoes-in-transit) | LNG trader | `11_lng_cargo_plan.py` |

## Check the server and make a first call

`fetch_health` needs no credential and tells you the server version and profile. The Today
read is a good first authenticated call because it touches prices, positions and
fundamentals at once.

```python
from eurogas_nexus_sdk import fetch_health
from eurogas_nexus_sdk.desk import fetch_desk_today_result

health = fetch_health(BASE_URL)
result = fetch_desk_today_result(BASE_URL)
today = result.data
print(health.version, today.gas_day, today.front_month, today.focus_hubs)
print(result.meta.source_references, result.meta.warnings)
```

Output of [`01_first_call.py`](../../examples/sdk/01_first_call.py), abridged:

```text
server 1.0.0-beta, profile development, status ok
gas day 2026-11-24, front month Dec-26, hubs ['NBP', 'TTF', 'THE', 'PEG']
note: Demo data: simulated figures, not market data.
sources: ['runtime-postgresql:desk-today']; warnings: ['contract demo-mspa-atlantic-cn07: an FOB cargo is not on a European hub until it is sold or discharged', ...]
```

## Today's prices and book

The Today read (`GET /api/desk/today`) is computed on the server for the calling user: up to
four focus hubs, their day-ahead and front-month prices in each hub's own quotation, the
book against the market, fundamentals, what needs attention and the gas-day checklist.
`today.row(key)` returns one row as a dictionary. Each figure carries `value`, `unit`,
`as_of`, `state` (`current`, `late`, `stale`) and `simulated`.

```python
from eurogas_nexus_sdk.desk import fetch_desk_today_result

today = fetch_desk_today_result(BASE_URL).data
market = today.row("key_figures")["market"]
for hub in market["hubs"]:
    figure = hub["front_month"]
    print(figure["label"], figure["value"], figure["unit"], figure["state"])

for hub in today.row("book")["hubs"]:
    pnl = hub["day_pnl_change"]
    print(hub["hub"], hub["net_open_mwh"], pnl["value"], pnl["unit"])
```

Output of [`02_trader_today.py`](../../examples/sdk/02_trader_today.py), abridged:

```text
  NBP DA            103.778 GBp/th   current [simulated]
  NBP Dec-26         98.654 GBp/th   current [simulated]
  TTF DA             41.468 EUR/MWh  current [simulated]
  ...
Book against the market
  NBP  net open     11,964,399 MWh  day P&L change       -981,081 GBP
  TTF  net open      7,216,000 MWh  day P&L change     -1,197,856 EUR
```

Rows the server could not fill are absent or marked `populated: false`; `today.stale_figures`
names every late or stale figure. Each book figure carries a `method` with what it includes
and excludes; read it before quoting the number.

## Bid/ask board for a hub

`fetch_market_quotes_result` returns the latest quote per instrument. Prices are normalised
to `currency` per `unit` (NBP in GBP/MWh, not p/th). The venue's own quotation is in
`metadata_json` when the source provides it.

```python
from eurogas_nexus_sdk.market import fetch_market_quotes_result

quotes = fetch_market_quotes_result(BASE_URL).data
nbp = sorted((q for q in quotes if q.hub == "NBP"), key=lambda q: q.delivery_start_utc)
for quote in nbp[:4]:
    native = quote.metadata_json
    print(quote.product, quote.bid_price, quote.ask_price, f"{quote.currency}/{quote.unit}")
    print("  native:", native.get("native_bid"), native.get("native_ask"), native.get("native_unit"))
```

Output of [`03_trader_hub_quotes.py`](../../examples/sdk/03_trader_hub_quotes.py), abridged:

```text
NBP  within-day     35.4726/35.5647   GBP/MWh  native 103.96/104.23 GBp/th [simulated]
NBP  bom            35.2372/35.3259   GBP/MWh  native 103.27/103.53 GBp/th [simulated]
NBP  day-ahead      35.4317/35.4931   GBP/MWh  native 103.84/104.02 GBp/th [simulated]
```

The function takes no filter; it returns every quote the caller may see. For live updates,
`streaming.stream_events(BASE_URL, "stream/quotes")` yields server-sent events; it is not
covered by a script here.

## Convert a price

The server converts between EUR/MWh, GBP/MWh, GBp/th, USD/MMBtu, EUR/GJ and others with an
FX fix. Name the fix (`fx_source`, `fx_fixing`, `fx_date`) or pass explicit rates. Without
rates and without a stored ECB fix the FX-dependent results are `None` and `meta.warnings`
says why.

```python
from eurogas_nexus_sdk.market import convert_gas_price_result

result = convert_gas_price_result(
    BASE_URL, value=42.47, from_unit="EUR/MWh", gbp_per_eur=0.86, usd_per_eur=1.08
)
print(result.data["converted"]["GBp/th"], result.data["converted"]["USD/MMBtu"])
```

Output of [`04_price_conversion.py`](../../examples/sdk/04_price_conversion.py), abridged:

```text
EUR/MWh    42.4700
GBp/th     107.0419
USD/MMBtu  13.4425
```

## Storage against the EU target

`fetch_storage_target_trajectory` compares current fill with a target (90 % by default) and
reports the gap, the required injection pace and the projected fill at the deadline. It
returns a plain dictionary.

```python
from eurogas_nexus_sdk.storage import fetch_storage_sites, fetch_storage_target_trajectory

target = fetch_storage_target_trajectory(BASE_URL, code="EU", target_pct=90.0)
print(target["fill_pct"], target["status"], target["gap_twh"], target["limitations"])
sites = fetch_storage_sites(BASE_URL)
```

Output of [`05_analyst_storage_vs_target.py`](../../examples/sdk/05_analyst_storage_vs_target.py), abridged:

```text
EU fill 85.52 % on 2026-11-23; target 90.0 % by 2026-12-01 (behind)
gap 50.7 TWh; projected fill at deadline 83.632 %
Germany (demo)               fill  64.67 % of  247.00 TWh (DEMO_Sim)
```

A site may have no working capacity or fill; those fields are `None`, not zero.

## Backtest a spread rule

The spread lab builds a weighted spread of one to four daily series and backtests one
declared rule on the server. List the available series first.

```python
from eurogas_nexus_sdk.research import analyse_spread, list_spread_series

series = list_spread_series(BASE_URL)
analysis = analyse_spread(
    BASE_URL,
    legs=[
        {"hub": "TTF", "tenor": "month-ahead", "weight": 1.0},
        {"hub": "THE", "tenor": "month-ahead", "weight": -1.0},
    ],
    rule={"kind": "zscore", "lookback": 20, "entry_z": 2.0, "exit_z": 0.5},
)
print(analysis["statistics"], analysis["metrics"], analysis["limitations"])
```

Output of [`06_analyst_spread_backtest.py`](../../examples/sdk/06_analyst_spread_backtest.py), abridged:

```text
['TTF month-ahead', 'THE month-ahead'] in EUR/MWh: last -0.905, mean -0.723195, z-score 0.3807
rule: 16 trades, hit rate 0.133, total P&L -36107.0 EUR
limitation: Includes simulated price sources: not market evidence.
```

`analyse_spread` passes its keyword arguments to `POST /api/research/spread-analysis`. The
accepted fields are `legs` (`hub`, `tenor`, `weight`, optional `source_system`),
`date_from`, `date_to`, `rule` (`kind` `zscore` or `threshold`, `lookback`, `entry_z`,
`exit_z`, `low`, `high`, `volume_mwh_per_day`, `cost_per_mwh`, `execution`), `unit`,
`route_cost` and `fx`. A backtest is evidence for review, not a trading signal.

## Cost of a route between hubs

Route cost is priced from stored TSO tariffs, leg by leg. List the route candidates, then
pass the candidate's legs explicitly; without `tariff_legs` the result is `BLOCKED` with
`ROUTE_TARIFF_LEGS_REQUIRED`.

```python
from datetime import date
from eurogas_nexus_sdk.route_cost import calculate_route_cost, fetch_route_candidates

route = next(c for c in fetch_route_candidates(BASE_URL) if c["target_point_name"] == "NBP")
legs = [
    {"leg_id": leg["leg_id"], "country": leg["country"], "tso": leg["tso"],
     "point_name": leg["point_name"], "direction": leg["direction"],
     "component_type": f"{leg['direction']}_CAPACITY"}
    for leg in route["route_legs"]
]
result = calculate_route_cost(
    BASE_URL, scenario_id="example-ttf-nbp", source_resource_type="PIPELINE_IMPORT",
    start_point_id="TTF", target_hub_or_point_id="NBP", business_model="CROSS_BORDER_TRANSFER",
    gas_year="2026/27", capacity_product="ANNUAL", firmness="FIRM",
    flow_quantity=1000, flow_unit="MWh/d", tariff_legs=legs,
    tariff_applicability_date=date(2026, 12, 1),
)
print(result.status, result.total_cost, result.unit, result.warnings)
```

Output of [`07_route_cost.py`](../../examples/sdk/07_route_cost.py), abridged:

```text
status SUCCESS: 1.88 EUR/MWh
  EXIT_CAPACITY    0.56 EUR/MWh  (demo-sim-gts-itp-00063-exit)
  EXIT_CAPACITY     1.2 EUR/MWh  (demo-sim-bbl-company-itp-00207-exit)
  ENTRY_CAPACITY   0.12 EUR/MWh  (demo-sim-national-gas-tso-itp-00207-entry)
missing inputs []; warnings ['TARIFF_STATUS_SIMULATOR_ONLY']
```

`fetch_route_candidates` returns plain dictionaries; `calculate_route_cost` returns a
`RouteCostResult` model. The request fields are those of the `RouteCostScenario` schema
(see `/docs` on a development server). Always pass `tariff_applicability_date`; without it
the server reports that tariff applicability was not assessed.

## Limits and outages

The Today read carries the net position and the tightest limit with the method behind it;
outages come from `physical.fetch_outages_result`.

```python
from eurogas_nexus_sdk.desk import fetch_desk_today_result
from eurogas_nexus_sdk.physical import fetch_outages_result

key_figures = fetch_desk_today_result(BASE_URL).data.row("key_figures")
limit = key_figures["tightest_limit"]
print(limit["label"], limit["value"], limit["unit"], limit["utilisation_pct"], limit["status"])
for event in fetch_outages_result(BASE_URL).data:
    print(event.facility_name, event.balancing_zone, event.unavailable_gwh_d, event.end_utc)
```

Output of [`08_risk_limits_and_outages.py`](../../examples/sdk/08_risk_limits_and_outages.py), abridged:

```text
Net position today: 52,000 MWh/d
tightest limit: Rhinmark Handel GmbH credit headroom -395,992 EUR (110.6 % used, breach)
outage Demo Haldor field, Norwegian shelf (NBP): 563.2 GWh/d until 2026-11-27T10:02:42.477052+00:00
```

## Keep provenance and warnings

Use the `_result` form of a function when you keep or share the numbers: `meta` carries the
server's source references and warnings, which the short form drops. Rows also say whether
they are simulated.

```python
from eurogas_nexus_sdk.market import fetch_market_quotes_result
from eurogas_nexus_sdk.sources import fetch_sources_result

result = fetch_market_quotes_result(BASE_URL)
print(result.meta.model_dump())
print(sum(q.simulated for q in result.data), "simulated of", len(result.data))
for source in fetch_sources_result(BASE_URL).data[:3]:
    print(source.source_id, source.category, source.operational_status)
```

Output of [`09_provenance_and_warnings.py`](../../examples/sdk/09_provenance_and_warnings.py), abridged:

```text
240 quotes; meta: {'research_only': True, 'human_review_required': True, 'source_references': ['runtime-postgresql'], 'warnings': []}
240 of 240 quotes are simulated
  src-ecb: fx, no_records
  src-entsog: infrastructure, active
```

## Handle errors and retry reads

A refusal raises `NexusAPIError`, which carries the stable code and never needs the body
parsed. The SDK never retries: retry only reads, only on network errors or answers marked
`recoverability: retry`.

```python
from eurogas_nexus_sdk import NexusAPIError
from eurogas_nexus_sdk.reference_network import fetch_node

try:
    fetch_node(BASE_URL, "NO-SUCH-NODE")
except NexusAPIError as error:
    print(error.status_code, error.code, error.recoverability)
    print("quote this to an administrator:", error.correlation_id)
```

Output of [`10_errors_and_retries.py`](../../examples/sdk/10_errors_and_retries.py), abridged:

```text
HTTP 404 not_found (recoverability permanent, correlation id afa34b8914914ab9)
network error after retries: ConnectError
```

The script also contains a `with_retries` helper with exponential back-off. See
[Troubleshooting](TROUBLESHOOTING.md) for the error codes.

## Cargoes in transit

Each firm cargo at sea as one plan: its slot status, the last change to it in one line, and
the energy per hub and delivery month against the hedges recorded for it. Decision support
only; nothing is traded or nominated. See
[LNG cargo in transit](../engineering/Commercial-Intelligence-V3/12_LNG_CARGO_IN_TRANSIT.md).

```python
from eurogas_nexus_sdk.lng_cargo_plan import fetch_cargo_plan, fetch_cargo_plans, try_cargo_eta

for line in fetch_cargo_plans(BASE_URL):
    print(line["cargo_id"], line["slot_status"], line.get("headline"))

plan = fetch_cargo_plan(BASE_URL, "SAB-0412")
for month in plan.months:
    print(month.hub, month.month, month.physical_mwh, month.hedge_mwh, month.net_mwh)

# What would a two-day slip do? Nothing is stored.
change = try_cargo_eta(BASE_URL, "SAB-0412", eta_utc="2026-12-27T06:00:00Z")
print(change["headline"])
```

The demo desk holds no firm cargoes, so against the demo server
[`11_lng_cargo_plan.py`](../../examples/sdk/11_lng_cargo_plan.py) prints that the board is
empty; an ETRM import of the firm's cargoes fills it.
