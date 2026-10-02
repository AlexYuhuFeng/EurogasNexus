/**
 * Contract notes round trip (editor integrity, baseline 35091c9).
 *
 * `buildContractPayload` used to replace the whole stored `notes` JSON object with the
 * editor's own `web_contract_capture` envelope, so unknown provenance/terms and raw
 * operator notes were dropped by the first save from the web editor. These tests pin the
 * repair on the actual mapper and builder: a stored load carries the row's own notes
 * object, an edit overlays only the fields the editor owns, a stored origin is never
 * rewritten, and no transition (contract switch, new draft, file import) lets one row's
 * notes ride into another. Copying is structural - parser-based, never recursive - so
 * stored keys cannot reach a prototype and no draft aliases the record it was read from.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  contractDraftFromRecord,
  preservedNotesFromRecord,
} from "../src/app/contractImport.ts";
import {
  contractPayloadReadiness,
  type ContractPayloadReadiness,
} from "../src/app/contractPayload.ts";
import { cloneDefaultContractDraft } from "../src/app/defaultContractDraft.ts";

/** A stored row's notes object: known keys, unknown nested terms and odd scalar values. */
const STORED_NOTES = {
  source: "upstream_confirmation_capture",
  decision_support_only: true,
  human_review_required: true,
  counterparty: "Recorded counterparty",
  contract_type: "EFET physical supply",
  source_reference: "email:2025-09-30",
  capture_reference: "case-4711",
  indexation: { index: "TTF", floor_gbp_mwh: 0, cap: null, enabled: false },
  tags: ["firm", "reviewed"],
  null_term: null,
  zero_term: 0,
  false_term: false,
};

/**
 * The stored read shape of one persisted contract (`_contract_payload`): columns plus the
 * raw `notes` value. `notes` is parameterized because the policy for each stored value is
 * what these tests pin.
 */
function storedRecord(
  notes: unknown = JSON.stringify(STORED_NOTES),
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
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
    // The write route carries the cost terms in the row's structured notes and the stored read
    // surfaces them top-level. The fixture records them because a row that records no cost term
    // is not transportable (`contractPayloadReadiness`), and these tests compose payloads.
    variable_cost_gbp_mwh: 1.25,
    regas_fee_gbp_mwh: 0.5,
    fuel_loss_allowance_pct: 1.1,
    allowed_exit_points: ["NBP", "TTF"],
    eligible_sale_modes: ["TARGET_MARKET_SALE"],
    notes,
    ...overrides,
  };
}

/**
 * The transportable payload of a complete fixture draft, through the readiness boundary the
 * editor itself uses. A fixture the boundary refuses fails the test instead of bypassing it.
 */
function payloadOf(draft: Parameters<typeof contractPayloadReadiness>[0]): NonNullable<ContractPayloadReadiness["payload"]> {
  const readiness = contractPayloadReadiness(draft);
  assert.equal(readiness.ready, true, "the fixture draft must be transportable");
  assert.ok(readiness.payload, "a ready readiness result carries its payload");
  return readiness.payload;
}

/**
 * A new draft the boundary can transport: the template's quantity is the operator-entered
 * placeholder, so the payload-path cases supply a volume the way an operator would.
 */
function completedNewDraft() {
  return { ...cloneDefaultContractDraft(), delivery_quantity_mwh_per_day: 100 };
}

/** The one shape the backend accepts: `notes` serialized as a JSON object string. */
function savedNotes(payload: { notes: string }): Record<string, unknown> {
  const parsed = JSON.parse(payload.notes) as unknown;
  assert.ok(parsed && typeof parsed === "object" && !Array.isArray(parsed), "notes must be a JSON object");
  return parsed as Record<string, unknown>;
}

test("a stored load keeps unknown notes fields through an edit and save", () => {
  const draft = contractDraftFromRecord(storedRecord(), cloneDefaultContractDraft(), "stored");
  const payload = payloadOf(draft);
  const notes = savedNotes(payload);

  // Unknown provenance and terms survive verbatim, including nested objects and lists.
  assert.equal(notes.source, "upstream_confirmation_capture");
  assert.equal(notes.capture_reference, "case-4711");
  assert.deepEqual(notes.indexation, STORED_NOTES.indexation);
  assert.deepEqual(notes.tags, ["firm", "reviewed"]);

  // The editor's fields still carry the hydrated stored values.
  assert.equal(notes.counterparty, "Recorded counterparty");
  assert.equal(notes.contract_type, "EFET physical supply");
  assert.equal(notes.source_reference, "email:2025-09-30");
  assert.equal(payload.delivery_quantity_mwh_per_day, 9_000);
  assert.equal(payload.owned_entry_capacity_mwh_per_day, null);
});

test("owned edits overlay stored note values and leave unknown fields untouched", () => {
  const draft = contractDraftFromRecord(storedRecord(), cloneDefaultContractDraft(), "stored");
  // The same shape the hook's update helpers produce: a new draft object, one field changed.
  const edited = { ...draft, counterparty: "Edited in web editor", delivery_quantity_mwh_per_day: 1_234.5 };
  const payload = payloadOf(edited);
  const notes = savedNotes(payload);

  assert.equal(notes.counterparty, "Edited in web editor");
  assert.equal(notes.contract_type, "EFET physical supply");
  assert.deepEqual(notes.indexation, STORED_NOTES.indexation);
  assert.equal(payload.delivery_quantity_mwh_per_day, 1_234.5);
  assert.equal(payload.owned_entry_capacity_mwh_per_day, null);
});

test("a stored source is preserved, never rewritten to the web capture", () => {
  const draft = contractDraftFromRecord(storedRecord(), cloneDefaultContractDraft(), "stored");
  assert.equal(savedNotes(payloadOf(draft)).source, "upstream_confirmation_capture");

  // A null or falsy recorded origin is still stored evidence: it is not replaced either.
  for (const source of [null, "", false, 0]) {
    const record = storedRecord(
      JSON.stringify({ source, custom: { keep: 1 }, counterparty: "Recorded counterparty" }),
    );
    const notes = savedNotes(payloadOf(contractDraftFromRecord(record, cloneDefaultContractDraft(), "stored")));
    assert.deepEqual(notes.source, source);
    assert.deepEqual(notes.custom, { keep: 1 });
  }

  // Only a draft with no stored notes object gets the editor's own explicit envelope.
  const freshNotes = savedNotes(payloadOf(completedNewDraft()));
  assert.equal(freshNotes.source, "web_contract_capture");
  assert.equal(freshNotes.decision_support_only, true);
  assert.equal(freshNotes.human_review_required, true);
});

test("null, false and zero recorded values are preserved as recorded", () => {
  const notes = savedNotes(
    payloadOf(contractDraftFromRecord(storedRecord(), cloneDefaultContractDraft(), "stored")),
  );
  assert.equal(notes.null_term, null);
  assert.equal(notes.false_term, false);
  assert.equal(notes.zero_term, 0);
  assert.equal(notes.indexation.cap, null);
  assert.equal(notes.indexation.enabled, false);
  assert.equal(notes.indexation.floor_gbp_mwh, 0);
});

test("switching contracts replaces the preserved base instead of accumulating", () => {
  const first = contractDraftFromRecord(storedRecord(), cloneDefaultContractDraft(), "stored");
  const secondRecord = storedRecord(
    JSON.stringify({
      source: "second_capture",
      second_only: { n: 2 },
      counterparty: "Second counterparty",
    }),
    {
      contract_id: "stored-contract-2",
      contract_name: "Stored contract 2",
    },
  );
  // Even reusing the previous draft object as the base, the load adopts only the new row.
  const second = contractDraftFromRecord(secondRecord, first, "stored");
  const notes = savedNotes(payloadOf(second));

  assert.equal(notes.source, "second_capture");
  assert.deepEqual(notes.second_only, { n: 2 });
  assert.equal("capture_reference" in notes, false);
  assert.equal("indexation" in notes, false);
  assert.equal("null_term" in notes, false);
});

test("a new draft after a stored load clears the preserved base", () => {
  const loaded = contractDraftFromRecord(storedRecord(), cloneDefaultContractDraft(), "stored");
  const fresh = completedNewDraft();
  assert.notEqual(fresh.preserved_notes, loaded.preserved_notes);
  assert.equal(fresh.preserved_notes, null);
  const notes = savedNotes(payloadOf(fresh));

  assert.equal(notes.source, "web_contract_capture");
  assert.equal(notes.counterparty, "Operator draft counterparty");
  assert.equal("capture_reference" in notes, false);
  assert.equal("indexation" in notes, false);
});

test("a file import starts a fresh capture and clears the loaded row's notes", () => {
  const loaded = contractDraftFromRecord(storedRecord(), cloneDefaultContractDraft(), "stored");
  const imported = contractDraftFromRecord(
    {
      contract_id: "imported-draft",
      counterparty: "Imported counterparty",
      notes: JSON.stringify({ imported_only: true, source: "file_export" }),
    },
    loaded,
  );
  assert.equal(imported.preserved_notes, null);
  const notes = savedNotes(payloadOf(imported));

  // The previously loaded row's evidence cannot ride into the imported draft's save.
  assert.equal("capture_reference" in notes, false);
  assert.equal("indexation" in notes, false);
  // An imported file is a draft overlay, not stored evidence: only its known fields are
  // mapped, so the save is this editor's own capture envelope.
  assert.equal("imported_only" in notes, false);
  assert.equal(notes.source, "web_contract_capture");
  assert.equal(notes.counterparty, "Imported counterparty");
});

test("non-object stored notes are kept as operator notes; blank notes preserve nothing", () => {
  // The live preview row's raw marker, malformed JSON, a JSON array and a JSON scalar all
  // take the same route the API takes for raw text: `operator_notes`.
  for (const [stored, raw] of [
    ["preview_portfolio_contract:not_customer_data", "preview_portfolio_contract:not_customer_data"],
    ["{not json", "{not json"],
    ["[1,2,3]", "[1,2,3]"],
    [42, "42"],
  ] as Array<[unknown, string]>) {
    // A raw-notes row still needs its other required terms recorded to compose a payload; the
    // counterparty fixture lands where the stored read would carry it (the notes/record merge).
    const draft = contractDraftFromRecord(
      storedRecord(stored, { counterparty: "Recorded counterparty" }),
      cloneDefaultContractDraft(),
      "stored",
    );
    const notes = savedNotes(payloadOf(draft));
    assert.equal(notes.operator_notes, raw, `notes=${JSON.stringify(stored)}`);
    assert.equal("source" in notes, false, `no origin is invented for notes=${JSON.stringify(stored)}`);
  }

  // Nothing stored means nothing to preserve: the save is a fresh web capture.
  for (const stored of [null, "", "   "]) {
    const draft = contractDraftFromRecord(
      storedRecord(stored, { counterparty: "Recorded counterparty" }),
      cloneDefaultContractDraft(),
      "stored",
    );
    assert.equal(draft.preserved_notes, null);
    const notes = savedNotes(payloadOf(draft));
    assert.equal(notes.source, "web_contract_capture");
    assert.equal("operator_notes" in notes, false);
  }
  const withoutNotes = storedRecord();
  delete withoutNotes.notes;
  assert.equal(contractDraftFromRecord(withoutNotes, cloneDefaultContractDraft(), "stored").preserved_notes, null);

  // A stored empty JSON object is still a stored object: the editor adds only its own
  // fields and invents no origin for it.
  const emptyObject = savedNotes(
    payloadOf(
      contractDraftFromRecord(
        storedRecord("{}", { counterparty: "Recorded counterparty" }),
        cloneDefaultContractDraft(),
        "stored",
      ),
    ),
  );
  assert.equal("source" in emptyObject, false);
  assert.equal("operator_notes" in emptyObject, false);
  assert.equal(emptyObject.counterparty, "Recorded counterparty");
});

test("copying is structural: no record aliasing and no prototype pollution", () => {
  const nested = { floor_gbp_mwh: 0 };
  const record = storedRecord({
    source: "object_form_capture",
    nested_container: nested,
    counterparty: "Recorded counterparty",
  });
  const draft = contractDraftFromRecord(record, cloneDefaultContractDraft(), "stored");
  assert.ok(draft.preserved_notes);
  assert.notEqual(draft.preserved_notes, record.notes);
  assert.notEqual(draft.preserved_notes.nested_container, nested);

  const payload = payloadOf(draft);
  // The payload is a snapshot: mutating the draft's base (or the record it came from)
  // after the build cannot change what was already built.
  (draft.preserved_notes.nested_container as { floor_gbp_mwh: number }).floor_gbp_mwh = 999;
  nested.floor_gbp_mwh = 111;
  assert.deepEqual(savedNotes(payload).nested_container, { floor_gbp_mwh: 0 });

  // A stored object is JSON data, never a merge source for `Object.prototype`.
  const polluted = preservedNotesFromRecord({
    notes: '{"__proto__":{"polluted":true},"constructor":{"prototype":{"polluted":true}},"legit":1}',
  });
  assert.ok(polluted);
  assert.equal(Object.getPrototypeOf(polluted), Object.prototype);
  assert.equal(Object.prototype.hasOwnProperty.call(polluted, "__proto__"), true);
  const pollutedPayload = payloadOf(
    contractDraftFromRecord(
      storedRecord(
        '{"__proto__":{"polluted":true},"constructor":{"prototype":{"polluted":true}},"legit":1,"counterparty":"Recorded counterparty"}',
      ),
      cloneDefaultContractDraft(),
      "stored",
    ),
  );
  assert.equal(({} as { polluted?: boolean }).polluted, undefined);
  const pollutedNotes = savedNotes(pollutedPayload);
  assert.deepEqual(pollutedNotes.legit, 1);
  assert.deepEqual(pollutedNotes["__proto__"], { polluted: true });
  assert.deepEqual(pollutedNotes.constructor, { prototype: { polluted: true } });
  assert.equal(Object.getPrototypeOf(pollutedNotes), Object.prototype);
});

test("the editor keeps one payload path and the base travels with the draft", () => {
  const hook = readFileSync(new URL("../src/app/hooks/useContractEditor.ts", import.meta.url), "utf8");
  // The readiness result is the editor's one payload path: the save transports its payload and
  // no second composition exists beside it.
  assert.match(
    hook,
    /const payloadReadiness = useMemo\(\(\) => contractPayloadReadiness\(contract\), \[contract\]\);/,
  );
  // No second copy of the preserved base lives in the hook: it is replaced with the draft
  // on load and cleared with the draft on new/import, so it cannot go stale on its own.
  assert.equal(hook.includes("preserved_notes"), false);
});
