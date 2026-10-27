import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";

import { PanelHeader } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  LNG_ECONOMICS_CHARGE_BASES,
  LNG_ECONOMICS_COST_CATEGORIES,
  LNG_ECONOMICS_ENERGY_UNITS,
  LNG_ECONOMICS_PURCHASE_BASES,
  LNG_ECONOMICS_REPORTING_CURRENCIES,
  LNG_ECONOMICS_STAGE_KINDS,
  emptyLngEconomicsCostDraft,
  emptyLngEconomicsDiscountDraft,
  emptyLngEconomicsStageDraft,
  lngEconomicsSubmitShortcut,
  type LngEconomicsCostDraft,
  type LngEconomicsDiscountDraft,
  type LngEconomicsDraft,
  type LngEconomicsStageDraft,
} from "@/app/model/lngEconomicsModel";
import type { LngEconomicsController } from "@/app/model/useLngEconomicsOnly";
import "./lng-economics.css";

type Translate = (key: string) => string;

interface LngEconomicsPanelProps {
  readonly t: Translate;
  readonly lngEconomics: LngEconomicsController;
  /** The selected contract is context only; it is never resolved or treated as verified. */
  readonly selectedContractId: string | null;
  readonly selectedContractName: string | null;
}

function optionalText(value: string | null | undefined, unknown: string): string {
  return value === null || value === undefined || value === "" ? unknown : value;
}

function booleanText(value: boolean | undefined, unknown: string): string {
  return typeof value === "boolean" ? String(value) : unknown;
}

/**
 * The LNG economics-only sandbox inside the existing Contracts workbench.
 *
 * `POST /api/research/lng-economics-only` is the explicit, caller-supplied composition. This panel
 * is a form and an exact readback, never a calculator:
 *
 * - every financial, energy and discount-factor field is text, transported as the caller typed it
 *   and rendered exactly as the backend returned it; there is no local parsing, rounding,
 *   conversion or margin/NPV step anywhere in this component;
 * - the ordered energy chain, invoiced cash costs and discount factors are explicit editable rows.
 *   Adding a row inserts blank text, never a sample stage, `1` factor or implied charge basis;
 * - the selected contract id is shown as context and can be copied into the editable `contract_id`
 *   field. It is not looked up, verified, or used to fill any other fact;
 * - the response's `physical_readiness` and `readiness_assessed` are displayed as returned. The
 *   panel never turns the backend's not-assessed status or its `false` boolean into a readiness
 *   claim, and it states that profitable economics is not delivery feasibility, a slot, a storage
 *   right or nomination authority;
 * - the previous result is not kept beside a changed draft, a pending run, a refusal or a
 *   transport failure.
 */
export function LngEconomicsPanel({
  t,
  lngEconomics,
  selectedContractId,
  selectedContractName,
}: LngEconomicsPanelProps) {
  const { draft, updateDraft, readiness, busy, result, meta, refusal, error } = lngEconomics;
  const resultRef = useRef<HTMLDivElement | null>(null);
  const transportFailure = error ? presentError(t, describeFailure(error)) : null;
  const showResult = result !== null && !busy && !refusal && !error;
  const unknown = t("contracts.lng_economics.unknown");

  useEffect(() => {
    if (!showResult || result === null) return;
    // Move focus to the backend's answer after a successful run. The region is programmatically
    // focusable, so keyboard and screen-reader users land on the result without another tab stop
    // in the form's tab order.
    resultRef.current?.focus({ preventScroll: true });
    resultRef.current?.scrollIntoView({ block: "start" });
  }, [result, showResult]);

  function update(patch: Partial<LngEconomicsDraft>): void {
    updateDraft((current) => ({ ...current, ...patch }));
  }

  function updateCost(index: number, patch: Partial<LngEconomicsCostDraft>): void {
    updateDraft((current) => ({
      ...current,
      downstreamCosts: current.downstreamCosts.map((row, position) =>
        position === index ? { ...row, ...patch } : row,
      ),
    }));
  }

  function addCost(): void {
    updateDraft((current) => ({
      ...current,
      downstreamCosts: [...current.downstreamCosts, emptyLngEconomicsCostDraft()],
    }));
  }

  function removeCost(index: number): void {
    updateDraft((current) => ({
      ...current,
      downstreamCosts: current.downstreamCosts.filter((_, position) => position !== index),
    }));
  }

  function updateStage(index: number, patch: Partial<LngEconomicsStageDraft>): void {
    updateDraft((current) => ({
      ...current,
      energyStages: current.energyStages.map((row, position) =>
        position === index ? { ...row, ...patch } : row,
      ),
    }));
  }

  function addStage(): void {
    updateDraft((current) => ({
      ...current,
      energyStages: [...current.energyStages, emptyLngEconomicsStageDraft()],
    }));
  }

  function removeStage(index: number): void {
    updateDraft((current) => ({
      ...current,
      energyStages: current.energyStages.filter((_, position) => position !== index),
    }));
  }

  function moveStage(index: number, direction: -1 | 1): void {
    updateDraft((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.energyStages.length) return current;
      const next = [...current.energyStages];
      const [row] = next.splice(index, 1);
      next.splice(target, 0, row);
      return { ...current, energyStages: next };
    });
  }

  function updateDiscount(index: number, patch: Partial<LngEconomicsDiscountDraft>): void {
    updateDraft((current) => ({
      ...current,
      discountFactors: current.discountFactors.map((row, position) =>
        position === index ? { ...row, ...patch } : row,
      ),
    }));
  }

  function addDiscount(): void {
    updateDraft((current) => ({
      ...current,
      discountFactors: [...current.discountFactors, emptyLngEconomicsDiscountDraft()],
    }));
  }

  function removeDiscount(index: number): void {
    updateDraft((current) => ({
      ...current,
      discountFactors: current.discountFactors.filter((_, position) => position !== index),
    }));
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>): void {
    // The chord is handled only here, inside the panel section: no window listener competes with
    // the workspace's other shortcuts.
    if (!lngEconomicsSubmitShortcut(event, { canSubmit: readiness.canSubmit, busy })) return;
    event.preventDefault();
    void lngEconomics.run();
  }

  return (
    <section
      className="workspace-panel lng-economics-panel"
      aria-labelledby="lng-economics-title"
      onKeyDown={handleKeyDown}
    >
      <PanelHeader
        title={<span id="lng-economics-title">{t("contracts.lng_economics.title")}</span>}
        meta={
          busy
            ? t("contracts.lng_economics.loading")
            : result
              ? `${t("contracts.lng_economics.model_version")}: ${result.model_version}`
              : t("contracts.lng_economics.not_run")
        }
      />
      <p className="panel-copy">{t("contracts.lng_economics.note")}</p>

      <div className="route-cost-issues" role="note">
        <strong>{t("contracts.lng_economics.sandbox_notice")}</strong>
        <p>{t("contracts.lng_economics.sandbox_detail")}</p>
        <p>{t("contracts.lng_economics.no_readiness_claim")}</p>
      </div>

      <div className="lng-economics-context" role="note">
        <div>
          <span className="eyebrow">{t("contracts.lng_economics.selected_context")}</span>
          <strong>
            {selectedContractName ?? selectedContractId ?? t("contracts.lng_economics.no_selection")}
          </strong>
          <span>
            {selectedContractId
              ? `${t("contracts.lng_economics.context_id")}: ${selectedContractId}`
              : t("contracts.lng_economics.no_selection")}
          </span>
        </div>
        <p>{t("contracts.lng_economics.context_only")}</p>
        <button
          type="button"
          className="secondary-button"
          disabled={!selectedContractId || busy}
          onClick={() => {
            if (selectedContractId) update({ contractId: selectedContractId });
          }}
        >
          {t("contracts.lng_economics.use_selected_contract")}
        </button>
      </div>

      <fieldset className="lng-economics-section" disabled={busy}>
        <legend>{t("contracts.lng_economics.scope_section")}</legend>
        <p className="panel-copy">{t("contracts.lng_economics.scope_help")}</p>
        <div className="contract-field-grid">
          <label>
            {t("contracts.lng_economics.contract_id")}
            <input
              type="text"
              value={draft.contractId}
              maxLength={128}
              aria-required="true"
              onChange={(event) => update({ contractId: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.cargo_id")}
            <input
              type="text"
              value={draft.cargoId}
              maxLength={128}
              aria-required="true"
              onChange={(event) => update({ cargoId: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.terminal_id")}
            <input
              type="text"
              value={draft.terminalId}
              maxLength={128}
              aria-required="true"
              onChange={(event) => update({ terminalId: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.resource_id")}
            <input
              type="text"
              value={draft.resourceId}
              maxLength={128}
              aria-required="true"
              onChange={(event) => update({ resourceId: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.valuation_date")}
            <input
              type="text"
              value={draft.valuationDate}
              maxLength={32}
              placeholder={t("contracts.lng_economics.date_placeholder")}
              aria-required="true"
              onChange={(event) => update({ valuationDate: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.purchase_payment_date")}
            <input
              type="text"
              value={draft.purchasePaymentDate}
              maxLength={32}
              placeholder={t("contracts.lng_economics.date_placeholder")}
              aria-required="true"
              onChange={(event) => update({ purchasePaymentDate: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.sale_payment_date")}
            <input
              type="text"
              value={draft.salePaymentDate}
              maxLength={32}
              placeholder={t("contracts.lng_economics.date_placeholder")}
              aria-required="true"
              onChange={(event) => update({ salePaymentDate: event.target.value })}
            />
          </label>
          <label className="span-2">
            {t("contracts.lng_economics.cost_scope_statement")}
            <textarea
              rows={3}
              value={draft.costScopeStatement}
              maxLength={1000}
              aria-required="true"
              aria-describedby="lng-economics-cost-scope-help"
              onChange={(event) => update({ costScopeStatement: event.target.value })}
            />
          </label>
        </div>
        <ul className="route-cost-notes">
          <li id="lng-economics-cost-scope-help">
            {t("contracts.lng_economics.cost_scope_help")}
          </li>
        </ul>
      </fieldset>

      <fieldset className="lng-economics-section" disabled={busy}>
        <legend>{t("contracts.lng_economics.purchase_sale_section")}</legend>
        <div className="contract-field-grid">
          <label>
            {t("contracts.lng_economics.purchased_energy")}
            <input
              type="text"
              inputMode="decimal"
              value={draft.purchasedEnergyMwh}
              maxLength={64}
              aria-required="true"
              onChange={(event) => update({ purchasedEnergyMwh: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.delivered_energy")}
            <input
              type="text"
              inputMode="decimal"
              value={draft.deliveredEnergyMwh}
              maxLength={64}
              aria-required="true"
              onChange={(event) => update({ deliveredEnergyMwh: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.purchase_unit_price")}
            <input
              type="text"
              inputMode="decimal"
              value={draft.purchaseUnitPriceEurPerMwh}
              maxLength={64}
              aria-required="true"
              aria-describedby="lng-economics-price-help"
              onChange={(event) => update({ purchaseUnitPriceEurPerMwh: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.sale_unit_price")}
            <input
              type="text"
              inputMode="decimal"
              value={draft.saleUnitPriceEurPerMwh}
              maxLength={64}
              aria-required="true"
              aria-describedby="lng-economics-price-help"
              onChange={(event) => update({ saleUnitPriceEurPerMwh: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.purchase_price_source")}
            <input
              type="text"
              value={draft.purchasePriceSourceReference}
              maxLength={256}
              aria-required="true"
              onChange={(event) => update({ purchasePriceSourceReference: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.sale_price_source")}
            <input
              type="text"
              value={draft.salePriceSourceReference}
              maxLength={256}
              aria-required="true"
              onChange={(event) => update({ salePriceSourceReference: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.purchase_basis")}
            <select
              value={draft.purchaseBasis}
              aria-required="true"
              onChange={(event) => update({ purchaseBasis: event.target.value })}
            >
              <option value="">{t("contracts.lng_economics.select_placeholder")}</option>
              {LNG_ECONOMICS_PURCHASE_BASES.map((basis) => (
                <option key={basis} value={basis}>{basis}</option>
              ))}
            </select>
          </label>
          <label className="span-2">
            {t("contracts.lng_economics.purchase_included_cost_items")}
            <textarea
              rows={3}
              value={draft.purchaseIncludedCostItems}
              aria-describedby="lng-economics-included-help"
              onChange={(event) => update({ purchaseIncludedCostItems: event.target.value })}
            />
          </label>
        </div>
        <ul className="route-cost-notes">
          <li id="lng-economics-price-help">{t("contracts.lng_economics.price_help")}</li>
          <li id="lng-economics-included-help">
            {t("contracts.lng_economics.included_cost_help")}
          </li>
        </ul>
      </fieldset>

      <fieldset className="lng-economics-section" disabled={busy}>
        <legend>{t("contracts.lng_economics.energy_section")}</legend>
        <div className="contract-field-grid">
          <label>
            {t("contracts.lng_economics.energy_basis_reference")}
            <input
              type="text"
              value={draft.energyBasisReference}
              maxLength={256}
              aria-required="true"
              onChange={(event) => update({ energyBasisReference: event.target.value })}
            />
          </label>
          <label>
            {t("contracts.lng_economics.energy_unit")}
            <select
              value={draft.energyUnit}
              aria-required="true"
              onChange={(event) => update({ energyUnit: event.target.value })}
            >
              <option value="">{t("contracts.lng_economics.select_placeholder")}</option>
              {LNG_ECONOMICS_ENERGY_UNITS.map((unit) => (
                <option key={unit} value={unit}>{unit}</option>
              ))}
            </select>
          </label>
          <label>
            {t("contracts.lng_economics.reporting_currency")}
            <select
              value={draft.reportingCurrency}
              aria-required="true"
              onChange={(event) => update({ reportingCurrency: event.target.value })}
            >
              <option value="">{t("contracts.lng_economics.select_placeholder")}</option>
              {LNG_ECONOMICS_REPORTING_CURRENCIES.map((currency) => (
                <option key={currency} value={currency}>{currency}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="panel-copy">{t("contracts.lng_economics.energy_stages_help")}</p>
        {draft.energyStages.map((stage, index) => (
          <fieldset className="lng-economics-row" key={`energy-stage-${index}`}>
            <legend>
              {t("contracts.lng_economics.stage")} {index + 1}
            </legend>
            <div className="contract-field-grid">
              <label>
                {t("contracts.lng_economics.stage_id")}
                <input
                  type="text"
                  value={stage.stageId}
                  maxLength={128}
                  aria-required="true"
                  onChange={(event) => updateStage(index, { stageId: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.stage_kind")}
                <select
                  value={stage.kind}
                  aria-required="true"
                  onChange={(event) => updateStage(index, { kind: event.target.value })}
                >
                  <option value="">{t("contracts.lng_economics.select_placeholder")}</option>
                  {LNG_ECONOMICS_STAGE_KINDS.map((kind) => (
                    <option key={kind} value={kind}>{kind}</option>
                  ))}
                </select>
              </label>
              <label>
                {t("contracts.lng_economics.stage_input")}
                <input
                  type="text"
                  inputMode="decimal"
                  value={stage.inputEnergyMwh}
                  maxLength={64}
                  aria-required="true"
                  onChange={(event) => updateStage(index, { inputEnergyMwh: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.stage_output")}
                <input
                  type="text"
                  inputMode="decimal"
                  value={stage.outputEnergyMwh}
                  maxLength={64}
                  aria-required="true"
                  onChange={(event) => updateStage(index, { outputEnergyMwh: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.stage_consumed")}
                <input
                  type="text"
                  inputMode="decimal"
                  value={stage.consumedEnergyMwh}
                  maxLength={64}
                  aria-required="true"
                  onChange={(event) => updateStage(index, { consumedEnergyMwh: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.stage_physical_loss")}
                <input
                  type="text"
                  inputMode="decimal"
                  value={stage.physicalLossEnergyMwh}
                  maxLength={64}
                  aria-required="true"
                  onChange={(event) =>
                    updateStage(index, { physicalLossEnergyMwh: event.target.value })
                  }
                />
              </label>
              <label className="span-2">
                {t("contracts.lng_economics.stage_source_references")}
                <textarea
                  rows={2}
                  value={stage.sourceReferences}
                  aria-required="true"
                  onChange={(event) =>
                    updateStage(index, { sourceReferences: event.target.value })
                  }
                />
              </label>
            </div>
            <div className="lng-economics-row-actions">
              <button
                type="button"
                className="secondary-button"
                disabled={index === 0}
                aria-label={`${t("contracts.lng_economics.move_stage_up")} ${index + 1}`}
                onClick={() => moveStage(index, -1)}
              >
                {t("contracts.lng_economics.move_stage_up")}
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={index === draft.energyStages.length - 1}
                aria-label={`${t("contracts.lng_economics.move_stage_down")} ${index + 1}`}
                onClick={() => moveStage(index, 1)}
              >
                {t("contracts.lng_economics.move_stage_down")}
              </button>
              <button
                type="button"
                className="secondary-button"
                aria-label={`${t("contracts.lng_economics.remove_stage")} ${index + 1}`}
                onClick={() => removeStage(index)}
              >
                {t("contracts.lng_economics.remove_stage")}
              </button>
            </div>
          </fieldset>
        ))}
        <div className="lng-economics-row-actions">
          <button type="button" className="secondary-button" onClick={addStage}>
            {t("contracts.lng_economics.add_stage")}
          </button>
        </div>
      </fieldset>

      <fieldset className="lng-economics-section" disabled={busy}>
        <legend>{t("contracts.lng_economics.costs_section")}</legend>
        <p className="panel-copy">{t("contracts.lng_economics.costs_help")}</p>
        {draft.downstreamCosts.map((cost, index) => (
          <fieldset className="lng-economics-row" key={`downstream-cost-${index}`}>
            <legend>
              {t("contracts.lng_economics.cost")} {index + 1}
            </legend>
            <div className="contract-field-grid">
              <label>
                {t("contracts.lng_economics.cost_id")}
                <input
                  type="text"
                  value={cost.costId}
                  maxLength={128}
                  aria-required="true"
                  onChange={(event) => updateCost(index, { costId: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.cost_category")}
                <select
                  value={cost.category}
                  aria-required="true"
                  onChange={(event) => updateCost(index, { category: event.target.value })}
                >
                  <option value="">{t("contracts.lng_economics.select_placeholder")}</option>
                  {LNG_ECONOMICS_COST_CATEGORIES.map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </label>
              <label>
                {t("contracts.lng_economics.cost_amount")}
                <input
                  type="text"
                  inputMode="decimal"
                  value={cost.amountEur}
                  maxLength={64}
                  aria-required="true"
                  onChange={(event) => updateCost(index, { amountEur: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.cost_payment_date")}
                <input
                  type="text"
                  value={cost.paymentDate}
                  maxLength={32}
                  placeholder={t("contracts.lng_economics.date_placeholder")}
                  aria-required="true"
                  onChange={(event) => updateCost(index, { paymentDate: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.cost_source_reference")}
                <input
                  type="text"
                  value={cost.sourceReference}
                  maxLength={256}
                  aria-required="true"
                  onChange={(event) => updateCost(index, { sourceReference: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.cost_charge_basis")}
                <select
                  value={cost.chargeBasis}
                  aria-required="true"
                  aria-describedby={`lng-economics-charge-help-${index}`}
                  onChange={(event) => updateCost(index, { chargeBasis: event.target.value })}
                >
                  <option value="">{t("contracts.lng_economics.select_placeholder")}</option>
                  {LNG_ECONOMICS_CHARGE_BASES.map((basis) => (
                    <option key={basis} value={basis}>{basis}</option>
                  ))}
                </select>
              </label>
            </div>
            <ul className="route-cost-notes">
              <li id={`lng-economics-charge-help-${index}`}>
                {t("contracts.lng_economics.charge_basis_help")}
              </li>
            </ul>
            <div className="lng-economics-row-actions">
              <button
                type="button"
                className="secondary-button"
                aria-label={`${t("contracts.lng_economics.remove_cost")} ${index + 1}`}
                onClick={() => removeCost(index)}
              >
                {t("contracts.lng_economics.remove_cost")}
              </button>
            </div>
          </fieldset>
        ))}
        <div className="lng-economics-row-actions">
          <button type="button" className="secondary-button" onClick={addCost}>
            {t("contracts.lng_economics.add_cost")}
          </button>
        </div>
      </fieldset>

      <fieldset className="lng-economics-section" disabled={busy}>
        <legend>{t("contracts.lng_economics.discounts_section")}</legend>
        <p className="panel-copy">{t("contracts.lng_economics.discounts_help")}</p>
        {draft.discountFactors.map((discount, index) => (
          <fieldset className="lng-economics-row" key={`discount-factor-${index}`}>
            <legend>
              {t("contracts.lng_economics.discount")} {index + 1}
            </legend>
            <div className="contract-field-grid">
              <label>
                {t("contracts.lng_economics.discount_payment_date")}
                <input
                  type="text"
                  value={discount.paymentDate}
                  maxLength={32}
                  placeholder={t("contracts.lng_economics.date_placeholder")}
                  aria-required="true"
                  onChange={(event) => updateDiscount(index, { paymentDate: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.discount_factor")}
                <input
                  type="text"
                  inputMode="decimal"
                  value={discount.factor}
                  maxLength={64}
                  aria-required="true"
                  aria-describedby={`lng-economics-discount-help-${index}`}
                  onChange={(event) => updateDiscount(index, { factor: event.target.value })}
                />
              </label>
              <label>
                {t("contracts.lng_economics.discount_curve_reference")}
                <input
                  type="text"
                  value={discount.curveReference}
                  maxLength={256}
                  aria-required="true"
                  onChange={(event) =>
                    updateDiscount(index, { curveReference: event.target.value })
                  }
                />
              </label>
              <label>
                {t("contracts.lng_economics.discount_source_reference")}
                <input
                  type="text"
                  value={discount.sourceReference}
                  maxLength={256}
                  aria-required="true"
                  onChange={(event) =>
                    updateDiscount(index, { sourceReference: event.target.value })
                  }
                />
              </label>
              <label>
                {t("contracts.lng_economics.discount_as_of")}
                <input
                  type="text"
                  value={discount.asOf}
                  maxLength={32}
                  placeholder={t("contracts.lng_economics.date_placeholder")}
                  aria-required="true"
                  onChange={(event) => updateDiscount(index, { asOf: event.target.value })}
                />
              </label>
            </div>
            <ul className="route-cost-notes">
              <li id={`lng-economics-discount-help-${index}`}>
                {t("contracts.lng_economics.discount_help")}
              </li>
            </ul>
            <div className="lng-economics-row-actions">
              <button
                type="button"
                className="secondary-button"
                aria-label={`${t("contracts.lng_economics.remove_discount")} ${index + 1}`}
                onClick={() => removeDiscount(index)}
              >
                {t("contracts.lng_economics.remove_discount")}
              </button>
            </div>
          </fieldset>
        ))}
        <div className="lng-economics-row-actions">
          <button type="button" className="secondary-button" onClick={addDiscount}>
            {t("contracts.lng_economics.add_discount")}
          </button>
        </div>
      </fieldset>

      {readiness.blockerKeys.length > 0 && (
        <div className="route-cost-issues" role="status">
          <strong>{t("contracts.lng_economics.required_fields")}</strong>
          <ul>
            {readiness.blockerKeys.map((key, index) => (
              <li key={`${key}-${index}`}>{t(key)}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="route-cost-component-actions">
        <button
          type="button"
          className="button"
          disabled={busy || !readiness.canSubmit}
          title={t(readiness.firstBlockerKey ?? "contracts.lng_economics.ready")}
          aria-keyshortcuts="Control+Enter"
          onClick={() => void lngEconomics.run()}
        >
          {busy ? t("contracts.lng_economics.loading") : t("contracts.lng_economics.calculate")}
        </button>
        <span className="muted">{t("contracts.lng_economics.shortcut_help")}</span>
      </div>

      <div aria-live="polite" aria-busy={busy}>
        {busy && <p className="muted">{t("contracts.lng_economics.loading")}</p>}

        {refusal && (
          <div className="alert" role="alert">
            <strong>{t("contracts.lng_economics.refusal")}</strong>
            <p>{t("contracts.lng_economics.refusal_help")}</p>
            <p>
              <strong>{t("contracts.lng_economics.refusal_code")}:</strong>{" "}
              <code>{refusal.code || unknown}</code>{" "}
              <span className="muted">HTTP {refusal.status}</span>
            </p>
            {refusal.message && <p>{refusal.message}</p>}
            {refusal.violations.length > 0 && (
              <div className="route-cost-issues">
                <strong>{t("contracts.lng_economics.refusal_violations")}</strong>
                <ul>
                  {refusal.violations.map((violation, index) => (
                    <li key={`${violation.code}-${index}`}>
                      <code>{violation.code || unknown}</code>
                      {violation.detail ? <span> {violation.detail}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {transportFailure && (
          <div className="alert" role="alert">
            <strong>{transportFailure.title}</strong>
            <p>{transportFailure.cause}</p>
            <p>{transportFailure.action}</p>
            <p className="muted">{t("contracts.lng_economics.transport_error_help")}</p>
          </div>
        )}

        {showResult && result && (
          <div
            className="route-cost-result lng-economics-result"
            ref={resultRef}
            tabIndex={-1}
            role="region"
            aria-label={t("contracts.lng_economics.result")}
          >
            <div className="section-heading">
              <span className="eyebrow">{t("contracts.lng_economics.result")}</span>
              <strong>{result.model_version}</strong>
            </div>
            <p className="muted">{t("contracts.lng_economics.result_exact")}</p>

            <div className="commercial-metric-strip" aria-label={t("contracts.lng_economics.result")}>
              <span>
                <small>{t("contracts.lng_economics.cargo_margin")}</small>
                <strong>{result.cargo_margin_eur} {result.reporting_currency}</strong>
              </span>
              <span>
                <small>{t("contracts.lng_economics.unit_netback")}</small>
                <strong>
                  {result.unit_netback_eur_per_purchased_mwh} {result.reporting_currency}/MWh
                </strong>
              </span>
              <span>
                <small>{t("contracts.lng_economics.net_present_value")}</small>
                <strong>{result.net_present_value_eur} {result.reporting_currency}</strong>
              </span>
              <span>
                <small>{t("contracts.lng_economics.purchase_outlay")}</small>
                <strong>{result.purchase_outlay_eur} {result.reporting_currency}</strong>
              </span>
              <span>
                <small>{t("contracts.lng_economics.sale_proceeds")}</small>
                <strong>{result.sale_proceeds_eur} {result.reporting_currency}</strong>
              </span>
              <span>
                <small>{t("contracts.lng_economics.downstream_costs_total")}</small>
                <strong>{result.total_downstream_costs_eur} {result.reporting_currency}</strong>
              </span>
            </div>

            <div className="route-cost-issues">
              <strong>{t("contracts.lng_economics.energy_result")}</strong>
              <div className="contract-definition-list">
                <div>
                  <span>{t("contracts.lng_economics.purchased_energy")}</span>
                  <strong>{result.purchased_energy_mwh} {result.energy_unit}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.delivered_energy")}</span>
                  <strong>{result.delivered_energy_mwh} {result.energy_unit}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.total_consumed")}</span>
                  <strong>{result.total_consumed_energy_mwh} {result.energy_unit}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.physical_loss")}</span>
                  <strong>{result.physical_loss_energy_mwh} {result.energy_unit}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.total_reduction")}</span>
                  <strong>{result.total_reduction_energy_mwh} {result.energy_unit}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.physical_readiness")}</span>
                  <strong>{optionalText(result.physical_readiness, unknown)}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.readiness_assessed")}</span>
                  <strong>{booleanText(result.readiness_assessed, unknown)}</strong>
                </div>
              </div>
              <p className="muted">{t("contracts.lng_economics.energy_totals_note")}</p>
            </div>

            <div className="route-cost-issues">
              <strong>{t("contracts.lng_economics.basis")}</strong>
              <div className="contract-definition-list">
                <div>
                  <span>{t("contracts.lng_economics.model_version")}</span>
                  <strong>{result.model_version}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.action")}</span>
                  <strong>{result.action}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.contract_id")}</span>
                  <strong>{result.contract_id}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.cargo_id")}</span>
                  <strong>{result.cargo_id}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.terminal_id")}</span>
                  <strong>{result.terminal_id}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.resource_id")}</span>
                  <strong>{result.resource_id}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.valuation_date")}</span>
                  <strong>{result.valuation_date}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.reporting_currency")}</span>
                  <strong>{result.reporting_currency}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.energy_basis_reference")}</span>
                  <strong>{result.energy_basis_reference}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.energy_unit")}</span>
                  <strong>{result.energy_unit}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.purchase_basis")}</span>
                  <strong>{result.purchase_basis}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.purchase_unit_price")}</span>
                  <strong>{result.purchase_unit_price_eur_per_mwh} EUR/MWh</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.sale_unit_price")}</span>
                  <strong>{result.sale_unit_price_eur_per_mwh} EUR/MWh</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.sale_basis")}</span>
                  <strong>{result.sale_basis_eur_per_delivered_mwh} EUR/MWh</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.margin_gap")}</span>
                  <strong>{result.margin_reconciliation_gap_eur} EUR</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.margin_tolerance")}</span>
                  <strong>{result.margin_reconciliation_tolerance_eur} EUR</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.total_undiscounted_cash")}</span>
                  <strong>{result.total_undiscounted_cash_eur} EUR</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.purchase_included_cost_items")}</span>
                  <strong>
                    {result.purchase_included_cost_items.length > 0
                      ? result.purchase_included_cost_items.join(", ")
                      : t("contracts.lng_economics.none_declared")}
                  </strong>
                </div>
                <div className="span-2">
                  <span>{t("contracts.lng_economics.cost_scope_statement")}</span>
                  <strong>{result.cost_scope_statement}</strong>
                </div>
              </div>
            </div>

            <div className="route-cost-issues">
              <strong>{t("contracts.lng_economics.cash_legs")}</strong>
              <div className="lng-economics-table-wrap">
                <table className="lng-economics-table">
                  <caption>{t("contracts.lng_economics.cash_legs_caption")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("contracts.lng_economics.leg_id")}</th>
                      <th scope="col">{t("contracts.lng_economics.leg_category")}</th>
                      <th scope="col">{t("contracts.lng_economics.payment_date")}</th>
                      <th scope="col">{t("contracts.lng_economics.signed_amount")}</th>
                      <th scope="col">{t("contracts.lng_economics.cash_amount")}</th>
                      <th scope="col">{t("contracts.lng_economics.present_value")}</th>
                      <th scope="col">{t("contracts.lng_economics.discount_factor")}</th>
                      <th scope="col">{t("contracts.lng_economics.source_reference")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.cash_valuation.leg_valuations.map((leg) => (
                      <tr key={leg.leg_id}>
                        <td><code>{leg.leg_id}</code></td>
                        <td>{leg.category}</td>
                        <td>{leg.payment_date}</td>
                        <td>{leg.signed_amount} {leg.currency}</td>
                        <td>{leg.cash_amount_reporting_ccy} {result.reporting_currency}</td>
                        <td>{leg.present_value_reporting_ccy} {result.reporting_currency}</td>
                        <td>
                          <span>{leg.discount_factor}</span>
                          <small>{leg.discount_curve_reference}</small>
                          <small>{leg.discount_source_reference}</small>
                          <small>{leg.discount_as_of}</small>
                        </td>
                        <td><code>{leg.source_reference}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="route-cost-issues">
              <strong>{t("contracts.lng_economics.stage_chain")}</strong>
              <div className="lng-economics-table-wrap">
                <table className="lng-economics-table">
                  <caption>{t("contracts.lng_economics.stage_chain_caption")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("contracts.lng_economics.stage_id")}</th>
                      <th scope="col">{t("contracts.lng_economics.stage_kind")}</th>
                      <th scope="col">{t("contracts.lng_economics.stage_input")}</th>
                      <th scope="col">{t("contracts.lng_economics.stage_output")}</th>
                      <th scope="col">{t("contracts.lng_economics.stage_consumed")}</th>
                      <th scope="col">{t("contracts.lng_economics.stage_physical_loss")}</th>
                      <th scope="col">{t("contracts.lng_economics.stage_source_references")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.energy_balance.stages.map((stage) => (
                      <tr key={stage.stage_id}>
                        <td><code>{stage.stage_id}</code></td>
                        <td>{stage.kind}</td>
                        <td>{stage.input_energy_mwh} {result.energy_unit}</td>
                        <td>{stage.output_energy_mwh} {result.energy_unit}</td>
                        <td>{stage.consumed_energy_mwh} {result.energy_unit}</td>
                        <td>{stage.physical_loss_energy_mwh} {result.energy_unit}</td>
                        <td><code>{stage.source_references.join(", ")}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="route-cost-issues">
              <strong>{t("contracts.lng_economics.provenance")}</strong>
              {result.source_references.length > 0 ? (
                <ul>
                  {result.source_references.map((reference) => (
                    <li key={reference}><code>{reference}</code></li>
                  ))}
                </ul>
              ) : (
                <p>{unknown}</p>
              )}
              <strong>{t("contracts.lng_economics.lineage")}</strong>
              {result.lineage.length > 0 ? (
                <ul>
                  {result.lineage.map((item) => (
                    <li key={item}><code>{item}</code></li>
                  ))}
                </ul>
              ) : (
                <p>{unknown}</p>
              )}
            </div>

            <div className="route-cost-issues">
              <strong>{t("contracts.lng_economics.assumptions")}</strong>
              {result.assumptions.length > 0 ? (
                <ul>
                  {result.assumptions.map((assumption, index) => (
                    <li key={`assumption-${index}`}>{assumption}</li>
                  ))}
                </ul>
              ) : (
                <p>{unknown}</p>
              )}
            </div>

            <div className="route-cost-issues">
              <strong>{t("contracts.lng_economics.warnings")}</strong>
              {result.warnings.length > 0 ? (
                <ul>
                  {result.warnings.map((warning) => (
                    <li key={warning}><code>{warning}</code></li>
                  ))}
                </ul>
              ) : (
                <p>{t("contracts.lng_economics.no_warnings")}</p>
              )}
              {result.cash_valuation.warnings.length > 0 && (
                <>
                  <strong>{t("contracts.lng_economics.cash_warnings")}</strong>
                  <ul>
                    {result.cash_valuation.warnings.map((warning) => (
                      <li key={`cash-${warning}`}><code>{warning}</code></li>
                    ))}
                  </ul>
                </>
              )}
              {result.energy_balance.warnings.length > 0 && (
                <>
                  <strong>{t("contracts.lng_economics.energy_warnings")}</strong>
                  <ul>
                    {result.energy_balance.warnings.map((warning) => (
                      <li key={`energy-${warning}`}><code>{warning}</code></li>
                    ))}
                  </ul>
                </>
              )}
            </div>

            <div className="route-cost-issues">
              <strong>{t("contracts.lng_economics.envelope")}</strong>
              <div className="contract-definition-list">
                <div>
                  <span>{t("contracts.lng_economics.caller_supplied")}</span>
                  <strong>{booleanText(meta?.caller_supplied, unknown)}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.references_verified")}</span>
                  <strong>{booleanText(meta?.references_verified, unknown)}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.decision_context")}</span>
                  <strong>{optionalText(meta?.decision_context, unknown)}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.customer_approval")}</span>
                  <strong>{booleanText(meta?.customer_approval, unknown)}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.physical_readiness")}</span>
                  <strong>{optionalText(meta?.physical_readiness, unknown)}</strong>
                </div>
                <div>
                  <span>{t("contracts.lng_economics.readiness_assessed")}</span>
                  <strong>{booleanText(meta?.readiness_assessed, unknown)}</strong>
                </div>
              </div>
            </div>

            <p className="muted">{t("contracts.lng_economics.boundary_note")}</p>
          </div>
        )}
      </div>
    </section>
  );
}
