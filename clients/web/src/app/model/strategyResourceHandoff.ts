import type { UpstreamContractDTO } from "../../api/client.ts";
import { DEFAULT_STRATEGY_FORM, type StrategyDesignFormState } from "./strategyDraftModel.ts";

/** Carry identity and native daily energy only. A base price is not an all-in cost. */
export function strategyFormForContract(contract: UpstreamContractDTO): StrategyDesignFormState {
  const metadata = contract as unknown as Record<string, unknown>;
  const compatible = (metadata.currency === undefined || metadata.currency === "GBP") &&
    (metadata.unit === undefined || metadata.unit === "MWh") &&
    (metadata.quantity_unit === undefined || metadata.quantity_unit === "MWh/day");
  const quantity = contract.delivery_quantity_mwh_per_day;
  return {
    ...DEFAULT_STRATEGY_FORM,
    resourceId: contract.contract_id,
    resourceName: contract.contract_name,
    resourceQuantity: compatible && Number.isFinite(quantity) && quantity > 0 ? String(quantity) : "",
    resourceCost: "",
    resourceBasisBlocked: !compatible,
    // The OCM component needs an explicit price-series choice; the contract's delivery
    // point cannot establish that choice or convert a continental price basis into GBP.
    hubs: "",
    dayAheadNames: "",
    intradayNames: "",
  };
}
