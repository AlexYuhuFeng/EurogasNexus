import { useEffect, useState } from "react";
import type {
  CredentialProviderDTO,
  RuntimeDbStatusDTO,
  SourceSystemDTO,
} from "@/api/client";
import {
  clearApiBaseUrl,
  configuredApiBaseUrl,
  defaultApiBaseUrl,
  saveApiBaseUrl,
  testApiBaseUrl,
} from "@/api/client";
import type { ThemeMode } from "@/stores/theme";

type Translate = (key: string) => string;

const PREFERENCE_STORAGE_KEY = "eurogas.settings.preferences";

interface SettingsPreferences {
  default_currency: string;
  energy_unit: string;
  volume_unit: string;
  price_basis: string;
  session_timezone: string;
  map_density: string;
  refresh_profile: string;
}

type ApiConnectionState =
  | { kind: "connected"; version: string; profile: string }
  | { kind: "failed"; error: string };

interface SettingsCenterProps {
  t: Translate;
  language: string;
  mode: ThemeMode;
  dataStatus: string;
  runtimeDb: RuntimeDbStatusDTO | null;
  sources: SourceSystemDTO[];
  credentialProviders: CredentialProviderDTO[];
  counts: {
    nodes: number;
    edges: number;
    routes: number;
  };
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
  onOpenSources: () => void;
  onBackendBaseChanged: () => Promise<void>;
}

const defaultPreferences: SettingsPreferences = {
  default_currency: "GBP",
  energy_unit: "MWh",
  volume_unit: "MWh/d",
  price_basis: "hub_day_ahead",
  session_timezone: "Europe/London",
  map_density: "balanced",
  refresh_profile: "manual_review",
};

function readStoredPreferences(): SettingsPreferences {
  try {
    const raw = localStorage.getItem(PREFERENCE_STORAGE_KEY);
    if (!raw) return defaultPreferences;
    const parsed = JSON.parse(raw) as Partial<SettingsPreferences>;
    return {
      ...defaultPreferences,
      ...Object.fromEntries(
        Object.entries(parsed).filter(([, value]) => typeof value === "string" && value.trim().length > 0),
      ),
    };
  } catch {
    return defaultPreferences;
  }
}

export function SettingsCenter({
  t,
  language,
  mode,
  dataStatus,
  runtimeDb,
  sources,
  credentialProviders,
  counts,
  onLanguageChange,
  onModeChange,
  onOpenSources,
  onBackendBaseChanged,
}: SettingsCenterProps) {
  const [preferences, setPreferences] = useState<SettingsPreferences>(() => readStoredPreferences());
  const [apiBaseUrl, setApiBaseUrl] = useState(() => configuredApiBaseUrl());
  const [apiConnectionState, setApiConnectionState] = useState<ApiConnectionState | null>(null);
  const [testingApi, setTestingApi] = useState(false);

  useEffect(() => {
    localStorage.setItem(PREFERENCE_STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);

  useEffect(() => {
    setApiBaseUrl(configuredApiBaseUrl());
  }, [dataStatus]);

  const updatePreference = (key: keyof SettingsPreferences, value: string) => {
    setPreferences((current) => ({ ...current, [key]: value }));
  };

  const configuredCredentials = credentialProviders.filter((provider) => provider.configured).length;
  const missingCredentials = credentialProviders.filter(
    (provider) => provider.credential_required && !provider.configured,
  ).length;
  const activeSources = sources.filter((source) => source.workflow_ready).length;
  const licensedServices = sources.filter((source) => source.entitlement_scope === "licensed").length;
  const serviceRows = credentialProviders.slice(0, 8);
  const credentialStatusLabel = (provider: CredentialProviderDTO) => {
    if (!provider.credential_required) return t("credentials.not_required");
    if (provider.status === "disabled") return t("sources.credential.disabled");
    return provider.configured ? t("settings.configured") : t("settings.missing");
  };

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
      <div className="workspace-panel span-3 settings-overview-panel">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.settings")}</span>
          <strong>{t("settings.title")}</strong>
        </div>
        <p className="panel-copy">{t("settings.subtitle")}</p>
        <div className="metric-grid four-column settings-status-strip">
          <div><span>{t("settings.active_sources")}</span><strong>{activeSources}</strong></div>
          <div><span>{t("settings.api_services")}</span><strong>{credentialProviders.length}</strong></div>
          <div><span>{t("settings.runtime_api")}</span><strong>{t(`data.${dataStatus}`)}</strong></div>
          <div><span>{t("settings.runtime_db")}</span><strong>{runtimeDb?.connectivity.ok ? "ok" : "n/a"}</strong></div>
        </div>
      </div>

      <div className="workspace-panel span-3 settings-backend-panel">
        <div className="panel-title-row">
          <div>
            <h3>{t("settings.backend_api")}</h3>
            <p className="panel-copy">{t("settings.backend_api_help")}</p>
          </div>
          <span className={`status-badge status-${dataStatus}`}>{t(`data.${dataStatus}`)}</span>
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
      </div>

      <div className="workspace-panel settings-panel settings-unit-panel">
        <h3>{t("settings.display_preferences")}</h3>
        <label>
          {t("settings.language")}
          <select value={language} onChange={(event) => onLanguageChange(event.target.value)}>
            <option value="en">English</option>
            <option value="zh-CN">{t("settings.chinese")}</option>
          </select>
        </label>
        <label>
          {t("settings.appearance")}
          <select value={mode} onChange={(event) => onModeChange(event.target.value as ThemeMode)}>
            <option value="light">{t("theme.light")}</option>
            <option value="dark">{t("theme.dark")}</option>
            <option value="system">{t("theme.system")}</option>
          </select>
        </label>
        <label>
          {t("settings.default_currency")}
          <select
            value={preferences.default_currency}
            onChange={(event) => updatePreference("default_currency", event.target.value)}
          >
            <option value="GBP">GBP</option>
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
          </select>
        </label>
        <label>
          {t("settings.energy_unit")}
          <select value={preferences.energy_unit} onChange={(event) => updatePreference("energy_unit", event.target.value)}>
            <option value="MWh">MWh</option>
            <option value="therm">therm</option>
            <option value="kWh">kWh</option>
          </select>
        </label>
        <label>
          {t("settings.volume_unit")}
          <select value={preferences.volume_unit} onChange={(event) => updatePreference("volume_unit", event.target.value)}>
            <option value="MWh/d">MWh/d</option>
            <option value="GWh/d">GWh/d</option>
            <option value="mcm/d">mcm/d</option>
          </select>
        </label>
        <label>
          {t("settings.price_basis")}
          <select value={preferences.price_basis} onChange={(event) => updatePreference("price_basis", event.target.value)}>
            <option value="hub_day_ahead">{t("settings.price_basis_day_ahead")}</option>
            <option value="within_day">{t("settings.price_basis_within_day")}</option>
            <option value="month_ahead">{t("settings.price_basis_month_ahead")}</option>
          </select>
        </label>
      </div>

      <div className="workspace-panel settings-panel settings-session-panel">
        <h3>{t("settings.session_defaults")}</h3>
        <label>
          {t("settings.session_timezone")}
          <select
            value={preferences.session_timezone}
            onChange={(event) => updatePreference("session_timezone", event.target.value)}
          >
            <option value="Europe/London">Europe/London</option>
            <option value="Europe/Amsterdam">Europe/Amsterdam</option>
            <option value="Europe/Berlin">Europe/Berlin</option>
            <option value="UTC">UTC</option>
          </select>
        </label>
        <label>
          {t("settings.map_density")}
          <select value={preferences.map_density} onChange={(event) => updatePreference("map_density", event.target.value)}>
            <option value="balanced">{t("settings.map_density_balanced")}</option>
            <option value="compact">{t("settings.map_density_compact")}</option>
            <option value="operations">{t("settings.map_density_operations")}</option>
          </select>
        </label>
        <label>
          {t("settings.refresh_profile")}
          <select
            value={preferences.refresh_profile}
            onChange={(event) => updatePreference("refresh_profile", event.target.value)}
          >
            <option value="manual_review">{t("settings.refresh_manual_review")}</option>
            <option value="market_watch">{t("settings.refresh_market_watch")}</option>
            <option value="low_bandwidth">{t("settings.refresh_low_bandwidth")}</option>
          </select>
        </label>
        <div className="settings-preference-preview">
          <span>{t("settings.preference_preview")}</span>
          <strong>
            {preferences.default_currency}/{preferences.energy_unit} · {preferences.volume_unit} · {preferences.session_timezone}
          </strong>
          <small>{t("settings.stored_locally")}</small>
        </div>
      </div>

      <div className="workspace-panel settings-service-panel">
        <div className="panel-title-row">
          <h3>{t("settings.service_access")}</h3>
          <button type="button" onClick={onOpenSources}>{t("settings.manage_api_keys")}</button>
        </div>
        <div className="metric-grid two-column">
          <div><span>{t("settings.configured")}</span><strong>{configuredCredentials}</strong></div>
          <div><span>{t("settings.missing")}</span><strong>{missingCredentials}</strong></div>
          <div><span>{t("settings.licensed_services")}</span><strong>{licensedServices}</strong></div>
          <div><span>{t("panel.records")}</span><strong>{sources.reduce((total, source) => total + source.effective_record_count, 0)}</strong></div>
        </div>
        <div className="settings-service-list">
          {serviceRows.map((provider) => (
            <div key={`settings-provider-${provider.provider_id}`} className="settings-service-row">
              <span>
                <strong>{provider.display_name}</strong>
                <small>{provider.provider_id}</small>
              </span>
              <em className={!provider.credential_required || provider.configured ? "ready" : "attention"}>
                {credentialStatusLabel(provider)}
              </em>
            </div>
          ))}
          {serviceRows.length === 0 && <p className="panel-copy">{t("settings.no_api_services")}</p>}
        </div>
      </div>

      <div className="workspace-panel settings-boundary-panel">
        <h3>{t("settings.backend_boundary")}</h3>
        <p className="panel-copy">{t("settings.boundary_copy")}</p>
        <div className="settings-guardrail-list">
          <span>{t("settings.no_client_db_url")}</span>
          <span>{t("settings.no_client_secret_storage")}</span>
          <span>{t("settings.human_review")}</span>
          <span>{t("settings.decision_support_only")}</span>
        </div>
      </div>

      <div className="workspace-panel">
        <h3>{t("app.title")}</h3>
        <div className="metric-grid">
          <div><span>{t("map.nodes")}</span><strong>{counts.nodes}</strong></div>
          <div><span>{t("map.edges")}</span><strong>{counts.edges}</strong></div>
          <div><span>{t("map.routes")}</span><strong>{counts.routes}</strong></div>
        </div>
      </div>
    </div>
  );
}
