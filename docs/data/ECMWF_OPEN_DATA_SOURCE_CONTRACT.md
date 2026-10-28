# ECMWF Open Data source contract (RFC-0003 Phase A)

Status: implemented Phase A transport and authentic-GRIB decoder contract, 2026-10-28.
This is not production source activation, persistence, scheduler, API/UI exposure, or
evidence of forecast accuracy. No database, migration, registry, API, UI, schema, package
requirement, or requirement file is changed by this phase.

## Reviewed provider identity

Only these keyless, official origins are selectable with the explicit `source` parameter:

| `source` | Fixed origin | Use |
| --- | --- | --- |
| `ecmwf` (default) | `https://data.ecmwf.int/forecasts/` | official directory and GRIB byte ranges |
| `aws` | `https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/` | ECMWF-managed AWS Open Data replica; bucket `ecmwf-forecasts`, region `eu-central-1` |

References: <https://www.ecmwf.int/en/forecasts/datasets/open-data-0>,
<https://data.ecmwf.int/forecasts/>, and
<https://registry.opendata.aws/ecmwf-forecasts/>. Root observed the official
directory with forecast dates 2026-10-24 through 2026-10-27 and the anonymous AWS
XML listing with prefixes from 2023-01-18. Those observations establish access and
layout only; they do not establish usable history or field-level vintage coverage.

The host allowlist is fixed to those two hosts and the selected source's host. There
is no arbitrary-URL, mirror, credential, cookie, client-token, environment-auth, or
proxy-environment path. Redirects are followed manually only when HTTPS, the selected
fixed host, the same path, and the same query survive validation. A cross-origin or
path-changing redirect is refused before its body is read. Provider error bodies are
never read or copied into exceptions.

## Phase A request bounds

The only field identity in this phase is ECMWF IFS `0p25`, stream `oper`, surface
2-metre temperature: `paramId=167`, `shortName=2t`, units `K`. Requests contain:

- `run_date` from 2023-01-18 through the current UTC date;
- `cycle_hour` in `00/06/12/18`;
- `step_hours` in 0..360 at 3-hour increments (the IFS 0p25 operational horizon bound
  used by this contract, not a claim that every cycle publishes every step);
- one to 64 explicit `EcmwfLocation(point_id, latitude, longitude)` values, with finite
  latitude in [-90,90], longitude in [-180,180], and unique non-empty IDs.

Future **validity** is permitted when the run/step produces it. The run, valid time,
local receipt, and provider-reported last-modified time remain separate fields. A later
vintage is not made safe by this module; consumers must compare availability to their
decision origin. Phase A deliberately provides no point-in-time availability resolver.

## Discovery and index discipline

Official discovery follows actual HTML directory links from `/forecasts/` through the
date, cycle, `ifs`, `0p25`, and `oper` directories (at most six bounded listing pages).
It never guesses a missing directory. The AWS source uses one fixed ListObjectsV2
request with prefix `<YYYYMMDD>/<HH>z/ifs/0p25/oper/`, `max-keys=1000`; a truncated
listing is an error rather than an unbounded crawl.

The expected object basename is
`<YYYYMMDD><HH>0000-<step>h-oper-fc.grib2`; its sidecar index replaces the
`.grib2` suffix with `.index` (for example,
`20261027000000-24h-oper-fc.index` beside
`20261027000000-24h-oper-fc.grib2`). Both must be present in the discovered listing.
No whole-file fallback exists when the index or exact object is absent.

The index is bounded at 2 MiB. Official JSONL keys are read tolerantly. The captured
2026-10-27 00z 24 h index's `2t` row contains only `domain`, `date`, `time`, `expver`,
`class`, `type`, `stream`, `step`, `levtype`, `param`, `_offset`, and `_length`; it has
no `paramId`, `shortName`, `name`, or `units`. Such a row is valid. `paramId` is
optional: when present it is recorded as `param_id_basis=index_declared`; when absent,
only the reviewed short name `2t` maps to `167`
(`param_id_basis=reviewed_short_name`). Any other short name remains unselected with
`param_id=None`, so an unknown parameter is never assigned `167`. A present `paramId`
that conflicts with the present `shortName`/`param` (including `paramId=167` with a
different name, or `2t` with a different id) is an index error, as is a disagreement
between `shortName` and `param`. Unknown official keys remain preserved in the raw row
text; present run/date/time/step/stream/type/unit metadata must agree with the request.
More than one `2t` candidate is an ambiguity error. The immutable `EcmwfIndexRow`
preserves row byte offset, row hash, raw row JSON, byte offset, length, name, date,
time, step, the optional parameter id, and whether that id was declared or derived.
`EcmwfIndex` preserves the raw index SHA-256 and row count. Absent index units are not
treated as proof of Kelvin; the decoder validates the actual GRIB parameter and units.

## Byte retrieval and provenance

The index-derived byte range is fetched with an exact `Range: bytes=start-end` GET.
Success requires HTTP `206`, an exact matching `Content-Range`, matching
`Content-Length`, and the exact indexed byte count. HTTP `200` is never used as a
fallback; neither is a re-download of the whole GRIB object. Limits are 32 MiB per
field message, 2 MiB per index, and 1 MiB per listing page. Bodies are streamed through
a hard cap, not unbounded `response.content` reads.

HTTP 429/503 responses are retried at most three attempts total. `Retry-After` is
bounded to two seconds; absent/invalid values use bounded exponential delay. No retry
reads an error body. `Content-Encoding` must be identity so returned bytes remain the
exact GRIB message.

`EcmwfField` contains the exact immutable bytes and their SHA-256. Its reference also
preserves selected source/origin, exact asset URL, request SHA-256, index SHA-256/row
offset, run/cycle/step, and valid UTC instant. `EcmwfRun` preserves listing page hashes,
directory and object URLs, nominal issue time, valid time, request start, receipt
completion, and an optional provider `Last-Modified` timestamp.

`issued_at_utc` is the nominal model cycle, never inferred from the local receipt.
`receipt_completed_at_utc` is the actual local receipt of these bytes now, even when a
historical archive is requested. `provider_last_modified_utc` is unreviewed provider
evidence stored separately with `availability_basis=provider_last_modified`; the
absence of that header yields `local_receipt_only`. Neither is a historical local
receipt nor a reviewed publication/availability decision.

## Decoder contract

ecCodes is imported lazily. Missing or incomplete Python bindings raise
`ecmwf_decoder_unavailable`; a binding older than 2.50.0 raises the stable
`ecmwf_decoder_version_unsupported`. There is no mock, synthetic, JSON-weather, or
skip-based fallback. Unit tests inject a fake binding only to test mechanics. The GRIB
`paramId=167` and `units=K` checks are the parameter/unit proof; an index that omits
those keys is valid and is never treated as if it had proved them.

Before ecCodes sees bytes, the decoder requires GRIB magic, edition 2, an exact
declared length equal to the returned message length, a terminal `7777`, and therefore
exactly one message. It then validates `paramId=167`, `units=K`, `stepType=instant`,
`dataDate`/`dataTime`, UTC `validityDate`/`validityTime`, the forecast step, and the
global `regular_ll` 0.25-degree grid (`Ni=1440`, `Nj=721`) against the typed request
and reference. Wrong parameter, units, step type, grid, run, validity, cross-run
reference, missing key, non-finite/missing value, malformed/multi-message bytes, or
hash mismatch is refused with a stable error code.

For every explicit location, `codes_grib_find_nearest(..., npoints=1)` supplies the
actual nearest grid latitude/longitude/distance and Kelvin value. The result converts
once with `celsius = kelvin - 273.15` and does not round to a financial precision. No
observing station, regional weight, interpolation claim, climatology, or synthetic
value is introduced. `EcmwfDecodedField` preserves decoder library/version, grid
dimensions, run parameters, forecast step, request hash, and the raw field reference;
each `EcmwfPoint` retains the same reference and its requested/nearest coordinates.
Every ecCodes handle is released in a `finally` path.

## Evidence boundary and open follow-up

The HTTPX `MockTransport` tests are authored to exercise exact requests, range and
content-length mismatches, caps, hashes, redirect rejection, retry bounds, error-body
non-leakage, index ambiguity, malformed index, duplicate-index keys, missing assets,
and invalid inputs. The actual captured row shape is pinned by a literal `2t` row and
literal non-`2t` rows from the 2026-10-27 00z 24 h index, including declared/derived
parameter-id metadata and conflicting declarations. Fake-binding decoder tests cover
metadata, multi-message/malformed-container rejection, NaN and missing values, nearest
`npoints=1`, Celsius conversion, handle release, and parameter/unit validation when the
index omits those keys. They do not claim a live ECMWF response or an authentic ecCodes
decode. No test suite was executed in the implementation session that produced this
document; root must run the checks and preserve the output.

Root must still run the isolated ecCodes 2.50 collection and real-provider probe outside
these unit tests, capture actual field/index metadata, and obtain the separate license,
CVE, universal-closure, and hash review before any requirements/persistence activation.
If actual provider index keys differ from those tolerated here, the follow-up is a
narrow parser/decoder fix, not a fallback to the whole object or guessed JSON weather.

## Independent root evidence, 2026-10-28

The focused transport/decoder suite passed 54 tests. An isolated Linux probe
using ecCodes 2.50.0 fetched the real 2026-10-27 00z IFS 0p25 oper +24 h index,
selected the `2t` message and downloaded exactly 316,916 bytes by HTTP range.
GRIB SHA-256: `b5f2d7539233af58073c3c92abb6b1b672d4506558bab5226756c4ac370f5ba0`.
Index SHA-256: `562ca60ddc8ade16b0b507301d6a5eedb930f9169299f8282525797b237bccdb`.
ecCodes validated parameter 167, Kelvin, the 1440 by 721 grid, issue/run and
2026-10-28 00:00 UTC validity. The explicit London location mapped to grid
51.5 N, 0.0 E and decoded 282.32708740234375 K (9.177087402343773 C).

This is one authentic forecast field and nearest-grid-point observation of the
decoder, not an observed temperature station or regional forecast validation.
The isolated Windows ecCodes wheel loaded its version but failed to open its
embedded definition files; Windows decoder operation is unverified. Linux
success does not clear that issue. Dependency/license/CVE closure, persistence,
regional aggregation and actual business consumers remain separate work.
