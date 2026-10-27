import { useEffect, useRef, type KeyboardEvent } from "react";

import { MetricStrip, PanelHeader } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  CAPACITY_BILLING_CURRENCIES,
  CAPACITY_BILLING_TARIFF_UNITS,
  type CapacityBillingDraft,
} from "@/app/model/capacityBillingModel";
import type { CapacityBillingController } from "@/app/model/useCapacityBilling";
import "./capacity-billing.css";

type Translate = (key: string) => string;

interface CapacityBillingPanelProps {
  readonly t: Translate;
  readonly capacityBilling: CapacityBillingController;
}

interface CapacityBillingShortcutEvent {
  readonly key: string;
  readonly ctrlKey: boolean;
  readonly metaKey: boolean;
  readonly altKey: boolean;
  readonly isComposing?: boolean;
}

/**
 * Ctrl+Enter is the panel's own submit chord, not a global shortcut. It stays inert while the
 * form is incomplete or a request is in flight, and it never steals the plain Enter/IME keys used
 * by the text fields.
 */
export function isCapacityBillingShortcut(event: CapacityBillingShortcutEvent): boolean {
  return (
    event.key === "Enter" &&
    event.ctrlKey &&
    !event.metaKey &&
    !event.altKey &&
    event.isComposing !== true
  );
}

function optionalText(value: string | null | undefined, unknown: string): string {
  return value === null || value === undefined || value === "" ? unknown : value;
}

function flagText(
  value: boolean | undefined,
  yes: string,
  no: string,
  unknown: string,
): string {
  if (value === true) return yes;
  if (value === false) return no;
  return unknown;
}

/**
 * The capacity-billing sandbox beside the route-cost what-if in the Routes task.
 *
 * `POST /api/research/capacity-billing` is the shared engine's exact wire adaptation. This panel
 * is a form and an exact readback, never a calculator:
 *
 * - every financial and physical field is text, transported as the caller typed it and rendered
 *   exactly as the backend returned it; there is no `Number`, rounding, conversion or annualising
 *   step;
 * - billed capacity energy is a required explicit input, because the engine checks it by integer
 *   cross-multiplication against booked capacity and the exact UTC duration. The form never infers
 *   it;
 * - the request carries no decision-context claim; the response's sandbox metadata and
 *   `NOT_ASSESSED` physical readiness are shown as the boundary, not summarised away;
 * - the previous result is not kept beside a changed draft, a pending run, a refusal or a
 *   transport failure.
 */
export function CapacityBillingPanel({ t, capacityBilling }: CapacityBillingPanelProps) {
  const { draft, updateDraft, readiness, busy, result, meta, refusal, error } = capacityBilling;
  const transportFailure = error ? presentError(t, describeFailure(error)) : null;
  const showResult = result !== null && !busy && !refusal && !error;
  const unknown = t("portfolio.capacity_billing.unknown");
  const resultRef = useRef<HTMLDivElement | null>(null);
  const previousResultRef = useRef(result);
  const submitHint = t(
    readiness.firstBlockerKey ?? "portfolio.capacity_billing.ready",
  );

  // A successful answer is the next thing an operator must read. Move focus to it after the
  // response commits, but not when the panel is first mounted with an older answer.
  useEffect(() => {
    const previousResult = previousResultRef.current;
    previousResultRef.current = result;
    if (!showResult || !result || previousResult === result) return;
    resultRef.current?.focus({ preventScroll: true });
    resultRef.current?.scrollIntoView({ block: "start" });
  }, [result, showResult]);

  function update(patch: Partial<CapacityBillingDraft>): void {
    updateDraft((current) => ({ ...current, ...patch }));
  }

  function handlePanelKeyDown(event: KeyboardEvent<HTMLElement>): void {
    if (!isCapacityBillingShortcut(event.nativeEvent)) return;
    // The chord belongs to this panel. Do not let a host-level Ctrl+Enter handler see it even
    // while the form is incomplete or busy.
    event.stopPropagation();
    if (busy || !readiness.canSubmit) return;
    event.preventDefault();
    void capacityBilling.run();
  }

  return (
    <section
      className="workspace-panel commercial-route-cost-panel capacity-billing-panel"
      aria-labelledby="capacity-billing-title"
      onKeyDown={handlePanelKeyDown}
    >
      <PanelHeader
        title={<span id="capacity-billing-title">{t("portfolio.capacity_billing.title")}</span>}
        meta={
          busy
            ? t("portfolio.capacity_billing.loading")
            : result
              ? `${t("portfolio.capacity_billing.model_version")}: ${result.model_version}`
              : t("portfolio.capacity_billing.not_run")
        }
      />
      <p className="panel-copy">{t("portfolio.capacity_billing.note")}</p>

      <div className="route-cost-issues" role="status">
        <strong>{t("portfolio.capacity_billing.sandbox_notice")}</strong>
        <p>{t("portfolio.capacity_billing.sandbox_detail")}</p>
      </div>

      <fieldset className="route-cost-identity capacity-billing-form" disabled={busy}>
        <legend className="visually-hidden">{t("portfolio.capacity_billing.title")}</legend>

        <div className="capacity-billing-form-grid">
          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-scenario-id">
              {t("portfolio.capacity_billing.scenario_id")}
            </label>
            <input
              id="capacity-billing-scenario-id"
              type="text"
              value={draft.scenarioId}
              maxLength={128}
              aria-required="true"
              onChange={(event) => update({ scenarioId: event.target.value })}
            />
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-tariff-id">
              {t("portfolio.capacity_billing.tariff_id")}
            </label>
            <input
              id="capacity-billing-tariff-id"
              type="text"
              value={draft.tariffId}
              maxLength={128}
              aria-required="true"
              onChange={(event) => update({ tariffId: event.target.value })}
            />
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-tariff-rate">
              {t("portfolio.capacity_billing.tariff_rate")}
            </label>
            <input
              id="capacity-billing-tariff-rate"
              type="text"
              inputMode="decimal"
              value={draft.tariffRate}
              maxLength={64}
              aria-required="true"
              aria-describedby="capacity-billing-unit-help"
              onChange={(event) => update({ tariffRate: event.target.value })}
            />
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-tariff-unit">
              {t("portfolio.capacity_billing.tariff_unit")}
            </label>
            <select
              id="capacity-billing-tariff-unit"
              value={draft.tariffUnit}
              aria-required="true"
              aria-describedby="capacity-billing-unit-help"
              onChange={(event) => update({ tariffUnit: event.target.value })}
            >
              <option value="">{t("portfolio.capacity_billing.select_placeholder")}</option>
              {CAPACITY_BILLING_TARIFF_UNITS.map((unit) => (
                <option key={unit} value={unit}>{unit}</option>
              ))}
            </select>
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-currency">
              {t("portfolio.capacity_billing.currency")}
            </label>
            <select
              id="capacity-billing-currency"
              value={draft.currency}
              aria-required="true"
              aria-describedby="capacity-billing-unit-help"
              onChange={(event) => update({ currency: event.target.value })}
            >
              <option value="">{t("portfolio.capacity_billing.select_placeholder")}</option>
              {CAPACITY_BILLING_CURRENCIES.map((currency) => (
                <option key={currency} value={currency}>{currency}</option>
              ))}
            </select>
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-booked">
              {t("portfolio.capacity_billing.booked_capacity")}
            </label>
            <input
              id="capacity-billing-booked"
              type="text"
              inputMode="decimal"
              value={draft.bookedCapacityMwhPerHour}
              maxLength={64}
              aria-required="true"
              onChange={(event) => update({ bookedCapacityMwhPerHour: event.target.value })}
            />
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-delivered">
              {t("portfolio.capacity_billing.delivered_energy")}
            </label>
            <input
              id="capacity-billing-delivered"
              type="text"
              inputMode="decimal"
              value={draft.deliveredEnergyMwh}
              maxLength={64}
              aria-required="true"
              onChange={(event) => update({ deliveredEnergyMwh: event.target.value })}
            />
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-billed">
              {t("portfolio.capacity_billing.billed_capacity")}
            </label>
            <input
              id="capacity-billing-billed"
              type="text"
              inputMode="decimal"
              value={draft.billedCapacityEnergyMwh}
              maxLength={64}
              aria-required="true"
              aria-describedby="capacity-billing-billed-help"
              onChange={(event) => update({ billedCapacityEnergyMwh: event.target.value })}
            />
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-start">
              {t("portfolio.capacity_billing.billing_start")}
            </label>
            <input
              id="capacity-billing-start"
              type="text"
              value={draft.billingStart}
              maxLength={64}
              aria-required="true"
              aria-describedby="capacity-billing-utc-help"
              onChange={(event) => update({ billingStart: event.target.value })}
            />
          </div>

          <div className="capacity-billing-field">
            <label className="field-label" htmlFor="capacity-billing-end">
              {t("portfolio.capacity_billing.billing_end")}
            </label>
            <input
              id="capacity-billing-end"
              type="text"
              value={draft.billingEnd}
              maxLength={64}
              aria-required="true"
              aria-describedby="capacity-billing-utc-help"
              onChange={(event) => update({ billingEnd: event.target.value })}
            />
          </div>

          <div className="capacity-billing-field capacity-billing-field--wide">
            <label className="field-label" htmlFor="capacity-billing-source-references">
              {t("portfolio.capacity_billing.source_references")}
            </label>
            <textarea
              id="capacity-billing-source-references"
              rows={3}
              value={draft.sourceReferences}
              aria-required="true"
              aria-describedby="capacity-billing-source-references-help"
              onChange={(event) => update({ sourceReferences: event.target.value })}
            />
          </div>
        </div>
      </fieldset>

      <ul className="route-cost-notes">
        <li id="capacity-billing-unit-help">{t("portfolio.capacity_billing.unit_help")}</li>
        <li id="capacity-billing-billed-help">{t("portfolio.capacity_billing.billed_help")}</li>
        <li id="capacity-billing-utc-help">{t("portfolio.capacity_billing.utc_help")}</li>
        <li id="capacity-billing-source-references-help">
          {t("portfolio.capacity_billing.source_references_help")}
        </li>
      </ul>

      <p className="muted">{t("portfolio.capacity_billing.required_note")}</p>

      {readiness.blockerKeys.length > 0 && (
        <div className="route-cost-issues" role="status">
          <strong>{t("portfolio.capacity_billing.required_fields")}</strong>
          <ul>
            {readiness.blockerKeys.map((key) => (
              <li key={key}>{t(key)}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="route-cost-component-actions">
        <button
          type="button"
          className="button"
          disabled={busy || !readiness.canSubmit}
          title={`${busy ? t("portfolio.capacity_billing.loading") : submitHint} (Ctrl+Enter)`}
          aria-keyshortcuts="Control+Enter"
          onClick={() => void capacityBilling.run()}
        >
          {busy
            ? t("portfolio.capacity_billing.loading")
            : t("portfolio.capacity_billing.calculate")}
        </button>
      </div>

      <div aria-live="polite" aria-busy={busy}>
        {busy && <p className="muted">{t("portfolio.capacity_billing.loading")}</p>}

        {refusal && (
          <div className="alert" role="alert">
            <strong>{t("portfolio.capacity_billing.refusal")}</strong>
            <p>{t("portfolio.capacity_billing.refusal_help")}</p>
            <p>
              <strong>{t("portfolio.capacity_billing.refusal_code")}:</strong>{" "}
              <code>{refusal.code || unknown}</code>{" "}
              <span className="muted">HTTP {refusal.status}</span>
            </p>
            {refusal.message && <p>{refusal.message}</p>}
            {refusal.violations.length > 0 && (
              <div className="route-cost-issues">
                <strong>{t("portfolio.capacity_billing.refusal_violations")}</strong>
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
            <p className="muted">{t("portfolio.capacity_billing.transport_error_help")}</p>
          </div>
        )}

        {showResult && result && (
          <div
            className="route-cost-result capacity-billing-result"
            ref={resultRef}
            tabIndex={-1}
            role="region"
            aria-labelledby="capacity-billing-result-label"
          >
            <div className="section-heading">
              <span className="eyebrow" id="capacity-billing-result-label">
                {t("portfolio.capacity_billing.result")}
              </span>
              <strong>{result.model_version}</strong>
            </div>
            <p className="muted">{t("portfolio.capacity_billing.result_exact")}</p>

            <MetricStrip
              className="metric-grid three-column capacity-billing-metrics"
              items={[
                {
                  label: t("portfolio.capacity_billing.total_cost"),
                  value: (
                    <span className="capacity-billing-metric-amount">{result.total_cost}</span>
                  ),
                  unit: result.currency,
                },
                {
                  label: t("portfolio.capacity_billing.cost_per_delivered"),
                  value: (
                    <span className="capacity-billing-metric-amount">
                      {result.cost_per_delivered_mwh}
                    </span>
                  ),
                  unit: `${result.currency}/MWh`,
                },
                {
                  label: t("portfolio.capacity_billing.duration_microseconds"),
                  value: (
                    <span className="capacity-billing-metric-amount">
                      {String(result.duration_microseconds)}
                    </span>
                  ),
                  unit: t("portfolio.capacity_billing.microseconds_unit"),
                },
              ]}
            />

            <div className="route-cost-issues">
              <strong>{t("portfolio.capacity_billing.result_basis")}</strong>
              <ul className="capacity-billing-facts">
                <li>
                  <strong>{t("portfolio.capacity_billing.scenario_id")}:</strong>{" "}
                  {result.scenario_id}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.tariff_id")}:</strong>{" "}
                  {result.tariff_id}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.tariff")}:</strong>{" "}
                  {`${result.tariff_rate} ${result.tariff_unit}`}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.tariff_unit")}:</strong>{" "}
                  {result.tariff_unit}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.currency")}:</strong> {result.currency}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.booked_capacity_result")}:</strong>{" "}
                  {`${result.booked_capacity_mwh_per_h} MWh/h`}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.billed_capacity_result")}:</strong>{" "}
                  {`${result.billed_capacity_energy_mwh} MWh`}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.delivered_energy_result")}:</strong>{" "}
                  {`${result.delivered_energy_mwh} MWh`}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.billing_start")}:</strong>{" "}
                  {result.billing_start}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.billing_end")}:</strong>{" "}
                  {result.billing_end}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.duration_hours")}:</strong>{" "}
                  {`${result.duration_hours} h`}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.physical_readiness")}:</strong>{" "}
                  {optionalText(result.physical_readiness, unknown)}
                </li>
              </ul>
            </div>

            <div className="route-cost-issues">
              <strong>{t("portfolio.capacity_billing.envelope")}</strong>
              <ul className="capacity-billing-facts">
                <li>
                  <strong>{t("portfolio.capacity_billing.caller_supplied")}:</strong>{" "}
                  {flagText(
                    meta?.caller_supplied,
                    t("portfolio.capacity_billing.yes"),
                    t("portfolio.capacity_billing.no"),
                    unknown,
                  )}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.references_verified")}:</strong>{" "}
                  {flagText(
                    meta?.references_verified,
                    t("portfolio.capacity_billing.yes"),
                    t("portfolio.capacity_billing.not_verified"),
                    unknown,
                  )}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.booked_rights")}:</strong>{" "}
                  {flagText(
                    meta?.booked_rights_established,
                    t("portfolio.capacity_billing.established"),
                    t("portfolio.capacity_billing.not_established"),
                    unknown,
                  )}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.physical_readiness")}:</strong>{" "}
                  {optionalText(meta?.physical_readiness, unknown)}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.decision_context")}:</strong>{" "}
                  {optionalText(meta?.decision_context, unknown)}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.customer_approval")}:</strong>{" "}
                  {flagText(
                    meta?.customer_approval,
                    t("portfolio.capacity_billing.yes"),
                    t("portfolio.capacity_billing.no"),
                    unknown,
                  )}
                </li>
                <li>
                  <strong>{t("portfolio.capacity_billing.model_version")}:</strong>{" "}
                  {result.model_version}
                </li>
              </ul>
            </div>

            <div className="route-cost-issues">
              <strong>{t("portfolio.capacity_billing.source_references")}</strong>
              {result.source_references.length > 0 ? (
                <ul>
                  {result.source_references.map((reference) => (
                    <li key={reference}><code>{reference}</code></li>
                  ))}
                </ul>
              ) : (
                <p>{unknown}</p>
              )}
            </div>

            <div className="route-cost-issues">
              <strong>{t("portfolio.capacity_billing.assumptions")}</strong>
              {result.assumptions.length > 0 ? (
                <ul>
                  {result.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              ) : (
                <p>{unknown}</p>
              )}
            </div>

            <div className="route-cost-issues">
              <strong>{t("portfolio.capacity_billing.warnings")}</strong>
              {result.warnings.length > 0 ? (
                <ul>
                  {result.warnings.map((warning) => (
                    <li key={warning}><code>{warning}</code></li>
                  ))}
                </ul>
              ) : (
                <p>{t("portfolio.capacity_billing.no_warnings")}</p>
              )}
            </div>

            <p className="muted">{t("portfolio.capacity_billing.duration_note")}</p>
          </div>
        )}
      </div>
    </section>
  );
}
