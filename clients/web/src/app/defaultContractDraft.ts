import type { ContractDraft as ContractDraftModel } from "@/components/ContractWorkbench";

export type ContractDraft = ContractDraftModel;

export const defaultContractDraft: ContractDraft = {
  contract_id: "operator-ttf-supply-2025",
  contract_name: "Operator TTF supply 2025",
  counterparty: "Operator draft counterparty",
  contract_type: "EFET physical supply",
  delivery_point_name: "TTF",
  gas_year: "2025+",
  delivery_quantity_mwh_per_day: 0,
  contract_price_gbp_mwh: 0,
  nbp_sale_price_gbp_mwh: 0,
  physical_exit_sale_price_gbp_mwh: 0,
  physical_exit_point_name: "NBP",
  title_transfer_point: "TTF virtual trading point",
  beach_delivery_point: "Bacton Beach",
  index_basis: "TTF day-ahead index",
  terminal_access: "BBL / Bacton terminal access to confirm",
  capacity_expiry: "operator to enter",
  document_name: "manual draft",
  document_status: "MANUAL_DRAFT",
  source_reference: "operator manual entry",
  governing_law: "English law / EFET master confirmation to review",
  delivery_tolerance_pct: 2,
  nomination_tolerance_pct: 1,
  tolerance_risk_allowance_gbp_mwh: 0.1,
  variable_cost_gbp_mwh: 0,
  regas_fee_gbp_mwh: 0,
  fuel_loss_allowance_pct: 0,
  settlement_frequency: "monthly",
  upstream_payment_lag_days: 20,
  screen_sale_cash_lag_days: 1,
  annual_financing_rate_pct: 6,
  owned_entry_capacity_mwh_per_day: null,
  owned_exit_capacity_mwh_per_day: null,
  allowed_exit_points: ["NBP", "TTF"],
  eligible_sale_modes: ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE", "REROUTE_SALE"],
};

export function cloneDefaultContractDraft(): ContractDraft {
  return {
    ...defaultContractDraft,
    allowed_exit_points: [...defaultContractDraft.allowed_exit_points],
    eligible_sale_modes: [...defaultContractDraft.eligible_sale_modes],
  };
}
