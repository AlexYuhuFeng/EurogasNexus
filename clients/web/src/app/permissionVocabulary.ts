/**
 * Backend permission keys in words an administrator can compare (#25).
 *
 * The keys (`source.credentials.write`) stay the exact contract with the backend and are shown
 * on request; what the Roles view leads with is the business area and the action. A key not
 * listed here is shown as itself, so a new backend permission is never hidden.
 */
export type PermissionArea =
  | "account"
  | "market"
  | "portfolio"
  | "strategy"
  | "decisions"
  | "research"
  | "sources"
  | "platform"
  | "access";

export const PERMISSION_AREAS: readonly PermissionArea[] = [
  "account",
  "market",
  "portfolio",
  "strategy",
  "decisions",
  "research",
  "sources",
  "platform",
  "access",
];

/** Area and action (an i18n key under `access.permission.action.`) of each known key. */
export const PERMISSION_VOCABULARY: Readonly<Record<string, { area: PermissionArea; action: string }>> = {
  "me.read": { area: "account", action: "own_profile" },
  "market.read": { area: "market", action: "view_prices" },
  "portfolio.read": { area: "portfolio", action: "view" },
  "portfolio.write": { area: "portfolio", action: "edit_contracts" },
  "strategy.read": { area: "strategy", action: "view" },
  "strategy.create": { area: "strategy", action: "create" },
  "strategy.edit": { area: "strategy", action: "edit" },
  "strategy.freeze": { area: "strategy", action: "freeze" },
  "strategy.retire": { area: "strategy", action: "retire" },
  "strategy.shadow.manage": { area: "strategy", action: "shadow" },
  "scenario.create": { area: "decisions", action: "prepare_scenarios" },
  "optimization.run": { area: "decisions", action: "run_optimisation" },
  "review.read": { area: "decisions", action: "view_reviews" },
  "review.record": { area: "decisions", action: "record_reviews" },
  "analysis.query": { area: "research", action: "query_data" },
  "agent.read": { area: "research", action: "view_agent_runs" },
  "agent.research": { area: "research", action: "run_agent_research" },
  "capability.read": { area: "research", action: "view_capabilities" },
  "capability.invoke": { area: "research", action: "use_capabilities" },
  "source.read": { area: "sources", action: "view" },
  "source.run": { area: "sources", action: "run_ingestion" },
  "source.backfill": { area: "sources", action: "backfill" },
  "source.credentials.write": { area: "sources", action: "manage_credentials" },
  "source.certification.manage": { area: "sources", action: "certify" },
  "runtime.read": { area: "platform", action: "view_health" },
  "identity.read": { area: "access", action: "view_users" },
  "identity.manage": { area: "access", action: "manage_users" },
  "api_keys.manage": { area: "access", action: "manage_api_keys" },
  "audit.read": { area: "access", action: "view_audit" },
};

export interface PermissionGroup {
  area: PermissionArea | "other";
  /** Known keys as action i18n keys, unknown keys as themselves. */
  actions: Array<{ key: string; actionKey: string | null }>;
}

/** One role's permissions grouped by area, in a fixed area order for comparing roles. */
export function groupPermissions(keys: readonly string[]): PermissionGroup[] {
  const groups = new Map<PermissionArea | "other", PermissionGroup>();
  for (const key of keys) {
    const known = PERMISSION_VOCABULARY[key];
    const area = known?.area ?? "other";
    if (!groups.has(area)) groups.set(area, { area, actions: [] });
    groups.get(area)!.actions.push({ key, actionKey: known ? `access.permission.action.${known.action}` : null });
  }
  const order = [...PERMISSION_AREAS, "other"] as const;
  return [...groups.values()].sort((a, b) => order.indexOf(a.area) - order.indexOf(b.area));
}
