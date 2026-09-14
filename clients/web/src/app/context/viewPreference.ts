import {
  MARKET_VIEW_TASKS,
  marketTaskFromSearch,
  DEFAULT_MARKET_TASK,
  type MarketTask,
} from "../model/marketCockpitModel.ts";

/**
 * Per-user market view preference.
 *
 * The market primary owns two separate inspection task views: the numeric
 * terminal (`curves`) and the map/network view (`network`). The fused
 * `overview` dashboard stays reachable as an explicit opt-in task, but it is
 * never the implicit landing view and it is not a persistable preference.
 *
 * Persistence is browser-local and scoped by principal so two operators on the
 * same workstation do not overwrite each other's landing view. Precedence when
 * resolving what to show is URL task > persisted preference > numeric default.
 */
export const MARKET_VIEW_PREFERENCE_STORAGE_KEY = "eurogas.marketView.v1";

export type MarketViewPreferenceId = "curves" | "network";

export const MARKET_VIEW_PREFERENCE_IDS: MarketViewPreferenceId[] = [
  "curves",
  "network",
];

/** With nothing persisted the landing view is the numeric market analysis. */
export const DEFAULT_MARKET_VIEW_PREFERENCE: MarketViewPreferenceId = "curves";

/** Principal key used when identity is unknown; never a shared user identity. */
export const MARKET_VIEW_PREFERENCE_ANONYMOUS_PRINCIPAL = "anonymous";

export type MarketViewPreferenceSource = "url" | "persisted" | "default";

export interface MarketViewTaskResolution {
  task: MarketTask;
  source: MarketViewPreferenceSource;
}

/** The market primary shell; it owns the task switcher for every task. */
export const MARKET_SHELL_PAGE_ID = "market" as const;

/**
 * Page that renders a persisted view with the task switcher available.
 *
 * The standalone `network` page is the map-first workspace and stays reachable
 * as a deep link (`?workspace=network`), but it has no task tabs. Landing a
 * map-preferring user there would leave no in-UI way back to the numeric view,
 * so a persisted preference always lands on the market shell and the resolved
 * task decides which of the two views is shown.
 */
export function marketViewLandingPage(_view: MarketViewPreferenceId): typeof MARKET_SHELL_PAGE_ID {
  return MARKET_SHELL_PAGE_ID;
}

/**
 * Child page the market primary should open, or `null` when the declared
 * default stands. Order: an explicit URL task wins (it needs the shell that
 * owns the task switcher), then the persisted per-user view.
 */
export function marketViewLandingPageCandidate(input: {
  task: MarketTask | null;
  persisted: MarketViewPreferenceId | null | undefined;
}): "market" | "network" | null {
  if (input.task) return MARKET_SHELL_PAGE_ID;
  if (isMarketViewPreferenceId(input.persisted)) {
    return marketViewLandingPage(input.persisted);
  }
  return null;
}

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): StorageLike | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function isMarketViewPreferenceId(
  value: string | null | undefined,
): value is MarketViewPreferenceId {
  return MARKET_VIEW_PREFERENCE_IDS.includes(value as MarketViewPreferenceId);
}

export function normalizeMarketViewPreference(
  value: string | null | undefined,
  fallback: MarketViewPreferenceId = DEFAULT_MARKET_VIEW_PREFERENCE,
): MarketViewPreferenceId {
  return isMarketViewPreferenceId(value) ? value : fallback;
}

/** Stable storage key for one principal; unknown identity is its own scope. */
export function marketViewPreferencePrincipalKey(
  principalId: string | null | undefined,
): string {
  const normalized = principalId?.trim();
  return normalized ? normalized : MARKET_VIEW_PREFERENCE_ANONYMOUS_PRINCIPAL;
}

/** The two separate task views are persistable; `overview`/`capacity` are not. */
export function marketViewPreferenceForTask(
  task: MarketTask,
): MarketViewPreferenceId | null {
  return MARKET_VIEW_TASKS.includes(task) && isMarketViewPreferenceId(task)
    ? task
    : null;
}

function storedPreferenceForPrincipal(
  record: Record<string, unknown>,
  principalKey: string,
): MarketViewPreferenceId | null {
  const entry = record[principalKey];
  if (typeof entry === "string") {
    return isMarketViewPreferenceId(entry) ? entry : null;
  }
  // Tolerate an earlier object-shaped entry without trusting it.
  if (entry && typeof entry === "object") {
    const view = (entry as { view?: unknown; task?: unknown }).view ??
      (entry as { view?: unknown; task?: unknown }).task;
    return typeof view === "string" && isMarketViewPreferenceId(view) ? view : null;
  }
  return null;
}

/**
 * Read the persisted view for one principal. Returns `null` when nothing valid
 * is stored - including unknown, legacy or malformed values - so callers fall
 * back to the numeric default instead of rendering an unsupported view.
 */
export function readMarketViewPreference(
  principalId: string | null | undefined,
  storage: StorageLike | null = defaultStorage(),
): MarketViewPreferenceId | null {
  if (!storage) return null;
  let raw: string | null = null;
  try {
    raw = storage.getItem(MARKET_VIEW_PREFERENCE_STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let parsed: unknown = null;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed === "string") {
    // Legacy single-value shape; only a supported view is accepted.
    return isMarketViewPreferenceId(parsed) ? parsed : null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  return storedPreferenceForPrincipal(
    parsed as Record<string, unknown>,
    marketViewPreferencePrincipalKey(principalId),
  );
}

/** Best-effort write for one principal; other principals' entries are kept. */
export function writeMarketViewPreference(
  principalId: string | null | undefined,
  view: MarketViewPreferenceId,
  storage: StorageLike | null = defaultStorage(),
): void {
  if (!storage) return;
  const principalKey = marketViewPreferencePrincipalKey(principalId);
  let record: Record<string, unknown> = {};
  try {
    const raw = storage.getItem(MARKET_VIEW_PREFERENCE_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        record = { ...(parsed as Record<string, unknown>) };
      }
    }
  } catch {
    record = {};
  }
  record[principalKey] = normalizeMarketViewPreference(view);
  try {
    storage.setItem(MARKET_VIEW_PREFERENCE_STORAGE_KEY, JSON.stringify(record));
  } catch {
    // Persistence is best-effort; the URL and the numeric default stay
    // deterministic when storage is unavailable.
  }
}

/**
 * Resolve the landing task for the market primary.
 *
 * URL/workspace-derived tasks (including the `?workspace=network` deep link and
 * explicit `?task=overview`) always win over the stored preference so deep
 * links, history navigation and explicit opt-ins stay authoritative.
 */
export function resolveMarketViewTask(input: {
  search: string;
  activeWorkspace: string;
  persisted: MarketViewPreferenceId | null | undefined;
}): MarketViewTaskResolution {
  const urlTask = marketTaskFromSearch(input.search);
  if (urlTask) return { task: urlTask, source: "url" };
  if (input.activeWorkspace === "network") return { task: "network", source: "url" };
  if (input.activeWorkspace === "capacity") return { task: "capacity", source: "url" };
  if (isMarketViewPreferenceId(input.persisted)) {
    return { task: input.persisted, source: "persisted" };
  }
  return { task: DEFAULT_MARKET_TASK, source: "default" };
}
