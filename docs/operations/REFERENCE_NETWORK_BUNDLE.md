# Reference network bundle

The map draws the gas network from `reference_nodes` and `reference_edges`. On a fresh
installation those tables are empty until ENTSOG is first read, and an installation without
outbound network never reads it. The product therefore ships a small north-west Europe
network and loads it at install time.

## What ships

`src/eurogas_nexus/reference_data/nwe_reference_network.json` (package data, version
`2026-11-14`, about 390 KB, one record per line):

| Part | Count | Content |
|---|---|---|
| Points | 318 | ENTSOG interconnection, storage, LNG, production and trading points with an operator in BE, DE, DK, FR, GB, IE, LU, NL or NO, plus every balance landing point |
| with a position | 267 | ENTSOG's map position transformed to approximate lon/lat (`display_approximation`, never `verified`) |
| without a position | 51 | ENTSOG publishes no map position (Dornum ITP-00126/00188, Emden ITP-00080/00081/00160 and others): no coordinate, counted as not located |
| Operator point directions | 683 | operators, adjacent operators, booking platform and product flags |
| Schematic links | 288 | each point to the trading point of its operator's entry-exit zone (TTF, THE, NBP, ZTP, PEG, GTF, IBP); `schematic: true`, zone membership, not pipeline routes and never drawn as lines |

Distribution and final-consumer points are left out. The source, download date and the
citation ENTSOG's terms require are in the file's `source` block and in each seeded row; the
licence position is in `docs/legal/DATA_SOURCE_TERMS.md` ("Reference network bundle").

## Loading it

```bash
python scripts/ops/seed_reference_network.py --json
```

The server stack runs this as the one-shot `reference-seed` service after `migrate`; the
Windows installer runs it right after the migration. It writes through the live ingestion's
own `upsert_reference_snapshot` (upsert under stable ids, retire rather than delete), so:

- a repeat run converges on the same rows;
- a store that already holds a live ENTSOG reference read is left unchanged
  (`skipped_live_reference_present`);
- a later live ENTSOG read takes over the same ids; the schematic links stay
  (`source_system = EGN_REFERENCE_BUNDLE`).

## On the map

Points draw as approximate positions. The zone links are not drawn: a trading point is a
market area, not a place wired to each of its points, and drawing them put a star of lines
on every hub. They are used to ring a hub's points when the hub is selected and for the
topology check. The bundle carries no surveyed route and no point-to-point link, so the
network shows as points only (see `docs/ux/LIVE_MAP.md`, "Topology over geometry"). The
situation strip reads "Network points 318 · 51
without a published position"; the points without one are listed in its tooltip and in
`unlocated_network_points` of `GET /api/portfolio/map-situation` (`unlocated.network_points`;
flows at points with no position count in `unlocated.flows`), following the outage rule:
counted, never placed at a guessed position. Twynholm and Carrickfergus (Northern Ireland)
have no zone trading point in ENTSOG's list and stay unlinked, so the map's topology check
reports them.

## Refreshing it

After a complete ENTSOG reference read on a development store:

```bash
python scripts/ops/build_reference_network_bundle.py --version <yyyy-mm-dd> --downloaded <yyyy-mm-dd>
pytest -q tests/unit/test_reference_network_bundle.py
```

The build is read-only, checks the bundle (unique ids, links between positioned points,
schematic and verified flags) and refuses to write a defective one. Review the line diff
before committing.
