import { PanelHeader } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  ROUTE_COST_COMPONENT_TYPES,
  ROUTE_COST_MAX_COMPONENTS,
  emptyRouteCostComponent,
  netbackReadiness,
  outcomeIsPartial,
  outcomeSources,
  routeCostReadiness,
  type RouteCostComponentDraft,
  type RouteCostDraft,
} from "@/app/model/routeCostModel";
import type { RouteCandidateDTO } from "@/api/client";
import type { RouteCostWhatIf } from "@/app/model/useRouteCostWhatIf";

type Translate = (key: string) => string;

interface RouteCostWhatIfPanelProps {
  readonly t: Translate;
  readonly whatIf: RouteCostWhatIf;
  /** The route the user has selected, so the form starts on the route they are looking at. */
  readonly route: RouteCandidateDTO | null;
  readonly onUseSelectedRoute: () => void;
}

function componentTypeLabel(t: Translate, componentType: string): string {
  return t(`portfolio.route_cost.component.${componentType}`);
}

/**
 * Cost a route and value its indicative netback (slice D of the D3 decision).
 *
 * `POST /api/research/route-cost` and `POST /api/research/netback` had no consumer. Both are
 * deterministic engines over the caller's own numbers, and the surface's job is to say exactly
 * that: the figures are the caller's inputs (`source_references: ["operator-input"]`), the result
 * carries the assumptions it rests on, the inputs it lacked and its warnings, and its as-of is the
 * instant the engine generated it.
 *
 * The panel configures and reports; the workspace header starts the run, because a `compute`
 * belongs in the primary slot. Three refusals are deliberate:
 *
 * - the client does no arithmetic. The netback body carries the cost the engine returned, so the
 *   two figures cannot disagree about the same number;
 * - a run the engines will report as incomplete is not hidden: their own caveats are listed before
 *   the click as well as after it;
 * - a partial result says so. `human_review_required`, the missing inputs and the warnings are
 *   rendered from the payload rather than summarised away.
 */
export function RouteCostWhatIfPanel({
  t,
  whatIf,
  route,
  onUseSelectedRoute,
}: RouteCostWhatIfPanelProps) {
  const { draft, updateDraft, readiness, cost, netback, error, busy } = whatIf;
  const failure = error ? presentError(t, describeFailure(error)) : null;
  const netbackState = netbackReadiness(draft, cost ? cost.total_cost_eur_mwh : null);
  const costPartial = outcomeIsPartial(cost);
  const netbackPartial = outcomeIsPartial(netback);

  function updateComponent(index: number, patch: Partial<RouteCostComponentDraft>): void {
    updateDraft((current: RouteCostDraft) => ({
      ...current,
      components: current.components.map((component, position) =>
        position === index ? { ...component, ...patch } : component,
      ),
    }));
  }

  return (
    <section className="workspace-panel commercial-route-cost-panel" aria-label={t("portfolio.route_cost.title")}>
      <PanelHeader
        title={t("portfolio.route_cost.title")}
        meta={
          cost
            ? `${t("portfolio.route_cost.as_of")}: ${cost.generated_at_utc}`
            : t("portfolio.route_cost.not_run")
        }
      />
      <p className="panel-copy">{t("portfolio.route_cost.note")}</p>

      <div className="route-cost-identity">
        <label className="field-label" htmlFor="route-cost-name">
          {t("portfolio.route_cost.route_name")}
        </label>
        <input
          id="route-cost-name"
          type="text"
          value={draft.routeName}
          maxLength={120}
          onChange={(event) =>
            updateDraft((current) => ({ ...current, routeName: event.target.value }))
          }
        />
        <button type="button" disabled={!route} onClick={onUseSelectedRoute}>
          {t("portfolio.route_cost.use_selected_route")}
        </button>
        <label className="field-label" htmlFor="route-cost-from">
          {t("portfolio.route_cost.from_node")}
        </label>
        <input
          id="route-cost-from"
          type="text"
          value={draft.fromNodeId}
          maxLength={120}
          onChange={(event) =>
            updateDraft((current) => ({ ...current, fromNodeId: event.target.value }))
          }
        />
        <label className="field-label" htmlFor="route-cost-to">
          {t("portfolio.route_cost.to_node")}
        </label>
        <input
          id="route-cost-to"
          type="text"
          value={draft.toNodeId}
          maxLength={120}
          onChange={(event) =>
            updateDraft((current) => ({ ...current, toNodeId: event.target.value }))
          }
        />
        <label className="field-label" htmlFor="route-cost-km">
          {t("portfolio.route_cost.route_km")}
        </label>
        <input
          id="route-cost-km"
          type="text"
          inputMode="decimal"
          value={draft.routeKm}
          onChange={(event) =>
            updateDraft((current) => ({ ...current, routeKm: event.target.value }))
          }
        />
      </div>

      <div className="route-cost-components">
        <div className="section-heading">
          <span className="eyebrow">{t("portfolio.route_cost.components")}</span>
          <strong>{draft.components.length}</strong>
        </div>
        <div className="data-table route-cost-component-table" tabIndex={0}>
          <div className="data-table-row header five">
            <span>{t("portfolio.route_cost.component_type")}</span>
            <span>{t("portfolio.route_cost.amount")}</span>
            <span>{t("portfolio.route_cost.unit")}</span>
            <span>{t("portfolio.route_cost.currency")}</span>
            <span>{t("portfolio.route_cost.description")}</span>
          </div>
          {draft.components.map((component, index) => (
            <div key={`component-${index}`} className="data-table-row five">
              <select
                aria-label={t("portfolio.route_cost.component_type")}
                value={component.componentType}
                onChange={(event) => updateComponent(index, { componentType: event.target.value })}
              >
                {ROUTE_COST_COMPONENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {componentTypeLabel(t, type)}
                  </option>
                ))}
              </select>
              <input
                aria-label={t("portfolio.route_cost.amount")}
                type="text"
                inputMode="decimal"
                value={component.amount}
                onChange={(event) => updateComponent(index, { amount: event.target.value })}
              />
              <input
                aria-label={t("portfolio.route_cost.unit")}
                type="text"
                value={component.unit}
                maxLength={24}
                onChange={(event) => updateComponent(index, { unit: event.target.value })}
              />
              <input
                aria-label={t("portfolio.route_cost.currency")}
                type="text"
                value={component.currency}
                maxLength={8}
                onChange={(event) => updateComponent(index, { currency: event.target.value })}
              />
              <input
                aria-label={t("portfolio.route_cost.description")}
                type="text"
                value={component.description}
                maxLength={120}
                onChange={(event) => updateComponent(index, { description: event.target.value })}
              />
            </div>
          ))}
        </div>
        <div className="route-cost-component-actions">
          <button
            type="button"
            disabled={draft.components.length >= ROUTE_COST_MAX_COMPONENTS}
            onClick={() =>
              updateDraft((current) => ({
                ...current,
                components: [...current.components, emptyRouteCostComponent()],
              }))
            }
          >
            {t("portfolio.route_cost.add_component")}
          </button>
          <button
            type="button"
            disabled={draft.components.length <= 1}
            onClick={() =>
              updateDraft((current) => ({
                ...current,
                components: current.components.slice(0, -1),
              }))
            }
          >
            {t("portfolio.route_cost.remove_component")}
          </button>
        </div>
      </div>

      <div className="route-cost-netback-inputs">
        <div className="section-heading">
          <span className="eyebrow">{t("portfolio.route_cost.netback_inputs")}</span>
        </div>
        <label className="field-label" htmlFor="route-cost-market">
          {t("portfolio.route_cost.to_market")}
        </label>
        <input
          id="route-cost-market"
          type="text"
          value={draft.toMarket}
          maxLength={120}
          onChange={(event) =>
            updateDraft((current) => ({ ...current, toMarket: event.target.value }))
          }
        />
        <label className="field-label" htmlFor="route-cost-price">
          {t("portfolio.route_cost.market_price")}
        </label>
        <input
          id="route-cost-price"
          type="text"
          inputMode="decimal"
          value={draft.marketPriceEurMwh}
          onChange={(event) =>
            updateDraft((current) => ({ ...current, marketPriceEurMwh: event.target.value }))
          }
        />
        <label className="field-label" htmlFor="route-cost-fx">
          {t("portfolio.route_cost.fx_rate")}
        </label>
        <input
          id="route-cost-fx"
          type="text"
          inputMode="decimal"
          value={draft.fxRate}
          onChange={(event) =>
            updateDraft((current) => ({ ...current, fxRate: event.target.value }))
          }
        />
        <label className="field-label" htmlFor="route-cost-fx-pair">
          {t("portfolio.route_cost.fx_pair")}
        </label>
        <input
          id="route-cost-fx-pair"
          type="text"
          value={draft.fxPair}
          maxLength={24}
          onChange={(event) =>
            updateDraft((current) => ({ ...current, fxPair: event.target.value }))
          }
        />
        {/* The netback is part of the same run. This states whether that half will run, rather
            than offering a second control for it. */}
        <p className="muted">
          {netbackState.canCompute
            ? t("portfolio.route_cost.netback_will_run")
            : t(netbackState.firstBlockerKey ?? "portfolio.route_cost.blocker.cost_required")}
        </p>
      </div>

      {readiness.noteKeys.length > 0 && (
        <ul className="route-cost-notes">
          {readiness.noteKeys.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ul>
      )}
      {readiness.firstBlockerKey && (
        <p className="strategy-error">{t(readiness.firstBlockerKey)}</p>
      )}
      {busy && <p className="muted">{t("status.loading")}</p>}
      {failure && (
        <div className="alert">
          <strong>{failure.title}</strong>
          <p>{failure.action}</p>
        </div>
      )}

      {cost && (
        <div className="route-cost-result">
          <div className="section-heading">
            <span className="eyebrow">{t("portfolio.route_cost.result")}</span>
            <strong>
              {cost.total_cost_eur_mwh.toLocaleString()} EUR/MWh
            </strong>
          </div>
          <div className="metric-grid three-column">
            <div>
              <span>{t("portfolio.route_cost.total_cost")}</span>
              <strong>{cost.total_cost_eur_mwh.toLocaleString()} EUR/MWh</strong>
            </div>
            <div>
              <span>{t("portfolio.route_cost.total_boe")}</span>
              <strong>{cost.total_cost_boe.toLocaleString()} EUR/boe</strong>
            </div>
            <div>
              <span>{t("portfolio.route_cost.components_used")}</span>
              <strong>{cost.components.length}</strong>
            </div>
          </div>
          <p className="muted">
            {t("portfolio.route_cost.provenance")}: {outcomeSources(cost).join(", ") || t("data.unavailable")}
          </p>
          {costPartial && <p className="strategy-error">{t("portfolio.route_cost.partial")}</p>}
          {cost.missing_inputs.length > 0 && (
            <div className="route-cost-issues">
              <strong>{t("portfolio.route_cost.missing_inputs")}</strong>
              <ul>
                {cost.missing_inputs.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {cost.warnings.length > 0 && (
            <div className="route-cost-issues">
              <strong>{t("portfolio.route_cost.warnings")}</strong>
              <ul>
                {cost.warnings.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {cost.assumptions.length > 0 && (
            <div className="route-cost-issues">
              <strong>{t("portfolio.route_cost.assumptions")}</strong>
              <ul>
                {cost.assumptions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {netback && (
        <div className="route-cost-result">
          <div className="section-heading">
            <span className="eyebrow">{t("portfolio.route_cost.netback_result")}</span>
            <strong>{netback.netback_eur_mwh.toLocaleString()} EUR/MWh</strong>
          </div>
          <div className="metric-grid three-column">
            <div>
              <span>{t("portfolio.route_cost.netback")}</span>
              <strong>{netback.netback_eur_mwh.toLocaleString()} EUR/MWh</strong>
            </div>
            <div>
              <span>{t("portfolio.route_cost.netback_local")}</span>
              <strong>{netback.netback_local_mwh.toLocaleString()} EUR/MWh</strong>
            </div>
            <div>
              <span>{t("portfolio.route_cost.route_cost_used")}</span>
              <strong>{netback.route_cost_eur_mwh.toLocaleString()} EUR/MWh</strong>
            </div>
          </div>
          <p className="muted">
            {t("portfolio.route_cost.as_of")}: {netback.generated_at_utc} ·{" "}
            {t("portfolio.route_cost.provenance")}:{" "}
            {outcomeSources(netback).join(", ") || t("data.unavailable")}
          </p>
          {netbackPartial && <p className="strategy-error">{t("portfolio.route_cost.partial")}</p>}
          {netback.warnings.length > 0 && (
            <div className="route-cost-issues">
              <strong>{t("portfolio.route_cost.warnings")}</strong>
              <ul>
                {netback.warnings.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {netback.assumptions.length > 0 && (
            <div className="route-cost-issues">
              <strong>{t("portfolio.route_cost.assumptions")}</strong>
              <ul>
                {netback.assumptions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
