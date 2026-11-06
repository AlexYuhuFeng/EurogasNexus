"""Weather connector manifest (src-weather)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    FreshnessPolicy,
    LicensedDataPolicy,
    SourceClass,
)

MANIFEST = ConnectorManifest(
    source_id="src-weather",
    system="Weather",
    category="weather",
    datasets=("temperature", "hdd", "cdd", "forecast"),
    description="Template for a licensed weather vendor the deployment has not chosen yet; "
    "no connector reads it. ECMWF Open Data is the implemented weather source.",
    entitled=True,
    freshness_minutes=180,
    integration="template",
    operations={
        "source_class": SourceClass.LICENSED,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(180, 360, 720),
        "licensed_data": LicensedDataPolicy(),
    },
    credentials=(ProviderCredentialSpec("Weather", "Weather", implemented=False),),
)
