"""Société Générale bank-rate connector manifest (src-bank-socgen, TAR-2, ADR Decision 38).

The firm's own bank's FX fixings and interest rates over the bank's API, for the institution
key ``SOCGEN`` in the organisation setting ``financial_institutions``
(``ingestion/connectors/socgen.py``, written by ``application/bank_feeds.py``). The rows are
``BANK:SOCGEN`` rows of the ``bank.fx_rates.v1`` / ``bank.interest_rates.v1`` contracts, the
``contracted_bank`` tier of the source-precedence resolver.

Off by default (``enabled_default`` false): the scheduler runs it only once an administrator
enables it, and it fetches only with the firm's agreement recorded, the deployment's endpoint
configuration and the firm's own credential. No address of the bank is held here; the
schedule time below is an assumption to confirm with the bank.
"""

from __future__ import annotations

from eurogas_nexus.domain.connectors.manifest import ConnectorManifest, ProviderCredentialSpec
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    FreshnessPolicy,
    RateLimitPolicy,
    RetryPolicy,
    ScheduleType,
    SourceCalendar,
    SourceClass,
    SourceScheduleSpec,
)

MANIFEST = ConnectorManifest(
    source_id="src-bank-socgen",
    system="BANK:SOCGEN",
    category="fx",
    datasets=("bank-fx-rates", "bank-interest-rates"),
    description=(
        "Societe Generale (the firm's own bank): FX fixings and interest rates over the bank's "
        "API, stored as BANK:SOCGEN rows of the bank.fx_rates.v1 and bank.interest_rates.v1 "
        "contracts and used before published reference rates and the ECB. Fetches only with "
        "the firm's agreement recorded, its endpoint configuration and its own credential."
    ),
    entitled=False,
    freshness_minutes=1440,
    integration="api",
    licensed_import=True,
    operations={
        "source_class": SourceClass.PUBLIC,
        "access_mode": AccessMode.KEYED_HTTP,
        "schedulable": True,
        "enabled_default": False,
        # Once a business day in the evening, Paris time: an assumption about when the bank
        # publishes its fixings, to confirm with the bank.
        "schedule": SourceScheduleSpec(
            schedule_type=ScheduleType.DAILY, daily_at="18:30", timezone="Europe/Paris"
        ),
        "calendar": SourceCalendar.WEEKDAYS_ONLY,
        "freshness_policy": FreshnessPolicy(1440 * 2, 1440 * 4, 1440 * 6),
        "retry_policy": RetryPolicy(3, 300.0, 3600.0),
        "rate_limit_policy": RateLimitPolicy(4, 3600.0, 60.0, 1),
        "adapter_version": "bank-rate-connector/1",
    },
    credentials=(
        ProviderCredentialSpec(
            "SOCGEN",
            "Societe Generale API (the firm's own credential)",
            ("EUROGAS_NEXUS_SOCGEN_API_SECRET",),
            file_env="EUROGAS_NEXUS_SOCGEN_API_SECRET_FILE",
            note=(
                "The firm's own client secret or API key from its agreement with the bank. "
                "Also needs agreement_recorded on SOCGEN in financial_institutions and the "
                "endpoint configuration file (EUROGAS_NEXUS_SOCGEN_API_CONFIG_FILE)."
            ),
        ),
    ),
)
