/**
 * Human-readable presentation of the reviewed transport vocabulary.
 *
 * The strict decoder in `contractPaymentTerms.ts` verifies the stored declaration against the
 * frozen backend spellings and preserves every value verbatim. This module is the read-only
 * display counterpart: it maps each reviewed spelling to its declared translation key, and
 * nothing else. It resolves no anchor, computes no date or amount, derives no field from
 * another, and never rewrites the stored value.
 *
 * The maps are typed against the decoder's own vocabularies, so a spelling the decoder accepts
 * cannot exist without a label (`npm run build` fails instead). A value the decoder's read
 * could not have produced is not given the vocabulary's meaning: the label lookup
 * returns null and the caller keeps the raw spelling, so an unknown runtime value is shown as
 * unverified transport text rather than silently assigned another meaning.
 */

import type {
  PaymentTermsAnchorEvent,
  PaymentTermsBusinessDayConvention,
  PaymentTermsCashFlowCategory,
  PaymentTermsOffsetDayKind,
} from "./contractPaymentTerms";

type Translate = (key: string) => string;

/** The four reviewed vocabularies of the declared document, one per displayed transport field. */
export type PaymentTermsVocabularyKind =
  | "cash_flow_category"
  | "anchor_event"
  | "offset_day_kind"
  | "business_day_convention";

/**
 * One translation key per reviewed spelling, exhaustive over the decoder's vocabulary.
 *
 * This is a display map only: the keys are never sent anywhere, and no transport value is
 * derived from a label.
 */
const VOCABULARY_LABEL_KEYS: {
  readonly cash_flow_category: Readonly<Record<PaymentTermsCashFlowCategory, string>>;
  readonly anchor_event: Readonly<Record<PaymentTermsAnchorEvent, string>>;
  readonly offset_day_kind: Readonly<Record<PaymentTermsOffsetDayKind, string>>;
  readonly business_day_convention: Readonly<Record<PaymentTermsBusinessDayConvention, string>>;
} = {
  cash_flow_category: {
    cargo_purchase: "contracts.payment_terms.category.cargo_purchase",
    cargo_sale: "contracts.payment_terms.category.cargo_sale",
    shipping: "contracts.payment_terms.category.shipping",
    transport: "contracts.payment_terms.category.transport",
    regas: "contracts.payment_terms.category.regas",
    storage: "contracts.payment_terms.category.storage",
    fuel: "contracts.payment_terms.category.fuel",
    demurrage: "contracts.payment_terms.category.demurrage",
    boil_off: "contracts.payment_terms.category.boil_off",
    other: "contracts.payment_terms.category.other",
  },
  anchor_event: {
    INVOICE_DATE: "contracts.payment_terms.anchor_event.invoice_date",
    DELIVERY_PERIOD_START: "contracts.payment_terms.anchor_event.delivery_period_start",
    DELIVERY_PERIOD_END: "contracts.payment_terms.anchor_event.delivery_period_end",
    METER_READ_DATE: "contracts.payment_terms.anchor_event.meter_read_date",
  },
  offset_day_kind: {
    CALENDAR_DAYS: "contracts.payment_terms.offset_day_kind.calendar_days",
    BUSINESS_DAYS: "contracts.payment_terms.offset_day_kind.business_days",
  },
  business_day_convention: {
    NONE: "contracts.payment_terms.business_day_convention.none",
    FOLLOWING: "contracts.payment_terms.business_day_convention.following",
    MODIFIED_FOLLOWING: "contracts.payment_terms.business_day_convention.modified_following",
    PRECEDING: "contracts.payment_terms.business_day_convention.preceding",
  },
};

/**
 * The map's own keys are the membership check: a spelling that is not a reviewed value of this
 * exact vocabulary is never given a key, so it can never borrow another field's meaning.
 */
function reviewedLabelKey<T extends string>(
  map: Readonly<Record<T, string>>,
  value: string,
): string | null {
  return Object.prototype.hasOwnProperty.call(map, value) ? map[value as T] : null;
}

/**
 * The declared translation key of one reviewed spelling, or null when the value is not a
 * reviewed spelling of that field's vocabulary.
 */
export function paymentTermVocabularyLabelKey(
  kind: PaymentTermsVocabularyKind,
  value: string,
): string | null {
  switch (kind) {
    case "cash_flow_category":
      return reviewedLabelKey(VOCABULARY_LABEL_KEYS.cash_flow_category, value);
    case "anchor_event":
      return reviewedLabelKey(VOCABULARY_LABEL_KEYS.anchor_event, value);
    case "offset_day_kind":
      return reviewedLabelKey(VOCABULARY_LABEL_KEYS.offset_day_kind, value);
    case "business_day_convention":
      return reviewedLabelKey(VOCABULARY_LABEL_KEYS.business_day_convention, value);
  }
}

/**
 * The reviewed label of one spelling, or the raw value when it is not reviewed.
 *
 * The raw fallback is deliberate: an unknown runtime value is displayed verbatim rather than
 * being coerced into a known label or another vocabulary's meaning.
 */
export function paymentTermVocabularyLabel(
  kind: PaymentTermsVocabularyKind,
  value: string,
  t: Translate,
): string {
  const key = paymentTermVocabularyLabelKey(kind, value);
  return key === null ? value : t(key);
}
