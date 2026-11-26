# Which ontology is authoritative for what

Eurogas Nexus has three ontologies. They overlap in vocabulary, so a reader has to know which
one decides a question. This page states it, and traces one real identifier through all three
to an API response. The trace runs as a test:
[`tests/contract/test_ontology_worked_example.py`](../../tests/contract/test_ontology_worked_example.py).

## The three ontologies

| Ontology | Where | Authoritative for | Not authoritative for |
|---|---|---|---|
| **Executable domain ontology** | `src/eurogas_nexus/domain/ontology/` (`vocabulary.py`, `markets.py`, `quantity.py`, `currency.py`, `timebase.py`, `identity.py`, `source_identity.py`, `boundary.py`, `semantic_kernel.py`) with the gas-day calendar in `domain/market/gas_day.py` | Every meaning the product computes with: hub and market codes and aliases, units and conversions (the unit authority, `tests/unit/test_unit_authority.py`), currencies and quote units, gas days and periods (the gas-day authority, `tests/unit/test_gas_day_authority.py`), controlled vocabularies, which text names which hub (`resolve_hub`), which provider identifier names which entity (`resolve_identifier`), and what an importer may accept (`check_boundary`, ONT-03). Versioned by `semantic_kernel.current_ontology_version()`. | Stored instances (PostgreSQL holds them) and display wording (the glossary). |
| **GRM OWL model** | `docs/ontology/eurogas-nexus-grm.ttl`, explained in [OWL_GAS_ROLE_MODEL.md](OWL_GAS_ROLE_MODEL.md) | The externally checkable rendering of the EASEE-gas Harmonised Gas Role Model (roles, processes, interactions) aligned with SAREF, for exchange with tools outside the product. | Nothing the product computes. It is generated from `vocabulary.py` by `domain/ontology/grm_turtle.py`; `tests/contract/test_ontology_grm_parity.py` fails if the two differ. When they disagree, the vocabulary wins and the Turtle is regenerated. |
| **Research energy ontology** | `src/eurogas_nexus/domain/research/ontology.py` (`energy-ontology/v1`), the `canonical_entities` and `source_entity_mappings` tables, [ENERGY_ONTOLOGY.md](../research/ENERGY_ONTOLOGY.md) | Canonical entity ids (`ent:<type>:<code>`), the point-in-time mapping of a source's identifier to them (`source_entity_mappings`, valid from/to), and the `ontology_version` every dataset snapshot carries. | Units, hubs, periods: a dataset series takes those from the executable ontology. |

[europe-natural-gas.md](europe-natural-gas.md) is the domain architecture these were built from
(a design reference, not code); [the glossary](../architecture/TERMINOLOGY.md) is display.

**Rules.**

1. A computed meaning has one home: the executable ontology. Any other module that needs a
   hub, a unit, a gas day or a provider identity calls it; it does not keep its own table
   or guess (no first word of a product, no substring of a point name, no default hub).
2. Identity is resolved once, at the boundary: provider keys at ingest and hubs in contracts
   go through `application/identity_resolution.py`, which reads `source_entity_mappings`
   and the built-in identities in `domain/ontology/source_identity.py`. What does not
   resolve is quarantined and listed on the Sources page (`unresolved_identifiers`), never
   mapped by a heuristic.
3. Values cross the boundary checked: every operator file importer and the contract save
   call `check_boundary` (unit, hub, product, period) and report a refusal with a reason
   code (`BoundaryReason`).
4. The OWL file follows the code, never the reverse.

## Worked example: ENTSOG point ITP-00106

Zeebrugge ZPT (Zeepipe landing, Fluxys Belgium) on gas day 10 November 2026. Each row is a
step the test executes; the identifier and the unit are asserted at every hop.

| Hop | Code that does it | Identifier | Unit and value |
|---|---|---|---|
| 1. Provider record | ENTSOG `operationaldatas`; `ingestion/entsog_native_observations.py` | `pointKey` ITP-00106, `operatorKey` BE-TSO-0001, direction entry | `"423450000"` kWh/d as published (a numeric string, kept exactly); period 06:00 CET to 06:00 CET = 05:00 to 05:00 UTC (gas-day authority) |
| 2. Canonical id | `identity_resolution.load_resolver(...).resolve("src-entsog", "entsog_point", "ITP-00106")`, mapping written by the ENTSOG reference ingest | `ent:point:ITP-00106` (basis `mapping`); operator `ent:operator:BE-TSO-0001` | unchanged |
| 3. Stored observation | `flow_observations` (native row, `native_rate_json`) | `point_id` ITP-00106, `metadata_json.operatorKey` BE-TSO-0001 | `original_value` 423,450,000 `original_unit` kWh/d; `flow_mcm_d` NULL (no volume is invented from energy) |
| 4. Feature input | `research_data._fundamental_evidence` (one operator per point and day, closed days only) | series `flow.gwh_d.ITP-00106.entry`, entity `ent:point:ITP-00106` | 423.45 GWh/d, through `quantity.convert(kWh -> GWh)` |
| 5. Dataset snapshot | `domain/research/datasets.build_dataset` via `POST /api/research/datasets` | feature `ZPT_ENTRY_GWH_D`, content-addressed `dataset_snapshot_id`, `ontology_version` `energy-ontology/v1` | 423.45 GWh/d; `source_refs` `entsog-operationaldatas` |
| 6. API response | `GET /api/research/datasets/{id}` | the same snapshot id; `trusted_source_ids` `src-entsog`; ENTSOG attribution | as stored in the snapshot |

## Known inconsistencies (recorded, not yet changed)

- Dataset entity ids use types the research ontology does not list: `ent:point:`,
  `ent:storage_site:`, `ent:bidding_zone:` (its enum has `network_node`,
  `storage_facility`, `market_area`). The resolver issues the ids the datasets already
  carry, so no stored snapshot changes; aligning the enum is a versioned change
  (`energy-ontology/v2`).
- `ent:storage_site:<CC>` and `ent:lng_terminal:<CC>` name GIE **country aggregates**, not
  sites.
- **Decided 2026-11-15 (owner):** `ETF` is the Danish Exchange Transfer Facility (exchange
  trades, EEX, formerly Gaspoint Nordic: alias `GASPOINT`), never an alias of TTF (Title
  Transfer Facility, NL). `GTF` is the Danish Gas Transfer Facility for bilateral OTC
  transfers (ENTSOG VTP-00001 "GTF (Bilateral Trading Point)"); ETF and GTF are separate
  markets in `markets.py`, separate glossary terms (`hub-etf`, `hub-gtf`) and separate intake
  names, and are not merged. Both are DK, EUR/MWh, MW, on the European gas day: an
  assumption for ETF's quotation not checked against a licensed feed; GTF has no price
  source, so a GTF position is unvalued rather than marked at ETF. A guard test refuses any
  alias that names another registered market. `scripts/ops/audit_danish_hub_references.py`
  lists stored rows naming ETF/GTF/Gaspoint with their hub before and after (read-only; it
  corrects a stored hub column only with `--commit`): 0 rows in the demo store and in the
  live store on 2026-11-15.
- **Decided 2026-11-26 (owner), superseding the ETF/GTF split above:** the Danish hub is
  one hub with one identity, processed like every other hub. ETF (the EEX product name) and
  GTF (Energinet's and the OTC name, ENTSOG VTP-00001) name the same virtual trading point of
  the joint DK/SE balancing zone. `markets.py` codes it `ETF` with aliases `GTF` and
  `GASPOINT`, and `venue_names` records which venue says which (`venue_name("ETF", "OTC")`
  is `GTF`). Every intake resolves a hub through the registry (`canonical_hub`;
  `licensed_quote_import.intake_hub` for the tick feed and the screen import, whose accepted
  hubs are now the registry's active European gas hubs rather than a hand list), so a tick, a
  close, a contract, the reference network's trading point and the glossary all name `ETF`.
  The same rule moved `VTP` (stored as its own hub by the screen import) to `CEGH` and added
  `TRF` (Trading Region France, the merged PEG Nord/TRS zone since 2018) as an alias of PEG.
  Migration `0091_hub_one_identity` moves stored `GTF`/`VTP` hub codes to the registry code
  and deletes the demo's second, invented GTF series. One quote key per product on every
  intake: `products.board_tenor` (`jan-27`, `month-ahead`, `bom`), which the demo board now
  uses too (it wrote `Jan-27`).
