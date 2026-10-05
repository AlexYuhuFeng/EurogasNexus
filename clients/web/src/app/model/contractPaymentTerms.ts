/**
 * Read-only presentation model for a stored contract's declared payment terms.
 *
 * The contract read carries the strictly decoded `contract-payment-terms/v1` document, `null`
 * for "not stated", or - from a deployment that predates the carrier - no field at all. Those
 * are three different facts and this module keeps them apart:
 *
 * * `declared` - the document is a canonical declaration this client can verify and is
 *   re-emitted verbatim: exact field sets at the document, item and date-specification levels;
 *   reviewed backend vocabulary spellings for the cash-flow category, flow direction, anchor
 *   event, offset day kind, business-day convention and date kind; the declared storage guards
 *   (at most 1,000 items, 2,000 characters per reference or item id, at most a 36,525-day
 *   offset); a real canonical plain `YYYY-MM-DD` calendar date; and a calendar reference
 *   required exactly when a business-day count or a roll convention needs it and refused when
 *   nothing uses it;
 * * `not_declared` - the response said `null`: nothing is recorded for this resource;
 * * `unavailable` - the response carried no declaration field: the client cannot state whether
 *   anything is recorded;
 * * `malformed` - the field is present but this client cannot verify it as a canonical
 *   declaration (an unknown schema version, an unexpected or missing field, an unknown
 *   vocabulary spelling, an oversized value, an impossible date, a missing or unused
 *   calendar). It is never coerced into an empty or partial schedule and never rendered.
 *
 * Verification here is a transport-shape gate only: it refuses a document the strict backend
 * decoder could not have produced, and it keeps every verified string exactly as declared. The
 * module resolves nothing: no anchor fact, calendar, offset, day count or amount is computed,
 * and the ISO date string is only validated as a real calendar date so a broken stored value
 * is refused rather than presented as a payable date. Date resolution and valuation remain the
 * shared backend engine's responsibility (see
 * `docs/engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md`).
 */

import type { PaymentScheduleItemDTO, PaymentTermsDTO } from "@/api/client";

/** The only declaration schema this client can verify. */
export const CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION = "contract-payment-terms/v1";

/**
 * Declared storage guards of the canonical document, mirrored from the backend domain module
 * as transport-shape limits: this client computes nothing from them, it only refuses a
 * document the strict server-side decoder could not have produced.
 */
const MAX_PAYMENT_SCHEDULE_ITEMS = 1_000;
const MAX_PAYMENT_TERMS_TEXT_LENGTH = 2_000;
const MAX_ANCHOR_OFFSET_DAYS = 36_525;

/** Exact field sets of the canonical document and of each declared date shape. */
const DOCUMENT_FIELDS = ["schema_version", "quantity_basis_reference", "items"] as const;
const ITEM_FIELDS = [
  "item_id",
  "cash_flow_category",
  "flow_direction",
  "source_reference",
  "date_specification",
] as const;
const EXPLICIT_DATE_FIELDS = ["kind", "final_payable_date", "source_reference"] as const;
const ANCHORED_RULE_FIELDS = [
  "kind",
  "anchor_event",
  "anchor_offset_days",
  "offset_day_kind",
  "business_day_convention",
  "calendar_reference",
  "source_reference",
] as const;

/**
 * The reviewed backend vocabulary spellings this client can verify.
 *
 * These are the frozen transport values of the shared domain enums, not a client taxonomy:
 * nothing here is translated, defaulted or derived from another field, and a value outside the
 * reviewed vocabulary makes the declaration unverifiable instead of presenting an invented
 * meaning.
 *
 * The exported spellings are the single source of the decoder's membership and of the
 * exhaustive presentation label maps, so every spelling this client verifies has a declared
 * label and a label map can never cover a spelling the decoder refuses.
 */
export const PAYMENT_TERMS_CASH_FLOW_CATEGORIES = [
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
] as const;
export type PaymentTermsCashFlowCategory = (typeof PAYMENT_TERMS_CASH_FLOW_CATEGORIES)[number];

export const PAYMENT_TERMS_ANCHOR_EVENTS = [
  "INVOICE_DATE",
  "DELIVERY_PERIOD_START",
  "DELIVERY_PERIOD_END",
  "METER_READ_DATE",
] as const;
export type PaymentTermsAnchorEvent = (typeof PAYMENT_TERMS_ANCHOR_EVENTS)[number];

export const PAYMENT_TERMS_OFFSET_DAY_KINDS = ["CALENDAR_DAYS", "BUSINESS_DAYS"] as const;
export type PaymentTermsOffsetDayKind = (typeof PAYMENT_TERMS_OFFSET_DAY_KINDS)[number];

export const PAYMENT_TERMS_BUSINESS_DAY_CONVENTIONS = [
  "NONE",
  "FOLLOWING",
  "MODIFIED_FOLLOWING",
  "PRECEDING",
] as const;
export type PaymentTermsBusinessDayConvention =
  (typeof PAYMENT_TERMS_BUSINESS_DAY_CONVENTIONS)[number];

/** Stable reasons a present declaration was refused; never a caller-supplied value. */
export type PaymentTermsMalformedReason =
  | "not_an_object"
  | "document_fields"
  | "schema_version"
  | "quantity_basis"
  | "items"
  | "schedule_empty"
  | "schedule_bounds"
  | "item"
  | "item_fields"
  | "item_id"
  | "item_id_duplicate"
  | "category"
  | "direction"
  | "item_evidence"
  | "date_specification"
  | "date_kind"
  | "specification_fields"
  | "date_value"
  | "specification_evidence"
  | "anchor_event"
  | "anchor_offset"
  | "offset_day_kind"
  | "business_day_convention"
  | "calendar_reference";

/**
 * What one contract read established about the stored declaration.
 *
 * `unavailable` and `not_declared` are deliberately distinct: only `not_declared` supports the
 * statement "no terms are recorded". `malformed` carries a stable reason code for tests and
 * diagnostics and is never rendered as evidence content.
 */
export type PaymentTermsReadState =
  | { readonly state: "declared"; readonly terms: PaymentTermsDTO }
  | { readonly state: "not_declared" }
  | { readonly state: "unavailable" }
  | { readonly state: "malformed"; readonly reason: PaymentTermsMalformedReason };

function malformed(reason: PaymentTermsMalformedReason): PaymentTermsReadState {
  return { state: "malformed", reason };
}

/** One JSON object value; a JSON array is not an object here, as in the backend decoder. */
function isPlainObjectValue(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Whether a mapping's own field set is exactly the schema's: no extra and no missing field.
 *
 * Mirrors the backend decoder, which refuses any mapping whose field set is not exactly the
 * canonical one, so an unknown field can never ride into the rendered evidence.
 */
function exactFieldSet(record: Record<string, unknown>, expected: readonly string[]): boolean {
  if (Object.keys(record).length !== expected.length) return false;
  return expected.every((field) => Object.prototype.hasOwnProperty.call(record, field));
}

/**
 * One non-blank reference or item id inside the declared storage bound, preserved exactly.
 *
 * The bound is the backend's storage guard, counted in characters (code points), so the same
 * declaration the strict server-side decoder accepts is accepted here - nothing is trimmed,
 * normalised or otherwise rewritten.
 */
function boundedEvidence(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.trim().length > 0 &&
    [...value].length <= MAX_PAYMENT_TERMS_TEXT_LENGTH
  );
}

/** One reviewed vocabulary spelling; the value itself is never transformed or defaulted. */
function knownSpelling(value: unknown, known: readonly string[]): value is string {
  return typeof value === "string" && known.includes(value);
}

function isLeapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/**
 * Whether a value is a real canonical plain `YYYY-MM-DD` calendar date.
 *
 * A transport check, not date resolution: it verifies the declared spelling and that the day
 * exists in the proleptic Gregorian calendar (leap years included, year 0000 refused), so
 * `2026-02-31` is refused rather than presented as a payable date. No timezone, clock, anchor
 * or offset arithmetic is involved, and the string is displayed exactly as declared.
 */
function plainIsoDate(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (year < 1 || month < 1 || month > 12) return false;
  const lastDay = month === 2 && isLeapYear(year) ? 29 : DAYS_IN_MONTH[month - 1];
  return day >= 1 && day <= lastDay;
}

/**
 * Decode the declaration field of one stored-contract response.
 *
 * Presence is read with `hasOwnProperty`: an absent field is `unavailable`, while an explicit
 * `null` is `not_declared`. The two must not collapse, because only one of them supports the
 * statement that nothing is recorded.
 */
export function paymentTermsReadFromRecord(
  record: Readonly<Record<string, unknown>>,
): PaymentTermsReadState {
  if (!Object.prototype.hasOwnProperty.call(record, "payment_terms")) {
    return { state: "unavailable" };
  }
  return paymentTermsReadFromValue(record.payment_terms);
}

/**
 * Decode one declaration value into the client's read state.
 *
 * Strict on the declared canonical shape - the same exact field sets, reviewed vocabulary
 * spellings, storage guards, real plain date and calendar requirement the backend's decoder
 * enforces - and liberal on nothing else: a document this client cannot verify is `malformed`,
 * so no partial schedule, invented default or empty list can ever be presented as the stored
 * declaration.
 */
export function paymentTermsReadFromValue(value: unknown): PaymentTermsReadState {
  if (value === null) return { state: "not_declared" };
  if (!isPlainObjectValue(value)) return malformed("not_an_object");
  if (!exactFieldSet(value, DOCUMENT_FIELDS)) return malformed("document_fields");
  if (value.schema_version !== CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION) {
    return malformed("schema_version");
  }
  if (!boundedEvidence(value.quantity_basis_reference)) return malformed("quantity_basis");
  const rawItems = value.items;
  if (!Array.isArray(rawItems)) return malformed("items");
  if (rawItems.length === 0) return malformed("schedule_empty");
  if (rawItems.length > MAX_PAYMENT_SCHEDULE_ITEMS) return malformed("schedule_bounds");
  const items: PaymentScheduleItemDTO[] = [];
  const seenItemIds = new Set<string>();
  for (const rawItem of rawItems) {
    const decoded = decodeScheduleItem(rawItem);
    if (typeof decoded === "string") return malformed(decoded);
    if (seenItemIds.has(decoded.item_id)) return malformed("item_id_duplicate");
    seenItemIds.add(decoded.item_id);
    items.push(decoded);
  }
  return {
    state: "declared",
    terms: {
      schema_version: CONTRACT_PAYMENT_TERMS_SCHEMA_VERSION,
      quantity_basis_reference: value.quantity_basis_reference,
      items,
    },
  };
}

/** One decoded schedule item, or the stable reason it was refused. */
function decodeScheduleItem(
  raw: unknown,
): PaymentScheduleItemDTO | PaymentTermsMalformedReason {
  if (!isPlainObjectValue(raw)) return "item";
  if (!exactFieldSet(raw, ITEM_FIELDS)) return "item_fields";
  const itemId = raw.item_id;
  if (!boundedEvidence(itemId)) return "item_id";
  const category = raw.cash_flow_category;
  if (!knownSpelling(category, PAYMENT_TERMS_CASH_FLOW_CATEGORIES)) return "category";
  const direction = raw.flow_direction;
  if (direction !== "INFLOW" && direction !== "OUTFLOW") return "direction";
  const itemEvidence = raw.source_reference;
  if (!boundedEvidence(itemEvidence)) return "item_evidence";
  const specification = raw.date_specification;
  if (!isPlainObjectValue(specification)) return "date_specification";
  const kind = specification.kind;
  if (kind !== "EXPLICIT_DATE" && kind !== "ANCHORED_RULE") return "date_kind";
  if (kind === "EXPLICIT_DATE") {
    if (!exactFieldSet(specification, EXPLICIT_DATE_FIELDS)) return "specification_fields";
    if (!plainIsoDate(specification.final_payable_date)) return "date_value";
    const dateEvidence = specification.source_reference;
    if (!boundedEvidence(dateEvidence)) return "specification_evidence";
    return {
      item_id: itemId,
      cash_flow_category: category,
      flow_direction: direction,
      source_reference: itemEvidence,
      date_specification: {
        kind: "EXPLICIT_DATE",
        final_payable_date: specification.final_payable_date,
        source_reference: dateEvidence,
      },
    };
  }
  if (!exactFieldSet(specification, ANCHORED_RULE_FIELDS)) return "specification_fields";
  const anchorEvent = specification.anchor_event;
  if (!knownSpelling(anchorEvent, PAYMENT_TERMS_ANCHOR_EVENTS)) return "anchor_event";
  const offset = specification.anchor_offset_days;
  if (
    typeof offset !== "number" ||
    !Number.isInteger(offset) ||
    offset < 0 ||
    offset > MAX_ANCHOR_OFFSET_DAYS
  ) {
    return "anchor_offset";
  }
  const dayKind = specification.offset_day_kind;
  if (!knownSpelling(dayKind, PAYMENT_TERMS_OFFSET_DAY_KINDS)) return "offset_day_kind";
  const convention = specification.business_day_convention;
  if (!knownSpelling(convention, PAYMENT_TERMS_BUSINESS_DAY_CONVENTIONS)) {
    return "business_day_convention";
  }
  // The calendar requirement is the declared rule's own: a business-day count or a roll
  // convention needs an explicit calendar reference, and a rule that needs none must not
  // declare one. Nothing is defaulted in either direction.
  const rawCalendar = specification.calendar_reference;
  const needsCalendar = dayKind === "BUSINESS_DAYS" || convention !== "NONE";
  let calendar: string | null;
  if (needsCalendar) {
    if (!boundedEvidence(rawCalendar)) return "calendar_reference";
    calendar = rawCalendar;
  } else {
    if (rawCalendar !== null) return "calendar_reference";
    calendar = null;
  }
  const ruleEvidence = specification.source_reference;
  if (!boundedEvidence(ruleEvidence)) return "specification_evidence";
  return {
    item_id: itemId,
    cash_flow_category: category,
    flow_direction: direction,
    source_reference: itemEvidence,
    date_specification: {
      kind: "ANCHORED_RULE",
      anchor_event: anchorEvent,
      anchor_offset_days: offset,
      offset_day_kind: dayKind,
      business_day_convention: convention,
      calendar_reference: calendar,
      source_reference: ruleEvidence,
    },
  };
}
