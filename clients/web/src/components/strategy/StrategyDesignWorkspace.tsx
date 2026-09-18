/**
 * Strategy design panel (Architecture V2 Wave 9, action geography).
 *
 * This panel renders the draft the workspace owns and reports the validation verdict it is handed.
 * Saving is the workspace's primary action - a `persist` consequence belongs there, not among the
 * form's own controls - so what stays here are the two `lifecycle` acts: freezing a version and
 * forking one. The geography keeps those bounded next to the version they change, and
 * `requiresDeliberateStep` says neither may be promoted to the primary slot.
 */

import type { StrategyLabController } from "@/app/model/useStrategyLab";
import type { StrategyDesignDraft } from "@/app/model/useStrategyDesignDraft";

type Translate = (key: string) => string;

interface StrategyDesignWorkspaceProps {
  controller: StrategyLabController;
  /** The draft and its rule, owned by the workspace that hosts the save action. */
  draft: StrategyDesignDraft;
  t: Translate;
}

export function StrategyDesignWorkspace({
  controller,
  draft,
  t,
}: StrategyDesignWorkspaceProps) {
  // Everything about *what would be written* belongs to the workspace that hosts the save action;
  // this panel renders it and reports the verdict it was handed.
  const { form, setField: set, validation } = draft;
  const { frozen, busy, message, error } = draft;
  const version = controller.selectedVersion;

  return (
    <div className="strategy-design">
      <div className="strategy-validation-summary">
        <span>{t("strategy_lab.validation")}</span>
        <span className="status-badge status-blocked">{validation.blockerKeys.length} {t("strategy_lab.blockers")}</span>
        <span className="status-badge status-warning">{validation.warningKeys.length} {t("strategy_lab.warnings")}</span>
        <div className="strategy-validation-list">
          {validation.blockerKeys.map((key) => <div key={key}>BLOCKER: {t(key)}</div>)}
          {validation.warningKeys.map((key) => <div key={key}>WARNING: {t(key)}</div>)}
        </div>
      </div>
      <section className="workspace-panel">
        <h2>{t("strategy_lab.hypothesis")}</h2>
        <label>
          {t("strategy_lab.name")}
          <input value={form.name} disabled={frozen} onChange={(event) => set("name", event.target.value)} />
        </label>
        <label>
          {t("strategy_lab.description")}
          <input value={form.description} disabled={frozen} onChange={(event) => set("description", event.target.value)} />
        </label>
        <label>
          {t("strategy_lab.thesis")}
          <textarea value={form.hypothesis} disabled={frozen} onChange={(event) => set("hypothesis", event.target.value)} />
        </label>
      </section>
      <section className="workspace-panel">
        <h2>{t("strategy_lab.component")} · OCM_VS_DAY_AHEAD</h2>
        <div className="strategy-form-grid">
          <label>{t("strategy_lab.hubs")}<input value={form.hubs} disabled={frozen} onChange={(event) => set("hubs", event.target.value)} /></label>
          <label>{t("strategy_lab.day_ahead_names")}<input value={form.dayAheadNames} disabled={frozen} onChange={(event) => set("dayAheadNames", event.target.value)} /></label>
          <label>{t("strategy_lab.intraday_names")}<input value={form.intradayNames} disabled={frozen} onChange={(event) => set("intradayNames", event.target.value)} /></label>
          <label>{t("strategy_lab.weight")}<input type="number" step="0.1" value={form.weight} disabled={frozen} onChange={(event) => set("weight", event.target.value)} /></label>
          <label>{t("strategy_lab.positive_threshold")}<input type="number" step="0.1" value={form.positiveThreshold} disabled={frozen} onChange={(event) => set("positiveThreshold", event.target.value)} /></label>
          <label>{t("strategy_lab.negative_threshold")}<input type="number" step="0.1" value={form.negativeThreshold} disabled={frozen} onChange={(event) => set("negativeThreshold", event.target.value)} /></label>
          <label>{t("strategy_lab.window_start")}<input value={form.windowStart} disabled={frozen} onChange={(event) => set("windowStart", event.target.value)} /></label>
          <label>{t("strategy_lab.window_end")}<input value={form.windowEnd} disabled={frozen} onChange={(event) => set("windowEnd", event.target.value)} /></label>
          <label>{t("strategy_lab.bar_minutes")}<input type="number" value={form.barMinutes} disabled={frozen} onChange={(event) => set("barMinutes", event.target.value)} /></label>
        </div>
      </section>
      <section className="workspace-panel">
        <h2>{t("strategy_lab.resource_scope")}</h2>
        <div className="strategy-form-grid">
          <label>{t("strategy_lab.resource_id")}<input value={form.resourceId} disabled={frozen} onChange={(event) => set("resourceId", event.target.value)} /></label>
          <label>{t("strategy_lab.resource_name")}<input value={form.resourceName} disabled={frozen} onChange={(event) => set("resourceName", event.target.value)} /></label>
          <label>{t("strategy_lab.resource_quantity")}<input type="number" value={form.resourceQuantity} disabled={frozen} onChange={(event) => set("resourceQuantity", event.target.value)} /></label>
          <label>{t("strategy_lab.resource_cost")}<input type="number" value={form.resourceCost} disabled={frozen} onChange={(event) => set("resourceCost", event.target.value)} /></label>
        </div>
      </section>
      <section className="workspace-panel">
        <h2>{t("strategy_lab.risk_controls")}</h2>
        <div className="strategy-form-grid">
          <label>{t("strategy_lab.max_ocm")} %<input type="number" value={form.maxOcm} disabled={frozen} onChange={(event) => set("maxOcm", event.target.value)} /></label>
          <label>{t("strategy_lab.min_day_ahead")} %<input type="number" value={form.minDayAhead} disabled={frozen} onChange={(event) => set("minDayAhead", event.target.value)} /></label>
          <label className="strategy-checkbox">
            <input type="checkbox" checked={form.requireTsoAccess} disabled={frozen} onChange={(event) => set("requireTsoAccess", event.target.checked)} />
            {t("strategy_lab.require_tso_access")}
          </label>
        </div>
      </section>
      <section className="workspace-panel">
        <h2>{t("strategy_lab.assumptions")}</h2>
        <div className="strategy-form-grid">
          <label>{t("strategy_lab.fill_price_policy")}
            <select value={form.fillPricePolicy} disabled={frozen} onChange={(event) => set("fillPricePolicy", event.target.value)}>
              <option>NEXT_ELIGIBLE</option><option>MID</option><option>BID</option><option>ASK</option><option>LAST</option><option>ASSESSMENT</option>
            </select>
          </label>
          <label>{t("strategy_lab.missing_data_policy")}
            <select value={form.missingDataPolicy} disabled={frozen} onChange={(event) => set("missingDataPolicy", event.target.value)}>
              <option>FAIL</option><option>SKIP_DECISION</option><option>CARRY_FORWARD_WITH_MAX_AGE</option><option>USE_APPROVED_FALLBACK_SOURCE</option>
            </select>
          </label>
          <label>{t("strategy_lab.transaction_cost_treatment")}
            <select value={form.transactionCostTreatment} disabled={frozen} onChange={(event) => set("transactionCostTreatment", event.target.value)}>
              <option>UNAVAILABLE</option><option>MODELED_COST</option><option>EXCLUDED</option>
            </select>
          </label>
          <label>{t("strategy_lab.transaction_cost")} GBP/MWh<input type="number" step="0.01" value={form.transactionCost} disabled={frozen} onChange={(event) => set("transactionCost", event.target.value)} /></label>
          <label>{t("strategy_lab.slippage_treatment")}
            <select value={form.slippageTreatment} disabled={frozen} onChange={(event) => set("slippageTreatment", event.target.value)}>
              <option>UNAVAILABLE</option><option>MODELED_COST</option><option>EXCLUDED</option>
            </select>
          </label>
          <label>{t("strategy_lab.slippage")} GBP/MWh<input type="number" step="0.01" value={form.slippage} disabled={frozen} onChange={(event) => set("slippage", event.target.value)} /></label>
        </div>
      </section>
      {/* Saving the draft is the workspace's primary action. What remains here changes a version's
          standing, so it is bounded next to the version it affects rather than promoted: the
          geography keeps `lifecycle` consequences out of the primary slot because neither is
          reversible from the surface that triggers it. */}
      <section className="strategy-version-actions" aria-label={t("strategy_lab.version_actions")}>
        <span className="eyebrow">{t("strategy_lab.version_actions")}</span>
        <p className="panel-copy">{t("strategy_lab.version_actions_note")}</p>
        <div className="strategy-design-actions">
          {frozen && (
            <button type="button" disabled={busy} onClick={() => void draft.createNewVersion()}>
              {t("strategy_lab.create_new_version")}
            </button>
          )}
          {version?.status === "DRAFT" && (
            <button type="button" disabled={busy} onClick={() => void draft.freezeVersion()}>
              {t("strategy_lab.freeze_version")}
            </button>
          )}
        </div>
      </section>
      {message && <p className="muted">{t("strategy_lab.saved")}: {message}</p>}
      {error && <p className="strategy-error">{error}</p>}
    </div>
  );
}
