import type {
  ApiMeta,
  PipelineHealthDTO,
  RuntimeDbStatusDTO,
} from "@/api/client";

type Translate = (key: string) => string;

interface RuntimeWorkspaceProps {
  meta: ApiMeta | null;
  runtimeDb: RuntimeDbStatusDTO | null;
  pipelineHealth: PipelineHealthDTO | null;
  t: Translate;
  onRefreshHealth: () => Promise<void>;
}

function formatHealthTime(value: string | null | undefined): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function RuntimeWorkspace({
  meta,
  runtimeDb,
  pipelineHealth,
  t,
  onRefreshHealth,
}: RuntimeWorkspaceProps) {
  const health = pipelineHealth;
  const freshnessEntries = health ? Object.entries(health.quote_freshness) : [];
  return (
    <div className="workspace-grid runtime-page">
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
