import type { ContractDraft } from "./defaultContractDraft";
import { paymentTermsReadFromRecord } from "./model/contractPaymentTerms.ts";

export function stringFromRecord(record: Record<string, unknown>, key: string, fallback: string): string {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

/**
 * Read one numeric term from a record, keeping "omitted" and "supplied" apart.
 *
 * * A key the record does not carry (or carries as `undefined`) is genuinely omitted and keeps
 *   the caller's fallback - the working draft's value on the file-import overlay, or `null` for
 *   stored hydration, which must not inherit template terms.
 * * A finite number, or a non-blank string that parses to one, is recorded as it stands
 *   (an explicit `0` stays `0`).
 * * Any other *supplied* value - `null`, `false`, `""`, `NaN`, `±Infinity`, a non-numeric
 *   string - is not a recordable number and maps to `null` (unknown). It never falls back to a
 *   template or draft value, so a stored row or an import that states an invalid term cannot
 *   silently present a different number as recorded.
 */
export function numberFromRecord(
  record: Record<string, unknown>,
  key: string,
  fallback: number | null,
): number | null {
  const value = record[key];
  if (value === undefined) return fallback;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function stringArrayFromRecord(record: Record<string, unknown>, key: string, fallback: string[]): string[] {
  const value = record[key];
  if (Array.isArray(value)) {
    const items = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
    return items.length > 0 ? items : [...fallback];
  }
  if (typeof value === "string" && value.trim()) {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }
  // A fresh copy in the fallback branch too, so a mapped draft never aliases the base draft.
  return [...fallback];
}

export function notesRecordFromRecord(record: Record<string, unknown>): Record<string, unknown> {
  const notes = record.notes;
  if (notes && typeof notes === "object" && !Array.isArray(notes)) return notes as Record<string, unknown>;
  if (typeof notes !== "string" || !notes.trim()) return {};
  try {
    const parsed = JSON.parse(notes) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

/**
 * The persisted row's own notes object to carry through an editor save, or `null` when
 * there is nothing to preserve.
 *
 * A missing or blank notes value preserves nothing. A stored JSON object is copied so the
 * draft never aliases the record it was read from and no stored key can reach a prototype.
 * A non-empty value that is not a JSON object - free text, malformed JSON, an array or a
 * scalar - is kept as raw operator notes under the write path's existing `operator_notes`
 * key (`db/repositories/route_cost.py::_merged_contract_notes`), which is exactly where
 * the same value lands when raw text is written through the API, so a save cannot silently
 * discard it.
 */
export function preservedNotesFromRecord(record: Record<string, unknown>): Record<string, unknown> | null {
  const notes = record.notes;
  if (notes === null || notes === undefined) return null;
  if (typeof notes === "object" && !Array.isArray(notes)) {
    return cloneNotesJson(notes as Record<string, unknown>);
  }
  const raw = (typeof notes === "string" ? notes : JSON.stringify(notes) ?? "").trim();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return cloneNotesJson(parsed as Record<string, unknown>);
    }
  } catch {
    // Not JSON text: the raw value keeps its place under the operator-notes convention.
  }
  return { operator_notes: raw };
}

/**
 * A fresh, structural copy of a stored notes object.
 *
 * The copy goes through the JSON parser rather than a recursive merge: the input is JSON
 * data, no key is ever assigned onto `Object.prototype`, and the result can alias neither
 * the record nor the draft. A value the parser cannot round-trip falls back to a shallow
 * copy; stored notes are JSON text in the runtime, so that branch is defensive only.
 */
function cloneNotesJson(notes: Record<string, unknown>): Record<string, unknown> {
  try {
    const cloned = JSON.parse(JSON.stringify(notes)) as unknown;
    if (cloned && typeof cloned === "object" && !Array.isArray(cloned)) {
      return cloned as Record<string, unknown>;
    }
  } catch {
    // Fall through to the shallow copy.
  }
  return { ...notes };
}

export function sourceReferenceFromRecord(record: Record<string, unknown>): string {
  const notes = notesRecordFromRecord(record);
  const sourceReference = stringFromRecord({ ...notes, ...record }, "source_reference", "");
  if (sourceReference) return sourceReference;
  if (typeof record.notes !== "string") return "";
  const rawNotes = record.notes.trim();
  return rawNotes.startsWith("{") || rawNotes.startsWith("[") ? "" : rawNotes;
}

/**
 * Which value an absent text field takes when a record is merged into a draft.
 *
 * `"draft"` (the default) is the file-import path: the record overlays the working draft, so
 * an unstated term keeps the draft's value. `"stored"` hydrates a persisted record: absent
 * text clears to blank, because a stored row must not be presented with template facts
 * (counterparty, agreement form, governing law, source document, index basis, title transfer,
 * terminal access, ...) that its columns and notes do not hold.
 */
export type ContractRecordBase = "draft" | "stored";

/**
 * The stored identity and opaque edit token of one persisted record, or `null`.
 *
 * The token is only usable together with the identity it was read from: both must be
 * non-empty strings on the record, or the draft stays create-only. A stored record without
 * a token (an older deployment) fails closed into a create-only save rather than sending
 * anything else.
 */
function storedEditFromRecord(
  record: Record<string, unknown>,
): { contract_id: string; edit_token: string } | null {
  const contractId = typeof record.contract_id === "string" ? record.contract_id.trim() : "";
  const editToken = typeof record.edit_token === "string" ? record.edit_token.trim() : "";
  if (!contractId || !editToken) return null;
  return { contract_id: contractId, edit_token: editToken };
}

export function contractDraftFromRecord(
  record: Record<string, unknown>,
  current: ContractDraft,
  base: ContractRecordBase = "draft",
): ContractDraft {
  const mergedRecord = { ...notesRecordFromRecord(record), ...record };
  const text = (key: string, fromDraft: string) =>
    stringFromRecord(mergedRecord, key, base === "stored" ? "" : fromDraft);
  // Stored hydration has no template numeric fallback: a term the row does not record stays
  // unknown (`null`) instead of inheriting the working template's rate/cost/lag/tolerance/
  // quantity/price. The import overlay keeps the current draft's value for a genuinely
  // omitted key; a supplied invalid value maps to unknown either way (`numberFromRecord`).
  const number = (key: string, fromDraft: number | null) =>
    numberFromRecord(mergedRecord, key, base === "stored" ? null : fromDraft);
  return {
    ...current,
    // The preserved base belongs to where the draft came from, not to what it says: a
    // stored load adopts that record's own notes and clears an earlier row's; every other
    // base (the file-import overlay) clears it too, so notes never ride along from a
    // previously loaded contract into an import or a new draft.
    preserved_notes: base === "stored" ? preservedNotesFromRecord(record) : null,
    // The edit lease belongs to the stored record this draft was loaded from: a
    // `"stored"` load adopts that record's identity+token, and every other base
    // (file import, record overlay) clears it, so a save can never send a
    // previously loaded contract's token for another identity.
    stored_edit: base === "stored" ? storedEditFromRecord(record) : null,
    // The persisted declaration belongs to the stored record too: a `"stored"` load decodes
    // this record's own `payment_terms` (absent / null / declared / unverifiable, kept apart),
    // and every other base clears it - an imported file's `payment_terms` key is draft input,
    // not stored evidence, and must not present another record's declaration.
    persisted_payment_terms: base === "stored" ? paymentTermsReadFromRecord(record) : null,
    contract_id: text("contract_id", current.contract_id),
    contract_name: text("contract_name", current.contract_name),
    resource_type: text("resource_type", current.resource_type),
    counterparty: text("counterparty", current.counterparty),
    contract_type: text("contract_type", current.contract_type),
    delivery_point_name: text("delivery_point_name", current.delivery_point_name),
    physical_exit_point_name: text("physical_exit_point_name", current.physical_exit_point_name),
    title_transfer_point: text("title_transfer_point", current.title_transfer_point),
    beach_delivery_point: text("beach_delivery_point", current.beach_delivery_point),
    index_basis: text("index_basis", current.index_basis),
    terminal_access: text("terminal_access", current.terminal_access),
    capacity_expiry: text("capacity_expiry", current.capacity_expiry),
    document_name: text("document_name", current.document_name),
    document_status: text("document_status", current.document_status),
    source_reference: text("source_reference", current.source_reference),
    governing_law: text("governing_law", current.governing_law),
    gas_year: text("gas_year", current.gas_year),
    delivery_quantity_mwh_per_day: number(
      "delivery_quantity_mwh_per_day",
      current.delivery_quantity_mwh_per_day,
    ),
    contract_price_gbp_mwh: number("contract_price_gbp_mwh", current.contract_price_gbp_mwh),
    nbp_sale_price_gbp_mwh: number("nbp_sale_price_gbp_mwh", current.nbp_sale_price_gbp_mwh),
    physical_exit_sale_price_gbp_mwh: number(
      "physical_exit_sale_price_gbp_mwh",
      current.physical_exit_sale_price_gbp_mwh,
    ),
    delivery_tolerance_pct: number("delivery_tolerance_pct", current.delivery_tolerance_pct),
    nomination_tolerance_pct: number("nomination_tolerance_pct", current.nomination_tolerance_pct),
    tolerance_risk_allowance_gbp_mwh: number(
      "tolerance_risk_allowance_gbp_mwh",
      current.tolerance_risk_allowance_gbp_mwh,
    ),
    variable_cost_gbp_mwh: number("variable_cost_gbp_mwh", current.variable_cost_gbp_mwh),
    regas_fee_gbp_mwh: number("regas_fee_gbp_mwh", current.regas_fee_gbp_mwh),
    fuel_loss_allowance_pct: number("fuel_loss_allowance_pct", current.fuel_loss_allowance_pct),
    settlement_frequency: text("settlement_frequency", current.settlement_frequency),
    upstream_payment_lag_days: number("upstream_payment_lag_days", current.upstream_payment_lag_days),
    screen_sale_cash_lag_days: number(
      "screen_sale_cash_lag_days",
      current.screen_sale_cash_lag_days,
    ),
    annual_financing_rate_pct: number(
      "annual_financing_rate_pct",
      current.annual_financing_rate_pct,
    ),
    owned_entry_capacity_mwh_per_day: number(
      "owned_entry_capacity_mwh_per_day",
      current.owned_entry_capacity_mwh_per_day,
    ),
    owned_exit_capacity_mwh_per_day: number(
      "owned_exit_capacity_mwh_per_day",
      current.owned_exit_capacity_mwh_per_day,
    ),
    allowed_exit_points: stringArrayFromRecord(mergedRecord, "allowed_exit_points", current.allowed_exit_points),
    eligible_sale_modes: stringArrayFromRecord(mergedRecord, "eligible_sale_modes", current.eligible_sale_modes),
  };
}

export function contractRecordFromParsedJson(parsed: unknown): Record<string, unknown> | null {
  if (Array.isArray(parsed)) {
    return parsed.find((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") ?? null;
  }
  if (parsed && typeof parsed === "object") {
    const record = parsed as Record<string, unknown>;
    const wrapped = record.contract;
    if (wrapped && typeof wrapped === "object" && !Array.isArray(wrapped)) {
      return wrapped as Record<string, unknown>;
    }
    return record;
  }
  return null;
}

export function parseContractTextDraft(fileName: string, text: string): Record<string, unknown> {
  const record: Record<string, unknown> = {
    document_name: fileName,
    document_status: "STAGED_REVIEW_REQUIRED",
    source_reference: fileName,
  };
  const captureText = (key: string, labels: string[]) => {
    const pattern = new RegExp(`(?:^|\\n)\\s*(?:${labels.join("|")})\\s*[:\\-]\\s*([^\\r\\n]+)`, "i");
    const value = text.match(pattern)?.[1]?.trim();
    if (value) record[key] = value;
  };
  const captureNumber = (key: string, labels: string[]) => {
    const pattern = new RegExp(`(?:^|\\n)\\s*(?:${labels.join("|")})\\s*[:\\-]\\s*([0-9]+(?:\\.[0-9]+)?)`, "i");
    const value = text.match(pattern)?.[1];
    if (value !== undefined && Number.isFinite(Number(value))) record[key] = Number(value);
  };

  captureText("contract_id", ["contract id", "agreement id", "confirmation id"]);
  captureText("contract_name", ["contract name", "agreement", "confirmation"]);
  captureText("counterparty", ["counterparty", "seller", "buyer"]);
  captureText("contract_type", ["contract type", "agreement type"]);
  captureText("gas_year", ["gas year", "term"]);
  captureText("delivery_point_name", ["delivery point", "delivery hub"]);
  captureText("title_transfer_point", ["title transfer point", "title-transfer point", "transfer point"]);
  captureText("beach_delivery_point", ["beach delivery point", "beach", "landing point"]);
  captureText("index_basis", ["index basis", "price index", "pricing basis"]);
  captureText("terminal_access", ["terminal access", "terminal", "tso access"]);
  captureText("capacity_expiry", ["capacity expiry", "capacity end", "expiry"]);
  captureText("governing_law", ["governing law", "law"]);
  captureNumber("delivery_quantity_mwh_per_day", ["quantity", "daily quantity", "mwh per day", "mwh/d"]);
  captureNumber("contract_price_gbp_mwh", ["contract price", "price", "gbp/mwh"]);
  captureNumber("delivery_tolerance_pct", ["delivery tolerance", "tolerance"]);
  captureNumber("nomination_tolerance_pct", ["nomination tolerance"]);
  captureNumber("variable_cost_gbp_mwh", ["variable cost"]);
  captureNumber("regas_fee_gbp_mwh", ["regas fee", "regasification fee"]);
  captureNumber("fuel_loss_allowance_pct", ["fuel loss", "shrinkage"]);

  return record;
}

export function contractRecordFromImportedFile(fileName: string, text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text) as unknown;
    const record = contractRecordFromParsedJson(parsed);
    return record ? { document_name: fileName, document_status: "IMPORTED_JSON_DRAFT", ...record } : null;
  } catch {
    return parseContractTextDraft(fileName, text);
  }
}
