"""Every analyst: keep provenance and warnings with the numbers.

Functions ending in ``_result`` return an ``SdkResult`` with ``data`` and ``meta``. ``meta``
carries the server's source references and warnings; the shorter form without ``_result``
drops them. Rows also say whether they are simulated.
"""

import os

from eurogas_nexus_sdk.market import fetch_market_quotes, fetch_market_quotes_result
from eurogas_nexus_sdk.sources import fetch_sources_result

BASE_URL = os.environ.get("EUROGAS_NEXUS_BASE_URL", "http://127.0.0.1:8000")

with_meta = fetch_market_quotes_result(BASE_URL)
data_only = fetch_market_quotes(BASE_URL)
print(f"{len(data_only)} quotes; meta: {with_meta.meta.model_dump()}")

simulated = sum(q.simulated for q in with_meta.data)
print(f"{simulated} of {len(with_meta.data)} quotes are simulated")

sources = fetch_sources_result(BASE_URL)
print(f"{len(sources.data)} registered sources; first three:")
for source in sources.data[:3]:
    print(f"  {source.source_id}: {source.category}, {source.operational_status}")
