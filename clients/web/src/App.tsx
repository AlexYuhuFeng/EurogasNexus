import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { GasNetworkMap } from "@/components/GasNetworkMap";
import { useApiStore } from "@/stores/api";
import { useThemeStore } from "@/stores/theme";
import "./styles/app.css";

export default function App() {
  const { t, i18n } = useTranslation();
  const { mode, setMode } = useThemeStore();
  const {
    nodes,
    edges,
    sources,
    markets,
    flows,
    storage,
    lng,
    routes,
    credentialProviders,
    runtimeDb,
    dataStatus,
    meta,
    loading,
    error,
    credentialMessage,
    fetchWorkspace,
    saveProviderCredential,
  } = useApiStore();
  const [credentialProvider, setCredentialProvider] = useState("GIE");
  const [credentialLabel, setCredentialLabel] = useState("default");
  const [credentialValue, setCredentialValue] = useState("");
  const selectedCredentialProvider = useMemo(
    () => credentialProviders.find((provider) => provider.provider_id === credentialProvider),
    [credentialProvider, credentialProviders]
  );

  useEffect(() => {
    fetchWorkspace();
  }, [fetchWorkspace]);

  async function onCredentialSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCredentialProvider?.credential_required || !credentialValue.trim()) return;
    await saveProviderCredential(credentialProvider, credentialValue, credentialLabel || "default");
    setCredentialValue("");
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>{t("app.title")}</h1>
          <p>{t("app.subtitle")}</p>
        </div>
        <div className="header-controls">
          <span className={`status-badge status-${dataStatus}`}>{t(`data.${dataStatus}`)}</span>
          <select value={i18n.language} onChange={(event) => i18n.changeLanguage(event.target.value)}>
            <option value="en">English</option>
            <option value="zh-CN">中文</option>
          </select>
          <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
            <option value="light">{t("theme.light")}</option>
            <option value="dark">{t("theme.dark")}</option>
            <option value="system">{t("theme.system")}</option>
          </select>
        </div>
      </header>

      <nav className="app-nav">
        {["network", "market", "scenario", "strategy", "review", "sources", "glossary", "runtime", "settings"].map(
          (item) => (
            <button key={item} className="nav-btn">
              {t(`nav.${item}`)}
            </button>
          )
        )}
      </nav>

      <main className="app-main">
        <section className="map-container" id="map">
          <GasNetworkMap nodes={nodes} edges={edges} routes={routes} themeMode={mode} />
          <div className="map-overlay">
            <span>
              {t("map.nodes")}: {nodes.length}
            </span>
            <span>
              {t("map.edges")}: {edges.length}
            </span>
            <span>
              {t("map.routes")}: {routes.length}
            </span>
          </div>
        </section>

        <aside className="sidebar">
          {error && <div className="panel alert">{error}</div>}
          {loading && <div className="panel">{t("status.loading")}</div>}

          <div className="panel">
            <h3>{t("panel.routes")}</h3>
            <div className="route-list">
              {routes.map((route) => (
                <div key={route.route_id} className="route-row">
                  <span>
                    {route.from_node_id} {"->"} {route.to_node_id}
                  </span>
                  <strong>{Math.round(route.confidence * 100)}%</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <h3>{t("panel.market")}</h3>
            <div className="metric-grid">
              {markets.slice(0, 3).map((market) => (
                <div key={market.observation_id}>
                  <span>
                    {market.market_venue} {market.product}
                  </span>
                  <strong>
                    {market.price} {market.currency}
                  </strong>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <h3>{t("panel.sources")}</h3>
            <p>
              {sources.length} {t("panel.sources_registered")}
            </p>
            <ul className="source-list">
              {sources.slice(0, 5).map((source) => (
                <li key={source.source_id}>
                  {source.source_system}: {source.status}
                  {source.live_record_count > 0 ? ` (${source.live_record_count})` : ""}
                </li>
              ))}
            </ul>
          </div>

          <div className="panel">
            <h3>{t("panel.infrastructure")}</h3>
            <div className="metric-grid">
              <div>
                <span>{t("panel.flows")}</span>
                <strong>{flows.filter((item) => item.source_system === "ENTSOG").length}</strong>
              </div>
              <div>
                <span>{t("panel.storage")}</span>
                <strong>{storage.filter((item) => item.source_system === "GIE").length}</strong>
              </div>
              <div>
                <span>{t("panel.lng")}</span>
                <strong>{lng.filter((item) => item.source_system === "GIE").length}</strong>
              </div>
            </div>
          </div>

          <div className="panel">
            <h3>{t("panel.credentials")}</h3>
            <form className="credential-form" onSubmit={onCredentialSubmit}>
              <select value={credentialProvider} onChange={(event) => setCredentialProvider(event.target.value)}>
                {credentialProviders.map((provider) => (
                  <option key={provider.provider_id} value={provider.provider_id}>
                    {provider.display_name}
                  </option>
                ))}
              </select>
              <input
                value={credentialLabel}
                onChange={(event) => setCredentialLabel(event.target.value)}
                placeholder={t("credentials.label")}
              />
              <input
                type="password"
                value={credentialValue}
                disabled={!selectedCredentialProvider?.credential_required}
                onChange={(event) => setCredentialValue(event.target.value)}
                placeholder={
                  selectedCredentialProvider?.credential_required
                    ? t("credentials.api_key")
                    : t("credentials.not_required")
                }
              />
              <button type="submit" disabled={!selectedCredentialProvider?.credential_required || !credentialValue}>
                {t("credentials.save")}
              </button>
            </form>
            {credentialMessage && <p>{credentialMessage}</p>}
            <ul className="source-list">
              {credentialProviders.map((provider) => (
                <li key={provider.provider_id}>
                  {provider.display_name}: {provider.configured ? provider.redacted_preview : provider.status}
                </li>
              ))}
            </ul>
          </div>

          <div className="panel">
            <h3>{t("panel.governance")}</h3>
            {meta && (
              <>
                <p>
                  {t("status.research_only")}: {String(meta.research_only)}
                </p>
                <p>
                  {t("status.human_review_required")}: {String(meta.human_review_required)}
                </p>
                <p>
                  {t("status.source")}: {meta.source_references.join(", ")}
                </p>
              </>
            )}
            {runtimeDb && (
              <>
                <p>
                  {t("status.db")}: {runtimeDb.connectivity.ok ? "ok" : "failed"}
                </p>
                <p>
                  {t("status.alembic")}: {runtimeDb.alembic_revision ?? "unavailable"}
                </p>
                <p>
                  {t("status.missing_tables")}: {runtimeDb.missing_tables.length}
                </p>
              </>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
