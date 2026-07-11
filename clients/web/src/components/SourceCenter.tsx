import type { FormEventHandler } from "react";
import type {
  CapacityObsDTO,
  CredentialProviderDTO,
  FlowObsDTO,
  LngObsDTO,
  SourceCategoryPostureDTO,
  SourceSystemDTO,
  StorageObsDTO,
  TsoTariffDTO,
} from "@/api/client";

interface SourceStats {
  total: number;
  active: number;
  issues: number;
  records: number;
  missingCredentials: number;
}

interface SourceCenterProps {
  t: (key: string) => string;
  sources: SourceSystemDTO[];
  sourceCategories: string[];
  sourceCategory: string;
  sourceCategoryCounts: Map<string, number>;
  sourceStats: SourceStats;
  sourcePostureRows: SourceCategoryPostureDTO[];
  filteredSources: SourceSystemDTO[];
  selectedSource: SourceSystemDTO | null;
  selectedCredentialProvider: CredentialProviderDTO | undefined;
  selectedSourceCredentialProvider: CredentialProviderDTO | null;
  credentialProviders: CredentialProviderDTO[];
  credentialProvider: string;
  credentialLabel: string;
  credentialValue: string;
  credentialMessage: string | null;
  flows: FlowObsDTO[];
  capacity: CapacityObsDTO[];
  storage: StorageObsDTO[];
  lng: LngObsDTO[];
  tsoAccessCount: number;
  tsoTariffs: TsoTariffDTO[];
  latestCapacityRows: CapacityObsDTO[];
  onSourceCategoryChange: (category: string, nextSourceId: string | null) => void;
  onSourceSelect: (sourceId: string) => void;
  onCredentialProviderChange: (providerId: string) => void;
  onCredentialLabelChange: (label: string) => void;
  onCredentialValueChange: (value: string) => void;
  onCredentialSubmit: FormEventHandler<HTMLFormElement>;
  sourceLabel: (prefix: string, value: string | null | undefined) => string;
  categoryProviderSummary: (category: string) => string;
  sourceNextAction: (source: SourceSystemDTO | null) => string;
  formatSourceTimestamp: (value: string | null | undefined) => string;
}

function sourcePriority(source: SourceSystemDTO): number {
  if (!source.workflow_ready && ["error", "failed", "unreachable", "degraded"].includes(source.connectivity_status)) return 0;
  if (!source.workflow_ready && (source.credential_state === "missing" || source.connectivity_status === "credential_required")) return 1;
  if (source.live_record_count === 0 && source.preview_substitute_record_count === 0) return 2;
  if (source.connectivity_status === "stale") return 3;
  if (source.operational_status === "active_simulated") return 4;
  return 5;
}

function sourceMode(source: SourceSystemDTO, t: (key: string) => string): string {
  if (source.preview_substitute_status === "active") return t("sources.mode_simulated");
  if (source.credential_provider_id) return t("sources.mode_licensed");
  return t("sources.mode_public");
}

export function SourceCenter({
  t,
  sources,
  sourceCategories,
  sourceCategory,
  sourceCategoryCounts,
  sourceStats,
  sourcePostureRows,
  filteredSources,
  selectedSource,
  selectedCredentialProvider,
  selectedSourceCredentialProvider,
  credentialProviders,
  credentialProvider,
  credentialLabel,
  credentialValue,
  credentialMessage,
  flows,
  capacity,
  storage,
  lng,
  tsoAccessCount,
  tsoTariffs,
  latestCapacityRows,
  onSourceCategoryChange,
  onSourceSelect,
  onCredentialProviderChange,
  onCredentialLabelChange,
  onCredentialValueChange,
  onCredentialSubmit,
  sourceLabel,
  categoryProviderSummary,
  sourceNextAction,
  formatSourceTimestamp,
}: SourceCenterProps) {
  const sortedSources = [...filteredSources].sort((left, right) => {
    const priorityDelta = sourcePriority(left) - sourcePriority(right);
    return priorityDelta || left.source_system.localeCompare(right.source_system);
  });

  return (
    <div className="workspace-grid sources-page source-center">
      <div className="workspace-panel span-3 source-overview">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.sources")}</span>
          <strong>{t("sources.title")}</strong>
        </div>
        <p>{t("sources.subtitle")}</p>
        <div className="metric-grid four-column source-kpi-grid">
          <div><span>{t("sources.total_sources")}</span><strong>{sourceStats.total}</strong></div>
          <div><span>{t("sources.active_sources")}</span><strong>{sourceStats.active}</strong></div>
          <div><span>{t("sources.issue_sources")}</span><strong>{sourceStats.issues}</strong></div>
          <div><span>{t("sources.runtime_records")}</span><strong>{sourceStats.records.toLocaleString()}</strong></div>
        </div>
      </div>

      <div className="workspace-panel span-3 source-posture-board">
        <div className="panel-title-row">
          <h3>{t("sources.posture_board")}</h3>
          <span>{t("sources.next_action")}</span>
        </div>
        <div className="source-category-filter" role="tablist" aria-label={t("sources.categories")}>
          {sourceCategories.map((category) => {
            const nextSource = category === "all"
              ? sources[0]
              : sources.find((source) => source.category === category);
            return (
              <button
                key={`source-category-${category}`}
                type="button"
                role="tab"
                aria-selected={sourceCategory === category}
                className={sourceCategory === category ? "source-category-chip active" : "source-category-chip"}
                title={categoryProviderSummary(category)}
                onClick={() => onSourceCategoryChange(category, nextSource?.source_id ?? null)}
              >
                <span>{sourceLabel("sources.category", category)}</span>
                <strong>{category === "all" ? sources.length : sourceCategoryCounts.get(category) ?? 0}</strong>
              </button>
            );
          })}
        </div>
        <div className="source-posture-grid compact">
          {sourcePostureRows.map((row) => (
            <button
              key={`source-posture-row-${row.category}`}
              type="button"
              className={sourceCategory === row.category ? "source-posture-row active" : "source-posture-row"}
              onClick={() => {
                const nextSource = sources.find((source) => source.category === row.category);
                onSourceCategoryChange(row.category, nextSource?.source_id ?? null);
              }}
            >
              <strong>{sourceLabel("sources.category", row.category)}</strong>
              <span>{row.workflow_ready_sources}/{row.registered_sources} {t("sources.workflow_ready")}</span>
              <span>{row.sources_needing_attention} {t("context.issues")}</span>
              <small>{t(`sources.action.${row.next_action}`)}</small>
            </button>
          ))}
        </div>
      </div>

      <div className="workspace-panel span-3 source-catalog-panel">
        <div className="panel-title-row">
          <h3>{t("sources.registered_feeds")}</h3>
          <span>{sortedSources.length} / {sources.length} · {sourceStats.missingCredentials} {t("sources.missing_credentials")}</span>
        </div>
        <div className="source-operations-table-wrap">
          <table className="source-operations-table">
            <thead>
              <tr>
                <th>{t("panel.status")}</th>
                <th>{t("sources.source")}</th>
                <th>{t("sources.mode")}</th>
                <th>{t("sources.last_success")}</th>
                <th>{t("panel.records")}</th>
                <th>{t("sources.next_action")}</th>
              </tr>
            </thead>
            <tbody>
              {sortedSources.map((source) => (
                <tr
                  key={`source-row-${source.source_id}`}
                  className={selectedSource?.source_id === source.source_id ? "active" : undefined}
                >
                  <td>
                    <span className={`source-status source-status-${source.operational_status}`}>
                      {sourceLabel("sources.status", source.operational_status)}
                    </span>
                  </td>
                  <td>
                    <button type="button" className="source-row-select" onClick={() => onSourceSelect(source.source_id)}>
                      <strong>{source.source_system}</strong>
                      <small>{sourceLabel("sources.category", source.category)}</small>
                    </button>
                  </td>
                  <td><span>{sourceMode(source, t)}</span></td>
                  <td><span>{formatSourceTimestamp(source.effective_last_success_at_utc)}</span></td>
                  <td>
                    <strong>{source.effective_record_count.toLocaleString()}</strong>
                    {source.operational_status === "active_simulated" && <small>{source.effective_source_system}</small>}
                  </td>
                  <td>
                    <button type="button" className="source-diagnostic-action" onClick={() => onSourceSelect(source.source_id)}>
                      {sourceNextAction(source)}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="workspace-panel source-detail-panel">
        <div className="panel-title-row">
          <h3>{selectedSource?.source_system ?? t("sources.no_source")}</h3>
          {selectedSource && (
            <span className={`source-status source-status-${selectedSource.operational_status}`}>
              {sourceLabel("sources.status", selectedSource.operational_status)}
            </span>
          )}
        </div>
        {selectedSource && (
          <>
            <p>{selectedSource.description}</p>
            <div className="metric-grid two-column source-detail-metrics">
              <div><span>{t("sources.category_label")}</span><strong>{sourceLabel("sources.category", selectedSource.category)}</strong></div>
              <div><span>{t("sources.entitlement")}</span><strong>{selectedSource.entitlement_scope}</strong></div>
              <div><span>{t("sources.native_status")}</span><strong>{sourceLabel("sources.status", selectedSource.connectivity_status)}</strong></div>
              <div><span>{t("sources.effective_source")}</span><strong>{selectedSource.effective_source_system}</strong></div>
              <div><span>{t("sources.credential_state")}</span><strong>{sourceLabel("sources.credential", selectedSource.credential_state)}</strong></div>
              <div><span>{t("sources.freshness")}</span><strong>{selectedSource.freshness_expectation_minutes ? `${selectedSource.freshness_expectation_minutes}m` : "n/a"}</strong></div>
              <div><span>{t("sources.last_success")}</span><strong>{formatSourceTimestamp(selectedSource.effective_last_success_at_utc)}</strong></div>
              <div><span>{t("sources.last_failure")}</span><strong>{formatSourceTimestamp(selectedSource.last_failure_at_utc)}</strong></div>
            </div>
            <div className="source-datasets">
              <span>{t("panel.datasets")}</span>
              <div>{selectedSource.datasets.map((dataset) => <strong key={`${selectedSource.source_id}-${dataset}`}>{dataset}</strong>)}</div>
            </div>
            <div className="source-diagnostics">
              <span>{t("sources.diagnostics")}</span>
              <div>
                {selectedSource.diagnostics.map((diagnostic) => (
                  <strong key={`${selectedSource.source_id}-${diagnostic}`}>{sourceLabel("sources.diagnostic", diagnostic)}</strong>
                ))}
              </div>
            </div>
            <div className="source-next-action">
              <span>{t("sources.next_action")}</span>
              <strong>{sourceNextAction(selectedSource)}</strong>
            </div>
            {selectedSource.preview_substitute_source_system && (
              <div className="source-next-action source-preview-substitute">
                <span>{t("sources.preview_substitute")}</span>
                <strong>
                  {selectedSource.preview_substitute_source_system} / {sourceLabel("sources.status", selectedSource.preview_substitute_status)}
                </strong>
                <small>
                  {selectedSource.preview_substitute_record_count.toLocaleString()} {t("panel.records")} / {t("sources.preview_substitute_active")}
                </small>
              </div>
            )}
            <p className="source-ingestion-note">
              {t("sources.latest_ingestion")}: {selectedSource.last_ingestion_status ?? "n/a"}
              {selectedSource.last_ingestion_message ? ` / ${selectedSource.last_ingestion_message}` : ""}
            </p>
          </>
        )}
      </div>

      <div className="workspace-panel source-credential-panel">
        <h3>{t("panel.credentials")}</h3>
        <p>
          {selectedSource?.credential_provider_id
            ? `${selectedSource.credential_provider_id}: ${sourceLabel("sources.credential", selectedSource.credential_state)}`
            : t("credentials.not_required")}
        </p>
        <form className="credential-form source-credential-form" onSubmit={onCredentialSubmit}>
          <select
            aria-label={t("panel.credentials")}
            value={credentialProvider}
            onChange={(event) => onCredentialProviderChange(event.target.value)}
          >
            {credentialProviders.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>)}
          </select>
          <input
            aria-label={t("credentials.label")}
            autoComplete="username"
            value={credentialLabel}
            onChange={(event) => onCredentialLabelChange(event.target.value)}
            placeholder={t("credentials.label")}
          />
          <input
            aria-label={t("credentials.api_key")}
            type="password"
            autoComplete="current-password"
            value={credentialValue}
            disabled={!selectedCredentialProvider?.credential_required}
            onChange={(event) => onCredentialValueChange(event.target.value)}
            placeholder={selectedCredentialProvider?.credential_required ? t("credentials.api_key") : t("credentials.not_required")}
          />
          <button type="submit" disabled={!selectedCredentialProvider?.credential_required || !credentialValue}>{t("credentials.save")}</button>
        </form>
        {selectedSourceCredentialProvider && (
          <div className="credential-status-card">
            <span>{selectedSourceCredentialProvider.display_name}</span>
            <strong>{sourceLabel("sources.credential", selectedSourceCredentialProvider.status)}</strong>
            <small>{selectedSourceCredentialProvider.last_test_status ?? t("sources.not_tested")}</small>
          </div>
        )}
        {credentialMessage && <p>{credentialMessage}</p>}
      </div>

      <div className="workspace-panel span-3 source-runtime-panel">
        <div className="section-heading">
          <span className="eyebrow">{t("data.runtime")}</span>
          <strong>{t("panel.infrastructure")}</strong>
        </div>
        <div className="metric-grid six-column source-kpi-grid">
          <div><span>{t("panel.flows")}</span><strong>{flows.filter((item) => item.source_system === "ENTSOG").length}</strong></div>
          <div><span>{t("panel.capacity")}</span><strong>{capacity.filter((item) => item.source_system === "ENTSOG").length}</strong></div>
          <div><span>{t("panel.tso_access")}</span><strong>{tsoAccessCount}</strong></div>
          <div><span>{t("panel.storage")}</span><strong>{storage.filter((item) => item.source_system === "GIE").length}</strong></div>
          <div><span>{t("panel.lng")}</span><strong>{lng.filter((item) => item.source_system === "GIE").length}</strong></div>
          <div><span>{t("panel.tariffs")}</span><strong>{tsoTariffs.length}</strong></div>
        </div>
        <div className="source-table-split">
          <div className="data-table">
            <div className="data-table-row header four"><span>{t("panel.point")}</span><span>{t("panel.direction")}</span><span>{t("panel.capacity_type")}</span><span>mcm/d</span></div>
            {latestCapacityRows.map((row) => (
              <div key={`capacity-row-${row.observation_id}`} className="data-table-row four">
                <strong>{row.point_name}</strong>
                <span>{row.direction}</span>
                <span>{row.capacity_type}</span>
                <span>{row.capacity_mcm_d.toFixed(2)}</span>
              </div>
            ))}
            {latestCapacityRows.length === 0 && (
              <div className="data-table-row four"><strong>n/a</strong><span>ENTSOG</span><span>{t("data.unavailable")}</span><span>n/a</span></div>
            )}
          </div>
          <div className="data-table tariff-table">
            <div className="data-table-row header four"><span>{t("panel.point")}</span><span>{t("panel.direction")}</span><span>{t("panel.product")}</span><span>{t("panel.tariff")}</span></div>
            {tsoTariffs.slice(0, 5).map((tariff) => (
              <div key={`tariff-page-${tariff.tariff_id}`} className="data-table-row four">
                <strong>{tariff.source_point_name}</strong>
                <span>{tariff.direction}</span>
                <span>{tariff.capacity_product}</span>
                <span>{tariff.tariff_value.toFixed(4)} {tariff.currency}/MWh</span>
              </div>
            ))}
            {tsoTariffs.length === 0 && (
              <div className="data-table-row four"><strong>n/a</strong><span>TSO</span><span>{t("data.unavailable")}</span><span>n/a</span></div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
