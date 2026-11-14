"""The connector registry: built-in manifests plus allow-listed plugins (C1, C2).

Built-in manifests are listed here in catalogue order. Installed plugin packages declare
manifests through the ``eurogas_nexus.connectors`` entry-point group (see
``domain/connectors/plugins.py``).
"""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest

#: Catalogue order of the built-in connectors (module names under ``builtin/``).
BUILTIN_MODULES: tuple[str, ...] = (
    "ecb",
    "entsog",
    "gie",
    "national_gas_nts",
    "bbl",
    "iuk",
    "gts",
    "natran",
    "german_tso",
    "fluxys_belgium",
    "cnmc_enagas",
    "eex",
    "eex_sim",
    "ice_ocm",
    "ice_ocm_sim",
    "trayport",
    "trayport_sim",
    "ice_endex",
    "cme",
    "ngx",
    "eia",
    "platts",
    "icis",
    "icis_sim",
    "argus",
    "kpler",
    "weather",
    "entsoe",
    "elexon",
    "national_gas_supply",
    "national_gas_demand",
    "boe",
    "ecb_estr",
    "nyfed",
    "remit_umm",
    "ecmwf_open_data",
    "deepseek",
    "wmr",
    "bfix",
)


@lru_cache(maxsize=1)
def builtin_manifests() -> tuple[ConnectorManifest, ...]:
    manifests = tuple(
        import_module(f"eurogas_nexus.domain.connectors.builtin.{name}").MANIFEST
        for name in BUILTIN_MODULES
    )
    ids = [manifest.source_id for manifest in manifests]
    if len(ids) != len(set(ids)):
        raise RuntimeError("two built-in connector manifests declare the same source_id")
    return manifests


def connector_manifests() -> tuple[ConnectorManifest, ...]:
    """Every connector the product offers: built-in first, then installed plugins."""

    from eurogas_nexus.domain.connectors.plugins import plugin_manifests

    builtin = builtin_manifests()
    taken = {manifest.source_id for manifest in builtin}
    return builtin + tuple(
        manifest for manifest in plugin_manifests() if manifest.source_id not in taken
    )


def manifest_for(source_id: str) -> ConnectorManifest | None:
    for manifest in connector_manifests():
        if manifest.source_id == source_id:
            return manifest
    return None


def source_attribution(source_id: str | None) -> str:
    """The attribution a source's terms require, from its manifest ("" when none recorded)."""

    needle = (source_id or "").strip().casefold()
    for manifest in connector_manifests():
        if manifest.source_id.casefold() == needle:
            return manifest.attribution
    return ""
