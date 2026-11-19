/**
 * The reviewed-tariff entry form's logic (TariffEntryPanel): the units the pricing reads, a new
 * draft for the current gas year, and what the draft still needs. Pure, so it is tested
 * without a browser.
 */

/** Units the pricing reads (domain/route_cost/tariff_units.py), as operators publish them. */
export const ENTRY_UNITS: Record<string, string[]> = {
  EUR: ["EUR/(kWh/h)/y", "EUR/(kWh/d)/y", "EUR/(kWh/h)/d", "EUR/(kWh/h)/m", "EUR/(kWh/h)/q", "EUR/(kWh/h)/h", "EUR/MWh"],
  GBP: ["p/kWh/d", "GBP/(kWh/d)/y", "GBP/(kWh/h)/y", "GBP/MWh"],
  DKK: ["DKK/(kWh/h)/y"],
  CHF: ["CHF/(kWh/h)/y"],
  CZK: ["CZK/(kWh/d)/y"],
};

export interface Draft {
  point_key: string | null;
  operator_key: string | null;
  direction: "ENTRY" | "EXIT";
  capacity_product: string;
  firmness: string;
  tariff_value: string;
  currency: string;
  unit: string;
  valid_from: string;
  valid_to: string;
  published_status: "FINAL" | "INDICATIVE";
  source_url: string;
  published_on: string;
  source_location: string;
  note: string;
}

function gasYearBounds(today = new Date()): { from: string; to: string } {
  const year = today.getUTCMonth() >= 9 ? today.getUTCFullYear() : today.getUTCFullYear() - 1;
  return { from: `${year}-10-01`, to: `${year + 1}-09-30` };
}

export function emptyDraft(): Draft {
  const { from, to } = gasYearBounds();
  return {
    point_key: null,
    operator_key: null,
    direction: "EXIT",
    capacity_product: "ANNUAL",
    firmness: "FIRM",
    tariff_value: "",
    currency: "EUR",
    unit: "EUR/(kWh/h)/y",
    valid_from: from,
    valid_to: to,
    published_status: "FINAL",
    source_url: "",
    published_on: "",
    source_location: "",
    note: "",
  };
}

/** What the form still needs before it can be sent (keys of the missing fields). */
export function draftMissing(draft: Draft): string[] {
  const missing: string[] = [];
  if (!draft.point_key) missing.push("point");
  if (!draft.operator_key) missing.push("operator");
  if (draft.tariff_value.trim() === "" || !Number.isFinite(Number(draft.tariff_value)) || Number(draft.tariff_value) < 0) missing.push("value");
  if (!draft.source_url.startsWith("https://")) missing.push("source_url");
  if (!draft.published_on) missing.push("published_on");
  if (!draft.source_location.trim()) missing.push("source_location");
  if (!draft.valid_from || !draft.valid_to || draft.valid_to < draft.valid_from) missing.push("validity");
  return missing;
}
