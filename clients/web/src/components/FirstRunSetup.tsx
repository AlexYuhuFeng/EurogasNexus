/**
 * First-run setup: the first administrator's welcome flow (one page per category of data).
 *
 * Every page lists the sources of its category (from GET /api/setup, derived on the server from
 * the connector manifests), with one line on what each turns on, its state, and the input it
 * needs. Every step can be skipped and nothing here blocks the product. Keys go to the one
 * credential mechanism (PUT /api/credentials/{provider}, encrypted at rest; the input is
 * write-only and only "saved · …last four" comes back); approvals to POST
 * /api/sources/{id}/approve after the administrator has read the terms summary - never
 * accepted on their behalf. Licensed data only ever flows through the firm's own entitlement.
 */
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import {
  api,
  type CredentialProviderDTO,
  type CurrentUserDTO,
  type SetupItemDTO,
  type SetupViewDTO,
} from "@/api/client";
import {
  FINISH_WHERE,
  itemState,
  setupSummary,
  startStep,
  stepIds,
  type SetupContext,
  type SetupSourceFacts,
  type SetupTone,
} from "@/app/model/firstRunSetupModel";
import { Button, Dialog, StatusBadge, type StatusTone } from "@/components/ui";
import "./first-run-setup.css";

type T = (key: string) => string;
/** Where a "finish it there" link leads: a page and, for administration pages, its view. */
export type SetupDestination = { page: "sources" | "access" | "contracts"; view?: string };

const TONE: Record<SetupTone, StatusTone> = { on: "ok", action: "watch", later: "neutral", info: "info" };
const SHOWN_KEY = "eurogas.setup.shown.v1";
export const OPEN_SETUP_EVENT = "eurogas:open-setup";

function fill(text: string, values: Record<string, string | number>): string {
  return Object.entries(values).reduce((out, [key, value]) => out.replaceAll(`{{${key}}}`, String(value)), text);
}

/**
 * Mounted once in the signed-in shell. Opens the flow for an administrator when the installation
 * has not completed or dismissed it (once per browser session), and whenever Admin → Access →
 * Setup asks for it. Never shown to anyone without identity administration.
 */
export function FirstRunSetupGate({
  currentUser,
  t,
  onNavigate,
}: {
  currentUser: CurrentUserDTO | null;
  t: T;
  onNavigate: (destination: SetupDestination) => void;
}) {
  const isAdmin = Boolean(currentUser?.permissions.includes("identity.manage"));
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    let shown = false;
    try {
      shown = sessionStorage.getItem(SHOWN_KEY) === "1";
    } catch {
      shown = false;
    }
    if (!shown) {
      api.setup().then((response) => {
        if (!cancelled && response.data.show_on_sign_in) setOpen(true);
      }).catch(() => undefined);
    }
    const reopen = () => setOpen(true);
    window.addEventListener(OPEN_SETUP_EVENT, reopen);
    return () => {
      cancelled = true;
      window.removeEventListener(OPEN_SETUP_EVENT, reopen);
    };
  }, [isAdmin]);

  if (!isAdmin || !open) return null;
  const close = () => {
    try {
      sessionStorage.setItem(SHOWN_KEY, "1");
    } catch {
      // A private window: the flow may show again next time; the server state still decides.
    }
    setOpen(false);
  };
  return (
    <FirstRunSetup
      t={t}
      onClose={close}
      onNavigate={(destination) => {
        close();
        onNavigate(destination);
      }}
    />
  );
}

export function FirstRunSetup({
  t,
  onClose,
  onNavigate,
}: {
  t: T;
  onClose: () => void;
  onNavigate: (destination: SetupDestination) => void;
}) {
  const [view, setView] = useState<SetupViewDTO | null>(null);
  const [sources, setSources] = useState<Record<string, SetupSourceFacts>>({});
  const [providers, setProviders] = useState<Record<string, CredentialProviderDTO>>({});
  const [families, setFamilies] = useState<Set<string>>(new Set());
  const [userCount, setUserCount] = useState(1);
  const [step, setStep] = useState<string>("welcome");
  const [loadError, setLoadError] = useState(false);

  const refresh = useCallback(async () => {
    const [setup, sourceRows, providerRows, licences, users] = await Promise.allSettled([
      api.setup(),
      api.sources(),
      api.credentialProviders(),
      api.marketDataLicences(),
      api.accessUsers(),
    ]);
    if (setup.status === "fulfilled") setView(setup.value.data);
    else setLoadError(true);
    if (sourceRows.status === "fulfilled") {
      setSources(Object.fromEntries(sourceRows.value.data.map((row) => [row.source_id, row as SetupSourceFacts])));
    }
    if (providerRows.status === "fulfilled") {
      setProviders(Object.fromEntries(providerRows.value.data.map((row) => [row.provider_id, row])));
    }
    if (licences.status === "fulfilled") {
      setFamilies(new Set(licences.value.data.filter((row) => row.active).map((row) => row.source_family.toUpperCase())));
    }
    if (users.status === "fulfilled") setUserCount(users.value.data.length);
    return setup.status === "fulfilled" ? setup.value.data : null;
  }, []);

  useEffect(() => {
    void refresh().then((loaded) => {
      if (!loaded) return;
      const first = startStep(loaded);
      setStep(first);
      if (loaded.state.status !== "in_progress" || loaded.state.current_step !== first) {
        void api.saveSetup("in_progress", first).catch(() => undefined);
      }
    });
  }, [refresh]);

  const steps = stepIds(view);
  const index = Math.max(0, steps.indexOf(step));
  const context: SetupContext = useMemo(
    () => ({ sources, providers, licensedFamilies: families, userCount, terminalTariffs: view?.terminal_tariffs }),
    [sources, providers, families, userCount, view],
  );
  const items = view?.catalogue.steps.find((entry) => entry.step === step)?.items ?? [];

  const go = (next: number) => {
    const target = steps[Math.min(Math.max(next, 0), steps.length - 1)];
    if (!target) return;
    setStep(target);
    void api.saveSetup("in_progress", target).catch(() => undefined);
  };
  const finish = async (status: "completed" | "dismissed") => {
    try {
      await api.saveSetup(status, status === "completed" ? "summary" : step);
    } catch {
      // The flow stays resumable from Admin → Access → Setup either way.
    }
    onClose();
  };
  const last = index === steps.length - 1;

  return (
    <Dialog
      open
      size="lg"
      id="first-run-setup"
      className="setup-dialog"
      eyebrow={steps.length ? fill(t("setup.progress"), { n: index + 1, total: steps.length }) : undefined}
      title={t(`setup.step.${step}.title`)}
      closeLabel={t("setup.finish_later")}
      onClose={() => void finish("dismissed")}
      dataAttributes={{ "data-setup-step": step }}
      footer={
        <div className="setup-foot">
          <Button variant="quiet" size="md" onClick={() => void finish("dismissed")}>
            {t("setup.finish_later")}
          </Button>
          <span className="setup-foot-spacer" />
          {index > 0 && (
            <Button variant="secondary" size="md" onClick={() => go(index - 1)}>{t("setup.back")}</Button>
          )}
          {!last && index > 0 && items.length > 0 && (
            <Button variant="quiet" size="md" onClick={() => go(index + 1)} data-action="setup-skip" disabled={!view}>
              {t("setup.skip")}
            </Button>
          )}
          {last ? (
            <Button variant="primary" size="md" onClick={() => void finish("completed")} data-action="setup-finish">
              {t("setup.finish")}
            </Button>
          ) : (
            <Button variant="primary" size="md" onClick={() => go(index + 1)} data-action="setup-next" loading={!view && !loadError}>
              {index === 0 ? t("setup.start") : t("setup.next")}
            </Button>
          )}
        </div>
      }
    >
      <ol className="setup-rail" aria-label={t("setup.steps_label")}>
        {steps.map((id, position) => (
          <li key={id} className={position === index ? "is-current" : position < index ? "is-done" : undefined}
            aria-current={position === index ? "step" : undefined}>
            <span className="ds-visually-hidden">{t(`setup.step.${id}.title`)}</span>
          </li>
        ))}
      </ol>
      {loadError && !view ? (
        <p className="setup-copy" role="alert">{t("setup.load_failed")}</p>
      ) : step === "welcome" ? (
        <Welcome t={t} view={view} />
      ) : step === "summary" && view ? (
        <Summary t={t} view={view} context={context} onNavigate={onNavigate} />
      ) : (
        <>
          <p className="setup-copy setup-intro">{t(`setup.step.${step}.intro`)}</p>
          {step === "ai" && view && !view.ai_external_enabled && (
            <p className="setup-note" role="note">{t("setup.ai.off_here")}</p>
          )}
          {view && !view.key_storage_ready && items.some((item) => item.credential_provider) && (
            <p className="setup-note" role="note">{t("setup.keys_unavailable")}</p>
          )}
          <ul className="setup-items">
            {items.map((item) => (
              <SetupItem
                key={item.item_id}
                item={item}
                t={t}
                context={context}
                keyStorageReady={Boolean(view?.key_storage_ready)}
                onChanged={() => void refresh()}
                onNavigate={onNavigate}
              />
            ))}
          </ul>
        </>
      )}
    </Dialog>
  );
}

function Welcome({ t, view }: { t: T; view: SetupViewDTO | null }) {
  return (
    <div className="setup-welcome">
      <p className="setup-copy setup-intro">{t("setup.step.welcome.intro")}</p>
      <ul className="setup-points">
        <li>{t("setup.welcome.categories")}</li>
        <li>{t("setup.welcome.keys")}</li>
        <li>{t("setup.welcome.licences")}</li>
        <li>{t("setup.welcome.skip")}</li>
      </ul>
      {view?.state.configured_by === "demo_profile" && <p className="setup-note">{t("setup.welcome.demo")}</p>}
      {view?.state.configured_by === "environment" && <p className="setup-note">{t("setup.welcome.environment")}</p>}
    </div>
  );
}

function Summary({ t, view, context, onNavigate }: {
  t: T;
  view: SetupViewDTO;
  context: SetupContext;
  onNavigate: (destination: SetupDestination) => void;
}) {
  const rows = setupSummary(view, context);
  return (
    <div className="setup-summary">
      <p className="setup-copy setup-intro">{t("setup.step.summary.intro")}</p>
      <ul className="setup-items">
        {rows.map((row) => (
          <li key={row.step} className="setup-item" data-summary-step={row.step}>
            <div className="setup-item-head">
              <strong>{t(`setup.step.${row.step}.title`)}</strong>
              <StatusBadge tone={row.left.length === 0 ? "ok" : "neutral"}>
                {fill(t("setup.summary.counts"), { on: row.on.length, left: row.left.length })}
              </StatusBadge>
            </div>
            {row.left.length > 0 && (
              <p className="setup-item-purpose">
                {t("setup.summary.left")}{" "}
                {row.left.map((id) => t(`setup.item.${id}.name`)).join(", ")}
                {FINISH_WHERE[row.step] && (
                  <>
                    {" · "}
                    <button type="button" className="setup-link" onClick={() => onNavigate(destinationFor(row.step))}>
                      {t(FINISH_WHERE[row.step]!)}
                    </button>
                  </>
                )}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function destinationFor(step: string): SetupDestination {
  if (step === "people") return { page: "access", view: "users" };
  if (step === "prices" || step === "lng_shipping" || step === "fx_rates") return { page: "access", view: "catalogue" };
  if (step === "book") return { page: "contracts" };
  return { page: "sources" };
}

function SetupItem({ item, t, context, keyStorageReady, onChanged, onNavigate }: {
  item: SetupItemDTO;
  t: T;
  context: SetupContext;
  keyStorageReady: boolean;
  onChanged: () => void;
  onNavigate: (destination: SetupDestination) => void;
}) {
  const state = itemState(item, context);
  const source = item.source_id ? context.sources[item.source_id] : undefined;
  const needsApproval = (item.connection === "approval" || item.connection === "approval_and_key")
    && source?.approval?.state === "not_approved";
  const wantsKey = Boolean(item.credential_provider)
    && ["key", "model", "approval_and_key", "licensed_key"].includes(item.connection);
  const tariffs = item.connection === "public_tariffs" ? context.terminalTariffs : undefined;
  return (
    <li className="setup-item" data-setup-item={item.item_id} data-setup-tone={state.tone}>
      <div className="setup-item-head">
        <strong>{t(`setup.item.${item.item_id}.name`)}</strong>
        <StatusBadge tone={TONE[state.tone]}>
          {t(state.key)}{state.preview ? ` · ${state.preview}` : ""}
        </StatusBadge>
      </div>
      <p className="setup-item-purpose">{t(`setup.item.${item.item_id}.purpose`)}</p>
      <p className="setup-item-how">{t(`setup.how.${item.connection}`)}</p>
      {tariffs && (
        <p className="setup-item-how">
          {tariffs.held > 0
            ? fill(t("setup.tariffs.held"), { held: tariffs.held, operator: tariffs.from_operator, desk: tariffs.desk_entered })
            : t("setup.tariffs.none")}
        </p>
      )}
      {tariffs && (tariffs.operators_needing_terms ?? []).length > 0 && (
        <p className="setup-item-how">
          {fill(t("setup.tariffs.needs_terms"), { operators: (tariffs.operators_needing_terms ?? []).join(", ") })}
        </p>
      )}
      {item.import_tools && item.import_tools.length > 0 && (
        <p className="setup-item-how">
          {t("setup.import_with")} <code>{item.import_tools.join(" · ")}</code>
        </p>
      )}
      {needsApproval && source?.approval && <ApprovalForm t={t} sourceId={item.source_id!} approval={source.approval} onDone={onChanged} />}
      {wantsKey && keyStorageReady && (
        <KeyForm t={t} item={item} provider={context.providers[item.credential_provider!]} onDone={onChanged} />
      )}
      {(item.connection === "licensed_import" || item.connection === "licensed_none" || item.connection === "licensed_key") && (
        <p className="setup-actions">
          <button type="button" className="setup-link" onClick={() => onNavigate({ page: "access", view: "catalogue" })}>
            {t("setup.record_licence")}
          </button>
        </p>
      )}
      {item.connection === "admin" && (
        <p className="setup-actions">
          <Button size="md" variant="secondary" onClick={() => onNavigate({ page: "access", view: "users" })}>
            {t("setup.open_users")}
          </Button>
        </p>
      )}
    </li>
  );
}

function KeyForm({ t, item, provider, onDone }: {
  t: T;
  item: SetupItemDTO;
  provider: CredentialProviderDTO | undefined;
  onDone: () => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; key: string; detail?: string } | null>(null);
  const providerId = item.credential_provider!;
  const fromEnvironment = provider?.effective_source === "env" || provider?.effective_source === "file";

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!value.trim() || busy) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.saveCredential(providerId, { api_key: value.trim(), label: "setup" });
      // The key is never kept in the page once saved; only the server's redacted preview returns.
      setValue("");
      setMessage({ ok: true, key: "setup.key.saved" });
      onDone();
    } catch {
      setMessage({ ok: false, key: "setup.key.save_failed" });
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await api.testCredentialConnection(providerId);
      const ok = !response.data.connection_status || response.data.connection_status === "ok"
        || response.data.connection_status === "connected";
      setMessage(ok
        ? { ok: true, key: "setup.key.test_ok" }
        : { ok: false, key: "setup.key.test_failed", detail: response.data.connection_error_code ?? response.data.connection_status });
    } catch (error) {
      setMessage({ ok: false, key: "setup.key.test_failed", detail: String(error).replace(/^Error:\s*/, "").slice(0, 160) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="setup-key" onSubmit={(event) => void save(event)}>
      {fromEnvironment ? (
        <p className="setup-item-how">{fill(t("setup.key.from_environment"), { variable: provider?.effective_variable ?? "" })}</p>
      ) : null}
      <label className="setup-key-label" htmlFor={`setup-key-${item.item_id}`}>
        {fill(t("setup.key.label"), { provider: t(`setup.item.${item.item_id}.name`) })}
      </label>
      <div className="setup-key-row">
        <input
          id={`setup-key-${item.item_id}`}
          className="setup-input"
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={value}
          placeholder={provider?.redacted_preview ? t("setup.key.replace") : ""}
          onChange={(event) => setValue(event.target.value)}
        />
        <Button size="md" variant="secondary" type="submit" loading={busy} disabled={!value.trim()}>{t("setup.key.save")}</Button>
        {provider?.connection_test_supported && provider.configured && (
          <Button size="md" variant="quiet" onClick={() => void test()} disabled={busy}>{t("setup.key.test")}</Button>
        )}
      </div>
      {item.key_registration_url && (
        <a className="setup-link" href={item.key_registration_url} target="_blank" rel="noreferrer noopener">
          {t("setup.key.get")}
        </a>
      )}
      {message && (
        <p className={message.ok ? "setup-result" : "setup-result is-problem"} role="status">
          {t(message.key)}{message.detail ? ` (${message.detail})` : ""}
        </p>
      )}
    </form>
  );
}

function ApprovalForm({ t, sourceId, approval, onDone }: {
  t: T;
  sourceId: string;
  approval: NonNullable<SetupSourceFacts["approval"]> & {
    terms?: { provider: string; summary: string; terms_url: string; attribution: string } | null;
  };
  onDone: () => void;
}) {
  const [openForm, setOpenForm] = useState(false);
  const [reason, setReason] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  if (!openForm) {
    return (
      <p className="setup-actions">
        <Button size="md" variant="secondary" onClick={() => setOpenForm(true)}>{t("setup.approval.review")}</Button>
      </p>
    );
  }
  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reason.trim() || !accepted || busy) return;
    setBusy(true);
    try {
      const response = await api.approveSource(sourceId, reason.trim(), true);
      setMessage(t(`source_approval.state.${response.data.state}`) + (response.data.failure ? ` (${response.data.failure})` : ""));
      onDone();
    } catch {
      setMessage(t("source_approval.failed"));
    } finally {
      setBusy(false);
    }
  }
  const terms = approval.terms;
  return (
    <form className="setup-approval" onSubmit={(event) => void approve(event)}>
      {terms && (
        <div className="setup-terms">
          <strong>{terms.provider}</strong>
          <p>{terms.summary}</p>
          <p className="setup-item-how">{t("setup.approval.attribution")} {terms.attribution}</p>
          <a className="setup-link" href={terms.terms_url} target="_blank" rel="noreferrer noopener">{t("setup.approval.read_terms")}</a>
        </div>
      )}
      <label className="setup-key-label" htmlFor={`setup-reason-${sourceId}`}>{t("setup.approval.reason")}</label>
      <input id={`setup-reason-${sourceId}`} className="setup-input" value={reason} maxLength={256} onChange={(event) => setReason(event.target.value)} />
      <label className="setup-check">
        <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
        <span>{t("setup.approval.accept")}</span>
      </label>
      <p className="setup-actions">
        <Button size="md" variant="secondary" type="submit" loading={busy} disabled={!reason.trim() || !accepted}>
          {t("setup.approval.approve")}
        </Button>
      </p>
      {message && <p className="setup-result" role="status">{message}</p>}
    </form>
  );
}
