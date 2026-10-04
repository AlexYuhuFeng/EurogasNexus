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

import { apiErrorDetailCode } from "../experience/errorPresentation.ts";
import type { PaymentTermsReadState } from "./contractPaymentTerms.ts";

/**
 * The stored identity and opaque edit token a draft was loaded from.
 *
 * The token belongs to one stored contract row, so the identity travels with it: a draft
 * whose contract id changed is create-only and must never send the old row's token.
 */
export interface StoredContractEdit {
  readonly contract_id: string;
  readonly edit_token: string;
}

/**
 * The reviewed draft a user edits before it is persisted.
 *
 * Every numeric term is `number | null`, and the two states are different facts:
 *
 * * a `number` is a *recorded* value. An explicit `0` is a recorded zero and stays `0`;
 * * `null` is *unknown*: nothing recorded in the stored row, or a control the operator has
 *   cleared. An unknown required term is shown blank, blocks the save through
 *   `contractValidationIssueKeys`, and is never composed into a request - the governed write
 *   route's defaults would otherwise record a `0` nobody entered (`contractPayload.ts`).
 *
 * `owned_entry_capacity_mwh_per_day`, `owned_exit_capacity_mwh_per_day` and
 * `tolerance_risk_allowance_gbp_mwh` additionally keep their documented `null` meaning for an
 * *optional* route field: "not declared". The write route types each of them `float | None`,
 * so a blank control is representable as recorded absence rather than an assumed zero.
 */
export interface ContractDraft {
  contract_id: string;
  contract_name: string;
  resource_type: string;
  counterparty: string;
  contract_type: string;
  delivery_point_name: string;
  gas_year: string;
  delivery_quantity_mwh_per_day: number | null;
  contract_price_gbp_mwh: number | null;
  nbp_sale_price_gbp_mwh: number | null;
  physical_exit_sale_price_gbp_mwh: number | null;
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
  delivery_tolerance_pct: number | null;
  nomination_tolerance_pct: number | null;
  tolerance_risk_allowance_gbp_mwh: number | null;
  variable_cost_gbp_mwh: number | null;
  regas_fee_gbp_mwh: number | null;
  fuel_loss_allowance_pct: number | null;
  settlement_frequency: string;
  upstream_payment_lag_days: number | null;
  screen_sale_cash_lag_days: number | null;
  annual_financing_rate_pct: number | null;
  owned_entry_capacity_mwh_per_day: number | null;
  owned_exit_capacity_mwh_per_day: number | null;
  allowed_exit_points: string[];
  eligible_sale_modes: string[];
  /**
   * The persisted row's own `notes` JSON object, kept only so a save can put back the
   * fields this editor does not own (unknown provenance/terms, `operator_notes` prose).
   *
   * The editor neither renders nor edits it. `buildContractPayload` starts from a copy of
   * it and overlays only the fields this surface owns, so stored evidence survives the next
   * save instead of being replaced by the editor's own capture envelope. It is assigned on
   * every stored load and cleared by a new draft or a file import - replaced, never
   * accumulated - so a save cannot carry a previously loaded contract's notes into another
   * record.
   */
  preserved_notes: Record<string, unknown> | null;
  /**
   * The stored row's own identity plus the opaque edit token this draft was loaded from,
   * or `null` for a new draft, a file import or a changed/unknown identity.
   *
   * A save sends it as `expected_edit_token`, so the governed write refuses a draft whose
   * row changed after it was read instead of overwriting it. New draft, import, reset and
   * contract-id edit all clear it: a token never binds a different identity.
   */
  stored_edit: StoredContractEdit | null;
  /**
   * The declared payment terms read with the stored record this draft was loaded from.
   *
   * `null` means this draft is not a stored load (a new draft, a file import, a typed
   * contract-id change, an unsaved draft whose identity session ended): no persisted
   * declaration is shown, and one record's terms can never ride into another draft. A stored
   * load carries the decoded read state -
   * `declared`, `not_declared`, `unavailable` or `malformed` - so "nothing was read" and
   * "nothing is recorded" stay different facts
   * (`app/model/contractPaymentTerms.ts`). The read is presentation only: the save builder
   * omits `payment_terms` entirely (omission preserves the stored declaration) and no editing,
   * clearing, date resolution or cash math happens in the client.
   */
  persisted_payment_terms: PaymentTermsReadState | null;
}

/**
 * The draft after the authenticated identity session changed (sign-out or another principal).
 *
 * The persisted declaration is commercial evidence read for one identity session, so it does
 * not survive sign-out even though the rest of the editor draft is not identity-scoped. Only
 * this carrier is cleared: the bounded change keeps the presented declaration from outliving
 * the session that read it without altering the draft's existing save semantics.
 */
export function contractDraftAfterIdentityChange(contract: ContractDraft): ContractDraft {
  if (contract.persisted_payment_terms === null) return contract;
  return { ...contract, persisted_payment_terms: null };
}

/**
 * Validation issue keys for a draft, in the order the workbench reports them.
 *
 * Keys, not messages: the same rule then serves the panel's issue list and any other surface
 * that needs to know whether the draft is complete, with no second chance for the two to
 * disagree about what a valid draft is.
 *
 * The numeric bounds are the existing governed write route's own request bounds
 * (`api/routes/public/route_cost.py::UpstreamContractUpsertRequest`), not a new financial
 * convention: `delivery_quantity` above 0, prices/costs/tolerances/rates at 0 or above, fuel
 * loss in [0, 100), whole-day lags, and the route's nullable fields (`tolerance_risk_allowance`,
 * owned capacities) allowed to stay blank. A term that is not a recorded finite number is
 * reported exactly like a term outside its bound: it blocks the save instead of being sent.
 */
export function contractValidationIssueKeys(contract: ContractDraft): string[] {
  const issues: string[] = [];
  if (!contract.contract_id.trim()) issues.push("contracts.validation.contract_id");
  if (!contract.contract_name.trim()) issues.push("contracts.validation.contract_name");
  if (!contract.counterparty.trim()) issues.push("contracts.validation.counterparty");
  if (!contract.delivery_point_name.trim()) issues.push("contracts.validation.delivery_point");
  if (!contract.gas_year.trim()) issues.push("contracts.validation.gas_year");
  if (
    !isRecordedNumber(contract.delivery_quantity_mwh_per_day) ||
    contract.delivery_quantity_mwh_per_day <= 0
  ) {
    issues.push("contracts.validation.volume");
  }
  if (!isNonNegativeTerm(contract.contract_price_gbp_mwh)) {
    issues.push("contracts.validation.price");
  }
  if (
    !isNonNegativeTerm(contract.variable_cost_gbp_mwh) ||
    !isNonNegativeTerm(contract.regas_fee_gbp_mwh) ||
    !isBlankOrNonNegativeTerm(contract.tolerance_risk_allowance_gbp_mwh)
  ) {
    issues.push("contracts.validation.costs");
  }
  if (
    !isRecordedNumber(contract.fuel_loss_allowance_pct) ||
    contract.fuel_loss_allowance_pct < 0 ||
    contract.fuel_loss_allowance_pct >= 100
  ) {
    issues.push("contracts.validation.fuel_loss");
  }
  if (
    !isNonNegativeTerm(contract.delivery_tolerance_pct) ||
    !isNonNegativeTerm(contract.nomination_tolerance_pct)
  ) {
    issues.push("contracts.validation.tolerance");
  }
  if (
    !isWholeDayCount(contract.upstream_payment_lag_days) ||
    !isWholeDayCount(contract.screen_sale_cash_lag_days)
  ) {
    issues.push("contracts.validation.cash_lag");
  }
  if (!isNonNegativeTerm(contract.annual_financing_rate_pct)) {
    issues.push("contracts.validation.financing_rate");
  }
  if (
    !isBlankOrNonNegativeTerm(contract.owned_entry_capacity_mwh_per_day) ||
    !isBlankOrNonNegativeTerm(contract.owned_exit_capacity_mwh_per_day)
  ) {
    issues.push("contracts.validation.capacity");
  }
  return issues;
}

/**
 * Whether a draft term is a recorded finite number.
 *
 * `null` is the draft's explicit unknown state; `NaN` and `±Infinity` are not representable
 * values for the write route's float fields. Both count as "not recorded", so a cleared
 * control or a poisoned value blocks the save rather than being coerced to `0`.
 */
export function isRecordedNumber(value: number | null): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** A required route field: recorded and at 0 or above. */
function isNonNegativeTerm(value: number | null): boolean {
  return isRecordedNumber(value) && value >= 0;
}

/** An optional route field (`float | None`): blank is allowed, a recorded value is at 0 or above. */
function isBlankOrNonNegativeTerm(value: number | null): boolean {
  return value === null || isNonNegativeTerm(value);
}

/** A whole-day count, as the write route's `int >= 0` fields require. */
function isWholeDayCount(value: number | null): boolean {
  return isRecordedNumber(value) && Number.isInteger(value) && value >= 0;
}

/**
 * The number a cleared or invalid numeric control holds.
 *
 * An empty control is unknown (`null`), never `0`; a non-finite entry (`1e999`, `NaN`) is not
 * a recordable value either. A `0` the operator actually typed stays `0`, so an explicit zero
 * is reported as itself by validation and saved as itself.
 */
export function draftNumberFromInput(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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

/**
 * The edit token a save must send for this draft, or null for a create-only save.
 *
 * The token belongs to the identity it was read from: a draft whose contract id no longer
 * equals the stored identity (the user typed another id, or a load/import replaced the
 * draft) is create-only, so a stale token can never bind it to a different stored row.
 */
export function draftExpectedEditToken(contract: ContractDraft): string | null {
  const identity = contract.contract_id.trim();
  const stored = contract.stored_edit;
  if (!stored || stored.contract_id !== identity) return null;
  const token = stored.edit_token.trim();
  return token || null;
}

/** How one contract save resolved against the stored row. */
export interface ContractSaveApplication {
  /** The draft after the saved response is folded in; editor fields are never overwritten. */
  readonly contract: ContractDraft;
  /**
   * True only when the response belongs to the submitted draft session and no editor act
   * happened after the submitted generation.
   */
  readonly clearDirty: boolean;
}

/**
 * Fold one successful save response into the current draft.
 *
 * The response is applied only to the *draft session* that submitted it. A session is replaced
 * by a stored load, a reset, a file import or a contract-id edit - acts that rebind what the
 * draft is about - while a field edit only advances the generation within the same session.
 * So a same-ID reload, a reset/import, or an id typed away and back (A -> B -> A) is a
 * different session even when `contract_id` reads the same again: that response belongs to a
 * draft that no longer exists, is not folded in, and cannot clear dirty.
 *
 * Within the same session only the lease (stored identity + opaque token) and the preserved
 * notes base are taken from the response: the editor-owned fields stay exactly as the user has
 * them, so edits made while the request was in flight are never destroyed and adopt the
 * refreshed token. `clearDirty` is true only when the generation is still the submitted one;
 * an edit during the request leaves the draft dirty because that edit is not what was saved.
 */
export function applyContractSaveResult(input: {
  readonly current: ContractDraft;
  readonly savedContractId: string;
  readonly savedEditToken: string | null;
  readonly savedPreservedNotes: Record<string, unknown> | null;
  readonly submittedContractId: string;
  /** The draft session that submitted the save (`currentSession` must still be it). */
  readonly submittedSession: number;
  readonly currentSession: number;
  readonly submittedGeneration: number;
  readonly currentGeneration: number;
}): ContractSaveApplication {
  if (
    input.current.contract_id.trim() !== input.submittedContractId ||
    input.savedContractId !== input.submittedContractId ||
    input.currentSession !== input.submittedSession
  ) {
    return { contract: input.current, clearDirty: false };
  }
  const token =
    typeof input.savedEditToken === "string" && input.savedEditToken.trim()
      ? input.savedEditToken.trim()
      : null;
  return {
    contract: {
      ...input.current,
      stored_edit: token ? { contract_id: input.savedContractId, edit_token: token } : null,
      preserved_notes: input.savedPreservedNotes,
    },
    clearDirty: input.currentGeneration === input.submittedGeneration,
  };
}

/** The save-failure kinds a surface must present differently. */
export type ContractSaveFailureKind = "contract_edit_conflict" | "other";

/**
 * Classify a failed contract save from the backend's stable codes.
 *
 * The governed write answers 409 `contract_edit_conflict` (the stored row changed or the
 * request conflicts with the stored identity) and `contract_edit_token_malformed` (the
 * supplied lease is not a token this API issues). Both mean: the draft was kept and must be
 * reconciled against a fresh read - never silently retried against the same stale token.
 */
export function contractSaveFailureKind(cause: unknown): ContractSaveFailureKind {
  const code = apiErrorDetailCode(cause);
  return code === "contract_edit_conflict" || code === "contract_edit_token_malformed"
    ? "contract_edit_conflict"
    : "other";
}
