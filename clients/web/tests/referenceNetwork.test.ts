/**
 * The reference-network register and the capacity profile book (slice D of the D3 decision).
 *
 * Five declared reads had no consumer; three of them are reference and contract reads whose
 * absence made the map's topology and the operating board's capacity uncheckable:
 * `GET /api/reference-network/facilities`, `GET /api/reference-network/market-hubs` and
 * `GET /api/contracts/capacity`.
 *
 * The theme these tests hold is the one the routes themselves are careful about: an unconfigured
 * runtime database is answered with an empty list *plus the reason*, so a surface must not render
 * it as a register that holds nothing. The other theme is arithmetic nobody stated - a capacity a
 * row does not declare is not zero, and separate windows over the same point are not a total.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  REFERENCE_READ_LIMIT,
  readMayBeTruncated,
  readState,
} from "../src/app/model/readPosture.ts";
import {
  declaredCapacityCounts,
  facilityCountryOptions,
  facilityRows,
  facilityTypeKey,
  facilityTypeOptions,
  marketHubRows,
} from "../src/app/model/referenceNetworkModel.ts";
import {
  capacityContractRows,
  coveredPointCount,
  firmnessOptions,
} from "../src/app/model/capacityContractModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const MEASURED = {
  research_only: true,
  human_review_required: true,
  source_references: ["runtime-postgresql"],
  warnings: [],
};

const NOT_CONFIGURED = {
  research_only: true,
  human_review_required: true,
  source_references: ["runtime-db-not-configured"],
  warnings: ["Reference-network data is unavailable until a runtime DB is configured."],
  missing_inputs: ["RUNTIME_STORE_DATABASE_URL", "reference_facilities"],
};

test("an unconfigured runtime database is not an empty register", () => {
  assert.equal(readState(NOT_CONFIGURED).posture, "runtime-db-not-configured");
  assert.deepEqual(readState(NOT_CONFIGURED).missingInputs, [
    "RUNTIME_STORE_DATABASE_URL",
    "reference_facilities",
  ]);
  // A read that happened and found nothing is a measurement - a different sentence on the page.
  assert.equal(readState(MEASURED).posture, "measured");
  assert.deepEqual(readState(MEASURED).missingInputs, []);
  assert.equal(readState(MEASURED).source, "runtime-postgresql");
  // No envelope at all is "not read", never "empty".
  assert.equal(readState(null).posture, "not-read");
  assert.equal(readState(undefined).posture, "not-read");

  // The contracts route marks the same situation with its source tag rather than with
  // `missing_inputs`, so the tag alone has to be enough.
  assert.equal(
    readState({ ...MEASURED, source_references: ["runtime-db-not-configured"] }).posture,
    "runtime-db-not-configured",
  );
  // An envelope whose provenance the route omitted is still a measurement, and says so honestly.
  const noProvenance = { research_only: true, human_review_required: true };
  assert.equal(readState(noProvenance).posture, "measured");
  assert.equal(readState(noProvenance).source, null);
});

test("a bound is not a total", () => {
  assert.equal(REFERENCE_READ_LIMIT, 2000);
  // The model mirrors the client's read limit and the route's own ceiling; if either moves, the
  // count the panel states would be wrong.
  assert.match(readWebSource("api/client.ts"), /REFERENCE_NETWORK_READ_LIMIT = "2000"/);
  assert.equal(readMayBeTruncated(2000), true);
  assert.equal(readMayBeTruncated(1999), false);
  assert.equal(readMayBeTruncated(0), false);
});

test("a facility row keeps an undeclared capacity undeclared", () => {
  const rows = facilityRows([
    {
      id: "f-2",
      name: "Zeebrugge",
      facility_type: "lng_terminal",
      country: "BE",
      lat: 51.3,
      lon: 3.2,
      capacity_boe_d: null,
      source_system: "GIE ALSI",
    },
    {
      id: "f-1",
      name: "Arnhem",
      facility_type: "entry_point",
      country: "NL",
      lat: 51.9,
      lon: 5.9,
      capacity_boe_d: 1200,
      source_system: null,
    },
  ]);

  assert.deepEqual(
    rows.map((row) => row.name),
    ["Arnhem", "Zeebrugge"],
  );
  assert.equal(rows[0].capacityBoeD, 1200);
  assert.equal(rows[0].source, null);
  assert.equal(rows[1].capacityBoeD, null);
  assert.equal(rows[1].source, "GIE ALSI");
  assert.deepEqual(declaredCapacityCounts(rows), { declared: 1, undeclared: 1 });
  assert.deepEqual(declaredCapacityCounts([]), { declared: 0, undeclared: 0 });
  assert.deepEqual(facilityRows(null), []);
});

test("a declared facility type becomes words, and an unknown one stays the deployment's token", () => {
  assert.equal(facilityTypeKey("border_point"), "network.facility_type.border_point");
  assert.equal(facilityTypeKey("storage"), "network.facility_type.storage");
  assert.equal(facilityTypeKey("lng_terminal"), "network.facility_type.lng_terminal");
  assert.equal(facilityTypeKey("entry_point"), "network.facility_type.entry_point");
  // A type a newer deployment stores is not blanked and not guessed at.
  assert.equal(facilityTypeKey("hydrogen_hub"), null);
});

test("the filter options are the values the read returned, without blanks", () => {
  const rows = facilityRows([
    { id: "1", name: "A", facility_type: "storage", country: "DE", lat: 0, lon: 0, capacity_boe_d: null },
    { id: "2", name: "B", facility_type: "storage", country: "AT", lat: 0, lon: 0, capacity_boe_d: null },
    { id: "3", name: "C", facility_type: "border_point", country: "  ", lat: 0, lon: 0, capacity_boe_d: null },
  ]);
  assert.deepEqual(facilityTypeOptions(rows), ["border_point", "storage"]);
  assert.deepEqual(facilityCountryOptions(rows), ["AT", "DE"]);
  assert.deepEqual(facilityTypeOptions([]), []);
});

test("market hubs and capacity profiles render what the rows state", () => {
  const hubs = marketHubRows([
    { id: "h-2", name: "TTF", hub_code: "TTF", country: "NL", description: null },
    { id: "h-1", name: "THE", hub_code: "THE", country: "DE", description: "Trading Hub Europe" },
  ]);
  assert.deepEqual(hubs.map((hub) => hub.name), ["THE", "TTF"]);
  assert.equal(hubs[1].description, null);
  assert.deepEqual(marketHubRows(null), []);

  const contracts = capacityContractRows([
    {
      contract_id: "c-1",
      route_name: "Oberkappel",
      from_node_id: "Oberkappel",
      to_node_id: "Oberkappel",
      capacity_boe_d: 42000,
      unit: "MWh/d",
      start_utc: "2026-10-01T00:00:00+00:00",
      end_utc: "2027-10-01T00:00:00+00:00",
      status: "firm",
    },
    {
      contract_id: "c-2",
      route_name: "Baumgarten",
      from_node_id: "Baumgarten",
      to_node_id: "Baumgarten",
      capacity_boe_d: 15000,
      unit: "MWh/d",
      start_utc: "2026-01-01T00:00:00+00:00",
      end_utc: "2026-04-01T00:00:00+00:00",
      status: "interruptible",
    },
  ]);

  // The route owns the order (newest window first) and the unit each row declares; this module
  // re-sorts nothing and converts nothing.
  assert.deepEqual(contracts.map((row) => row.pointName), ["Oberkappel", "Baumgarten"]);
  assert.equal(contracts[0].unit, "MWh/d");
  assert.equal(contracts[1].firmness, "interruptible");
  assert.deepEqual(firmnessOptions(contracts), ["firm", "interruptible"]);
  assert.equal(coveredPointCount(contracts), 2);
  assert.equal(coveredPointCount(contracts.slice(0, 2).concat(contracts[0])), 2);
  assert.deepEqual(capacityContractRows(null), []);
});

test("the panels read the declared calls and state what each read established", () => {
  const register = readWebSource("components/ReferenceNetworkCatalogue.tsx");
  const book = readWebSource("components/CapacityContractBook.tsx");

  // The three calls that had no consumer, through the loader seam.
  assert.match(register, /api\s*\.facilities\(\)/);
  assert.match(register, /api\s*\.marketHubs\(\)/);
  assert.match(book, /api\s*\.capacityContracts\(\)/);

  // The filters are the route's own parameters, not a client sieve over a bounded page.
  assert.match(register, /api\s*\.facilities\(\{/);
  assert.match(register, /facility_type: facilityType === "all" \? undefined : facilityType/);
  assert.match(register, /country: country === "all" \? undefined : country/);

  // An unavailable read is a governed statement naming the missing input, and the tables are not
  // rendered as if they were empty.
  assert.match(register, /facilityRead\.posture === "runtime-db-not-configured" \?/);
  assert.match(register, /facilityRead\.missingInputs\.join\(", "\)/);
  assert.match(book, /read\.posture === "runtime-db-not-configured" \?/);
  assert.match(book, /t\("capacity\.contracts\.none"\)/);

  // The capacity is the row's own, with the unit the row declares, and never a total.
  assert.match(book, /row\.capacity\.toLocaleString\(\)\} \{row\.unit\}/);
  assert.equal(/\breduce\(/.test(book), false, "the book sums nothing");

  // A truncated read says so.
  assert.match(register, /readMayBeTruncated\(facilities\.length\)/);
  assert.match(register, /t\("network\.reference\.bounded"\)/);

  // Both failures are presented through the taxonomy rather than as raw transport strings.
  for (const panel of [register, book]) {
    assert.equal(panel.includes("setError(String("), false);
    assert.match(panel, /presentError\(t, describeFailure\(error\)\)/);
  }

  // They are mounted on tasks that already exist, and the register shares the network task with
  // the map it is the register for.
  assert.match(readWebSource("components/MarketCockpit.tsx"), /<ReferenceNetworkCatalogue t=\{t\} \/>/);
  assert.match(readWebSource("components/CapacityWorkspace.tsx"), /<CapacityContractBook t=\{t\} \/>/);
});

test("the reference and contract vocabulary is bilingual", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "network.reference.title",
    "network.reference.note",
    "network.reference.not_configured",
    "network.reference.missing_inputs",
    "network.reference.type",
    "network.reference.all_types",
    "network.reference.facilities",
    "network.reference.no_match",
    "network.reference.no_facilities",
    "network.reference.name",
    "network.reference.capacity",
    "network.reference.capacity_undeclared",
    "network.reference.capacity_declared",
    "network.reference.capacity_undeclared_count",
    "network.reference.source",
    "network.reference.bounded",
    "network.reference.hubs",
    "network.reference.hub",
    "network.reference.hub_code",
    "network.reference.hub_description",
    "network.reference.no_hubs",
    "network.facility_type.border_point",
    "network.facility_type.storage",
    "network.facility_type.lng_terminal",
    "network.facility_type.entry_point",
    "capacity.contracts.title",
    "capacity.contracts.note",
    "capacity.contracts.not_configured",
    "capacity.contracts.missing_inputs",
    "capacity.contracts.none",
    "capacity.contracts.profiles",
    "capacity.contracts.points",
    "capacity.contracts.point",
    "capacity.contracts.capacity",
    "capacity.contracts.window_from",
    "capacity.contracts.window_to",
    "capacity.contracts.firmness",
    "capacity.contracts.window_note",
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
  // Every facility type key the model can produce is declared in both locales.
  for (const type of ["border_point", "storage", "lng_terminal", "entry_point"]) {
    const key = facilityTypeKey(type);
    assert.ok(key, type);
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
  }
});
