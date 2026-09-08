import assert from "node:assert/strict";
import test from "node:test";
import {
  DECISION_TASKS,
  PORTFOLIO_TASKS,
  classifyRouteFeasibility,
  dedupeWarnings,
  decisionTaskFromLocation,
  decisionTaskToSearch,
  portfolioTaskFromLocation,
  portfolioTaskToSearch,
} from "../src/app/model/commercialWorkflowModel.ts";
import { selectScenarioRouteEconomics } from "../src/app/model/scenarioRouteEconomics.ts";
import { workspaceTaskSearch } from "../src/workspaceNavigation.ts";

function route(overrides: Record<string, unknown> = {}) {
  return {
    route_id: "route-1",
    route_name: "Route 1",
    start_point_name: "NBP",
    target_point_name: "TTF",
    required_tso_access: [],
    ...overrides,
  } as Parameters<typeof classifyRouteFeasibility>[0];
}

test("portfolio tasks are overview resources routes exposure", () => {
  assert.deepEqual(PORTFOLIO_TASKS, ["overview", "resources", "routes", "exposure"]);
  assert.deepEqual(DECISION_TASKS, ["scenario", "optimize", "review"]);
});

test("portfolio and decision task deep links preserve context", () => {
  assert.equal(portfolioTaskFromLocation("?task=routes"), "routes");
  assert.equal(portfolioTaskFromLocation("?task=unknown"), "overview");
  assert.equal(decisionTaskFromLocation("?task=review"), "review");
  assert.equal(decisionTaskFromLocation("?task=unknown"), "scenario");
  assert.equal(decisionTaskFromLocation("?workspace=review"), "review");
  assert.equal(decisionTaskFromLocation("?workspace=review&task=optimize"), "review");
  assert.equal(decisionTaskFromLocation("?workspace=scenario"), "scenario");
  assert.equal(
    portfolioTaskToSearch("?gasDay=2026-09-07", "resources"),
    "gasDay=2026-09-07&workspace=contracts&task=resources",
  );
  assert.equal(
    decisionTaskToSearch("?gasDay=2026-09-07", "optimize"),
    "gasDay=2026-09-07&workspace=scenario&task=optimize",
  );
  assert.equal(
    decisionTaskToSearch("?gasDay=2026-09-07", "review"),
    "gasDay=2026-09-07&workspace=review&task=review",
  );
});

test("workspace handoffs normalize local task and preserve trader context", () => {
  const search = "?gasDay=2026-09-07&product=day-ahead&hub=NBP&resource=res-1&route=route-1&task=optimize";
  assert.equal(
    workspaceTaskSearch(search, "review"),
    "gasDay=2026-09-07&product=day-ahead&hub=NBP&resource=res-1&route=route-1&task=review&workspace=review",
  );
  assert.equal(
    workspaceTaskSearch(search, "market"),
    "gasDay=2026-09-07&product=day-ahead&hub=NBP&resource=res-1&route=route-1&workspace=market",
  );
  assert.equal(
    workspaceTaskSearch(search, "scenario", "optimize"),
    "gasDay=2026-09-07&product=day-ahead&hub=NBP&resource=res-1&route=route-1&task=optimize&workspace=scenario",
  );
  const samePageScenario = workspaceTaskSearch(search, "scenario");
  assert.equal(
    samePageScenario,
    "gasDay=2026-09-07&product=day-ahead&hub=NBP&resource=res-1&route=route-1&task=scenario&workspace=scenario",
  );
  assert.equal(decisionTaskFromLocation(samePageScenario), "scenario");
});

test("browser history locations rehydrate matching decision content", () => {
  const reviewSearch = workspaceTaskSearch("?gasDay=2026-09-07&task=optimize", "review");
  const optimizeSearch = decisionTaskToSearch(reviewSearch, "optimize");
  assert.equal(decisionTaskFromLocation(reviewSearch), "review");
  assert.equal(decisionTaskFromLocation(optimizeSearch), "optimize");
});

test("route feasibility is conservative and never treats unknown as feasible", () => {
  const candidate = route();
  assert.equal(classifyRouteFeasibility(candidate, null, null), "UNKNOWN");
  const unknownAccess = route({ required_tso_access: ["GTS"] });
  assert.equal(classifyRouteFeasibility(unknownAccess, null, null), "UNKNOWN");
});

test("positive SUCCESS allocation proves a route feasible despite required TSO access", () => {
  const candidate = route({ route_id: "public-route-ttf-bbl-nbp", required_tso_access: ["BBL Company"] });
  const optimizer = {
    status: "SUCCESS",
    allocations: [{ option_id: candidate.route_id, allocated_quantity_mwh_per_day: 2000, warnings: [] }],
    missing_inputs: [],
    warnings: [],
  } as Parameters<typeof classifyRouteFeasibility>[2];

  assert.equal(classifyRouteFeasibility(candidate, null, optimizer), "FEASIBLE");
});

function scenarioInputs(overrides: Record<string, unknown> = {}) {
  return {
    carriedRouteId: "route-2",
    selectedResourceId: "resource-1",
    routeRecommendation: {
      allocations: [
        { route_id: "route-1", route_name: "Route 1", allocated_mwh_per_day: 10, route_cost: 1, sale_price: 41 },
        { route_id: "route-2", route_name: "Route 2", allocated_mwh_per_day: 20, route_cost: 2, sale_price: 52 },
      ],
    },
    resourcePoolResult: null,
    portfolioResources: [{ resource_id: "resource-1", contract_cost_gbp_mwh: 30 }],
    saleOptionById: new Map([
      ["route-1", { option_id: "route-1", route_cost_gbp_mwh: 1 }],
      ["route-2", { option_id: "route-2", route_cost_gbp_mwh: 2 }],
    ]),
    ...overrides,
  } as Parameters<typeof selectScenarioRouteEconomics>[0];
}

test("scenario economics selects the second route and its selected resource", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs());

  assert.deepEqual(economics, {
    routeId: "route-2",
    scope: "selected",
    source: "route_recommendation",
    volumeScope: "route",
    purchasePrice: 30,
    salePrice: 52,
    routeCharge: 2,
    allocatedVolumeMwhPerDay: 20,
  });
});

test("scenario economics keeps the first recommendation as the explicit no-selection default", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs({ carriedRouteId: null }));

  assert.deepEqual(economics, {
    routeId: "route-1",
    scope: "recommended",
    source: "route_recommendation",
    volumeScope: "route",
    purchasePrice: 30,
    salePrice: 41,
    routeCharge: 1,
    allocatedVolumeMwhPerDay: 10,
  });
});

test("scenario economics keeps route recommendation fields coherent over pool and input conflicts", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs({
    resourcePoolResult: {
      allocations: [{
        resource_id: "resource-1",
        option_id: "route-2",
        allocated_quantity_mwh_per_day: 999,
        gross_sale_price_gbp_mwh: 99,
      }],
    },
    saleOptionById: new Map([
      ["route-2", { option_id: "route-2", route_cost_gbp_mwh: 77 }],
    ]),
  }));

  assert.equal(economics.source, "route_recommendation");
  assert.equal(economics.volumeScope, "route");
  assert.equal(economics.salePrice, 52);
  assert.equal(economics.routeCharge, 2);
  assert.equal(economics.allocatedVolumeMwhPerDay, 20);
});

test("scenario economics is unavailable for an unknown selected route", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs({ carriedRouteId: "missing-route" }));

  assert.equal(economics.scope, "selected");
  assert.equal(economics.routeId, "missing-route");
  assert.equal(economics.source, "unavailable");
  assert.equal(economics.volumeScope, "unavailable");
  assert.equal(economics.purchasePrice, null);
  assert.equal(economics.salePrice, null);
  assert.equal(economics.routeCharge, null);
  assert.equal(economics.allocatedVolumeMwhPerDay, null);
});

test("scenario economics is unavailable when no result identifies a route", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs({
    carriedRouteId: null,
    routeRecommendation: null,
    resourcePoolResult: null,
  }));

  assert.equal(economics.routeId, null);
  assert.equal(economics.source, "unavailable");
  assert.equal(economics.volumeScope, "unavailable");
  assert.equal(economics.purchasePrice, null);
  assert.equal(economics.salePrice, null);
  assert.equal(economics.routeCharge, null);
  assert.equal(economics.allocatedVolumeMwhPerDay, null);
});

test("scenario economics preserves a zero route cost", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs({
    routeRecommendation: {
      allocations: [{ route_id: "route-2", route_name: "Route 2", allocated_mwh_per_day: 20, route_cost: 0, sale_price: 52 }],
    },
    saleOptionById: new Map(),
  }));

  assert.equal(economics.source, "route_recommendation");
  assert.equal(economics.volumeScope, "route");
  assert.equal(economics.routeCharge, 0);
});

test("scenario economics uses a coherent pool fallback when route result is absent", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs({
    routeRecommendation: null,
    resourcePoolResult: {
      allocations: [{
        resource_id: "resource-1",
        option_id: "route-2",
        allocated_quantity_mwh_per_day: 40,
        gross_sale_price_gbp_mwh: 61,
      }],
    },
    saleOptionById: new Map([
      ["route-2", { option_id: "route-2", route_cost_gbp_mwh: 99 }],
    ]),
  }));

  assert.deepEqual(economics, {
    routeId: "route-2",
    scope: "selected",
    source: "resource_pool",
    volumeScope: "resource",
    purchasePrice: 30,
    salePrice: 61,
    routeCharge: null,
    allocatedVolumeMwhPerDay: 40,
  });
});

test("scenario economics does not choose an arbitrary pool allocation without a resource selection", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs({
    selectedResourceId: null,
    routeRecommendation: null,
    resourcePoolResult: {
      allocations: [
        {
          resource_id: "resource-1",
          option_id: "route-2",
          allocated_quantity_mwh_per_day: 40,
          gross_sale_price_gbp_mwh: 61,
        },
        {
          resource_id: "resource-2",
          option_id: "route-2",
          allocated_quantity_mwh_per_day: 20,
          gross_sale_price_gbp_mwh: 62,
        },
      ],
    },
  }));

  assert.deepEqual(economics, {
    routeId: "route-2",
    scope: "selected",
    source: "unavailable",
    volumeScope: "unavailable",
    purchasePrice: null,
    salePrice: null,
    routeCharge: null,
    allocatedVolumeMwhPerDay: null,
  });
});

test("scenario economics leaves purchase unavailable without a selected resource", () => {
  const economics = selectScenarioRouteEconomics(scenarioInputs({ selectedResourceId: null }));

  assert.equal(economics.source, "route_recommendation");
  assert.equal(economics.purchasePrice, null);
});

test("explicit denied route blockers override a conflicting allocation", () => {
  const candidate = route({ route_id: "route-blocked", required_tso_access: ["GTS"] });
  const recommendation = {
    status: "PARTIAL",
    allocations: [{ route_id: candidate.route_id, allocated_mwh_per_day: 10 }],
    excluded_routes: [{ route_id: candidate.route_id, blockers: ["TSO_ACCESS_MISSING:GTS"] }],
    warnings: [],
  } as Parameters<typeof classifyRouteFeasibility>[1];

  assert.equal(classifyRouteFeasibility(candidate, recommendation, null), "BLOCKED");
});

test("zero allocation is not feasibility evidence", () => {
  const candidate = route({ route_id: "route-zero", required_tso_access: [] });
  const optimizer = {
    status: "SUCCESS",
    allocations: [{ option_id: candidate.route_id, allocated_quantity_mwh_per_day: 0, warnings: [] }],
    missing_inputs: [],
    warnings: [],
  } as Parameters<typeof classifyRouteFeasibility>[2];

  assert.equal(classifyRouteFeasibility(candidate, null, optimizer), "UNKNOWN");
});

test("failed result with a stale allocation is not feasibility evidence", () => {
  const candidate = route({ route_id: "route-failed" });
  const optimizer = {
    status: "FAILED",
    allocations: [{ option_id: candidate.route_id, allocated_quantity_mwh_per_day: 10, warnings: [] }],
    missing_inputs: [],
    warnings: [],
  } as Parameters<typeof classifyRouteFeasibility>[2];

  assert.equal(classifyRouteFeasibility(candidate, null, optimizer), "UNKNOWN");
});

test("route diagnostics use exact route identity, not route ID prefixes", () => {
  const candidate = route({ route_id: "route1" });
  const optimizer = {
    status: "BLOCKED",
    allocations: [],
    missing_inputs: ["ROUTE_COST_MISSING:route10:TARIFF_MISSING"],
    warnings: [],
  } as Parameters<typeof classifyRouteFeasibility>[2];

  assert.equal(classifyRouteFeasibility(candidate, null, optimizer), "UNKNOWN");
});

test("exact route diagnostics block the matching route", () => {
  const candidate = route({ route_id: "route1" });
  const optimizer = {
    status: "BLOCKED",
    allocations: [],
    missing_inputs: ["ROUTE_COST_MISSING:route1:TARIFF_MISSING"],
    warnings: [],
  } as Parameters<typeof classifyRouteFeasibility>[2];

  assert.equal(classifyRouteFeasibility(candidate, null, optimizer), "BLOCKED");
});

test("matching option warnings affect only the allocated route", () => {
  const candidate = route({ route_id: "route1" });
  const optimizer = {
    status: "SUCCESS",
    allocations: [{ option_id: candidate.route_id, allocated_quantity_mwh_per_day: 10, warnings: [] }],
    missing_inputs: [],
    warnings: [],
  } as Parameters<typeof classifyRouteFeasibility>[2];
  const options = {
    warnings: ["ROUTE_WARNING:route1", "ROUTE_WARNING:route10"],
    blockers: [],
    sale_options: [],
    portfolio_resources: [],
  } as Parameters<typeof classifyRouteFeasibility>[3];

  assert.equal(classifyRouteFeasibility(candidate, null, optimizer, options), "FEASIBLE_WITH_WARNINGS");
  assert.equal(
    classifyRouteFeasibility(route({ route_id: "route10" }), null, optimizer, options),
    "UNKNOWN",
  );
});

test("warning aggregation preserves order and removes duplicates", () => {
  assert.deepEqual(
    dedupeWarnings(["PORTFOLIO_VOLUME_UNALLOCATED", "ROUTE_CAPACITY_SHORTFALL"], ["ROUTE_CAPACITY_SHORTFALL"], ["OPTIONS_WARNING"]),
    ["PORTFOLIO_VOLUME_UNALLOCATED", "ROUTE_CAPACITY_SHORTFALL", "OPTIONS_WARNING"],
  );
});
