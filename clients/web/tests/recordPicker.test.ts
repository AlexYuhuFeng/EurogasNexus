import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { bookOptions, contractOptions, counterpartyOptions, gasYearOptions, personOptions } from "../src/app/model/recordOptions.ts";
import { idFromName, matchRank, MAX_VISIBLE, moveActive, pickerEntries, readRecent, withRecent } from "../src/components/ui/recordPickerModel.ts";

// UX_REFERENCE rule 25 (the live principle): choose records that exist, never type their ids.

const options = [
  { id: "cp-rhinmark", label: "Rhinmark Handel GmbH", keywords: ["Rhinmark"] },
  { id: "cp-nordvik", label: "Nordvik Petroleum ASA" },
  { id: "cp-aldermoor", label: "Aldermoor Energy plc", keywords: ["AEP"] },
];

test("search ranks a name's start, then a word's start, then anywhere, then the id and keywords", () => {
  assert.equal(matchRank(options[0], "rhin"), 0);
  assert.equal(matchRank(options[1], "petro"), 1);
  assert.equal(matchRank(options[1], "troleum"), 2);
  assert.equal(matchRank(options[2], "aep"), 3);
  assert.equal(matchRank(options[0], "cp-rhin"), 3);
  assert.equal(matchRank(options[0], "zzz"), null);
  assert.equal(matchRank({ id: "x", label: "Société Générale" }, "societe"), 0);
  const { entries } = pickerEntries(options, "a");
  assert.deepEqual(entries.map((entry) => entry.type === "record" && entry.option.id), ["cp-aldermoor", "cp-nordvik", "cp-rhinmark"]);
});

test("recent picks lead an empty search; at most twelve rows, the rest by typing", () => {
  const { entries } = pickerEntries(options, "", { recent: ["cp-nordvik", "gone"] });
  assert.deepEqual(entries.map((entry) => entry.type === "record" && [entry.option.id, entry.recent]), [
    ["cp-nordvik", true],
    ["cp-rhinmark", false],
    ["cp-aldermoor", false],
  ]);
  const many = Array.from({ length: 30 }, (_, index) => ({ id: `c${index}`, label: `Contract ${index}` }));
  const result = pickerEntries(many, "");
  assert.equal(result.entries.length, MAX_VISIBLE);
  assert.equal(result.hidden, 30 - MAX_VISIBLE);
  assert.deepEqual(withRecent(["a", "b", "c", "d", "e"], "c"), ["c", "a", "b", "d", "e"]);
  assert.deepEqual(readRecent({ getItem: () => "not json" }, "k"), []);
});

test("manual entry is an explicit last option, and only where the form allows it", () => {
  assert.equal(pickerEntries(options, "Nordwind AG").entries.length, 0);
  const { entries } = pickerEntries(options, "Nordwind AG", { allowManual: true });
  assert.deepEqual(entries.at(-1), { type: "manual", text: "Nordwind AG" });
  assert.ok(!pickerEntries(options, "Nordvik Petroleum ASA", { allowManual: true }).entries.some((entry) => entry.type === "manual"));
});

test("keyboard moves wrap and stop at the list", () => {
  assert.equal(moveActive(0, "ArrowDown", 3), 1);
  assert.equal(moveActive(2, "ArrowDown", 3), 0);
  assert.equal(moveActive(0, "ArrowUp", 3), 2);
  assert.equal(moveActive(1, "End", 3), 2);
  assert.equal(moveActive(1, "Home", 3), 0);
  assert.equal(moveActive(0, "a", 3), null);
  assert.equal(moveActive(0, "ArrowDown", 0), null);
});

test("a new record's id is made from its name, never typed", () => {
  assert.equal(idFromName("Rhinmark Handel GmbH"), "rhinmark-handel-gmbh");
  assert.equal(idFromName("Rhinmark Handel GmbH", ["rhinmark-handel-gmbh"]), "rhinmark-handel-gmbh-2");
  assert.equal(idFromName("Śląsk Gaz"), "slask-gaz");
  assert.equal(idFromName("中文"), "item");
});

test("records are offered by name: contracts in execution, active books, counterparties, people", () => {
  const contracts = contractOptions(
    [
      { contract_id: "c1", contract_name: "Norway pipeline 2026", delivery_point_name: "NBP", gas_year: "2026/27" },
      { contract_id: "c2", contract_name: "Old swap", retired_at_utc: "2026-01-01T00:00:00Z" },
    ],
    [],
  );
  assert.deepEqual(contracts.map((item) => [item.id, item.label, item.detail]), [["c1", "Norway pipeline 2026", "NBP · 2026/27"]]);
  const kept = contractOptions([{ contract_id: "c2", contract_name: "Old swap", retired_at_utc: "2026-01-01T00:00:00Z" }], ["c2"]);
  assert.equal(kept[0].disabled, true);
  assert.deepEqual(bookOptions([{ book_id: "demo-nl-ttf", name: "NL TTF desk", active: true }, { book_id: "x", name: "Closed", active: false }]).map((item) => item.label), ["NL TTF desk"]);
  assert.deepEqual(counterpartyOptions([{ counterparty_id: "a", counterparty: "A plc" }, { counterparty_id: "a", counterparty: "A plc" }]).length, 1);
  assert.deepEqual(personOptions([{ id: "demo.nl.trader", name: "Demo TTF desk trader" }, { id: "demo.trader" }]).map((item) => item.label), ["Demo TTF desk trader", "demo.trader"]);
  assert.deepEqual(gasYearOptions(new Date(Date.UTC(2026, 10, 19))).slice(0, 3), ["2025/26", "2026/27", "2027/28"]);
  assert.equal(gasYearOptions(new Date(Date.UTC(2026, 5, 1)))[1], "2025/26");
});

test("forms that asked for typed ids now choose (the audit's conversions)", () => {
  const read = (file: string) => readFileSync(new URL(`../src/components/${file}`, import.meta.url), "utf8");
  const limits = read("RiskLimitsPanel.tsx");
  assert.doesNotMatch(limits, /t\("limits\.counterparty_id"\)|t\("limits\.mandate_id"\)/);
  for (const id of ["credit-counterparty", "credit-contracts", "mandate", "mandate-trader", "mandate-books", "mandate-hubs", "mandate-instruments"]) {
    assert.match(limits, new RegExp(`id="${id}"`), id);
  }
  assert.doesNotMatch(read("ReviewWorkspace.tsx"), /review\.entity_id_placeholder/);
  assert.match(read("ReviewWorkspace.tsx"), /id="review-entity"/);
  assert.match(read("DecisionCasePanel.tsx"), /id="decision-case-evidence"/);
  assert.doesNotMatch(read("ContractWorkbench.tsx"), /t\("contracts\.contract_id"\)<input/);
  assert.match(read("ContractWorkbench.tsx"), /id="contract-counterparty"/);
  assert.doesNotMatch(read("TradingBooksPanel.tsx"), /t\("books\.book_id"\)/);
  assert.doesNotMatch(read("NotificationChannelsPanel.tsx"), /t\("notify\.channel_id"\)/);
  assert.doesNotMatch(read("decision/NominationWindowPanel.tsx"), /decision\.nomination\.window_id/);
  assert.doesNotMatch(read("decision/StorageDispatchPanel.tsx"), /decision\.dispatch\.period_id"\), render/);
  assert.match(read("decision/StorageDispatchPanel.tsx"), /id="dispatch-facility"/);
});
