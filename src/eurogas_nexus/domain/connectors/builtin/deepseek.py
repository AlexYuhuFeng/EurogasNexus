"""DEEPSEEK connector manifest (src-deepseek)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    FreshnessPolicy,
    LicensedDataPolicy,
    SourceClass,
)

_LLM_NOTE = "External calls stay off until EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED allows them."

MANIFEST = ConnectorManifest(
    source_id="src-deepseek",
    system="DEEPSEEK",
    category="ai",
    datasets=("analysis", "reporting", "qa"),
    description="Model endpoint for operator-reviewed analysis: any OpenAI-compatible "
    "chat-completions service (DeepSeek by default; provider, URL and model are "
    "set by EUROGAS_NEXUS_LLM_PROVIDER_NAME, _BASE_URL and _MODEL). A service, "
    "not a data feed: it has no freshness or ingestion schedule.",
    entitled=True,
    freshness_minutes=0,
    integration="model_service",
    operations={
        "source_class": SourceClass.MODEL,
        "access_mode": AccessMode.KEYED_HTTP,
        "credential_fields": ("api_key",),
        "certification_required": True,
        "freshness_policy": FreshnessPolicy(0, 0, 0),
        "licensed_data": LicensedDataPolicy(),
    },
    credentials=(
        ProviderCredentialSpec(
            "DEEPSEEK",
            "DeepSeek",
            ("EUROGAS_NEXUS_LLM_API_KEY", "DEEPSEEK_API_KEY"),
            note=_LLM_NOTE,
        ),
        ProviderCredentialSpec(
            "LLM",
            "OpenAI-compatible model endpoint",
            ("EUROGAS_NEXUS_LLM_API_KEY",),
            note=_LLM_NOTE,
        ),
    ),
)
