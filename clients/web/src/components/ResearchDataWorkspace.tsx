import { useEffect, useMemo, useRef, useState } from "react";
import {
  ResearchDatasetDTO,
  ResearchDatasetDetailDTO,
  ResearchDatasetQualityDTO,
  ResearchFeatureDTO,
  ResearchTargetDTO,
  api,
  apiOutcome,
} from "@/api/client";
import { MetricStrip, PanelHeader, StatusBadge, WorkspaceTabs } from "@/components/ui";
import { DataProductCatalogue } from "@/components/DataProductCatalogue";
import {
  DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
  WorkspaceLoadCoordinator,
  loadWorkspaceEndpoint,
} from "@/stores/workspaceLoading";
import { useApiStore } from "@/stores/api";
import {
  EMPTY_RESEARCH_SPEC_DRAFT,
  RESEARCH_EXPORT_FORMATS,
  ResearchBuildGate,
  ResearchBuildSummary,
  ResearchExportState,
  ResearchIssue,
  ResearchIssueGroup,
  ResearchSpecDraft,
  ResearchValidationOutcome,
  groupResearchIssues,
  isCurrentResearchSelection,
  isResearchDetailForSelection,
  researchAnswerCode,
  researchBuildGate,
  researchBuildSummary,
  researchDisplayValue,
  researchExportCanRequest,
  researchExportDecision,
  researchExportStateFromAnswer,
  researchFormatOptions,
  researchFormatRows,
  researchHttpStatus,
  researchIssueTotal,
  researchIssuesFromAnswer,
  researchRequestErrorMessage,
  researchSpecFingerprint,
  researchSpecFromDraft,
  researchSpecMissingInputs,
  researchValidationOutcome,
  safeResearchErrorMessage,
} from "@/app/model/researchDataModel";
import "@/styles/researchDataWorkspace.css";

type Translate = (key: string) => string;
type ResearchViewId = "datasets" | "products" | "features" | "targets";
type ExportFormat = "parquet" | "csv";

const VIEWS: ResearchViewId[] = ["datasets", "products", "features", "targets"];

interface ResearchDataWorkspaceProps {
  t: Translate;
}

type DetailState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; detail: ResearchDatasetDetailDTO; quality: ResearchDatasetQualityDTO }
  | { status: "error"; message: string };

type ValidationState =
  | { status: "idle" }
  | { status: "busy" }
  | { status: "ready"; outcome: ResearchValidationOutcome; fingerprint: string }
  | { status: "error"; message: string };

type BuildState =
  | { status: "idle" }
  | { status: "busy" }
  | { status: "created"; summary: ResearchBuildSummary }
  | { status: "rejected"; code: string; issues: ResearchIssue[]; message: string }
  | { status: "error"; message: string };

const genericErrorMessages = (t: Translate) => ({
  generic: t("research.request_error"),
  unauthorized: t("research.unauthorized_error"),
  forbidden: t("research.forbidden_error"),
  exportDenied: t("research.export_denied_backend"),
});

const specRequestMessages = (t: Translate) => ({
  generic: t("research.request_error"),
  unauthorized: t("research.unauthorized_error"),
  forbidden: t("research.build_forbidden"),
});

/** Field labels are declared once so the required-input hint can name them. */
const SPEC_FIELD_LABELS: Record<keyof ResearchSpecDraft, string> = {
  datasetSpecId: "research.spec_dataset_spec_id",
  name: "research.spec_name",
  description: "research.spec_description",
  featureIds: "research.spec_feature_ids",
  targetIds: "research.spec_target_ids",
  entityIds: "research.spec_entity_ids",
  start: "research.spec_start",
  end: "research.spec_end",
  historyLookback: "research.spec_history_lookback",
  forecastOriginFrequency: "research.spec_forecast_origin_frequency",
  resamplingPolicyId: "research.spec_resampling_policy_id",
  outputFormat: "research.spec_output_format",
};

interface SpecFieldSpec {
  key: keyof ResearchSpecDraft;
  placeholderKey: string;
  multiline?: boolean;
}

const SPEC_TEXT_FIELDS: readonly SpecFieldSpec[] = [
  { key: "datasetSpecId", placeholderKey: "research.spec_placeholder_spec_id" },
  { key: "name", placeholderKey: "research.spec_placeholder_name" },
  { key: "description", placeholderKey: "research.spec_placeholder_description" },
  { key: "targetIds", placeholderKey: "research.spec_placeholder_list" },
  { key: "featureIds", placeholderKey: "research.spec_placeholder_list" },
  { key: "entityIds", placeholderKey: "research.spec_placeholder_list" },
  { key: "start", placeholderKey: "research.spec_placeholder_timestamp" },
  { key: "end", placeholderKey: "research.spec_placeholder_timestamp" },
  { key: "historyLookback", placeholderKey: "research.spec_placeholder_duration" },
  { key: "forecastOriginFrequency", placeholderKey: "research.spec_placeholder_frequency" },
  { key: "resamplingPolicyId", placeholderKey: "research.spec_placeholder_policy" },
  { key: "outputFormat", placeholderKey: "research.spec_placeholder_output_format" },
];

const SPEC_REQUIRED_KEYS: ReadonlyArray<keyof ResearchSpecDraft> = [
  "datasetSpecId",
  "name",
  "description",
  "targetIds",
  "start",
  "end",
];

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

function ResearchIssueList({ t, groups }: { t: Translate; groups: ResearchIssueGroup[] }) {
  return (
    <div className="research-issue-block">
      <strong>{t("research.validation_issues")}</strong>
      <ul className="research-issue-groups">
        {groups.map((group) => (
          <li key={group.field || "unassigned"}>
            <span className="research-issue-field">{group.field || t("research.issue_field_unassigned")}</span>
            <ul className="research-detail-list">
              {group.issues.map((issue) => (
                <li key={`${issue.code}-${issue.message}`}>
                  <code className="research-issue-code">{issue.code || t("research.issue_code_unknown")}</code>
                  {issue.message ? <span className="research-issue-message">{issue.message}</span> : null}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ResearchSpecPanel({
  t,
  draft,
  onDraftChange,
  missingInputs,
  validationState,
  buildState,
  gate,
  createdDetail,
  onValidate,
  onBuild,
}: {
  t: Translate;
  draft: ResearchSpecDraft;
  onDraftChange: (key: keyof ResearchSpecDraft, value: string) => void;
  missingInputs: Array<keyof ResearchSpecDraft>;
  validationState: ValidationState;
  buildState: BuildState;
  gate: ResearchBuildGate;
  createdDetail: ResearchDatasetDetailDTO | null;
  onValidate: () => void;
  onBuild: () => void;
}) {
  const busy = validationState.status === "busy" || buildState.status === "busy";
  const ready = missingInputs.length === 0;
  const outcome = validationState.status === "ready" ? validationState.outcome : null;
  const issueGroups = outcome ? groupResearchIssues(outcome.issues) : [];
  const buildGroups = buildState.status === "rejected" ? groupResearchIssues(buildState.issues) : [];

  return (
    <section className="research-spec-panel" aria-labelledby="research-spec-title">
      <PanelHeader title={<span id="research-spec-title">{t("research.spec_build_title")}</span>} meta={t("research.spec_build_help")} />
      <p className="research-muted">{t("research.spec_build_note")}</p>
      <fieldset className="research-spec-fieldset" disabled={busy}>
        <legend className="visually-hidden">{t("research.spec_build_title")}</legend>
        <div className="research-spec-grid">
          {SPEC_TEXT_FIELDS.map((field) => (
            <label key={field.key} className={field.key === "description" ? "span-2" : undefined}>
              {t(SPEC_FIELD_LABELS[field.key])}
              {SPEC_REQUIRED_KEYS.includes(field.key) ? <span aria-hidden="true"> *</span> : null}
              <input
                type="text"
                value={draft[field.key]}
                placeholder={t(field.placeholderKey)}
                onChange={(event) => onDraftChange(field.key, event.target.value)}
              />
            </label>
          ))}
        </div>
      </fieldset>
      <p className="research-muted">{t("research.spec_required_note")}</p>
      {missingInputs.length > 0 && (
        <p className="research-spec-required" role="status">
          <strong>{t("research.spec_required_fields")}</strong>
          <span>{missingInputs.map((key) => t(SPEC_FIELD_LABELS[key])).join(", ")}</span>
        </p>
      )}
      <div className="research-spec-actions">
        <button type="button" className="button" onClick={onValidate} disabled={busy || !ready}>{validationState.status === "busy" ? t("status.loading") : t("research.validate_action")}</button>
        <button type="button" className="button primary" onClick={onBuild} disabled={busy || !gate.canBuild}>{buildState.status === "busy" ? t("status.loading") : t("research.build_action")}</button>
        <span className="research-muted" role="status">{gate.reason === "not_validated" ? t("research.build_locked_not_validated") : gate.reason === "spec_changed" ? t("research.build_locked_spec_changed") : gate.reason === "validation_failed" ? t("research.build_locked_validation_failed") : t("research.build_unlocked")}</span>
      </div>

      <section className="research-run-result" aria-labelledby="research-validation-result">
        <h3 id="research-validation-result">{t("research.validation_result")}</h3>
        {validationState.status === "idle" && <p className="research-muted">{t("research.validation_not_run")}</p>}
        {validationState.status === "busy" && <p className="research-muted" aria-busy="true">{t("status.loading")}</p>}
        {validationState.status === "error" && <p className="research-export-error" role="alert">{validationState.message}</p>}
        {outcome && (
          <>
            <MetricStrip
              className="metric-grid research-run-metrics"
              items={[
                { label: t("research.validation_status"), value: <StatusBadge variant="pipeline" status={outcome.ok ? "succeeded" : "failed"}>{outcome.ok ? t("research.validation_ok") : t("research.validation_failed")}</StatusBadge> },
                { label: t("research.spec_hash"), value: researchDisplayValue(outcome.specHash, t("research.unknown")) },
                { label: t("research.registry_resolution"), value: researchDisplayValue(outcome.registryResolution, t("research.unknown")) },
                { label: t("research.validation_issue_count"), value: researchIssueTotal(issueGroups) },
              ]}
            />
            {outcome.code && <p className="research-muted"><strong>{t("research.issue_code")}</strong> <code className="research-issue-code">{outcome.code}</code></p>}
            {issueGroups.length > 0
              ? <ResearchIssueList t={t} groups={issueGroups} />
              : <p className="research-muted">{t("research.validation_no_issues")}</p>}
          </>
        )}
      </section>

      <section className="research-run-result" aria-labelledby="research-build-result">
        <h3 id="research-build-result">{t("research.build_result")}</h3>
        {buildState.status === "idle" && <p className="research-muted">{t("research.build_not_run")}</p>}
        {buildState.status === "busy" && <p className="research-muted" aria-busy="true">{t("status.loading")}</p>}
        {buildState.status === "error" && <p className="research-export-error" role="alert">{buildState.message}</p>}
        {buildState.status === "rejected" && (
          <>
            <p className="research-export-error" role="alert"><strong>{t("research.build_rejected")}</strong> {buildState.message}</p>
            {buildState.code && <p className="research-muted"><strong>{t("research.issue_code")}</strong> <code className="research-issue-code">{buildState.code}</code></p>}
            {buildGroups.length > 0 && <ResearchIssueList t={t} groups={buildGroups} />}
          </>
        )}
        {buildState.status === "created" && (
          <>
            <p className="research-artifact-result" role="status"><strong>{t("research.build_created")}</strong> {buildState.summary.datasetSnapshotId}</p>
            <p className="research-muted">{t("research.build_created_help")}</p>
            <dl className="research-detail-grid">
              <DetailValue label={t("research.name")} value={researchDisplayValue(buildState.summary.datasetSpecId, t("research.unknown"))} />
              <DetailValue label={t("research.spec_hash")} value={researchDisplayValue(buildState.summary.specHash, t("research.unknown"))} />
              <DetailValue label={t("research.rows")} value={researchDisplayValue(buildState.summary.rowCount, t("research.unknown"))} />
              <DetailValue label={t("research.columns")} value={researchDisplayValue(buildState.summary.columnCount, t("research.unknown"))} />
              <DetailValue
                label={t("research.artifact_reference")}
                value={researchDisplayValue(createdDetail?.artifact_ref ?? buildState.summary.artifactRef, t("research.unknown"))}
              />
            </dl>
            <div className="research-format-block">
              <strong>{t("research.format_availability")}</strong>
              <ul className="research-format-list">
                {researchFormatRows(buildState.summary.availableFormats).map((row) => (
                  <li key={row.format}><span className="research-format-name">{row.format}</span><span className={`research-format-state research-format-${row.availability}`}>{row.availability === "registered" ? t("research.format_registered") : row.availability === "unregistered" ? t("research.format_unregistered") : t("research.format_unknown")}</span></li>
                ))}
              </ul>
              <p className="research-muted">{buildState.summary.availableFormats === null ? t("research.build_formats_unreported") : t("research.build_formats_reported")}</p>
            </div>
          </>
        )}
      </section>
    </section>
  );
}

function ArtifactDeliverySection({
  t,
  decision,
  exportState,
  exportError,
  exportFormat,
  onExportFormatChange,
  onExport,
  exportBusy,
}: {
  t: Translate;
  decision: ReturnType<typeof researchExportDecision>;
  exportState: ResearchExportState;
  exportError: string | null;
  exportFormat: ExportFormat;
  onExportFormatChange: (format: ExportFormat) => void;
  onExport: () => void;
  exportBusy: boolean;
}) {
  // The route only accepts parquet/csv, so the control can offer nothing else;
  // once the backend reports its registered formats, only those are offered so
  // a refused format is never requested twice.
  const requestableFormats = researchFormatOptions(exportState.availableFormats)
    .filter((format): format is ExportFormat => (RESEARCH_EXPORT_FORMATS as readonly string[]).includes(format));
  const canRequest = researchExportCanRequest(decision) && exportState.status !== "restricted";
  const showControl = canRequest && requestableFormats.length > 0;
  const formatRows = researchFormatRows(exportState.availableFormats);
  const formatStateLabel = (availability: string) => availability === "registered"
    ? t("research.format_registered")
    : availability === "unregistered"
      ? t("research.format_unregistered")
      : t("research.format_unknown");

  return (
    <section className="research-detail-section research-export-section" aria-labelledby="research-export">
      <h3 id="research-export">{t("research.export_reference")}</h3>
      <p className="research-muted">{t("research.export_reference_help")}</p>
      <p className="research-policy-note" role="status">
        <strong>{t("research.entitlement_state")}</strong>{" "}
        {decision === "allowed" ? t("research.entitlement_allowed") : decision === "unknown" ? t("research.entitlement_unknown") : t("research.entitlement_restricted")}
      </p>
      {decision === "unknown" && <p className="research-policy-note">{t("research.export_unknown_policy")} {t("research.export_unknown_explanation")}</p>}
      {decision === "restricted" && <p className="research-policy-note">{t("research.export_restricted_policy")} {t("research.export_restricted_explanation")}</p>}
      <div className="research-format-block">
        <strong>{t("research.format_availability")}</strong>
        <ul className="research-format-list">
          {formatRows.map((row) => (
            <li key={row.format}><span className="research-format-name">{row.format}</span><span className={`research-format-state research-format-${row.availability}`}>{formatStateLabel(row.availability)}</span></li>
          ))}
        </ul>
      </div>
      {showControl && (
        <div className="research-export-controls">
          <label htmlFor="research-export-format">{t("research.format")}</label>
          <select id="research-export-format" value={exportFormat} onChange={(event) => onExportFormatChange(event.target.value as ExportFormat)}>{requestableFormats.map((format) => <option key={format} value={format}>{format.toUpperCase()}</option>)}</select>
          <button type="button" className="button primary" onClick={onExport} disabled={exportBusy}>{exportBusy ? t("status.loading") : t("research.request_artifact_reference")}</button>
        </div>
      )}
      {canRequest && requestableFormats.length === 0 && <p className="research-policy-note">{t("research.export_no_registered_format")}</p>}
      {exportState.status === "restricted" && <p className="research-policy-note" role="status">{t("research.export_answer_restricted")}</p>}
      {exportState.status === "format_unregistered" && (
        <div className="research-policy-note" role="status">
          <p>{t("research.export_answer_format_unregistered")}</p>
          <p><strong>{t("research.export_answer_available_formats")}</strong> {exportState.availableFormats && exportState.availableFormats.length ? exportState.availableFormats.join(", ") : t("research.export_answer_no_formats")}</p>
        </div>
      )}
      {exportState.status === "file_missing" && <p className="research-policy-note" role="status">{t("research.export_answer_file_missing")}</p>}
      {exportState.status === "unavailable" && (
        <p className="research-policy-note" role="status">{t("research.export_answer_unavailable")} {exportState.code ? <code className="research-issue-code">{exportState.code}</code> : null}</p>
      )}
      {exportState.status === "granted" && (
        <>
          <dl className="research-detail-grid">
            <DetailValue label={t("research.artifact_reference")} value={researchDisplayValue(exportState.artifactRef, t("research.unknown"))} />
            <DetailValue label={t("research.artifact_id")} value={researchDisplayValue(exportState.artifactId, t("research.unknown"))} />
            <DetailValue label={t("research.artifact_sha256")} value={researchDisplayValue(exportState.artifactSha256, t("research.unknown"))} />
            <DetailValue label={t("research.format")} value={researchDisplayValue(exportState.format, t("research.unknown"))} />
            <DetailValue label={t("research.entitlement_state")} value={researchDisplayValue(exportState.entitlementPolicy, t("research.unknown"))} />
          </dl>
          <p className="research-artifact-result" role="status"><strong>{t("research.artifact_reference")}</strong> {researchDisplayValue(exportState.artifactRef, t("research.unknown"))} {t("research.export_reference_only")}</p>
        </>
      )}
      {exportError && <p className="research-export-error" role="alert">{exportError}</p>}
    </section>
  );
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
  exportState,
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
  exportState: ResearchExportState;
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

      <ArtifactDeliverySection
        t={t}
        decision={exportDecision}
        exportState={exportState}
        exportError={exportError}
        exportFormat={exportFormat}
        onExportFormatChange={onExportFormatChange}
        onExport={onExport}
        exportBusy={exportBusy}
      />
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
      <PanelHeader title={<span id="research-dataset-table-title">{t("research.dataset_snapshots")}</span>} meta={t("research.dataset_snapshots_help")} />
      {error && <div className="research-catalog-error" role="alert">{error}</div>}
      {/* Scrollable region: focusable so keyboard users can scroll a wide table
          (axe: scrollable-region-focusable). */}
      <div className="research-table-wrap" tabIndex={0} role="region" aria-labelledby="research-dataset-table-title">
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
  const [catalogReloadKey, setCatalogReloadKey] = useState(0);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [detailState, setDetailState] = useState<DetailState>({ status: "idle" });
  const [detailRetryKey, setDetailRetryKey] = useState(0);
  const [exportFormat, setExportFormat] = useState<ExportFormat>("parquet");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportState, setExportState] = useState<ResearchExportState>(() => researchExportStateFromAnswer(null));
  const [exportError, setExportError] = useState<string | null>(null);
  const [specDraft, setSpecDraft] = useState<ResearchSpecDraft>(EMPTY_RESEARCH_SPEC_DRAFT);
  const [validationState, setValidationState] = useState<ValidationState>({ status: "idle" });
  const [buildState, setBuildState] = useState<BuildState>({ status: "idle" });
  const catalogCoordinator = useRef(new WorkspaceLoadCoordinator()).current;
  const detailCoordinator = useRef(new WorkspaceLoadCoordinator()).current;
  const exportCoordinator = useRef(new WorkspaceLoadCoordinator()).current;
  const validateCoordinator = useRef(new WorkspaceLoadCoordinator()).current;
  const buildCoordinator = useRef(new WorkspaceLoadCoordinator()).current;
  const selectedDatasetIdRef = useRef<string | null>(null);
  const pendingSnapshotRef = useRef<string | null>(null);

  const spec = useMemo(() => researchSpecFromDraft(specDraft), [specDraft]);
  const specFingerprint = useMemo(() => researchSpecFingerprint(spec), [spec]);
  const missingInputs = useMemo(() => researchSpecMissingInputs(specDraft), [specDraft]);
  const lastValidation = validationState.status === "ready"
    ? { fingerprint: validationState.fingerprint, ok: validationState.outcome.ok }
    : null;
  const buildGate = researchBuildGate(lastValidation, specFingerprint);
  const specFingerprintRef = useRef(specFingerprint);

  useEffect(() => {
    specFingerprintRef.current = specFingerprint;
  }, [specFingerprint]);

  useEffect(() => {
    selectedDatasetIdRef.current = selectedDatasetId;
  }, [selectedDatasetId]);

  useEffect(() => {
    catalogCoordinator.cancel();
    detailCoordinator.cancel();
    exportCoordinator.cancel();
    validateCoordinator.cancel();
    buildCoordinator.cancel();
    selectedDatasetIdRef.current = null;
    pendingSnapshotRef.current = null;
    setFeatures([]);
    setTargets([]);
    setDatasets([]);
    setCatalogIdentityKey(null);
    setSelectedDatasetId(null);
    setCatalogError(null);
    setCatalogLoading(true);
    setDetailState({ status: "idle" });
    setExportBusy(false);
    setExportState(researchExportStateFromAnswer(null));
    setExportError(null);
    // Validation and build answers are identity-scoped evidence, so they are
    // dropped with the session. The typed spec draft is the operator's own
    // input and is deliberately kept.
    setValidationState({ status: "idle" });
    setBuildState({ status: "idle" });
  }, [buildCoordinator, catalogCoordinator, detailCoordinator, exportCoordinator, identityKey, validateCoordinator]);

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
      // A freshly built snapshot is selected only once the refreshed catalog
      // contains it, so the selection guard cannot drop it as unknown.
      const pendingSnapshotId = pendingSnapshotRef.current;
      if (
        pendingSnapshotId
        && datasetResult.ok
        && datasetResult.value.data.some((dataset) => dataset.dataset_snapshot_id === pendingSnapshotId)
      ) {
        pendingSnapshotRef.current = null;
        selectedDatasetIdRef.current = pendingSnapshotId;
        setSelectedDatasetId(pendingSnapshotId);
      }
    }).catch(() => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (catalogCoordinator.isCurrent(load.generation, load.signal) && liveIdentity === requestedIdentity) setCatalogError(t("research.catalog_error"));
    }).finally(() => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      if (catalogCoordinator.isCurrent(load.generation, load.signal) && liveIdentity === requestedIdentity) { setCatalogLoading(false); catalogCoordinator.finish(load.generation); }
    });
    return () => catalogCoordinator.cancel();
  }, [catalogCoordinator, catalogReloadKey, identityKey, t]);

  useEffect(() => {
    if (selectedDatasetId && !datasets.some((dataset) => dataset.dataset_snapshot_id === selectedDatasetId)) {
      setSelectedDatasetId(null);
      setDetailState({ status: "idle" });
    }
  }, [datasets, selectedDatasetId]);

  useEffect(() => {
    if (!selectedDatasetId) { detailCoordinator.cancel(); setDetailState({ status: "idle" }); setExportState(researchExportStateFromAnswer(null)); setExportError(null); return; }
    const requestedDatasetId = selectedDatasetId;
    const requestedIdentity = identityKey;
    const load = detailCoordinator.start();
    setDetailState({ status: "loading" });
    setExportState(researchExportStateFromAnswer(null));
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
    setExportState(researchExportStateFromAnswer(null));
    setExportError(null);
  }, [exportCoordinator, identityKey, selectedDatasetId]);

  useEffect(() => () => {
    exportCoordinator.cancel();
    validateCoordinator.cancel();
    buildCoordinator.cancel();
  }, [buildCoordinator, exportCoordinator, validateCoordinator]);

  const tabs = useMemo(() => VIEWS.map((id) => ({ id, label: t(`research.tab.${id}`) })), [t]);
  const catalogVisible = catalogIdentityKey === identityKey;
  const visibleDatasets = catalogVisible ? datasets : [];
  const visibleFeatures = catalogVisible ? features : [];
  const visibleTargets = catalogVisible ? targets : [];
  const visibleSelectedDatasetId = catalogVisible ? selectedDatasetId : null;
  const createdDetail = buildState.status === "created"
    && detailState.status === "ready"
    && detailState.detail.dataset_snapshot_id === buildState.summary.datasetSnapshotId
    ? detailState.detail
    : null;

  async function validateSpecDraft() {
    const requestedSpec = spec;
    const requestedFingerprint = specFingerprint;
    const requestedIdentity = identityKey;
    const load = validateCoordinator.start();
    setValidationState({ status: "busy" });
    const result = await loadWorkspaceEndpoint(
      (options) => apiOutcome(() => api.validateResearchDataset(requestedSpec, options)),
      { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS },
    );
    const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
    if (!validateCoordinator.isCurrent(load.generation, load.signal) || liveIdentity !== requestedIdentity) return;
    validateCoordinator.finish(load.generation);
    if (!result.ok) {
      setValidationState({ status: "error", message: safeResearchErrorMessage(result.error.message, genericErrorMessages(t)) });
      return;
    }
    const answer = result.value.ok ? result.value.data : result.value.failure;
    setValidationState({
      status: "ready",
      outcome: researchValidationOutcome(answer),
      fingerprint: requestedFingerprint,
    });
  }

  async function buildSnapshot() {
    if (!buildGate.canBuild) return;
    const requestedSpec = spec;
    const requestedIdentity = identityKey;
    const load = buildCoordinator.start();
    setBuildState({ status: "busy" });
    const result = await loadWorkspaceEndpoint(
      (options) => apiOutcome(() => api.buildResearchDataset(requestedSpec, options)),
      { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS },
    );
    const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
    if (!buildCoordinator.isCurrent(load.generation, load.signal) || liveIdentity !== requestedIdentity) return;
    buildCoordinator.finish(load.generation);
    if (!result.ok) {
      setBuildState({ status: "error", message: t("research.build_error") });
      return;
    }
    if (!result.value.ok) {
      const failure = result.value.failure;
      const status = researchHttpStatus(failure);
      setBuildState({
        status: "rejected",
        code: researchAnswerCode(failure),
        issues: researchIssuesFromAnswer(failure),
        // A 401/403 is an identity refusal, not a spec problem: the structured
        // issues (when any) stay the authoritative reason for everything else.
        message: status === 401 || status === 403
          ? researchRequestErrorMessage(failure, specRequestMessages(t))
          : t("research.build_rejected_help"),
      });
      return;
    }
    const summary = researchBuildSummary(result.value.data);
    if (!summary) {
      setBuildState({ status: "error", message: t("research.build_error") });
      return;
    }
    setBuildState({ status: "created", summary });
    pendingSnapshotRef.current = summary.datasetSnapshotId;
    setCatalogReloadKey((value) => value + 1);
  }

  async function requestArtifactReference() {
    if (!selectedDatasetId || detailState.status !== "ready") return;
    const policy = detailState.detail.entitlement_envelope?.export_policy;
    if (!researchExportCanRequest(researchExportDecision(policy))) return;
    const requestedDatasetId = selectedDatasetId;
    const requestedIdentity = identityKey;
    const load = exportCoordinator.start();
    setExportBusy(true);
    setExportState(researchExportStateFromAnswer(null));
    setExportError(null);
    void loadWorkspaceEndpoint(
      (options) => apiOutcome(() => api.exportResearchDataset(requestedDatasetId, { format: exportFormat }, options)),
      { signal: load.signal, retries: 0, timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS },
    ).then((result) => {
      const liveIdentity = useApiStore.getState().currentUser?.principal_id ?? "anonymous";
      const current = exportCoordinator.isCurrent(load.generation, load.signal)
        && isCurrentResearchSelection(selectedDatasetIdRef.current, requestedDatasetId, liveIdentity, requestedIdentity);
      if (!current) return;
      if (!result.ok) {
        setExportError(safeResearchErrorMessage(result.error.message, genericErrorMessages(t)));
        return;
      }
      const answer = result.value.ok ? result.value.data : result.value.failure;
      const answerState = researchExportStateFromAnswer(answer);
      setExportState(answerState);
      // A server-reported format list is authoritative: never leave a refused
      // format selected while offering only the formats the backend registered.
      const options = researchFormatOptions(answerState.availableFormats)
        .filter((format): format is ExportFormat => (RESEARCH_EXPORT_FORMATS as readonly string[]).includes(format));
      if (options.length && !options.includes(exportFormat)) setExportFormat(options[0]);
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

  return <div className={`research-data-page research-view-${activeView}`}>
    <div className="research-task-tabs-wrap"><WorkspaceTabs idPrefix="research-task" label={t("research.title")} tabs={tabs} activeId={activeView} panelId="research-task-panel" className="research-task-tabs" onActivate={(view) => setActiveView(view as ResearchViewId)} /></div>
    {activeView === "datasets" && <ResearchSpecPanel t={t} draft={specDraft} onDraftChange={(key, value) => setSpecDraft((current) => ({ ...current, [key]: value }))} missingInputs={missingInputs} validationState={validationState} buildState={buildState} gate={buildGate} createdDetail={createdDetail} onValidate={() => void validateSpecDraft()} onBuild={() => void buildSnapshot()} />}
    {activeView === "datasets" && <div className="research-master-detail" id="research-task-panel" role="tabpanel" aria-label={t("research.tab.datasets")}><DatasetCatalog t={t} datasets={visibleDatasets} loading={catalogLoading} error={catalogError} selectedId={visibleSelectedDatasetId} onSelect={(datasetId) => { selectedDatasetIdRef.current = datasetId; setSelectedDatasetId(datasetId); }} /><DatasetDetailRail t={t} selectedId={visibleSelectedDatasetId} detailState={detailState} onRetry={() => setDetailRetryKey((value) => value + 1)} onExport={() => void requestArtifactReference()} exportFormat={exportFormat} onExportFormatChange={setExportFormat} exportBusy={exportBusy} exportState={exportState} exportError={exportError} /></div>}
    {activeView === "products" && <DataProductCatalogue t={t} />}
    {activeView !== "datasets" && activeView !== "products" && <RegistryTable t={t} type={activeView} features={visibleFeatures} targets={visibleTargets} loading={catalogLoading} error={catalogError} />}
  </div>;
}
