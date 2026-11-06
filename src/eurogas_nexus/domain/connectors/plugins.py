"""Connector plugins (docs/product/CONNECTORS.md, C2).

A plugin is an installed Python package that declares one or more connector manifests
through the ``eurogas_nexus.connectors`` entry-point group::

    [project.entry-points."eurogas_nexus.connectors"]
    kpler_cargo = "acme_kpler.connector:MANIFESTS"

The entry point names a ``ConnectorManifest`` or a sequence of them. No code is uploaded
through the browser: a plugin is installed with the deployment, reviewed like any
dependency (licence check, AGENTS rule 18) and versioned with the release.

An installed plugin appears in the catalogue as available. It runs only once an
administrator lists its entry-point name in ``EUROGAS_NEXUS_CONNECTOR_PLUGINS``; until then
its operations are forced off (not schedulable, not enabled), whatever it declares. A
plugin can never replace a built-in connector's ``source_id`` and grants no data scope,
licence or certification.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import replace
from importlib.metadata import EntryPoint, entry_points
from types import MappingProxyType

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest

ENTRY_POINT_GROUP = "eurogas_nexus.connectors"
#: The administrator's allow-list: comma-separated entry-point names.
ALLOW_LIST_ENV = "EUROGAS_NEXUS_CONNECTOR_PLUGINS"

_LOGGER = logging.getLogger(__name__)
_DISABLED_OPERATIONS = MappingProxyType({"schedulable": False, "enabled_default": False})


def enabled_plugin_names(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    env = os.environ if environ is None else environ
    raw = str(env.get(ALLOW_LIST_ENV) or "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def _declared(entry_point: EntryPoint) -> list[ConnectorManifest]:
    loaded = entry_point.load()
    items: Iterable[object] = (loaded,) if isinstance(loaded, ConnectorManifest) else loaded
    manifests = [item for item in items if isinstance(item, ConnectorManifest)]
    if not manifests:
        raise TypeError(f"plugin {entry_point.name!r} declares no ConnectorManifest")
    return manifests


def plugin_manifests(
    environ: Mapping[str, str] | None = None,
    discovered: Iterable[EntryPoint] | None = None,
) -> tuple[ConnectorManifest, ...]:
    """Manifests of installed plugins, enabled only where the allow-list names them.

    A plugin that fails to load is skipped and logged; it never takes the catalogue down.
    """

    allowed = enabled_plugin_names(environ)
    points = discovered if discovered is not None else entry_points(group=ENTRY_POINT_GROUP)
    manifests: list[ConnectorManifest] = []
    for entry_point in points:
        try:
            declared = _declared(entry_point)
        except Exception:  # noqa: BLE001 - a broken plugin must not break the catalogue
            _LOGGER.warning("connector plugin %s could not be loaded", entry_point.name)
            continue
        for manifest in declared:
            enabled = entry_point.name in allowed
            operations = (
                manifest.operations
                if enabled
                else MappingProxyType({**manifest.operations, **_DISABLED_OPERATIONS})
            )
            manifests.append(replace(manifest, plugin=entry_point.name, operations=operations))
    return tuple(manifests)


def plugin_enabled(manifest: ConnectorManifest, environ: Mapping[str, str] | None = None) -> bool:
    return manifest.plugin is not None and manifest.plugin in enabled_plugin_names(environ)
