import type { UpstreamContractInputDTO } from "@/api/client";
import type { ContractDraft } from "./defaultContractDraft";
import {
  contractValidationIssueKeys,
  draftExpectedEditToken,
  isRecordedNumber,
} from "./model/contractDraftModel.ts";

/**
 * The numeric terms the governed write route requires as finite numbers
 * (`api/routes/public/route_cost.py::UpstreamContractUpsertRequest`).
 *
 * `tolerance_risk_allowance_gbp_mwh` and the owned capacities are deliberately absent: the
 * route types them `float | None`, so a draft that leaves them blank sends an explicit `null`
 * rather than an assumed zero. The three cost terms carried in the row's structured notes
 * (`variable_cost_gbp_mwh`, `regas_fee_gbp_mwh`, `fuel_loss_allowance_pct`) have a route
 * default of `0` and no null form, so an unrecorded value must not be sent at all.
 */
const REQUIRED_RECORDED_TERMS = [
  "delivery_quantity_mwh_per_day",
  "contract_price_gbp_mwh",
  "delivery_tolerance_pct",
  "nomination_tolerance_pct",
  "variable_cost_gbp_mwh",
  "regas_fee_gbp_mwh",
  "fuel_loss_allowance_pct",
  "upstream_payment_lag_days",
  "screen_sale_cash_lag_days",
  "annual_financing_rate_pct",
] as const;

type RequiredRecordedTerm = (typeof REQUIRED_RECORDED_TERMS)[number];

/**
 * A draft whose required numeric terms are all recorded finite numbers.
 *
 * This is the strict payload boundary: `buildContractPayload` accepts only this shape, and the
 * only producer of it is `contractPayloadReadiness`, which narrows with the same recorded-value
 * rule the validation issue list reports. An unknown required term therefore cannot reach the
 * composer at all.
 */
export type RecordedContractDraft = Omit<ContractDraft, RequiredRecordedTerm> & {
  readonly [Term in RequiredRecordedTerm]: number;
};

/**
 * Whether a draft may be transported, and the exact request when it may.
 *
 * `ready: false` carries a `null` payload and the draft's own validation issue keys, so a
 * caller never has to invent a second completeness rule: an unrecorded (or out-of-bounds)
 * required term is refused with the same reason the workbench shows.
 */
export interface ContractPayloadReadiness {
  readonly ready: boolean;
  readonly payload: UpstreamContractInputDTO | null;
  readonly issueKeys: readonly string[];
}

/**
 * The reviewed draft as a transportable request, or why it is not one.
 *
 * The validation rule decides policy (`contractValidationIssueKeys`), and the type guard below
 * narrows the draft for the composer. The guard can only accept what validation accepts - it
 * checks presence/finiteness, never a weaker bound - so `ready` and the save rule cannot
 * disagree in the direction that matters: a draft validation refuses is never ready.
 */
export function contractPayloadReadiness(contract: ContractDraft): ContractPayloadReadiness {
  const issueKeys = contractValidationIssueKeys(contract);
  if (issueKeys.length > 0 || !isRecordedContractDraft(contract)) {
    return { ready: false, payload: null, issueKeys };
  }
  return { ready: true, payload: buildContractPayload(contract), issueKeys: [] };
}

/**
 * Whether every required numeric term is a recorded finite number.
 *
 * This is the boundary's own presence check, not a second completeness opinion: validation
 * already requires each of these terms to be finite and in bounds, so this can only narrow a
 * draft validation has accepted.
 */
export function isRecordedContractDraft(contract: ContractDraft): contract is RecordedContractDraft {
  return REQUIRED_RECORDED_TERMS.every((term) => isRecordedNumber(contract[term]));
}

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
 *
 * Only a `RecordedContractDraft` is accepted: every numeric field the route requires as a
 * number is one here, so this composer has no `null` to coerce and no default to invent.
 */
export function buildContractPayload(contract: RecordedContractDraft): UpstreamContractInputDTO {
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
