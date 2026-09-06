import { useEffect, useMemo, useState } from "react";
import { api as apiClient } from "@/api/client";
import type { StrategyLabController, StrategyLabSelection } from "@/app/model/useStrategyLab";

type Translate = (key: string) => string;

interface StrategyDesignWorkspaceProps {
  controller: StrategyLabController;
  selection: StrategyLabSelection;
  t: Translate;
}

interface DesignFormState {
  name: string;
  description: string;
  hypothesis: string;
  hubs: string;
  dayAheadNames: string;
  intradayNames: string;
  weight: string;
  positiveThreshold: string;
  negativeThreshold: string;
  windowStart: string;
  windowEnd: string;
  barMinutes: string;
  maxOcm: string;
  minDayAhead: string;
  requireTsoAccess: boolean;
  fillPricePolicy: string;
  missingDataPolicy: string;
  transactionCostTreatment: string;
  transactionCost: string;
  slippageTreatment: string;
  slippage: string;
  resourceId: string;
  resourceName: string;
  resourceQuantity: string;
  resourceCost: string;
}

const DEFAULT_FORM: DesignFormState = {
  name: "",
  description: "",
  hypothesis: "",
  hubs: "NBP",
  dayAheadNames: "SAP",
  intradayNames: "ICE_OCM",
  weight: "1.0",
  positiveThreshold: "0.0",
  negativeThreshold: "0.0",
  windowStart: "05:00",
  windowEnd: "05:30",
  barMinutes: "5",
  maxOcm: "80.0",
  minDayAhead: "10.0",
  requireTsoAccess: false,
  fillPricePolicy: "NEXT_ELIGIBLE",
  missingDataPolicy: "FAIL",
  transactionCostTreatment: "UNAVAILABLE",
  transactionCost: "",
  slippageTreatment: "UNAVAILABLE",
  slippage: "",
  resourceId: "res-1",
  resourceName: "Resource 1",
  resourceQuantity: "100",
  resourceCost: "20",
};

function formFromVersion(definition: Record<string, unknown> | undefined): DesignFormState {
  if (!definition) return DEFAULT_FORM;
  const component = Array.isArray(definition.components)
    ? (definition.components[0] as Record<string, unknown>)
    : null;
  const extension = (component?.extension_json as Record<string, unknown>) ?? {};
  const risk = (definition.risk_controls as Record<string, unknown>) ?? {};
  const resources = Array.isArray(definition.resource_contexts)
    ? (definition.resource_contexts[0] as Record<string, unknown>)
    : null;
  return {
    ...DEFAULT_FORM,
    name: String(definition.strategy_name ?? ""),
    hypothesis: String(definition.hypothesis ?? ""),
    hubs: Array.isArray(component?.hubs)
      ? (component?.hubs as string[]).join(", ")
      : "NBP",
    dayAheadNames: Array.isArray(extension.day_ahead_price_names)
      ? (extension.day_ahead_price_names as string[]).join(", ")
      : "SAP",
    intradayNames: Array.isArray(extension.intraday_price_names)
      ? (extension.intraday_price_names as string[]).join(", ")
      : "ICE_OCM",
    weight: String(extension.weight ?? 1.0),
    positiveThreshold: String(extension.positive_spread_threshold_gbp_mwh ?? 0.0),
    negativeThreshold: String(extension.negative_spread_threshold_gbp_mwh ?? 0.0),
    windowStart: String(extension.time_window_start ?? "05:00"),
    windowEnd: String(extension.time_window_end ?? "05:30"),
    barMinutes: String(extension.target_bar_minutes ?? 5),
    maxOcm: String(risk.max_ocm_allocation_pct ?? 80.0),
    minDayAhead: String(risk.min_day_ahead_allocation_pct ?? 10.0),
    requireTsoAccess: Boolean(risk.require_tso_access),
    resourceId: String(resources?.resource_id ?? "res-1"),
    resourceName: String(resources?.resource_name ?? "Resource 1"),
    resourceQuantity: String(resources?.available_quantity_mwh_per_day ?? "100"),
    resourceCost: String(resources?.all_in_cost_gbp_mwh ?? "20"),
  };
}

function csv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function numberValue(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function StrategyDesignWorkspace({
  controller,
  selection,
  t,
}: StrategyDesignWorkspaceProps) {
  const [form, setForm] = useState<DesignFormState>(DEFAULT_FORM);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const version = controller.selectedVersion;
  const frozen = version?.status === "FROZEN";

  useEffect(() => {
    setForm(formFromVersion(version?.definition_json));
  }, [version?.definition_json, version?.strategy_version_id]);

  const set = (key: keyof DesignFormState, value: string | boolean) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const validation = useMemo(() => {
    const blockers: string[] = [];
    const warnings: string[] = [];
    if (!form.name.trim()) blockers.push(t("strategy_lab.blocker.name"));
    if (csv(form.dayAheadNames).length === 0) blockers.push(t("strategy_lab.blocker.day_ahead"));
    if (csv(form.intradayNames).length === 0) blockers.push(t("strategy_lab.blocker.intraday"));
    const quantity = numberValue(form.resourceQuantity);
    const cost = numberValue(form.resourceCost);
    if (quantity === null || quantity <= 0 || cost === null || cost <= 0) {
      blockers.push(t("strategy_lab.blocker.resource"));
    }
    if (form.transactionCostTreatment === "MODELED_COST" && numberValue(form.transactionCost) === null) {
      blockers.push(t("strategy_lab.blocker.transaction_cost"));
    }
    if (form.transactionCostTreatment === "UNAVAILABLE") {
      warnings.push(t("strategy_lab.warning.transaction_cost_unavailable"));
    }
    if (form.missingDataPolicy === "CARRY_FORWARD_WITH_MAX_AGE") {
      warnings.push(t("strategy_lab.warning.carry_forward"));
    }
    return { blockers, warnings };
  }, [form, t]);

  const buildBody = () => ({
    hypothesis: form.hypothesis,
    definition: {
      components: [
        {
          component_id: "ocm-da-1",
          component_type: "OCM_VS_DAY_AHEAD",
          hubs: csv(form.hubs),
          tenors: ["within-day", "day-ahead"],
          extension_json: {
            weight: numberValue(form.weight) ?? 1.0,
            day_ahead_price_names: csv(form.dayAheadNames),
            intraday_price_names: csv(form.intradayNames),
            positive_spread_threshold_gbp_mwh: numberValue(form.positiveThreshold) ?? 0,
            negative_spread_threshold_gbp_mwh: numberValue(form.negativeThreshold) ?? 0,
            time_window_start: form.windowStart || null,
            time_window_end: form.windowEnd || null,
            target_bar_minutes: numberValue(form.barMinutes) ?? 5,
          },
        },
      ],
      parameter_definitions: [],
      parameter_values: {},
      risk_controls: {
        max_ocm_allocation_pct: numberValue(form.maxOcm) ?? 80,
        min_day_ahead_allocation_pct: numberValue(form.minDayAhead) ?? 10,
        require_tso_access: form.requireTsoAccess,
      },
      economic_assumptions: {
        fill_price_policy: form.fillPricePolicy,
        missing_data_policy: form.missingDataPolicy,
        cost_components: [
          {
            code: "TRANSACTION_COST",
            treatment: form.transactionCostTreatment,
            amount_gbp_mwh:
              form.transactionCostTreatment === "MODELED_COST"
                ? numberValue(form.transactionCost)
                : null,
          },
          {
            code: "SLIPPAGE",
            treatment: form.slippageTreatment,
            amount_gbp_mwh:
              form.slippageTreatment === "MODELED_COST"
                ? numberValue(form.slippage)
                : null,
          },
        ],
      },
      data_requirements: { hubs: csv(form.hubs) },
      evaluation_windows: [],
    },
    strategy_name: form.name,
    run_mode: "BACKTEST",
    resource_contexts: [
      {
        resource_id: form.resourceId,
        resource_name: form.resourceName,
        available_quantity_mwh_per_day: numberValue(form.resourceQuantity) ?? 100,
        all_in_cost_gbp_mwh: numberValue(form.resourceCost) ?? 20,
        required_tso_access: [],
      },
    ],
    price_observations: [],
    existing_shadow_pnl_gbp: 0,
  });

  const saveDraft = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const body = buildBody();
      if (!controller.selectedStrategy) {
        const strategyName = form.name.trim() || "Untitled strategy";
        const created = await apiClient.createStrategy({
          name: strategyName,
          description: form.description,
        });
        controller.selectStrategy(created.data.strategy_id);
        const versionResult = await apiClient.createStrategyVersion(created.data.strategy_id, body);
        selection.setStrategyVersionId(versionResult.data.strategy_version_id);
        setMessage(versionResult.data.strategy_version_id);
        await controller.refreshStrategies();
        await controller.refreshVersions(created.data.strategy_id);
      } else if (version && version.status === "DRAFT") {
        await apiClient.updateStrategyVersionDraft(version.strategy_version_id, body);
        await controller.refreshVersions(controller.selectedStrategy.strategy_id);
        setMessage(version.strategy_version_id);
      } else {
        setError(t("strategy_lab.error.frozen_create_new_version"));
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const createNewVersion = async () => {
    if (!version || version.status !== "FROZEN") return;
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.forkStrategyVersion(version.strategy_version_id, {
        definition: buildBody().definition,
        hypothesis: form.hypothesis,
      });
      controller.selectVersion(result.data.strategy_version_id);
      await controller.refreshVersions(version.strategy_id);
      setMessage(result.data.strategy_version_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const freeze = async () => {
    if (!version || version.status !== "DRAFT") return;
    setBusy(true);
    try {
      await apiClient.freezeStrategyVersion(version.strategy_version_id);
      await controller.refreshVersions(version.strategy_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="strategy-design">
      <div className="strategy-validation-summary">
        <span>{t("strategy_lab.validation")}</span>
        <span className="status-badge status-blocked">{validation.blockers.length} {t("strategy_lab.blockers")}</span>
        <span className="status-badge status-warning">{validation.warnings.length} {t("strategy_lab.warnings")}</span>
        <div className="strategy-validation-list">
          {validation.blockers.map((item) => <div key={item}>BLOCKER: {item}</div>)}
          {validation.warnings.map((item) => <div key={item}>WARNING: {item}</div>)}
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
      <div className="strategy-design-actions">
        {frozen ? (
          <button type="button" disabled={busy} onClick={createNewVersion}>
            {t("strategy_lab.create_new_version")}
          </button>
        ) : (
          <button type="button" disabled={busy || validation.blockers.length > 0} onClick={saveDraft}>
            {t("strategy_lab.save_draft")}
          </button>
        )}
        {version?.status === "DRAFT" && (
          <button type="button" disabled={busy} onClick={freeze}>
            {t("strategy_lab.freeze_version")}
          </button>
        )}
      </div>
      {message && <p className="muted">{t("strategy_lab.saved")}: {message}</p>}
      {error && <p className="strategy-error">{error}</p>}
    </div>
  );
}
