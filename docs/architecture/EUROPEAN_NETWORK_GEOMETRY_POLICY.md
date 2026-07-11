# European Network Geometry Policy

## Decision

Eurogas Nexus separates network **topology**, **operational state**, and **map
geometry**. ENTSOG and GIE are authoritative operational sources, but they are not
treated as a complete engineering-grade pipeline centerline dataset.

No generated straight line, route-candidate corridor, inferred connection, or
schematic map edge may be labelled as an official pipeline alignment.

## Source Responsibilities

### ENTSOG Transparency Platform

Use ENTSOG for:

- connection points and operator point directions;
- operators, balancing zones, interconnections, and aggregate interconnections;
- physical flow, nominations/allocations where published, technical capacity,
  interruptions, and urgent market messages;
- EIC and operator identifiers used to reconcile TSO records.

Official API reference:
`https://transparency.entsog.eu/api/archiveDirectories/8/api-manual/TP_REG715_Documentation_TP_API%20-%20v2.1.pdf`

ENTSOG topology can prove that systems and points connect. It does not, by itself,
prove every intermediate bend or surveyed centerline coordinate of a pipeline.

### GIE AGSI/ALSI

Use GIE for:

- LNG terminal and underground storage facility identities;
- operator/EIC mapping;
- inventory, send-out, injection, withdrawal, contracted/available capacity, and
  data-quality state at the platform's publication cadence;
- facility operating and service context where published.

Official platform reference:
`https://www.gie.eu/agsi-and-alsi-transparency-platforms/`

GIE validates facility identity and operating context. It is not the primary source
for transmission pipeline centerlines.

## Geometry Authority Order

Persist geometry independently from operational observations. Accepted geometry
authority, in descending order:

1. TSO-published GIS or other machine-readable geospatial data whose licence permits
   commercial storage and display.
2. A commercially licensed European gas-network geometry dataset.
3. A public, licence-approved geospatial source that has been reconciled to ENTSOG
   point, operator, balancing-zone, and EIC identifiers.
4. A schematic or inferred corridor, stored and rendered explicitly as
   `schematic` or `route_candidate`, never `verified_pipeline`.

Do not scrape map tiles or digitise copyrighted maps unless the licence explicitly
permits commercial derivative use.

## Required Geometry Record Contract

Each persisted line or point must carry:

- stable internal id and source record id;
- source system, dataset, reference URL/document, and licence class;
- geometry type and coordinate reference system;
- operator/TSO, countries, connected point ids, and EIC ids where available;
- `geometry_authority`: `tso_official`, `commercial_licensed`,
  `public_reconciled`, `schematic`, or `route_candidate`;
- `verification_status`: `verified`, `cross_checked`, `unverified`, or `rejected`;
- verification timestamp, method, and reviewer/tool version;
- validity interval and superseded record id;
- data-quality warnings.

Operational flow/capacity rows reference topology point ids. They do not overwrite
geometry.

## Verification Pipeline

1. Ingest source geometry into a staging table without altering the published map.
2. Validate CRS, bounds, geometry validity, duplicate ids, and coordinate precision.
3. Reconcile endpoints to ENTSOG operator-point-direction and interconnection data.
4. Reconcile LNG/storage endpoints to GIE EIC/operator/facility records.
5. Check country, TSO, balancing-zone, direction, and adjacency consistency.
6. Quarantine unmatched or contradictory records with explicit diagnostics.
7. Publish only records meeting the configured authority threshold.
8. Retain source version and validation evidence so a release can be reproduced.

## Client Rendering Rules

- `verified_pipeline`: solid network line with source and verification details.
- `public_reconciled`: solid line with a lower-confidence indicator.
- `schematic`: subdued dashed line.
- `route_candidate`: highlighted commercial decision corridor, visually distinct
  from physical infrastructure.
- unavailable geometry: show validated nodes and topology status; do not invent a
  line to make the map appear complete.

## V1 Acceptance Boundary

V1 may deliver a verified multi-country topology and operating-state graph from
ENTSOG/GIE plus approved TSO data. It may claim complete European pipeline geometry
only after a licence-approved geometry dataset passes the verification pipeline
above. Until then, the UI and reports must state the actual geometry coverage and
authority level.
