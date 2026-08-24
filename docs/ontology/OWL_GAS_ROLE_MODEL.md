# Eurogas Nexus OWL Gas Role Model

> Machine-readable companion: [`eurogas-nexus-grm.ttl`](eurogas-nexus-grm.ttl)
> Mandarin companion: [OWL_GAS_ROLE_MODEL-CN.md](OWL_GAS_ROLE_MODEL-CN.md)

## 1. Purpose and status

This document explains the OWL/Turtle ontology delivered as
`docs/ontology/eurogas-nexus-grm.ttl`. It is the semantic, machine-readable
rendering of the **EASEE-gas Harmonised Gas Role Model (GRM), business-process
view**, aligned with the **SAREF core Commodity pattern**.

| Property | Value |
| --- | --- |
| Ontology IRI | `https://eurogas-nexus.eu/ontology/grm` |
| Namespace prefix | `https://eurogas-nexus.eu/ontology/grm#` |
| Format | OWL 2 in Turtle syntax |
| Version | `0.5.0` |
| Reference source | `Harmonised_GRM_Document_FINAL_2018-05-30.pdf` |
| SAREF reference | `https://saref.etsi.org/core/Commodity` |
| Product status | Decision-support model only, non-executable |

The file is normative for semantic mapping. The typed implementation ontology
in `src/eurogas_nexus/domain/ontology/` remains the executable authority inside
the product; this OWL file makes the GRM and SAREF alignment externally
checkable and tool-neutral.

## 2. Namespace and import

```turtle
@prefix :      <https://eurogas-nexus.eu/ontology/grm#> .
@prefix saref: <https://saref.etsi.org/core/> .

<https://eurogas-nexus.eu/ontology/grm> a owl:Ontology ;
    owl:imports <https://saref.etsi.org/core/> .
```

The ontology imports the ETSI SAREF core ontology. Consumers that cannot fetch
remote imports should load SAREF core into the same RDF graph first, then parse
the local Turtle file.

## 3. Commodity alignment

The GRM is a role and process model, so commodities enter through the SAREF
Commodity pattern:

| Local class | SAREF alignment | Meaning |
| --- | --- | --- |
| `:GasCommodity` | `saref:EnergyCommodity` and `saref:NaturalResourceCommodity` | Pipeline gas traded and transported in the European market |
| `:LngCommodity` | subclass of `:GasCommodity` | Liquefied natural gas handled by an LNG system operator |
| `:GasMarketServiceCommodity` | subclass of `saref:Commodity` | Marketable storage, capacity, and balancing services |
| `:StorageServiceCommodity` | subclass of `:GasMarketServiceCommodity` | Storage service provided by a storage system operator |
| `:CapacityCommodity` | subclass of `:GasMarketServiceCommodity` | Entry/exit capacity offered through capacity allocation |
| `:BalanceServiceCommodity` | subclass of `:GasMarketServiceCommodity` | Balancing energy procured for system balance |

This mirrors the SAREF example where `ex:Gas` is typed as both
`saref:EnergyCommodity` and `saref:NaturalResourceCommodity`. Storage,
capacity, and balancing energy are deliberately modelled under
`saref:Commodity`, not under SAREF core's `saref:Service`, because in SAREF
core `saref:Service` means a network-exposed device function rather than a
marketable energy-market service.

## 4. GRM role model

The ontology declares `:MarketParty` (a legal or organisational party),
`:GasMarketRole` (an external business-interaction role), and the property
`:playsRole` linking them. One market party may play several roles, exactly as
the GRM states.

The 22 harmonised GRM roles are captured with their GRM descriptions as
`skos:definition`:

`AllocationResponsible`, `AreaCoordinator`, `BalanceResponsibleParty`,
`BalancingEnergyResponsible`, `CapacityPlatformResponsible`,
`CapacityResponsibleParty`, `ClearingResponsible`,
`DistributionSystemOperator`, `EnergyTradingPlatformResponsible`,
`FinalCustomer`, `LngSystemOperator`, `MarketInformationAggregator`,
`MeterOperator`, `MeteredDataResponsible`, `ProductionFacilityOperator`,
`ReconciliationResponsible`, `StorageSystemOperator`, `Supplier`,
`SystemOperator`, `Trader`, `TransmissionSystemOperator`,
`WeatherDataProvider`.

## 5. GRM business-process view

The ontology declares `:GasBusinessProcess` and nine GRM processes:

`CapacityAllocationProcess`, `ExchangeGasTradingProcess`,
`OtcGasTradingProcess`, `NominationMatchingProcess`, `MeteringProcess`,
`AllocationProcess`, `BalancingProcess`, `SettlementProcess`,
`RemitTransparencyProcess`.

Roles participate in processes through `:participatesIn`, and processes may be
linked to the commodities they concern through `:concerns`.

The GRM's interaction arrows are represented as named object properties, for
example `:providesValidatedMeteredData`, `:submitsBidsOrOffers`,
`:nominatesConcludedTrades`, `:purchasesCapacityFrom`,
`:offersAvailableCapacity`, `:commissionsBalancingEnergy`, and
`:suppliesGasTo`.

## 6. Product boundary annotation

Eurogas Nexus is decision-support only. The ontology makes that boundary
explicit:

```turtle
:DecisionSupportOutput a owl:Class ;
    rdfs:subClassOf saref:Commodity .

:hasHumanReviewRequirement a owl:DatatypeProperty ;
    rdfs:domain :DecisionSupportOutput ;
    rdfs:range xsd:boolean .
```

No class or property in this ontology represents order submission, trade
execution, nomination submission, or settlement instructions. Those are
external actions of market parties, not product capabilities.

## 7. Validation

Without adding a runtime dependency to the project, the file can be checked
with any OWL/Turtle parser, for example:

```bash
pip install rdflib
python -c "import rdflib; g=rdflib.Graph(); g.parse('docs/ontology/eurogas-nexus-grm.ttl', format='turtle'); print(len(g))"
```

The repository contract test
`tests/contract/test_grm_owl_ontology.py` additionally enforces the namespace,
the SAREF import, the complete role/process inventory, the decision-support
boundary, and the absence of execution-action terms.
