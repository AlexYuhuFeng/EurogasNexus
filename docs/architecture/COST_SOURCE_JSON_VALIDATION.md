# Cost-source JSON validation

## Scope

`src/eurogas_nexus/ingestion/connectors/cost_source.py` contains a generic
machine-readable JSON adapter (`JsonCostObservationConnector`). It maps a
provider feed to `CostObservation` rows for TSO tariffs, LNG slots and related
cost sources.

This note records the validation contract added to that adapter. It does not
declare a provider feed official, approve a source, change entitlement or
certification metadata, or add a database migration.

## Fail-closed record contract

A record is refused unless every required field below is present and valid.
Optional fields are validated when supplied. A JSON `null`, an absent key, an
empty string or a wrong type is never replaced by a default for a required
field.

| Field | Contract |
| --- | --- |
| `observation_id` or `id` | Non-empty string, at most 128 characters. If both keys are supplied they must agree. The adapter never generates an id. |
| `scope_type` | One of `ROUTE`, `POINT`, `LNG_TERMINAL`, `RESOURCE`; normalized to upper case. |
| `scope_id` | Non-empty string, at most 128 characters. |
| `observation_type` | One of the domain `OBSERVATION_TYPES`; normalized to upper case. |
| `value` | Present JSON number, excluding booleans; finite and non-negative. `0` and `0.0` are valid only when actually present. |
| `currency` | Non-empty ISO-4217-shaped three-letter code; normalized to upper case. No default currency is applied. |
| `unit` | A recognized unit/basis from the adapter vocabulary, for example `MWh`, `kWh`, `MMBtu`, `therm`, `m3`, or a `/d`, `/day`, `/h`, `/hr` rate variant. No default unit is applied. |
| `effective_from_utc` | Explicit ISO-8601 timestamp with a real UTC offset. A naive timestamp is refused. |
| `effective_to_utc` | Optional; when present it must be an offset-aware ISO-8601 timestamp and must not precede `effective_from_utc`. `null` means an open-ended window. |
| `source_reference` | Required provenance string, at most 256 characters. It may be a provider reference or URL, but a refusal never repeats it. |
| `created_at_utc` | Optional offset-aware timestamp. When absent, the refresh service stamps the ingestion receipt time. It is not used as the observation's effective time. |
| `source_system` | Optional in the record. If declared, it must match the connector's configured source identity. The connector value is authoritative; a feed cannot override it. |
| `direction`, `capacity_product`, `firmness`, `gas_year`, `document_id`, `superseded_by` | Optional text fields, bounded by their persistence widths. |
| `entitlement_scope` | Optional list or tuple of non-empty strings. |
| `manual_review_required` | Optional boolean; absent or `null` defaults to the safe `true`. A non-boolean value is refused. |
| `status` | Optional text; absent defaults to `ACTIVE`, matching existing domain behavior. |

Booleans are not numbers for `value`: `true` and `false` are refused rather
than converted to `1` and `0`. `NaN`, `Infinity` and `-Infinity` are refused.
Negative values are refused because the domain contract already requires a
non-negative cost observation.

## Envelope and HTTP behavior

The payload must be either:

- a JSON array of records, or
- an object with an `items` array.

An empty array or `{"items": []}` is a successful empty result. A missing or
non-array `items` member, a non-object record, a non-list top-level payload, or
a truthy provider `error` member is a typed refusal. The adapter accepts at most
`COST_SOURCE_MAX_RECORDS` (1000) records per response before parsing any record.

HTTP `200` is parsed. HTTP `204` is an empty success. Any other HTTP status is a
`CostSourceHttpRefusal` and is not converted into an empty observation tuple.
Transport exceptions and malformed JSON are also typed refusals. Consequently,
the refresh service does not report an HTTP or provider failure as a successful
zero-row refresh.

## Batch atomicity

`JsonCostObservationConnector.fetch_cost_observations()` validates the whole
batch and constructs every domain observation before returning. If any record
is invalid, the call raises and returns nothing, so the refresh service never
opens a persistence session for a partially valid batch.

When persistence itself fails, `cost_source_refresh.refresh_cost_source()`
rolls back the session and re-raises. It commits once, only after every row has
been upserted. There is no partial batch commit.

## Refusal type

All parse, transport, HTTP and configuration refusals derive from
`CostSourceRefusal`, a `ValueError`. Each carries:

- `code`: a stable string such as `COST_SOURCE_FIELD_MISSING`,
  `COST_SOURCE_FIELD_INVALID`, `COST_SOURCE_ENUM_INVALID`,
  `COST_SOURCE_VALUE_NOT_FINITE`, `COST_SOURCE_VALUE_NEGATIVE`,
  `COST_SOURCE_UNIT_UNSUPPORTED`, `COST_SOURCE_CURRENCY_INVALID`,
  `COST_SOURCE_TIMESTAMP_INVALID`, `COST_SOURCE_SOURCE_MISSING`,
  `COST_SOURCE_SOURCE_MISMATCH`, `COST_SOURCE_CONFIGURATION_INVALID`,
  `COST_SOURCE_JSON_MALFORMED`,
  `COST_SOURCE_ENVELOPE_INVALID`, `COST_SOURCE_PROVIDER_ERROR`,
  `COST_SOURCE_RECORD_LIMIT_EXCEEDED`, `COST_SOURCE_HTTP_REFUSED` or
  `COST_SOURCE_TRANSPORT_FAILED`;
- `record_index`: the zero-based index inside the records array, or `None` for
  an envelope/HTTP/transport refusal;
- `field`: the failing record field or envelope section, when applicable.

`CostSourceHttpRefusal` additionally carries the numeric `status_code`.

The exception string contains only the code, record index and field. It never
contains the record payload, a provider URL, credentials or a caught
exception's text.

## Compatibility boundary

The valid provider fixture shape remains supported: identifier, route scope,
`TSO_PUBLISHED` observation type, numeric price, `EUR`, `MWh`, and an explicit
effective timestamp. Existing callers still receive a tuple of observations,
and an unconfigured JSON connector still returns an empty tuple without making
a request.

Refused feed shapes must be corrected at the provider/adapter boundary or
handled by an explicit reviewed adapter. They are not to be made to pass by
weakening entitlement, certification, provenance or domain money validation.
