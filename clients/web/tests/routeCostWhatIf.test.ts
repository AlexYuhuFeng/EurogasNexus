/**
 * The route-cost and indicative-netback what-if (slice D of the D3 decision).
 *
 * `POST /api/research/route-cost` and `POST /api/research/netback` are the last two declared client
 * calls with no consumer. Both are deterministic engines over the caller's own numbers, and the
 * theme these tests hold is that the surface does not become a second engine:
 *
 * - the netback request carries the cost **the engine returned**, never a total summed in the
 *   browser, so the two figures cannot disagree about the same number;
 * - the readiness rule mirrors the engines' own behaviour rather than inventing a stricter one: the
 *   engines accept a missing route label or no components and report them, so the surface refuses
 *   only what cannot be sent and repeats the engines' caveats as notes;
 * - a partial result stays partial. `human_review_required`, the missing inputs and the warnings
 *   are rendered from the payload.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ROUTE_COST_COMPONENT_TYPES,
  ROUTE_COST_MAX_COMPONENTS,
  emptyRouteCostDraft,
  netbackReadiness,
  netbackRequest,
  outcomeIsPartial,
  outcomeSources,
  routeCostDraftForRoute,
  routeCostReadiness,
  routeCostRequest,
  type RouteCostDraft,
} from "../src/app/model/routeCostModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function draftWith(patch: Partial<RouteCostDraft>): RouteCostDraft {
  return { ...emptyRouteCostDraft(), ...patch };
}

test("the rule refuses only what cannot be sent, and states the engines' caveats first", () => {
  // A blank amount is not a number: the request would have to invent one.
  const empty = routeCostReadiness(emptyRouteCostDraft());
  assert.equal(empty.canCompute, false);
  assert.deepEqual(empty.blockerKeys, ["portfolio.route_cost.blocker.amount_required"]);
  // The engines accept a missing route label, missing node ids and no components - they report them
  // as missing inputs and warnings - so the surface repeats them as notes instead of refusing.
  assert.deepEqual(empty.noteKeys, [
    "portfolio.route_cost.note.route_name_missing",
    "portfolio.route_cost.note.nodes_missing",
  ]);

  const costed = routeCostReadiness(
    draftWith({
      routeName: "NBP -> ZTP",
      fromNodeId: "node-a",
      toNodeId: "node-b",
      components: [{ ...emptyRouteCostDraft().components[0], amount: "2.5" }],
    }),
  );
  assert.equal(costed.canCompute, true);
  assert.deepEqual(costed.blockerKeys, []);
  assert.deepEqual(costed.noteKeys, []);

  // A distance that is not a number, or is negative, is refused: the engine takes a number or None.
  assert.deepEqual(
    routeCostReadiness(
      draftWith({
        routeKm: "far",
        components: [{ ...emptyRouteCostDraft().components[0], amount: "1" }],
      }),
    ).blockerKeys,
    ["portfolio.route_cost.blocker.route_km_invalid"],
  );
  assert.deepEqual(
    routeCostReadiness(
      draftWith({
        routeKm: "-5",
        components: [{ ...emptyRouteCostDraft().components[0], amount: "1" }],
      }),
    ).blockerKeys,
    ["portfolio.route_cost.blocker.route_km_invalid"],
  );
  assert.equal(
    routeCostReadiness(
      draftWith({
        routeKm: "0",
        components: [{ ...emptyRouteCostDraft().components[0], amount: "1" }],
      }),
    ).canCompute,
    true,
  );

  // No components at all is the engine's own case, not the client's: it returns a zero cost with a
  // warning, so the surface says so rather than refusing the run.
  const noComponents = routeCostReadiness(draftWith({ components: [] }));
  assert.equal(noComponents.canCompute, true);
  assert.ok(noComponents.noteKeys.includes("portfolio.route_cost.note.no_components"));

  // The component kinds are the engine's own list, and the form is bounded.
  assert.deepEqual([...ROUTE_COST_COMPONENT_TYPES], [
    "tariff",
    "fuel",
    "transport",
    "regas",
    "storage",
    "fx",
    "other",
  ]);
  assert.ok(ROUTE_COST_MAX_COMPONENTS > 0);
});

test("the request is composed only when the rule allows it, and declares what it means by no distance", () => {
  assert.equal(routeCostRequest(emptyRouteCostDraft()), null);

  const body = routeCostRequest(
    draftWith({
      routeName: "  NBP -> ZTP  ",
      fromNodeId: " node-a ",
      toNodeId: "node-b",
      components: [
        { componentType: "tariff", amount: "2.5", unit: "", currency: "", description: " IUK " },
        { componentType: "fuel", amount: "0.4", unit: "EUR/MWh", currency: "EUR", description: "" },
      ],
    }),
  );
  assert.ok(body);
  assert.equal(body.route_name, "NBP -> ZTP");
  assert.equal(body.from_node_id, "node-a");
  // A blank unit or currency is declared as the route's own default rather than sent empty.
  assert.deepEqual(body.components[0], {
    component_type: "tariff",
    amount: 2.5,
    unit: "EUR/MWh",
    currency: "EUR",
    description: "IUK",
  });
  // No distance is sent as null, which is the field's own "not supplied".
  assert.equal(body.route_km, null);

  const withDistance = routeCostRequest(
    draftWith({
      routeKm: "412.5",
      components: [{ ...emptyRouteCostDraft().components[0], amount: "1" }],
    }),
  );
  assert.equal(withDistance?.route_km, 412.5);
});

test("the netback is valued over the engine's cost, not over a total summed here", () => {
  const draft = draftWith({ marketPriceEurMwh: "24", toMarket: "ZTP", fxRate: "0.86", fxPair: "EURGBP" });

  // No cost yet: the netback has nothing to stand on.
  assert.deepEqual(netbackReadiness(draft, null).blockerKeys, [
    "portfolio.route_cost.blocker.cost_required",
  ]);
  assert.equal(netbackRequest(draft, null), null);

  // A price the engine would report as a missing input is refused before the click.
  assert.deepEqual(
    netbackReadiness(draftWith({ marketPriceEurMwh: "0" }), 2.9).blockerKeys,
    ["portfolio.route_cost.blocker.market_price_invalid"],
  );
  assert.deepEqual(
    netbackReadiness(draftWith({ marketPriceEurMwh: "" }), 2.9).blockerKeys,
    ["portfolio.route_cost.blocker.market_price_invalid"],
  );

  const body = netbackRequest(draft, 2.9);
  assert.ok(body);
  // The cost is the one the engine returned, passed through unchanged.
  assert.equal(body.route_cost_eur_mwh, 2.9);
  assert.equal(body.market_price_eur_mwh, 24);
  assert.equal(body.fx_rate, 0.86);
  assert.equal(body.from_market, "");
  assert.equal(body.to_market, "ZTP");
});

test("a partial result stays partial, and provenance is read from where the payload carries it", () => {
  const partial = {
    route_name: "r",
    from_node_id: "a",
    to_node_id: "b",
    total_cost_eur_mwh: 0,
    total_cost_boe: 0,
    components: [],
    route_km: null,
    research_only: true,
    human_review_required: true,
    assumptions: ["Cost components are additive."],
    missing_inputs: ["route_name is required."],
    warnings: ["No cost components provided; total cost is zero."],
    source_references: ["operator-input"],
    lineage: ["route-cost-computation"],
    generated_at_utc: "2026-09-19T00:00:00+00:00",
  };
  assert.equal(outcomeIsPartial(partial), true);
  assert.equal(outcomeIsPartial({ ...partial, human_review_required: false }), true);
  assert.equal(
    outcomeIsPartial({
      ...partial,
      human_review_required: false,
      missing_inputs: [],
      warnings: [],
    }),
    false,
  );
  assert.equal(outcomeIsPartial(null), false);

  // These routes put the engine's provenance inside `data` and return a meta without it, so a
  // surface reading meta would show nothing for a figure that does name its origin.
  assert.deepEqual(outcomeSources(partial), ["operator-input"]);
  assert.deepEqual(outcomeSources(null), []);
});

test("selecting a route prefills its label and nothing that would be a lie", () => {
  const draft = draftWith({ routeName: "typed by hand", fromNodeId: "node-a", toNodeId: "node-b" });
  const prefilled = routeCostDraftForRoute(draft, {
    route_id: "public-route-nbp-iuk-ztp",
    route_name: "NBP -> IUK -> ZTP",
    start_point_name: "NBP",
    target_point_name: "ZTP",
    business_model: "CROSS_BORDER_TRANSFER",
    route_legs: [],
    required_entry_point_name: null,
    required_exit_point_name: null,
    required_tso_access: [],
    source_systems: [],
  });
  assert.equal(prefilled.routeName, "NBP -> IUK -> ZTP");
  // A candidate carries point *names*; the engine's node fields are identifiers. Copying a name
  // into an identifier field would put a value where it does not belong.
  assert.equal(prefilled.fromNodeId, "node-a");
  assert.equal(prefilled.toNodeId, "node-b");
  assert.equal(routeCostDraftForRoute(draft, null), draft);
});

test("the panel configures and reports; the workspace header runs it", () => {
  const panel = readWebSource("components/RouteCostWhatIfPanel.tsx");
  const workspace = readWebSource("components/PortfolioWorkspace.tsx");
  const hook = readWebSource("app/model/useRouteCostWhatIf.ts");
  const client = readWebSource("api/client.ts");

  // Both calls, typed, through the loader seam.
  assert.match(hook, /api\s*\.routeCost\(body\)/);
  assert.match(hook, /api\s*\.netback\(netbackBody\)/);
  assert.match(client, /routeCost: \(body: RouteCostRequestDTO\) => post<RouteCostOutcomeDTO>/);
  assert.match(client, /netback: \(body: NetbackRequestDTO\) => post<NetbackOutcomeDTO>/);

  // The client does no arithmetic: no summation, and the netback body takes the engine's cost.
  for (const source of [hook, panel]) {
    assert.equal(/\breduce\(/.test(source), false, "nothing is summed on the client");
  }
  assert.match(hook, /netbackRequest\(draft, costResponse\.data\.total_cost_eur_mwh\)/);

  // The compute sits in the Routes task's primary slot, and the panel renders no run control of
  // its own: one act, one control.
  assert.match(workspace, /task === "routes" \? \(/);
  assert.match(workspace, /onClick=\{\(\) => void routeCost\.run\(\)\}/);
  assert.match(workspace, /disabled=\{!routeCost\.readiness\.canCompute \|\| routeCost\.busy\}/);
  assert.equal((workspace.match(/primaryAction=\{/g) ?? []).length, 1);
  assert.equal(panel.includes("api.routeCost"), false);
  assert.equal(panel.includes("routeCostRequest("), false);

  // A partial result is rendered as partial, with the engine's own statements.
  assert.match(panel, /outcomeIsPartial\(cost\)/);
  assert.match(panel, /outcomeIsPartial\(netback\)/);
  assert.match(panel, /cost\.missing_inputs\.map/);
  assert.match(panel, /cost\.warnings\.map/);
  assert.match(panel, /cost\.assumptions\.map/);
  assert.match(panel, /t\("portfolio\.route_cost\.partial"\)/);
});

test("the route-cost vocabulary is bilingual", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "portfolio.route_cost.title",
    "portfolio.route_cost.note",
    "portfolio.route_cost.as_of",
    "portfolio.route_cost.not_run",
    "portfolio.route_cost.route_name",
    "portfolio.route_cost.use_selected_route",
    "portfolio.route_cost.from_node",
    "portfolio.route_cost.to_node",
    "portfolio.route_cost.route_km",
    "portfolio.route_cost.components",
    "portfolio.route_cost.component_type",
    "portfolio.route_cost.amount",
    "portfolio.route_cost.unit",
    "portfolio.route_cost.currency",
    "portfolio.route_cost.description",
    "portfolio.route_cost.add_component",
    "portfolio.route_cost.remove_component",
    "portfolio.route_cost.netback_inputs",
    "portfolio.route_cost.to_market",
    "portfolio.route_cost.market_price",
    "portfolio.route_cost.fx_rate",
    "portfolio.route_cost.fx_pair",
    "portfolio.route_cost.netback_will_run",
    "portfolio.route_cost.result",
    "portfolio.route_cost.total_cost",
    "portfolio.route_cost.total_boe",
    "portfolio.route_cost.components_used",
    "portfolio.route_cost.provenance",
    "portfolio.route_cost.partial",
    "portfolio.route_cost.missing_inputs",
    "portfolio.route_cost.warnings",
    "portfolio.route_cost.assumptions",
    "portfolio.route_cost.netback_result",
    "portfolio.route_cost.netback",
    "portfolio.route_cost.netback_local",
    "portfolio.route_cost.route_cost_used",
    "portfolio.route_cost.run",
    "portfolio.route_cost.ready",
    "portfolio.route_cost.blocker.amount_required",
    "portfolio.route_cost.blocker.route_km_invalid",
    "portfolio.route_cost.blocker.cost_required",
    "portfolio.route_cost.blocker.market_price_invalid",
    "portfolio.route_cost.note.route_name_missing",
    "portfolio.route_cost.note.nodes_missing",
    "portfolio.route_cost.note.no_components",
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
  // Every component kind the form offers is declared in both locales.
  for (const type of ROUTE_COST_COMPONENT_TYPES) {
    const key = `portfolio.route_cost.component.${type}`;
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
  }
});
