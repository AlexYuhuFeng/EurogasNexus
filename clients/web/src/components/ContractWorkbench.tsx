import { DataGrid, PeriodPicker, RecordPicker, Sheet, WorkProgress, buttonClass } from "@/components/ui";
import { useCompactWidth } from "@/app/shell/useShellLayout";
import { formatDeliveryMonth } from "@/app/time/timeFormat";
import { idFromName } from "@/components/ui/recordPickerModel";
import { counterpartyOptions, gasYearOptions } from "@/app/model/recordOptions";
import { useCachedRead } from "@/app/data/readCache";
import { useApiStore } from "@/stores/api";
import { useStagedProgress } from "@/app/hooks/useWorkProgress";
import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, ReactNode, RefObject } from "react";
import { api, type ContractIntakeDTO, type PortfolioResourceDTO, type RouteCandidateDTO, type UpstreamContractDTO } from "@/api/client";
import { ContractPaymentTerms } from "@/components/ContractPaymentTerms";
import { ContractKindChooser, TypedContractForm } from "@/components/ContractKindForm";
import {
  STATUS_ORDER,
  TYPED_KINDS,
  contractStatus,
  kindHeadline,
  listedContracts,
  periodText,
  type AuthorableKind,
} from "@/app/model/contractKinds";
import type { TypedContractInputDTO } from "@/api/client";
import { RetireContractButton, RetiredContractsList, type ContractLifecycleAction } from "@/components/ContractLifecycleControls";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import {
  contractValidationIssueKeys,
  type ContractDraft,
  type ContractSaveState,
  type ContractViewFacts,
} from "@/app/model/contractDraftModel";
import { useInspectorStore } from "@/stores/inspector";
import {
  notesRecordFromRecord,
  stringFromRecord,
} from "@/app/contractImport";
import {
  GOVERNING_LAWS,
  SALE_MODES,
  hubCurrency,
  contractPriceCurrency,
  PRICE_CURRENCIES,
  hubOfPoint,
  indexOptions,
  hubLabelKey,
  pointOptions,
} from "@/app/contractChoices";

/** A select over closed options, keeping a recorded value that is not one of them. */
function ChoiceSelect({ value, options, onChange, blank, recordedLabel, labelFor }: {
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
  blank: string;
  recordedLabel: string;
  /** The label shown for an option; the stored value stays the option itself. */
  labelFor?: (option: string) => string;
}) {
  const known = options.includes(value);
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{blank}</option>
      {options.map((option) => <option key={option} value={option}>{labelFor ? labelFor(option) : option}</option>)}
      {value && !known && <option value={value}>{`${value} (${recordedLabel})`}</option>}
    </select>
  );
}

/** Checkboxes over closed options; a recorded value outside them stays ticked until cleared. */
function ChoiceChecks({ values, options, label, onChange }: {
  values: readonly string[];
  options: readonly { value: string; label: string }[];
  label: string;
  onChange: (values: string[]) => void;
}) {
  const all = [...options, ...values.filter((value) => !options.some((option) => option.value === value)).map((value) => ({ value, label: value }))];
  return (
    <fieldset className="choice-checks span-2">
      <legend>{label}</legend>
      {all.map((option) => (
        <label key={option.value} className="checkbox-row">
          <input
            type="checkbox"
            checked={values.includes(option.value)}
            onChange={() => onChange(values.includes(option.value) ? values.filter((value) => value !== option.value) : [...values, option.value])}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

const RESOURCE_TYPES = ["PIPELINE_IMPORT", "BEACH_DELIVERY", "LNG_REGAS", "STORAGE", "CONTRACT_POOL"] as const;

export type ContractNumberKey =
  | "delivery_quantity_mwh_per_day"
  | "contract_price_gbp_mwh"
  | "nbp_sale_price_gbp_mwh"
  | "physical_exit_sale_price_gbp_mwh"
  | "delivery_tolerance_pct"
  | "nomination_tolerance_pct"
  | "tolerance_risk_allowance_gbp_mwh"
  | "variable_cost_gbp_mwh"
  | "regas_fee_gbp_mwh"
  | "fuel_loss_allowance_pct"
  | "upstream_payment_lag_days"
  | "screen_sale_cash_lag_days"
  | "annual_financing_rate_pct"
  | "owned_entry_capacity_mwh_per_day"
  | "owned_exit_capacity_mwh_per_day";

export type ContractTextKey =
  | "contract_id"
  | "contract_name"
  | "resource_type"
  | "counterparty"
  | "contract_type"
  | "delivery_point_name"
  | "physical_exit_point_name"
  | "title_transfer_point"
  | "beach_delivery_point"
  | "index_basis"
  | "terminal_access"
  | "capacity_expiry"
  | "document_name"
  | "document_status"
  | "source_reference"
  | "governing_law"
  | "gas_year"
  | "settlement_frequency"
  | "contract_price_currency";

export type ContractListKey = "allowed_exit_points" | "eligible_sale_modes";

/**
 * Re-exported for existing callers. The draft shape is owned by
 * `app/model/contractDraftModel.ts` so that the save rule and the form cannot drift apart.
 */
export type { ContractDraft };

type Translate = (key: string, options?: Record<string, unknown>) => string;
/** The resource-contract sub-views. Owned by the workspace, which also hosts the save action. */
export type ContractTaskView = "source" | "terms" | "impact" | "library";
type ClauseView = "agreement" | "product" | "delivery" | "quantity" | "costs" | "capacity" | "settlement" | "restrictions";

/** Funding segments (#14): one row per lender, each priced at its own rate and day count. */
function FundingSegments({
  rows,
  currency,
  t,
  onChange,
}: {
  rows: ContractDraft["financing_tranches"];
  currency: string;
  t: (key: string, options?: Record<string, unknown>) => string;
  onChange: (rows: ContractDraft["financing_tranches"]) => void;
}) {
  const update = (index: number, patch: Partial<ContractDraft["financing_tranches"][number]>) =>
    onChange(rows.map((row, position) => (position === index ? { ...row, ...patch } : row)));
  const number = (value: string) => (value.trim() === "" || !Number.isFinite(Number(value)) ? null : Number(value));
  return (
    <div className="funding-segments">
      <h4>{t("contracts.tranches.title")}</h4>
      <p className="muted">{t("contracts.tranches.hint")} {t("contracts.tranches.currency_note", { currency })}</p>
      {rows.length === 0 ? (
        <p className="muted">{t("contracts.tranches.none")}</p>
      ) : (
        <div className="funding-segments-grid" role="table" aria-label={t("contracts.tranches.title")}>
          <div className="funding-segments-row is-head" role="row">
            <span role="columnheader">{t("contracts.tranches.lender")}</span>
            <span role="columnheader">{t("contracts.tranches.principal")}</span>
            <span role="columnheader">{t("contracts.tranches.rate")}</span>
            <span role="columnheader">{t("contracts.tranches.day_count")}</span>
            <span role="columnheader" aria-label={t("contracts.tranches.remove")} />
          </div>
          {rows.map((row, index) => (
            <div className="funding-segments-row" role="row" key={index}>
              <input role="cell" aria-label={t("contracts.tranches.lender")} value={row.lender} onChange={(event) => update(index, { lender: event.target.value })} />
              <input role="cell" aria-label={t("contracts.tranches.principal")} type="number" min="0" value={row.principal ?? ""} onChange={(event) => update(index, { principal: number(event.target.value) })} />
              <input role="cell" aria-label={t("contracts.tranches.rate")} type="number" min="0" step="0.01" value={row.annual_rate_pct ?? ""} onChange={(event) => update(index, { annual_rate_pct: number(event.target.value) })} />
              <select role="cell" aria-label={t("contracts.tranches.day_count")} value={row.day_count} onChange={(event) => update(index, { day_count: event.target.value === "ACT/360" ? "ACT/360" : "ACT/365F" })}>
                <option value="ACT/365F">ACT/365F</option>
                <option value="ACT/360">ACT/360</option>
              </select>
              <button role="cell" type="button" className="link-button" aria-label={`${t("contracts.tranches.remove")}: ${row.lender || index + 1}`} onClick={() => onChange(rows.filter((_, position) => position !== index))}>{t("contracts.tranches.remove_short")}</button>
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        className="secondary"
        onClick={() => onChange([...rows, { lender: "", principal: null, annual_rate_pct: null, day_count: "ACT/365F" }])}
      >
        {t("contracts.tranches.add")}
      </button>
    </div>
  );
}

interface ContractWorkbenchProps {
  contract: ContractDraft;
  /** Save to pool: the draft's own action, beside Import and New draft (UX_REFERENCE rule 26). */
  saveAction?: ReactNode;
  /** Save a typed contract (CONTRACT_TYPES.md); absent, the kinds' form is read-only. */
  saveTypedContract?: (body: TypedContractInputDTO) => Promise<UpstreamContractDTO | null>;
  /** Close the open contract (clears the page's selection). */
  onCloseDetail?: () => void;
  upstreamContracts: UpstreamContractDTO[];
  portfolioResources: PortfolioResourceDTO[];
  totalPoolVolume: number;
  firstPoolAllocation: { early_cash_value_gbp_mwh: number; net_margin_gbp_mwh: number; net_pnl_gbp_per_day: number } | null;
  runtimeDbReady: boolean;
  /** False while the data-store status read has not answered. */
  runtimeDbKnown?: boolean;
  loading: boolean;
  draftDirty: boolean;
  selectedResourceId: string | null;
  /**
   * Action geography (`app/experience/actionGeography.ts`): writing a reviewed draft is a
   * `persist` consequence, so the save action lives in the workspace's single primary slot
   * and this panel only reports it. The sub-view and the readiness facts therefore arrive as
   * props instead of being re-derived here, so the header's action and this report cannot
   * disagree about whether the draft may be written.
   */
  taskView: ContractTaskView;
  onTaskViewChange: (view: ContractTaskView) => void;
  viewFacts: ContractViewFacts;
  saveState: ContractSaveState;
  contractImportRef: RefObject<HTMLInputElement | null>;
  contractImportMessage: string | null;
  contractImportBusy?: boolean;
  /** Terms a PDF intake read, each with its page and words, until the reviewer dismisses it. */
  contractIntake?: ContractIntakeDTO | null;
  onDismissContractIntake?: () => void;
  /** Retire or reinstate a stored contract (absent: the library is read-only). */
  onContractLifecycle?: ContractLifecycleAction;
  contractSaveMessage: string | null;
  /** The last save was refused as a stale-edit conflict (`stores/api.ts`). */
  contractSaveConflict: boolean;
  t: Translate;
  updateContractText: (key: ContractTextKey, value: string) => void;
  updateContractNumber: (key: ContractNumberKey, value: string) => void;
  updateContractList: (key: ContractListKey, value: string) => void;
  /** Replace the draft's funding segments (#14). */
  updateContractTranches?: (rows: ContractDraft["financing_tranches"]) => void;
  /** Route network the delivery and exit points are chosen from. */
  routeCandidates?: readonly RouteCandidateDTO[];
  resetContractDraft: () => void;
  importContractDraftFile: (event: ChangeEvent<HTMLInputElement>) => void;
  loadPersistedContract: (saved: UpstreamContractDTO) => void;
}

function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return `${Math.round(value).toLocaleString()} MWh/d`;
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}


export function ContractWorkbench({
  contract, upstreamContracts, portfolioResources, totalPoolVolume,
  firstPoolAllocation, runtimeDbReady, runtimeDbKnown = true, loading, draftDirty, selectedResourceId,
  taskView, onTaskViewChange, viewFacts, saveState,
  contractImportRef, contractImportMessage, contractImportBusy = false,
  contractIntake = null, onDismissContractIntake, onContractLifecycle,
  contractSaveMessage, contractSaveConflict, t,
  updateContractText, updateContractNumber, updateContractList, updateContractTranches, routeCandidates = [],
  resetContractDraft, importContractDraftFile, loadPersistedContract, saveAction, saveTypedContract, onCloseDetail,
}: ContractWorkbenchProps) {
  // Wave 9: object detail goes to the canonical Inspector instead of growing a third
  // detail pane inside this workbench. The selection stays local; only the detail moves.
  const inspector = useInspectorStore();
  const [clauseView, setClauseView] = useState<ClauseView>("agreement");
  const persistedTerm = upstreamContracts.find((item) => item.contract_id === contract.contract_id);
  const selectedPersistedTerm = selectedResourceId
    ? upstreamContracts.find((item) => item.contract_id === selectedResourceId) ?? null
    : null;
  const persistedResource = portfolioResources.find((item) => item.resource_id === contract.contract_id);
  // Desk words for where the draft came from; an unknown code is shown as recorded.
  const points = useMemo(() => pointOptions(routeCandidates), [routeCandidates]);
  const pointLabel = (point: string) => {
    const key = hubLabelKey(point);
    return key ? t(key) : point;
  };
  const deliveryHub = hubOfPoint(contract.delivery_point_name);
  const creditRead = useCachedRead("/portfolio/credit-exposure", () => api.creditExposure());
  const lngTerminals = useApiStore((state) => state.lng);
  // Counterparties the firm holds a credit line for, by name (a contract records the name).
  const counterpartyChoices = useMemo(
    () => counterpartyOptions(creditRead.data?.data.rows ?? []).map((item) => ({ ...item, id: item.label })),
    [creditRead.data],
  );
  const terminalChoices = useMemo(
    () => [...new Map(lngTerminals.map((row) => [row.terminal_name, { id: row.terminal_name, label: row.terminal_name, detail: row.country }])).values()],
    [lngTerminals],
  );
  const gasYears = useMemo(() => gasYearOptions(), []);
  const priceCurrency = contractPriceCurrency(contract.contract_price_currency, contract.delivery_point_name);

  const validationIssues = useMemo(
    () => contractValidationIssueKeys(contract).map((key) => t(key)),
    [contract, t],
  );

  const clauseTabs: Array<[ClauseView, string]> = [
    ["agreement", t("contracts.agreement")], ["product", t("contracts.product_term")],
    ["delivery", t("contracts.delivery")], ["quantity", t("contracts.quantity_tolerance")],
    ["costs", t("contracts.price_costs")], ["capacity", t("contracts.capacity_rights")],
    ["settlement", t("contracts.settlement_cash")], ["restrictions", t("contracts.restrictions")],
  ];

  // Contract kinds, type first (CONTRACT_TYPES.md): a new contract starts from the kind; a
  // stored typed one opens in its kind's form; a supply agreement keeps the editor below.
  const [kindChoice, setKindChoice] = useState<AuthorableKind | null>(null);
  const [typedEditing, setTypedEditing] = useState<UpstreamContractDTO | null>(null);
  const persistedKind = persistedTerm?.contract_kind ?? "SUPPLY_GSA";
  const typedStored = typedEditing ?? (persistedTerm && TYPED_KINDS.has(persistedKind) ? persistedTerm : null);
  const termsMode: "typed" | "legacy" | "choose" = typedStored || (kindChoice && TYPED_KINDS.has(kindChoice) && !persistedTerm)
    ? "typed"
    : persistedTerm || draftDirty || kindChoice === "SUPPLY_GSA"
      ? "legacy"
      : kindChoice
        ? "typed"
        : "choose";
  const typedKind = (typedStored?.contract_kind ?? kindChoice ?? "SUPPLY_GSA") as AuthorableKind;
  const proposedKind = typeof contractIntake?.record?.contract_kind === "string" ? contractIntake.record.contract_kind : null;
  useEffect(() => {
    // A PDF intake proposes the kind; the reviewer sees that kind's form with the terms read.
    if (!contractIntake) return;
    setTypedEditing(null);
    setKindChoice(proposedKind && TYPED_KINDS.has(proposedKind) ? (proposedKind as AuthorableKind) : "SUPPLY_GSA");
  }, [contractIntake, proposedKind]);
  function inspect(saved: UpstreamContractDTO) {
    const subject = inspectorSubjectFor(
      "contract",
      saved.contract_id,
      saved.contract_name,
      "contracts",
    );
    if (subject) inspector.open(subject);
  }

  function closeDetail() {
    if (draftDirty && taskView === "terms" && !window.confirm(t("contracts.edit_confirm"))) return;
    setKindChoice(null);
    setTypedEditing(null);
    onCloseDetail?.();
    onTaskViewChange("library");
  }

  function startNewDraft() {
    setKindChoice(null);
    setTypedEditing(null);
    resetContractDraft();
    onTaskViewChange("terms");
  }

  function loadTerm(saved: UpstreamContractDTO) {
    if (draftDirty && !window.confirm(t("contracts.edit_confirm"))) return;
    const savedKind = saved.contract_kind ?? "SUPPLY_GSA";
    setTypedEditing(TYPED_KINDS.has(savedKind) ? saved : null);
    setKindChoice(savedKind as AuthorableKind);
    loadPersistedContract(saved);
    onTaskViewChange("terms");
    setClauseView("agreement");
  }

  const intakeBlock = contractIntake ? (

        <section className="contract-intake" aria-labelledby="contract-intake-title">
          <div className="section-heading">
            <strong id="contract-intake-title">
              {t("contracts.intake_title", {
                name: contractIntake.file_name,
                terms: contractIntake.terms.filter((term) => !term.field.startsWith("_")).length,
                pages: contractIntake.pages,
              })}
            </strong>
            {onDismissContractIntake && (
              <button type="button" className="link-button" onClick={onDismissContractIntake}>{t("contracts.intake_dismiss")}</button>
            )}
          </div>
          {contractIntake.warnings.length > 0 && (
            <ul className="contract-intake-warnings">
              {contractIntake.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          )}
          <DataGrid
            id="contract-intake"
            label={t("contracts.intake_field")}
            rows={contractIntake.terms}
            rowKey={(term) => term.field}
            density="compact"
            rowAttributes={(term) => ({ "data-applied": term.field.startsWith("_") ? "false" : "true" })}
            columns={[
              { id: "field", header: t("contracts.intake_field"), rowHeader: true, value: (term) => t(`contracts.intake_term.${term.field.replace(/^_/, "")}`) },
              {
                id: "value",
                header: t("contracts.intake_value"),
                value: (term) => String(term.value),
                render: (term) => (
                  <>
                    <strong>{String(term.value)}</strong> {term.unit && <small>{term.unit}</small>}
                    {term.note && <small className="muted"> {term.note}</small>}
                  </>
                ),
              },
              { id: "page", header: t("contracts.intake_page"), type: "number", value: (term) => term.page ?? null },
              { id: "evidence", header: t("contracts.intake_evidence"), value: (term) => term.evidence ?? null, render: (term) => <q>{term.evidence}</q> },
            ]}
          />
        </section>
  ) : null;

  // The page is the contract list (owner, 2026-11-19): the firm's contracts the caller may see,
  // in execution first, with search and a kind filter; a row opens the contract beside the list
  // (a sheet on a phone); New and Import are the list's own actions.
  const today = new Date().toISOString().slice(0, 10);
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const compact = useCompactWidth();
  const counterpartyOf = (row: UpstreamContractDTO) =>
    stringFromRecord({ ...notesRecordFromRecord(row as unknown as Record<string, unknown>) }, "counterparty", "");
  const rows = useMemo(
    () => listedContracts(upstreamContracts, { query, kind: kindFilter, today, counterpartyOf }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [upstreamContracts, query, kindFilter, today],
  );
  const kindsHeld = useMemo(() => [...new Set(upstreamContracts.map((row) => row.contract_kind ?? "SUPPLY_GSA"))], [upstreamContracts]);
  const shown = selectedPersistedTerm ?? (taskView === "terms" ? persistedTerm ?? null : null);
  const detailMode: "none" | "view" | "edit" | "new" = taskView === "terms"
    ? (persistedTerm || typedEditing ? "edit" : "new")
    : shown ? "view" : "none";
  const monthName = (iso: string) => formatDeliveryMonth(iso.slice(0, 7));
  // Say what happened to a save or an import; opening or starting a contract needs no notice.
  const importNotice = contractImportBusy || contractIntake || (contractImportMessage ?? "").startsWith(t("contracts.import_failed"));
  const feedback = contractSaveMessage ?? (importNotice ? contractImportMessage : null);

  function openContract(saved: UpstreamContractDTO) {
    if (draftDirty && !window.confirm(t("contracts.edit_confirm"))) return;
    const savedKind = saved.contract_kind ?? "SUPPLY_GSA";
    setTypedEditing(null);
    setKindChoice(savedKind as AuthorableKind);
    loadPersistedContract(saved);
    onTaskViewChange("library");
  }

  const legacyEditor = (
        <div className="contract-terms-layout">
          <nav className="contract-clause-nav" aria-label={t("contracts.clause_sections")} tabIndex={0}>
            {clauseTabs.map(([key, label], index) => <button key={key} type="button" className={clauseView === key ? "active" : ""} onClick={() => setClauseView(key)}><span>{String(index + 1).padStart(2, "0")}</span>{label}</button>)}
          </nav>
          <section className="contract-clause-editor">
            {clauseView === "agreement" && <fieldset><legend>{t("contracts.agreement")}</legend><p>{t("contracts.section_help.agreement")}</p><div className="contract-field-grid">
              {/* The live principle (UX_REFERENCE rule 25): a new contract's reference is made from
                  its name, never typed; a saved one's never changes. */}
              <label>{t("contracts.contract_name")}<input value={contract.contract_name} onChange={(event) => {
                updateContractText("contract_name", event.target.value);
                if (!persistedTerm) updateContractText("contract_id", idFromName(event.target.value, upstreamContracts.map((item) => item.contract_id)));
              }} /></label>
              <RecordPicker
                id="contract-counterparty"
                label={t("contracts.counterparty")}
                options={counterpartyChoices}
                value={contract.counterparty || null}
                recentKey="contract-counterparty"
                allowManual
                onChange={(choice) => updateContractText("counterparty", choice ? (counterpartyChoices.find((item) => item.id === choice.id)?.label ?? choice.id) : "")}
              />
              <label>{t("contracts.resource_type")}<select value={contract.resource_type} onChange={(event) => updateContractText("resource_type", event.target.value)}>{RESOURCE_TYPES.map((value) => <option key={value} value={value}>{t(`contracts.resource_type.${value}`)}</option>)}</select></label>
              <label className="span-2">{t("contracts.contract_type")}<input value={contract.contract_type} onChange={(event) => updateContractText("contract_type", event.target.value)} /></label>
            </div></fieldset>}
            {clauseView === "product" && <fieldset><legend>{t("contracts.product_term")}</legend><p>{t("contracts.section_help.product")}</p><div className="contract-field-grid">
              <label>{t("contracts.gas_year")}<ChoiceSelect value={contract.gas_year} options={gasYears} blank={t("contracts.choose")} recordedLabel={t("contracts.as_recorded")} onChange={(value) => updateContractText("gas_year", value)} /></label>
              <label>{t("contracts.index_basis")}<ChoiceSelect value={contract.index_basis} options={indexOptions(deliveryHub)} blank={t("contracts.choose")} recordedLabel={t("contracts.as_recorded")} labelFor={pointLabel} onChange={(value) => updateContractText("index_basis", value)} /></label>
            </div></fieldset>}
            {clauseView === "delivery" && <fieldset><legend>{t("contracts.delivery")}</legend><p>{t("contracts.section_help.delivery")}</p><div className="contract-field-grid">
              <label>{t("contracts.delivery_point")}<ChoiceSelect value={contract.delivery_point_name} options={points} blank={t("contracts.choose")} recordedLabel={t("contracts.as_recorded")} labelFor={pointLabel} onChange={(value) => updateContractText("delivery_point_name", value)} /></label>
              <label>{t("contracts.title_transfer_point")}<ChoiceSelect value={contract.title_transfer_point} options={points} blank={t("contracts.choose")} recordedLabel={t("contracts.as_recorded")} labelFor={pointLabel} onChange={(value) => updateContractText("title_transfer_point", value)} /></label>
              <label>{t("contracts.beach_delivery_point")}<ChoiceSelect value={contract.beach_delivery_point} options={points} blank={t("contracts.choose")} recordedLabel={t("contracts.as_recorded")} labelFor={pointLabel} onChange={(value) => updateContractText("beach_delivery_point", value)} /></label>
              <label>{t("contracts.physical_exit_point")}<ChoiceSelect value={contract.physical_exit_point_name} options={points} blank={t("contracts.choose")} recordedLabel={t("contracts.as_recorded")} labelFor={pointLabel} onChange={(value) => updateContractText("physical_exit_point_name", value)} /></label>
            </div>
              {contract.delivery_point_name && !deliveryHub && <div className="contract-model-boundary">{t("contracts.point_not_hub")}</div>}
            </fieldset>}
            {clauseView === "quantity" && <fieldset><legend>{t("contracts.quantity_tolerance")}</legend><p>{t("contracts.section_help.quantity")}</p><div className="contract-field-grid">
              <label>{t("economics.volume")}<input type="number" min="0" value={contract.delivery_quantity_mwh_per_day ?? ""} onChange={(event) => updateContractNumber("delivery_quantity_mwh_per_day", event.target.value)} /></label>
              <label>{t("economics.delivery_tolerance")}<input type="number" min="0" value={contract.delivery_tolerance_pct ?? ""} onChange={(event) => updateContractNumber("delivery_tolerance_pct", event.target.value)} /></label>
              <label>{t("economics.nomination_tolerance")}<input type="number" min="0" value={contract.nomination_tolerance_pct ?? ""} onChange={(event) => updateContractNumber("nomination_tolerance_pct", event.target.value)} /></label>
              <label>{t("contracts.fuel_loss")}<input type="number" min="0" max="99.99" value={contract.fuel_loss_allowance_pct ?? ""} onChange={(event) => updateContractNumber("fuel_loss_allowance_pct", event.target.value)} /></label>
            </div><div className="contract-model-boundary">{t("contracts.minimum_take_not_modeled")}</div></fieldset>}
            {clauseView === "costs" && <fieldset><legend>{t("contracts.price_costs")}</legend><p>{t("contracts.section_help.costs")}</p><div className="contract-field-grid">
              <label>{t("contracts.price_per_mwh", { currency: priceCurrency })}<input type="number" min="0" value={contract.contract_price_gbp_mwh ?? ""} onChange={(event) => updateContractNumber("contract_price_gbp_mwh", event.target.value)} /></label>
              <label>{t("contracts.price_currency")}<select value={priceCurrency} onChange={(event) => updateContractText("contract_price_currency", event.target.value)}>{PRICE_CURRENCIES.map((code) => <option key={code} value={code}>{code}</option>)}</select></label>
              <label>{t("contracts.balancing_allowance")}<input type="number" min="0" value={contract.tolerance_risk_allowance_gbp_mwh ?? ""} onChange={(event) => updateContractNumber("tolerance_risk_allowance_gbp_mwh", event.target.value)} /></label>
              <label>{t("contracts.variable_cost")}<input type="number" min="0" value={contract.variable_cost_gbp_mwh ?? ""} onChange={(event) => updateContractNumber("variable_cost_gbp_mwh", event.target.value)} /></label>
              <label>{t("contracts.regas_fee")}<input type="number" min="0" value={contract.regas_fee_gbp_mwh ?? ""} onChange={(event) => updateContractNumber("regas_fee_gbp_mwh", event.target.value)} /></label>
            </div>{deliveryHub && hubCurrency(deliveryHub) !== priceCurrency && <div className="contract-model-boundary">{t("contracts.currency_translated", { currency: priceCurrency, hub: deliveryHub, hubCurrency: hubCurrency(deliveryHub) })}</div>}</fieldset>}
            {clauseView === "capacity" && <fieldset><legend>{t("contracts.capacity_rights")}</legend><p>{t("contracts.section_help.capacity")}</p><div className="contract-field-grid">
              <RecordPicker
                id="contract-terminal"
                label={t("contracts.terminal_access")}
                options={terminalChoices}
                value={contract.terminal_access || null}
                allowManual
                emptyText={t("contracts.no_terminals")}
                onChange={(choice) => updateContractText("terminal_access", choice?.id ?? "")}
              />
              <label>{t("contracts.capacity_expiry")}{/^\d{4}-\d{2}-\d{2}$/.test(contract.capacity_expiry) || !contract.capacity_expiry ? <PeriodPicker label={t("contracts.capacity_expiry")} value={contract.capacity_expiry} clearable onChange={(value) => updateContractText("capacity_expiry", value)} /> : <input value={contract.capacity_expiry} onChange={(event) => updateContractText("capacity_expiry", event.target.value)} />}</label>
              <label>{t("contracts.entry_capacity")}<input type="number" min="0" value={contract.owned_entry_capacity_mwh_per_day ?? ""} onChange={(event) => updateContractNumber("owned_entry_capacity_mwh_per_day", event.target.value)} /></label>
              <label>{t("contracts.exit_capacity")}<input type="number" min="0" value={contract.owned_exit_capacity_mwh_per_day ?? ""} onChange={(event) => updateContractNumber("owned_exit_capacity_mwh_per_day", event.target.value)} /></label>
            </div></fieldset>}
            {clauseView === "settlement" && <fieldset><legend>{t("contracts.settlement_cash")}</legend><p>{t("contracts.section_help.settlement")}</p><div className="contract-field-grid">
              <label>{t("contracts.settlement_frequency")}<select value={contract.settlement_frequency} onChange={(event) => updateContractText("settlement_frequency", event.target.value)}><option value="daily">daily</option><option value="weekly">weekly</option><option value="monthly">monthly</option></select></label>
              <label>{t("economics.cash_lag")}<input type="number" min="0" value={contract.screen_sale_cash_lag_days ?? ""} onChange={(event) => updateContractNumber("screen_sale_cash_lag_days", event.target.value)} /></label>
              <label>{t("contracts.upstream_payment_lag")}<input type="number" min="0" value={contract.upstream_payment_lag_days ?? ""} onChange={(event) => updateContractNumber("upstream_payment_lag_days", event.target.value)} /></label>
              <label>{t("economics.finance_rate")}<input type="number" min="0" value={contract.annual_financing_rate_pct ?? ""} onChange={(event) => updateContractNumber("annual_financing_rate_pct", event.target.value)} /></label>
              <label className="span-2">{t("contracts.governing_law")}<ChoiceSelect value={contract.governing_law} options={GOVERNING_LAWS} blank={t("contracts.choose")} recordedLabel={t("contracts.as_recorded")} labelFor={pointLabel} onChange={(value) => updateContractText("governing_law", value)} /></label>
            </div>
            {updateContractTranches && (
              <FundingSegments
                rows={contract.financing_tranches ?? []}
                currency={priceCurrency}
                t={t}
                onChange={updateContractTranches}
              />
            )}
            <ContractPaymentTerms read={contract.persisted_payment_terms} t={t} /></fieldset>}
            {clauseView === "restrictions" && <fieldset><legend>{t("contracts.restrictions")}</legend><p>{t("contracts.section_help.restrictions")}</p><div className="contract-field-grid">
              <ChoiceChecks label={t("contracts.allowed_exit_points_pick")} values={contract.allowed_exit_points} options={points.map((point) => ({ value: point, label: pointLabel(point) }))} onChange={(values) => updateContractList("allowed_exit_points", values.join(", "))} />
              <ChoiceChecks label={t("contracts.eligible_sale_modes_pick")} values={contract.eligible_sale_modes} options={SALE_MODES.map((mode) => ({ value: mode, label: t(`contracts.sale_mode.${mode}`) }))} onChange={(values) => updateContractList("eligible_sale_modes", values.join(", "))} />
            </div></fieldset>}
          </section>

          <aside className="contract-decision-rail" aria-label={t("contracts.validation.title")}>
            {/* What is still needed shows once the person has started; never on an untouched draft. */}
            {draftDirty && <section><div className="section-heading"><span className="eyebrow">{t("contracts.validation.title")}</span><strong className={validationIssues.length ? "warning-text" : "success-text"}>{validationIssues.length ? t("contracts.validation.not_ready") : t("contracts.validation.ready")}</strong></div>{validationIssues.length > 0 ? <ul>{validationIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : <p>{t("contracts.validation.complete")}</p>}</section>}
            <section><span className="eyebrow">{t("contracts.source_evidence")}</span><div className="contract-definition-list compact"><div><span>{t("contracts.source_file")}</span><strong>{contract.document_name || t("contracts.manual_entry")}</strong></div><div><span>{t("contracts.source_reference")}</span><strong>{contract.source_reference || t("contracts.no_source_reference")}</strong></div></div></section>
            <section><span className="eyebrow">{t("contracts.persisted_impact")}</span><div className="contract-definition-list compact"><div><span>{t("contracts.pool_state")}</span><strong>{persistedResource ? t("contracts.in_pool") : t("contracts.not_in_pool")}</strong></div><div><span>{t("portfolio.scope.quantity")}</span><strong>{formatQuantity(totalPoolVolume)}</strong></div><div><span>{t("result.cash_value")}</span><strong>{firstPoolAllocation ? formatMoney(firstPoolAllocation.early_cash_value_gbp_mwh) : "n/a"}</strong></div></div></section>
          </aside>
        </div>
  );

  const detail = detailMode === "none" ? null : (
    <div className="contract-detail-body" data-contract-detail={detailMode}>
      {detailMode === "view" && shown && (
        <ContractReadView
          contract={shown}
          t={t}
          monthName={monthName}
          counterparty={counterpartyOf(shown)}
          confirmations={upstreamContracts.filter((item) => item.master_contract_id === shown.contract_id)}
          onEdit={() => loadTerm(shown)}
          onInspect={() => inspect(shown)}
          retire={onContractLifecycle ? <RetireContractButton contract={shown} onLifecycle={onContractLifecycle} t={t} /> : null}
        />
      )}
      {detailMode !== "view" && contractIntake && intakeBlock}
      {detailMode !== "view" && termsMode === "choose" && <ContractKindChooser t={t} onChoose={setKindChoice} />}
      {detailMode !== "view" && termsMode === "typed" && (
        <TypedContractForm
          kind={typedKind}
          editing={typedStored}
          upstreamContracts={upstreamContracts}
          routeCandidates={routeCandidates}
          intake={contractIntake}
          save={async (body) => (saveTypedContract ? saveTypedContract(body as unknown as TypedContractInputDTO) : null)}
          onSaved={(saved) => setTypedEditing(saved)}
          onChangeKind={() => setKindChoice(null)}
          t={t}
        />
      )}
      {detailMode !== "view" && termsMode === "legacy" && (
        <>
          <div className="contract-detail-actions">{saveAction}</div>
          {legacyEditor}
        </>
      )}
    </div>
  );
  const detailTitle = detailMode === "new"
    ? t("contracts.list.new_title")
    : (typedEditing?.contract_name ?? shown?.contract_name ?? contract.contract_name) || t("contracts.list.new_title");

  return (
    <div className="contract-task-workspace contract-list-page">
      <section className="contract-list-command" aria-label={t("contracts.command_strip")}>
        <strong className="contract-list-count" data-contract-count={upstreamContracts.length}>
          {t("contracts.list.count", { count: upstreamContracts.length })}
        </strong>
        <input
          type="search"
          className="contract-list-search"
          aria-label={t("contracts.list.search")}
          placeholder={t("contracts.list.search")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select aria-label={t("contracts.list.kind_filter")} value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}>
          <option value="">{t("contracts.list.all_kinds")}</option>
          {kindsHeld.map((kind) => <option key={kind} value={kind}>{t(`contracts.kind.${kind}`)}</option>)}
        </select>
        <div className="contract-command-actions" tabIndex={0}>
          <button type="button" className={buttonClass("primary", "md")} data-page-action="contract-new" onClick={startNewDraft}>{t("contracts.action.new")}</button>
          <button type="button" className="secondary-button" onClick={() => contractImportRef.current?.click()}>{t("contracts.action.import")}</button>
          <input ref={contractImportRef} className="contract-import-input" type="file" accept=".pdf,application/pdf" hidden onChange={importContractDraftFile} />
        </div>
      </section>

      {contractImportBusy && <ContractImportProgress t={t} />}
      {feedback && (
        <div className="contract-feedback" role="status" aria-live="polite"><span>{feedback}</span></div>
      )}
      {contractSaveConflict && (
        <div className="runtime-blocker-list compact" role="alert">
          <strong>{t("contracts.edit_conflict_title")}</strong>
          <span>{t("contracts.edit_conflict_detail")}</span>
        </div>
      )}

      <div className={`contract-list-layout${detail && !compact ? " has-detail" : ""}`}>
        <section className="contract-list" aria-label={t("contracts.list.title")}>
          <DataGrid
            id="contract-list"
            label={t("contracts.list.title")}
            rows={rows}
            rowKey={(row) => row.contract_id}
            density="compact"
            selectedKey={shown?.contract_id ?? null}
            onRowAction={openContract}
            // The row carries the stored contract's own id, so the acceptance sweep compares it
            // with the upstream-terms read by exact id (`scripts/uat/readToRender.mjs`).
            rowAttributes={(row) => ({ "data-record": "upstream-contract", "data-record-id": row.contract_id, "data-contract-kind": row.contract_kind ?? "SUPPLY_GSA", "data-master": row.master_contract_id ?? undefined })}
            rowClassName={(row) => (row.master_contract_id && rows.some((item) => item.contract_id === row.master_contract_id) ? "contract-row-confirmation" : undefined)}
            empty={<span data-empty-state="contract-library">{t(upstreamContracts.length ? "contracts.list.none_match" : "contracts.no_saved_contracts")}</span>}
            columns={[
              { id: "name", header: t("contracts.list.name"), rowHeader: true, priority: "primary", value: (row) => row.contract_name, render: (row) => (
                row.master_contract_id && rows.some((item) => item.contract_id === row.master_contract_id)
                  ? <span className="contract-confirmation-name" title={t("contracts.list.under_master")}><span aria-hidden="true">↳ </span>{row.contract_name}</span>
                  : row.contract_name
              ) },
              { id: "kind", header: t("contracts.list.kind"), priority: "secondary", value: (row) => t(`contracts.kind.${row.contract_kind ?? "SUPPLY_GSA"}`), render: (row) => (
                <span className="contract-kind-badge" data-kind-reviewed={row.contract_kind_reviewed === false ? "false" : "true"} title={row.contract_kind_reviewed === false ? t("contracts.kind.inferred") : undefined}>{t(`contracts.kind.${row.contract_kind ?? "SUPPLY_GSA"}`)}</span>
              ) },
              { id: "figure", header: t("contracts.list.figure"), priority: "primary", value: (row) => kindFigure(row, upstreamContracts, t), cellTitle: (row) => t(`contracts.figure.${figureKey(row, upstreamContracts)}`) },
              { id: "status", header: t("contracts.list.status"), priority: "primary", value: (row) => STATUS_ORDER.indexOf(contractStatus(row, today)), render: (row) => (
                <span className="contract-status" data-contract-status={contractStatus(row, today)}>{t(`contracts.status.${contractStatus(row, today)}`)}</span>
              ) },
              { id: "counterparty", header: t("contracts.counterparty"), priority: "secondary", value: (row) => counterpartyOf(row) || t("contracts.list.not_recorded"), cellClassName: (row) => (counterpartyOf(row) ? undefined : "muted") },
              { id: "delivery", header: t("contracts.list.delivery"), priority: "secondary", value: (row) => deliveryText(row, t) },
              { id: "period", header: t("contracts.list.period"), priority: "secondary", value: (row) => contractPeriodText(row, monthName) },
            ]}
          />
          {onContractLifecycle && <RetiredContractsList onLifecycle={onContractLifecycle} refreshKey={upstreamContracts.length} t={t} />}
        </section>
        {detail && !compact && (
          <section className="contract-detail" aria-label={detailTitle}>
            <div className="contract-detail-head">
              <strong>{detailTitle}</strong>
              <button type="button" className="link-button" onClick={closeDetail}>{t("contracts.list.close")}</button>
            </div>
            {detail}
          </section>
        )}
      </div>
      {detail && compact && (
        <Sheet open onClose={closeDetail} title={detailTitle} closeLabel={t("contracts.list.close")} side="bottom">
          {detail}
        </Sheet>
      )}
    </div>
  );
}

/** A contract import at work: reading the file, finding the terms, filling the draft. */
function ContractImportProgress({ t }: { t: (key: string) => string }) {
  const stages = ["contracts.import_stage.read", "contracts.import_stage.terms", "contracts.import_stage.fill"];
  const progress = useStagedProgress(true, stages.length, 2000);
  return <WorkProgress label={t("contracts.import_stage.read")} stages={stages.map((stage) => t(stage))} current={progress.stage} />;
}

/** A typed contract's price as signed, in its native unit (never converted). */
function priceLine(terms: Record<string, unknown>, t: Translate): string {
  // The desk writes pence per therm as p/th.
  const unit = String(terms.price_unit ?? "").replace("GBp/th", "p/th");
  const number = (value: unknown) => (typeof value === "number" ? value : Number(value));
  if (terms.price_type === "fixed" || terms.price_formula === "fixed") return `${number(terms.fixed_price).toFixed(2)} ${unit}`;
  if (terms.price_type === "index") {
    const diff = number(terms.differential ?? 0);
    return `${String(terms.index)} ${diff < 0 ? "−" : "+"} ${Math.abs(diff).toFixed(2)} ${unit}`;
  }
  if (terms.price_formula === "hub") {
    const constant = number(terms.constant ?? 0);
    return `${String(terms.hub_index)} ${constant < 0 ? "−" : "+"} ${Math.abs(constant).toFixed(2)} ${unit}`;
  }
  const driver = terms.price_formula === "brent" ? "Brent" : "HH";
  return t("contracts.kind.slope_price", { slope: number(terms.slope).toFixed(2), driver, constant: number(terms.constant).toFixed(2), unit });
}

/** Where a contract delivers, as the desk says it: the point or terminal; a master's terms. */
function deliveryText(row: UpstreamContractDTO, t: Translate): string {
  const terms = row.kind_terms ?? {};
  if (row.contract_kind === "LNG_MSPA") return Array.isArray(terms.delivery_terms) ? terms.delivery_terms.join(", ") : "–";
  if (row.contract_kind === "LNG_CARGO") {
    const term = String(terms.delivery_term ?? "");
    return term === "DES" ? `DES ${String(terms.discharge_terminal ?? "")} → ${String(terms.terminal_hub ?? "")}` : `FOB ${String(terms.load_port ?? "")}`;
  }
  return row.delivery_point_name || t("contracts.no_source_reference");
}

/** The one figure that matters for the kind, in the contract's own units. */
function kindFigure(row: UpstreamContractDTO, all: readonly UpstreamContractDTO[], t: Translate): string {
  const head = kindHeadline(row, all, (id) => all.find((item) => item.contract_id === id)?.master_contract_id ?? null);
  return head.key === "master" ? t("contracts.kind.confirmations", { count: Number(head.text) }) : head.text;
}

/** A stored contract, read first: its terms in words, then Edit, Inspect and Retire. */
function ContractReadView({ contract, counterparty, confirmations, monthName, onEdit, onInspect, retire, t }: {
  contract: UpstreamContractDTO;
  counterparty: string;
  confirmations: readonly UpstreamContractDTO[];
  monthName: (iso: string) => string;
  onEdit: () => void;
  onInspect: () => void;
  retire: ReactNode;
  t: Translate;
}) {
  const kind = contract.contract_kind ?? "SUPPLY_GSA";
  const terms = contract.kind_terms ?? null;
  const facts: Array<[string, string]> = [
    [t("contracts.list.kind"), t(`contracts.kind.${kind}`)],
    [t("contracts.counterparty"), counterparty || t("contracts.list.not_recorded_edit")],
    [t("contracts.list.delivery"), deliveryText(contract, t)],
    [t("contracts.list.period"), contractPeriodText(contract, monthName)],
    [t("contracts.list.figure"), kindFigure(contract, [contract, ...confirmations], t)],
  ];
  if (terms && typeof terms.price_unit === "string") facts.push([t("contracts.contract_price"), priceLine(terms, t)]);
  else if (kind === "SUPPLY_GSA") facts.push([t("contracts.contract_price"), `${formatMoney(contract.contract_price_gbp_mwh)} ${contract.contract_price_currency ?? "GBP"}/MWh`]);
  if (kind === "UPSTREAM_TENDER" && terms) facts.push([t("contracts.kind_field.nomination"), t(`contracts.kind_option.${String(terms.nomination)}`)]);
  if (kind === "LNG_MSPA" && terms) {
    facts.push([t("contracts.kind_field.our_side"), t(`contracts.kind_option.${String(terms.our_side)}`)]);
    if (terms.demurrage_usd_per_day) facts.push([t("contracts.kind_field.demurrage_usd_per_day"), `${Number(terms.demurrage_usd_per_day).toLocaleString("en-GB")} USD/d`]);
    facts.push([t("contracts.kind_field.credit_support"), t(`contracts.kind_option.${String(terms.credit_support)}`)]);
  }
  return (
    <div className="contract-read" data-contract-read={contract.contract_id}>
      {contract.contract_kind_reviewed === false && <p className="muted">{t("contracts.kind.inferred")}</p>}
      <dl className="contract-definition-list">
        {facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
      {contract.unmodelled_terms && (
        <section>
          <span className="eyebrow">{t("contracts.kind_field.unmodelled_terms")}</span>
          <p className="contract-unmodelled">{contract.unmodelled_terms}</p>
        </section>
      )}
      {confirmations.length > 0 && (
        <section>
          <span className="eyebrow">{t("contracts.kind.confirmations", { count: confirmations.length })}</span>
          <ul className="contract-confirmations">
            {confirmations.map((item) => <li key={item.contract_id}>{item.contract_name} · {kindFigure(item, [], t)}</li>)}
          </ul>
        </section>
      )}
      <div className="contract-detail-actions">
        <button type="button" className={buttonClass("primary", "md")} data-page-action="contract-edit" onClick={onEdit}>{t("contracts.edit")}</button>
        <button type="button" className="secondary-button" onClick={onInspect}>{t("contracts.inspect")}</button>
        {retire}
      </div>
    </div>
  );
}

/** The period as signed: a cargo's delivery window by day, a master's term, else the gas year. */
function contractPeriodText(row: UpstreamContractDTO, monthName: (iso: string) => string): string {
  const terms = row.kind_terms ?? {};
  const window = row.headline?.window;
  if (row.contract_kind === "LNG_CARGO" && window) {
    return `${Number(window[0].slice(8))}–${Number(window[1].slice(8))} ${monthName(window[1])}`;
  }
  if (row.contract_kind === "LNG_MSPA" && typeof terms.term_start === "string") {
    return typeof terms.term_end === "string" ? `${monthName(terms.term_start)} – ${monthName(terms.term_end)}` : `${monthName(terms.term_start)} →`;
  }
  return periodText(row.gas_year, monthName);
}

function figureKey(row: UpstreamContractDTO, all: readonly UpstreamContractDTO[]): string {
  return kindHeadline(row, all, (id) => all.find((item) => item.contract_id === id)?.master_contract_id ?? null).key;
}
