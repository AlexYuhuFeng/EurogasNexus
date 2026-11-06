"""Connector manifests: one declaration per provider, registries derived from them (C1, C2)."""

from __future__ import annotations

import dataclasses
import enum
import json
from importlib.metadata import EntryPoint
from pathlib import Path
from types import MappingProxyType

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.connectors.plugins import plugin_manifests
from eurogas_nexus.domain.connectors.registry import BUILTIN_MODULES, builtin_manifests
from eurogas_nexus.domain.dataops.contracts import AccessMode, SourceClass
from eurogas_nexus.domain.dataops.registry import source_definitions
from eurogas_nexus.domain.ingestion.source_registry import registered_sources
from eurogas_nexus.security.provider_credentials import (
    PROVIDER_CREDENTIAL_ENV_VARS,
    PROVIDER_CREDENTIAL_SPECS,
)

SNAPSHOT = Path(__file__).parents[1] / "fixtures" / "connectors" / "registry_snapshot.json"


def _plain(value):
    if dataclasses.is_dataclass(value):
        return {key: _plain(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def test_the_derived_registries_are_unchanged_from_before_the_manifests() -> None:
    """Moving every provider into one manifest changed no registry row or policy."""
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    now = json.loads(
        json.dumps(
            {
                "registered_sources": registered_sources(),
                "source_definitions": [_plain(item) for item in source_definitions()],
                "provider_credential_specs": [_plain(s) for s in PROVIDER_CREDENTIAL_SPECS],
                "provider_credential_env_vars": list(PROVIDER_CREDENTIAL_ENV_VARS),
            },
            sort_keys=True,
            default=str,
        )
    )
    for key in snapshot:
        assert now[key] == snapshot[key], key


def test_one_module_per_provider_and_unique_ids() -> None:
    manifests = builtin_manifests()
    assert len(manifests) == len(BUILTIN_MODULES)
    assert len({manifest.source_id for manifest in manifests}) == len(manifests)


def test_every_credential_variable_is_read_through_the_contract_tuple() -> None:
    declared = {
        name
        for spec in PROVIDER_CREDENTIAL_SPECS
        for name in (*spec.env_vars, *((spec.file_env,) if spec.file_env else ()))
    }
    assert declared == set(PROVIDER_CREDENTIAL_ENV_VARS)


def _plugin_point(name: str, manifest: ConnectorManifest) -> EntryPoint:
    point = EntryPoint(name=name, value="tests.unit:unused", group="eurogas_nexus.connectors")

    class _Loaded(EntryPoint):
        def load(self):  # type: ignore[override]
            return manifest

    return _Loaded(name=point.name, value=point.value, group=point.group)


_PLUGIN = ConnectorManifest(
    source_id="src-acme-cargo",
    system="ACME",
    category="infrastructure",
    datasets=("cargo-tracks",),
    description="Example plugin connector.",
    entitled=True,
    freshness_minutes=60,
    operations=MappingProxyType(
        {
            "source_class": SourceClass.LICENSED,
            "access_mode": AccessMode.KEYED_HTTP,
            "schedulable": True,
            "enabled_default": True,
        }
    ),
)


def test_an_installed_plugin_is_available_but_never_runs_until_enabled() -> None:
    points = [_plugin_point("acme_cargo", _PLUGIN)]
    off = plugin_manifests(environ={}, discovered=points)
    assert [manifest.source_id for manifest in off] == ["src-acme-cargo"]
    assert off[0].plugin == "acme_cargo"
    assert off[0].operations["schedulable"] is False
    assert off[0].operations["enabled_default"] is False

    on = plugin_manifests(
        environ={"EUROGAS_NEXUS_CONNECTOR_PLUGINS": "other, acme_cargo"}, discovered=points
    )
    assert on[0].operations["schedulable"] is True


def test_a_broken_plugin_is_skipped_not_fatal() -> None:
    class _Broken(EntryPoint):
        def load(self):  # type: ignore[override]
            raise ImportError("missing dependency")

    broken = _Broken(name="broken", value="x:y", group="eurogas_nexus.connectors")
    assert plugin_manifests(environ={}, discovered=[broken]) == ()
