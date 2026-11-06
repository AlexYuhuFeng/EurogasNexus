"""REMIT connector manifest (src-remit-umm)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import AccessMode, SourceClass

MANIFEST = ConnectorManifest(
    source_id="src-remit-umm",
    system="REMIT",
    category="infrastructure",
    datasets=("gas-umm-outages",),
    description="REMIT urgent market messages: planned and unplanned outages of gas "
    "production, storage, LNG and transmission, imported from the desk's "
    "inside-information platform export (scripts/ops/import_remit_umm.py).",
    entitled=False,
    freshness_minutes=60,
    integration="file_import",
    # Operator file import (scripts/ops/import_remit_umm.py); nothing for the scheduler to run.
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.FILE_UPLOAD,
        "schedulable": False,
        "enabled_default": False,
        "adapter_version": "remit-umm-acer-fields-v1",
    },
)
