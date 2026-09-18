import { useEffect, useState } from "react";
import {
  api,
  type AccessApiKeyDTO,
  type AccessUserDTO,
  type AuditEventDTO,
  type CurrentUserDTO,
} from "@/api/client";
import {
  apiKeyReadiness,
  apiKeyRequest,
  declaredScopes,
  roleRows,
  scopeFamilyRows,
  undeclaredScopes,
  type DataScopeCatalogue,
} from "@/app/model/accessCatalogueModel";
import { PanelHeader, StatusBadge, WorkspaceTabs } from "@/components/ui";

type AccessViewId = "users" | "api_keys" | "catalogue" | "audit" | "sso";
const ACCESS_VIEWS: AccessViewId[] = ["users", "api_keys", "catalogue", "audit", "sso"];

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
  // The two published catalogues. They are the deployment's own declaration of what a role grants
  // and which scope families exist, so the surface can stop editing grants against a vocabulary it
  // cannot see - and off them, the API-key form offers scopes that are declared rather than typed.
  const [roles, setRoles] = useState<Record<string, string[]> | null>(null);
  const [scopeCatalogue, setScopeCatalogue] = useState<DataScopeCatalogue | null>(null);
  // The create-key draft.
  const [keyPrincipalId, setKeyPrincipalId] = useState("");
  const [keyDisplayName, setKeyDisplayName] = useState("");
  const [keyExpiresOn, setKeyExpiresOn] = useState("");
  const [keyScopes, setKeyScopes] = useState<string[]>([]);
  // The bearer the route returned, held only long enough to show it once. It is never stored, never
  // re-read and cleared as soon as the operator leaves the view.
  const [issuedKey, setIssuedKey] = useState<string | null>(null);
  const [keyBusy, setKeyBusy] = useState(false);

  const isAdmin = Boolean(currentUser?.permissions.includes("identity.manage"));

  const draft = {
    principalId: keyPrincipalId,
    displayName: keyDisplayName,
    expiresOn: keyExpiresOn,
    scopes: keyScopes,
  };
  const readiness = apiKeyReadiness({ draft, catalogue: scopeCatalogue });
  const undeclared = undeclaredScopes(keyScopes, scopeCatalogue);
  const availableScopes = declaredScopes(scopeCatalogue);

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
      api.accessRoles().then((response) => setRoles(response.data)),
      api.accessDataScopes().then((response) => setScopeCatalogue(response.data)),
    ]).catch(() => setError("access.load_failed"));
  }, [isAdmin]);

  async function createKey() {
    const body = apiKeyRequest({ draft, catalogue: scopeCatalogue }, readiness);
    if (!body) return;
    setKeyBusy(true);
    setError(null);
    try {
      const response = await api.createAccessApiKey(body);
      // The route returns the bearer exactly once; the surface shows it and keeps only the record.
      setIssuedKey(response.data.api_key);
      const refreshed = await api.accessApiKeys();
      setKeys(refreshed.data);
      setKeyDisplayName("");
      setKeyScopes([]);
      setKeyExpiresOn("");
    } catch {
      setError("access.key.create_failed");
    } finally {
      setKeyBusy(false);
    }
  }

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
          <div className="data-table" tabIndex={0}>
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
          {/* Issuing a key had no surface: the panel could revoke one but not create one, so the
              most common administration act needed the API. The rule mirrors the route (principal,
              a 1..128 character name, declared scopes) and the bearer is shown once, because that
              is what the route promises - it is never stored and never re-read. */}
          <section className="access-key-create" aria-label={t("access.key.create")}>
            <h3>{t("access.key.create")}</h3>
            <p className="panel-copy">{t("access.key.create_note")}</p>
            <div className="access-key-form">
              <label>
                {t("access.key.owner")}
                <select
                  value={keyPrincipalId}
                  onChange={(event) => setKeyPrincipalId(event.target.value)}
                >
                  <option value="">{t("access.key.choose_principal")}</option>
                  {users.map((user) => (
                    <option key={user.principal_id} value={user.principal_id}>
                      {user.display_name} · {user.principal_id}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("access.key_label")}
                <input
                  value={keyDisplayName}
                  maxLength={128}
                  onChange={(event) => setKeyDisplayName(event.target.value)}
                />
              </label>
              <label>
                {t("access.key.expires_on")}
                <input
                  type="date"
                  value={keyExpiresOn}
                  onChange={(event) => setKeyExpiresOn(event.target.value)}
                />
              </label>
            </div>
            <fieldset className="access-key-scopes">
              <legend>{t("access.key.scopes")}</legend>
              {availableScopes.length === 0 ? (
                <span className="muted">{t("access.catalogue.unavailable")}</span>
              ) : (
                availableScopes.map((scope) => (
                  <label key={scope} className="access-key-scope">
                    <input
                      type="checkbox"
                      checked={keyScopes.includes(scope)}
                      onChange={(event) =>
                        setKeyScopes((current) =>
                          event.target.checked
                            ? [...current, scope]
                            : current.filter((item) => item !== scope),
                        )
                      }
                    />
                    {scope}
                  </label>
                ))
              )}
            </fieldset>
            {readiness.blockerKeys.length > 0 && (
              <ul className="access-key-blockers">
                {readiness.blockerKeys.map((key) => (
                  <li key={key}>{t(key)}</li>
                ))}
              </ul>
            )}
            {undeclared.length > 0 && (
              <p className="strategy-error">
                {t("access.key.undeclared")}: {undeclared.join(", ")}
              </p>
            )}
            <button
              type="button"
              disabled={!readiness.canCreate || keyBusy}
              onClick={() => void createKey()}
            >
              {t("access.key.issue")}
            </button>
            {issuedKey && (
              <div className="access-key-issued" role="status">
                <p className="panel-copy">{t("access.key.issued_once")}</p>
                <code className="access-key-secret">{issuedKey}</code>
                <button type="button" onClick={() => setIssuedKey(null)}>
                  {t("access.key.dismiss")}
                </button>
              </div>
            )}
          </section>
          <div className="data-table" tabIndex={0}>
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

      {activeView === "catalogue" && (
        <div id="access-active-panel" role="tabpanel" aria-labelledby="access-tab-catalogue" className="workspace-panel span-3">
          {/* What the platform declares, read from the routes that publish it: the roles and the
              permissions they grant, and the data-scope families an entitlement may name. Without
              these the users view edited grants against a vocabulary the administrator could not
              see, and a scope typo looked like any other value. */}
          <section className="access-catalogue" aria-label={t("access.view.catalogue")}>
            <h3>{t("access.catalogue.roles")}</h3>
            {roleRows(roles).length === 0 ? (
              <p className="muted">{t("access.catalogue.unavailable")}</p>
            ) : (
              <div className="data-table" tabIndex={0}>
                <div className="data-table-row header two">
                  <span>{t("access.roles")}</span>
                  <span>{t("access.catalogue.permissions")}</span>
                </div>
                {roleRows(roles).map((row) => (
                  <div key={row.role} className="data-table-row two">
                    <strong>{row.role}</strong>
                    <span>{row.permissions.length > 0 ? row.permissions.join(", ") : t("access.catalogue.grants_nothing")}</span>
                  </div>
                ))}
              </div>
            )}
            <h3>{t("access.catalogue.scope_families")}</h3>
            {scopeFamilyRows(scopeCatalogue).length === 0 ? (
              <p className="muted">{t("access.catalogue.unavailable")}</p>
            ) : (
              <div className="data-table" tabIndex={0}>
                <div className="data-table-row header two">
                  <span>{t("access.catalogue.family")}</span>
                  <span>{t("access.key.scopes")}</span>
                </div>
                {scopeFamilyRows(scopeCatalogue).map((row) => (
                  <div key={row.family} className="data-table-row two">
                    <strong>{t(`access.catalogue.family_${row.family}`)}</strong>
                    <span>{row.scopes.join(", ")}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {activeView === "audit" && (
        <div id="access-active-panel" role="tabpanel" aria-labelledby="access-tab-audit" className="workspace-panel span-3">
          <div className="data-table" tabIndex={0}>
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
