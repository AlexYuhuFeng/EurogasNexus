/**
 * The tariff book view's pure logic (TAR-1): facilities, status tone (indicative is never shown
 * as final), the version trail and capacity window timing. Made-up figures.
 */
import assert from "node:assert/strict";
import test from "node:test";

import type { TariffPublisherDTO, TariffVersionDTO } from "../src/api/client.ts";
import {
  daysUntil,
  facilities,
  noticeTone,
  publisherOrder,
  publisherTone,
  statusTone,
  tariffFigure,
  versionTrail,
} from "../src/app/model/tariffBookModel.ts";

function version(changes: Partial<TariffVersionDTO>): TariffVersionDTO {
  return {
    tariff_key: "entsog-tp:entsog-ITP-1",
    version: 1,
    version_id: "tv-1",
    change_kind: "first",
    status: "INDICATIVE",
    status_basis: "nc_tar_before_yearly_auction",
    status_change: null,
    data_class: "indicative",
    publisher_id: "entsog-tp",
    publisher_name: "ENTSOG",
    facility_kind: "point",
    facility_id: "ITP-1",
    facility_name: "Point one",
    operator: "Operator A",
    country: "XX",
    market_area: null,
    direction: "EXIT",
    product: "ANNUAL",
    duration: "yearly",
    firmness: "FIRM",
    value: 4,
    by_class: null,
    unit: "EUR/(kWh/h)/y",
    currency: "EUR",
    period_from: "2026-10-01",
    period_to: "2027-09-30",
    published_at_utc: null,
    retrieved_at_utc: "2026-11-20T09:00:00+00:00",
    recorded_at_utc: "2026-11-20T09:00:00+00:00",
    superseded_at_utc: null,
    source_url: "https://publisher.example/tariffs/ITP-1",
    source_ref: "",
    content_hash: "x",
    event_id: null,
    withdrawn: false,
    ...changes,
  };
}

test("facilities with an indicative tariff come first", () => {
  const rows = [
    version({ facility_id: "A", facility_name: "Alpha", status: "FINAL" }),
    version({ facility_id: "Z", facility_name: "Zeta" }),
    version({ facility_id: "A", facility_name: "Alpha", status: "FINAL" }),
  ];
  assert.deepEqual(
    facilities(rows).map((item) => [item.id, item.final, item.indicative]),
    [
      ["Z", 0, 1],
      ["A", 2, 0],
    ],
  );
});

test("indicative never reads as final", () => {
  assert.equal(statusTone(version({ status: "FINAL" })), "ok");
  assert.equal(statusTone(version({ status: "INDICATIVE" })), "watch");
  assert.equal(statusTone(version({ withdrawn: true })), "stale");
});

test("figures as published, by cargo class when there is no single value", () => {
  assert.equal(tariffFigure(version({})), "4 EUR/(kWh/h)/y");
  assert.equal(
    tariffFigure(version({ value: null, by_class: { "Q-Flex": 900000 }, unit: "EUR/cargo" })),
    "Q-Flex 900,000 EUR/cargo",
  );
});

test("the version trail names each change and the move against the one before", () => {
  const trail = versionTrail([
    version({ version: 2, change_kind: "status_change", status: "FINAL", status_change: "INDICATIVE->FINAL", value: 4.5 }),
    version({ version: 1, superseded_at_utc: "2026-11-23T09:00:00+00:00" }),
  ]);
  assert.deepEqual(
    trail.map((step) => [step.version, step.status, step.statusChange, step.delta, step.current]),
    [
      [1, "INDICATIVE", null, null, false],
      [2, "FINAL", "INDICATIVE->FINAL", 0.5, true],
    ],
  );
});

test("capacity windows: days to opening and the three-day alert horizon", () => {
  const now = new Date("2026-10-30T12:00:00Z");
  assert.equal(daysUntil("2026-11-02T08:00:00+00:00", now), 3);
  assert.equal(noticeTone({ opens_at_utc: "2026-11-02T08:00:00+00:00", state: "open" }, now), "info");
  assert.equal(noticeTone({ opens_at_utc: "2026-11-16T08:00:00+00:00", state: "open" }, now), "neutral");
  assert.equal(noticeTone({ opens_at_utc: "2026-11-02T08:00:00+00:00", state: "cancelled" }, now), "stale");
});

test("publishers needing attention first", () => {
  const publisher = (id: string, state: TariffPublisherDTO["state"]) =>
    ({ publisher_id: id, name: id, state }) as TariffPublisherDTO;
  const ordered = publisherOrder([publisher("b", "manual"), publisher("a", "current"), publisher("c", "stale")]);
  assert.deepEqual(ordered.map((row) => row.publisher_id), ["c", "a", "b"]);
  assert.equal(publisherTone("excluded"), "breach");
  assert.equal(publisherTone("current"), "ok");
});
