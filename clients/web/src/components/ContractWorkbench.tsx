import { useMemo, useState } from "react";
import type { ChangeEvent, RefObject } from "react";
import type { PortfolioResourceDTO, UpstreamContractDTO, UpstreamContractInputDTO } from "@/api/client";

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
  | "settlement_frequency";

export type ContractListKey = "allowed_exit_points" | "eligible_sale_modes";

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

type Translate = (key: string) => string;
type TaskView = "source" | "terms" | "impact" | "library";
type ClauseView = "agreement" | "product" | "delivery" | "quantity" | "costs" | "capacity" | "settlement" | "restrictions";

interface ContractWorkbenchProps {
  contract: ContractDraft;
  contractPayload: UpstreamContractInputDTO;
  upstreamContracts: UpstreamContractDTO[];
  portfolioResources: PortfolioResourceDTO[];
  totalPoolVolume: number;
  firstPoolAllocation: { early_cash_value_gbp_mwh: number; net_margin_gbp_mwh: number; net_pnl_gbp_per_day: number } | null;
  runtimeDbReady: boolean;
  loading: boolean;
  contractImportRef: RefObject<HTMLInputElement | null>;
  contractImportMessage: string | null;
  contractSaveMessage: string | null;
  t: Translate;
  updateContractText: (key: ContractTextKey, value: string) => void;
  updateContractNumber: (key: ContractNumberKey, value: string) => void;
  updateContractList: (key: ContractListKey, value: string) => void;
  saveDraftContract: (contract: UpstreamContractInputDTO) => void;
  resetContractDraft: () => void;
  importContractDraftFile: (event: ChangeEvent<HTMLInputElement>) => void;
  loadPersistedContract: (saved: UpstreamContractDTO) => void;
}

function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${Math.round(value).toLocaleString()} MWh/d`;
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(2);
}

function formatPercentage(value: number | null | undefined): string {
  const formatted = formatMoney(value);
  return formatted === "n/a" ? formatted : `${formatted}%`;
}

function formatTimestamp(value: string | undefined): string {
  if (!value) return "n/a";
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString();
}

export function ContractWorkbench({
  contract, contractPayload, upstreamContracts, portfolioResources, totalPoolVolume,
  firstPoolAllocation, runtimeDbReady, loading, contractImportRef, contractImportMessage,
  contractSaveMessage, t, updateContractText, updateContractNumber, updateContractList,
  saveDraftContract, resetContractDraft, importContractDraftFile, loadPersistedContract,
}: ContractWorkbenchProps) {
  const [taskView, setTaskView] = useState<TaskView>("terms");
  const [clauseView, setClauseView] = useState<ClauseView>("agreement");
  const persistedTerm = upstreamContracts.find((item) => item.contract_id === contract.contract_id);
  const persistedResource = portfolioResources.find((item) => item.resource_id === contract.contract_id);
  const stagedStatus = contract.document_status || "MANUAL_DRAFT";

  const validationIssues = useMemo(() => {
    const issues: string[] = [];
    if (!contract.contract_id.trim()) issues.push(t("contracts.validation.contract_id"));
    if (!contract.contract_name.trim()) issues.push(t("contracts.validation.contract_name"));
    if (!contract.counterparty.trim()) issues.push(t("contracts.validation.counterparty"));
    if (!contract.delivery_point_name.trim()) issues.push(t("contracts.validation.delivery_point"));
    if (!contract.gas_year.trim()) issues.push(t("contracts.validation.gas_year"));
    if (contract.delivery_quantity_mwh_per_day <= 0) issues.push(t("contracts.validation.volume"));
    if (contract.contract_price_gbp_mwh < 0) issues.push(t("contracts.validation.price"));
    if (contract.variable_cost_gbp_mwh < 0 || contract.regas_fee_gbp_mwh < 0) issues.push(t("contracts.validation.costs"));
    if (contract.fuel_loss_allowance_pct < 0 || contract.fuel_loss_allowance_pct >= 100) issues.push(t("contracts.validation.fuel_loss"));
    return issues;
  }, [contract, t]);

  const canSave = runtimeDbReady && !loading && validationIssues.length === 0;
  const saveStatus = !runtimeDbReady
    ? t("home.blocker_runtime_db")
    : validationIssues.length > 0
      ? t("contracts.validation.blocked")
      : t("contracts.validation.ready");
  const taskTabs: Array<[TaskView, string]> = [
    ["source", t("contracts.view.source")], ["terms", t("contracts.view.terms")],
    ["impact", t("contracts.view.impact")], ["library", t("contracts.view.library")],
  ];
  const clauseTabs: Array<[ClauseView, string]> = [
    ["agreement", t("contracts.agreement")], ["product", t("contracts.product_term")],
    ["delivery", t("contracts.delivery")], ["quantity", t("contracts.quantity_tolerance")],
    ["costs", t("contracts.price_costs")], ["capacity", t("contracts.capacity_rights")],
    ["settlement", t("contracts.settlement_cash")], ["restrictions", t("contracts.restrictions")],
  ];

  function loadTerm(saved: UpstreamContractDTO) {
    loadPersistedContract(saved);
    setTaskView("terms");
    setClauseView("agreement");
  }

  return (
    <div className="contract-task-workspace">
      <section className="contract-command-strip" aria-label={t("contracts.command_strip")}>
        <div className="contract-command-identity">
          <span className="eyebrow">{persistedTerm ? t("contracts.persisted_term") : t("contracts.resource_draft")}</span>
          <strong>{contract.contract_name || t("contracts.unnamed_draft")}</strong>
          <span className={`contract-state ${persistedTerm ? "ready" : "draft"}`}>{persistedTerm ? t("contracts.persisted") : stagedStatus}</span>
        </div>
        <dl className="contract-command-facts">
          <div><dt>{t("contracts.counterparty")}</dt><dd>{contract.counterparty || "n/a"}</dd></div>
          <div><dt>{t("status.source")}</dt><dd>{contract.document_name || t("contracts.manual_entry")}</dd></div>
          <div><dt>{t("status.db")}</dt><dd>{runtimeDbReady ? t("data.runtime") : t("data.unavailable")}</dd></div>
          <div><dt>{t("panel.status")}</dt><dd>{t("settings.human_review")}</dd></div>
        </dl>
        <div className="contract-command-actions">
          <button type="button" className="secondary-button" onClick={() => contractImportRef.current?.click()}>{t("contracts.action.import")}</button>
          <button type="button" className="secondary-button" onClick={resetContractDraft}>{t("contracts.action.new")}</button>
          <button type="button" disabled={!canSave} title={saveStatus} onClick={() => canSave && saveDraftContract(contractPayload)}>{t("contracts.action.save")}</button>
          <input ref={contractImportRef} className="contract-import-input" type="file" accept=".json,.txt,application/json,text/plain" hidden onChange={importContractDraftFile} />
        </div>
      </section>

      <div className="contract-feedback" role="status" aria-live="polite"><strong>{saveStatus}</strong><span>{contractSaveMessage ?? contractImportMessage ?? t("contracts.save_hint")}</span></div>
      <nav className="contract-task-tabs" aria-label={t("contracts.workspace_views")}>
        {taskTabs.map(([key, label]) => <button key={key} type="button" className={taskView === key ? "active" : ""} onClick={() => setTaskView(key)}>{label}</button>)}
      </nav>

      {taskView === "source" && (
        <div className="contract-source-view">
          <section className="contract-content-band">
            <div className="section-heading"><span className="eyebrow">{t("contracts.source_intake")}</span><strong>{stagedStatus}</strong></div>
            <p className="panel-copy">{t("contracts.upload_hint")}</p>
            <button type="button" onClick={() => contractImportRef.current?.click()}>{t("contracts.upload_contract")}</button>
            <p className="contract-support-note">{t("contracts.supported_formats")}</p>
          </section>
          <section className="contract-content-band">
            <div className="section-heading"><span className="eyebrow">{t("contracts.source_evidence")}</span><strong>{t("settings.human_review")}</strong></div>
            <div className="contract-definition-list">
              <div><span>{t("contracts.document_status")}</span><strong>{stagedStatus}</strong></div>
              <div><span>{t("contracts.source_file")}</span><strong>{contract.document_name || t("contracts.manual_entry")}</strong></div>
              <div><span>{t("contracts.source_reference")}</span><strong>{contract.source_reference || t("contracts.no_source_reference")}</strong></div>
              <div><span>{t("contracts.review_state")}</span><strong>{t("settings.human_review")}</strong></div>
            </div>
          </section>
        </div>
      )}

      {taskView === "terms" && (
        <div className="contract-terms-layout">
          <nav className="contract-clause-nav" aria-label={t("contracts.clause_sections")}>
            {clauseTabs.map(([key, label], index) => <button key={key} type="button" className={clauseView === key ? "active" : ""} onClick={() => setClauseView(key)}><span>{String(index + 1).padStart(2, "0")}</span>{label}</button>)}
          </nav>
          <section className="contract-clause-editor">
            {clauseView === "agreement" && <fieldset><legend>{t("contracts.agreement")}</legend><p>{t("contracts.section_help.agreement")}</p><div className="contract-field-grid">
              <label>{t("contracts.contract_id")}<input value={contract.contract_id} onChange={(event) => updateContractText("contract_id", event.target.value)} /></label>
              <label>{t("contracts.contract_name")}<input value={contract.contract_name} onChange={(event) => updateContractText("contract_name", event.target.value)} /></label>
              <label>{t("contracts.counterparty")}<input value={contract.counterparty} onChange={(event) => updateContractText("counterparty", event.target.value)} /></label>
              <label>{t("contracts.resource_type")}<select value={contract.resource_type} onChange={(event) => updateContractText("resource_type", event.target.value)}><option value="PIPELINE_IMPORT">PIPELINE_IMPORT</option><option value="BEACH_DELIVERY">BEACH_DELIVERY</option><option value="LNG_REGAS">LNG_REGAS</option><option value="STORAGE">STORAGE</option><option value="CONTRACT_POOL">CONTRACT_POOL</option></select></label>
              <label className="span-2">{t("contracts.contract_type")}<input value={contract.contract_type} onChange={(event) => updateContractText("contract_type", event.target.value)} /></label>
            </div></fieldset>}
            {clauseView === "product" && <fieldset><legend>{t("contracts.product_term")}</legend><p>{t("contracts.section_help.product")}</p><div className="contract-field-grid">
              <label>{t("contracts.gas_year")}<input value={contract.gas_year} onChange={(event) => updateContractText("gas_year", event.target.value)} /></label>
              <label>{t("contracts.index_basis")}<input value={contract.index_basis} onChange={(event) => updateContractText("index_basis", event.target.value)} /></label>
            </div></fieldset>}
            {clauseView === "delivery" && <fieldset><legend>{t("contracts.delivery")}</legend><p>{t("contracts.section_help.delivery")}</p><div className="contract-field-grid">
              <label>{t("contracts.delivery_point")}<input value={contract.delivery_point_name} onChange={(event) => updateContractText("delivery_point_name", event.target.value)} /></label>
              <label>{t("contracts.title_transfer_point")}<input value={contract.title_transfer_point} onChange={(event) => updateContractText("title_transfer_point", event.target.value)} /></label>
              <label>{t("contracts.beach_delivery_point")}<input value={contract.beach_delivery_point} onChange={(event) => updateContractText("beach_delivery_point", event.target.value)} /></label>
              <label>{t("contracts.physical_exit_point")}<input value={contract.physical_exit_point_name} onChange={(event) => updateContractText("physical_exit_point_name", event.target.value)} /></label>
            </div></fieldset>}
            {clauseView === "quantity" && <fieldset><legend>{t("contracts.quantity_tolerance")}</legend><p>{t("contracts.section_help.quantity")}</p><div className="contract-field-grid">
              <label>{t("economics.volume")}<input type="number" min="0" value={contract.delivery_quantity_mwh_per_day} onChange={(event) => updateContractNumber("delivery_quantity_mwh_per_day", event.target.value)} /></label>
              <label>{t("economics.delivery_tolerance")}<input type="number" min="0" value={contract.delivery_tolerance_pct} onChange={(event) => updateContractNumber("delivery_tolerance_pct", event.target.value)} /></label>
              <label>{t("economics.nomination_tolerance")}<input type="number" min="0" value={contract.nomination_tolerance_pct} onChange={(event) => updateContractNumber("nomination_tolerance_pct", event.target.value)} /></label>
              <label>{t("contracts.fuel_loss")}<input type="number" min="0" max="99.99" value={contract.fuel_loss_allowance_pct} onChange={(event) => updateContractNumber("fuel_loss_allowance_pct", event.target.value)} /></label>
            </div><div className="contract-model-boundary">{t("contracts.minimum_take_not_modeled")}</div></fieldset>}
            {clauseView === "costs" && <fieldset><legend>{t("contracts.price_costs")}</legend><p>{t("contracts.section_help.costs")}</p><div className="contract-field-grid">
              <label>{t("economics.contract_price")}<input type="number" min="0" value={contract.contract_price_gbp_mwh} onChange={(event) => updateContractNumber("contract_price_gbp_mwh", event.target.value)} /></label>
              <label>{t("contracts.balancing_allowance")}<input type="number" min="0" value={contract.tolerance_risk_allowance_gbp_mwh} onChange={(event) => updateContractNumber("tolerance_risk_allowance_gbp_mwh", event.target.value)} /></label>
              <label>{t("contracts.variable_cost")}<input type="number" min="0" value={contract.variable_cost_gbp_mwh} onChange={(event) => updateContractNumber("variable_cost_gbp_mwh", event.target.value)} /></label>
              <label>{t("contracts.regas_fee")}<input type="number" min="0" value={contract.regas_fee_gbp_mwh} onChange={(event) => updateContractNumber("regas_fee_gbp_mwh", event.target.value)} /></label>
            </div></fieldset>}
            {clauseView === "capacity" && <fieldset><legend>{t("contracts.capacity_rights")}</legend><p>{t("contracts.section_help.capacity")}</p><div className="contract-field-grid">
              <label>{t("contracts.terminal_access")}<input value={contract.terminal_access} onChange={(event) => updateContractText("terminal_access", event.target.value)} /></label>
              <label>{t("contracts.capacity_expiry")}<input value={contract.capacity_expiry} onChange={(event) => updateContractText("capacity_expiry", event.target.value)} /></label>
              <label>{t("contracts.entry_capacity")}<input type="number" min="0" value={contract.owned_entry_capacity_mwh_per_day ?? ""} onChange={(event) => updateContractNumber("owned_entry_capacity_mwh_per_day", event.target.value)} /></label>
              <label>{t("contracts.exit_capacity")}<input type="number" min="0" value={contract.owned_exit_capacity_mwh_per_day ?? ""} onChange={(event) => updateContractNumber("owned_exit_capacity_mwh_per_day", event.target.value)} /></label>
            </div></fieldset>}
            {clauseView === "settlement" && <fieldset><legend>{t("contracts.settlement_cash")}</legend><p>{t("contracts.section_help.settlement")}</p><div className="contract-field-grid">
              <label>{t("contracts.settlement_frequency")}<select value={contract.settlement_frequency} onChange={(event) => updateContractText("settlement_frequency", event.target.value)}><option value="daily">daily</option><option value="weekly">weekly</option><option value="monthly">monthly</option></select></label>
              <label>{t("economics.cash_lag")}<input type="number" min="0" value={contract.screen_sale_cash_lag_days} onChange={(event) => updateContractNumber("screen_sale_cash_lag_days", event.target.value)} /></label>
              <label>{t("contracts.upstream_payment_lag")}<input type="number" min="0" value={contract.upstream_payment_lag_days} onChange={(event) => updateContractNumber("upstream_payment_lag_days", event.target.value)} /></label>
              <label>{t("economics.finance_rate")}<input type="number" min="0" value={contract.annual_financing_rate_pct} onChange={(event) => updateContractNumber("annual_financing_rate_pct", event.target.value)} /></label>
              <label className="span-2">{t("contracts.governing_law")}<input value={contract.governing_law} onChange={(event) => updateContractText("governing_law", event.target.value)} /></label>
            </div></fieldset>}
            {clauseView === "restrictions" && <fieldset><legend>{t("contracts.restrictions")}</legend><p>{t("contracts.section_help.restrictions")}</p><div className="contract-field-grid">
              <label className="span-2">{t("contracts.allowed_exit_points")}<input value={contract.allowed_exit_points.join(", ")} onChange={(event) => updateContractList("allowed_exit_points", event.target.value)} /></label>
              <label className="span-2">{t("contracts.eligible_sale_modes")}<input value={contract.eligible_sale_modes.join(", ")} onChange={(event) => updateContractList("eligible_sale_modes", event.target.value)} /></label>
            </div></fieldset>}
          </section>

          <aside className="contract-decision-rail" aria-label={t("contracts.validation.title")}>
            <section><div className="section-heading"><span className="eyebrow">{t("contracts.validation.title")}</span><strong className={validationIssues.length ? "warning-text" : "success-text"}>{validationIssues.length ? t("contracts.validation.not_ready") : t("contracts.validation.ready")}</strong></div>{validationIssues.length > 0 ? <ul>{validationIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : <p>{t("contracts.validation.complete")}</p>}</section>
            <section><span className="eyebrow">{t("contracts.source_evidence")}</span><div className="contract-definition-list compact"><div><span>{t("contracts.source_file")}</span><strong>{contract.document_name || t("contracts.manual_entry")}</strong></div><div><span>{t("contracts.source_reference")}</span><strong>{contract.source_reference || t("contracts.no_source_reference")}</strong></div></div></section>
            <section><span className="eyebrow">{t("contracts.persisted_impact")}</span><div className="contract-definition-list compact"><div><span>{t("contracts.pool_state")}</span><strong>{persistedResource ? t("contracts.in_pool") : t("contracts.not_in_pool")}</strong></div><div><span>{t("home.pool_volume")}</span><strong>{formatQuantity(totalPoolVolume)}</strong></div><div><span>{t("result.cash_value")}</span><strong>{firstPoolAllocation ? formatMoney(firstPoolAllocation.early_cash_value_gbp_mwh) : "n/a"}</strong></div></div></section>
          </aside>
        </div>
      )}

      {taskView === "impact" && (
        <div className="contract-impact-view">
          <section className="contract-content-band span-2">
            <div className="section-heading"><span className="eyebrow">{t("contracts.persisted_impact")}</span><strong>{persistedResource ? t("contracts.in_pool") : t("contracts.not_in_pool")}</strong></div>
              {persistedResource ? <div className="contract-impact-grid"><div><span>{t("contracts.resource_id")}</span><strong>{persistedResource.resource_id}</strong></div><div><span>{t("economics.volume")}</span><strong>{formatQuantity(persistedResource.available_quantity_mwh_per_day)}</strong></div><div><span>{t("economics.contract_price")}</span><strong>{formatMoney(persistedResource.contract_cost_gbp_mwh)}</strong></div><div><span>{t("contracts.variable_and_regas")}</span><strong>{formatMoney(persistedResource.variable_cost_gbp_mwh)}</strong></div><div><span>{t("contracts.fuel_loss")}</span><strong>{formatPercentage(persistedResource.fuel_loss_allowance_pct)}</strong></div><div><span>{t("contracts.pricing_method")}</span><strong>{persistedResource.pricing_method || "n/a"}</strong></div></div> : <p className="panel-copy">{t("contracts.impact_pending")}</p>}
            </section>
          <section className="contract-content-band"><div className="section-heading"><span className="eyebrow">{t("home.resource_pool")}</span><strong>{portfolioResources.length} {t(portfolioResources.length === 1 ? "contracts.resource_singular" : "home.resources")}</strong></div><div className="contract-definition-list"><div><span>{t("home.pool_volume")}</span><strong>{formatQuantity(totalPoolVolume)}</strong></div><div><span>{t("result.cash_value")}</span><strong>{firstPoolAllocation ? formatMoney(firstPoolAllocation.early_cash_value_gbp_mwh) : "n/a"}</strong></div><div><span>{t("result.net_margin")}</span><strong>{firstPoolAllocation ? formatMoney(firstPoolAllocation.net_margin_gbp_mwh) : "n/a"}</strong></div></div></section>
        </div>
      )}

      {taskView === "library" && (
        <section className="contract-library-view">
          <div className="panel-title-row"><h3>{t("contracts.library")}</h3><span>{upstreamContracts.length} {t("panel.records")}</span></div>
          <div className="contract-library-header" aria-hidden="true"><span>{t("contracts.resource_term")}</span><span>{t("economics.volume")}</span><span>{t("economics.contract_price")}</span><span>{t("panel.status")}</span></div>
          <div className="contract-library-list">{upstreamContracts.map((saved) => <button key={saved.contract_id} type="button" className={`contract-library-row ${saved.contract_id === contract.contract_id ? "selected" : ""}`} onClick={() => loadTerm(saved)}><span><strong>{saved.contract_name}</strong><small>{saved.contract_id} · {saved.delivery_point_name} · {saved.gas_year}</small></span><span><strong>{formatQuantity(saved.delivery_quantity_mwh_per_day)}</strong></span><span><strong>{formatMoney(saved.contract_price_gbp_mwh)}</strong><small>GBP/MWh</small></span><span><strong>{t("contracts.persisted")}</strong><small>{formatTimestamp(saved.updated_at_utc)}</small></span></button>)}{upstreamContracts.length === 0 && <p className="panel-copy">{t("contracts.no_saved_contracts")}</p>}</div>
        </section>
      )}
      <footer className="contract-boundary-note">{t("contracts.boundary_note")}</footer>
    </div>
  );
}
