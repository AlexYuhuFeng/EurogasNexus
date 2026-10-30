import type { StorageTrajectoryDTO } from "@/api/client";

/** Quotations the backend `/market/price-conversion` route supports, desk order. */
export const PRICE_UNIT_OPTIONS = ["EUR/MWh", "GBp/th", "USD/MMBtu", "GBP/MWh", "USD/MWh", "EUR/GJ"] as const;

/**
 * FX benchmark fixes the converter can apply. ECB is public; WMR (WM/Reuters, LSEG) and BFIX
 * (Bloomberg) are licensed and answer only for principals holding that data scope - the usual
 * reference in LNG contracts.
 */
export const FX_SOURCE_OPTIONS = ["ECB", "WMR", "BFIX"] as const;

/** `EUR/USD 1.0850 (WMR 2026-10-28)`; an average names its window and fix count. */
export function describeFxRate(
  currency: string,
  fx: { rate: number; source?: string | null; value_dates?: string[] },
): string {
  const dates = fx.value_dates ?? [];
  const when = dates.length > 1
    ? ` ${dates[0]}..${dates[dates.length - 1]}, ${dates.length} fixes`
    : dates.length === 1 ? ` ${dates[0]}` : "";
  return `EUR/${currency} ${fx.rate.toFixed(4)} (${fx.source ?? "?"}${when})`;
}

/** AGSI codes offered by the storage trajectory selector (EU aggregate first). */
export const STORAGE_CODES = ["EU", "DE", "NL", "FR", "IT", "AT", "BE", "ES", "PL", "CZ", "SK", "HU"] as const;

/** A converted price, or the caller's label when the backend had no FX rate for it. */
export function formatConverted(value: number | null | undefined, missingLabel: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return missingLabel;
  return value.toFixed(value >= 100 ? 2 : 3);
}

/** A signed flow such as `+3.20 TWh/d`; `n/a` when the backend reported none. */
export function formatSigned(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)} ${unit}`;
}

export function storageStatusKey(status: StorageTrajectoryDTO["status"]): string {
  return `desk.status.${status}`;
}
