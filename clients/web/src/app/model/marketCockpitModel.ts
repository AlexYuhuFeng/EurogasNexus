export type MarketTask = "overview" | "curves" | "network" | "capacity";

export const MARKET_TASKS: MarketTask[] = ["overview", "curves", "network", "capacity"];

export const MAJOR_MARKET_HUBS = ["TTF", "NBP", "ZTP", "THE", "PEG", "PSV"];

export function marketTaskFromLocation(
  search: string,
  activeWorkspace: string,
): MarketTask {
  if (activeWorkspace === "network") return "network";
  if (activeWorkspace === "capacity") return "capacity";
  const value = new URLSearchParams(search).get("task");
  return value === "curves" || value === "network" || value === "capacity"
    ? value
    : "overview";
}

export function marketTaskToSearch(currentSearch: string, task: MarketTask): string {
  const next = new URLSearchParams(currentSearch);
  next.set("workspace", "market");
  next.set("task", task);
  return next.toString();
}
