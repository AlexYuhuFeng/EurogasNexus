import type {
  ApiMeta,
  PipelineHealthDTO,
  RuntimeDbStatusDTO,
  SourceSystemDTO,
} from "@/api/client";

type Translate = (key: string) => string;
type ReadinessState = "ready" | "partial" | "blocked";

interface ReleaseReadinessRow {
  key: string;
  label: string;
  state: ReadinessState;
  value: string;
  detail: string;
}

interface RuntimeWorkspaceProps {
  meta: ApiMeta | null;
  runtimeDb: RuntimeDbStatusDTO | null;
  pipelineHealth: PipelineHealthDTO | null;
  sources: SourceSystemDTO[];
  streamingActive: boolean;
  endpointErrors: Record<string, string>;
  t: Translate;
  onRefreshHealth: () => Promise<void>;
}

function formatHealthTime(value: string | null | undefined): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function readinessStateLabel(state: ReadinessState, t: Translate): string {
  if (state === "ready") return t("runtime.state_ready");
  if (state === "partial") return t("runtime.state_partial");
  return t("runtime.state_blocked");
}

function isLicensedCommercialSource(source: SourceSystemDTO): boolean {
  const sourceKey = source.source_system.toUpperCase().replace(/[\s-]+/g, "_");
  const commercialSourceKeys = ["ARGUS", "EEX", "ICE_OCM", "ICIS", "KPLER", "PLATTS", "TRAYPORT"];
  return (
    source.entitlement_scope === "licensed" ||
    source.credential_requirements.length > 0 ||
    commercialSourceKeys.includes(sourceKey)
  );
}

function needsCredential(source: SourceSystemDTO): boolean {
  return (
    source.credential_requirements.length > 0 &&
    source.credential_state !== "configured" &&
    source.credential_state !== "not_required"
  );
}

function needsLiveCertification(source: SourceSystemDTO): boolean {
  return (
    isLicensedCommercialSource(source) &&
    source.live_record_count > 0 &&
    !source.certification_allows_live
  );
}

export function RuntimeWorkspace({
  meta,
  runtimeDb,
  pipelineHealth,
  sources,
  streamingActive,
  endpointErrors,
  t,
  onRefreshHealth,
}: RuntimeWorkspaceProps) {
  const health = pipelineHealth;
  const freshnessEntries = health ? Object.entries(health.quote_freshness) : [];
  const endpointFailureCount = Object.keys(endpointErrors).length;
  const dbReady = Boolean(
    runtimeDb?.database_url_present &&
      runtimeDb.connectivity.ok &&
      runtimeDb.missing_tables.length === 0,
  );
  const workflowReadySources = sources.filter((source) => source.workflow_ready).length;
  const commercialSourceRows = sources.filter(isLicensedCommercialSource);
  const credentialBlockers = commercialSourceRows.filter(needsCredential);
  const certificationBlockers = commercialSourceRows.filter(needsLiveCertification);
  const noExecutionBoundaryReady = Boolean(meta?.research_only && meta.human_review_required);
  const sourceOperationsState: ReadinessState =
    sources.length === 0 ? "blocked" : endpointFailureCount > 0 ? "partial" : "ready";
  const sourceOperationsDetail =
    sources.length === 0
      ? t("runtime.no_sources")
      : endpointFailureCount > 0
        ? `${endpointFailureCount} ${t("runtime.endpoint_failures")}`
        : t("runtime.source_operations_detail");
  const commercialCertificationState: ReadinessState =
    commercialSourceRows.length === 0
      ? "blocked"
      : credentialBlockers.length === 0 && certificationBlockers.length === 0
        ? "ready"
        : "blocked";
  const commercialCertificationDetail =
    commercialSourceRows.length === 0
      ? t("runtime.commercial_source_blocked_detail")
      : `${credentialBlockers.length} ${t("runtime.credential_blockers")} / ${certificationBlockers.length} ${t("runtime.certification_blockers")}`;
  const releaseReadinessRows: ReleaseReadinessRow[] = [
    {
      key: "runtime_schema",
      label: t("runtime.runtime_schema"),
      state: dbReady ? "ready" : "blocked",
      value: dbReady ? t("runtime.state_ready") : t("runtime.state_blocked"),
      detail: dbReady
        ? t("runtime.runtime_schema_ready_detail")
        : t("runtime.runtime_schema_blocked_detail"),
    },
    {
      key: "source_operations",
      label: t("runtime.source_operations"),
      state: sourceOperationsState,
      value: `${workflowReadySources}/${sources.length} ${t("runtime.workflow_ready_sources")}`,
      detail: sourceOperationsDetail,
    },
    {
      key: "streaming_delivery",
      label: t("runtime.stream_delivery"),
      state: streamingActive ? "ready" : "partial",
      value: streamingActive ? t("stream.live") : t("stream.polling_fallback"),
      detail: streamingActive
        ? t("runtime.stream_delivery_ready_detail")
        : t("runtime.stream_delivery_partial_detail"),
    },
    {
      key: "commercial_source_certification",
      label: t("runtime.commercial_source_certification"),
      state: commercialCertificationState,
      value: `${commercialSourceRows.length} ${t("runtime.active_commercial_sources")}`,
      detail: commercialCertificationDetail,
    },
    {
      key: "no_execution_boundary",
      label: t("runtime.no_execution_boundary"),
      state: noExecutionBoundaryReady ? "ready" : "blocked",
      value: noExecutionBoundaryReady ? t("runtime.state_ready") : t("runtime.state_blocked"),
      detail: noExecutionBoundaryReady
        ? t("runtime.no_execution_boundary_detail")
        : t("runtime.no_execution_boundary_blocked_detail"),
    },
    {
      key: "external_security_acceptance",
      label: t("runtime.security_acceptance"),
      state: "blocked",
      value: t("runtime.external_gate"),
      detail: t("runtime.security_acceptance_detail"),
    },
  ];
  const releaseBlockers = [
    ...(!dbReady ? [t("runtime.runtime_schema_blocked_detail")] : []),
    ...(sources.length === 0 ? [t("runtime.no_sources")] : []),
    ...(commercialSourceRows.length === 0 ? [t("runtime.commercial_source_blocked_detail")] : []),
    ...Object.keys(endpointErrors).map((key) => `${t("runtime.endpoint_failures")}: ${key}`),
    ...credentialBlockers.map((source) => `${t("runtime.credential_blockers")}: ${source.source_system}`),
    ...certificationBlockers.map((source) => `${t("runtime.certification_blockers")}: ${source.source_system}`),
    t("runtime.security_acceptance_detail"),
  ];

  return (
    <div className="workspace-grid runtime-page">
      <div className="workspace-panel span-3 runtime-release-readiness">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.runtime")}</span>
          <strong>{t("runtime.release_readiness")}</strong>
        </div>
        <div className="runtime-readiness-grid">
          {releaseReadinessRows.map((row) => (
            <div key={`readiness-${row.key}`} className="runtime-readiness-row">
              <div>
                <strong>{row.label}</strong>
                <span>{row.detail}</span>
              </div>
              <span className={`runtime-readiness-state ${row.state}`}>
                {readinessStateLabel(row.state, t)}
              </span>
              <small>{row.value}</small>
            </div>
          ))}
        </div>
        <div className="runtime-blocker-list compact">
          <strong>{t("runtime.release_blockers")}</strong>
          {releaseBlockers.slice(0, 8).map((blocker) => (
            <span key={`release-blocker-${blocker}`}>{blocker}</span>
          ))}
        </div>
      </div>

      <div className="workspace-panel span-3 runtime-commercial-sources">
        <div className="panel-title-row">
          <h3>{t("runtime.commercial_sources")}</h3>
          <span>{commercialSourceRows.length} {t("panel.records")}</span>
        </div>
        <div className="data-table">
          <div className="data-table-row header four">
            <span>{t("panel.source")}</span>
            <span>{t("sources.credential_state")}</span>
            <span>{t("runtime.certification_stage")}</span>
            <span>{t("runtime.effective_source")}</span>
          </div>
          {commercialSourceRows.map((source) => (
            <div key={`runtime-commercial-source-${source.source_id}`} className="data-table-row four">
              <strong>{source.source_system}</strong>
              <span>{source.credential_state}</span>
              <span className={`source-cert source-cert-${source.certification_stage}`}>
                {source.certification_stage}
              </span>
              <span>{source.effective_source_system}</span>
            </div>
          ))}
          {commercialSourceRows.length === 0 && (
            <div className="data-table-row four">
              <strong>{t("runtime.no_sources")}</strong><span>n/a</span><span>n/a</span><span>n/a</span>
            </div>
          )}
        </div>
      </div>

      <div className="workspace-panel">
        <h3>{t("panel.governance")}</h3>
        {meta ? (
          <div className="metric-grid">
            <div><span>{t("status.research_only")}</span><strong>{String(meta.research_only)}</strong></div>
            <div><span>{t("status.human_review_required")}</span><strong>{String(meta.human_review_required)}</strong></div>
            <div><span>{t("status.source")}</span><strong>{meta.source_references.join(", ") || "n/a"}</strong></div>
          </div>
        ) : <p className="panel-copy">{t("data.unavailable")}</p>}
      </div>
      <div className="workspace-panel span-2">
        <h3>{t("status.db")}</h3>
        {runtimeDb ? (
          <div className="metric-grid three-column">
            <div><span>{t("status.db")}</span><strong>{runtimeDb.connectivity.ok ? "ok" : "failed"}</strong></div>
            <div><span>{t("status.alembic")}</span><strong>{runtimeDb.alembic_revision ?? "unavailable"}</strong></div>
            <div><span>{t("status.missing_tables")}</span><strong>{runtimeDb.missing_tables.length}</strong></div>
          </div>
        ) : <p className="panel-copy">{t("data.unavailable")}</p>}
      </div>
      <div className="workspace-panel span-3">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.runtime")}</span>
          <strong>{t("runtime.pipeline_health")}</strong>
        </div>
        <div className="metric-grid three-column">
          <div><span>{t("runtime.open_alerts")}</span><strong>{health?.open_alerts ?? "n/a"}</strong></div>
          <div><span>{t("runtime.latest_opportunity")}</span><strong>{formatHealthTime(health?.latest_opportunity_detected_at_utc)}</strong></div>
          <div><span>{t("runtime.generated_at")}</span><strong>{formatHealthTime(health?.generated_at_utc)}</strong></div>
        </div>
        <button type="button" className="runtime-health-refresh" onClick={() => void onRefreshHealth()}>
          {t("market.refresh")}
        </button>
        <div className="data-table">
          <div className="data-table-row header four">
            <span>{t("panel.source")}</span>
            <span>{t("runtime.source_status")}</span>
            <span>{t("runtime.consecutive_failures")}</span>
            <span>{t("runtime.last_success")}</span>
          </div>
          {(health?.sources ?? []).map((source) => (
            <div key={`pipeline-source-${source.source_name}`} className="data-table-row four">
              <strong>{source.source_name}</strong>
              <span className={`pipeline-status pipeline-status-${source.status}`}>{source.status}</span>
              <span>{source.consecutive_failures}</span>
              <span>
                {source.finished_at_utc ? formatHealthTime(source.finished_at_utc) : formatHealthTime(source.started_at_utc)}
              </span>
            </div>
          ))}
          {(health?.sources ?? []).length === 0 && (
            <div className="data-table-row four"><strong>{t("runtime.no_sources")}</strong><span>n/a</span><span>n/a</span><span>n/a</span></div>
          )}
        </div>
      </div>
      <div className="workspace-panel span-2">
        <h3>{t("runtime.quote_freshness")}</h3>
        <div className="data-table">
          <div className="data-table-row header three">
            <span>{t("panel.source")}</span>
            <span>{t("runtime.recent_5m")}</span>
            <span>{t("runtime.latest_observation")}</span>
          </div>
          {freshnessEntries.map(([source, entry]) => (
            <div key={`freshness-${source}`} className="data-table-row three">
              <strong>{source}</strong>
              <span>{entry.count_recent_5m}</span>
              <span>{formatHealthTime(entry.latest_observed_at_utc)}</span>
            </div>
          ))}
          {freshnessEntries.length === 0 && (
            <div className="data-table-row three"><strong>{t("runtime.no_sources")}</strong><span>n/a</span><span>n/a</span></div>
          )}
        </div>
      </div>
    </div>
  );
}
