"""Contract tests for the machine-readable GRM/SAREF OWL ontology."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "docs" / "ontology" / "eurogas-nexus-grm.ttl"

GRM_ROLES = {
    "AllocationResponsible",
    "AreaCoordinator",
    "BalanceResponsibleParty",
    "BalancingEnergyResponsible",
    "CapacityPlatformResponsible",
    "CapacityResponsibleParty",
    "ClearingResponsible",
    "DistributionSystemOperator",
    "EnergyTradingPlatformResponsible",
    "FinalCustomer",
    "LngSystemOperator",
    "MarketInformationAggregator",
    "MeterOperator",
    "MeteredDataResponsible",
    "ProductionFacilityOperator",
    "ReconciliationResponsible",
    "StorageSystemOperator",
    "Supplier",
    "SystemOperator",
    "Trader",
    "TransmissionSystemOperator",
    "WeatherDataProvider",
}

GRM_PROCESSES = {
    "CapacityAllocationProcess",
    "ExchangeGasTradingProcess",
    "OtcGasTradingProcess",
    "NominationMatchingProcess",
    "MeteringProcess",
    "AllocationProcess",
    "BalancingProcess",
    "SettlementProcess",
    "RemitTransparencyProcess",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_grm_owl_file_exists_with_declared_namespace_and_version() -> None:
    text = _read(ONTOLOGY)

    assert "@prefix : <https://eurogas-nexus.eu/ontology/grm#> ." in text
    assert "<https://eurogas-nexus.eu/ontology/grm> a owl:Ontology" in text
    assert 'owl:versionInfo "0.5.0"' in text


def test_grm_owl_imports_saref_core_and_aligns_gas_commodity() -> None:
    text = _read(ONTOLOGY)

    assert "@prefix saref: <https://saref.etsi.org/core/> ." in text
    assert "owl:imports <https://saref.etsi.org/core/> ." in text
    assert "dcterms:source <https://saref.etsi.org/core/Commodity>" in text
    assert ":GasCommodity a owl:Class ;" in text
    assert (
        "rdfs:subClassOf saref:EnergyCommodity , saref:NaturalResourceCommodity"
        in text
    )
    assert ":GasMarketServiceCommodity a owl:Class ;" in text
    assert "rdfs:subClassOf saref:Commodity ;" in text
    assert text.count("rdfs:subClassOf :GasMarketServiceCommodity ;") == 3
    # SAREF core saref:Service is a network-exposed function, not a marketable
    # energy-market service; commodity services must stay in saref:Commodity.
    assert "saref:Service" not in text


def test_grm_owl_contains_complete_role_and_process_inventory() -> None:
    text = _read(ONTOLOGY)

    for role in GRM_ROLES:
        assert f":{role} a owl:Class ;" in text

    assert text.count("rdfs:subClassOf :GasMarketRole ;") == len(GRM_ROLES)

    for process in GRM_PROCESSES:
        assert f":{process} a owl:Class ;" in text

    assert text.count("rdfs:subClassOf :GasBusinessProcess ;") == len(GRM_PROCESSES)


def test_grm_owl_exposes_interaction_properties_and_decision_support_boundary() -> None:
    text = _read(ONTOLOGY)

    for prop in (
        "providesValidatedMeteredData",
        "submitsBidsOrOffers",
        "nominatesConcludedTrades",
        "purchasesCapacityFrom",
        "offersAvailableCapacity",
        "commissionsBalancingEnergy",
        "suppliesGasTo",
    ):
        assert f":{prop} a owl:ObjectProperty ;" in text

    assert ":DecisionSupportOutput a owl:Class ;" in text
    assert "rdfs:subClassOf saref:Commodity ;" in text
    assert ":hasHumanReviewRequirement a owl:DatatypeProperty ;" in text
    assert "rdfs:range xsd:boolean ." in text
    assert "never an order, nomination submission, or settlement instruction" in text


def test_grm_owl_contains_no_execution_action_terms() -> None:
    text = _read(ONTOLOGY)

    forbidden = (
        ":ExecutionInstruction",
        ":SubmitOrder",
        ":ExecuteTrade",
        ":AutoTrade",
        ":SubmitNomination",
        ":SendSettlementInstruction",
        ":StraightThroughProcessing",
    )
    for term in forbidden:
        assert term not in text


def test_grm_owl_mandarin_companion_matches_english_surface() -> None:
    en = _read(ROOT / "docs" / "ontology" / "OWL_GAS_ROLE_MODEL.md")
    cn = _read(ROOT / "docs" / "ontology" / "OWL_GAS_ROLE_MODEL-CN.md")

    for marker in (
        "eurogas-nexus-grm.ttl",
        "https://eurogas-nexus.eu/ontology/grm#",
        "https://saref.etsi.org/core/Commodity",
        "AllocationResponsible",
        "TransmissionSystemOperator",
        "DecisionSupportOutput",
    ):
        assert marker in en
        assert marker in cn

    assert "决策支持" in cn
    assert "\ufffd" not in cn
