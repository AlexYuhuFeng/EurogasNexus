import type {
  PortfolioOptimizationResultDTO,
  PortfolioSaleOptionDTO,
  RouteCandidateDTO,
  RouteRecommendationResultDTO,
  UpstreamContractDTO,
} from "@/api/client";
import type { ContractDraft } from "@/app/index";
import {
  SCENARIO_EDITABLE_DRAFT_INPUTS,
  resolvePoolFinancingRate,
} from "@/app/model/scenarioInputProvenance";
import type { ScenarioRouteEconomics } from "@/app/model/scenarioRouteEconomics";
import type { ContractNumberKey } from "@/components/ContractWorkbench";

type Translate = (key: string) => string;

interface ScenarioWorkspaceProps {
  routeCandidates: RouteCandidateDTO[];
  routeEconomics: ScenarioRouteEconomics;
  routeRecommendation: RouteRecommendationResultDTO | null;
  contract: ContractDraft;
  /**
   * The pool-optimiser run and the route comparison are the Decision workspace's primary
   * actions, not this panel's: each is one `compute` consequence and each has one control.
   * Both runs compose from the persisted resource-pool read; the only draft value this panel
   * can send is the annual financing-rate fallback (`app/model/scenarioInputProvenance.ts`).
   * The panel reports the preflight blockers and shows the allocation the runs produced.
   */
  poolInputBlockers: string[];
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  saleOptionById: Map<string, PortfolioSaleOptionDTO>;
  carriedRouteId: string | null;
  contextMismatch: boolean;
  /** The saved upstream contracts the pool optimiser's financing rate may come from. */
  upstreamContracts: UpstreamContractDTO[];
  t: Translate;
  updateContractNumber: (key: ContractNumberKey, value: string) => void;
}

function moneyPerMwh(value: number | null): string {
  return value === null ? "n/a" : `GBP ${value.toFixed(2)}/MWh`;
}

function economicsSourceKey(source: ScenarioRouteEconomics["source"]): string {
  if (source === "route_recommendation") return "result.source_route_recommendation";
  if (source === "resource_pool") return "result.source_resource_pool";
  return "result.source_unavailable";
}

export function ScenarioWorkspace({
  routeCandidates,
  routeEconomics,
  routeRecommendation,
  contract,
  poolInputBlockers,
  resourcePoolResult,
  saleOptionById,
  carriedRouteId,
  contextMismatch,
  upstreamContracts,
  t,
  updateContractNumber,
}: ScenarioWorkspaceProps) {
  const financingRate = resolvePoolFinancingRate(contract, upstreamContracts);

  return (
    <div className="workspace-grid scenario-page">
      {(carriedRouteId || contextMismatch) && (
        <div className="workspace-panel span-3 scenario-context-banner" role="status" aria-live="polite">
          {carriedRouteId && (
            <span><small>{t("scenario.carried_route")}</small><strong>{carriedRouteId}</strong></span>
          )}
          {contextMismatch && (
            <span className="context-mismatch"><strong>{t("context.result_mismatch")}</strong><small>{t("context.result_mismatch_hint")}</small></span>
          )}
        </div>
      )}
      <div className="workspace-panel span-2">
        <div className="section-heading"><span className="eyebrow">{t("home.recommended_paths")}</span><strong>{t("panel.routes")}</strong></div>
        <div className="route-list">
          {routeCandidates.map((route) => (
            <div
              key={`scenario-route-${route.route_id}`}
              className={`route-row route-candidate ${carriedRouteId === route.route_id ? "carried-route" : ""}`}
            >
              <span>{route.route_name}</span>
              <strong>{route.required_tso_access.join(", ") || "n/a"}</strong>
            </div>
          ))}
        </div>
      </div>
      <div className="workspace-panel">
        <h2>
          {t(routeEconomics.scope === "selected" ? "result.selected_route_economics" : "result.recommended_route_economics")}
          {routeEconomics.routeId ? ` · ${routeEconomics.routeId}` : ""}
        </h2>
        <p className="muted">{t("result.economics_source")}: {t(economicsSourceKey(routeEconomics.source))}</p>
        <div className="metric-grid two-column">
          <div><span>{t("result.purchase")}</span><strong>{moneyPerMwh(routeEconomics.purchasePrice)}</strong></div>
          <div><span>{t("result.sale")}</span><strong>{moneyPerMwh(routeEconomics.salePrice)}</strong></div>
          <div><span>{t("result.route_cost")}</span><strong>{moneyPerMwh(routeEconomics.routeCharge)}</strong></div>
          <div>
            <span>{t(
              routeEconomics.volumeScope === "resource"
                ? "result.resource_allocation_volume"
                : routeEconomics.scope === "selected"
                  ? "result.selected_route_volume"
                  : "result.recommended_route_volume",
            )}</span>
            <strong>{routeEconomics.allocatedVolumeMwhPerDay == null ? "n/a" : `${routeEconomics.allocatedVolumeMwhPerDay.toLocaleString()} MWh/d`}</strong>
          </div>
        </div>
      </div>
      <div className="workspace-panel span-3">
        <div className="section-heading"><span className="eyebrow">{t("home.resource_pool")}</span><strong>{t("panel.route_allocation")}</strong></div>
        <div className="economics-grid wide">
          {/* The only draft value either action consumes is the annual financing-rate
              fallback; the persisted resource-pool read supplies every other input. */}
          {SCENARIO_EDITABLE_DRAFT_INPUTS.map(({ key, labelKey }) => (
            <label key={key}>{t(labelKey)}<input
              type="number"
              min="0"
              step="any"
              value={financingRate.pct}
              readOnly={financingRate.source === "saved_upstream_contract"}
              onChange={(event) => updateContractNumber(key, event.target.value)}
            /></label>
          ))}
        </div>
        <p className="muted">
          {financingRate.source === "saved_upstream_contract"
            ? t("scenario.financing_rate_from_saved_contract")
            : t("scenario.financing_rate_from_draft_fallback")}
        </p>
        <p className="panel-copy">{t("scenario.compare_location")}</p>
        <p className="panel-copy">{t("scenario.optimizer_location")}</p>
        {poolInputBlockers.length > 0 && (
          <div className="runtime-blocker-list compact">
            <strong>{t("home.optimizer_blocked")}</strong>
            {poolInputBlockers.map((blocker) => <span key={`scenario-blocker-${blocker}`}>{blocker}</span>)}
          </div>
        )}
        {resourcePoolResult && (
          <div className="route-list compact-route-list">
            {resourcePoolResult.allocations.map((allocation) => {
              const option = saleOptionById.get(allocation.option_id);
              return (
                <div key={`scenario-pool-${allocation.resource_id}-${allocation.option_id}`} className="route-row route-candidate">
                  <span>{option?.label ?? allocation.option_id}</span>
                  <strong>{allocation.allocated_quantity_mwh_per_day.toLocaleString()} MWh/d</strong>
                  <small>{allocation.net_margin_gbp_mwh.toFixed(2)} GBP/MWh / GBP {Math.round(allocation.net_pnl_gbp_per_day).toLocaleString()}</small>
                </div>
              );
            })}
          </div>
        )}
        {routeRecommendation && (
          <div className="route-list compact-route-list">
            {routeRecommendation.allocations.map((allocation) => (
              <div key={`allocation-${allocation.route_id}`} className="route-row route-candidate">
                <span>{allocation.route_name}</span>
                <strong>{allocation.allocated_mwh_per_day.toLocaleString()} MWh/d</strong>
                <small>{allocation.destination_market ?? "market"} / {allocation.netback == null ? "n/a" : `${allocation.netback.toFixed(2)} GBP/MWh`}</small>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
