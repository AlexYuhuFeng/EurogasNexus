"""Public tariffs as versioned publications, their publishers and capacity notices (TAR-1).

``model``        one tariff publication, its identity and content hash, and how a newer
                 publication supersedes an older one (indicative never silently final);
``publishers``   who publishes what, where, how often, and whether it may be reused;
``auction_calendar``  the standard capacity auctions the CAM network code schedules.

Import-safe and DB-free.
"""

from eurogas_nexus.domain.tariffs.auction_calendar import (
    AuctionWindow,
    standard_auctions,
)
from eurogas_nexus.domain.tariffs.model import (
    FINAL,
    INDICATIVE,
    STATUSES,
    ChangeKind,
    TariffSpec,
    VersionDecision,
    decide_version,
)
from eurogas_nexus.domain.tariffs.publishers import (
    PUBLISHERS,
    Publisher,
    publisher,
)

__all__ = [
    "FINAL",
    "INDICATIVE",
    "PUBLISHERS",
    "STATUSES",
    "AuctionWindow",
    "ChangeKind",
    "Publisher",
    "TariffSpec",
    "VersionDecision",
    "decide_version",
    "publisher",
    "standard_auctions",
]
