import { useCallback, useEffect, useState } from "react";

import { api, type NotificationChannelDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const CATEGORIES = ["alert", "support", "limits", "tariff", "source"];
const EMPTY = { channel_id: "", name: "", kind: "email" as "email" | "webhook" | "sms", recipients: "", webhook_url: "", categories: [] as string[], min_severity: "high" };

/**
 * Where notifications go (administrators): email through the firm's SMTP relay, a Teams or
 * Slack webhook (stored encrypted) or SMS through the firm's gateway, each with the
 * categories and minimum severity it receives, a test button and its last delivery.
 */
export function NotificationChannelsPanel({ t }: { t: Translate }) {
  const [rows, setRows] = useState<NotificationChannelDTO[] | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => {
    api.notificationChannels().then((response) => setRows(response.data.rows)).catch(() => setRows(null));
  }, []);
  useEffect(load, [load]);
  if (rows === null) return null; // not an administrator, or the server has no database

  const fail = (caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught));
  const save = () => {
    api.saveNotificationChannel(draft.channel_id.trim(), {
      name: draft.name.trim(),
      kind: draft.kind,
      recipients: draft.kind === "webhook" ? null : draft.recipients,
      webhook_url: draft.kind === "webhook" ? draft.webhook_url || null : null,
      categories: draft.categories,
      min_severity: draft.min_severity,
      enabled: true,
    })
      .then(() => {
        setDraft(EMPTY);
        setMessage(t("notify.saved"));
        load();
      })
      .catch(fail);
  };
  const test = (row: NotificationChannelDTO) => {
    api.testNotificationChannel(row.channel_id)
      .then((response) => setMessage(response.data.sent ? t("notify.test_sent", { name: row.name }) : t("notify.test_failed", { detail: response.data.detail })))
      .catch(fail);
  };
  const toggle = (category: string) =>
    setDraft({
      ...draft,
      categories: draft.categories.includes(category)
        ? draft.categories.filter((item) => item !== category)
        : [...draft.categories, category],
    });

  return (
    <section className="settings-section notification-channels" aria-labelledby="notify-title">
      <h3 id="notify-title">{t("notify.title")}</h3>
      <p className="settings-backend-message">{t("notify.copy")}</p>
      {rows.length > 0 && (
        <table className="position-ladder">
          <thead>
            <tr>
              <th scope="col">{t("notify.name")}</th>
              <th scope="col">{t("notify.kind")}</th>
              <th scope="col">{t("notify.receives")}</th>
              <th scope="col">{t("notify.last")}</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.channel_id}>
                <td><strong>{row.name}</strong> <small>{row.recipients ?? row.webhook ?? ""}</small></td>
                <td>{t(`notify.kind_${row.kind}`)}</td>
                <td><small>{(row.categories.length ? row.categories : [t("notify.all")]).join(", ")} · ≥ {row.min_severity}</small></td>
                <td>{row.last_delivery ? <span className="limit-badge" data-status={row.last_delivery.status === "sent" ? "ok" : "breach"} title={row.last_delivery.detail}>{row.last_delivery.status}</span> : <small className="muted">-</small>}</td>
                <td><button type="button" className="link-button" onClick={() => test(row)}>{t("notify.test")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="licence-form">
        <label><span>{t("notify.channel_id")}</span><input value={draft.channel_id} onChange={(event) => setDraft({ ...draft, channel_id: event.target.value })} /></label>
        <label><span>{t("notify.name")}</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label>
          <span>{t("notify.kind")}</span>
          <select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as typeof draft.kind })}>
            {(["email", "webhook", "sms"] as const).map((kind) => <option key={kind} value={kind}>{t(`notify.kind_${kind}`)}</option>)}
          </select>
        </label>
        {draft.kind === "webhook" ? (
          <label><span>{t("notify.webhook")}</span><input type="url" value={draft.webhook_url} placeholder="https://" onChange={(event) => setDraft({ ...draft, webhook_url: event.target.value })} /></label>
        ) : (
          <label><span>{t(draft.kind === "sms" ? "notify.numbers" : "notify.emails")}</span><input value={draft.recipients} onChange={(event) => setDraft({ ...draft, recipients: event.target.value })} /></label>
        )}
        <label>
          <span>{t("notify.min_severity")}</span>
          <select value={draft.min_severity} onChange={(event) => setDraft({ ...draft, min_severity: event.target.value })}>
            {["info", "low", "medium", "high", "critical"].map((level) => <option key={level} value={level}>{level}</option>)}
          </select>
        </label>
        <fieldset className="notify-categories">
          <legend>{t("notify.receives")}</legend>
          {CATEGORIES.map((category) => (
            <label key={category} className="checkbox-row">
              <input type="checkbox" checked={draft.categories.includes(category)} onChange={() => toggle(category)} />
              <span>{t(`notify.category_${category}`)}</span>
            </label>
          ))}
        </fieldset>
        <button type="button" disabled={!draft.channel_id.trim() || !draft.name.trim()} onClick={save}>{t("notify.save")}</button>
      </div>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
