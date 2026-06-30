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
  | "annual_financing_rate_pct";

export type ContractTextKey =
  | "contract_id"
  | "contract_name"
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

export interface ContractDraft {
  contract_id: string;
  contract_name: string;
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

function evidenceValue(value: string | null | undefined, fallback: string): string {
  return value && value.trim() ? value.trim() : fallback;
}

export function ContractWorkbench({
  contract,
  contractPayload,
  upstreamContracts,
  portfolioResources,
  totalPoolVolume,
  firstPoolAllocation,
  runtimeDbReady,
  loading,
  contractImportRef,
  contractImportMessage,
  contractSaveMessage,
  t,
  updateContractText,
  updateContractNumber,
  saveDraftContract,
  resetContractDraft,
  importContractDraftFile,
  loadPersistedContract,
}: ContractWorkbenchProps) {
  const stagedStatus = contract.document_status || "MANUAL_DRAFT";
  const sourceEvidence = [
    evidenceValue(contract.document_name, t("contracts.manual_entry")),
    evidenceValue(contract.source_reference, t("contracts.no_source_reference")),
    stagedStatus,
  ];
  const warningStack = [
    t("settings.decision_support_only"),
    t("settings.human_review"),
    runtimeDbReady ? null : t("home.blocker_runtime_db"),
    contract.document_status === "STAGED_REVIEW_REQUIRED" ? t("contracts.review_uploaded_text") : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <div className="workspace-grid contracts-page contract-intake-workbench">
      <section className="workspace-panel span-2 contract-upload-zone">
        <div className="section-heading">
          <span className="eyebrow">{t("contracts.upload_contract")}</span>
          <strong>{t("contracts.document_status")}: {stagedStatus}</strong>
        </div>
        <p className="panel-copy">{t("contracts.upload_hint")}</p>
        <div className="contract-upload-actions">
          <button type="button" onClick={() => contractImportRef.current?.click()}>
            {t("contracts.upload_contract")}
          </button>
          <button type="button" className="secondary-button" onClick={resetContractDraft}>
            {t("contracts.new_draft")}
          </button>
          <input
            ref={contractImportRef}
            className="contract-import-input"
            type="file"
            accept=".json,.txt,.pdf,.doc,.docx,application/json,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            hidden
            onChange={importContractDraftFile}
          />
          <span>{contractImportMessage ?? contractSaveMessage ?? t("contracts.save_hint")}</span>
        </div>
        <div className="contract-source-evidence">
          {sourceEvidence.map((item) => (
            <strong key={`contract-source-${item}`}>{item}</strong>
          ))}
        </div>
      </section>

      <section className="workspace-panel contract-detail-preview">
        <div className="section-heading">
          <span className="eyebrow">{t("contracts.preview")}</span>
          <strong>{contract.contract_name || contract.contract_id}</strong>
        </div>
        <div className="metric-grid">
          <div><span>{t("contracts.counterparty")}</span><strong>{contract.counterparty || "n/a"}</strong></div>
          <div><span>{t("contracts.beach_delivery")}</span><strong>{contract.beach_delivery_point || "n/a"}</strong></div>
          <div><span>{t("contracts.title_transfer_point")}</span><strong>{contract.title_transfer_point || "n/a"}</strong></div>
          <div><span>{t("economics.volume")}</span><strong>{formatQuantity(contract.delivery_quantity_mwh_per_day)}</strong></div>
        </div>
        <div className="contract-warning-stack">
          {warningStack.map((item) => <span key={`contract-warning-${item}`}>{item}</span>)}
        </div>
      </section>

      <section className="workspace-panel span-3 contract-manual-editor">
        <div className="section-heading">
          <span className="eyebrow">{t("contracts.efet_style")}</span>
          <strong>{t("contracts.title")}</strong>
        </div>
        <p className="panel-copy">{t("contracts.description")}</p>

        <div className="efet-section-grid efet-clause-map">
          <div className="efet-section">
            <span className="eyebrow">{t("contracts.agreement")}</span>
            <label>{t("contracts.contract_id")}<input value={contract.contract_id} onChange={(event) => updateContractText("contract_id", event.target.value)} /></label>
            <label>{t("contracts.contract_name")}<input value={contract.contract_name} onChange={(event) => updateContractText("contract_name", event.target.value)} /></label>
            <label>{t("contracts.counterparty")}<input value={contract.counterparty} onChange={(event) => updateContractText("counterparty", event.target.value)} /></label>
            <label>{t("contracts.contract_type")}<input value={contract.contract_type} onChange={(event) => updateContractText("contract_type", event.target.value)} /></label>
          </div>
          <div className="efet-section">
            <span className="eyebrow">{t("contracts.product_term")}</span>
            <label>{t("contracts.gas_year")}<input value={contract.gas_year} onChange={(event) => updateContractText("gas_year", event.target.value)} /></label>
            <label>{t("economics.volume")}<input type="number" value={contract.delivery_quantity_mwh_per_day} onChange={(event) => updateContractNumber("delivery_quantity_mwh_per_day", event.target.value)} /></label>
            <label>{t("contracts.index_basis")}<input value={contract.index_basis} onChange={(event) => updateContractText("index_basis", event.target.value)} /></label>
          </div>
          <div className="efet-section">
            <span className="eyebrow">{t("contracts.delivery")}</span>
            <label>{t("contracts.delivery_point")}<input value={contract.delivery_point_name} onChange={(event) => updateContractText("delivery_point_name", event.target.value)} /></label>
            <label>{t("contracts.title_transfer_point")}<input value={contract.title_transfer_point} onChange={(event) => updateContractText("title_transfer_point", event.target.value)} /></label>
            <label>{t("contracts.delivery_mode")}<input value="PHYSICAL_ENTRY_DELIVERY" readOnly /></label>
          </div>
          <div className="efet-section">
            <span className="eyebrow">{t("contracts.quantity_tolerance")}</span>
            <label>{t("economics.delivery_tolerance")}<input type="number" value={contract.delivery_tolerance_pct} onChange={(event) => updateContractNumber("delivery_tolerance_pct", event.target.value)} /></label>
            <label>{t("economics.nomination_tolerance")}<input type="number" value={contract.nomination_tolerance_pct} onChange={(event) => updateContractNumber("nomination_tolerance_pct", event.target.value)} /></label>
            <label>{t("contracts.fuel_loss")}<input type="number" value={contract.fuel_loss_allowance_pct} onChange={(event) => updateContractNumber("fuel_loss_allowance_pct", event.target.value)} /></label>
          </div>
          <div className="efet-section">
            <span className="eyebrow">{t("contracts.price")}</span>
            <label>{t("economics.contract_price")}<input type="number" value={contract.contract_price_gbp_mwh} onChange={(event) => updateContractNumber("contract_price_gbp_mwh", event.target.value)} /></label>
            <label>{t("contracts.pricing_method")}<input value={contract.index_basis || "OPERATOR_DRAFT / index-ready"} readOnly /></label>
          </div>
          <div className="efet-section">
            <span className="eyebrow">{t("contracts.costs")}</span>
            <label>{t("contracts.balancing_allowance")}<input type="number" value={contract.tolerance_risk_allowance_gbp_mwh} onChange={(event) => updateContractNumber("tolerance_risk_allowance_gbp_mwh", event.target.value)} /></label>
            <label>{t("contracts.variable_cost")}<input type="number" value={contract.variable_cost_gbp_mwh} onChange={(event) => updateContractNumber("variable_cost_gbp_mwh", event.target.value)} /></label>
            <label>{t("contracts.regas_fee")}<input type="number" value={contract.regas_fee_gbp_mwh} onChange={(event) => updateContractNumber("regas_fee_gbp_mwh", event.target.value)} /></label>
          </div>
          <div className="efet-section beach-delivery-strip">
            <span className="eyebrow">{t("contracts.beach_delivery")}</span>
            <label>{t("contracts.beach_delivery_point")}<input value={contract.beach_delivery_point} onChange={(event) => updateContractText("beach_delivery_point", event.target.value)} /></label>
            <label>{t("contracts.terminal_access")}<input value={contract.terminal_access} onChange={(event) => updateContractText("terminal_access", event.target.value)} /></label>
            <label>{t("contracts.capacity_expiry")}<input value={contract.capacity_expiry} onChange={(event) => updateContractText("capacity_expiry", event.target.value)} /></label>
          </div>
          <div className="efet-section">
            <span className="eyebrow">{t("contracts.capacity_rights")}</span>
            <label>{t("contracts.entry_capacity")}<input value={contract.owned_entry_capacity_mwh_per_day ?? "operator to enter"} readOnly /></label>
            <label>{t("contracts.tso_access")}<input value={contract.terminal_access || "operator to enter"} readOnly /></label>
          </div>
          <div className="efet-section">
            <span className="eyebrow">{t("contracts.settlement_cash")}</span>
            <label>{t("economics.cash_lag")}<input type="number" value={contract.screen_sale_cash_lag_days} onChange={(event) => updateContractNumber("screen_sale_cash_lag_days", event.target.value)} /></label>
            <label>{t("contracts.upstream_payment_lag")}<input type="number" value={contract.upstream_payment_lag_days} onChange={(event) => updateContractNumber("upstream_payment_lag_days", event.target.value)} /></label>
            <label>{t("contracts.governing_law")}<input value={contract.governing_law} onChange={(event) => updateContractText("governing_law", event.target.value)} /></label>
          </div>
          <div className="efet-section span-2">
            <span className="eyebrow">{t("contracts.restrictions")}</span>
            <div className="destination-switcher">
              {contract.allowed_exit_points.map((point) => <span key={`allowed-${point}`} className="chip active">{point}</span>)}
              {contract.eligible_sale_modes.map((modeLabel) => <span key={`sale-mode-${modeLabel}`} className="chip">{modeLabel}</span>)}
            </div>
          </div>
        </div>

        <div className="action-row contract-action-row">
          <button type="button" disabled={!runtimeDbReady || loading} onClick={() => saveDraftContract(contractPayload)}>
            {t("contracts.save_to_resource_pool")}
          </button>
          <span>{contractSaveMessage ?? t("contracts.save_hint")}</span>
        </div>
      </section>

      <section className="workspace-panel span-2 contract-library-panel">
        <div className="panel-title-row">
          <h3>{t("contracts.library")}</h3>
          <span>{upstreamContracts.length} {t("panel.records")}</span>
        </div>
        <div className="contract-library-list">
          {upstreamContracts.map((saved) => (
            <button
              key={`saved-contract-${saved.contract_id}`}
              type="button"
              className="contract-library-row"
              onClick={() => loadPersistedContract(saved)}
            >
              <span>
                <strong>{saved.contract_name}</strong>
                <small>{saved.contract_id} · {saved.delivery_point_name} · {saved.gas_year}</small>
              </span>
              <span>
                <strong>{formatQuantity(saved.delivery_quantity_mwh_per_day)}</strong>
                <small>MWh/d</small>
              </span>
              <span>
                <strong>{formatMoney(saved.contract_price_gbp_mwh)}</strong>
                <small>GBP/MWh</small>
              </span>
              <em>{t("contracts.edit")}</em>
            </button>
          ))}
          {upstreamContracts.length === 0 && (
            <p className="panel-copy">{t("contracts.no_saved_contracts")}</p>
          )}
        </div>
      </section>

      <section className="workspace-panel contract-resource-panel">
        <h3>{t("home.resource_pool")}</h3>
        <div className="metric-grid">
          <div><span>{t("home.resources")}</span><strong>{portfolioResources.length}</strong></div>
          <div><span>{t("home.pool_volume")}</span><strong>{formatQuantity(totalPoolVolume)}</strong></div>
          <div><span>{t("result.cash_value")}</span><strong>{firstPoolAllocation ? formatMoney(firstPoolAllocation.early_cash_value_gbp_mwh) : "n/a"}</strong></div>
        </div>
      </section>
    </div>
  );
}
