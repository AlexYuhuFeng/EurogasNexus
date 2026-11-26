"""Financial-institution connector manifest (src-bank-rates): the firm's own bank's FX and
interest rates, configured per institution (TAR-2, ADR Decision 38).

A firm that converts or finances through its clearing or account bank pays that bank's rates,
not the ECB's; the source-precedence resolver (``domain/pricing/source_precedence.py``) puts
them first. Each institution is configured in the organisation setting
``financial_institutions`` (``domain/pricing/financial_institutions.py``). Rates arrive by the
firm's own export, imported through the ``bank.fx_rates.v1`` and ``bank.interest_rates.v1``
contracts (``scripts/ops/import_contract_file.py``), or are entered by hand as a file of the
same shape. A live feed from a bank's website or API needs the firm's own agreement with that
bank and the firm's own credentials: none is connected in this build, and the platform holds
no bank credential.
"""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.dataops.contracts import AccessMode, FreshnessPolicy, SourceClass

MANIFEST = ConnectorManifest(
    source_id="src-bank-rates",
    system="BANK",
    category="fx",
    datasets=("bank-fx-rates", "bank-interest-rates"),
    description=(
        "The firm's own clearing or account bank's FX and interest rates, one institution per "
        "configured entry, imported from the firm's export (import contracts bank.fx_rates.v1 "
        "and bank.interest_rates.v1) or entered by hand. Used before published reference "
        "rates and the ECB. A live bank feed needs the firm's own agreement and credentials."
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
        "freshness_policy": FreshnessPolicy(1440, 2880, 4320),
    },
    credentials=(
        ProviderCredentialSpec(
            "BANK",
            "Financial institution (the firm's own bank)",
            implemented=False,
            note=(
                "A live feed needs the firm's own agreement with the bank and its own "
                "credentials; none is connected in this build. Use the file import."
            ),
        ),
    ),
)
