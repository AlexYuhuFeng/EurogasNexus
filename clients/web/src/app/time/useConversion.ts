/**
 * The converted secondary value for a native figure, asked of the server and kept in the read
 * cache (a rate is good for minutes; the same pair is asked once for every figure that needs it).
 * Returns null when no conversion is due (the native unit already is the reader's) or allowed
 * (G7), and while the first answer is on its way: the native figure never waits for it.
 */
import { useTranslation } from "react-i18next";

import { api } from "../../api/client.ts";
import { readKey, useCachedRead } from "../data/readCache.ts";
import { useDisplayPreferenceStore } from "../../stores/displayPreference.ts";
import {
  conversionAllowed,
  convertedAmountText,
  convertedPriceText,
  targetCurrency,
  targetPriceUnit,
  type ConvertedText,
  type FigureSubject,
} from "./valueFormat.ts";

const RATE_FRESH_MS = 10 * 60_000;

export interface PriceToConvert {
  value: number | null | undefined;
  /** The native unit as the board writes it ("p/th", "EUR/MWh", "USD/MMBtu"). */
  unit: string;
  /** The delivery period (a desk product code, "Dec-26", "DA"): decides spot or forward FX. */
  product?: string;
  simulated?: boolean;
  subject?: FigureSubject;
}

/** A price in the reader's currency and energy unit, with the rate and method that made it. */
export function useConvertedPrice({ value, unit, product, simulated = false, subject = "price" }: PriceToConvert): ConvertedText | null {
  const { t, i18n } = useTranslation();
  const preference = useDisplayPreferenceStore();
  const target = conversionAllowed(subject) && typeof value === "number" && Number.isFinite(value)
    ? targetPriceUnit(unit, preference)
    : null;
  const key = target
    ? readKey("/market/normalise", { value, unit, to: target, product, simulated: simulated ? 1 : 0 })
    : null;
  const read = useCachedRead(
    key,
    async (signal) => {
      const response = await api.normaliseMarket(
        { to_unit: target!, values: [{ value: value as number, unit, product, simulated }] },
        { signal },
      );
      return response.data.values[0] ?? null;
    },
    { freshMs: RATE_FRESH_MS },
  );
  if (!key || !read.data) return null;
  return convertedPriceText(read.data, i18n.language || "en", t);
}

export interface AmountToConvert {
  amount: number | null | undefined;
  /** ISO currency of the amount ("EUR", "GBP"). */
  currency: string;
  /** The delivery period the amount is for; none for realised and spot values (G5). */
  product?: string;
  /** The value date of a historical figure: its own date's rate, never today's (G5). */
  valueDate?: string;
  subject?: FigureSubject;
  digits?: number;
  simulated?: boolean;
}

/** An amount in the reporting currency at the server's rate for its value date or delivery. */
export function useConvertedAmount({ amount, currency, product, valueDate, subject = "total", digits = 0, simulated = false }: AmountToConvert): ConvertedText | null {
  const { t, i18n } = useTranslation();
  const preference = useDisplayPreferenceStore();
  const quote = conversionAllowed(subject) && typeof amount === "number" && Number.isFinite(amount)
    ? targetCurrency(currency, preference)
    : null;
  const base = currency.trim().toUpperCase();
  const key = quote ? readKey("/market/fx-forward", { base, quote, product, value_date: valueDate }) : null;
  const read = useCachedRead(
    key,
    async (signal) => (await api.fxForward({ base, quote: quote!, product, value_date: valueDate }, { signal })).data,
    { freshMs: RATE_FRESH_MS },
  );
  if (!key || !read.data) return null;
  return convertedAmountText(amount as number, read.data, i18n.language || "en", t, digits, simulated);
}
