/**
 * Gas-desk unit conversion in the answer bar, with the units authority's own factors.
 *
 * The factors are not written here: they come from the server's units authority
 * (`domain/market/units.py` → `units_reference()`, served with `GET /api/analysis/ontology` as
 * `units`). This module only reads what is typed and applies those factors, so the bar and the
 * server cannot disagree. Until the reference has loaded, no conversion answer is given.
 *
 * Three kinds of conversion:
 * - **energy and volume**, and rates of them (`/h`, `/d`; `MW` is MWh per hour):
 *   `100 GWh to th`, `500 MW in GWh/d`, `20 mcm/d to GWh/d`;
 * - **volume to energy** only with a calorific value stated on the answer line: the one typed
 *   (`10 mcm to GWh at 11.2`) or the authority's assumed value, labelled as an assumption with
 *   its reference conditions;
 * - **prices** between quotations (`40 EUR/MWh to p/th`, `12 $/MMBtu in €/MWh`). A change of
 *   currency uses the latest ECB reference rate the product holds, and the answer line names
 *   that rate and its date. With no rate held the answer says so and converts nothing.
 */

import type { UnitsReferenceDTO } from "../../api/client.ts";
import { normalizeTyped, readNumber } from "./numbers.ts";

/** The ECB reference rates the product holds: units of currency per EUR, with value date. */
export interface FxHeld {
  source: string;
  rates: Partial<Record<string, { rate: number; date: string | null }>>;
}

export interface ConversionLine {
  /** A key into the answer bar's strings, with its values. */
  key: string;
  values: Record<string, string | number>;
}

export interface Conversion {
  kind: "energy" | "volume-energy" | "price";
  input: { value: number; unit: string };
  /** Null when the conversion could not be made (no FX rate held): `notes` says why. */
  value: number | null;
  unit: string;
  notes: ConversionLine[];
}

interface Quantity {
  dimension: "energy" | "volume";
  code: string;
  /** Hours the rate is over: 1 for /h, 24 for /d, null for an amount. */
  per: number | null;
}

interface PriceUnit {
  currency: string;
  divisor: number;
  energy: string;
  label: string;
}

const ENERGY_ALIASES: Record<string, string> = {
  kwh: "kWh", mwh: "MWh", gwh: "GWh", twh: "TWh", gj: "GJ", mj: "MJ",
  th: "th", therm: "th", therms: "th", mmbtu: "MMBtu",
  千瓦时: "kWh", 兆瓦时: "MWh", 吉瓦时: "GWh", 太瓦时: "TWh", 吉焦: "GJ",
  撒姆: "th", 色姆: "th", 百万英热: "MMBtu", 百万英热单位: "MMBtu",
};
const VOLUME_ALIASES: Record<string, string> = {
  m3: "m3", "m³": "m3", cm: "m3", mcm: "mcm", bcm: "bcm",
  立方米: "m3", 百万立方米: "mcm", 十亿立方米: "bcm",
};
const PER_ALIASES: Record<string, number> = {
  h: 1, hr: 1, hour: 1, 小时: 1, 时: 1,
  d: 24, day: 24, 天: 24, 日: 24,
};
/** Money words: the currency and its divisor (pence are a hundredth of a pound). */
const MONEY_ALIASES: Record<string, { currency: string; divisor: number }> = {
  eur: { currency: "EUR", divisor: 1 }, "€": { currency: "EUR", divisor: 1 }, euro: { currency: "EUR", divisor: 1 },
  欧元: { currency: "EUR", divisor: 1 },
  gbp: { currency: "GBP", divisor: 1 }, "£": { currency: "GBP", divisor: 1 }, 英镑: { currency: "GBP", divisor: 1 },
  p: { currency: "GBP", divisor: 100 }, pence: { currency: "GBP", divisor: 100 }, gbx: { currency: "GBP", divisor: 100 },
  便士: { currency: "GBP", divisor: 100 },
  usd: { currency: "USD", divisor: 1 }, $: { currency: "USD", divisor: 1 }, 美元: { currency: "USD", divisor: 1 },
};

function quantityUnit(raw: string, reference: UnitsReferenceDTO): Quantity | null {
  let text = raw.trim().toLowerCase().replace(/\s+per\s+/g, "/").replace(/\s+/g, "");
  if (text === "mw") return { dimension: "energy", code: "MWh", per: 1 };
  if (text === "gw") return { dimension: "energy", code: "GWh", per: 1 };
  let per: number | null = null;
  const slash = text.lastIndexOf("/");
  if (slash > 0) {
    const hours = PER_ALIASES[text.slice(slash + 1)];
    if (hours === undefined) return null;
    per = hours;
    text = text.slice(0, slash);
  } else {
    const zh = /^(.+?)每(天|日|小时)$/.exec(text);
    if (zh) {
      per = PER_ALIASES[zh[2]];
      text = zh[1];
    }
  }
  const energy = ENERGY_ALIASES[text];
  if (energy && reference.energy_in_mwh[energy] !== undefined) return { dimension: "energy", code: energy, per };
  const volume = VOLUME_ALIASES[text];
  if (volume && reference.volume_in_m3[volume] !== undefined) return { dimension: "volume", code: volume, per };
  return null;
}

function priceUnit(raw: string, reference: UnitsReferenceDTO): PriceUnit | null {
  const text = raw.trim().replace(/\s+/g, "");
  // The authority's own spellings and aliases first ("GBp/th" is pence: case decides there).
  const canonical = reference.price_units[text]
    ? text
    : reference.price_aliases[text.toUpperCase()] ??
      Object.keys(reference.price_units).find((code) => code.toUpperCase() === text.toUpperCase() && code !== "GBp/th");
  if (canonical && reference.price_units[canonical]) {
    const known = reference.price_units[canonical];
    return { currency: known.currency, divisor: known.divisor, energy: known.unit, label: canonical };
  }
  const slash = text.indexOf("/");
  if (slash <= 0) return null;
  const money = MONEY_ALIASES[text.slice(0, slash).toLowerCase()];
  const energy = ENERGY_ALIASES[text.slice(slash + 1).toLowerCase()];
  if (!money || !energy || reference.energy_in_mwh[energy] === undefined) return null;
  const label = money.divisor === 100 && money.currency === "GBP"
    ? `GBp/${energy}`
    : `${money.currency}/${energy}`;
  return { ...money, energy, label };
}

/** How a desk writes a unit: `p/th` for pence per therm, `m³` for cubic metres, `/d`. */
export function deskUnitLabel(code: string): string {
  return code
    .replace(/^GBp\/th$/, "p/th")
    .replace(/(^|\/)m3(?=$|\/)/g, "$1m³");
}

function quantityLabel(quantity: Quantity): string {
  if (quantity.per === 1 && quantity.code === "MWh") return "MW";
  const unit = deskUnitLabel(quantity.code);
  return quantity.per === null ? unit : `${unit}/${quantity.per === 1 ? "h" : "d"}`;
}

const CONNECTOR = /\s+(?:to|in|into|as|in\s+terms\s+of)\s+|\s*(?:->|→|=>|=|换算成|换算为|换成|转换为|转换成|转为|折合|合)\s*/i;
const GCV_CLAUSE = /\s*(?:at|@|按|热值)\s*(\d+(?:\.\d+)?)\s*(?:kwh\/m(?:3|³)|千瓦时\/立方米)?\s*/i;

/**
 * The conversion `raw` asks for, or null when it is not clearly one. `raw` reads
 * `<number> <unit> to <unit>`, optionally with `at <kWh/m³>` for a volume.
 */
export function convertQuery(
  raw: string,
  reference: UnitsReferenceDTO | null,
  fx: FxHeld | null,
): Conversion | null {
  if (!reference) return null;
  let text = normalizeTyped(raw).trim().replace(/[?？]$/, "").trim();
  let statedGcv: number | null = null;
  const gcv = GCV_CLAUSE.exec(text);
  if (gcv) {
    statedGcv = Number(gcv[1]);
    text = (text.slice(0, gcv.index) + " " + text.slice(gcv.index + gcv[0].length)).trim();
  }
  const number = readNumber(text);
  if (!number) return null;
  const rest = text.slice(number.length).trim();
  const parts = rest.split(CONNECTOR);
  if (parts.length !== 2 || !parts[0] || !parts[1]) return null;
  const [fromText, toText] = parts;
  const value = number.value;

  const fromPrice = priceUnit(fromText, reference);
  const toPrice = priceUnit(toText, reference);
  if (fromPrice && toPrice) return convertPrice(value, fromPrice, toPrice, reference, fx);
  if (fromPrice || toPrice) return null;

  const from = quantityUnit(fromText, reference);
  const to = quantityUnit(toText, reference);
  if (!from || !to) return null;
  // A rate converts only to a rate, an amount only to an amount.
  if ((from.per === null) !== (to.per === null)) return null;
  const rateFactor = from.per === null || to.per === null ? 1 : to.per / from.per;
  const base = (quantity: Quantity) =>
    quantity.dimension === "energy" ? reference.energy_in_mwh[quantity.code] : reference.volume_in_m3[quantity.code];
  const input = { value, unit: quantityLabel(from) };
  if (from.dimension === to.dimension) {
    return {
      kind: "energy",
      input,
      value: (value * base(from)) / base(to) * rateFactor,
      unit: quantityLabel(to),
      notes: [],
    };
  }
  if (statedGcv === null && gcv) return null;
  const assumption = reference.volume_to_energy;
  const [low, high] = assumption.valid_range_kwh_per_m3;
  const used = statedGcv ?? assumption.gcv_kwh_per_m3;
  if (used < low || used > high) {
    return {
      kind: "volume-energy",
      input,
      value: null,
      unit: quantityLabel(to),
      notes: [{ key: "answer.convert.gcv_range", values: { low, high } }],
    };
  }
  // kWh per m3 → MWh per m3 is a thousandth.
  const mwhPerM3 = used / 1000;
  const result = from.dimension === "volume"
    ? (value * base(from) * mwhPerM3) / base(to)
    : (value * base(from)) / mwhPerM3 / base(to);
  return {
    kind: "volume-energy",
    input,
    value: result * rateFactor,
    unit: quantityLabel(to),
    notes: [
      statedGcv === null
        ? { key: "answer.convert.gcv_assumed", values: { gcv: used, conditions: assumption.reference_conditions } }
        : { key: "answer.convert.gcv_stated", values: { gcv: used, conditions: assumption.reference_conditions } },
    ],
  };
}

function shortDate(iso: string | null): string {
  if (!iso) return "";
  const parsed = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

function convertPrice(
  value: number,
  from: PriceUnit,
  to: PriceUnit,
  reference: UnitsReferenceDTO,
  fx: FxHeld | null,
): Conversion {
  const input = { value, unit: deskUnitLabel(from.label) };
  // Price per MWh in the source currency, then per target energy unit.
  const perMwh = value / from.divisor / reference.energy_in_mwh[from.energy];
  const notes: ConversionLine[] = [];
  let inTarget = perMwh;
  if (from.currency !== to.currency) {
    const rateOf = (currency: string) => (currency === "EUR" ? { rate: 1, date: null } : fx?.rates[currency] ?? null);
    const source = rateOf(from.currency);
    const target = rateOf(to.currency);
    const missing = [from.currency, to.currency].filter((currency) => currency !== "EUR" && !fx?.rates[currency]);
    if (!source || !target) {
      return {
        kind: "price",
        input,
        value: null,
        unit: deskUnitLabel(to.label),
        notes: [{ key: "answer.convert.no_fx", values: { pairs: missing.map((c) => `EUR${c}`).join(", ") } }],
      };
    }
    inTarget = (perMwh / source.rate) * target.rate;
    for (const currency of [from.currency, to.currency]) {
      const held = fx?.rates[currency];
      if (currency !== "EUR" && held) {
        notes.push({
          key: "answer.convert.fx",
          values: { source: fx?.source ?? "ECB", date: shortDate(held.date), pair: `EUR${currency}`, rate: held.rate.toFixed(4) },
        });
      }
    }
  }
  return {
    kind: "price",
    input,
    value: inTarget * reference.energy_in_mwh[to.energy] * to.divisor,
    unit: deskUnitLabel(to.label),
    notes,
  };
}

/** The ECB rates a `GET /api/market/price-conversion` read reports as held. */
export function fxHeldFrom(
  conversion: { fx: Record<string, { rate: number; source?: string | null; value_dates?: string[] }>; fx_fixing?: { source_system?: string } } | null,
): FxHeld {
  const rates: FxHeld["rates"] = {};
  for (const [currency, entry] of Object.entries(conversion?.fx ?? {})) {
    if (entry && Number.isFinite(entry.rate) && entry.rate > 0) {
      const dates = entry.value_dates ?? [];
      rates[currency] = { rate: entry.rate, date: dates.length ? dates[dates.length - 1] : null };
    }
  }
  return { source: conversion?.fx_fixing?.source_system ?? "ECB", rates };
}
