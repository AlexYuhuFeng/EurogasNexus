# Energy Ontology (CR-14)

## Version

- Executable ontology schema version: `energy-ontology/v1`
  (`src/eurogas_nexus/domain/research/ontology.py`).
- Every research dataset snapshot carries `ontology_version` and is rejected
  if a future reader cannot map the version.

## Canonical identity

- Canonical identifiers are stable semantic keys, not display names:
  `ent:<entity_type>:<CODE>`.
- Examples: `ent:market_hub:NBP`, `ent:interconnector:BBL`.
- Source systems are mapped into canonical entities through versioned,
  point-in-time `source_entity_mappings` rows. A mapping has
  `valid_from_utc`/`valid_to_utc`, `mapping_status`, `confidence`, and
  `evidence`. Ambiguous overlap resolves to "unresolved", never to a silent
  first row.

## Canonical entity classes

`CanonicalEntityType` currently includes:

- Market topology: `market_hub`, `market_area`, `market_venue`,
  `network_node`, `pipeline`, `interconnector`, `infrastructure_asset`,
  `lng_terminal`, `storage_facility`, `production_source`.
- Product/basis: `delivery_product`, `contract_product`, `price_basis`.
- Commercial structure: `portfolio`, `resource`, `commercial_term`,
  `contract`, `route`, `route_segment`, `tariff`, `access_right`.
- Analytics: `source`, `transformation`, `strategy`, `strategy_version`,
  `feature_definition`, `target_definition`, `dataset_spec`,
  `dataset_snapshot`.

## Named concepts

`CORE_CONCEPTS` includes `MarketHub`, `MarketArea`, `MarketVenue`,
`DeliveryProduct`, `PriceObservation`, `NetworkNode`, `Interconnector`,
`Route`, `Strategy`, and `DatasetSnapshot` concepts, with explicit
relationships where the relationship is currently used. Concepts are typed
schemas and controlled vocabularies first; an RDF/graph serialization may be
an adapter in a later milestone, but semantics never live only in an OWL
mirror.

## Boundaries

- The ontology does not introduce execution, order, nomination, or trading
  vocabulary. The research domain remains decision support.
- Hubs are not venues, and venues are not hubs. A source identifier such as
  `ICE_OCM_Sim:NBP` maps to the canonical hub `ent:market_hub:NBP`, while
  venue/product metadata stays on the observation.
- Entity descriptions are stable metadata; identity changes require a new
  canonical id plus a versioned source mapping, not a description edit.

## Seeded catalog

`scripts/research/seed_research_catalog.py` seeds:

- Hubs: TTF, NBP, THE, PEG, ZTP, PSV.
- Interconnectors: BBL, IUK.
- Point-in-time source mappings for `EEX_Sim`, `ICE_OCM_Sim`, `ICIS_Sim`.
