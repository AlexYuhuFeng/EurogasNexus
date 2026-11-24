"""Trader/analyst: cost of moving gas TTF -> NBP over BBL from the stored TSO tariffs."""

import os
from datetime import date

from eurogas_nexus_sdk.route_cost import calculate_route_cost, fetch_route_candidates

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

candidates = fetch_route_candidates(BASE_URL)  # plain dicts
for candidate in candidates:
    print(f"route {candidate['route_id']}: {candidate['route_name']}")
route = next(
    c for c in candidates if c["start_point_name"] == "TTF" and c["target_point_name"] == "NBP"
)

# The calculation needs the TSO legs explicitly; without them it returns BLOCKED.
legs = [
    {
        "leg_id": leg["leg_id"],
        "country": leg["country"],
        "tso": leg["tso"],
        "point_name": leg["point_name"],
        "direction": leg["direction"],
        "component_type": f"{leg['direction']}_CAPACITY",
    }
    for leg in route["route_legs"]
]
result = calculate_route_cost(
    BASE_URL,
    scenario_id="example-ttf-nbp",
    source_resource_type="PIPELINE_IMPORT",
    start_point_id="TTF",
    target_hub_or_point_id="NBP",
    business_model="CROSS_BORDER_TRANSFER",
    gas_year="2026/27",
    capacity_product="ANNUAL",
    firmness="FIRM",
    flow_quantity=1000,
    flow_unit="MWh/d",
    tariff_legs=legs,
    tariff_applicability_date=date(2026, 12, 1),
)
print(f"status {result.status}: {result.total_cost} {result.unit}")
for part in result.cost_breakdown:
    print(f"  {part.component_type:<14} {part.amount:>6} {part.unit}  ({part.tariff_id})")
print(f"missing inputs {result.missing_inputs}; warnings {result.warnings}")
