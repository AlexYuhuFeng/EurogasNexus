import { localDeadlineToUtc } from "@/app/model/decisionDeadline";
import { tabLabels } from "@/components/ui/tabLabels";
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
  userAccessBlocker,
  type UserAccessDraft,
  type DataScopeCatalogue,
} from "@/app/model/accessCatalogueModel";
import { PanelHeader, StatusBadge, WorkspaceTabs } from "@/components/ui";
import { LicenceRegisterPanel } from "@/components/LicenceRegisterPanel";
import { groupPermissions } from "@/app/permissionVocabulary";
import { useUrlView } from "@/app/navigation/useUrlView";

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
  const [activeView, setActiveView] = useUrlView<AccessViewId>("access", "users");
  const [users, setUsers] = useState<AccessUserDTO[]>([]);
  const [keys, setKeys] = useState<AccessApiKeyDTO[]>([]);
  const [audit, setAudit] = useState<AuditEventDTO[]>([]);
  // Investigation walk (#59): an explicit window and filter, and a continuation that pages
  // past any page size without repeating or skipping an event.
  const [auditFrom, setAuditFrom] = useState("");
  const [auditTo, setAuditTo] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditCursor, setAuditCursor] = useState<string | null>(null);
  const [auditBusy, setAuditBusy] = useState(false);
  const auditParams = () => ({
    limit: "100",
    action: auditAction.trim(),
    start_utc: localDeadlineToUtc(auditFrom) ?? "",
    end_utc: localDeadlineToUtc(auditTo) ?? "",
  });
  const searchAudit = async () => {
    setAuditBusy(true);
    try {
      const response = await api.auditEvents(auditParams());
      setAudit(response.data);
      setAuditCursor(response.meta.continuation?.cursor ?? null);
    } catch {
      setError("access.load_failed");
    } finally {
      setAuditBusy(false);
    }
  };
  const moreAudit = async () => {
    if (!auditCursor) return;
    setAuditBusy(true);
    try {
      const response = await api.auditEvents({ ...auditParams(), cursor: auditCursor });
      setAudit((current) => [...current, ...response.data]);
      setAuditCursor(response.meta.continuation?.cursor ?? null);
    } catch {
      setError("access.load_failed");
    } finally {
      setAuditBusy(false);
    }
  };
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
  const [userDrafts, setUserDrafts] = useState<Record<string, UserAccessDraft>>({});
  const [busyRows, setBusyRows] = useState<Record<string, boolean>>({});
  const [rowErrors, setRowErrors] = useState<Record<string, string | null>>({});

  useEffect(() => { if (activeView !== "api_keys") setIssuedKey(null); }, [activeView]);

  function editUser(user: AccessUserDTO, field: keyof UserAccessDraft, values: string[]) {
    setUserDrafts((current) => ({ ...current, [user.principal_id]: {
      ...(current[user.principal_id] ?? { roles: user.roles, data_scopes: user.data_scopes }),
      [field]: values,
    } }));
  }

  async function mutateRow(id: string, action: () => Promise<void>) {
    if (busyRows[id]) return;
    setBusyRows((current) => ({ ...current, [id]: true }));
    setRowErrors((current) => ({ ...current, [id]: null }));
    try { await action(); }
    catch { setRowErrors((current) => ({ ...current, [id]: "access.mutation_failed" })); }
    finally { setBusyRows((current) => ({ ...current, [id]: false })); }
  }

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
      api.auditEvents({ limit: "100" }).then((response) => {
        setAudit(response.data);
        setAuditCursor(response.meta.continuation?.cursor ?? null);
      }),
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

  async function updateUserAccess(user: AccessUserDTO) {
    const draft = userDrafts[user.principal_id];
    if (!draft || userAccessBlocker(draft, user, roles, scopeCatalogue)) return;
    await mutateRow(user.principal_id, async () => {
      const response = await api.patchAccessUser(user.principal_id, draft);
      setUsers((current) => current.map((item) => item.principal_id === user.principal_id ? response.data : item));
      setUserDrafts((current) => { const next = { ...current }; delete next[user.principal_id]; return next; });
    });
  }

  async function toggleUserStatus(user: AccessUserDTO) {
    await mutateRow(user.principal_id, async () => {
      const response = await api.patchAccessUser(user.principal_id, { status: user.status === "ACTIVE" ? "DISABLED" : "ACTIVE" });
      setUsers((current) => current.map((item) => item.principal_id === user.principal_id ? response.data : item));
    });
  }

  async function revokeKey(keyId: string) {
    await mutateRow(keyId, async () => {
      await api.revokeAccessApiKey(keyId);
      const response = await api.accessApiKeys();
      setKeys(response.data);
    });
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
          ...tabLabels(t, `access.view.${view}`),
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
                {(["roles", "data_scopes"] as const).map((field) => {
                  const offered = field === "roles" ? Object.keys(roles ?? {}).sort() : availableScopes;
                  return (
                    <GrantPicker
                      key={field}
                      label={`${user.display_name} · ${t(field === "roles" ? "access.roles" : "access.data_access")}`}
                      options={[...new Set([...offered, ...user[field]])]}
                      storedOnly={(value) => !offered.includes(value)}
                      selected={(userDrafts[user.principal_id] ?? user)[field]}
                      changed={Boolean(userDrafts[user.principal_id]) && (userDrafts[user.principal_id]![field].join("|") !== user[field].join("|"))}
                      disabled={Boolean(busyRows[user.principal_id]) || !roles || !scopeCatalogue}
                      t={t}
                      onChange={(values) => editUser(user, field, values)}
                    />
                  );
                })}
                <span className="access-row-actions">
                  <JobProfileEditor
                    user={user}
                    busy={Boolean(busyRows[user.principal_id])}
                    t={t}
                    onSave={(body) => mutateRow(user.principal_id, async () => {
                      const response = await api.patchAccessUser(user.principal_id, body);
                      setUsers((current) => current.map((item) => item.principal_id === user.principal_id ? response.data : item));
                    })}
                  />
                  <button type="button" disabled={busyRows[user.principal_id]} onClick={() => void toggleUserStatus(user)}>
                    {user.status === "ACTIVE" ? t("access.disable") : t("access.enable")}
                  </button>
                  <button type="button" disabled={busyRows[user.principal_id] || !userDrafts[user.principal_id] || Boolean(userAccessBlocker(userDrafts[user.principal_id] ?? user, user, roles, scopeCatalogue))} onClick={() => void updateUserAccess(user)}>
                    {t("access.save")}
                  </button>
                  {userAccessBlocker(userDrafts[user.principal_id] ?? user, user, roles, scopeCatalogue) && <span role="status">{t(userAccessBlocker(userDrafts[user.principal_id] ?? user, user, roles, scopeCatalogue)!)}</span>}
                  {rowErrors[user.principal_id] && <span role="alert">{t(rowErrors[user.principal_id]!)}</span>}
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
                <button type="button" disabled={Boolean(key.revoked_at_utc) || busyRows[key.key_id]} onClick={() => void revokeKey(key.key_id)}>{t("access.revoke")}</button>
                {rowErrors[key.key_id] && <span role="alert">{t(rowErrors[key.key_id]!)}</span>}
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
                  <div key={row.role} className="data-table-row two access-role-row">
                    <strong>{row.role}</strong>
                    {row.permissions.length > 0 ? (
                      <div className="access-role-grants">
                        {/* By business area, in plain words; the exact keys on request (#25). */}
                        <dl>
                          {groupPermissions(row.permissions).map((group) => (
                            <div key={group.area}>
                              <dt>{t(`access.permission.area.${group.area}`)}</dt>
                              <dd>
                                {group.actions.map((action) => (action.actionKey ? t(action.actionKey) : action.key)).join(" · ")}
                              </dd>
                            </div>
                          ))}
                        </dl>
                        <details className="access-technical-keys">
                          <summary>{t("access.permission.technical_keys")}</summary>
                          <code>{row.permissions.join(", ")}</code>
                        </details>
                      </div>
                    ) : (
                      <span>{t("access.catalogue.grants_nothing")}</span>
                    )}
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
          <LicenceRegisterPanel t={t} />
        </div>
      )}

      {activeView === "audit" && (
        <div id="access-active-panel" role="tabpanel" aria-labelledby="access-tab-audit" className="workspace-panel span-3">
          <form
            className="access-audit-filters"
            onSubmit={(event) => {
              event.preventDefault();
              void searchAudit();
            }}
          >
            <label>
              <span>{t("access.audit_from")}</span>
              <input type="datetime-local" value={auditFrom} onChange={(event) => setAuditFrom(event.target.value)} />
            </label>
            <label>
              <span>{t("access.audit_to")}</span>
              <input type="datetime-local" value={auditTo} onChange={(event) => setAuditTo(event.target.value)} />
            </label>
            <label>
              <span>{t("access.audit_action")}</span>
              <input value={auditAction} maxLength={64} onChange={(event) => setAuditAction(event.target.value)} />
            </label>
            <button type="submit" disabled={auditBusy}>{t("access.audit_search")}</button>
          </form>
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
          <p className="access-audit-continuation">
            <span className="muted">{t("access.audit_shown").replace("{{count}}", String(audit.length))}</span>
            {auditCursor && (
              <button type="button" className="secondary-button" disabled={auditBusy} onClick={() => void moreAudit()}>
                {t("access.audit_more")}
              </button>
            )}
          </p>
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


/** Declared job functions and home office: what the person does, never what they may do. */
export const JOB_FUNCTIONS = [
  "TRADER",
  "HQ_BUSINESS_ANALYST",
  "QUANT_RESEARCHER",
  "RISK_MANAGER",
  "FINANCE_SETTLEMENT",
  "LEGAL_COMPLIANCE",
  "MANAGEMENT",
  "REVIEWER_MANAGEMENT",
  "DATA_OPERATOR",
  "PLATFORM_ADMINISTRATOR",
] as const;

export const OFFICES = ["UK", "CA", "SG", "CN", "NL", "DE", "CH"] as const;

function JobProfileEditor({
  user,
  busy,
  t,
  onSave,
}: {
  user: AccessUserDTO;
  busy: boolean;
  t: (key: string) => string;
  onSave: (body: { job_functions: string[]; office: string | null }) => Promise<void> | void;
}) {
  const [functions, setFunctions] = useState<string[]>(user.job_functions ?? []);
  const [office, setOffice] = useState<string>(user.office ?? "");
  return (
    <details className="access-job-profile">
      <summary>{t("access.job_profile")}</summary>
      <label>
        <span>{t("access.job_functions")}</span>
        <select
          multiple
          aria-label={`${user.display_name} · ${t("access.job_functions")}`}
          value={functions}
          disabled={busy}
          onChange={(event) => setFunctions(Array.from(event.target.selectedOptions, (option) => option.value))}
        >
          {JOB_FUNCTIONS.map((item) => <option key={item} value={item}>{t(`access.job_function.${item}`)}</option>)}
        </select>
      </label>
      <label>
        <span>{t("access.office")}</span>
        <select value={office} disabled={busy} onChange={(event) => setOffice(event.target.value)}>
          <option value="">—</option>
          {OFFICES.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
      <small>{t("access.job_profile_note")}</small>
      <button type="button" disabled={busy} onClick={() => void onSave({ job_functions: functions, office: office || null })}>
        {t("access.save")}
      </button>
    </details>
  );
}

/**
 * A user's roles or data scopes (#24): the current grants as a readable summary, and a
 * labelled checkbox list (with a filter when long) to change them. Replaces the native
 * multi-select, which hid most options and the selection and needed Ctrl/Shift to use.
 * Changes stay a draft until the row's Save; nothing here widens a grant on its own.
 */
function GrantPicker({
  label,
  options,
  selected,
  storedOnly,
  changed,
  disabled,
  t,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  storedOnly: (value: string) => boolean;
  changed: boolean;
  disabled: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
  onChange: (values: string[]) => void;
}) {
  const [filter, setFilter] = useState("");
  const shown = filter ? options.filter((option) => option.toLowerCase().includes(filter.toLowerCase())) : options;
  // "*" is the wildcard scope: say what it covers instead of showing a bare asterisk.
  const word = (value: string) => (value === "*" ? t("access.grant.wildcard") : value);
  const summary = selected.length === 0 ? t("access.grant.none") : selected.map(word).join(", ");
  return (
    <details className={`access-grant-picker${changed ? " is-changed" : ""}`}>
      <summary aria-label={label} title={summary}>
        <span className="access-grant-summary">{summary}</span>
        <span className="access-grant-edit">{t("access.grant.edit")}</span>
      </summary>
      <fieldset disabled={disabled}>
        <legend>{label} · {t("access.grant.selected").replace("{{count}}", String(selected.length))}</legend>
        {options.length > 8 && (
          <input
            type="search"
            className="access-grant-filter"
            placeholder={t("access.grant.filter")}
            aria-label={t("access.grant.filter")}
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
        )}
        <div className="access-grant-options">
          {shown.map((value) => (
            <label key={value} className="settings-checkbox">
              <input
                type="checkbox"
                checked={selected.includes(value)}
                onChange={(event) =>
                  onChange(event.target.checked ? [...selected, value] : selected.filter((item) => item !== value))
                }
              />
              {word(value)}
              {storedOnly(value) && <small> ({t("access.user.stored_grant")})</small>}
            </label>
          ))}
        </div>
      </fieldset>
    </details>
  );
}
