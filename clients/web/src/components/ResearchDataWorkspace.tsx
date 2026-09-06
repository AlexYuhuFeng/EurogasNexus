import { useEffect, useMemo, useState } from "react";
import {
  ResearchCapabilityDTO,
  ResearchDatasetDTO,
  ResearchFeatureDTO,
  ResearchTargetDTO,
  api,
} from "@/api/client";
import { PanelHeader, WorkspaceTabs } from "@/components/ui";

type Translate = (key: string) => string;
type ResearchViewId = "datasets" | "features" | "targets";

const VIEWS: ResearchViewId[] = ["datasets", "features", "targets"];

interface ResearchDataWorkspaceProps {
  t: Translate;
}

function loadingRow(label: string) {
  return <div className="data-table-row"><span>{label}</span></div>;
}

export function ResearchDataWorkspace({ t }: ResearchDataWorkspaceProps) {
  const [activeView, setActiveView] = useState<ResearchViewId>("datasets");
  const [features, setFeatures] = useState<ResearchFeatureDTO[]>([]);
  const [targets, setTargets] = useState<ResearchTargetDTO[]>([]);
  const [datasets, setDatasets] = useState<ResearchDatasetDTO[]>([]);
  const [capabilities, setCapabilities] = useState<ResearchCapabilityDTO[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.researchFeatures(),
      api.researchTargets(),
      api.researchDatasets(),
      api.researchCapabilities(),
    ])
      .then(([featureResult, targetResult, datasetResult, capabilityResult]) => {
        if (!active) return;
        setFeatures(featureResult.data);
        setTargets(targetResult.data);
        setDatasets(datasetResult.data);
        setCapabilities(capabilityResult.data);
        setError(null);
      })
      .catch((reason) => active && setError(String(reason)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const tabs = useMemo(
    () => VIEWS.map((id) => ({ id, label: t(`research.tab.${id}`) })),
    [t],
  );

  return (
    <div className={`workspace-grid research-data-page research-view-${activeView}`}>
      <div className="workspace-panel span-3 research-intro-panel">
        <PanelHeader title={t("research.title")} meta={t("research.subtitle")} />
        <div className="research-capability-strip" aria-label={t("research.capabilities")}>
          {capabilities.length === 0 ? (
            <span className="muted">{t("research.no_capabilities")}</span>
          ) : (
            capabilities.map((capability) => (
              <span key={capability.name} className="research-capability-chip">
                {capability.name}
              </span>
            ))
          )}
        </div>
      </div>

      <div className="workspace-panel span-3">
        <WorkspaceTabs
          idPrefix="research-task"
          label={t("research.title")}
          tabs={tabs}
          activeId={activeView}
          panelId="research-task-panel"
          className="research-task-tabs"
          onActivate={(view) => setActiveView(view as ResearchViewId)}
        />
      </div>

      {error && <div className="workspace-panel span-3 alert">{error}</div>}
      {loading && <div className="workspace-panel span-3">{t("status.loading")}</div>}

      {!loading && activeView === "datasets" && (
        <div className="workspace-panel span-3">
          <PanelHeader title={t("research.dataset_snapshots")} meta={t("research.dataset_snapshots_help")} />
          <div className="data-table research-table">
            <div className="data-table-row header seven">
              <span>{t("research.name")}</span>
              <span>{t("research.rows")}</span>
              <span>{t("research.columns")}</span>
              <span>{t("research.coverage")}</span>
              <span>{t("research.temporal_integrity")}</span>
              <span>{t("research.created")}</span>
              <span>{t("research.status")}</span>
            </div>
            {datasets.map((dataset) => (
              <div key={dataset.dataset_snapshot_id} className="data-table-row seven">
                <strong>{dataset.dataset_spec_id}</strong>
                <span>{dataset.row_count.toLocaleString()}</span>
                <span>{dataset.column_count}</span>
                <span>{(dataset.coverage * 100).toFixed(1)}%</span>
                <span className="status-badge">{dataset.temporal_integrity}</span>
                <span>{new Date(dataset.created_at_utc).toLocaleString()}</span>
                <span>{dataset.status}</span>
              </div>
            ))}
            {datasets.length === 0 && loadingRow(t("research.no_datasets"))}
          </div>
        </div>
      )}

      {!loading && activeView === "features" && (
        <div className="workspace-panel span-3">
          <PanelHeader title={t("research.feature_registry")} meta={t("research.feature_registry_help")} />
          <div className="data-table research-table">
            <div className="data-table-row header seven">
              <span>{t("research.feature")}</span>
              <span>{t("research.category")}</span>
              <span>{t("research.unit")}</span>
              <span>{t("research.frequency")}</span>
              <span>{t("research.availability_class")}</span>
              <span>{t("research.dependencies")}</span>
              <span>{t("research.status")}</span>
            </div>
            {features.map((feature) => (
              <div key={feature.feature_id} className="data-table-row seven">
                <strong>{feature.feature_id}</strong>
                <span>{feature.definition.category}</span>
                <span>{feature.definition.output_unit}</span>
                <span>{feature.definition.frequency}</span>
                <span>{feature.definition.availability_class}</span>
                <span>{feature.definition.input_dependencies.join(", ") || "—"}</span>
                <span>{feature.status}</span>
              </div>
            ))}
            {features.length === 0 && loadingRow(t("research.no_features"))}
          </div>
        </div>
      )}

      {!loading && activeView === "targets" && (
        <div className="workspace-panel span-3">
          <PanelHeader title={t("research.target_registry")} meta={t("research.target_registry_help")} />
          <div className="data-table research-table">
            <div className="data-table-row header seven">
              <span>{t("research.target")}</span>
              <span>{t("research.entity")}</span>
              <span>{t("research.horizon")}</span>
              <span>{t("research.window")}</span>
              <span>{t("research.unit")}</span>
              <span>{t("research.aggregation")}</span>
              <span>{t("research.status")}</span>
            </div>
            {targets.map((target) => (
              <div key={target.target_id} className="data-table-row seven">
                <strong>{target.target_id}</strong>
                <span>{target.definition.entity_id}</span>
                <span>{target.definition.horizon}</span>
                <span>{target.definition.target_window}</span>
                <span>{target.definition.unit}</span>
                <span>{target.definition.aggregation}</span>
                <span>{target.status}</span>
              </div>
            ))}
            {targets.length === 0 && loadingRow(t("research.no_targets"))}
          </div>
        </div>
      )}
    </div>
  );
}
