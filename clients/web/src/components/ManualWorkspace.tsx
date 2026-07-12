import type { RuntimeDbStatusDTO } from "@/api/client";

type Translate = (key: string) => string;

interface ManualWorkspaceProps {
  runtimeDb: RuntimeDbStatusDTO | null;
  activeSourceCount: number;
  tariffCount: number;
  openOrderCount: number;
  t: Translate;
}

const WORKSPACE_GUIDE_KEYS = [
  "network",
  "capacity",
  "market",
  "contracts",
  "strategy",
  "review",
  "orders",
  "sources",
] as const;

export function ManualWorkspace({
  runtimeDb,
  activeSourceCount,
  tariffCount,
  openOrderCount,
  t,
}: ManualWorkspaceProps) {
  return (
    <div className="workspace-grid manual-page">
      <div className="workspace-panel span-3">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.manual")}</span>
          <strong>{t("manual.title")}</strong>
        </div>
        <p className="panel-copy">{t("manual.subtitle")}</p>
      </div>
      <div className="workspace-panel span-2">
        <h3>{t("manual.workspace_map")}</h3>
        <div className="manual-step-list">
          {WORKSPACE_GUIDE_KEYS.map((key) => (
            <div key={key}><strong>{t(`nav.${key}`)}</strong><span>{t(`manual.${key}`)}</span></div>
          ))}
        </div>
      </div>
      <div className="workspace-panel">
        <h3>{t("manual.operating_boundary")}</h3>
        <p className="panel-copy">{t("manual.boundary_copy")}</p>
        <div className="review-warning-list">
          <span>{t("manual.api_only")}</span>
          <span>{t("manual.no_execution")}</span>
          <span>{t("manual.no_client_db")}</span>
        </div>
      </div>
      <div className="workspace-panel span-3">
        <h3>{t("manual.release_readiness")}</h3>
        <div className="metric-grid four-column">
          <div><span>{t("status.db")}</span><strong>{runtimeDb?.connectivity.ok ? "ok" : "check"}</strong></div>
          <div><span>{t("sources.active_sources")}</span><strong>{activeSourceCount}</strong></div>
          <div><span>{t("panel.tariffs")}</span><strong>{tariffCount}</strong></div>
          <div><span>{t("portfolio.open_orders")}</span><strong>{openOrderCount}</strong></div>
        </div>
      </div>
    </div>
  );
}
