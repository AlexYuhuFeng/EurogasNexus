import assert from "node:assert/strict";
import test from "node:test";

import { ENTRY_UNITS, draftMissing, emptyDraft } from "../src/app/model/tariffEntryModel.ts";

// The reviewed-tariff entry form: a draft names what it still needs before it can be sent.

test("a new draft runs over the current gas year and needs the leg, value and source", () => {
  const draft = emptyDraft();
  assert.match(draft.valid_from, /^\d{4}-10-01$/);
  assert.match(draft.valid_to, /^\d{4}-09-30$/);
  assert.deepEqual(draftMissing(draft), ["point", "operator", "value", "source_url", "published_on", "source_location"]);
});

test("a complete draft needs nothing; a reversed validity or an http source is named", () => {
  const draft = {
    ...emptyDraft(),
    point_key: "ITP-00005",
    operator_key: "UK-TSO-0001",
    tariff_value: "0.0356",
    currency: "GBP",
    unit: "p/kWh/d",
    source_url: "https://example.org/notice.pdf",
    published_on: "2026-05-29",
    source_location: "page 2, table 1",
  };
  assert.deepEqual(draftMissing(draft), []);
  assert.deepEqual(draftMissing({ ...draft, valid_to: "2020-01-01" }), ["validity"]);
  assert.deepEqual(draftMissing({ ...draft, source_url: "http://example.org" }), ["source_url"]);
  assert.deepEqual(draftMissing({ ...draft, tariff_value: "-1" }), ["value"]);
});

test("every currency offers units, the GB pence convention included", () => {
  assert.ok(ENTRY_UNITS.GBP.includes("p/kWh/d"));
  for (const units of Object.values(ENTRY_UNITS)) assert.ok(units.length > 0);
});
