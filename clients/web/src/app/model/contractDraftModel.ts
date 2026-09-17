/**
 * Contract draft model (Architecture V2 Wave 9, action-geography precondition).
 *
 * The contract workbench decides whether a reviewed draft may be saved. The action geography
 * (`app/experience/actionGeography.ts`) classes writing a reviewed draft as a `persist`
 * consequence, which belongs in a workspace's single primary action slot. A header can only
 * own that action honestly if the rule deciding it lives somewhere both the panel and the
 * header can read, so the rule lives here once instead of inside the panel that happens to
 * render the form.
 *
 * The functions are pure and return issue *keys* plus a status key, never translated text,
 * so the panel keeps owning presentation while the rule stays testable without a browser.
 */

/** The reviewed draft a user edits before it is persisted. */
export interface ContractDraft {
  contract_id: string;
  contract_name: string;
  resource_type: string;
  counterparty: string;
  contract_type: string;
  delivery_point_name: string;
  gas_year: string;
  delivery_quantity_mwh_per_day: number;
  contract_price_gbp_mwh: number;
  nbp_sale_price_gbp_mwh: number;
  physical_exit_sale_price_gbp_mwh: number;
  physical_exit_point_name: string;
  title_transfer_point: string;
  beach_delivery_point: string;
  index_basis: string;
  terminal_access: string;
  capacity_expiry: string;
  document_name: string;
  document_status: string;
  source_reference: string;
  governing_law: string;
  delivery_tolerance_pct: number;
  nomination_tolerance_pct: number;
  tolerance_risk_allowance_gbp_mwh: number;
  variable_cost_gbp_mwh: number;
  regas_fee_gbp_mwh: number;
  fuel_loss_allowance_pct: number;
  settlement_frequency: string;
  upstream_payment_lag_days: number;
  screen_sale_cash_lag_days: number;
  annual_financing_rate_pct: number;
  owned_entry_capacity_mwh_per_day: number | null;
  owned_exit_capacity_mwh_per_day: number | null;
  allowed_exit_points: string[];
  eligible_sale_modes: string[];
}

/**
 * Validation issue keys for a draft, in the order the workbench reports them.
 *
 * Keys, not messages: the same rule then serves the panel's issue list and any other surface
 * that needs to know whether the draft is complete, with no second chance for the two to
 * disagree about what a valid draft is.
 */
export function contractValidationIssueKeys(contract: ContractDraft): string[] {
  const issues: string[] = [];
  if (!contract.contract_id.trim()) issues.push("contracts.validation.contract_id");
  if (!contract.contract_name.trim()) issues.push("contracts.validation.contract_name");
  if (!contract.counterparty.trim()) issues.push("contracts.validation.counterparty");
  if (!contract.delivery_point_name.trim()) issues.push("contracts.validation.delivery_point");
  if (!contract.gas_year.trim()) issues.push("contracts.validation.gas_year");
  if (contract.delivery_quantity_mwh_per_day <= 0) issues.push("contracts.validation.volume");
  if (contract.contract_price_gbp_mwh < 0) issues.push("contracts.validation.price");
  if (contract.variable_cost_gbp_mwh < 0 || contract.regas_fee_gbp_mwh < 0) {
    issues.push("contracts.validation.costs");
  }
  if (contract.fuel_loss_allowance_pct < 0 || contract.fuel_loss_allowance_pct >= 100) {
    issues.push("contracts.validation.fuel_loss");
  }
  return issues;
}

/**
 * Which resource-contract sub-view the surface is showing, and what it is showing in it.
 *
 * This is one fact, so it has one owner: the workspace that hosts the action decides the
 * sub-view, and both the header's action and the panel's command strip read these booleans
 * from here rather than each deriving their own version of "the library is showing".
 */
export interface ContractViewFacts {
  /** The stored-contract library is showing instead of the terms editor. */
  readonly readOnlyLibrary: boolean;
  /** The library is open on one specific stored resource. */
  readonly readOnlySelectedResource: boolean;
  /** That selected resource is actually known to the client. */
  readonly knownSelectedResource: boolean;
}

/**
 * Resolve the view facts from the selected id and the collections the client already holds.
 *
 * "Known" means the selected id resolves to a portfolio resource or to a persisted contract
 * term - the same two lookups the command strip performs to name what it is showing - so a
 * resource that has been selected but not yet loaded reads as unknown rather than as an
 * empty contract.
 */
export function contractViewFacts(input: {
  readonly selectedResourceId: string | null;
  readonly readOnlyLibrary: boolean;
  readonly resourceIds: readonly string[];
  readonly contractIds: readonly string[];
}): ContractViewFacts {
  const selected = input.selectedResourceId;
  return {
    readOnlyLibrary: input.readOnlyLibrary,
    readOnlySelectedResource: input.readOnlyLibrary && Boolean(selected),
    knownSelectedResource: Boolean(
      selected && (input.resourceIds.includes(selected) || input.contractIds.includes(selected)),
    ),
  };
}

export interface ContractSaveState {
  /** Whether the draft may be written as it stands. */
  readonly canSave: boolean;
  /**
   * Translation key explaining the state. A draft can be complete and still not saveable -
   * a read in flight blocks the write - and the workbench reports readiness in that case,
   * so the key describes the rule that is blocking, not merely `canSave` inverted.
   */
  readonly statusKey: string;
}

/**
 * Whether a draft may be saved, and which rule decides the reported status.
 *
 * A read-only library view never saves: it shows the stored-contract library, and reports the
 * selected stored contract (or that it is unknown) rather than save readiness. A runtime that
 * is not ready cannot accept the write; an incomplete draft is refused with its issue list
 * rather than written half-way; a read in flight blocks the write but does not misreport the
 * draft as incomplete.
 */
export function contractSaveState(input: {
  readonly contract: ContractDraft;
  readonly runtimeDbReady: boolean;
  readonly loading: boolean;
  /** What the surface is showing, resolved once by `contractViewFacts`. */
  readonly viewFacts: ContractViewFacts;
}): ContractSaveState {
  const issues = contractValidationIssueKeys(input.contract);
  const { readOnlyLibrary, readOnlySelectedResource, knownSelectedResource } = input.viewFacts;
  const statusKey = readOnlyLibrary
    ? readOnlySelectedResource
      ? knownSelectedResource
        ? "contracts.persisted"
        : "status.unknown"
      : "contracts.library"
    : !input.runtimeDbReady
      ? "home.blocker_runtime_db"
      : issues.length > 0
        ? "contracts.validation.blocked"
        : "contracts.validation.ready";
  return {
    canSave: !readOnlyLibrary && input.runtimeDbReady && !input.loading && issues.length === 0,
    statusKey,
  };
}
