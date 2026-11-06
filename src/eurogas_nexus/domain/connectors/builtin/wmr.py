"""WM/Reuters connector manifest (src-wmr): licensed FX fixes by file import (#33)."""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest
from eurogas_nexus.domain.dataops.contracts import AccessMode, SourceClass

MANIFEST = ConnectorManifest(
    source_id="src-wmr",
    system="WMR",
    category="fx",
    datasets=("wmr-1600-ldn", "wmr-1100-ldn"),
    description=(
        "WM/Reuters (LSEG) London closing and intraday spot fixes, imported from the "
        "desk's licensed export (scripts/ops/import_fx_fixings.py --source WMR). The "
        "fix most LNG contracts name; ECB reference rates are not a substitute."
    ),
    entitled=False,
    freshness_minutes=1440,
    integration="file_import",
    licensed_import=True,
    # Licensed FX fixes arrive only through the operator's import (#33).
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.FILE_UPLOAD,
        "schedulable": False,
        "enabled_default": False,
    },
)
