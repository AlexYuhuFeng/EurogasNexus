"""The connector manifest: one declaration per provider (docs/product/CONNECTORS.md, C1).

A manifest holds everything the product knows about one source in one place: the catalogue
row (what it provides, how it arrives, its licence family), its operations policy (schedule,
freshness, retry, rate limit, certification) and the credentials it may use. The source
registry, the data-operations registry and the provider credential contract are views
derived from the manifests, so nothing reads a provider from two places.

A manifest grants nothing: data scopes, the licence register, certification and the
four-eyes rules stay in the backend and a connector cannot widen them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class ProviderCredentialSpec:
    """Where one provider's key may come from (the #38 credential contract)."""

    provider_id: str
    display_name: str
    env_vars: tuple[str, ...] = ()
    file_env: str | None = None
    implemented: bool = True
    note: str = ""


@dataclass(frozen=True)
class ConnectorManifest:
    source_id: str
    system: str
    category: str
    datasets: tuple[str, ...]
    description: str
    entitled: bool
    freshness_minutes: int
    #: How the data arrives: "api", "file_import", "template" or "model_service" (#33).
    integration: str = "api"
    #: A file-imported licensed dataset: served only to holders of its data scope even though
    #: no key is configured for it (WM/Reuters, BFIX).
    licensed_import: bool = False
    #: Operations policy overrides for the data-operations registry (schedule, freshness...).
    operations: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    #: Credentials the connector may use, in the order the credential manager lists them.
    credentials: tuple[ProviderCredentialSpec, ...] = ()
    #: Set for a connector loaded from an installed plugin package (C2).
    plugin: str | None = None
    #: The credit the provider's terms require wherever its data is shown or exported
    #: (docs/legal/DATA_SOURCE_TERMS.md); empty when none is recorded.
    attribution: str = ""
