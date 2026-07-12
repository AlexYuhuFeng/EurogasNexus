import type {
  PortfolioOptimizationResultDTO,
  PortfolioSaleOptionDTO,
  RouteCandidateDTO,
  RouteRecommendationResultDTO,
} from "@/api/client";
import type { ContractDraft } from "@/app/index";
import type { ContractNumberKey } from "@/components/ContractWorkbench";

type Translate = (key: string) => string;

interface ScenarioWorkspaceProps {
  routeCandidates: RouteCandidateDTO[];
  purchasePrice: number | null;
  salePrice: number | null;
  routeCharge: number | null;
  routeRecommendation: RouteRecommendationResultDTO | null;
  contract: ContractDraft;
  canRunPoolOptimizer: boolean;
  canCompareRoutes: boolean;
  poolInputBlockers: string[];
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  saleOptionById: Map<string, PortfolioSaleOptionDTO>;
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
  return value === null ? "n/a" : `EUR ${value.toFixed(2)}/MWh`;
}

export function ScenarioWorkspace({
  routeCandidates,
  purchasePrice,
  salePrice,
  routeCharge,
  routeRecommendation,
  contract,
  canRunPoolOptimizer,
  canCompareRoutes,
  poolInputBlockers,
  resourcePoolResult,
  saleOptionById,
  t,
  updateContractNumber,
  onOptimize,
  onCompare,
}: ScenarioWorkspaceProps) {
  return (
    <div className="workspace-grid scenario-page">
      <div className="workspace-panel span-2">
        <div className="section-heading"><span className="eyebrow">{t("home.recommended_paths")}</span><strong>{t("panel.routes")}</strong></div>
        <div className="route-list">
          {routeCandidates.map((route) => (
            <div key={`scenario-route-${route.route_id}`} className="route-row route-candidate"><span>{route.route_name}</span><strong>{route.required_tso_access.join(", ") || "n/a"}</strong></div>
          ))}
        </div>
      </div>
      <div className="workspace-panel">
        <h3>{t("result.economics_snapshot")}</h3>
        <div className="metric-grid two-column">
          <div><span>{t("result.purchase")}</span><strong>{moneyPerMwh(purchasePrice)}</strong></div>
          <div><span>{t("result.sale")}</span><strong>{moneyPerMwh(salePrice)}</strong></div>
          <div><span>{t("result.route_cost")}</span><strong>{moneyPerMwh(routeCharge)}</strong></div>
          <div><span>{t("result.cash_value")}</span><strong>{routeRecommendation ? `${routeRecommendation.total_allocated_mwh_per_day.toLocaleString()} MWh/d` : "n/a"}</strong></div>
        </div>
      </div>
      <div className="workspace-panel span-3">
        <div className="section-heading"><span className="eyebrow">{t("home.resource_pool")}</span><strong>{t("panel.route_allocation")}</strong></div>
        <div className="economics-grid wide">
          {ECONOMIC_INPUTS.map(({ key, label }) => (
            <label key={key}>{t(label)}<input type="number" value={contract[key]} onChange={(event) => updateContractNumber(key, event.target.value)} /></label>
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
                  <small>{allocation.net_margin_gbp_mwh.toFixed(2)} EUR/MWh / EUR {Math.round(allocation.net_pnl_gbp_per_day).toLocaleString()}</small>
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
                <small>{allocation.destination_market ?? "market"} / {allocation.netback == null ? "n/a" : `${allocation.netback.toFixed(2)} EUR/MWh`}</small>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
