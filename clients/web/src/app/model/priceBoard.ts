/**
 * Desk → Prices board (CP-20): which hubs it lists (the six majors by default; a desk adds or
 * removes hubs with the instrument picker, kept per browser), and the reporting-unit value shown
 * on hover beside a native price (design basis 2, G1 and G3). The conversion is the server's
 * (`POST /api/market/normalise`, spot for prompt tenors, forward for a month); this module only
 * builds the request and reads the answers back by hub.
 */

import type { NormaliseRequestDTO, NormaliseResponseDTO } from "../../api/comparablePrices.ts";
import { canonicalHub } from "../hubAliases.ts";

export const BOARD_DEFAULT_HUBS: readonly string[] = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV"];
export const BOARD_HUBS_KEY = "egn.prices.board-hubs";
export const MAX_BOARD_HUBS = 12;
/** The reporting unit a native price is also shown in (display preferences come with CP-05). */
export const REPORTING_UNIT = "EUR/MWh";

/** The board's tenor keys as the server's product codes. */
const TENOR_PRODUCT: Record<string, string> = {
  "within-day": "WD",
  "day-ahead": "DA",
  weekend: "WE",
  "month-ahead": "M+1",
};

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function storage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** The hubs this browser keeps on the board, or the six majors. */
export function readBoardHubs(store: StorageLike | null = storage()): string[] {
  try {
    const raw = store?.getItem(BOARD_HUBS_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    if (Array.isArray(parsed)) {
      // A board saved with a hub's other name (GTF) lists that hub (ETF), once.
      const hubs = parsed
        .filter((item): item is string => typeof item === "string" && /^[A-Z]{2,8}$/.test(item))
        .map(canonicalHub);
      if (hubs.length > 0) return [...new Set(hubs)].slice(0, MAX_BOARD_HUBS);
    }
  } catch {
    /* blocked or corrupt storage: the default board */
  }
  return [...BOARD_DEFAULT_HUBS];
}

export function writeBoardHubs(hubs: readonly string[], store: StorageLike | null = storage()): void {
  try {
    store?.setItem(BOARD_HUBS_KEY, JSON.stringify(hubs.slice(0, MAX_BOARD_HUBS)));
  } catch {
    /* a convenience only */
  }
}

/** The board with one hub added (at the end) or removed; never empty, never over the cap. */
export function withHub(hubs: readonly string[], hub: string): string[] {
  return hubs.includes(hub) ? [...hubs] : [...hubs, hub].slice(0, MAX_BOARD_HUBS);
}

export function withoutHub(hubs: readonly string[], hub: string): string[] {
  const next = hubs.filter((item) => item !== hub);
  return next.length > 0 ? next : [...hubs];
}

export interface BoardPrice {
  hub: string;
  tenor: string;
  value: number | null;
  /** The unit the value is printed in (the hub's quotation). */
  unit: string | null;
}

/** The request that puts every native board price that is not already in the reporting unit
 * into it. "p/th" is the desk's spelling of the server's GBp/th. */
export function boardReportingRequest(prices: readonly BoardPrice[]): { body: NormaliseRequestDTO; hubs: string[] } {
  const hubs: string[] = [];
  const values: NormaliseRequestDTO["values"] = [];
  for (const price of prices) {
    if (price.value === null || !price.unit || price.unit === REPORTING_UNIT) continue;
    const product = TENOR_PRODUCT[price.tenor];
    hubs.push(price.hub);
    values.push({ value: price.value, unit: price.unit === "p/th" ? "GBp/th" : price.unit, ...(product ? { product } : {}) });
  }
  return { body: { to_unit: REPORTING_UNIT, values }, hubs };
}

export interface ReportingValue {
  value: number | null;
  unit: string;
  /** The desk pair and rate the server used (EUR/GBP 0.8530), or null without FX. */
  pair: string | null;
  rate: number | null;
  method: string | null;
  label: string | null;
  simulated: boolean;
  refused: string | null;
}

/** The server's answers by hub. */
export function reportingByHub(hubs: readonly string[], response: NormaliseResponseDTO): Map<string, ReportingValue> {
  const out = new Map<string, ReportingValue>();
  hubs.forEach((hub, index) => {
    const answer = response.values[index];
    if (!answer) return;
    const fx = answer.normalisation?.fx ?? null;
    out.set(hub, {
      value: answer.value ?? null,
      unit: REPORTING_UNIT,
      pair: fx?.desk_quote?.pair ?? null,
      rate: fx?.desk_quote?.rate ?? null,
      method: fx?.method ?? null,
      label: fx?.label ?? null,
      simulated: Boolean(answer.simulated),
      refused: answer.refused?.message ?? null,
    });
  });
  return out;
}
