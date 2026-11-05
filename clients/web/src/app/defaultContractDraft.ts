import type { ContractDraft as ContractDraftModel } from "./model/contractDraftModel";

export type ContractDraft = ContractDraftModel;

/**
 * The operator-entry template for a new manual draft.
 *
 * Facts only the contract can state (identity, counterparty, points, capacity, law) start
 * blank so nothing invented can be saved as a recorded term: the save stays blocked until
 * the trader types them. Only conventions every desk starts from are pre-filled (EFET form,
 * TTF delivery, the current gas year, tolerances, monthly settlement).
 *
 * These are explicit pre-filled entry defaults for a *new* draft, not recorded contract facts:
 * stored hydration never inherits them, and a file import keeps them only for terms the file
 * genuinely omits (the import overlay; see `contractImport.ts`). The numeric terms are validated
 * against the governed write route before a save.
 */
export const defaultContractDraft: ContractDraft = {
  contract_id: "",
  contract_name: "",
  resource_type: "PIPELINE_IMPORT",
  counterparty: "",
  contract_type: "EFET physical supply",
  delivery_point_name: "",
  gas_year: currentGasYear(new Date()),
  delivery_quantity_mwh_per_day: 0,
  contract_price_gbp_mwh: 0,
  contract_price_currency: "",
  financing_tranches: [],
  nbp_sale_price_gbp_mwh: 0,
  physical_exit_sale_price_gbp_mwh: 0,
  physical_exit_point_name: "",
  title_transfer_point: "",
  beach_delivery_point: "",
  index_basis: "",
  terminal_access: "",
  capacity_expiry: "",
  document_name: "manual draft",
  document_status: "MANUAL_DRAFT",
  source_reference: "operator manual entry",
  governing_law: "",
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
  // A new draft has no stored notes to preserve, so a save writes the explicit
  // `web_contract_capture` envelope; see `contractPayload.ts`.
  preserved_notes: null,
  // A new draft has no stored identity or edit token: its first save is create-only.
  // See `contractDraftModel.ts::draftExpectedEditToken`.
  stored_edit: null,
  // A new draft was not read from a stored record, so it carries no persisted declared
  // payment terms to present; see `contractDraftModel.ts::ContractDraft`.
  persisted_payment_terms: null,
};

/** The gas year (1 October to 30 September) containing `now`, as "2026+". */
export function currentGasYear(now: Date): string {
  const year = now.getUTCMonth() >= 9 ? now.getUTCFullYear() : now.getUTCFullYear() - 1;
  return `${year}+`;
}

export function cloneDefaultContractDraft(): ContractDraft {
  return {
    ...defaultContractDraft,
    gas_year: currentGasYear(new Date()),
    allowed_exit_points: [...defaultContractDraft.allowed_exit_points],
    eligible_sale_modes: [...defaultContractDraft.eligible_sale_modes],
  };
}
