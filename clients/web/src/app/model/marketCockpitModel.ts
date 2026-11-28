export type MarketTask = "board" | "overview" | "curves" | "network" | "cargoes" | "auctions";

/**
 * `cargoes`: the LNG cargo board and each cargo's plan (QA-L-05). `board`: the small desk's one
 * screen beside the trading screen (SMALL_DESK_PLAN step 4): its five hubs' prices, spreads,
 * book and fundamentals. `auctions`: the regas auction desk ("bid at most X for this slot"), the
 * second view of Desk → Cargoes behind its switch (the one LNG workspace; AGENTS rule 9).
 */
export const MARKET_TASKS: MarketTask[] = ["board", "overview", "curves", "network", "cargoes", "auctions"];

/**
 * Task names that no longer have a page of their own and the task that now shows them. The
 * Desk's "Outages & capacity" (`capacity`) became the Network page's panel beside the map
 * (Capacity tab: `networkPanelFromSearch`), so its links keep working.
 */
export const RETIRED_MARKET_TASKS: Readonly<Record<string, MarketTask>> = { capacity: "network" };

/**
 * The two separate market task views: numeric analysis (`curves`) and
 * geographic/network inspection (`network`). Only these are selectable as a
 * persisted per-user landing view; `overview` stays an explicit combined
 * opt-in.
 */
export const MARKET_VIEW_TASKS: MarketTask[] = ["curves", "network"];

/** Landing task when no URL task and no persisted preference exist. */
export const DEFAULT_MARKET_TASK: MarketTask = "overview";

export const MAJOR_MARKET_HUBS = ["TTF", "NBP", "ZTP", "THE", "PEG", "PSV"];

/** Explicit `?task=` value, or null when the URL does not request a task. */
export function marketTaskFromSearch(search: string): MarketTask | null {
  const value = new URLSearchParams(search).get("task");
  if (value && RETIRED_MARKET_TASKS[value]) return RETIRED_MARKET_TASKS[value];
  return MARKET_TASKS.includes(value as MarketTask) ? (value as MarketTask) : null;
}

export function marketTaskFromLocation(
  search: string,
  activeWorkspace: string,
): MarketTask {
  // The retired capacity page opens Network (its Capacity tab).
  if (activeWorkspace === "network" || activeWorkspace === "capacity") return "network";
  return marketTaskFromSearch(search) ?? DEFAULT_MARKET_TASK;
}

export function marketTaskToSearch(currentSearch: string, task: MarketTask): string {
  const next = new URLSearchParams(currentSearch);
  next.set("workspace", "market");
  next.set("task", task);
  return next.toString();
}

/** The board's tenors, in screen order (WD, DA, WE, MA). */
export const BOARD_TENORS = ["within-day", "day-ahead", "weekend", "month-ahead"] as const;

/** The order a desk looks for prices when it has not chosen: day-ahead first, then the rest. */
const BOARD_TENOR_PREFERENCE = ["day-ahead", "within-day", "weekend", "month-ahead"] as const;

/** The tenor a URL names (`?tenor=`), when it is one of the board's tenors. */
export function boardTenorFromSearch(search: string): string | null {
  const value = new URLSearchParams(search).get("tenor");
  return value && (BOARD_TENORS as readonly string[]).includes(value) ? value : null;
}

/** The URL with the user's tenor choice written into it. */
export function boardTenorToSearch(search: string, tenor: string): string {
  const next = new URLSearchParams(search);
  next.set("tenor", tenor);
  return next.toString();
}

/**
 * The tenor Prices opens on: the user's explicit choice (the URL) when there is one, else the
 * first tenor this desk has prices for, so the board never opens on a column of "Awaiting
 * licensed feed" while another tenor is priced. With no prices at all, day-ahead.
 */
export function openingBoardTenor(chosen: string | null, priced: ReadonlySet<string>): string {
  if (chosen) return chosen;
  return BOARD_TENOR_PREFERENCE.find((tenor) => priced.has(tenor)) ?? "day-ahead";
}
