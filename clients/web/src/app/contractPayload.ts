import type { ContractDraft } from "./defaultContractDraft";
import { draftExpectedEditToken } from "./model/contractDraftModel.ts";

/**
 * The reviewed draft as the governed write path receives it.
 *
 * The top-level fields are the current editor values, unchanged. `notes` is where the
 * stored row's own JSON object lives: this builder copies `contract.preserved_notes` and
 * overlays only the keys the editor owns (the term fields below plus its two capture
 * posture flags), so unrelated provenance and terms recorded on the row survive the save
 * instead of being replaced by this builder's own envelope. The copy is never mutated.
 *
 * The stored `source` is evidence, not an editor field: it is preserved verbatim and this
 * writer does not stamp its own origin over it. Only a draft with no preserved base - a new
 * draft, an imported file draft, or a stored row whose notes carry no JSON object - gets the
 * explicit `web_contract_capture` envelope. No edit marker is added either: the governed
 * write path already attributes the write itself (`recorded_by`, `capture_origin` on the
 * captured revision), and the editor's own metadata (document name/status/source reference)
 * travels in the fields it owns.
 *
 * `expected_edit_token` is the opaque token read with this draft's stored identity, or
 * `null` (new draft, import, changed id) - create-only on the backend, never an overwrite.
 * It is not the captured revision number and is never derived from editor fields.
 */
export function buildContractPayload(contract: ContractDraft) {
  const preserved = contract.preserved_notes;
  const notes: Record<string, unknown> = {
    ...preserved,
    ...(preserved ? {} : { source: "web_contract_capture" }),
    decision_support_only: true,
    human_review_required: true,
    counterparty: contract.counterparty,
    contract_type: contract.contract_type,
    title_transfer_point: contract.title_transfer_point,
    beach_delivery_point: contract.beach_delivery_point,
    index_basis: contract.index_basis,
    terminal_access: contract.terminal_access,
    capacity_expiry: contract.capacity_expiry,
    document_name: contract.document_name,
    document_status: contract.document_status,
    source_reference: contract.source_reference,
    governing_law: contract.governing_law,
    physical_exit_point_name: contract.physical_exit_point_name,
    variable_cost_gbp_mwh: contract.variable_cost_gbp_mwh,
    regas_fee_gbp_mwh: contract.regas_fee_gbp_mwh,
    fuel_loss_allowance_pct: contract.fuel_loss_allowance_pct,
  };
  return {
    contract_id: contract.contract_id.trim(),
    contract_name: contract.contract_name.trim(),
    resource_type: contract.resource_type,
    delivery_point_name: contract.delivery_point_name.trim(),
    gas_year: contract.gas_year.trim(),
    delivery_quantity_mwh_per_day: contract.delivery_quantity_mwh_per_day,
    contract_price_gbp_mwh: contract.contract_price_gbp_mwh,
    settlement_frequency: contract.settlement_frequency,
    upstream_payment_lag_days: contract.upstream_payment_lag_days,
    screen_sale_cash_lag_days: contract.screen_sale_cash_lag_days,
    delivery_tolerance_pct: contract.delivery_tolerance_pct,
    nomination_tolerance_pct: contract.nomination_tolerance_pct,
    tolerance_risk_allowance_gbp_mwh: contract.tolerance_risk_allowance_gbp_mwh,
    annual_financing_rate_pct: contract.annual_financing_rate_pct,
    owned_entry_capacity_mwh_per_day: contract.owned_entry_capacity_mwh_per_day,
    owned_exit_capacity_mwh_per_day: contract.owned_exit_capacity_mwh_per_day,
    allowed_exit_points: contract.allowed_exit_points,
    eligible_sale_modes: contract.eligible_sale_modes,
    variable_cost_gbp_mwh: contract.variable_cost_gbp_mwh,
    regas_fee_gbp_mwh: contract.regas_fee_gbp_mwh,
    fuel_loss_allowance_pct: contract.fuel_loss_allowance_pct,
    notes: JSON.stringify(notes),
    expected_edit_token: draftExpectedEditToken(contract),
  };
}
