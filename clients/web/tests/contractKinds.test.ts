/**
 * Contract kinds, type first (docs/product/CONTRACT_TYPES.md): the form shows only a kind's
 * terms, builds the typed request, reads stored terms back, and the list's headline; the cargo
 * study fills itself from a confirmed cargo; the page's wiring (cards, pickers, own save).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  CONTRACT_KINDS,
  KIND_FIELDS,
  contractPeriod,
  contractStatus,
  listedContracts,
  periodText,
  draftFromTerms,
  draftWithProposal,
  kindHeadline,
  kindTermsFromDraft,
  newKindDraft,
  typedContractBody,
  visibleFields,
} from "../src/app/model/contractKinds.ts";
import { exampleForm, formFromConfirmation } from "../src/app/model/cargoStudy.ts";
import en from "../src/i18n/en.json" with { type: "json" };
import zh from "../src/i18n/zh.json" with { type: "json" };

const tender = {
  ...newKindDraft("UPSTREAM_TENDER"),
  seller_name: "Nordvik Energy",
  counterparty_id: "DEMO-NORDVIK",
  delivery_point: "NBP",
  period_start: "2026-12-01",
  period_end: "2027-02-28",
  dcq_mwh_per_day: "5000",
  min_dcq_mwh_per_day: "4000",
  max_dcq_mwh_per_day: "6000",
  index: "NBP day-ahead",
  differential: "-0.4",
  financing_rate_pct: "5",
};

test("the four authorable kinds start from cards; the typed three have their own fields", () => {
  assert.deepEqual([...CONTRACT_KINDS], ["SUPPLY_GSA", "UPSTREAM_TENDER", "LNG_MSPA", "LNG_CARGO"]);
  assert.deepEqual(visibleFields("SUPPLY_GSA", {}), []);
  for (const fields of Object.values(KIND_FIELDS)) {
    assert.ok(fields.every((field) => field.input !== "picker" || field.picker), "a picker names its register");
  }
});

test("a tender draft becomes typed terms with numbers, the credit line and its schema", () => {
  const { terms, missing } = kindTermsFromDraft("UPSTREAM_TENDER", tender);
  assert.deepEqual(missing, []);
  assert.equal(terms?.schema, "upstream-tender/v1");
  assert.equal(terms?.dcq_mwh_per_day, 5000);
  assert.equal(terms?.differential, -0.4);
  assert.equal(terms?.payment_lag_days, 20);
  assert.equal(terms?.counterparty_id, "DEMO-NORDVIK");
  assert.equal(terms?.field_outage_force_majeure, true);
  assert.equal("fixed_price" in (terms ?? {}), false, "a hidden field is not sent");
});

test("required terms block the save and are named; a fixed price swaps the index fields", () => {
  const { terms, missing } = kindTermsFromDraft("UPSTREAM_TENDER", { ...tender, dcq_mwh_per_day: "", index: "" });
  assert.equal(terms, null);
  assert.deepEqual(missing.sort(), ["dcq_mwh_per_day", "index"]);
  const fixed = visibleFields("UPSTREAM_TENDER", { ...tender, price_type: "fixed" }).map((field) => field.key);
  assert.ok(fixed.includes("fixed_price") && !fixed.includes("index"));
});

test("a DES cargo asks for its terminal and hub, an FOB cargo for its load port", () => {
  const des = visibleFields("LNG_CARGO", newKindDraft("LNG_CARGO")).map((field) => field.key);
  assert.ok(des.includes("discharge_terminal") && des.includes("terminal_hub") && !des.includes("load_port"));
  const fob = visibleFields("LNG_CARGO", { ...newKindDraft("LNG_CARGO"), delivery_term: "FOB" }).map((field) => field.key);
  assert.ok(fob.includes("load_port") && !fob.includes("discharge_terminal"));
  const { missing } = kindTermsFromDraft("LNG_CARGO", newKindDraft("LNG_CARGO"));
  assert.ok(missing.includes("master_contract_id"));
});

test("stored terms read back into the form, and an intake proposal fills only known fields", () => {
  const { terms } = kindTermsFromDraft("UPSTREAM_TENDER", tender);
  const draft = draftFromTerms("UPSTREAM_TENDER", terms);
  assert.equal(draft.dcq_mwh_per_day, "5000");
  assert.equal(draft.counterparty_id, "DEMO-NORDVIK");
  const proposed = draftWithProposal("LNG_CARGO", newKindDraft("LNG_CARGO"), { quantity_mmbtu: 3600000, surprise: 1 });
  assert.equal(proposed.quantity_mmbtu, "3600000");
  assert.equal("surprise" in proposed, false);
});

test("the typed request carries kind, terms, master, unmodelled text and the edit token", () => {
  const body = typedContractBody({ contractId: "c", contractName: " CN-07 ", kind: "LNG_CARGO", terms: { schema: "lng-cargo/v1" }, masterId: "m", unmodelled: "  ", editToken: "sha256:x" });
  assert.deepEqual(body, {
    contract_id: "c", contract_name: "CN-07", contract_kind: "LNG_CARGO", kind_terms: { schema: "lng-cargo/v1" },
    master_contract_id: "m", unmodelled_terms: null, notes: null, expected_edit_token: "sha256:x",
  });
});

test("the list shows the figure that matters for the kind", () => {
  const rows = [
    { contract_id: "t", contract_kind: "UPSTREAM_TENDER", delivery_quantity_mwh_per_day: 5000, headline: { key: "swing", value: 5000, min: 4000, max: 6000, unit: "MWh/d" } },
    { contract_id: "c", contract_kind: "LNG_CARGO", delivery_quantity_mwh_per_day: 1, headline: { key: "cargo", value: 3.6, unit: "TBtu", term: "DES", window: ["2027-01-10", "2027-01-14"] } },
    { contract_id: "m", contract_kind: "LNG_MSPA", delivery_quantity_mwh_per_day: 0 },
    { contract_id: "g", contract_kind: "SUPPLY_GSA", delivery_quantity_mwh_per_day: 1200 },
  ];
  assert.equal(kindHeadline(rows[0]).text, "5,000 MWh/d (4,000–6,000)");
  assert.equal(kindHeadline(rows[1]).text, "DES 3.60 TBtu");
  assert.equal(kindHeadline(rows[2], rows, (id) => (id === "c" ? "m" : null)).text, "1");
  assert.equal(kindHeadline(rows[3]).text, "1,200 MWh/d");
});

test("the cargo study fills itself from a confirmed HH-priced cargo", () => {
  const base = exampleForm(new Date(Date.UTC(2026, 10, 19)));
  const next = formFromConfirmation(base, {
    delivery_term: "DES", quantity_mmbtu: 3600000, window_start: "2027-01-10", pricing_month: "2026-12",
    price_formula: "hh", slope: 1.15, constant: 2.5, boil_off_pct_per_day: 0.1,
  });
  assert.equal(next.term, "DES");
  assert.equal(next.cargoSize, "3600000");
  assert.equal(next.arrivalMonth, "2027-01");
  assert.equal(next.pricingMonth, "2026-12");
  assert.equal(next.slope, "1.15");
  assert.equal(next.fee, "2.5");
  const brent = formFromConfirmation(base, { delivery_term: "FOB", price_formula: "brent", slope: 0.13, constant: 0.5 });
  assert.equal(brent.slope, base.slope, "a Brent slope is not an HH slope");
});

test("every kind string is in English and Chinese", () => {
  const keys = Object.keys(en).filter((key) => key.startsWith("contracts.kind"));
  assert.ok(keys.length > 100);
  for (const key of keys) assert.ok(key in zh, key);
  for (const kind of CONTRACT_KINDS) assert.ok(`contracts.kind.about.${kind}` in en);
  for (const fields of Object.values(KIND_FIELDS)) {
    for (const field of fields) assert.ok(`contracts.kind_field.${field.key}` in en, field.key);
  }
});

test("the page chooses the kind first, picks records, and the form saves itself", () => {
  const form = readFileSync(new URL("../src/components/ContractKindForm.tsx", import.meta.url), "utf8");
  const bench = readFileSync(new URL("../src/components/ContractWorkbench.tsx", import.meta.url), "utf8");
  assert.match(form, /data-contract-kind=\{kind\}/);
  assert.match(form, /<RecordPicker/);
  assert.match(form, /type="submit"/);
  assert.match(bench, /termsMode === "choose" && <ContractKindChooser/);
  // The page is the list; a row opens the contract; the supply editor's save sits with it.
  assert.match(bench, /<DataGrid\s+id="contract-list"/);
  assert.match(bench, /onRowAction=\{openContract\}/);
  assert.match(bench, /termsMode === "legacy" && \(\s*<>\s*<div className="contract-detail-actions">\{saveAction\}/);
});

test("the list puts contracts in execution first, finds by name, counterparty or point, filters by kind", () => {
  const today = "2026-11-19";
  assert.deepEqual(contractPeriod("2026/27"), { start: "2026-10-01", end: "2027-09-30" });
  assert.deepEqual(contractPeriod("2026-12..2027-02"), { start: "2026-12-01", end: "2027-02-28" });
  assert.equal(contractPeriod("2025+")?.end, null);
  assert.equal(contractStatus({ gas_year: "2024/25" }, today), "expired");
  assert.equal(contractStatus({ gas_year: "2026-12..2027-02" }, today), "upcoming");
  assert.equal(contractStatus({ gas_year: "2025+" }, today), "in_execution");
  assert.equal(contractStatus({ gas_year: "2026/27", retired_at_utc: "2026-11-01" }, today), "retired");
  const rows = [
    { contract_id: "a", contract_name: "Old", gas_year: "2024/25", delivery_point_name: "TTF", contract_kind: "SUPPLY_GSA" },
    { contract_id: "b", contract_name: "Tender", gas_year: "2026-12..2027-02", delivery_point_name: "NBP", contract_kind: "UPSTREAM_TENDER" },
    { contract_id: "c", contract_name: "Live", gas_year: "2026/27", delivery_point_name: "NBP", contract_kind: "SUPPLY_GSA" },
  ];
  const counterpartyOf = (row: { contract_id: string }) => (row.contract_id === "b" ? "Nordvik" : "");
  assert.deepEqual(listedContracts(rows, { query: "", kind: "", today, counterpartyOf }).map((row) => row.contract_id), ["c", "b", "a"]);
  assert.deepEqual(listedContracts(rows, { query: "nordvik", kind: "", today, counterpartyOf }).map((row) => row.contract_id), ["b"]);
  assert.deepEqual(listedContracts(rows, { query: "", kind: "SUPPLY_GSA", today, counterpartyOf }).map((row) => row.contract_id), ["c", "a"]);
  const month = (iso: string) => iso.slice(0, 7);
  assert.equal(periodText("2026/27", month), "GY 2026/27");
  assert.equal(periodText("2026-12..2027-02", month), "2026-12 – 2027-02");
  assert.equal(periodText("2025+", month), "2025-10 →");
});

test("a confirmation is listed under its master, whatever its own status", () => {
  const rows = [
    { contract_id: "cargo", contract_name: "A cargo", gas_year: "2027-01..2027-01", delivery_point_name: "Gate", contract_kind: "LNG_CARGO", master_contract_id: "mspa" },
    { contract_id: "gsa", contract_name: "B supply", gas_year: "2026/27", delivery_point_name: "TTF", contract_kind: "SUPPLY_GSA" },
    { contract_id: "mspa", contract_name: "Z master", gas_year: "2025+", delivery_point_name: "LNG master agreement", contract_kind: "LNG_MSPA" },
  ];
  const ids = listedContracts(rows, { query: "", kind: "", today: "2026-11-19", counterpartyOf: () => "" }).map((row) => row.contract_id);
  assert.deepEqual(ids, ["gsa", "mspa", "cargo"]);
  // A cargo found alone (its master filtered out) is still listed.
  const alone = listedContracts(rows, { query: "", kind: "LNG_CARGO", today: "2026-11-19", counterpartyOf: () => "" }).map((row) => row.contract_id);
  assert.deepEqual(alone, ["cargo"]);
});
