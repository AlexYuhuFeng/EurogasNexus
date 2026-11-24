"""Check the server, then make a first authenticated read (the desk's Today view)."""

import os

from eurogas_nexus_sdk import fetch_health
from eurogas_nexus_sdk.desk import fetch_desk_today_result

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

# Health needs no credential. It says the server is up; it says nothing about data.
health = fetch_health(BASE_URL)
print(f"server {health.version}, profile {health.profile}, status {health.status}")

# Every other call needs the deployment token in EUROGAS_NEXUS_PUBLIC_API_TOKEN.
result = fetch_desk_today_result(BASE_URL)
today = result.data
print(f"gas day {today.gas_day}, front month {today.front_month}, hubs {today.focus_hubs}")
if today.simulated:
    print(f"note: {today.simulated_notice}")
print(f"sources: {result.meta.source_references}; warnings: {result.meta.warnings}")
