import { useEffect, useState } from "react";
import { NotificationChannelsPanel } from "@/components/NotificationChannelsPanel";
import type {
  CredentialProviderDTO,
  RuntimeDbStatusDTO,
  RuntimeReleaseDTO,
  SourceSystemDTO,
} from "@/api/client";
import type { ReleaseCompatibility } from "@/app/releaseCompatibility";
import { CLIENT_BUILD_GIT_SHA, CLIENT_BUILD_GIT_REF, CLIENT_RELEASE_CHANNEL, CLIENT_APPLICATION_VERSION } from "@/app/releaseMetadata";
import {
  clearApiBaseUrl,
  configuredApiBaseUrl,
  configuredApiToken,
  configuredOperatorPrincipal,
  defaultApiBaseUrl,
  saveApiAuth,
  saveApiBaseUrl,
  testApiBaseUrl,
} from "@/api/client";
import {
  MAP_TILE_PROVIDERS,
  configuredMapTileProviderId,
  configuredMapTileToken,
  mapTileProviderById,
  saveMapTileProvider,
  saveMapTileToken,
} from "@/app/mapTileProviders";
import {
  RUNTIME_DATA_AVAILABILITY_CAPTION_KEY,
  dataPlaneState,
  runtimeDataAvailability,
  runtimeDataAvailabilityLabelKey,
} from "@/app/model/dataPlaneStatus";
import { StatusBadge } from "@/components/ui";
import { OrganisationDefaultsPanel, PersonalPreferencesPanel } from "@/components/PreferencesPanels";
import { PanelHelp } from "@/components/ui/PanelHelp";

type Translate = (key: string) => string;

type ApiConnectionState =
  | { kind: "connected"; version: string; profile: string }
  | { kind: "failed"; error: string };

interface SettingsCenterProps {
  t: Translate;
  language: string;
  /** Authenticated principal whose preferences are being edited. */
  principalId: string | null;
  /** Platform administrators edit the organisation defaults; everyone else reads them. */
  canManageOrganisation: boolean;
  dataStatus: string;
  runtimeDb: RuntimeDbStatusDTO | null;
  runtimeRelease: RuntimeReleaseDTO | null;
  releaseCompatibility: ReleaseCompatibility | null;
  sources: SourceSystemDTO[];
  credentialProviders: CredentialProviderDTO[];
  counts: {
    nodes: number;
    edges: number;
    routes: number;
  };
  onOpenSources: () => void;
  onBackendBaseChanged: () => Promise<void>;
}

export function SettingsCenter({
  t,
  language,
  principalId,
  canManageOrganisation,
  dataStatus,
  runtimeDb,
  runtimeRelease,
  releaseCompatibility,
  sources,
  credentialProviders,
  counts,
  onOpenSources,
  onBackendBaseChanged,
}: SettingsCenterProps) {
  const [apiBaseUrl, setApiBaseUrl] = useState(() => configuredApiBaseUrl());
  const [apiToken, setApiToken] = useState(() => configuredApiToken());
  const [operatorPrincipal, setOperatorPrincipal] = useState(() => configuredOperatorPrincipal());
  const [authMessage, setAuthMessage] = useState<string | null>(null);
  const [apiConnectionState, setApiConnectionState] = useState<ApiConnectionState | null>(null);
  const [testingApi, setTestingApi] = useState(false);
  const [mapTileProviderId, setMapTileProviderId] = useState(() => configuredMapTileProviderId());
  const [mapTileToken, setMapTileToken] = useState(() => configuredMapTileToken());
  const [mapTileMessage, setMapTileMessage] = useState<string | null>(null);
  const selectedMapTileProvider =
    mapTileProviderById(mapTileProviderId) ?? MAP_TILE_PROVIDERS[0];
  /**
   * The runtime store's own availability, as the workspace batch reported it - never a
   * statement that the readings inside that store are fresh or fit to decide on.
   */
  const runtimeAvailability = runtimeDataAvailability(dataStatus);

  useEffect(() => {
    setApiBaseUrl(configuredApiBaseUrl());
  }, [dataStatus]);


  const testAndApplyApiBase = async (value: string, useDefault = false) => {
    setTestingApi(true);
    setApiConnectionState(null);
    try {
      const health = await testApiBaseUrl(value);
      const normalized = useDefault ? clearApiBaseUrl() : saveApiBaseUrl(value);
      setApiBaseUrl(normalized);
      setApiConnectionState({ kind: "connected", version: health.version, profile: health.profile });
      await onBackendBaseChanged();
    } catch (error) {
      setApiConnectionState({ kind: "failed", error: String(error) });
    } finally {
      setTestingApi(false);
    }
  };

  const restoreDefaultApiBase = async () => {
    const fallback = defaultApiBaseUrl();
    setApiBaseUrl(fallback);
    await testAndApplyApiBase(fallback, true);
  };

  return (
    <div className="workspace-grid settings-page settings-preference-center">
      {/* The page header already names the page: its explanation is one fold, not a panel. */}
      <div className="span-3">
        <PanelHelp text={t("settings.subtitle")} label={t("panel.how_to_read")} />
      </div>

      {/* Personal preferences and the organisation defaults they override are one pair:
          side by side across the full width, not two thirds of a three-column row (#19). */}
      <div className="span-3 settings-preference-pair">
        <PersonalPreferencesPanel t={t} principalId={principalId} />
        <OrganisationDefaultsPanel t={t} canManage={canManageOrganisation} />
      </div>
      {canManageOrganisation && (
        <div className="workspace-panel span-3">
          <NotificationChannelsPanel t={t} />
        </div>
      )}

      <div className="workspace-panel span-3 settings-about-panel">
        <div className="panel-title-row">
          <div>
            <h2>{t("release.about_title")}</h2>
            <PanelHelp text={t("release.about_subtitle")} label={t("panel.how_to_read")} />
          </div>
          <span className={`status-badge status-${releaseCompatibility?.state === "compatible" ? "runtime" : "unavailable"}`}>
            {t(releaseCompatibility?.messageKey ?? "release.compat_unknown")}
          </span>
        </div>
        <div className="kv-list settings-about-grid">
          <div><span>{t("release.product")}</span><strong>Eurogas Nexus</strong></div>
          <div><span>{t("release.client_version")}</span><strong>{CLIENT_APPLICATION_VERSION}</strong></div>
          <div><span>{t("release.channel")}</span><strong>{CLIENT_RELEASE_CHANNEL}</strong></div>
          <div><span>{t("release.client_build")}</span><strong>{CLIENT_BUILD_GIT_SHA ?? t("release.not_reported")}</strong></div>
          <div><span>{t("release.server_version")}</span><strong>{runtimeRelease?.application_version ?? t("release.not_reported")}</strong></div>
          <div><span>{t("release.api_contract")}</span><strong>{runtimeRelease?.api_contract_version ?? t("release.not_reported")}</strong></div>
          <div><span>{t("release.db_schema_revision")}</span><strong>{runtimeRelease?.database_schema_revision ?? t("release.not_reported")}</strong></div>
          <div><span>{t("release.update_status")}</span><strong>{t("release.update_disabled_managed")}</strong></div>
        </div>
        {CLIENT_BUILD_GIT_REF && (
          <p className="settings-backend-message" role="status">
            {t("release.build_ref")}: {CLIENT_BUILD_GIT_REF}
          </p>
        )}
      </div>

      <div className="workspace-panel span-3 settings-backend-panel">
        <div className="panel-title-row">
          <div>
            <h2>{t("settings.backend_api")}</h2>
            <PanelHelp text={t("settings.backend_api_help")} label={t("panel.how_to_read")} />
          </div>
          <StatusBadge
            variant="runtime-readiness-state"
            status={dataPlaneState(dataStatus)}
            title={t("data.runtime_detail")}
          >
            {t(runtimeDataAvailabilityLabelKey(runtimeAvailability))}
          </StatusBadge>
        </div>
        <div className="settings-backend-form">
          <label>
            {t("settings.backend_api_url")}
            <input
              type="url"
              value={apiBaseUrl}
              spellCheck={false}
              onChange={(event) => setApiBaseUrl(event.target.value)}
              placeholder="https://nexus.example.com/api"
            />
          </label>
          <button type="button" disabled={testingApi} onClick={() => void testAndApplyApiBase(apiBaseUrl)}>
            {testingApi ? t("settings.backend_testing") : t("settings.backend_save_test")}
          </button>
          <button type="button" className="secondary-button" disabled={testingApi} onClick={() => void restoreDefaultApiBase()}>
            {t("settings.backend_use_default")}
          </button>
        </div>
        {apiConnectionState && (
          <p className="settings-backend-message" role="status">
            {apiConnectionState.kind === "connected"
              ? `${t("settings.backend_connected")} ${apiConnectionState.version} / ${apiConnectionState.profile}`
              : `${t("settings.backend_failed")}: ${apiConnectionState.error}`}
          </p>
        )}
        <div className="settings-auth-form" aria-label={t("settings.auth_help")}>
          <PanelHelp text={t("settings.auth_help")} label={t("panel.how_to_read")} />
          <div className="settings-auth-grid">
            <label className="settings-auth-field">
              <span>{t("settings.api_token")}</span>
              <input
                type="password"
                name="eurogas-api-token"
                value={apiToken}
                spellCheck={false}
                autoComplete="new-password"
                aria-label={t("settings.api_token")}
                onChange={(event) => setApiToken(event.target.value)}
                placeholder="EUROGAS_NEXUS_PUBLIC_API_TOKEN"
              />
            </label>
            <label className="settings-auth-field">
              <span>{t("settings.operator_principal")}</span>
              <input
                name="eurogas-operator-principal"
                value={operatorPrincipal}
                spellCheck={false}
                autoComplete="off"
                aria-label={t("settings.operator_principal")}
                onChange={(event) => setOperatorPrincipal(event.target.value)}
                placeholder="operator-name"
              />
            </label>
            <button
              className="settings-auth-save"
              type="button"
              onClick={() => {
                saveApiAuth(apiToken, operatorPrincipal);
                setAuthMessage(t("settings.auth_saved"));
              }}
            >
              {t("settings.auth_save")}
            </button>
          </div>
          {authMessage && (
            <p className="settings-backend-message" role="status">{authMessage}</p>
          )}
        </div>
      </div>


      <div className="workspace-panel settings-panel settings-unit-panel">
        <h2>{t("preferences.workstation_title")}</h2>
        <PanelHelp text={t("preferences.workstation_help")} label={t("panel.how_to_read")} />
        <label>
          {t("settings.map_tile_provider")}
          <select
            value={mapTileProviderId}
            onChange={(event) => setMapTileProviderId(event.target.value as typeof mapTileProviderId)}
          >
            {MAP_TILE_PROVIDERS.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {language.startsWith("zh") ? provider.labelZh : provider.label}
              </option>
            ))}
          </select>
        </label>
        {/*
          Owner decision D4: the product ships no third-party basemap, and the endpoints whose terms
          exclude commercial use say so where the operator picks one. A licence the operator is
          about to rely on belongs next to the control that selects it, not in a document.
        */}
        <p
          className={
            selectedMapTileProvider.licence === "not-for-commercial-use"
              ? "settings-map-licence is-restricted"
              : "settings-map-licence"
          }
          role="status"
        >
          <strong>
            {t(
              selectedMapTileProvider.licence === "not-for-commercial-use"
                ? "settings.map_tile_licence_evaluation"
                : selectedMapTileProvider.licence === "open-licence"
                  ? "settings.map_tile_licence_open"
                  : "settings.map_tile_licence_deployment",
            )}
          </strong>
          <small>{t(`settings.map_tile_provider_${selectedMapTileProvider.id}`)}</small>
          <small>{t(`settings.map_tile_availability_${selectedMapTileProvider.availability}`)}</small>
        </p>
        {selectedMapTileProvider.id === "custom" && (
          <p className="settings-map-licence">
            <small>{t("settings.map_tile_custom_detail")}</small>
          </p>
        )}
        <label>
          {t("settings.map_tile_token")}
          <input
            type="password"
            value={mapTileToken}
            spellCheck={false}
            autoComplete="off"
            onChange={(event) => setMapTileToken(event.target.value)}
            placeholder="Tianditu tk"
          />
        </label>
        <button
          type="button"
          onClick={() => {
            saveMapTileProvider(mapTileProviderId);
            saveMapTileToken(mapTileToken);
            setMapTileMessage(t("settings.map_tile_saved"));
          }}
        >
          {t("settings.map_tile_save")}
        </button>
        {mapTileMessage && (
          <p className="settings-backend-message" role="status">{mapTileMessage}</p>
        )}
      </div>

      {canManageOrganisation && (
        <div className="workspace-panel settings-service-panel">
          {/* Supplier connections have one home, Admin → Data Sources (#26): no counts here. */}
          <h2>{t("settings.service_access")}</h2>
          <p className="panel-copy">{t("settings.service_access_moved")}</p>
          <button type="button" className="secondary-button" onClick={onOpenSources}>{t("settings.open_data_sources")}</button>
        </div>
      )}

      <div className="workspace-panel settings-boundary-panel">
        <h2>{t("settings.backend_boundary")}</h2>
        <PanelHelp text={t("settings.boundary_copy")} label={t("panel.how_to_read")} />
        {/* Four constant guarantees: a one-line list, not four badges (#69). */}
        <p className="settings-guardrail-line muted">
          {[t("settings.no_client_db_url"), t("settings.no_client_secret_storage"), t("settings.human_review"), t("settings.decision_support_only")].join(" · ")}
        </p>
        {/* What this deployment's network reference holds; one line, not a card of its own. */}
        <p className="settings-reference-counts">
          {t("map.nodes")} <strong>{counts.nodes}</strong> · {t("map.edges")} <strong>{counts.edges}</strong> · {t("map.routes")} <strong>{counts.routes}</strong>
        </p>
      </div>
    </div>
  );
}
