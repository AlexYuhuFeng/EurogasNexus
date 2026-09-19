/**
 * The route-cost and indicative-netback what-if (slice D of the D3 decision).
 *
 * `POST /api/research/route-cost` and `POST /api/research/netback` are the two declared computes
 * that had no consumer. Both are deterministic engines over the caller's own numbers - a route's
 * cost components, then a destination market price - and both answer with the research contract:
 * the figure, the assumptions it rests on, the inputs it lacked, its warnings and its provenance
 * (`operator-input`: these are the caller's numbers, not market data).
 *
 * The client does not do the arithmetic. The netback request carries the **cost the engine
 * returned**, never a total summed here, and the surface renders what came back instead of
 * computing a second opinion.
 *
 * The readiness rule mirrors the engines' own behaviour rather than inventing a stricter one: the
 * engines accept a missing route label or no components and report it as a missing input or a
 * warning, so the surface does not refuse them - it refuses only what cannot be sent at all (an
 * amount that is not a number, a distance that is not one) and repeats the engines' own caveats as
 * notes before the click.
 */

import type {
  NetbackOutcomeDTO,
  NetbackRequestDTO,
  RouteCandidateDTO,
  RouteCostComponentDTO,
  RouteCostOutcomeDTO,
  RouteCostRequestDTO,
} from "@/api/client";

/** The component kinds `domain/research/route_cost.py` names. */
export const ROUTE_COST_COMPONENT_TYPES = [
  "tariff",
  "fuel",
  "transport",
  "regas",
  "storage",
  "fx",
  "other",
] as const;

export type RouteCostComponentType = (typeof ROUTE_COST_COMPONENT_TYPES)[number];

/** One cost component as the form holds it: text in, so a half-typed number is a state. */
export interface RouteCostComponentDraft {
  readonly componentType: string;
  readonly amount: string;
  readonly unit: string;
  readonly currency: string;
  readonly description: string;
}

export interface RouteCostDraft {
  readonly routeName: string;
  readonly fromNodeId: string;
  readonly toNodeId: string;
  readonly routeKm: string;
  readonly components: readonly RouteCostComponentDraft[];
  readonly toMarket: string;
  readonly marketPriceEurMwh: string;
  readonly fxRate: string;
  readonly fxPair: string;
}

export interface RouteCostReadiness {
  readonly canCompute: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
  /**
   * What the engines will report themselves if the run proceeds: their own `missing_inputs` and
   * warnings, restated before the click rather than discovered afterwards.
   */
  readonly noteKeys: readonly string[];
}

/** How many components one run may declare, so the form stays bounded. */
export const ROUTE_COST_MAX_COMPONENTS = 12;

/** The default unit and currency the route's own request model declares. */
export const ROUTE_COST_DEFAULT_UNIT = "EUR/MWh";
export const ROUTE_COST_DEFAULT_CURRENCY = "EUR";

export function emptyRouteCostComponent(): RouteCostComponentDraft {
  return {
    componentType: "tariff",
    amount: "",
    unit: ROUTE_COST_DEFAULT_UNIT,
    currency: ROUTE_COST_DEFAULT_CURRENCY,
    description: "",
  };
}

export function emptyRouteCostDraft(): RouteCostDraft {
  return {
    routeName: "",
    fromNodeId: "",
    toNodeId: "",
    routeKm: "",
    components: [emptyRouteCostComponent()],
    toMarket: "",
    marketPriceEurMwh: "",
    fxRate: "1",
    fxPair: "",
  };
}

/**
 * The draft a selected route candidate starts from.
 *
 * Only the route's **name** is taken from the candidate. The engine's `from_node_id` and
 * `to_node_id` are node identifiers, and a candidate carries point *names* - copying a name into an
 * identifier field would put a value where it does not belong, so those fields stay for the caller
 * (the reference register lists the identifiers the deployment uses).
 */
export function routeCostDraftForRoute(
  draft: RouteCostDraft,
  route: RouteCandidateDTO | null,
): RouteCostDraft {
  if (!route) return draft;
  return { ...draft, routeName: route.route_name };
}

function parsedNumber(value: string): number | null {
  const text = value.trim();
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

/** The rule the compute action is enabled by, and the caveats it states before the click. */
export function routeCostReadiness(draft: RouteCostDraft): RouteCostReadiness {
  const blockerKeys: string[] = [];
  for (const component of draft.components) {
    if (parsedNumber(component.amount) === null) {
      blockerKeys.push("portfolio.route_cost.blocker.amount_required");
      break;
    }
  }
  if (draft.routeKm.trim() && (parsedNumber(draft.routeKm) ?? -1) < 0) {
    blockerKeys.push("portfolio.route_cost.blocker.route_km_invalid");
  }

  const noteKeys: string[] = [];
  if (!draft.routeName.trim()) noteKeys.push("portfolio.route_cost.note.route_name_missing");
  if (!draft.fromNodeId.trim() || !draft.toNodeId.trim()) {
    noteKeys.push("portfolio.route_cost.note.nodes_missing");
  }
  if (draft.components.length === 0) noteKeys.push("portfolio.route_cost.note.no_components");

  return {
    canCompute: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys[0] ?? null,
    noteKeys,
  };
}

/** The route-cost body, or null when the rule blocks it: a partial body would invent a number. */
export function routeCostRequest(draft: RouteCostDraft): RouteCostRequestDTO | null {
  if (!routeCostReadiness(draft).canCompute) return null;
  const components: RouteCostComponentDTO[] = draft.components.map((component) => ({
    component_type: component.componentType,
    amount: parsedNumber(component.amount) ?? 0,
    unit: component.unit.trim() || ROUTE_COST_DEFAULT_UNIT,
    currency: component.currency.trim() || ROUTE_COST_DEFAULT_CURRENCY,
    description: component.description.trim(),
  }));
  const routeKm = parsedNumber(draft.routeKm);
  return {
    route_name: draft.routeName.trim(),
    from_node_id: draft.fromNodeId.trim(),
    to_node_id: draft.toNodeId.trim(),
    components,
    route_km: routeKm === null ? null : routeKm,
  };
}

/**
 * Whether the netback half can run.
 *
 * It needs a cost the engine produced (never a sum kept here) and a market price the engine will
 * accept: `compute_netback` reports a non-positive price as a missing input, so the surface asks
 * for a positive one before the click.
 */
export function netbackReadiness(
  draft: RouteCostDraft,
  routeCostEurMwh: number | null,
): { canCompute: boolean; blockerKeys: readonly string[]; firstBlockerKey: string | null } {
  const blockerKeys: string[] = [];
  if (routeCostEurMwh === null) blockerKeys.push("portfolio.route_cost.blocker.cost_required");
  const price = parsedNumber(draft.marketPriceEurMwh);
  if (price === null || price <= 0) {
    blockerKeys.push("portfolio.route_cost.blocker.market_price_invalid");
  }
  return {
    canCompute: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys[0] ?? null,
  };
}

/** The netback body, or null when the rule blocks it. */
export function netbackRequest(
  draft: RouteCostDraft,
  routeCostEurMwh: number | null,
): NetbackRequestDTO | null {
  if (!netbackReadiness(draft, routeCostEurMwh).canCompute) return null;
  const price = parsedNumber(draft.marketPriceEurMwh) ?? 0;
  const fxRate = parsedNumber(draft.fxRate) ?? 1;
  return {
    route_name: draft.routeName.trim(),
    from_market: draft.fromNodeId.trim(),
    to_market: draft.toMarket.trim(),
    market_price_eur_mwh: price,
    route_cost_eur_mwh: routeCostEurMwh ?? 0,
    fx_rate: fxRate,
    fx_pair: draft.fxPair.trim(),
  };
}

/**
 * Whether a research compute result is partial: the engines mark `human_review_required` when they
 * lacked an input or raised a warning, and that marker is what the surface renders.
 */
export function outcomeIsPartial(
  outcome: RouteCostOutcomeDTO | NetbackOutcomeDTO | null,
): boolean {
  if (!outcome) return false;
  return (
    outcome.human_review_required ||
    outcome.missing_inputs.length > 0 ||
    outcome.warnings.length > 0
  );
}

/**
 * The provenance the engine reported, read from where the payload actually carries it.
 *
 * These routes put the engine's own `source_references` inside `data` and return a meta without
 * them, so a surface reading meta would show nothing for a figure that does name its origin.
 */
export function outcomeSources(
  outcome: RouteCostOutcomeDTO | NetbackOutcomeDTO | null,
): readonly string[] {
  return outcome?.source_references ?? [];
}
