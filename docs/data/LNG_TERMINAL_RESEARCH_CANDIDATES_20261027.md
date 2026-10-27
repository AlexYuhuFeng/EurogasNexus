# LNG terminal reference research candidates — 2026-10-27

These are operator-publication candidates for the versioned reference contract.
They are not automatic economic inputs, booked rights or a declaration of current
technical availability. Effective dates are not established by these undated
pages. Capture date and content hash identify the inspected publication, not its
effective interval. Review and resolve applicability before promoting a fact.

All five pages below were independently retrieved with HTTP 200; original bytes
and the UTC retrieval manifest are retained in the ignored local evidence folder
`.local-runtime/delivery-20261027/terminal-sources/`. Do not put full operator
documents in customer artifacts without appropriate rights.

| Facility / fact | Exact published value and unit | Interpretation and applicability | Official source / short quotation |
| --- | --- | --- | --- |
| Gate vessel unloading maximum | `12.500 m3/h of LNG` | Publication's thousands notation; liquid LNG volume. Do not substitute actual/normal gas volume or energy throughput. Not a guaranteed average discharge rate. | [Operational data](https://www.gateterminal.com/en/commercial/operational-data/): “Max. Vessel discharge rate is 12.500 m3/h of LNG” |
| Gate minimum sendout | `139.000 m3(n)/h` | Normal-gas volumetric rate, conditional on service terms; publication mentions additional lower-flow services. Not the unloading limit and not MWh/h. | [Operational data](https://www.gateterminal.com/en/commercial/operational-data/) |
| Gate evaporation statement | approximately `0.07% of the tank capacity per day` | Denominator is tank capacity. This is an insulation/evaporation description, not an evidenced cargo loss, retained-fuel percentage, invoice deduction or irrecoverable energy loss. Do not apply it to cargo energy. | [Operator FAQ](https://www.gateterminal.com/en/gate-terminal/faq/): “approximately 0.07% of the tank capacity per day” |
| Dunkerque vessel unloading maximum | `14,000 m³ per hour` | Jetty unloading in LNG vessel context. Keep separate from the page's reloading limit and gas sendout. | [Operator infrastructure](https://www.fluxys.com/en/about-us/dunkerque-lng/infrastructure): “maximum flow rate of 14,000 m³ per hour” |
| Grain regas equipment capacity | `645 GWh/d` | Equipment subsection. The same page also reports approximately `654 GWh/d` in its primary-capacity subsection. Preserve both as distinct claims; resolve basis/version before selecting a maximum. No silent overwrite or averaging. | [Operational information](https://www.grainlng.com/operational-information): “capable of regasifying 645 GWh/d”; later “circa 654 GWh/d regasification capacity” |
| South Hook vessel discharge duration | up to `24 hours` | Descriptive vessel discharge duration, not a guaranteed slot duration, constant unloading rate or universally applicable turnaround. Mooring and other operations are not inferred. | [Operator operations](https://www.southhooklng.com/operations/what-we-do/): “discharge process which can take up to 24 hours” |

## Captured source versions

| Source | SHA-256 of downloaded bytes |
| --- | --- |
| Gate operational data | `222f6d89f422fd8f33fbd4959461fa4b49959be744d2850b55dfb36fd860f205` |
| Gate FAQ | `e7bcff83d859b7f9025450d11ea6e6f48c58f33abea78abcc5ecc657f681752f` |
| Grain operational information | `9243ff6f925f5ae2e5a3dcda66d309ec6a6cd7fc3c83efe5c43614e4b64dfc5e` |
| Dunkerque infrastructure | `aca9b21f8bb8cb705481e2016e910f2ceea411000fa3bf61adb16832e64a82ad` |
| South Hook operations | `792b29e57c4f306c177ce7f4796171e9f4341085b2107249a8fe18c669bfa22c` |

Hashes are byte-sensitive: navigation, dynamic slots or markup changes can trigger
a candidate without changing the technical fact. A changed hash requires review;
it never automatically replaces a reviewed model input. Preserve the old bytes,
source section, original unit, quotation, retrieval time and applicability.

## Remaining research and integration

- Fuel retention, invoiced gas-in-kind, unrecovered physical loss and BOG handling
  remain separate missing facts. No zero or generic industry percentage is supplied.
- Retrieve dated operator contracts/tariff schedules for the exact service and
  agreement; resolve Grain's two capacity figures and each fact's effective scope.
- Complete the versioned fact schema and offline comparison tooling, then expose
  reviewed informational facts and explicit scenario adoption through existing LNG
  workflows. Missing physical rights, slot/storage availability and network entry
  capacity remain independent readiness blockers.
- Extend coverage to the terminals actually selected by the European desk. These
  four facilities do not establish complete European terminal coverage.
