"""Analyst: EU storage against the 90 % target, and fill by country."""

import os

from eurogas_nexus_sdk.storage import fetch_storage_sites, fetch_storage_target_trajectory

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

target = fetch_storage_target_trajectory(BASE_URL, code="EU", target_pct=90.0)
print(
    f"EU fill {target['fill_pct']:.2f} % on {target['as_of_gas_day']}; target"
    f" {target['effective_target_pct']} % by {target['deadline']} ({target['status']})"
)
print(
    f"gap {target['gap_twh']:.1f} TWh;"
    f" projected fill at deadline {target['projected_fill_at_deadline_pct']} %"
)
for limitation in target.get("limitations", []):
    print(f"limitation: {limitation}")

# Capacity or fill can be missing for a site; missing is not zero, so it is shown as "n/a".
sites = fetch_storage_sites(BASE_URL)
for site in sorted(sites, key=lambda s: s.working_capacity_twh or 0, reverse=True)[:5]:
    fill = f"{site.fill_pct:.2f} %" if site.fill_pct is not None else "n/a"
    capacity = f"{site.working_capacity_twh:.2f} TWh" if site.working_capacity_twh else "n/a"
    print(f"{site.name:<28} fill {fill:>8} of {capacity:>11} ({site.source_system})")
