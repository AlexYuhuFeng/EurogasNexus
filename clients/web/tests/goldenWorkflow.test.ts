import assert from "node:assert/strict";
import test from "node:test";
import {
  classifyRouteFeasibility,
  decisionTaskFromLocation,
  decisionTaskToSearch,
} from "../src/app/model/commercialWorkflowModel.ts";
import { buildResourcePoolOptimizationRequest } from "../src/app/resourcePoolRequest.ts";

test("market to scenario handoff keeps route identity in the decision task", () => {
  assert.equal(decisionTaskFromLocation("?workspace=scenario"), "scenario");
  assert.equal(decisionTaskFromLocation("?workspace=review"), "review");
  assert.equal(
    decisionTaskToSearch("?gasDay=2026-09-07&route=route-1", "review"),
    "gasDay=2026-09-07&route=route-1&workspace=scenario&task=review",
  );
});

test("portfolio optimizer request carries company TSO access to the backend", () => {
  const request = buildResourcePoolOptimizationRequest(
    { annual_financing_rate_pct: 6 },
    [
      {
        resource_id: "preview-portfolio-contract-ttf-pool-2025",
        resource_name: "Preview TTF portfolio supply 2025",
        resource_type: "PIPELINE_IMPORT",
        delivery_mode: "PHYSICAL_ENTRY_DELIVERY",
        location_point_name: "TTF",
        available_quantity_mwh_per_day: 10_000,
        contract_cost_gbp_mwh: 25,
        variable_cost_gbp_mwh: 0,
        fuel_loss_allowance_pct: 0,
        delivery_tolerance_pct: 2,
        nomination_tolerance_pct: 1,
        tolerance_risk_allowance_gbp_mwh: 0.1,
        upstream_payment_lag_days: 20,
        screen_sale_cash_lag_days: 1,
        settlement_frequency: "monthly",
        required_tso_access: [],
        accessible_tsos: ["BBL Company"],
        pricing_method: "OPERATOR_CONTRACT",
        source_refs: [],
      },
    ],
    [
      {
        option_id: "route-1",
        label: "TTF -> BBL -> NBP",
        delivery_mode: "VIRTUAL_HUB_SALE",
        target_point_name: "NBP",
        route_topology_kind: "NETWORK_ROUTE",
        sale_price_gbp_mwh: 28,
        sale_price_currency: "GBP",
        sale_price_unit: "GBP/MWh",
        sale_price_source_system: "ICE_OCM_Sim",
        sale_price_source_reference: "ref",
        sale_price_observed_at_utc: "2026-09-07T05:00:00Z",
        sale_price_freshness: "simulated_live",
        sale_price_quality_score: 0.6,
        sale_price_simulated: true,
        source_family: "ICE_OCM",
        sale_price_original_currency: "GBP",
        sale_price_original_unit: "GBP/MWh",
        route_cost_gbp_mwh: 0.86,
        route_cost_currency: "GBP",
        route_cost_unit: "GBP/MWh",
        capacity_limit_mwh_per_day: 2000,
        capacity_status: "KNOWN",
        screen_sale_cash_lag_days: 1,
        eligible_resource_ids: ["preview-portfolio-contract-ttf-pool-2025"],
        required_tso_access: ["BBL Company"],
        source_refs: [],
      },
    ],
    [],
  );
  assert.deepEqual(request.resources[0].accessible_tsos, ["BBL Company"]);
  assert.equal(request.sale_options[0].required_tso_access[0], "BBL Company");
});

test("route feasibility never upgrades unknown access into feasible", () => {
  const route = {
    route_id: "route-1",
    route_name: "TTF -> BBL -> NBP",
    start_point_name: "TTF",
    target_point_name: "NBP",
    required_tso_access: ["BBL Company"],
  };
  assert.equal(classifyRouteFeasibility(route, null, null), "BLOCKED");
});
