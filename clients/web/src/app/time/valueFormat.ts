/**
 * Figures in the reader's reporting currency and energy unit, beside the native figure
 * (design basis G1-G7). The sibling of timeFormat.ts: one place that says how a number reads.
 *
 * - The native figure is always primary where the desk trades; a preference never replaces it.
 * - A converted value is only ever one the server converted (`/api/market/normalise`,
 *   `/api/market/fx-forward`): this module holds no factor and no rate of its own.
 * - Never silent: the converted text always carries the rate, its date and the method.
 * - Some figures are never converted (G7): contract terms as signed, tariffs as published,
 *   frozen decision evidence. Limits are tested in their own currency; a converted limit is a
 *   secondary view only.
 * - A total over mixed currencies is shown only converted, with the conversion line; a total that
 *   would mix simulated and non-simulated figures is refused.
 */
import type { FxForwardDTO, NormalisedQuantityDTO, NormalisedValueDTO } from "../../api/comparablePrices.ts";
import { formatGasDay, formattingLocale } from "./timeFormat.ts";

export type Translate = (key: string, options?: Record<string, unknown>) => string;

/** What a figure is, for the conversion rules (G7). */
export type FigureSubject =
  | "price"
  | "position"
  | "pnl"
  | "exposure"
  | "limit"
  | "total"
  | "contract_term"
  | "tariff"
  | "frozen_evidence";

/** G7: shown as signed, published or frozen; never converted, not even as a secondary value. */
export const NEVER_CONVERTED: readonly FigureSubject[] = ["contract_term", "tariff", "frozen_evidence"];

/** Subjects whose converted value is a visible second line, not a hover (G3 reporting contexts). */
export const REPORTING_SUBJECTS: readonly FigureSubject[] = ["pnl", "total", "limit", "exposure"];

export const ENERGY_UNITS = ["MWh", "th", "MMBtu", "GJ"] as const;
export type EnergyUnit = (typeof ENERGY_UNITS)[number];

/** Mirrors REPORTING_CURRENCIES in domain/settings/preferences.py (the ECB reference table). */
export const REPORTING_CURRENCIES = [
  "EUR", "USD", "GBP", "CHF", "NOK", "SEK", "DKK", "PLN", "CZK", "HUF", "RON", "JPY",
  "CNY", "HKD", "SGD", "KRW", "INR", "AUD", "NZD", "CAD", "BRL", "MXN", "ZAR", "TRY",
  "ILS", "ISK", "IDR", "MYR", "PHP", "THB",
] as const;

export interface DisplayPreference {
  reportingCurrency: string;
  energyUnit: EnergyUnit;
}

export const DEFAULT_DISPLAY_PREFERENCE: DisplayPreference = { reportingCurrency: "EUR", energyUnit: "MWh" };

export function isEnergyUnit(value: unknown): value is EnergyUnit {
  return typeof value === "string" && (ENERGY_UNITS as readonly string[]).includes(value);
}

export function isReportingCurrency(value: unknown): value is string {
  return typeof value === "string" && (REPORTING_CURRENCIES as readonly string[]).includes(value);
}

/** Whether `subject` may carry a converted value at all. */
export function conversionAllowed(subject: FigureSubject): boolean {
  return !NEVER_CONVERTED.includes(subject);
}

/** "p/th" → GBP; "EUR/MWh" → EUR; "USD/MMBtu" → USD; a bare currency code → itself. */
export function currencyOfUnit(unit: string): string | null {
  const text = unit.trim();
  if (/^p\s*\/\s*th(erm)?$/i.test(text) || /^GBp\b/.test(text)) return "GBP";
  const match = /^([A-Z]{3})(?:\s*\/|$)/.exec(text);
  return match ? match[1] : null;
}

/** "EUR/MWh" → MWh; "p/th" → th; a bare currency → null. */
export function energyOfUnit(unit: string): string | null {
  const match = /\/\s*([A-Za-z]+)$/.exec(unit.trim());
  if (!match) return null;
  const code = match[1];
  if (/^therm$/i.test(code) || code === "th") return "th";
  if (/^mmbtu$/i.test(code)) return "MMBtu";
  return code;
}

/**
 * The unit a price reads in for this reader ("GBP/MWh" for a p/th price and EUR, MWh), or null
 * when the native unit already is the reader's.
 */
export function targetPriceUnit(nativeUnit: string, preference: DisplayPreference): string | null {
  const currency = currencyOfUnit(nativeUnit);
  const energy = energyOfUnit(nativeUnit);
  if (!currency || !energy) return null;
  if (currency === preference.reportingCurrency && energy === preference.energyUnit) return null;
  return `${preference.reportingCurrency}/${preference.energyUnit}`;
}

/**
 * The unit a quantity reads in for this reader ("th/d" for "MWh/d" and therms), or null when it
 * already is, or when it is not an energy amount (a volume needs a stated heating value).
 */
export function targetQuantityUnit(nativeUnit: string, preference: DisplayPreference): string | null {
  const match = /^\s*(MWh|GWh|TWh|kWh|th|therm|MMBtu|GJ)\s*(?:\/\s*(d|h))?\s*$/i.exec(nativeUnit);
  if (!match) return null;
  const amount = /^therm$/i.test(match[1]) ? "th" : match[1];
  if (amount === preference.energyUnit) return null;
  return match[2] ? `${preference.energyUnit}/${match[2].toLowerCase()}` : preference.energyUnit;
}

/** A converted quantity: the figure, and that it is the units authority's exact factor. */
export function convertedQuantityText(result: NormalisedQuantityDTO, language: string, t: Translate): ConvertedText {
  const digits = Math.abs(result.value) >= 100 ? 0 : 2;
  const figure = `${formatAmount(result.value, language, digits)} ${result.unit}`;
  const heating = result.normalisation.heating_value;
  return {
    text: heating
      ? t("convert.quantity_heating", { figure, gcv: formatAmount(heating.gcv_kwh_per_m3, language, 2) })
      : t("convert.quantity", { figure }),
    figure,
    simulated: result.simulated,
    refused: false,
  };
}

/** The reporting currency for an amount in `currency`, or null when no conversion is due. */
export function targetCurrency(currency: string, preference: DisplayPreference): string | null {
  const code = currency.trim().toUpperCase();
  return /^[A-Z]{3}$/.test(code) && code !== preference.reportingCurrency ? preference.reportingCurrency : null;
}

/** A number in the app's language, never the browser's locale; a true minus, as on the board. */
export function formatAmount(value: number, language: string, digits = 0): string {
  return new Intl.NumberFormat(formattingLocale(language), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
    .format(value)
    .replace(/^-/, "\u2212");
}

/** Decimals a gas price reads in, as on the board. */
export const PRICE_DIGITS = 3;

// ---------------------------------------------------------------------------------------------
// One formatter per measure (UX R3, P-20). A component never writes `toFixed` for a figure a
// person reads: it names the measure, and this table gives the decimals, the sign rule and the
// grouping. Every result writes a true minus (U+2212), a space between the number and its unit
// and a space before % (NIST SP 811 §7). tests/numberFormatUsage.test.ts fails on a new
// `toFixed(` under components/.

export type Measure =
  /** A quoted gas price in the hub's quotation (EUR/MWh, p/th, USD/MMBtu), as on the board. */
  | "price"
  /** A signed change of a price (tick, against the close). */
  | "change"
  /** A spread between two prices, always signed. */
  | "spread"
  /** A value per unit that is not a quoted gas price: route cost, margin, power, carbon, spark spread. */
  | "unit_value"
  /** A quantity of energy or volume (MWh, GWh/d, mcm/d). */
  | "volume"
  /** Profit and loss in a currency, always signed. */
  | "pnl"
  /** A share or fill level. */
  | "percent"
  /** A change in percentage points or a percentage change, always signed. */
  | "percent_change"
  /** An exchange rate. */
  | "fx_rate"
  /** A published tariff, at the precision the operator publishes. */
  | "tariff"
  /** An air temperature. */
  | "temperature"
  /** A latitude or longitude in degrees. */
  | "coordinate"
  /** A statistic without a unit (R², a coefficient). */
  | "ratio";

interface MeasureRule {
  decimals: number;
  /** `always`: + before a positive value; `negative`: only the minus. Zero never has a sign. */
  sign: "always" | "negative";
  /** Thousands separators in the app's language (quantities and money, not prices). */
  grouping: boolean;
  /** The unit when the measure has one of its own. */
  unit?: string;
}

export const MEASURES: Readonly<Record<Measure, MeasureRule>> = {
  price: { decimals: PRICE_DIGITS, sign: "negative", grouping: false },
  change: { decimals: PRICE_DIGITS, sign: "always", grouping: false },
  spread: { decimals: PRICE_DIGITS, sign: "always", grouping: false },
  unit_value: { decimals: 2, sign: "negative", grouping: false },
  volume: { decimals: 0, sign: "negative", grouping: true },
  pnl: { decimals: 0, sign: "always", grouping: true },
  percent: { decimals: 1, sign: "negative", grouping: false, unit: "%" },
  percent_change: { decimals: 1, sign: "always", grouping: false, unit: "%" },
  fx_rate: { decimals: 4, sign: "negative", grouping: false },
  tariff: { decimals: 4, sign: "negative", grouping: false },
  temperature: { decimals: 1, sign: "negative", grouping: false, unit: "°C" },
  coordinate: { decimals: 4, sign: "negative", grouping: false },
  ratio: { decimals: 2, sign: "negative", grouping: false },
};

export interface MeasureOptions {
  /** The unit written after the number ("EUR/MWh", "GWh/d"); the measure's own unit otherwise. */
  unit?: string | null;
  /** Leave the unit out (it is named once in the column header). */
  bare?: boolean;
  /** Overrides the table, for a figure whose precision is part of its meaning. */
  decimals?: number;
  /** Overrides the sign rule. */
  signed?: boolean;
  /** App language (i18n.language); grouping and digits follow it, never the browser's locale. */
  language?: string;
  /** What a missing value reads (default "–"). */
  missing?: string;
}

/** A figure as a person reads it: "34.125 EUR/MWh", "−1,250 MWh", "+0.4 %", "21.3 °C". */
export function formatMeasure(measure: Measure, value: number | null | undefined, options: MeasureOptions = {}): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return options.missing ?? "–";
  const rule = MEASURES[measure];
  const decimals = options.decimals ?? rule.decimals;
  const digits = new Intl.NumberFormat(formattingLocale(options.language ?? "en"), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping: rule.grouping,
  }).format(Math.abs(value));
  // A value that rounds to zero has no sign (never "−0.000").
  const zero = Number(digits.replace(/[^0-9.]/g, "")) === 0;
  const always = options.signed ?? rule.sign === "always";
  const sign = zero ? "" : value < 0 ? "\u2212" : always ? "+" : "";
  const unit = options.bare ? null : (options.unit ?? rule.unit ?? null);
  return unit ? `${sign}${digits} ${unit}` : `${sign}${digits}`;
}

/**
 * A number for a machine, not a reader: a form field's value, a CSV cell, an SVG coordinate or a
 * CSS length. ASCII minus, no grouping, no unit. Components use this, never `toFixed`, so the
 * formatter lint can tell the two apart.
 */
export function plainDecimal(value: number, decimals: number): string {
  return value.toFixed(decimals);
}

/** What one conversion says about its rate (G3, G6): pair, rate, source, date, method. */
export interface RateStatement {
  pair: string;
  rate: number;
  source: "ecb" | "simulated" | "licensed";
  /** The rate's own date (the ECB reference day, or the licensed forward's value date). */
  date: string | null;
  method: "spot" | "forward" | "licensed" | "identity";
  /** The delivery the forward is for ("Jan-27"), when it is a forward. */
  delivery: string | null;
}

/** Read the server's FX record into the statement shown beside a converted value. */
export function rateStatement(fx: FxForwardDTO): RateStatement {
  const method: RateStatement["method"] = fx.method.startsWith("derived")
    ? "forward"
    : fx.method === "licensed"
      ? "licensed"
      : fx.method === "same currency"
        ? "identity"
        : "spot";
  const quote = fx.desk_quote ?? { pair: `${fx.base}/${fx.quote}`, rate: fx.rate };
  return {
    pair: quote.pair.includes("/") ? quote.pair : `${quote.pair.slice(0, 3)}/${quote.pair.slice(3)}`,
    rate: quote.rate,
    source: fx.simulated ? "simulated" : method === "licensed" ? "licensed" : "ecb",
    date: fx.licensed?.value_date ?? fx.spot?.value_date ?? fx.value_date ?? null,
    method,
    delivery: method === "forward" || method === "licensed" ? fx.delivery?.label ?? null : null,
  };
}

/** "EUR/USD 1.1600 (ECB 16 Nov; forward Jan-27, derived)" in the app's language. */
export function describeRate(statement: RateStatement, language: string, t: Translate): string {
  const source = t(`convert.source.${statement.source}`);
  const date = statement.date ? formatGasDay(statement.date, language) : "";
  const method =
    statement.method === "forward"
      ? t("convert.method.forward", { delivery: statement.delivery ?? "" })
      : t(`convert.method.${statement.method}`);
  return t("convert.rate", {
    pair: statement.pair,
    rate: formatAmount(statement.rate, language, 4),
    source,
    date,
    method,
  });
}

/** The secondary text for a converted price or amount, or why there is none. */
export interface ConvertedText {
  /** "10.20 USD/MMBtu at EUR/USD 1.1600 (ECB 16 Nov; forward Jan-27, derived)". */
  text: string;
  /** Just the converted figure ("10.20 USD/MMBtu"), for a compact line. */
  figure: string;
  simulated: boolean;
  refused: boolean;
  /** The server's own reason for a refusal, for the hover title (provenance on demand). */
  reason?: string;
}

/** A normalised price (the server's record) as the reader's secondary text. */
export function convertedPriceText(result: NormalisedValueDTO, language: string, t: Translate): ConvertedText {
  if (result.value === null || result.value === undefined || result.refused) {
    const code = result.refused?.code === "beyond_horizon" ? "beyond_horizon" : "not_held";
    return {
      text: t(`convert.refused.${code}`),
      figure: "",
      simulated: Boolean(result.simulated),
      refused: true,
      reason: result.refused?.message,
    };
  }
  const unit = result.unit ?? "";
  const figure = `${formatAmount(result.value, language, PRICE_DIGITS)} ${unit}`;
  const fx = result.normalisation?.fx ?? null;
  const rate = fx && fx.method !== "same currency" ? describeRate(rateStatement(fx), language, t) : null;
  return {
    text: rate ? t("convert.at", { figure, rate }) : t("convert.units_only", { figure }),
    figure,
    simulated: Boolean(result.simulated),
    refused: false,
  };
}

/**
 * An amount converted at the rate the server stated (`/api/market/fx-forward`, base = the
 * amount's currency): an amount has no unit factor, so the rate is the whole conversion.
 */
export function convertedAmountText(
  amount: number,
  fx: FxForwardDTO,
  language: string,
  t: Translate,
  digits = 0,
  simulated = false,
): ConvertedText {
  const figure = `${formatAmount(amount * fx.rate, language, digits)} ${fx.quote}`;
  return {
    text: t("convert.at", { figure, rate: describeRate(rateStatement(fx), language, t) }),
    figure,
    // A simulated input or a simulated rate makes the converted figure simulated (G9).
    simulated: simulated || fx.simulated,
    refused: false,
  };
}

/** One figure in a total: its value, currency and whether it is simulated. */
export interface TotalPart {
  value: number;
  currency: string;
  simulated?: boolean;
}

/**
 * How a total across `parts` may be shown (G4, G7): one currency → native; several → only
 * converted (the caller asks the server for each rate); simulated mixed with non-simulated →
 * refused, never added.
 */
export function totalRule(parts: readonly TotalPart[]): { kind: "native"; currency: string } | { kind: "converted"; currencies: string[] } | { kind: "refused"; reason: "mixes_simulated" } | { kind: "empty" } {
  if (parts.length === 0) return { kind: "empty" };
  const simulated = new Set(parts.map((part) => Boolean(part.simulated)));
  if (simulated.size > 1) return { kind: "refused", reason: "mixes_simulated" };
  const currencies = [...new Set(parts.map((part) => part.currency.toUpperCase()))].sort();
  return currencies.length === 1 ? { kind: "native", currency: currencies[0] } : { kind: "converted", currencies };
}

/** Export columns that carry a conversion (G6): a file never holds a bare converted number. */
export function conversionExportColumns(fx: FxForwardDTO | null | undefined): Record<string, string> {
  if (!fx) return { fx_pair: "", fx_rate: "", fx_rate_date: "", fx_method: "", fx_source: "" };
  const statement = rateStatement(fx);
  return {
    fx_pair: statement.pair,
    fx_rate: String(statement.rate),
    fx_rate_date: statement.date ?? "",
    fx_method: fx.label || fx.method,
    fx_source: statement.source,
  };
}
