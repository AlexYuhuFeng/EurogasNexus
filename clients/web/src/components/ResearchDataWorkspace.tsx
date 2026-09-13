import { useEffect, useMemo, useRef, useState } from "react";
import {
  ResearchDatasetDTO,
  ResearchDatasetDetailDTO,
  ResearchDatasetExportDTO,
  ResearchDatasetQualityDTO,
  ResearchFeatureDTO,
  ResearchTargetDTO,
  api,
} from "@/api/client";
import { StatusBadge, WorkspaceTabs } from "@/components/ui";
import {
  DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
  WorkspaceLoadCoordinator,
  loadWorkspaceEndpoint,
} from "@/stores/workspaceLoading";
import { useApiStore } from "@/stores/api";
import {
  isCurrentResearchSelection,
  isResearchDetailForSelection,
  researchDisplayValue,
  researchExportDecision,
  safeResearchErrorMessage,
} from "@/app/model/researchDataModel";
import "@/styles/researchDataWorkspace.css";

type Translate = (key: string) => string;
type ResearchViewId = "datasets" | "features" | "targets";
type ExportFormat = "parquet" | "csv";

const VIEWS: ResearchViewId[] = ["datasets", "features", "targets"];

interface ResearchDataWorkspaceProps {
  t: Translate;
}

type DetailState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; detail: ResearchDatasetDetailDTO; quality: ResearchDatasetQualityDTO }
  | { status: "error"; message: string };

const genericErrorMessages = (t: Translate) => ({
  generic: t("research.request_error"),
  unauthorized: t("research.unauthorized_error"),
  forbidden: t("research.forbidden_error"),
  exportDenied: t("research.export_denied_backend"),
});

function formatDate(value: string | null | undefined, unknownLabel: string): string {
  if (!value) return unknownLabel;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : `${parsed.toLocaleString([], { timeZone: "UTC" })} UTC`;
}

function formatCoverage(value: number | null | undefined, unknownLabel: string): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? unknownLabel
    : `${(value * 100).toFixed(1)}%`;
}

function detailMetadata(detail: ResearchDatasetDetailDTO): Record<string, unknown> {
  return detail.metadata && typeof detail.metadata === "object" ? detail.metadata : {};
}

function metadataStringList(metadata: Record<string, unknown>, key: string): string[] {
  const value = metadata[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function DetailValue({ label, value }: { label: string; value: string }) {
  return <div className="research-detail-value"><dt>{label}</dt><dd>{value}</dd></div>;
}

function DatasetDetailRail({
  t,
  selectedId,
  detailState,
  onRetry,
  onExport,
  exportFormat,
  onExportFormatChange,
  exportBusy,
  exportResult,
  exportError,
}: {
  t: Translate;
  selectedId: string | null;
  detailState: DetailState;
  onRetry: () => void;
  onExport: () => void;
  exportFormat: ExportFormat;
  onExportFormatChange: (format: ExportFormat) => void;
  exportBusy: boolean;
  exportResult: ResearchDatasetExportDTO | null;
  exportError: string | null;
}) {
  if (!selectedId) {
    return <aside className="research-detail-rail" aria-label={t("research.detail")}><div className="research-detail-empty"><strong>{t("research.select_dataset")}</strong><span>{t("research.select_dataset_help")}</span></div></aside>;
  }
  if (detailState.status === "loading") {
    return <aside className="research-detail-rail" aria-label={t("research.detail")} aria-busy="true"><div className="research-detail-loading">{t("status.loading")}</div></aside>;
  }
  if (detailState.status === "error") {
    return <aside className="research-detail-rail" aria-label={t("research.detail")}><div className="research-detail-error" role="alert"><strong>{t("research.detail_error")}</strong><span>{detailState.message}</span><button type="button" className="research-text-button" onClick={onRetry}>{t("research.retry")}</button></div></aside>;
  }
  if (detailState.status === "idle") return null;
  if (detailState.status === "ready" && !isResearchDetailForSelection(selectedId, detailState.detail.dataset_snapshot_id)) {
    return <aside className="research-detail-rail" aria-label={t("research.detail")} aria-busy="true"><div className="research-detail-loading">{t("status.loading")}</div></aside>;
  }

  const { detail, quality } = detailState;
  const metadata = detailMetadata(detail);
  const lineage = metadataStringList(metadata, "lineage");
  const warnings = quality.warnings.length ? quality.warnings : metadataStringList(metadata, "warnings");
  const qualityReport = quality.quality_report && typeof quality.quality_report === "object" ? quality.quality_report : {};
  const policy = detail.entitlement_envelope?.export_policy;
  const exportDecision = researchExportDecision(policy);
  const contentHash = detail.content_hash ?? metadata.content_hash;

  return (
    <aside className="research-detail-rail" aria-label={t("research.detail")}>
      <div className="research-detail-heading">
        <span className="research-eyebrow">{t("research.detail")}</span>
        <h2>{detail.dataset_spec_id}</h2>
        <StatusBadge variant="pipeline" status={detail.status.toLowerCase()}>{detail.status}</StatusBadge>
      </div>

      <section className="research-detail-section" aria-labelledby="research-detail-facts">
        <h3 id="research-detail-facts">{t("research.dataset_facts")}</h3>
        <dl className="research-detail-grid">
          <DetailValue label={t("research.snapshot_id")} value={detail.dataset_snapshot_id} />
          <DetailValue label={t("research.spec_hash")} value={detail.spec_hash || t("research.unknown")} />
          <DetailValue label={t("research.content_hash")} value={researchDisplayValue(contentHash, t("research.unknown"))} />
          <DetailValue label={t("research.ontology")} value={researchDisplayValue(detail.ontology_version, t("research.unknown"))} />
          <DetailValue label={t("research.cutoff")} value={formatDate(detail.source_cutoff_utc, t("research.unknown"))} />
          <DetailValue label={t("research.rows")} value={researchDisplayValue(detail.row_count, t("research.unknown"))} />
          <DetailValue label={t("research.columns")} value={researchDisplayValue(detail.column_count, t("research.unknown"))} />
          <DetailValue label={t("research.coverage")} value={formatCoverage(detail.coverage, t("research.unknown"))} />
          <DetailValue label={t("research.temporal_integrity")} value={researchDisplayValue(detail.temporal_integrity, t("research.unknown"))} />
          <DetailValue label={t("research.rights")} value={researchDisplayValue(policy, t("research.unknown"))} />
          <DetailValue label={t("research.artifact_reference")} value={researchDisplayValue(detail.artifact_ref, t("research.unknown"))} />
        </dl>
      </section>

      <section className="research-detail-section" aria-labelledby="research-lineage">
        <h3 id="research-lineage">{t("research.lineage")}</h3>
        {lineage.length ? <ul className="research-detail-list">{lineage.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="research-muted">{t("research.unknown")}</p>}
      </section>

      <section className="research-detail-section" aria-labelledby="research-quality">
        <h3 id="research-quality">{t("research.quality")}</h3>
        <dl className="research-quality-list">
          {Object.entries(qualityReport).map(([key, value]) => <DetailValue key={key} label={key} value={researchDisplayValue(value, t("research.unknown"))} />)}
        </dl>
        {quality.leakage_issues.length > 0 && <div className="research-warning-block"><strong>{t("research.leakage_issues")}</strong><ul className="research-detail-list">{quality.leakage_issues.map((issue, index) => <li key={`${index}-${researchDisplayValue(issue.code, "issue")}`}>{researchDisplayValue(issue, t("research.unknown"))}</li>)}</ul></div>}
        {warnings.length > 0 && <div className="research-warning-block"><strong>{t("research.warnings")}</strong><ul className="research-detail-list">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
        {!Object.keys(qualityReport).length && !quality.leakage_issues.length && !warnings.length && <p className="research-muted">{t("research.unknown")}</p>}
      </section>

      <section className="research-detail-section research-export-section" aria-labelledby="research-export">
        <h3 id="research-export">{t("research.export_reference")}</h3>
        <p className="research-muted">{t("research.export_reference_help")}</p>
        <div className="research-export-controls">
          <label htmlFor="research-export-format">{t("research.format")}</label>
          <select id="research-export-format" value={exportFormat} onChange={(event) => onExportFormatChange(event.target.value as ExportFormat)}><option value="parquet">Parquet</option><option value="csv">CSV</option></select>
          <button type="button" className="button primary" onClick={onExport} disabled={exportBusy || exportDecision !== "allowed"}>{exportBusy ? t("status.loading") : t("research.request_artifact_reference")}</button>
        </div>
        {exportDecision !== "allowed" && <p className="research-policy-note" role="status">{exportDecision === "unknown" ? t("research.export_unknown_policy") : t("research.export_restricted_policy")}</p>}
        {exportError && <p className="research-export-error" role="alert">{exportError}</p>}
        {exportResult && <p className="research-artifact-result" role="status"><strong>{t("research.artifact_reference")}</strong> {researchDisplayValue(exportResult.artifact_ref, t("research.unknown"))}</p>}
      </section>
    </aside>
  );
}

function DatasetCatalog({ t, datasets, loading, error, selectedId, onSelect }: {
  t: Translate;
  datasets: ResearchDatasetDTO[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  onSelect: (datasetId: string) => void;
}) {
  return (
    <section className="research-catalog" aria-labelledby="research-dataset-table-title">
      <div className="research-surface-heading"><h2 id="research-dataset-table-title">{t("research.dataset_snapshots")}</h2><span>{t("research.dataset_snapshots_help")}</span></div>
      {error && <div className="research-catalog-error" role="alert">{error}</div>}
      <div className="research-table-wrap">
        <table className="research-semantic-table" aria-busy={loading}>
          <caption className="visually-hidden">{t("research.dataset_snapshots")}</caption>
          <thead><tr><th scope="col">{t("research.name")}</th><th scope="col">{t("research.rows")}</th><th scope="col">{t("research.columns")}</th><th scope="col">{t("research.coverage")}</th><th scope="col">{t("research.temporal_integrity")}</th><th scope="col">{t("research.created")}</th><th scope="col">{t("research.status")}</th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="research-state-row">{t("status.loading")}</td></tr>}
            {!loading && datasets.map((dataset) => <tr key={dataset.dataset_snapshot_id} className={selectedId === dataset.dataset_snapshot_id ? "selected" : undefined} aria-selected={selectedId === dataset.dataset_snapshot_id} tabIndex={0} onClick={() => onSelect(dataset.dataset_snapshot_id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(dataset.dataset_snapshot_id); } }}><th scope="row"><button type="button" className="research-row-button" onClick={() => onSelect(dataset.dataset_snapshot_id)}>{dataset.dataset_spec_id}</button></th><td>{researchDisplayValue(dataset.row_count, t("research.unknown"))}</td><td>{researchDisplayValue(dataset.column_count, t("research.unknown"))}</td><td>{formatCoverage(dataset.coverage, t("research.unknown"))}</td><td><StatusBadge variant="pipeline" status={dataset.temporal_integrity.toLowerCase()}>{dataset.temporal_integrity}</StatusBadge></td><td>{formatDate(dataset.created_at_utc, t("research.unknown"))}</td><td>{dataset.status}</td></tr>)}
            {!loading && datasets.length === 0 && <tr><td colSpan={7} className="research-state-row">{t("research.no_datasets")}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RegistryTable({ t, type, features, targets, loading, error }: { t: Translate; type: "features" | "targets"; features: ResearchFeatureDTO[]; targets: ResearchTargetDTO[]; loading: boolean; error: string | null }) {
  if (type === "features") {
    return <section className="research-registry" id="research-task-panel" role="tabpanel" aria-label={t("research.tab.features")}><div className="research-surface-heading"><h2>{t("research.feature_registry")}</h2><span>{t("research.feature_registry_help")}</span></div>{error && <div className="research-catalog-error" role="alert">{error}</div>}<div className="research-table-wrap"><table className="research-semantic-table"><thead><tr><th scope="col">{t("research.feature")}</th><th scope="col">{t("research.category")}</th><th scope="col">{t("research.unit")}</th><th scope="col">{t("research.frequency")}</th><th scope="col">{t("research.availability_class")}</th><th scope="col">{t("research.dependencies")}</th><th scope="col">{t("research.status")}</th></tr></thead><tbody>{loading && <tr><td colSpan={7} className="research-state-row">{t("status.loading")}</td></tr>}{!loading && features.map((feature) => <tr key={feature.feature_id}><th scope="row">{feature.feature_id}</th><td>{feature.definition.category}</td><td>{feature.definition.output_unit}</td><td>{feature.definition.frequency}</td><td>{feature.definition.availability_class}</td><td>{feature.definition.input_dependencies.join(", ") || t("research.unknown")}</td><td>{feature.status}</td></tr>)}{!loading && features.length === 0 && <tr><td colSpan={7} className="research-state-row">{t("research.no_features")}</td></tr>}</tbody></table></div></section>;
  }
  return <section className="research-registry" id="research-task-panel" role="tabpanel" aria-label={t("research.tab.targets")}><div className="research-surface-heading"><h2>{t("research.target_registry")}</h2><span>{t("research.target_registry_help")}</span></div>{error && <div className="research-catalog-error" role="alert">{error}</div>}<div className="research-table-wrap"><table className="research-semantic-table"><thead><tr><th scope="col">{t("research.target")}</th><th scope="col">{t("research.entity")}</th><th scope="col">{t("research.horizon")}</th><th scope="col">{t("research.window")}</th><th scope="col">{t("research.unit")}</th><th scope="col">{t("research.aggregation")}</th><th scope="col">{t("research.status")}</th></tr></thead><tbody>{loading && <tr><td colSpan={7} className="research-state-row">{t("status.loading")}</td></tr>}{!loading && targets.map((target) => <tr key={target.target_id}><th scope="row">{target.target_id}</th><td>{target.definition.entity_id}</td><td>{target.definition.horizon}</td><td>{target.definition.target_window}</td><td>{target.definition.unit}</td><td>{target.definition.aggregation}</td><td>{target.status}</td></tr>)}{!loading && targets.length === 0 && <tr><td colSpan={7} className="research-state-row">{t("research.no_targets")}</td></tr>}</tbody></table></div></section>;
}

export function ResearchDataWorkspace({ t }: ResearchDataWorkspaceProps) {
  const identityKey = useApiStore((state) => state.currentUser?.principal_id ?? "anonymous");
  const [activeView, setActiveView] = useState<ResearchViewId>("datasets");
  const [features, setFeatures] = useState<ResearchFeatureDTO[]>([]);
  const [targets, setTargets] = useState<ResearchTargetDTO[]>([]);
  const [datasets, setDatasets] = useState<ResearchDatasetDTO[]>([]);
  const [catalogIdentityKey, setCatalogIdentityKey] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [detailState, setDetailState] = useState<DetailState>({ status: "idle" });
  const [detailRetryKey, setDetailRetryKey] = useState(0);
  const [exportFormat, setExportFormat] = useState<ExportFormat>("parquet");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportResult, setExportResult] = useState<ResearchDatasetExportDTO | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const catalogCoordinator = useRef(new WorkspaceLoadCoordinator()).current;
  const detailCoordinator = useRef(new WorkspaceLoadCoordinator()).current;
  const exportCoordinator = useRef(new WorkspaceLoadCoordinator()).current;
  const selectedDatasetIdRef = useRef<string | null>(null);

  useEffect(() => {
    selectedDatasetIdRef.current = selectedDatasetId;
  }, [selectedDatasetId]);

  useEffect(() => {
    catalogCoordinator.cancel();
    detailCoordinator.cancel();
    exportCoordinator.cancel();
    selectedDatasetIdRef.current = null;
    setFeatures([]);
    setTargets([]);
    setDatasets([]);
    setCatalogIdentityKey(null);
    setSelectedDatasetId(null);
    setCatalogError(null);
    setCatalogLoading(true);
    setDetailState({ status: "idle" });
    setExportBusy(false);
    setExportResult(null);
    setExportError(null);
  }, [catalogCoordinator, detailCoordinator, exportCoordinator, identityKey]);

  useEffect(() => {
    const load = catalogCoordinator.start();
    const requestedIdentity = identityKey;
    setCatalogLoading(true);
    void Promise.all([
      loadWorkspaceEndpoint(api.researchFeatures, { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS }),
      loadWorkspaceEndpoint(api.researchTargets, { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS }),
      loadWorkspaceEndpoint(api.researchDatasets, { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS }),
    ]).then(([featureResult, targetResult, datasetResult]) => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (!catalogCoordinator.isCurrent(load.generation, load.signal) || liveIdentity !== requestedIdentity) return;
      const failures = [featureResult, targetResult, datasetResult].filter((result) => !result.ok);
      if (featureResult.ok) setFeatures(featureResult.value.data);
      if (targetResult.ok) setTargets(targetResult.value.data);
      if (datasetResult.ok) setDatasets(datasetResult.value.data);
      setCatalogIdentityKey(requestedIdentity);
      setCatalogError(failures.length ? t("research.catalog_error") : null);
    }).catch(() => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (catalogCoordinator.isCurrent(load.generation, load.signal) && liveIdentity === requestedIdentity) setCatalogError(t("research.catalog_error"));
    }).finally(() => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (catalogCoordinator.isCurrent(load.generation, load.signal) && liveIdentity === requestedIdentity) { setCatalogLoading(false); catalogCoordinator.finish(load.generation); }
    });
    return () => catalogCoordinator.cancel();
  }, [catalogCoordinator, identityKey, t]);

  useEffect(() => {
    if (selectedDatasetId && !datasets.some((dataset) => dataset.dataset_snapshot_id === selectedDatasetId)) {
      setSelectedDatasetId(null);
      setDetailState({ status: "idle" });
    }
  }, [datasets, selectedDatasetId]);

  useEffect(() => {
    if (!selectedDatasetId) { detailCoordinator.cancel(); setDetailState({ status: "idle" }); setExportResult(null); setExportError(null); return; }
    const requestedDatasetId = selectedDatasetId;
    const requestedIdentity = identityKey;
    const load = detailCoordinator.start();
    setDetailState({ status: "loading" });
    setExportResult(null);
    setExportError(null);
    void Promise.all([
      loadWorkspaceEndpoint((options) => api.researchDataset(requestedDatasetId, options), { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS }),
      loadWorkspaceEndpoint((options) => api.researchDatasetQuality(requestedDatasetId, options), { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS }),
    ]).then(([detailResult, qualityResult]) => {
      const currentIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (!detailCoordinator.isCurrent(load.generation, load.signal) || !isCurrentResearchSelection(selectedDatasetIdRef.current, requestedDatasetId, currentIdentity, requestedIdentity)) return;
      if (detailResult.ok && qualityResult.ok) setDetailState({ status: "ready", detail: detailResult.value.data, quality: qualityResult.value.data });
      else { const failure = detailResult.ok ? qualityResult : detailResult; setDetailState({ status: "error", message: failure.ok ? t("research.detail_error") : safeResearchErrorMessage(failure.error.message, genericErrorMessages(t)) }); }
    }).catch((reason) => {
      const currentIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (detailCoordinator.isCurrent(load.generation, load.signal) && isCurrentResearchSelection(selectedDatasetIdRef.current, requestedDatasetId, currentIdentity, requestedIdentity)) setDetailState({ status: "error", message: safeResearchErrorMessage(reason, genericErrorMessages(t)) });
    });
    return () => detailCoordinator.cancel();
  }, [detailCoordinator, detailRetryKey, identityKey, selectedDatasetId, t]);

  useEffect(() => {
    exportCoordinator.cancel();
    setExportBusy(false);
    setExportResult(null);
    setExportError(null);
  }, [exportCoordinator, identityKey, selectedDatasetId]);

  const tabs = useMemo(() => VIEWS.map((id) => ({ id, label: t(`research.tab.${id}`) })), [t]);
  const catalogVisible = catalogIdentityKey === identityKey;
  const visibleDatasets = catalogVisible ? datasets : [];
  const visibleFeatures = catalogVisible ? features : [];
  const visibleTargets = catalogVisible ? targets : [];
  const visibleSelectedDatasetId = catalogVisible ? selectedDatasetId : null;

  async function requestArtifactReference() {
    if (!selectedDatasetId || detailState.status !== "ready") return;
    if (researchExportDecision(detailState.detail.entitlement_envelope?.export_policy) !== "allowed") return;
    const requestedDatasetId = selectedDatasetId;
    const requestedIdentity = identityKey;
    const load = exportCoordinator.start();
    setExportBusy(true); setExportError(null); setExportResult(null);
    void loadWorkspaceEndpoint(
      (options) => api.exportResearchDataset(requestedDatasetId, { format: exportFormat }, options),
      { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS },
    ).then((result) => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      const current = exportCoordinator.isCurrent(load.generation, load.signal)
        && isCurrentResearchSelection(selectedDatasetIdRef.current, requestedDatasetId, liveIdentity, requestedIdentity);
      if (!current) return;
      if (result.ok) setExportResult(result.value.data);
      else setExportError(safeResearchErrorMessage(result.error.message, genericErrorMessages(t)));
    }).catch((reason) => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (exportCoordinator.isCurrent(load.generation, load.signal) && isCurrentResearchSelection(selectedDatasetIdRef.current, requestedDatasetId, liveIdentity, requestedIdentity)) {
        setExportError(safeResearchErrorMessage(reason, genericErrorMessages(t)));
      }
    }).finally(() => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (exportCoordinator.isCurrent(load.generation, load.signal) && isCurrentResearchSelection(selectedDatasetIdRef.current, requestedDatasetId, liveIdentity, requestedIdentity)) {
        setExportBusy(false);
        exportCoordinator.finish(load.generation);
      }
    });
  }

  useEffect(() => () => exportCoordinator.cancel(), [exportCoordinator]);

  return <div className={`research-data-page research-view-${activeView}`}>
    <div className="research-task-tabs-wrap"><WorkspaceTabs idPrefix="research-task" label={t("research.title")} tabs={tabs} activeId={activeView} panelId="research-task-panel" className="research-task-tabs" onActivate={(view) => setActiveView(view as ResearchViewId)} /></div>
    {activeView === "datasets" && <div className="research-master-detail" id="research-task-panel" role="tabpanel" aria-label={t("research.tab.datasets")}><DatasetCatalog t={t} datasets={visibleDatasets} loading={catalogLoading} error={catalogError} selectedId={visibleSelectedDatasetId} onSelect={(datasetId) => { selectedDatasetIdRef.current = datasetId; setSelectedDatasetId(datasetId); }} /><DatasetDetailRail t={t} selectedId={visibleSelectedDatasetId} detailState={detailState} onRetry={() => setDetailRetryKey((value) => value + 1)} onExport={() => void requestArtifactReference()} exportFormat={exportFormat} onExportFormatChange={setExportFormat} exportBusy={exportBusy} exportResult={exportResult} exportError={exportError} /></div>}
    {activeView !== "datasets" && <RegistryTable t={t} type={activeView} features={visibleFeatures} targets={visibleTargets} loading={catalogLoading} error={catalogError} />}
  </div>;
}
