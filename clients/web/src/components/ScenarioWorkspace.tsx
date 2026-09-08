import type {
  PortfolioOptimizationResultDTO,
  PortfolioSaleOptionDTO,
  RouteCandidateDTO,
  RouteRecommendationResultDTO,
} from "@/api/client";
import type { ContractDraft } from "@/app/index";
import type { ScenarioRouteEconomics } from "@/app/model/scenarioRouteEconomics";
import type { ContractNumberKey } from "@/components/ContractWorkbench";

type Translate = (key: string) => string;

interface ScenarioWorkspaceProps {
  routeCandidates: RouteCandidateDTO[];
  routeEconomics: ScenarioRouteEconomics;
  routeRecommendation: RouteRecommendationResultDTO | null;
  contract: ContractDraft;
  canRunPoolOptimizer: boolean;
  canCompareRoutes: boolean;
  poolInputBlockers: string[];
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  saleOptionById: Map<string, PortfolioSaleOptionDTO>;
  carriedRouteId: string | null;
  contextMismatch: boolean;
  t: Translate;
  updateContractNumber: (key: ContractNumberKey, value: string) => void;
  onOptimize: () => void;
  onCompare: () => void;
}

const ECONOMIC_INPUTS: Array<{ key: ContractNumberKey; label: string }> = [
  { key: "delivery_quantity_mwh_per_day", label: "economics.volume" },
  { key: "contract_price_gbp_mwh", label: "economics.contract_price" },
  { key: "nbp_sale_price_gbp_mwh", label: "economics.nbp_price" },
  { key: "physical_exit_sale_price_gbp_mwh", label: "economics.physical_price" },
  { key: "delivery_tolerance_pct", label: "economics.delivery_tolerance" },
  { key: "nomination_tolerance_pct", label: "economics.nomination_tolerance" },
  { key: "screen_sale_cash_lag_days", label: "economics.cash_lag" },
  { key: "annual_financing_rate_pct", label: "economics.finance_rate" },
];

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
  canRunPoolOptimizer,
  canCompareRoutes,
  poolInputBlockers,
  resourcePoolResult,
  saleOptionById,
  carriedRouteId,
  contextMismatch,
  t,
  updateContractNumber,
  onOptimize,
  onCompare,
}: ScenarioWorkspaceProps) {
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
          {ECONOMIC_INPUTS.map(({ key, label }) => (
            <label key={key}>{t(label)}<input type="number" value={contract[key] ?? ""} onChange={(event) => updateContractNumber(key, event.target.value)} /></label>
          ))}
        </div>
        <div className="action-row">
          <button type="button" disabled={!canRunPoolOptimizer} onClick={onOptimize}>{t("home.optimize_pool")}</button>
          <button type="button" disabled={!canCompareRoutes} onClick={onCompare}>{t("economics.compare")}</button>
        </div>
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
