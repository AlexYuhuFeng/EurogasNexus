"""Convert a price between EUR/MWh, GBp/th and USD/MMBtu on the server.

The conversion uses an FX fix. Pass the rate explicitly, as here, or let the server use its
latest ECB reference rate (the demo store holds none, so explicit rates are used).
"""

import os

from eurogas_nexus_sdk.market import convert_gas_price_result

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

result = convert_gas_price_result(
    BASE_URL,
    value=42.47,
    from_unit="EUR/MWh",
    gbp_per_eur=0.86,
    usd_per_eur=1.08,
)
for unit in ("EUR/MWh", "GBp/th", "USD/MMBtu"):
    print(f"{unit:<10} {result.data['converted'][unit]:.4f}")
print(f"fx used: {result.data['fx']}")
print(f"warnings: {result.meta.warnings}")
