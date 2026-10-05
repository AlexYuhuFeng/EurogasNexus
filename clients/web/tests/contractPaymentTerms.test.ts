/**
 * Declared payment terms in the Resource Terms workbench: typed read, draft loading and
 * read-only presentation.
 *
 * The persisted declaration arrives on the stored-contract read as the strict canonical
 * `contract-payment-terms/v1` document, `null`, or no field at all. These tests pin the client
 * side of that contract without a browser:
 *
 * * the read keeps "no field", "explicitly null" and "declared" apart, and refuses a document
 *   it cannot verify - an unexpected or missing field, an unknown vocabulary spelling, an
 *   oversized value, an impossible date, a missing or unused calendar - instead of coercing it
 *   into an empty or partial schedule;
 * * a stored load carries its own decoded declaration, while a new draft, a file import and a
 *   record switch never let one record's terms ride into another draft;
 * * a sign-out or principal switch drops the persisted declaration carrier;
 * * the save builder sends no `payment_terms` at all, so omission preserves the stored
 *   declaration and the UI stays read-only;
 * * the workbench renders the declaration as labelled semantic rows inside the existing
 *   settlement section, warning that anchored rules are not calculated payable dates, with
 *   bilingual labels and safe wrapping.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { contractPayloadReadiness } from "../src/app/contractPayload.ts";
import { contractDraftFromRecord } from "../src/app/contractImport.ts";
import { cloneDefaultContractDraft } from "../src/app/defaultContractDraft.ts";
import {
  contractDraftAfterIdentityChange,
  type ContractDraft,
} from "../src/app/model/contractDraftModel.ts";
import {
  CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION,
  PAYMENT_TERMS_ANCHOR_EVENTS,
  PAYMENT_TERMS_BUSINESS_DAY_CONVENTIONS,
  PAYMENT_TERMS_CASH_FLOW_CATEGORIES,
  PAYMENT_TERMS_OFFSET_DAY_KINDS,
  paymentTermsReadFromRecord,
  paymentTermsReadFromValue,
} from "../src/app/model/contractPaymentTerms.ts";
import {
  paymentTermVocabularyLabel,
  paymentTermVocabularyLabelKey,
  type PaymentTermsVocabularyKind,
} from "../src/app/model/paymentTermsPresentation.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const EXPLICIT_ITEM = {
  item_id: "purchase-1",
  cash_flow_category: "cargo_purchase",
  flow_direction: "OUTFLOW",
  source_reference: "confirmation clause 7.2",
  date_specification: {
    kind: "EXPLICIT_DATE",
    final_payable_date: "2026-11-30",
    source_reference: "invoice schedule annex A",
  },
};

const ANCHORED_ITEM = {
  item_id: "sale-1",
  cash_flow_category: "cargo_sale",
  flow_direction: "INFLOW",
  source_reference:
    "confirmation clause 8.1 — a deliberately long evidence string that must wrap safely instead of overflowing the column",
  date_specification: {
    kind: "ANCHORED_RULE",
    anchor_event: "INVOICE_DATE",
    anchor_offset_days: 30,
    offset_day_kind: "BUSINESS_DAYS",
    business_day_convention: "MODIFIED_FOLLOWING",
    calendar_reference: "London banking calendar 2026 (operator reference)",
    source_reference: "confirmation clause 8.3",
  },
};

const NO_CALENDAR_ITEM = {
  item_id: "transport-1",
  cash_flow_category: "transport",
  flow_direction: "OUTFLOW",
  source_reference: "tariff statement 2026-01",
  date_specification: {
    kind: "ANCHORED_RULE",
    anchor_event: "DELIVERY_PERIOD_END",
    anchor_offset_days: 14,
    offset_day_kind: "CALENDAR_DAYS",
    business_day_convention: "NONE",
    calendar_reference: null,
    source_reference: "tariff statement annex 2",
  },
};

/** A copy of a mapping with one own field removed, the way a truncated payload arrives. */
function withoutField(record: Record<string, unknown>, field: string): Record<string, unknown> {
  const copy: Record<string, unknown> = { ...record };
  delete copy[field];
  return copy;
}

/** The explicit-date fixture with item-level overrides. */
function itemWith(overrides: Record<string, unknown>): Record<string, unknown> {
  return { ...EXPLICIT_ITEM, ...overrides };
}

/** The explicit-date fixture with overrides inside its date specification. */
function explicitSpecWith(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    ...EXPLICIT_ITEM,
    date_specification: { ...EXPLICIT_ITEM.date_specification, ...overrides },
  };
}

/** The anchored-rule fixture with overrides inside its date specification. */
function anchoredSpecWith(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    ...ANCHORED_ITEM,
    date_specification: { ...ANCHORED_ITEM.date_specification, ...overrides },
  };
}

/** A canonical declaration as the stored read serves it. */
function declaredTerms(items: unknown[] = [EXPLICIT_ITEM, ANCHORED_ITEM]) {
  return {
    schema_version: CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION,
    quantity_basis_reference: "delivered quantity per confirmation",
    items,
  };
}

/** The stored contract read shape a draft hydrates from (`_contract_payload`). */
function storedRecord(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const record: Record<string, unknown> = {
    contract_id: "stored-contract-1",
    contract_name: "Stored contract 1",
    resource_type: "PIPELINE_IMPORT",
    delivery_point_name: "TTF",
    gas_year: "2025+",
    delivery_quantity_mwh_per_day: 9_000,
    contract_price_gbp_mwh: 27.5,
    settlement_frequency: "monthly",
    upstream_payment_lag_days: 20,
    screen_sale_cash_lag_days: 1,
    annual_financing_rate_pct: 6,
    delivery_tolerance_pct: 2,
    nomination_tolerance_pct: 1,
    tolerance_risk_allowance_gbp_mwh: 0.1,
    owned_entry_capacity_mwh_per_day: null,
    owned_exit_capacity_mwh_per_day: null,
    variable_cost_gbp_mwh: 1.25,
    regas_fee_gbp_mwh: 0.5,
    fuel_loss_allowance_pct: 1.1,
    allowed_exit_points: ["NBP", "TTF"],
    eligible_sale_modes: ["TARGET_MARKET_SALE"],
    // The editor-owned counterparty lives in the row's structured notes; a row that records
    // none is not transportable, and these tests compose payloads.
    notes: JSON.stringify({ counterparty: "Recorded counterparty" }),
    edit_token: `sha256:${"a".repeat(64)}`,
    payment_terms: declaredTerms(),
  };
  // An override of `undefined` removes the field, the way a response without it arrives;
  // a spread would keep the key and turn "absent" into an unverifiable value.
  for (const [key, value] of Object.entries(overrides)) {
    if (value === undefined) delete record[key];
    else record[key] = value;
  }
  return record;
}

function loadedDraft(overrides: Record<string, unknown> = {}): ContractDraft {
  return contractDraftFromRecord(
    storedRecord(overrides),
    cloneDefaultContractDraft(),
    "stored",
  );
}

/** The transportable payload of a complete fixture draft, through the editor's own boundary. */
function payloadOf(draft: ContractDraft): Record<string, unknown> {
  const readiness = contractPayloadReadiness(draft);
  assert.equal(readiness.ready, true, "the fixture draft must be transportable");
  assert.ok(readiness.payload, "a ready readiness result carries its payload");
  return readiness.payload as unknown as Record<string, unknown>;
}

test("the read keeps absent, null and declared responses apart", () => {
  // A response with no declaration field is not evidence that nothing is recorded.
  assert.deepEqual(paymentTermsReadFromRecord(storedRecord({ payment_terms: undefined })), {
    state: "unavailable",
  });
  assert.deepEqual(paymentTermsReadFromValue(undefined), {
    state: "malformed",
    reason: "not_an_object",
  });

  // An explicit null is the stored "not stated".
  assert.deepEqual(paymentTermsReadFromRecord(storedRecord({ payment_terms: null })), {
    state: "not_declared",
  });

  // A canonical document decodes to itself: no field is renamed, defaulted or recomputed.
  const read = paymentTermsReadFromRecord(storedRecord());
  assert.deepEqual(read, { state: "declared", terms: declaredTerms() });
  if (read.state !== "declared") return;
  assert.deepEqual(read.terms.items, [EXPLICIT_ITEM, ANCHORED_ITEM]);
});

test("declared evidence and unresolved rules survive verbatim", () => {
  const read = paymentTermsReadFromValue(declaredTerms([EXPLICIT_ITEM, NO_CALENDAR_ITEM]));
  assert.equal(read.state, "declared");
  if (read.state !== "declared") return;

  // The explicit date is exactly the declared plain date, with both evidence references.
  assert.deepEqual(read.terms.items[0].date_specification, {
    kind: "EXPLICIT_DATE",
    final_payable_date: "2026-11-30",
    source_reference: "invoice schedule annex A",
  });
  // The anchored rule keeps its anchor, offset, day kind, convention and the explicit null
  // calendar of a rule that needs none; nothing is resolved into a pay date here.
  assert.deepEqual(read.terms.items[1].date_specification, NO_CALENDAR_ITEM.date_specification);
  assert.equal(read.terms.quantity_basis_reference, "delivered quantity per confirmation");
});

test("verified evidence is re-emitted with exactly the canonical fields, verbatim", () => {
  const evidence = " clause 7.2 — 原始证据 with  spaces  ";
  const read = paymentTermsReadFromValue({
    schema_version: CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION,
    quantity_basis_reference: evidence,
    items: [
      {
        ...EXPLICIT_ITEM,
        item_id: evidence,
        source_reference: evidence,
        date_specification: { ...EXPLICIT_ITEM.date_specification, source_reference: evidence },
      },
    ],
  });
  assert.equal(read.state, "declared");
  if (read.state !== "declared") return;

  // Nothing is trimmed, normalised or re-spelled: the declared evidence is preserved exactly.
  assert.equal(read.terms.quantity_basis_reference, evidence);
  assert.equal(read.terms.items[0].item_id, evidence);
  assert.equal(read.terms.items[0].source_reference, evidence);
  assert.equal(read.terms.items[0].date_specification.source_reference, evidence);

  // Only the canonical fields are re-emitted; an extra field is refused above, so it can never
  // ride into the rendered declaration.
  assert.deepEqual(Object.keys(read.terms).sort(), [
    "items",
    "quantity_basis_reference",
    "schema_version",
  ]);
  assert.deepEqual(Object.keys(read.terms.items[0]).sort(), [
    "cash_flow_category",
    "date_specification",
    "flow_direction",
    "item_id",
    "source_reference",
  ]);
  assert.deepEqual(Object.keys(read.terms.items[0].date_specification).sort(), [
    "final_payable_date",
    "kind",
    "source_reference",
  ]);
});

test("a declaration this client cannot verify is refused, never shown as an empty schedule", () => {
  const cases: Array<[string, unknown, string]> = [
    ["a raw string", "contract-payment-terms/v1", "not_an_object"],
    ["an array", [], "not_an_object"],
    ["an empty object", {}, "document_fields"],
    ["a document missing a field", withoutField(declaredTerms(), "quantity_basis_reference"), "document_fields"],
    ["an extra document field", { ...declaredTerms(), resolved_payment_date: "2026-11-30" }, "document_fields"],
    ["another schema version", { ...declaredTerms(), schema_version: "contract-payment-terms/v2" }, "schema_version"],
    ["a blank quantity basis", { ...declaredTerms(), quantity_basis_reference: "   " }, "quantity_basis"],
    ["items that are not an array", { ...declaredTerms(), items: "one" }, "items"],
    ["an empty schedule", { ...declaredTerms(), items: [] }, "schedule_empty"],
    ["a null item", declaredTerms([null]), "item"],
    ["a missing item field", declaredTerms([withoutField(EXPLICIT_ITEM, "source_reference")]), "item_fields"],
    ["an extra item field", declaredTerms([itemWith({ canonical_date: "2026-11-30" })]), "item_fields"],
    ["a blank item id", declaredTerms([{ ...EXPLICIT_ITEM, item_id: "  " }]), "item_id"],
    ["duplicate item ids", declaredTerms([EXPLICIT_ITEM, { ...EXPLICIT_ITEM }]), "item_id_duplicate"],
    ["a blank category", declaredTerms([{ ...EXPLICIT_ITEM, cash_flow_category: "" }]), "category"],
    ["an unknown category", declaredTerms([itemWith({ cash_flow_category: "mystery" })]), "category"],
    ["a mis-cased category", declaredTerms([itemWith({ cash_flow_category: "Cargo_Purchase" })]), "category"],
    ["a non-text category", declaredTerms([itemWith({ cash_flow_category: 7 })]), "category"],
    ["an unknown direction", declaredTerms([{ ...EXPLICIT_ITEM, flow_direction: "SIDEWAYS" }]), "direction"],
    ["a lower-case direction", declaredTerms([{ ...EXPLICIT_ITEM, flow_direction: "inflow" }]), "direction"],
    ["blank item evidence", declaredTerms([{ ...EXPLICIT_ITEM, source_reference: "" }]), "item_evidence"],
    ["a string date specification", declaredTerms([{ ...EXPLICIT_ITEM, date_specification: "2026-11-30" }]), "date_specification"],
    ["an unknown date kind", declaredTerms([{ ...EXPLICIT_ITEM, date_specification: { kind: "ROLLING_RULE" } }]), "date_kind"],
    ["a missing date kind", declaredTerms([{ ...EXPLICIT_ITEM, date_specification: {} }]), "date_kind"],
    ["a missing date field", declaredTerms([itemWith({ date_specification: { kind: "EXPLICIT_DATE", source_reference: "invoice schedule annex A" } })]), "specification_fields"],
    ["an extra date field", declaredTerms([explicitSpecWith({ resolved_payment_date: "2026-11-30" })]), "specification_fields"],
    ["a non-plain date", declaredTerms([{ ...EXPLICIT_ITEM, date_specification: { ...EXPLICIT_ITEM.date_specification, final_payable_date: "30/11/2026" } }]), "date_value"],
    ["an impossible month", declaredTerms([{ ...EXPLICIT_ITEM, date_specification: { ...EXPLICIT_ITEM.date_specification, final_payable_date: "2026-13-01" } }]), "date_value"],
    ["a datetime spelling", declaredTerms([{ ...EXPLICIT_ITEM, date_specification: { ...EXPLICIT_ITEM.date_specification, final_payable_date: "2026-11-30T00:00:00" } }]), "date_value"],
    ["blank date evidence", declaredTerms([{ ...EXPLICIT_ITEM, date_specification: { ...EXPLICIT_ITEM.date_specification, source_reference: " " } }]), "specification_evidence"],
    ["a missing anchor event", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, anchor_event: "" } }]), "anchor_event"],
    ["an unknown anchor event", declaredTerms([anchoredSpecWith({ anchor_event: "INVOICE_DATES" })]), "anchor_event"],
    ["a lower-case anchor event", declaredTerms([anchoredSpecWith({ anchor_event: "invoice_date" })]), "anchor_event"],
    ["a negative offset", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, anchor_offset_days: -1 } }]), "anchor_offset"],
    ["a fractional offset", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, anchor_offset_days: 1.5 } }]), "anchor_offset"],
    ["a string offset", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, anchor_offset_days: "30" } }]), "anchor_offset"],
    ["a boolean offset", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, anchor_offset_days: true } }]), "anchor_offset"],
    ["a missing offset day kind", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, offset_day_kind: "" } }]), "offset_day_kind"],
    ["an unknown offset day kind", declaredTerms([anchoredSpecWith({ offset_day_kind: "WEEKDAYS" })]), "offset_day_kind"],
    ["a missing convention", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, business_day_convention: "" } }]), "business_day_convention"],
    ["an unknown convention", declaredTerms([anchoredSpecWith({ business_day_convention: "NEAREST" })]), "business_day_convention"],
    ["an extra anchored field", declaredTerms([anchoredSpecWith({ resolved_anchor_date: "2026-11-01" })]), "specification_fields"],
    ["a missing anchored field", declaredTerms([itemWith({ date_specification: withoutField(ANCHORED_ITEM.date_specification, "calendar_reference") })]), "specification_fields"],
    ["a non-text calendar", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, calendar_reference: 42 } }]), "calendar_reference"],
    ["blank rule evidence", declaredTerms([{ ...ANCHORED_ITEM, date_specification: { ...ANCHORED_ITEM.date_specification, source_reference: "" } }]), "specification_evidence"],
  ];
  for (const [label, value, reason] of cases) {
    const read = paymentTermsReadFromValue(value);
    assert.deepEqual(read, { state: "malformed", reason }, label);
    assert.notEqual(read.state, "declared", label);
    assert.notEqual(read.state, "not_declared", label);
    assert.notEqual(read.state, "unavailable", label);
  }
});

test("only a real canonical ISO plain date is accepted", () => {
  const withDate = (finalPayableDate: string) =>
    declaredTerms([
      {
        ...EXPLICIT_ITEM,
        date_specification: {
          ...EXPLICIT_ITEM.date_specification,
          final_payable_date: finalPayableDate,
        },
      },
    ]);

  for (const impossible of [
    "2026-02-31",
    "2026-02-29",
    "1900-02-29",
    "2026-04-31",
    "2026-11-31",
    "2026-00-10",
    "2026-11-00",
    "0000-01-01",
  ]) {
    assert.deepEqual(
      paymentTermsReadFromValue(withDate(impossible)),
      { state: "malformed", reason: "date_value" },
      impossible,
    );
  }

  // A real day, including Gregorian leap days, stays declared and keeps its spelling.
  for (const real of ["2026-11-30", "2028-02-29", "2000-02-29", "0001-01-01", "9999-12-31"]) {
    const read = paymentTermsReadFromValue(withDate(real));
    assert.equal(read.state, "declared", real);
    if (read.state !== "declared") return;
    assert.equal(read.terms.items[0].date_specification.final_payable_date, real);
  }
});

test("the declared storage bounds are enforced, and the exact bound still decodes", () => {
  const atBound = "x".repeat(2_000);
  const overBound = "x".repeat(2_001);

  const bounded = declaredTerms([
    {
      ...EXPLICIT_ITEM,
      item_id: atBound,
      source_reference: atBound,
      date_specification: { ...EXPLICIT_ITEM.date_specification, source_reference: atBound },
    },
  ]);
  assert.equal(
    paymentTermsReadFromValue({ ...bounded, quantity_basis_reference: atBound }).state,
    "declared",
  );
  assert.equal(
    paymentTermsReadFromValue(
      declaredTerms([
        ...Array.from({ length: 999 }, (_, index) => ({
          ...EXPLICIT_ITEM,
          item_id: `line-${index}`,
        })),
        { ...EXPLICIT_ITEM, item_id: "line-999" },
      ]),
    ).state,
    "declared",
    "a 1,000-item schedule is inside the guard",
  );
  assert.equal(
    paymentTermsReadFromValue(declaredTerms([anchoredSpecWith({ anchor_offset_days: 36_525 })])).state,
    "declared",
    "the 36,525-day guard itself is declared",
  );

  const cases: Array<[string, unknown, string]> = [
    [
      "an oversized schedule",
      declaredTerms(
        Array.from({ length: 1_001 }, (_, index) => ({
          ...EXPLICIT_ITEM,
          item_id: `line-${index}`,
        })),
      ),
      "schedule_bounds",
    ],
    ["an oversized quantity basis", { ...declaredTerms(), quantity_basis_reference: overBound }, "quantity_basis"],
    ["an oversized item id", declaredTerms([itemWith({ item_id: overBound })]), "item_id"],
    ["oversized item evidence", declaredTerms([itemWith({ source_reference: overBound })]), "item_evidence"],
    ["oversized date evidence", declaredTerms([explicitSpecWith({ source_reference: overBound })]), "specification_evidence"],
    ["oversized rule evidence", declaredTerms([anchoredSpecWith({ source_reference: overBound })]), "specification_evidence"],
    ["an oversized calendar reference", declaredTerms([anchoredSpecWith({ calendar_reference: overBound })]), "calendar_reference"],
    ["an offset beyond the guard", declaredTerms([anchoredSpecWith({ anchor_offset_days: 36_526 })]), "anchor_offset"],
  ];
  for (const [label, value, reason] of cases) {
    assert.deepEqual(paymentTermsReadFromValue(value), { state: "malformed", reason }, label);
  }
});

test("a calendar is required exactly when a count or roll needs it, and refused when unused", () => {
  const refused = (overrides: Record<string, unknown>) =>
    paymentTermsReadFromValue(declaredTerms([anchoredSpecWith(overrides)]));

  // A business-day count needs its calendar...
  assert.deepEqual(
    refused({ offset_day_kind: "BUSINESS_DAYS", calendar_reference: null }),
    { state: "malformed", reason: "calendar_reference" },
  );
  // ...and so does a roll convention, even on a plain calendar-day count.
  assert.deepEqual(
    refused({ business_day_convention: "FOLLOWING", calendar_reference: null }),
    { state: "malformed", reason: "calendar_reference" },
  );
  // A blank reference is not an explicit calendar.
  assert.deepEqual(
    refused({ calendar_reference: "   " }),
    { state: "malformed", reason: "calendar_reference" },
  );
  // A calendar that neither a business-day count nor a roll uses is an unused declaration.
  assert.deepEqual(
    refused({
      offset_day_kind: "CALENDAR_DAYS",
      business_day_convention: "NONE",
      calendar_reference: "TARGET2",
    }),
    { state: "malformed", reason: "calendar_reference" },
  );

  // The declared "no calendar" of a rule that needs none stays declared...
  assert.equal(
    refused({
      offset_day_kind: "CALENDAR_DAYS",
      business_day_convention: "NONE",
      calendar_reference: null,
    }).state,
    "declared",
  );
  // ...and a roll keeps its calendar reference and convention verbatim.
  const read = refused({ business_day_convention: "PRECEDING", calendar_reference: "TARGET2" });
  assert.equal(read.state, "declared");
  if (read.state !== "declared") return;
  const specification = read.terms.items[0].date_specification;
  assert.equal(specification.kind, "ANCHORED_RULE");
  if (specification.kind !== "ANCHORED_RULE") return;
  assert.equal(specification.business_day_convention, "PRECEDING");
  assert.equal(specification.calendar_reference, "TARGET2");
});

test("the reviewed backend vocabulary spellings are accepted exactly as declared", () => {
  for (const cash_flow_category of [
    "cargo_purchase",
    "cargo_sale",
    "shipping",
    "transport",
    "regas",
    "storage",
    "fuel",
    "demurrage",
    "boil_off",
    "other",
  ]) {
    assert.equal(
      paymentTermsReadFromValue(declaredTerms([itemWith({ cash_flow_category })])).state,
      "declared",
      cash_flow_category,
    );
  }
  for (const anchor_event of [
    "INVOICE_DATE",
    "DELIVERY_PERIOD_START",
    "DELIVERY_PERIOD_END",
    "METER_READ_DATE",
  ]) {
    assert.equal(
      paymentTermsReadFromValue(declaredTerms([anchoredSpecWith({ anchor_event })])).state,
      "declared",
      anchor_event,
    );
  }
  for (const [offset_day_kind, business_day_convention, calendar_reference] of [
    ["CALENDAR_DAYS", "NONE", null],
    ["CALENDAR_DAYS", "FOLLOWING", "TARGET2"],
    ["CALENDAR_DAYS", "PRECEDING", "TARGET2"],
    ["BUSINESS_DAYS", "NONE", "TARGET2"],
    ["BUSINESS_DAYS", "MODIFIED_FOLLOWING", "TARGET2"],
  ]) {
    assert.equal(
      paymentTermsReadFromValue(
        declaredTerms([anchoredSpecWith({ offset_day_kind, business_day_convention, calendar_reference })]),
      ).state,
      "declared",
      `${offset_day_kind}/${business_day_convention}`,
    );
  }
});

test("a stored load carries its own declaration; new, imported and switched drafts cannot borrow it", () => {
  // Stored loads keep the three responses distinct on the draft itself.
  assert.equal(loadedDraft().persisted_payment_terms?.state, "declared");
  assert.equal(loadedDraft({ payment_terms: null }).persisted_payment_terms?.state, "not_declared");
  assert.equal(loadedDraft({ payment_terms: undefined }).persisted_payment_terms?.state, "unavailable");
  assert.equal(
    loadedDraft({ payment_terms: { schema_version: "contract-payment-terms/v9" } })
      .persisted_payment_terms?.state,
    "malformed",
  );

  // A new draft carries none.
  assert.equal(cloneDefaultContractDraft().persisted_payment_terms, null);

  // A file import overlays the working draft, but the previous record's declaration (and even
  // a `payment_terms` key inside the imported file) never rides into it: only a stored read
  // declares persisted terms.
  const loaded = loadedDraft();
  const imported = contractDraftFromRecord(
    { contract_id: "imported-1", payment_terms: declaredTerms() },
    loaded,
    "draft",
  );
  assert.equal(imported.persisted_payment_terms, null);

  // Switching stored records replaces the read instead of accumulating it.
  const second = contractDraftFromRecord(
    storedRecord({ contract_id: "stored-contract-2", payment_terms: null }),
    loaded,
    "stored",
  );
  assert.equal(second.persisted_payment_terms?.state, "not_declared");
});

test("the save builder sends no payment_terms, so omission preserves the stored declaration", () => {
  const draft = loadedDraft();
  const payload = payloadOf(draft);
  assert.equal("payment_terms" in payload, false, "the payload must omit the read-only field");
  assert.equal(draft.persisted_payment_terms?.state, "declared", "the draft still presents it");

  // The typed boundary documents the same rule: reads carry the field, the write input type
  // does not offer it, and the builder never mentions it.
  const client = readWebSource("api/client.ts");
  assert.match(client, /payment_terms\?: PaymentTermsDTO \| null;/);
  assert.match(client, /\| "payment_terms"\n/);
  assert.equal(readWebSource("app/contractPayload.ts").includes("payment_terms"), false);
});

test("a sign-out or principal switch drops the persisted declaration carrier", () => {
  const loaded = loadedDraft();
  const afterSwitch = contractDraftAfterIdentityChange(loaded);
  assert.equal(afterSwitch.persisted_payment_terms, null);
  // Only the carrier is cleared: the draft's other facts keep their values.
  assert.equal(afterSwitch.contract_id, loaded.contract_id);
  assert.deepEqual(afterSwitch.stored_edit, loaded.stored_edit);

  // A draft that carries none is returned unchanged, so a sign-out cannot churn editor state.
  const clean = cloneDefaultContractDraft();
  assert.equal(contractDraftAfterIdentityChange(clean), clean);

  // The editor wires the reset to the identity key it was given.
  const hook = readWebSource("app/hooks/useContractEditor.ts");
  assert.match(hook, /identityKey: string \| null = null,/);
  assert.match(hook, /const draftIdentityRef = useRef\(identityKey\);/);
  assert.match(hook, /commitDraft\(contractDraftAfterIdentityChange\);/);
  assert.match(hook, /\}, \[identityKey\]\);/);
  // Typing another contract id is the editor's own rebind: the draft stops claiming the
  // stored record's declaration the same way it stops claiming its edit token.
  assert.match(hook, /persisted_payment_terms: null \}/);
  const controller = readWebSource("app/hooks/useAppController.ts");
  assert.match(controller, /api\.currentUser\?\.principal_id \?\? null,/);
});

test("the workbench presents the read-only declaration inside the existing settlement section", () => {
  const workbench = readWebSource("components/ContractWorkbench.tsx");
  assert.match(
    workbench,
    /import \{ ContractPaymentTerms \} from "@\/components\/ContractPaymentTerms";/,
  );
  const settlementAt = workbench.indexOf('clauseView === "settlement"');
  const panelAt = workbench.indexOf("<ContractPaymentTerms read={contract.persisted_payment_terms} t={t} />");
  const restrictionsAt = workbench.indexOf('clauseView === "restrictions"');
  assert.ok(settlementAt > 0 && panelAt > settlementAt && panelAt < restrictionsAt,
    "the panel belongs to the settlement clause, and no page or section was added");

  // Semantic structure and no controls: rows live in a definition list, items in a list,
  // and the component offers no input, button or arithmetic.
  const panel = readWebSource("components/ContractPaymentTerms.tsx");
  for (const marker of ["<section", "<ul", "<li", "<dl", "<dt>", "<dd>", 'aria-label=', "data-payment-terms-state"]) {
    assert.ok(panel.includes(marker), marker);
  }
  for (const forbidden of ["<input", "<button", "<select", "Date(", "parseFloat", "toFixed", "payment_date"]) {
    assert.equal(panel.includes(forbidden), false, `the read-only panel must not contain ${forbidden}`);
  }
  // The anchored warning is shown for unresolved rules, and the direction and reference
  // labels come from the bilingual vocabulary.
  assert.match(panel, /hasAnchoredRule/);
  assert.match(panel, /contracts\.payment_terms\.unresolved_warning/);
  assert.match(panel, /contracts\.payment_terms\.direction\.inflow/);
  assert.match(panel, /contracts\.payment_terms\.calendar_reference/);

  // Long evidence wraps: the fact rows and item heads declare safe wrapping, and the narrow
  // viewport stacks the label and value instead of overflowing.
  const css = readWebSource("styles/app.css");
  assert.match(
    css,
    /\.contract-payment-facts dt,\s*\.contract-payment-facts dd \{[^}]*overflow-wrap: anywhere;/s,
  );
  assert.match(css, /\.contract-payment-item-head strong \{[^}]*overflow-wrap: anywhere;/s);
  assert.match(css, /@media \(max-width: 600px\) \{[\s\S]*?\.contract-payment-facts > div \{\s*grid-template-columns: 1fr;\s*\}/);
});

test("the settlement section still reads the legacy lag inputs while the declaration stays read-only", () => {
  const workbench = readWebSource("components/ContractWorkbench.tsx");
  const settlement = workbench.slice(
    workbench.indexOf('clauseView === "settlement"'),
    workbench.indexOf('clauseView === "restrictions"'),
  );
  // The legacy estimate fields and their numeric handlers are unchanged beside the panel.
  for (const marker of [
    'updateContractNumber("screen_sale_cash_lag_days"',
    'updateContractNumber("upstream_payment_lag_days"',
    'updateContractNumber("annual_financing_rate_pct"',
  ]) {
    assert.ok(settlement.includes(marker), marker);
  }
  assert.equal(settlement.includes("updateContractNumber(\"payment_terms"), false);
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  assert.match(en["contracts.payment_terms.estimate_distinction"], /estimate inputs/);
});

test("both locales declare the translated read-only vocabulary", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = Object.keys(en).filter((key) => key.startsWith("contracts.payment_terms."));
  assert.ok(keys.length >= 25, "the panel's vocabulary is declared");
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], `${key} must be translated, not copied`);
  }
  // The unresolved-rule warning is explicit in both locales.
  assert.match(en["contracts.payment_terms.unresolved_warning"], /not calculated payable dates/);
  assert.match(zh["contracts.payment_terms.unresolved_warning"], /并非计算得出的应付日期/);
  assert.match(en["contracts.payment_terms.date_kind.anchored"], /not a payable date/);
  assert.match(zh["contracts.payment_terms.date_kind.anchored"], /并非应付日期/);
  assert.match(zh["contracts.payment_terms.estimate_distinction"], /估算输入/);
});

/** Every reviewed vocabulary: the decoder's own spelling tuple and the displayed transport field. */
const REVIEWED_VOCABULARIES: Array<[PaymentTermsVocabularyKind, readonly string[]]> = [
  ["cash_flow_category", PAYMENT_TERMS_CASH_FLOW_CATEGORIES],
  ["anchor_event", PAYMENT_TERMS_ANCHOR_EVENTS],
  ["offset_day_kind", PAYMENT_TERMS_OFFSET_DAY_KINDS],
  ["business_day_convention", PAYMENT_TERMS_BUSINESS_DAY_CONVENTIONS],
];

function localeRecords(): { en: Record<string, string>; zh: Record<string, string> } {
  return {
    en: JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>,
    zh: JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>,
  };
}

test("every reviewed transport spelling has exactly one human-readable EN/ZH label", () => {
  const { en, zh } = localeRecords();
  const labelKeys = new Set<string>();
  for (const [kind, values] of REVIEWED_VOCABULARIES) {
    assert.ok(values.length > 0, `${kind} has a reviewed vocabulary`);
    for (const value of values) {
      const key = paymentTermVocabularyLabelKey(kind, value);
      assert.ok(key, `${kind}/${value}: a reviewed spelling must have a label key`);
      assert.match(
        key,
        /^contracts\.payment_terms\.[a-z_]+\.[a-z_]+$/,
        `${kind}/${value}: label key namespace`,
      );
      assert.equal(labelKeys.has(key), false, `${kind}/${value}: no two spellings share a label`);
      labelKeys.add(key);

      assert.ok(en[key]?.trim(), `en ${key}`);
      assert.ok(zh[key]?.trim(), `zh ${key}`);
      assert.notEqual(en[key], value, `en ${key} must read as a label, not the raw token`);
      assert.notEqual(zh[key], value, `zh ${key} must read as a label, not the raw token`);
      assert.notEqual(en[key], zh[key], `${key} must be translated, not copied`);

      // The wrapper resolves through exactly that key and returns the declared translation.
      const requested: string[] = [];
      const label = paymentTermVocabularyLabel(kind, value, (requestedKey) => {
        requested.push(requestedKey);
        return en[requestedKey] ?? "";
      });
      assert.deepEqual(requested, [key], `${kind}/${value}: one lookup for one spelling`);
      assert.equal(label, en[key], `${kind}/${value}: the label is the declared translation`);
    }
  }
  // Ten cash-flow categories, four anchor events, two offset day kinds, four conventions.
  assert.equal(labelKeys.size, 20, "the whole reviewed vocabulary is labelled");
});

test("an unreviewed runtime spelling is never given a known label or another meaning", () => {
  for (const [kind, values] of REVIEWED_VOCABULARIES) {
    const translate = () => "translated label";
    assert.equal(paymentTermVocabularyLabelKey(kind, "mystery"), null, `${kind}: unknown key`);
    assert.equal(
      paymentTermVocabularyLabel(kind, "mystery", translate),
      "mystery",
      `${kind}: an unknown runtime value stays raw`,
    );
    // Every reviewed spelling belongs to exactly one vocabulary: a spelling of another field is
    // not silently re-read as this field's value.
    for (const [otherKind, otherValues] of REVIEWED_VOCABULARIES) {
      if (otherKind === kind) continue;
      for (const value of otherValues) {
        if ((values as readonly string[]).includes(value)) continue;
        assert.equal(
          paymentTermVocabularyLabelKey(kind, value),
          null,
          `${kind} must not accept the ${otherKind} spelling ${value}`,
        );
        assert.equal(
          paymentTermVocabularyLabel(kind, value, translate),
          value,
          `${kind}/${value}: a foreign spelling stays raw`,
        );
      }
    }
  }
});

test("labels are presentation only: decoded spellings and evidence are never mutated", () => {
  const document = declaredTerms([EXPLICIT_ITEM, ANCHORED_ITEM]);
  const before = JSON.parse(JSON.stringify(document)) as Record<string, unknown>;
  const read = paymentTermsReadFromValue(document);
  assert.equal(read.state, "declared");
  if (read.state !== "declared") return;
  const { en } = localeRecords();
  const label = (kind: PaymentTermsVocabularyKind, value: string) =>
    paymentTermVocabularyLabel(kind, value, (key) => en[key] ?? key);

  for (const item of read.terms.items) {
    label("cash_flow_category", item.cash_flow_category);
    if (item.date_specification.kind === "ANCHORED_RULE") {
      label("anchor_event", item.date_specification.anchor_event);
      label("offset_day_kind", item.date_specification.offset_day_kind);
      label("business_day_convention", item.date_specification.business_day_convention);
    }
  }

  // Rendering-time lookups rewrite nothing: the transport document and the decoded declaration
  // still carry the exact reviewed spellings and every evidence string verbatim.
  assert.deepEqual(document, before, "the transport document is never rewritten by labelling");
  assert.deepEqual(read.terms, before, "the decoded declaration still carries the raw spellings");
  assert.deepEqual(read.terms.items, [EXPLICIT_ITEM, ANCHORED_ITEM]);
  assert.equal(read.terms.items[0].source_reference, EXPLICIT_ITEM.source_reference);
  assert.equal(read.terms.items[1].source_reference, ANCHORED_ITEM.source_reference);
  const anchored = read.terms.items[1].date_specification;
  assert.equal(anchored.kind, "ANCHORED_RULE");
  if (anchored.kind !== "ANCHORED_RULE") return;
  assert.equal(anchored.source_reference, ANCHORED_ITEM.date_specification.source_reference);
  assert.equal(anchored.calendar_reference, ANCHORED_ITEM.date_specification.calendar_reference);
});

test("the schedule detail list renders reviewed labels instead of raw transport spellings", () => {
  const panel = readWebSource("components/ContractPaymentTerms.tsx");
  for (const [kind, property] of [
    ["cash_flow_category", "item.cash_flow_category"],
    ["anchor_event", "specification.anchor_event"],
    ["offset_day_kind", "specification.offset_day_kind"],
    ["business_day_convention", "specification.business_day_convention"],
  ]) {
    // Source formatting is not part of the contract, so the call is matched across line breaks.
    assert.match(
      panel,
      new RegExp(
        `paymentTermVocabularyLabel\\(\\s*"${kind}",\\s*${property.replace(/\./g, "\\.")},\\s*t,?\\s*\\)`,
      ),
      `${kind} must be displayed through its label`,
    );
    assert.equal(panel.includes(`value={${property}}`), false, `${kind} must not render raw`);
  }
  // Stored evidence and reference strings are still rendered exactly as declared.
  for (const marker of [
    "value={item.source_reference}",
    "value={specification.source_reference}",
    "value={specification.final_payable_date}",
    "value={String(specification.anchor_offset_days)}",
    "specification.calendar_reference ??",
  ]) {
    assert.ok(panel.includes(marker), marker);
  }
});

test("the item header keeps the translated direction without a duplicate fact row", () => {
  const panel = readWebSource("components/ContractPaymentTerms.tsx");
  const headAt = panel.indexOf("contract-payment-item-head");
  const directionAt = panel.indexOf("contract-payment-direction");
  const factsAt = panel.indexOf("contract-payment-facts");
  assert.ok(
    headAt > 0 && directionAt > headAt && factsAt > directionAt,
    "the translated direction stays announced in the item header",
  );
  assert.ok(
    panel.includes("directionLabel(item.flow_direction, t)"),
    "the header still shows the translated direction",
  );
  assert.ok(
    panel.includes("contracts.payment_terms.direction.inflow"),
    "the direction vocabulary stays translated",
  );
  assert.equal(
    panel.includes('label={t("contracts.payment_terms.direction")}'),
    false,
    "the direction is not repeated as a second fact row",
  );
});
