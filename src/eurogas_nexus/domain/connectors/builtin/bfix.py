"""Bloomberg BFIX connector manifest (src-bfix): licensed FX fixes by file import (#33)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import AccessMode, SourceClass

MANIFEST = ConnectorManifest(
    source_id="src-bfix",
    system="BFIX",
    category="fx",
    datasets=("bfix-1600-ldn",),
    description=(
        "Bloomberg BFIX fixes, imported from the desk's licensed export "
        "(scripts/ops/import_fx_fixings.py --source BFIX)."
    ),
    entitled=False,
    freshness_minutes=1440,
    integration="file_import",
    licensed_import=True,
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.FILE_UPLOAD,
        "schedulable": False,
        "enabled_default": False,
    },
)
