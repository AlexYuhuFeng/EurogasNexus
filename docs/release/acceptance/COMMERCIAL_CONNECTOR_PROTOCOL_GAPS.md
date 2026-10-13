# Commercial connector protocol gaps

Reviewed 2026-10-08. This is an implementation backlog, not provider certification.
The user requires real commercial adapters that work once valid credentials and
entitlements are supplied. Simulated data is development-only and must not be
included in customer delivery.

## Current repository evidence

`ingestion/connectors/eex.py`, `ice_ocm.py` and `trayport.py` inherit
`MockConnector`. Their current shells do not establish live protocol support.
The separate `ingestion/eex_ngp.py` public-file integration does not establish
support for subscribed EEX market-data products. Complete the connector census
before claiming coverage of every configured commercial source.

## Verified official documentation entrypoints

- [EEX documentation index](https://www.eex.com/en/market-data/documentation/)
  lists REST, Cloud Stream and File Cloud as separate interfaces.
- [REST v2 guide, revision 008](https://www.eex.com/fileadmin/EEX/Downloads/Market_Data/EEX_Group_DataSource/API/EEX_Group_DataSource_REST_API__v2__User_Guide_v008.pdf)
  describes bearer authentication, GET data access, JSON/XML responses, a
  one-request-per-second user limit and a 60,000-record response cap. Sorting
  is endpoint-specific. Detailed endpoint/field contracts are OpenAPI YAMLs on
  the DataSource Hub. Retrieve these before implementing endpoint mappings;
  do not treat a capped response as a complete historical dataset.
- [EEX Cloud Stream guide 4.9](https://www.eex.com/fileadmin/EEX/Downloads/Market_Data/EEX_Group_DataSource/API/EEX_Cloud_Stream_API_User_Guide__Ref_4.9_.pdf)
  and [File Cloud guide 006](https://www.eex.com/fileadmin/EEX/Downloads/Market_Data/EEX_Group_DataSource/File_Cloud/20261005_EEX_Group_DataSource_File_Cloud_User_Guide_006.pdf)
  are available separately. Their protocol details still need a focused review.
- [ICE Data Services Developer Center](https://developer.theice.com/hc/en-us)
  provides product documentation and SDK access using an ICE Data Services
  account. Select the actual subscribed data product and obtain its contract;
  a generic ICE label does not identify an interchangeable REST interface.
- Trayport's exact approved data protocol/SDK and conformance documentation
  remain to be retrieved and verified. Do not implement an invented HTTP API,
  or confuse unrelated products also named Joule with Trayport.

## Required implementation and acceptance work

1. Inventory source families and their actual interface products, versions,
   authentication, deployment dependencies and entitlement requirements.
2. Implement each documented transport: request/response, streaming or file
   delivery as applicable. Preserve existing provider authority boundaries;
   never add order entry, execution, nomination or settlement operations.
3. Verify pagination or bounded partitioning, truncation detection, incremental
   checkpoints, duplicate/revised records, reconnect recovery, rate limits and
   retry/error behavior against the selected protocol. Never invent a cursor
   parameter or assume uniform sort order.
4. Normalize identifiers, quote basis, units, currencies, observation/receipt
   times and delivery intervals explicitly. Retain source provenance and
   distinguish unknown metadata from declared values.
5. Test adapters with documented, development-only protocol fixtures and
   failure cases. Then run credentialed read-only conformance checks when
   credentials and applicable data rights are available. Keep implemented,
   protocol-tested and live-certified statuses separate.
6. Verify customer artifacts and deployment paths exclude simulated records,
   mock payloads and development seed behavior. Customer startup must expose
   absent/unconfigured sources honestly, never substitute synthetic prices.
   Retain useful empty-state and configuration guidance.

Missing private specifications or credentials must be named precisely. They
must not be hidden behind a generic adapter that reports success without
accessing the contracted source. This backlog remains open alongside engine,
persona, lifecycle, release and operational acceptance.

## Owner addition: Market Data Hub default / API fallback

Official-page transport discovery on 2026-10-10: the Hub HTML loads
[widget metadata](https://eds.eex-group.com/widgets/pub/ee7aff9c-287d-4d4d-a509-ec628bd35ea5/metadata.html),
which declares `https://api.eex-group.com/pub/market-data` as its base URL and
loads an official
[widget template](https://eds.eex-group.com/widgets/pub/lib/v1/templates/customized-solution/marketDataHubTemplate.html).
That template constructs `/chart/eod`, `/chart/intraday`, `/table-data-option`,
`/table-data`, `/price-ticker` and `/price-ticker/more-details` requests. These
are observed website transport paths, not a supported commercial API contract.
Request parameters, response schema and entitlement/use rights still require
verification before implementation is accepted. No bulk price collection was
performed during this discovery. Keep this public widget distinct from the
licensed DataSource REST v2 protocol.

Template parameter review: intraday requests select commodity, pricing, area,
product, maturity, date and instrument shortcode. Tables additionally select
end date, maturity type and rolling behavior. The table response is positional
rows plus a header array; map by headers, never hardcode column offsets.
Intraday responses carry series/time-value arrays, last update, currency and
unit. Settlement-table values must not be normalized as intraday executable
quotes. Actual response validation and supported parameter values remain open.

### Scope extension: every project data source

The owner also explicitly requests European TSO connectors where important
live data is available. Include direct TSO sources in the census for flows,
capacity availability, maintenance and outages. Compare existing ENTSOG coverage
first; prioritize material missing coverage or timeliness improvements rather
than duplicate pipelines. Verify each official interface, publication cadence,
revision behavior, gas-day/timezone semantics and usage rights. Preserve
transmission-point/direction identifiers and distinguish measured flows,
forecasts and capacity products. No connector may submit nominations, bookings
or trades. This requirement remains open pending source-specific evidence.

GIE development credentials were supplied by the owner and saved outside the
repository in a restricted local secret file; no credential value belongs in
this document. Independently verify IIP, AGSI and ALSI access. Their official
[IIP](https://iip.gie.eu/account) and
[AGSI/ALSI](https://agsi.gie.eu/account) API pages require visible source credit
when using or repackaging their data. Connectivity tests must not silently write
into the database while the Docker migration snapshot is being verified.

Read-only credential smoke on 2026-10-08: existing `/api/data/EU` endpoints on
both `agsi.gie.eu` and `alsi.gie.eu` returned HTTP 200, valid JSON with
`last_page`, `total`, `dataset`, `gas_day`, `data`, and 30 data entries each.
The supplied credential was read privately from its external file and sent in
the `x-key` header. No database writes or raw payload retention occurred.
This proves connectivity and response shape only; pagination, completeness,
data quality, negative authentication and IIP connectivity remain unverified.

The official IIP homepage also links a public [JSON Feed](https://iip.gie.eu/json),
observed on 2026-10-09. It embeds REMIT XML inside `content_html` and describes a
default view of today's submissions; it does not establish complete history or
equivalence to the authenticated API. Observed message
`26100821X000000001083B002_001` has outer `date_published` at
`2026-10-08T11:00:58+02:00` but embedded `publicationDateTime` at
`2026-10-08T11:00:58Z`. Preserve both originals and flag the conflict; do not
silently choose a timezone or backdate training availability. Confirm timestamp
semantics against provider documentation before this feed can pass temporal
quality acceptance. Parse embedded content as data, never render raw HTML.

Initial code-path census (not a completed source inventory): the seven named
connector classes for ECB, EEX, ENTSOG, GIE, ICE OCM, Trayport and weather inherit
`MockConnector`. Their presence is not live-connectivity evidence. Separately,
`scripts/ops/ingest_public_sources.py` contains actual ECB XML, ENTSOG operational
and topology API, and GIE AGSI/ALSI fetch paths; the scheduler and public ingestion
worker invoke that script. Audit and integrate those existing paths rather than
creating duplicate ingestion pipelines. `ingestion/public_sources.py` contains
normalizers, not network fetches. The separate EEX NGP adapter must not be
misrepresented as coverage of every Market Data Hub product. Cost-source
skeletons and development simulation ingestion/seed scripts also belong in the
inventory and customer-artifact exclusion review.

Direct TSO discovery, 2026-10-09: [National Gas REST documentation index](https://data.nationalgas.com/apis/rest-apis)
states instantaneous entry flows are sampled every two minutes and published in
12-minute batches; gas-quality telemetry refreshes every 12 minutes. Its old
SOAP APIs were decommissioned in June 2026. Use the linked developer portal's
current REST contracts; do not implement the obsolete SOAP interface or label
two-minute sampling as two-minute availability. This is discovery evidence,
not implemented connectivity. [Fluxys EDP manual](https://www.fluxys.com/-/media/project/fluxys/public/corporate/fluxyscom/documents/fluxys-belgium/commercial/operational-information/user-manual-edp/fluxys---user-manual-edp---20250306.pdf)
is a candidate primary protocol source requiring detailed review before coding.

The owner subsequently applies this policy to every data source in the project.
Inventory the complete source registry and all active ingestion paths, recording
the real default transport, optional licensed higher-frequency transport,
compatible fallback, freshness limits, rights and verification status per source.
Do not assume every provider offers a public or equivalent fallback. An absent
or unverified fallback must remain explicitly unavailable, never synthetic.
Only switch between compatible products, delivery periods, currencies, units
and quote/measurement semantics. Preserve original observations and source
selection history; point-in-time datasets must use actual availability, not
backdate later fallback retrieval. Verify outages, stale responses, auth errors,
recovery and duplicate/revised records for each implemented transport family.
This is an open project-wide acceptance requirement, not an EEX-only feature.

The owner requests EEX Market Data Hub as the default source and fallback when
a configured higher-frequency API is unavailable. This is an implementation
requirement, not a completed integration. Prefer a healthy, entitled API for
the same product; retain original source, observation, availability and receipt
times across switches. Never overwrite historical provenance or replace a
missing feed with simulated data. Fail closed if no compatible fresh source
exists. Test outage, recovery, stale data and product mismatch explicitly.

The [official FAQ](https://www.eex.com/en/faq), inspected on 2026-10-08, states
that intraday prices have a 15-minute delay. A minute polling interval must not
be labelled minute-latency market data. It also identifies TTF versus TTF USD
filter ambiguity: use explicit product identifiers, not the hub label alone.

The [Hub's published terms](https://www.eex.com/en/market-data/market-data-hub)
require express permission for systematic republication or dissemination of
substantial data. Customer redistribution/default collection rights are not
established by public page access. Verify the actual transport and applicable
rights before enabling customer deployments; continue bounded adapter and
fallback-policy implementation without inventing an undocumented endpoint.
# EEX credential lifecycle follow-up (2026-10-12)

Rechecked the official [documentation index](https://www.eex.com/en/market-data/documentation)
and [REST v2 guide, revision 008](https://www.eex.com/fileadmin/EEX/Downloads/Market_Data/EEX_Group_DataSource/API/EEX_Group_DataSource_REST_API__v2__User_Guide_v008.pdf).
The guide's section 3 specifies operator-generated bearer tokens, a maximum of
four concurrent keys, one-year validity and operator renewal. An adapter must
not invent an OAuth refresh flow or imply that a saved token stays valid forever.
Connection failure must remain distinct from absent subscription entitlement.

The guide delegates exact field contracts to OpenAPI YAML on the DataSource Hub.
The public Hub returned a JavaScript shell; inspecting its referenced entry script
did not locate YAML/OpenAPI links in this bounded attempt. Exact schemas remain
unretrieved, not unavailable by proof. No authenticated session was used, no
subscription purchased and no data ingestion or entitlement was changed.

