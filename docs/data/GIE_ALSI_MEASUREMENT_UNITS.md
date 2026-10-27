# GIE ALSI measurement units and the energy seam — 2026-10-27

Status: reviewed source-unit note for the ALSI ingestion normalizer. This is a
documentation of the reviewed primary contract and the implemented fail-closed
seam; it is not a claim that GIE's current API contract, entitlements or a later
document version have been fully retrieved, certified or proven.

## Primary source reviewed

- GIE Transparency Platform API documentation **v007, 4 October 2022**:
  <https://www.gie.eu/transparency-platform/GIE_API_documentation_v007.pdf>

That manual describes the ALSI fields used here as:

| Field | Documented meaning and unit |
| --- | --- |
| `inventory` | LNG inventory volume in **10^3 m3 LNG** |
| `dtmi` | **Declared Total Maximum Inventory**, LNG volume in **10^3 m3 LNG** |
| `sendOut` | Send-out rate in **GWh/d** |

`DTMI` means Declared Total Maximum Inventory. It is **not** "days to monitor",
days of cover, a send-out duration or a forward-looking availability measure. The
reviewed contract contains no calorific value, so no volume-to-energy conversion
can be justified from it.

## Repository fixture shape

Newer repository synthetic fixtures also use objects of the form
`{"lng": <volume>, "gwh": <energy>}` for `inventory` and `dtmi`. That nesting is a
repository fixture convention; it is not presented here as proof of the current
official provider schema. The two members are kept distinct:

- `lng` is an LNG volume and is never converted to energy.
- `gwh` is an explicit energy measurement and is the only member converted.

## Implemented ingestion contract

`gie_lng_observations_from_json` in
`src/eurogas_nexus/ingestion/public_sources.py` applies the following rules:

| Source value | Canonical field | Result |
| --- | --- | --- |
| `inventory` object with a valid explicit `gwh` | `inventory_twh` | `gwh / 1000` |
| `dtmi` object with a valid explicit `gwh` | `dtmi_twh` | `gwh / 1000` |
| `sendOut` scalar | `send_out_twh_d` | `value / 1000` (GWh/d to TWh/d) |
| `sendOut` object with a valid explicit `gwh` | `send_out_twh_d` | `gwh / 1000` |
| Scalar `inventory` or `dtmi` | energy field | `None`; raw value retained |
| `inventory`/`dtmi` object with only `lng` | energy field | `None`; raw volume retained |
| Any explicit `gwh` that is boolean, non-finite or malformed | energy field | `None`; typed warning retained |
| Missing measurement | energy field | `None` |

The normalizer does not infer a calorific factor, does not treat a raw LNG volume
as GWh, and does not substitute zero for an unknown energy value. An explicit
`gwh` of `0` is a real measurement and becomes `0.0` TWh; it is not confused with
missing data.

### Raw provenance and unit warnings

Each ALSI row carries bounded provenance under
`metadata_json["measurement_provenance"]` for `inventory`, `dtmi` and `send_out`:

- `raw`: the scalar value, or only the `lng`/`gwh` members of a nested object,
  bounded and JSON-safe.
- `shape`: `scalar`, `nested`, `unsupported` or `absent`.
- `energy_basis`: for example `explicit_gwh`, `literal_lng_volume`,
  `scalar_volume_not_energy` or `malformed_explicit_gwh`.

`metadata_json["unit_warnings"]` lists the explicit reasons an energy field was
left missing, such as `inventory_scalar_volume_not_converted` or
`dtmi_explicit_gwh_invalid`. A valid explicit `gwh` produces no unit warning, even
when a sibling `lng` member is also preserved. `metadata_json["unit_contract"]`
records that the reviewed reference is GIE ALSI API v007 (2022-10-04) and that
later versions are unverified.

The existing CAM calendar and `updatedAt` provenance behavior is unchanged. A
bare `updatedAt` still uses the live receipt only when supplied, with
`availability_basis="response_receipt"` and
`provider_updated_at_zone="unproven"`; an offset stamp remains trusted.

AGSI is deliberately not changed by this ALSI seam. Its existing scalar
`injection`/`withdrawal` conversions and inventory handling remain as before.

## Known uncertainty and remediation boundary

- The later **v013** publication was **not retrieved** for this task. This note
  must not be cited as proof of the latest GIE contract, current field nesting,
  current units or a certification of the live API.
- The reviewed v007 manual is the primary source for `inventory`/`dtmi` volume in
  10^3 m3 LNG and `sendOut` in GWh/d. Later-version changes are unknown here.
- The nested `{"lng": ..., "gwh": ...}` form is evidenced by repository synthetic
  fixtures, not by an official current ALSI schema in this review.
- Existing stored rows are not migrated, overwritten or backfilled by this
  change. A row that previously accepted a scalar inventory/DTMI as GWh needs a
  separate remediation policy and review; this note does not authorize rewriting
  existing data.
- Unknown energy remains `None` in the canonical row. Consumers must treat that
  as missing, not as zero, and may inspect the bounded raw provenance and unit
  warnings for reconciliation.
