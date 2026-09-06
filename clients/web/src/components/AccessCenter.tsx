import { useEffect, useState } from "react";
import {
  api,
  type AccessApiKeyDTO,
  type AccessUserDTO,
  type AuditEventDTO,
  type CurrentUserDTO,
} from "@/api/client";
import { PanelHeader, StatusBadge, WorkspaceTabs } from "@/components/ui";

type AccessViewId = "users" | "api_keys" | "audit" | "sso";
const ACCESS_VIEWS: AccessViewId[] = ["users", "api_keys", "audit", "sso"];

interface AccessCenterProps {
  currentUser: CurrentUserDTO | null;
  t: (key: string) => string;
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export function AccessCenter({ currentUser, t }: AccessCenterProps) {
  const [activeView, setActiveView] = useState<AccessViewId>("users");
  const [users, setUsers] = useState<AccessUserDTO[]>([]);
  const [keys, setKeys] = useState<AccessApiKeyDTO[]>([]);
  const [audit, setAudit] = useState<AuditEventDTO[]>([]);
  const [sso, setSso] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = Boolean(currentUser?.permissions.includes("identity.manage"));

  useEffect(() => {
    if (!isAdmin) {
      setError("access.requires_admin");
      return;
    }
    setError(null);
    Promise.all([
      api.accessUsers().then((response) => setUsers(response.data)),
      api.accessApiKeys().then((response) => setKeys(response.data)),
      api.auditEvents({ limit: "100" }).then((response) => setAudit(response.data)),
      api.ssoProfile().then((response) => setSso(response.data)),
    ]).catch(() => setError("access.load_failed"));
  }, [isAdmin]);

  async function updateUserAccess(
    principalId: string,
    roles: string[],
    dataScopes: string[],
  ) {
    await api.patchAccessUser(principalId, { roles, data_scopes: dataScopes });
    const response = await api.accessUsers();
    setUsers(response.data);
  }

  async function toggleUserStatus(user: AccessUserDTO) {
    const next = user.status === "ACTIVE" ? "DISABLED" : "ACTIVE";
    await api.patchAccessUser(user.principal_id, { status: next });
    const response = await api.accessUsers();
    setUsers(response.data);
  }

  async function revokeKey(keyId: string) {
    await api.revokeAccessApiKey(keyId);
    const response = await api.accessApiKeys();
    setKeys(response.data);
  }

  if (!isAdmin) {
    return (
      <div className="workspace-grid access-page">
        <div className="workspace-panel span-3">
          <PanelHeader title={t("access.title")} />
          <p className="panel-copy">{t("access.restricted")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`workspace-grid access-page access-view-${activeView}`}>
      <div className="workspace-panel span-3 access-admin-strip">
        <PanelHeader
          title={t("access.title")}
          meta={currentUser ? `${currentUser.display_name ?? currentUser.name} · ${currentUser.role}` : ""}
        />
        <p className="panel-copy">{t("access.subtitle")}</p>
      </div>
      <WorkspaceTabs
        idPrefix="access-tab"
        label={t("access.workspace_views")}
        tabs={ACCESS_VIEWS.map((view) => ({
          id: view,
          label: t(`access.view.${view}`),
          controls: "access-active-panel",
        }))}
        activeId={activeView}
        panelId="access-active-panel"
        className="access-view-tabs span-3"
        onActivate={(view) => setActiveView(view as AccessViewId)}
      />

      {error && <div className="workspace-panel span-3"><p className="panel-copy">{t(error)}</p></div>}

      {activeView === "users" && (
        <div id="access-active-panel" role="tabpanel" aria-labelledby="access-tab-users" className="workspace-panel span-3">
          <div className="data-table">
            <div className="data-table-row header six">
              <span>{t("access.user")}</span>
              <span>{t("access.identity_source")}</span>
              <span>{t("access.status")}</span>
              <span>{t("access.roles")}</span>
              <span>{t("access.data_access")}</span>
              <span>{t("access.actions")}</span>
            </div>
            {users.map((user) => (
              <div key={`access-user-${user.principal_id}`} className="data-table-row six">
                <strong>{user.display_name}</strong>
                <span>{user.identity_source}</span>
                <StatusBadge variant="source" status={user.status.toLowerCase()}>{user.status}</StatusBadge>
                <span>{user.roles.join(", ")}</span>
                <span>{user.data_scopes.join(", ") || "public"}</span>
                <span className="access-row-actions">
                  <button type="button" onClick={() => void toggleUserStatus(user)}>
                    {user.status === "ACTIVE" ? t("access.disable") : t("access.enable")}
                  </button>
                  <button type="button" onClick={() => void updateUserAccess(user.principal_id, user.roles, user.data_scopes)}>
                    {t("access.save")}
                  </button>
                </span>
              </div>
            ))}
            {users.length === 0 && (
              <div className="data-table-row six"><strong>{t("access.no_users")}</strong><span>n/a</span><span>n/a</span><span>n/a</span><span>n/a</span><span>n/a</span></div>
            )}
          </div>
        </div>
      )}

      {activeView === "api_keys" && (
        <div id="access-active-panel" role="tabpanel" aria-labelledby="access-tab-api_keys" className="workspace-panel span-3">
          <div className="data-table">
            <div className="data-table-row header five">
              <span>{t("access.key_label")}</span>
              <span>{t("access.key_owner")}</span>
              <span>{t("access.key_prefix")}</span>
              <span>{t("access.key_status")}</span>
              <span>{t("access.actions")}</span>
            </div>
            {keys.map((key) => (
              <div key={`access-key-${key.key_id}`} className="data-table-row five">
                <strong>{key.display_name}</strong>
                <span>{key.principal_id}</span>
                <span>{key.key_prefix}***</span>
                <StatusBadge variant="source" status={key.revoked_at_utc ? "revoked" : "active"}>{key.revoked_at_utc ? t("access.revoked") : t("access.active")}</StatusBadge>
                <button type="button" disabled={Boolean(key.revoked_at_utc)} onClick={() => void revokeKey(key.key_id)}>{t("access.revoke")}</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeView === "audit" && (
        <div id="access-active-panel" role="tabpanel" aria-labelledby="access-tab-audit" className="workspace-panel span-3">
          <div className="data-table">
            <div className="data-table-row header six">
              <span>{t("access.audit_time")}</span>
              <span>{t("access.audit_actor")}</span>
              <span>{t("access.audit_action")}</span>
              <span>{t("access.audit_resource")}</span>
              <span>{t("access.audit_outcome")}</span>
              <span>{t("access.audit_detail")}</span>
            </div>
            {audit.map((event) => (
              <div key={`audit-${event.event_id}`} className="data-table-row six">
                <span>{formatTime(event.event_ts_utc)}</span>
                <strong>{event.principal}</strong>
                <span>{event.action}</span>
                <span>{event.resource}</span>
                <span>{event.outcome}</span>
                <span>{event.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeView === "sso" && (
        <div id="access-active-panel" role="tabpanel" aria-labelledby="access-tab-sso" className="workspace-panel span-3">
          <PanelHeader title={t("access.sso_title")} />
          <pre className="access-sso-json">{JSON.stringify(sso, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
