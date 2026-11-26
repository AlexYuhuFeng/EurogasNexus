import { personFunctionOfJob } from "@/app/experience/roleComposition";
/**
 * Admin -> Users: everyone who can sign in, how they sign in, their one state, and the
 * administrator's actions (add, edit access, disable/enable, reset password, delete).
 *
 * The backend owns every rule: who may do this (ADMIN), the password policy, the last active
 * administrator, "delete only without history" and the one-time password. This surface shows
 * the state it is given and explains a refusal in words; it never decides access itself.
 */
import { useId, useMemo, useState, type FormEvent, type ReactNode } from "react";

import {
  api,
  type AccessUserCreateInputDTO,
  type AccessUserDTO,
  type AccountOptionsDTO,
  type CurrentUserDTO,
} from "@/api/client";
import { declaredScopes, type DataScopeCatalogue } from "@/app/model/accessCatalogueModel";
import { accessErrorKey, userState } from "@/app/model/accessUsersModel";
import { Button, DataGrid, Dialog, Field, Segmented, Select, StatusBadge, type DataGridColumn, type StatusTone } from "@/components/ui";
import "./access-users.css";

type T = (key: string) => string;

/** Declared job functions: what the person does, never what they may do. */
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
  "ORIGINATOR",
  "OPERATIONS",
] as const;

export const OFFICES = ["UK", "CA", "SG", "CN", "NL", "DE", "CH"] as const;

const ROLE_ORDER = ["VIEWER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN"];
const byRank = (a: string, b: string) =>
  (ROLE_ORDER.indexOf(a) + 1 || 99) - (ROLE_ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b);

/** A person's functions as they are called (Trader, Risk manager), from their job functions. */
function functionsOf(user: AccessUserDTO, t: (key: string) => string): string {
  const names = (user.job_functions ?? []).map(personFunctionOfJob).filter((item): item is NonNullable<typeof item> => item !== null);
  return [...new Set(names)].map((item) => t(`person.function.${item}`)).join(", ");
}

const STATE_TONE: Record<string, StatusTone> = {
  ACTIVE: "ok",
  INVITED: "info",
  DISABLED: "neutral",
  LOCKED: "watch",
  PENDING: "watch",
};

function formatWhen(value: string | null | undefined, t: T): string {
  if (!value) return t("access.users.never");
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

interface AccessUsersProps {
  users: AccessUserDTO[];
  accountOptions: AccountOptionsDTO | null;
  roles: Record<string, string[]> | null;
  scopeCatalogue: DataScopeCatalogue | null;
  currentUser: CurrentUserDTO | null;
  loaded: boolean;
  t: T;
  onUsersChange: (users: AccessUserDTO[]) => void;
}

type Pending =
  | { kind: "add" }
  | { kind: "edit"; user: AccessUserDTO }
  | { kind: "confirm"; action: "disable" | "reset" | "delete"; user: AccessUserDTO }
  | { kind: "secret"; name: string; secret: string; reset: boolean };

export function AccessUsers({ users, accountOptions, roles, scopeCatalogue, currentUser, loaded, t, onUsersChange }: AccessUsersProps) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [rowError, setRowError] = useState<{ id: string; key: string } | null>(null);
  const invited = users.filter((user) => userState(user) === "INVITED").length;

  const replace = (row: AccessUserDTO) =>
    onUsersChange(users.map((item) => (item.principal_id === row.principal_id ? { ...item, ...row } : item)));

  async function act(user: AccessUserDTO, run: () => Promise<void>) {
    setBusy(true);
    setRowError(null);
    try {
      await run();
    } catch (error) {
      setRowError({ id: user.principal_id, key: accessErrorKey(error) });
      setPending(null);
    } finally {
      setBusy(false);
    }
  }

  async function enable(user: AccessUserDTO) {
    await act(user, async () => {
      const response = await api.patchAccessUser(user.principal_id, { status: "ACTIVE" });
      replace(response.data);
    });
  }

  async function confirm(action: "disable" | "reset" | "delete", user: AccessUserDTO) {
    await act(user, async () => {
      if (action === "disable") {
        const response = await api.patchAccessUser(user.principal_id, { status: "DISABLED" });
        replace(response.data);
        setPending(null);
      } else if (action === "reset") {
        const response = await api.resetAccessUserPassword(user.principal_id);
        replace(response.data.user);
        setPending({ kind: "secret", name: user.display_name, secret: response.data.one_time_password ?? "", reset: true });
      } else {
        await api.deleteAccessUser(user.principal_id);
        onUsersChange(users.filter((item) => item.principal_id !== user.principal_id));
        setPending(null);
      }
    });
  }

  const columns: DataGridColumn<AccessUserDTO>[] = [
    {
      id: "person",
      header: t("access.users.person"),
      rowHeader: true,
      value: (user) => user.display_name,
      sortable: true,
      render: (user) => (
        <span className="access-person">
          <strong>{user.display_name}</strong>
          <small>{[user.name, user.email].filter(Boolean).join(" · ")}</small>
        </span>
      ),
    },
    {
      id: "sign_in",
      header: t("access.users.sign_in"),
      value: (user) => user.account_kind ?? "",
      sortable: true,
      render: (user) => (
        <span className="access-kind">
          {t(`access.users.kind.${user.account_kind ?? "key"}`)}
          {user.local_password?.demo_account && <StatusBadge tone="neutral">{t("access.users.demo")}</StatusBadge>}
        </span>
      ),
    },
    {
      id: "state",
      header: t("access.users.state"),
      value: (user) => userState(user),
      sortable: true,
      render: (user) => (
        <StatusBadge tone={STATE_TONE[userState(user)] ?? "neutral"} title={stateTitle(user, t)}>
          {t(`access.users.state.${userState(user)}`)}
        </StatusBadge>
      ),
    },
    {
      // What the person is called (the role registry's function); the authority roles beside it
      // are permissions, and this page is the only one that shows them.
      id: "function",
      header: t("access.users.function"),
      value: (user) => functionsOf(user, t),
      sortable: true,
      render: (user) => <span className="access-function">{functionsOf(user, t) || "–"}</span>,
    },
    {
      id: "roles",
      header: t("access.users.permissions"),
      value: (user) => (user.roles ?? []).join(", "),
      render: (user) => <span className="access-roles">{(user.roles ?? []).map((role) => t(`access.role.${role}`).toLocaleLowerCase()).join(", ")}</span>,
    },
    {
      id: "last",
      header: t("access.users.last_sign_in"),
      type: "date",
      value: (user) => user.last_login_at_utc ?? "",
      sortable: true,
      render: (user) => <span className="access-when">{formatWhen(user.last_login_at_utc, t)}</span>,
    },
    {
      id: "actions",
      header: <span className="ds-visually-hidden">{t("access.actions")}</span>,
      render: (user) => {
        const state = userState(user);
        const self = user.principal_id === currentUser?.principal_id;
        return (
          <span className="access-user-actions">
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => setPending({ kind: "edit", user })}>
              {t("access.users.edit")}
            </Button>
            {state === "DISABLED" || state === "LOCKED" ? (
              <Button size="sm" variant="quiet" disabled={busy} onClick={() => void enable(user)}>
                {state === "LOCKED" ? t("access.users.unlock") : t("access.enable")}
              </Button>
            ) : (
              !self && (
                <Button size="sm" variant="quiet" disabled={busy} onClick={() => setPending({ kind: "confirm", action: "disable", user })}>
                  {t("access.disable")}
                </Button>
              )
            )}
            {user.account_kind === "local" && (
              <Button size="sm" variant="quiet" disabled={busy} onClick={() => setPending({ kind: "confirm", action: "reset", user })}>
                {t("access.users.reset_password")}
              </Button>
            )}
            {!self && (user.deletable ?? (!user.last_login_at_utc && (user.keys ?? []).length === 0)) && (
              <Button size="sm" variant="quiet" disabled={busy} onClick={() => setPending({ kind: "confirm", action: "delete", user })}>
                {t("access.users.delete")}
              </Button>
            )}
            {rowError?.id === user.principal_id && <span className="access-row-error" role="alert">{t(rowError.key)}</span>}
          </span>
        );
      },
    },
  ];

  return (
    <section className="access-users" aria-label={t("access.view.users")}>
      <div className="access-users-bar">
        <p className="access-users-count">
          {t("access.users.count").replace("{{count}}", String(users.length))}
          {invited > 0 && <> · {t("access.users.invited_count").replace("{{count}}", String(invited))}</>}
        </p>
        <Button variant="primary" size="md" onClick={() => setPending({ kind: "add" })} data-action="add-user">
          {t("access.users.add")}
        </Button>
      </div>
      <DataGrid
        id="access-users"
        label={t("access.view.users")}
        columns={columns}
        rows={users}
        rowKey={(user) => user.principal_id}
        rowAttributes={(user) => ({ "data-record": "access-user", "data-state": userState(user) })}
        defaultSort={{ columnId: "person", direction: "ascending" }}
        loading={!loaded}
        loadingLabel={t("access.users.loading")}
        empty={<span data-empty-state="access-users">{t("access.no_users")}</span>}
      />

      {pending?.kind === "add" && (
        <AddUserDialog
          t={t}
          options={accountOptions}
          roles={roles}
          scopeCatalogue={scopeCatalogue}
          onClose={() => setPending(null)}
          onCreated={(user, secret) => {
            onUsersChange([...users, user]);
            setPending(secret ? { kind: "secret", name: user.display_name, secret, reset: false } : null);
          }}
        />
      )}
      {pending?.kind === "edit" && (
        <EditAccessDialog
          t={t}
          user={pending.user}
          roles={roles}
          scopeCatalogue={scopeCatalogue}
          onClose={() => setPending(null)}
          onSaved={(user) => {
            replace(user);
            setPending(null);
          }}
        />
      )}
      {pending?.kind === "confirm" && (
        <Dialog
          open
          size="sm"
          id={`access-confirm-${pending.action}`}
          title={t(`access.users.confirm.${pending.action}.title`).replace("{{name}}", pending.user.display_name)}
          closeLabel={t("access.users.close")}
          onClose={() => setPending(null)}
          footer={
            <>
              <Button variant="quiet" size="md" onClick={() => setPending(null)}>{t("access.users.cancel")}</Button>
              <Button
                variant={pending.action === "reset" ? "primary" : "danger"}
                size="md"
                loading={busy}
                onClick={() => void confirm(pending.action, pending.user)}
              >
                {t(`access.users.confirm.${pending.action}.action`)}
              </Button>
            </>
          }
        >
          <p className="access-dialog-copy">{t(`access.users.confirm.${pending.action}.body`)}</p>
        </Dialog>
      )}
      {pending?.kind === "secret" && (
        <OneTimeSecretDialog
          t={t}
          name={pending.name}
          secret={pending.secret}
          hours={accountOptions?.temporary_password_hours ?? 72}
          reset={pending.reset}
          onClose={() => setPending(null)}
        />
      )}
    </section>
  );
}

function stateTitle(user: AccessUserDTO, t: T): string | undefined {
  const local = user.local_password;
  if (userState(user) === "LOCKED" && local?.locked_until_utc) {
    return t("access.users.locked_until").replace("{{time}}", formatWhen(local.locked_until_utc, t));
  }
  if (userState(user) === "INVITED" && user.account_kind === "local") {
    return local?.temporary_password_expired ? t("access.users.temporary_expired") : t("access.users.invited_local");
  }
  if (userState(user) === "INVITED") return t("access.users.invited_sso");
  return undefined;
}

/** Checkbox list for one grant family (roles, job functions, data access). */
function CheckList({ legend, hint, options, selected, label, onChange }: {
  legend: string;
  hint?: ReactNode;
  options: readonly string[];
  selected: string[];
  label: (value: string) => string;
  onChange: (values: string[]) => void;
}) {
  const hintId = useId();
  return (
    <fieldset className="access-checklist" aria-describedby={hint ? hintId : undefined}>
      <legend>{legend}</legend>
      {hint && <small id={hintId} className="ds-field-hint">{hint}</small>}
      <div className="access-checklist-options">
        {options.map((value) => (
          <label key={value} className="access-check">
            <input
              type="checkbox"
              checked={selected.includes(value)}
              onChange={(event) => onChange(event.target.checked ? [...selected, value] : selected.filter((item) => item !== value))}
            />
            <span>{label(value)}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function AddUserDialog({ t, options, roles, scopeCatalogue, onClose, onCreated }: {
  t: T;
  options: AccountOptionsDTO | null;
  roles: Record<string, string[]> | null;
  scopeCatalogue: DataScopeCatalogue | null;
  onClose: () => void;
  onCreated: (user: AccessUserDTO, secret: string | null) => void;
}) {
  const localAllowed = Boolean(options?.local_accounts);
  const ssoAllowed = Boolean(options?.sso_invites);
  const [kind, setKind] = useState<"local" | "sso">(ssoAllowed && !localAllowed ? "sso" : "local");
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [chosenRoles, setChosenRoles] = useState<string[]>(["VIEWER"]);
  const [functions, setFunctions] = useState<string[]>([]);
  const [office, setOffice] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [tried, setTried] = useState(false);
  const roleOptions = useMemo(() => Object.keys(roles ?? { VIEWER: [] }).sort(byRank), [roles]);
  const scopeOptions = declaredScopes(scopeCatalogue);
  const nothingAllowed = !localAllowed && !ssoAllowed;

  const problem =
    !displayName.trim()
      ? "access.users.need_name"
      : kind === "local" && !/^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$/.test(username.trim())
        ? "access.users.need_username"
        : kind === "sso" && !email.trim() && !subject.trim()
          ? "access.error.invite_identifier_missing"
          : chosenRoles.length === 0
            ? "access.user.roles_required"
            : null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTried(true);
    if (problem || busy || nothingAllowed) return;
    setBusy(true);
    setErrorKey(null);
    const body: AccessUserCreateInputDTO = {
      kind,
      display_name: displayName.trim(),
      roles: chosenRoles,
      job_functions: functions,
      office: office || null,
      data_scopes: scopes,
      ...(kind === "local"
        ? { username: username.trim(), email: email.trim() || null }
        : { email: email.trim() || null, subject: subject.trim() || null }),
    };
    try {
      const response = await api.createAccessUser(body);
      onCreated(response.data.user, response.data.one_time_password ?? null);
    } catch (error) {
      setErrorKey(accessErrorKey(error));
    } finally {
      setBusy(false);
    }
  }

  const formId = "access-add-user-form";
  return (
    <Dialog
      open
      size="lg"
      id="access-add-user"
      title={t("access.users.add_title")}
      closeLabel={t("access.users.close")}
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" size="md" onClick={onClose}>{t("access.users.cancel")}</Button>
          <Button variant="primary" size="md" type="submit" form={formId} loading={busy} disabled={nothingAllowed}>
            {kind === "local" ? t("access.users.create_local") : t("access.users.create_invite")}
          </Button>
        </>
      }
    >
      <form id={formId} className="access-add-form" onSubmit={(event) => void submit(event)} noValidate>
        {localAllowed && ssoAllowed ? (
          <div className="access-add-kind">
            <span className="ds-field-label">{t("access.users.how_sign_in")}</span>
            <Segmented
              label={t("access.users.how_sign_in")}
              size="md"
              value={kind}
              onChange={(value) => setKind(value)}
              options={[
                { value: "sso", label: t("access.users.kind.sso") },
                { value: "local", label: t("access.users.kind.local") },
              ]}
            />
          </div>
        ) : (
          <p className="access-dialog-copy">
            {nothingAllowed ? t("access.users.no_way_to_add") : localAllowed ? t("access.users.local_only") : t("access.users.sso_only")}
          </p>
        )}
        <p className="access-dialog-copy access-add-explain">
          {kind === "local" ? t("access.users.local_explain") : t("access.users.sso_explain")}
        </p>

        <div className="access-add-grid">
          <Field label={t("access.users.full_name")} error={tried && problem === "access.users.need_name" ? t(problem) : undefined}>
            <input className="access-input" value={displayName} maxLength={128} autoComplete="off" onChange={(event) => setDisplayName(event.target.value)} />
          </Field>
          {kind === "local" ? (
            <Field
              label={t("access.users.username")}
              hint={t("access.users.username_hint")}
              error={tried && problem === "access.users.need_username" ? t(problem) : undefined}
            >
              <input className="access-input" value={username} maxLength={64} autoComplete="off" spellCheck={false} onChange={(event) => setUsername(event.target.value)} />
            </Field>
          ) : (
            <Field label={t("access.users.sso_subject")} hint={t("access.users.sso_subject_hint")}>
              <input className="access-input" value={subject} maxLength={256} autoComplete="off" spellCheck={false} onChange={(event) => setSubject(event.target.value)} />
            </Field>
          )}
          <Field
            label={kind === "local" ? t("access.users.email_optional") : t("access.users.email")}
            hint={kind === "sso" ? t("access.users.email_sso_hint") : undefined}
            error={tried && problem === "access.error.invite_identifier_missing" ? t(problem) : undefined}
          >
            <input className="access-input" type="email" value={email} maxLength={254} autoComplete="off" onChange={(event) => setEmail(event.target.value)} />
          </Field>
          <Field label={t("access.office")}>
            <Select
              size="md"
              value={office}
              onChange={setOffice}
              options={[{ value: "", label: t("access.users.office_none") }, ...OFFICES.map((item) => ({ value: item, label: item }))]}
            />
          </Field>
        </div>

        <CheckList
          legend={t("access.roles")}
          hint={t("access.users.roles_hint")}
          options={roleOptions}
          selected={chosenRoles}
          label={(value) => t(`access.role.${value}`)}
          onChange={setChosenRoles}
        />
        <CheckList
          legend={t("access.job_functions")}
          hint={t("access.job_profile_note")}
          options={JOB_FUNCTIONS}
          selected={functions}
          label={(value) => t(`access.job_function.${value}`)}
          onChange={setFunctions}
        />
        {scopeOptions.length > 0 && (
          <details className="access-add-more">
            <summary>{t("access.users.data_access_optional")}</summary>
            <CheckList
              legend={t("access.data_access")}
              hint={t("access.users.data_access_hint")}
              options={scopeOptions}
              selected={scopes}
              label={(value) => (value === "*" ? t("access.grant.wildcard") : value)}
              onChange={setScopes}
            />
          </details>
        )}
        {tried && problem === "access.user.roles_required" && <p className="access-form-error" role="alert">{t(problem)}</p>}
        {errorKey && <p className="access-form-error" role="alert">{t(errorKey)}</p>}
      </form>
    </Dialog>
  );
}

function EditAccessDialog({ t, user, roles, scopeCatalogue, onClose, onSaved }: {
  t: T;
  user: AccessUserDTO;
  roles: Record<string, string[]> | null;
  scopeCatalogue: DataScopeCatalogue | null;
  onClose: () => void;
  onSaved: (user: AccessUserDTO) => void;
}) {
  const [chosenRoles, setChosenRoles] = useState<string[]>(user.roles ?? []);
  const [scopes, setScopes] = useState<string[]>(user.data_scopes ?? []);
  const [functions, setFunctions] = useState<string[]>(user.job_functions ?? []);
  const [office, setOffice] = useState(user.office ?? "");
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const roleOptions = [...new Set([...Object.keys(roles ?? {}), ...(user.roles ?? [])])].sort(byRank);
  const scopeOptions = [...new Set([...declaredScopes(scopeCatalogue), ...(user.data_scopes ?? [])])];
  const same = (a: string[], b: string[]) => [...a].sort().join("|") === [...b].sort().join("|");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (chosenRoles.length === 0) {
      setErrorKey("access.user.roles_required");
      return;
    }
    setBusy(true);
    setErrorKey(null);
    try {
      const grantsChanged = !same(chosenRoles, user.roles ?? []) || !same(scopes, user.data_scopes ?? []);
      const body = {
        ...(grantsChanged ? { roles: chosenRoles, data_scopes: scopes } : {}),
        job_functions: functions,
        office: office || null,
      };
      const response = await api.patchAccessUser(user.principal_id, body);
      onSaved(response.data);
    } catch (error) {
      setErrorKey(accessErrorKey(error));
    } finally {
      setBusy(false);
    }
  }

  const formId = "access-edit-user-form";
  return (
    <Dialog
      open
      size="lg"
      id="access-edit-user"
      eyebrow={user.name}
      title={user.display_name}
      closeLabel={t("access.users.close")}
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" size="md" onClick={onClose}>{t("access.users.cancel")}</Button>
          <Button variant="primary" size="md" type="submit" form={formId} loading={busy}>{t("access.save")}</Button>
        </>
      }
    >
      <form id={formId} className="access-add-form" onSubmit={(event) => void save(event)} noValidate>
        <CheckList
          legend={t("access.roles")}
          hint={t("access.users.roles_hint")}
          options={roleOptions}
          selected={chosenRoles}
          label={(value) => t(`access.role.${value}`)}
          onChange={setChosenRoles}
        />
        <CheckList
          legend={t("access.job_functions")}
          hint={t("access.job_profile_note")}
          options={JOB_FUNCTIONS}
          selected={functions}
          label={(value) => t(`access.job_function.${value}`)}
          onChange={setFunctions}
        />
        <div className="access-add-grid">
          <Field label={t("access.office")}>
            <Select
              size="md"
              value={office}
              onChange={setOffice}
              options={[{ value: "", label: t("access.users.office_none") }, ...OFFICES.map((item) => ({ value: item, label: item }))]}
            />
          </Field>
        </div>
        <CheckList
          legend={t("access.data_access")}
          hint={t("access.users.data_access_hint")}
          options={scopeOptions}
          selected={scopes}
          label={(value) => (value === "*" ? t("access.grant.wildcard") : value)}
          onChange={setScopes}
        />
        {errorKey && <p className="access-form-error" role="alert">{t(errorKey)}</p>}
      </form>
    </Dialog>
  );
}

function OneTimeSecretDialog({ t, name, secret, hours, reset, onClose }: {
  t: T;
  name: string;
  secret: string;
  hours: number;
  reset: boolean;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <Dialog
      open
      size="md"
      id="access-one-time-password"
      title={t("access.users.secret_title").replace("{{name}}", name)}
      closeLabel={t("access.users.close")}
      onClose={onClose}
      footer={<Button variant="primary" size="md" onClick={onClose}>{t("access.users.secret_done")}</Button>}
    >
      <p className="access-dialog-copy">
        {(reset ? t("access.users.secret_intro_reset") : t("access.users.secret_intro")).replace("{{name}}", name)}
      </p>
      <div className="access-secret">
        <code aria-label={t("access.users.secret_label")}>{secret}</code>
        <Button size="md" variant="secondary" onClick={() => void copy()}>
          {copied ? t("access.users.copied") : t("access.users.copy")}
        </Button>
      </div>
      <ul className="access-secret-notes">
        <li>{t("access.users.secret_once")}</li>
        <li>{t("access.users.secret_expires").replace("{{hours}}", String(hours))}</li>
        <li>{t("access.users.secret_change")}</li>
      </ul>
    </Dialog>
  );
}
