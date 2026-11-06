"""ECMWF_OPEN_DATA connector manifest (src-ecmwf-open-data)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest

MANIFEST = ConnectorManifest(
    source_id="src-ecmwf-open-data",
    system="ECMWF_OPEN_DATA",
    category="weather",
    datasets=("ifs_0p25_oper_2t_forecasts",),
    description="ECMWF Open Data IFS 0.25° 2 m temperature forecasts. Actual public "
    "source under CC BY 4.0; attribution: ECMWF.",
    entitled=False,
    freshness_minutes=720,
)
