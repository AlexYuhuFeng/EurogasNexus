"""UK National Gas NTS route-cost constants."""

from __future__ import annotations

from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    SourceResourceType,
)
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario

UK_NATIONAL_GAS_TSO = "National Gas NTS"
UK_NATIONAL_GAS_MARKET_AREA = "NTS"
UK_EASINGTON_POINT_NAME = "Easington Beach Terminal"
UK_BACTON_GDN_EXIT_POINT_NAME = "Bacton GDN (EA)"
UK_NBP_HUB = "NBP"
UK_ROUTE_COST_SCOPE = "UK_NATIONAL_GAS_NTS_ONLY"
UK_NTS_ENTRY_RESOURCE_TYPES = {
    SourceResourceType.BEACH_DELIVERY,
    SourceResourceType.LNG_REGAS,
    SourceResourceType.PIPELINE_IMPORT,
    SourceResourceType.STORAGE,
    SourceResourceType.CONTRACT_POOL,
}
UK_NTS_SUPPORTED_BUSINESS_MODELS = {
    BusinessModel.VIRTUAL_HUB_SALE,
    BusinessModel.PHYSICAL_DELIVERY,
    BusinessModel.CROSS_BORDER_TRANSFER,
}
NATIONAL_GAS_TARIFF_URL = (
    "https://www.gasgovernance.co.uk/sites/default/files/related-files/2025-07/"
    "Notice%20Of%20Transportation%20Statement%20Oct%2025.pdf"
)


def is_supported_uk_scenario(scenario: RouteCostScenario) -> bool:
    """Return True for generic UK NTS scenarios backed by tariff rows."""

    return (
        bool(scenario.start_point_id)
        and scenario.source_resource_type in UK_NTS_ENTRY_RESOURCE_TYPES
        and scenario.business_model in UK_NTS_SUPPORTED_BUSINESS_MODELS
    )
