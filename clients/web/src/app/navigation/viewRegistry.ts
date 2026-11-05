/**
 * Every navigable sub-view in the product, declared once (#31).
 *
 * A page's sub-view lives in the URL so it can be shared, refreshed and reached from a link
 * (an alert, the manual, the command palette) and so Back and Forward step through it. Business
 * pages call it `task`; administration and research pages call it `view`. An object a view is
 * about (a selected source, a contract) is a separate, named parameter. Transient state (an
 * open disclosure, a loading flag, anything typed into a form) never goes in the URL, and a
 * secret never does.
 *
 * An unknown or stale value falls back to the page's default view, never to "the first object"
 * pretending to be the one asked for. The backend authorises every read whatever the URL says.
 */
import { PAGE_OBJECT_PARAMS, type WorkspacePageId } from "../../workspaceNavigation.ts";
import { MARKET_TASKS } from "../model/marketCockpitModel.ts";
import { DECISION_TASKS, PORTFOLIO_TASKS } from "../model/commercialWorkflowModel.ts";
import { STRATEGY_TASKS } from "../model/strategyLabModel.ts";

export interface PageViews {
  /** The URL parameter carrying the sub-view. */
  param: "task" | "view";
  views: readonly string[];
  defaultView: string;
  /** Object parameters the page restores from the URL (never secrets). */
  objectParams?: readonly string[];
  /** Translation-key prefix of the view's tab label: `${labelPrefix}${view}`. */
  labelPrefix: string;
}

export const PAGE_VIEW_REGISTRY: Partial<Record<WorkspacePageId, PageViews>> = {
  market: { param: "task", views: MARKET_TASKS, defaultView: "curves", labelPrefix: "market.task." },
  contracts: { param: "task", views: PORTFOLIO_TASKS, defaultView: "overview", objectParams: PAGE_OBJECT_PARAMS.contracts, labelPrefix: "portfolio.task." },
  scenario: { param: "task", views: DECISION_TASKS, defaultView: "scenario", labelPrefix: "decision.task." },
  strategy: { param: "task", views: STRATEGY_TASKS, defaultView: "spread", labelPrefix: "strategy_lab.task." },
  sources: {
    param: "view",
    views: ["attention", "catalog", "access", "infrastructure"],
    defaultView: "attention",
    objectParams: PAGE_OBJECT_PARAMS.sources,
    labelPrefix: "sources.view.",
  },
  runtime: { param: "view", views: ["delivery", "readiness", "governance", "support"], defaultView: "delivery", labelPrefix: "runtime.view." },
  access: { param: "view", views: ["users", "api_keys", "catalogue", "audit", "sso"], defaultView: "users", labelPrefix: "access.view." },
  research: { param: "view", views: ["datasets", "products", "features", "targets"], defaultView: "datasets", labelPrefix: "research.tab." },
  agents: { param: "view", views: ["capabilities", "research", "runs"], defaultView: "capabilities", labelPrefix: "agents.tab." },
  glossary: { param: "view", views: ["terms"], defaultView: "terms", objectParams: PAGE_OBJECT_PARAMS.glossary, labelPrefix: "glossary.view." },
};

/** The sub-view a URL asks for on a page, or the page's default when it names none it has. */
export function viewFromSearch(page: WorkspacePageId, search: string): string | null {
  const entry = PAGE_VIEW_REGISTRY[page];
  if (!entry) return null;
  const value = new URLSearchParams(search).get(entry.param);
  return value !== null && entry.views.includes(value) ? value : entry.defaultView;
}

/** The URL search for a page and sub-view; object parameters of another page are dropped. */
export function viewToSearch(
  search: string,
  page: WorkspacePageId,
  view: string,
  objects: Record<string, string | null | undefined> = {},
): string {
  const entry = PAGE_VIEW_REGISTRY[page];
  const next = new URLSearchParams(search);
  // Object parameters belong to the page that declared them: a stale one from another page
  // would otherwise ride along and select something on the wrong page.
  const allObjectParams = new Set(
    Object.values(PAGE_VIEW_REGISTRY).flatMap((item) => item?.objectParams ?? []),
  );
  for (const name of allObjectParams) {
    if (!entry?.objectParams?.includes(name)) next.delete(name);
  }
  next.set("workspace", page);
  next.delete("task");
  next.delete("view");
  if (entry && entry.views.includes(view)) next.set(entry.param, view);
  for (const [name, value] of Object.entries(objects)) {
    if (!entry?.objectParams?.includes(name)) continue;
    if (value) next.set(name, value);
    else next.delete(name);
  }
  return next.toString();
}

/** An object parameter of the current URL (a selected source, contract or term), or null. */
export function objectFromSearch(page: WorkspacePageId, name: string, search: string): string | null {
  const entry = PAGE_VIEW_REGISTRY[page];
  if (!entry?.objectParams?.includes(name)) return null;
  const value = new URLSearchParams(search).get(name);
  return value && value.trim() ? value : null;
}

/** Every page and sub-view the registry declares, for enumeration (palette, tests). */
export function registeredViews(): Array<{
  page: WorkspacePageId;
  view: string;
  param: "task" | "view";
  labelKey: string;
}> {
  return Object.entries(PAGE_VIEW_REGISTRY).flatMap(([page, entry]) =>
    (entry?.views ?? []).map((view) => ({
      page: page as WorkspacePageId,
      view,
      param: entry!.param,
      labelKey: `${entry!.labelPrefix}${view}`,
    })),
  );
}
