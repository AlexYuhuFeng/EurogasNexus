import type { ApiMeta, RuntimeDbStatusDTO } from "@/api/client";

type Translate = (key: string) => string;

interface RuntimeWorkspaceProps {
  meta: ApiMeta | null;
  runtimeDb: RuntimeDbStatusDTO | null;
  t: Translate;
}

export function RuntimeWorkspace({ meta, runtimeDb, t }: RuntimeWorkspaceProps) {
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
    </div>
  );
}
