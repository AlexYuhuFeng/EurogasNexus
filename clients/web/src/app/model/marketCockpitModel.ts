export type MarketTask = "overview" | "curves" | "network" | "capacity";

export const MARKET_TASKS: MarketTask[] = ["overview", "curves", "network", "capacity"];

/**
 * The two separate market task views: numeric analysis (`curves`) and
 * geographic/network inspection (`network`). Only these are selectable as a
 * persisted per-user landing view; `overview` stays an explicit combined
 * opt-in and `capacity` stays a page-level task.
 */
export const MARKET_VIEW_TASKS: MarketTask[] = ["curves", "network"];

/** Landing task when no URL task and no persisted preference exist. */
export const DEFAULT_MARKET_TASK: MarketTask = "curves";

export const MAJOR_MARKET_HUBS = ["TTF", "NBP", "ZTP", "THE", "PEG", "PSV"];

/** Explicit `?task=` value, or null when the URL does not request a task. */
export function marketTaskFromSearch(search: string): MarketTask | null {
  const value = new URLSearchParams(search).get("task");
  return MARKET_TASKS.includes(value as MarketTask) ? (value as MarketTask) : null;
}

export function marketTaskFromLocation(
  search: string,
  activeWorkspace: string,
): MarketTask {
  if (activeWorkspace === "network") return "network";
  if (activeWorkspace === "capacity") return "capacity";
  return marketTaskFromSearch(search) ?? DEFAULT_MARKET_TASK;
}

export function marketTaskToSearch(currentSearch: string, task: MarketTask): string {
  const next = new URLSearchParams(currentSearch);
  next.set("workspace", "market");
  next.set("task", task);
  return next.toString();
}
