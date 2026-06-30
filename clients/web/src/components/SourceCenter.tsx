import type { FormEventHandler } from "react";
import type {
  CapacityObsDTO,
  CredentialProviderDTO,
  FlowObsDTO,
  LngObsDTO,
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

export function SourceCenter({
  t,
  sources,
  sourceCategories,
  sourceCategory,
  sourceCategoryCounts,
  sourceStats,
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

      <div className="workspace-panel source-category-rail">
        <h3>{t("sources.categories")}</h3>
        <div className="source-category-list">
          {sourceCategories.map((category) => {
            const nextSource = category === "all"
              ? sources[0]
              : sources.find((source) => source.category === category);
            return (
              <button
                key={`source-category-${category}`}
                type="button"
                className={sourceCategory === category ? "source-category active" : "source-category"}
                onClick={() => onSourceCategoryChange(category, nextSource?.source_id ?? null)}
              >
                <span>
                  <span>{sourceLabel("sources.category", category)}</span>
                  <small>{categoryProviderSummary(category)}</small>
                </span>
                <strong>{category === "all" ? sources.length : sourceCategoryCounts.get(category) ?? 0}</strong>
              </button>
            );
          })}
        </div>
        <div className="source-category-summary">
          <span>{t("sources.missing_credentials")}</span>
          <strong>{sourceStats.missingCredentials}</strong>
        </div>
      </div>

      <div className="workspace-panel source-catalog-panel">
        <div className="panel-title-row">
          <h3>{t("sources.registered_feeds")}</h3>
          <span>{filteredSources.length} / {sources.length}</span>
        </div>
        <div className="source-health-grid">
          {filteredSources.map((source) => (
            <button
              key={`source-card-${source.source_id}`}
              type="button"
              className={selectedSource?.source_id === source.source_id ? "source-health-card active" : "source-health-card"}
              onClick={() => onSourceSelect(source.source_id)}
            >
              <span className={`source-status source-status-${source.connectivity_status}`}>
                {sourceLabel("sources.status", source.connectivity_status)}
              </span>
              <strong>{source.source_system}</strong>
              <small>{source.description}</small>
              <span className="source-card-meta">
                {sourceLabel("sources.category", source.category)} / {source.live_record_count.toLocaleString()} {t("panel.records")}
              </span>
              <span className="source-action-line">{sourceNextAction(source)}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="workspace-panel source-detail-panel">
        <div className="panel-title-row">
          <h3>{selectedSource?.source_system ?? t("sources.no_source")}</h3>
          {selectedSource && (
            <span className={`source-status source-status-${selectedSource.connectivity_status}`}>
              {sourceLabel("sources.status", selectedSource.connectivity_status)}
            </span>
          )}
        </div>
        {selectedSource && (
          <>
            <p>{selectedSource.description}</p>
            <div className="metric-grid two-column source-detail-metrics">
              <div><span>{t("sources.category_label")}</span><strong>{sourceLabel("sources.category", selectedSource.category)}</strong></div>
              <div><span>{t("sources.entitlement")}</span><strong>{selectedSource.entitlement_scope}</strong></div>
              <div><span>{t("sources.credential_state")}</span><strong>{sourceLabel("sources.credential", selectedSource.credential_state)}</strong></div>
              <div><span>{t("sources.freshness")}</span><strong>{selectedSource.freshness_expectation_minutes ? `${selectedSource.freshness_expectation_minutes}m` : "n/a"}</strong></div>
              <div><span>{t("sources.last_success")}</span><strong>{formatSourceTimestamp(selectedSource.last_success_at_utc)}</strong></div>
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
          <select value={credentialProvider} onChange={(event) => onCredentialProviderChange(event.target.value)}>
            {credentialProviders.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>)}
          </select>
          <input autoComplete="username" value={credentialLabel} onChange={(event) => onCredentialLabelChange(event.target.value)} placeholder={t("credentials.label")} />
          <input type="password" autoComplete="current-password" value={credentialValue} disabled={!selectedCredentialProvider?.credential_required} onChange={(event) => onCredentialValueChange(event.target.value)} placeholder={selectedCredentialProvider?.credential_required ? t("credentials.api_key") : t("credentials.not_required")} />
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
