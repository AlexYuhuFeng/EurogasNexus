/**
 * Contract price terms (`price-terms/v1`, docs/product/CONTRACT_TYPES.md slice 2): the form a
 * supply agreement's price is edited in, and the request that saves it with the quantity as
 * written. The server validates the terms and prices them (`GET /api/contracts/{id}/price`);
 * this module only shapes the form and the request. Pure.
 */

export const PRICE_BASES = ["fixed", "index", "formula"] as const;
export type PriceBasis = (typeof PRICE_BASES)[number];
export const PRICE_UNITS = ["EUR/MWh", "GBp/th", "GBP/MWh", "USD/MMBtu"] as const;
export const QUANTITY_UNITS = ["MWh/d", "th/d", "kWh/h"] as const;
export const INDICES = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "PVB", "CEGH", "HH", "BRENT", "JKM"] as const;
export const PRODUCTS = ["month_ahead", "day_ahead", "bom", "weekend", "pricing_month"] as const;
export const AVERAGING = ["month_before_delivery", "delivery_day", "delivery_month", "last_n_trading_days", "pricing_month"] as const;

export interface IndexDraft {
  index: string;
  product: string;
  averaging: string;
  n_days: string;
  publication: string;
}

export interface PriceDraft {
  basis: PriceBasis;
  unit: string;
  fixed_price: string;
  index: IndexDraft;
  premium: string;
  components: Array<{ index: IndexDraft; weight: string }>;
  constant: string;
  cap: string;
  floor: string;
  quantity: string;
  quantity_unit: string;
}

const blankIndex = (index = "TTF"): IndexDraft => ({ index, product: "month_ahead", averaging: "month_before_delivery", n_days: "", publication: "" });

/** A supply agreement's draft: NBP contracts start in p/th and th/d, the rest in EUR/MWh and MWh/d. */
export function newPriceDraft(nbp: boolean): PriceDraft {
  return {
    basis: "fixed",
    unit: nbp ? "GBp/th" : "EUR/MWh",
    fixed_price: "",
    index: blankIndex(nbp ? "NBP" : "TTF"),
    premium: "0",
    components: [{ index: { ...blankIndex("HH"), product: "pricing_month", averaging: "pricing_month" }, weight: "" }],
    constant: "0",
    cap: "",
    floor: "",
    quantity: "",
    quantity_unit: nbp ? "th/d" : "MWh/d",
  };
}

const text = (value: unknown) => (value === null || value === undefined ? "" : String(value));

function indexDraft(value: unknown): IndexDraft {
  const index = (value ?? {}) as Record<string, unknown>;
  return {
    index: text(index.index) || "TTF",
    product: text(index.product) || "month_ahead",
    averaging: text(index.averaging) || "month_before_delivery",
    n_days: text(index.n_days),
    publication: text(index.publication),
  };
}

/** A stored `supply-gsa/v1` block (or none) back into the form. */
export function priceDraftFrom(block: Record<string, unknown> | null | undefined, nbp: boolean): PriceDraft {
  const draft = newPriceDraft(nbp);
  if (!block) return draft;
  const terms = (block.price_terms ?? null) as Record<string, unknown> | null;
  if (block.quantity !== undefined && block.quantity !== null) draft.quantity = text(block.quantity);
  if (block.quantity_unit) draft.quantity_unit = text(block.quantity_unit);
  if (!terms) return draft;
  draft.basis = (text(terms.basis) as PriceBasis) || "fixed";
  draft.unit = text(terms.unit) || draft.unit;
  draft.fixed_price = text(terms.fixed_price);
  if (terms.index) draft.index = indexDraft(terms.index);
  draft.premium = text(terms.premium) || "0";
  const components = Array.isArray(terms.components) ? terms.components : [];
  if (components.length) {
    draft.components = components.map((item) => ({ index: indexDraft((item as Record<string, unknown>).index), weight: text((item as Record<string, unknown>).weight) }));
  }
  draft.constant = text(terms.constant) || "0";
  draft.cap = text(terms.cap);
  draft.floor = text(terms.floor);
  return draft;
}

function num(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function indexTerms(draft: IndexDraft): Record<string, unknown> {
  return {
    index: draft.index,
    product: draft.product,
    averaging: draft.averaging,
    n_days: draft.averaging === "last_n_trading_days" ? num(draft.n_days) : null,
    publication: draft.publication.trim() || null,
  };
}

/** The `supply-gsa/v1` block from the form, and what is still needed (field keys). */
export function gsaBlockFromDraft(draft: PriceDraft): { block: Record<string, unknown> | null; missing: string[] } {
  const missing: string[] = [];
  const price: Record<string, unknown> = { schema: "price-terms/v1", basis: draft.basis, unit: draft.unit };
  if (draft.basis === "fixed") {
    if (num(draft.fixed_price) === null) missing.push("fixed_price");
    price.fixed_price = num(draft.fixed_price);
  } else if (draft.basis === "index") {
    price.index = indexTerms(draft.index);
    price.premium = num(draft.premium) ?? 0;
    if (draft.index.averaging === "last_n_trading_days" && num(draft.index.n_days) === null) missing.push("n_days");
  } else {
    const components = draft.components.filter((item) => num(item.weight) !== null);
    if (!components.length) missing.push("weight");
    price.components = components.map((item) => ({ index: indexTerms(item.index), weight: num(item.weight) }));
    price.constant = num(draft.constant) ?? 0;
  }
  price.cap = num(draft.cap);
  price.floor = num(draft.floor);
  const block: Record<string, unknown> = {
    schema: "supply-gsa/v1",
    quantity: num(draft.quantity),
    quantity_unit: draft.quantity_unit,
    price_terms: price,
  };
  return { block: missing.length ? null : block, missing };
}

/** Fields of a stored supply agreement the write takes back unchanged (all but the block). */
const KEPT = [
  "contract_id", "contract_name", "resource_type", "delivery_point_name", "gas_year",
  "delivery_quantity_mwh_per_day", "contract_price_gbp_mwh", "contract_price_currency",
  "settlement_frequency", "upstream_payment_lag_days", "screen_sale_cash_lag_days",
  "delivery_tolerance_pct", "nomination_tolerance_pct", "tolerance_risk_allowance_gbp_mwh",
  "annual_financing_rate_pct", "owned_entry_capacity_mwh_per_day", "owned_exit_capacity_mwh_per_day",
  "allowed_exit_points", "eligible_sale_modes", "variable_cost_gbp_mwh", "regas_fee_gbp_mwh",
  "fuel_loss_allowance_pct", "notes", "unmodelled_terms",
] as const;

/**
 * The request that saves a supply agreement's price terms and quantity as written: the stored
 * row as read (so nothing else changes), the kind stated, the block, and the edit token read
 * with it (a stale read is refused, never overwritten).
 */
export function gsaPriceBody(stored: Record<string, unknown>, block: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const key of KEPT) if (stored[key] !== undefined) body[key] = stored[key];
  body.contract_kind = "SUPPLY_GSA";
  body.kind_terms = block;
  body.expected_edit_token = stored.edit_token ?? null;
  return body;
}

/** Delivery months a contract runs in (at most `limit`), from its period. */
export function monthsBetween(first: string, last: string | null, limit = 18): string[] {
  const out: string[] = [];
  let year = Number(first.slice(0, 4));
  let month = Number(first.slice(5, 7));
  const end = last ? Number(last.slice(0, 4)) * 12 + Number(last.slice(5, 7)) : Infinity;
  while (out.length < limit && year * 12 + month <= end) {
    out.push(`${year}-${String(month).padStart(2, "0")}`);
    month += 1;
    if (month > 12) { month = 1; year += 1; }
  }
  return out;
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** The price terms in words, in the reader's language (the server's words are English). */
export function priceWords(terms: Record<string, unknown> | null | undefined, t: Translate): string | null {
  if (!terms) return null;
  const unit = String(terms.unit ?? "").replace("GBp/th", "p/th");
  const n = (value: unknown) => Number(value ?? 0);
  const signed = (value: number) => `${value < 0 ? "−" : "+"} ${Math.abs(value).toLocaleString("en-GB", { maximumFractionDigits: 4 })}`;
  const indexName = (index: Record<string, unknown>) => {
    const code = String(index.index ?? "");
    const name = code === "HH" || code === "BRENT" ? t(`contracts.price.index_name.${code}`) : code;
    const product = t(`contracts.price.product_name.${String(index.product ?? "month_ahead")}`);
    const averaging = t(`contracts.price.averaging_name.${String(index.averaging ?? "month_before_delivery")}`).replace("N", String(index.n_days ?? "N"));
    return t("contracts.price.words.index", { name, product, averaging });
  };
  let words: string;
  if (terms.basis === "fixed") {
    words = t("contracts.price.words.fixed", { price: n(terms.fixed_price).toLocaleString("en-GB", { maximumFractionDigits: 4 }), unit });
  } else if (terms.basis === "index") {
    words = `${indexName((terms.index ?? {}) as Record<string, unknown>)} ${signed(n(terms.premium))} ${unit}`;
  } else {
    const components = Array.isArray(terms.components) ? terms.components : [];
    const parts = components.map((item) => {
      const component = item as Record<string, unknown>;
      return `${n(component.weight)} × ${indexName((component.index ?? {}) as Record<string, unknown>)}`;
    });
    words = `${parts.join(" + ")} ${signed(n(terms.constant))} ${unit}`;
  }
  if (terms.floor !== null && terms.floor !== undefined && terms.cap !== null && terms.cap !== undefined) {
    words += t("contracts.price.words.collar", { floor: n(terms.floor), cap: n(terms.cap), unit });
  } else if (terms.cap !== null && terms.cap !== undefined) {
    words += t("contracts.price.words.cap", { cap: n(terms.cap), unit });
  } else if (terms.floor !== null && terms.floor !== undefined) {
    words += t("contracts.price.words.floor", { floor: n(terms.floor), unit });
  }
  return words;
}
