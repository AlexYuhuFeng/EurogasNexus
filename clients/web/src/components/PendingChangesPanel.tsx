/**
 * Changes awaiting approval (P-17 maker-checker): each proposed change to a limit, a hedge band,
 * the firm's marks or LNG reference data, with who proposed it, what it changes (each field
 * before and after), why and since when. A different authorised person approves or rejects it;
 * the proposer can withdraw it. Nothing takes effect until it is approved, and every step is
 * audited on the server in the same transaction as the change.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, type ChangeRequestDTO } from "@/api/client";
import { useCachedRead } from "@/app/data/readCache";
import {
  changeErrorKey,
  changeValueText,
  fieldLabel,
  orderChanges,
  personName,
} from "@/app/model/makerCheckerModel";
import { Button, Field, Instant, Panel, Segmented, StatusBadge, UpdatingMark } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;
type View = "pending" | "decided";

export const PENDING_CHANGES_KEY = "/portfolio/change-requests?state=pending";

const STATE_TONE = { pending: "watch", approved: "ok", rejected: "breach", withdrawn: "neutral" } as const;

function ChangeCard({
  change,
  t,
  zh,
  onDone,
}: {
  change: ChangeRequestDTO;
  t: Translate;
  zh: boolean;
  onDone: () => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const words = { yes: t("changes.value_yes"), no: t("changes.value_no") };

  const act = (call: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    call()
      .then(onDone)
      .catch((caught: unknown) => {
        const key = caught instanceof ApiError ? changeErrorKey(caught.detail) : null;
        setError(key ? t(key) : caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => setBusy(false));
  };

  const pending = change.state === "pending";
  return (
    <article className="pending-change" data-change-state={change.state} data-change-kind={change.kind}>
      <header className="pending-change-head">
        <strong>{zh ? change.label_zh : change.label}</strong>
        <span>{change.subject || change.target_key}</span>
        {change.new_record && <StatusBadge tone="neutral">{t("changes.new_record")}</StatusBadge>}
        <StatusBadge tone={STATE_TONE[change.state]}>{t(`changes.state.${change.state}`)}</StatusBadge>
      </header>
      <p className="pending-change-meta">
        {t("changes.proposed_by", { name: personName(change.proposed_by_name, change.proposed_by) })}{" "}
        <Instant value={change.proposed_at_utc} prefix={t("changes.since")} />
        {" · "}
        {t(`changes.approver.${change.approver}`)}
      </p>
      {change.reason && (
        <p className="pending-change-reason">
          <span className="pending-change-label">{t("changes.why")}</span> {change.reason}
        </p>
      )}
      <table className="pending-change-fields">
        <thead>
          <tr>
            <th scope="col">{t("changes.field")}</th>
            <th scope="col">{t("changes.before")}</th>
            <th scope="col">{t("changes.after")}</th>
          </tr>
        </thead>
        <tbody>
          {change.fields.map((field) => (
            <tr key={field.name}>
              <th scope="row">{fieldLabel(field.name)}</th>
              <td>{changeValueText(field.before, words)}</td>
              <td>
                <strong>{changeValueText(field.after, words)}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!pending && (
        <p className="pending-change-meta">
          {t(`changes.decided.${change.state}`, {
            name: personName(change.decided_by_name, change.decided_by),
          })}{" "}
          <Instant value={change.decided_at_utc} />
          {change.decision_note ? ` · ${change.decision_note}` : ""}
        </p>
      )}
      {pending && change.own && <p className="pending-change-meta">{t("changes.own_hint")}</p>}
      {pending && rejecting && (
        <Field label={t("changes.reject_note")} hint={t("changes.reject_note_hint")}>
          <textarea className="ds-input" rows={2} maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
      )}
      {error && (
        <p className="pending-change-error" role="alert">
          {error}
        </p>
      )}
      {pending && (change.may_approve || change.may_reject || change.may_withdraw) && (
        <div className="pending-change-actions">
          {change.may_approve && !rejecting && (
            <Button variant="primary" size="sm" disabled={busy} onClick={() => act(() => api.approveChangeRequest(change.change_id))}>
              {t("changes.approve")}
            </Button>
          )}
          {change.may_reject && !rejecting && (
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => setRejecting(true)}>
              {t("changes.reject")}
            </Button>
          )}
          {change.may_reject && rejecting && (
            <>
              <Button
                variant="danger"
                size="sm"
                disabled={busy || !note.trim()}
                onClick={() => act(() => api.rejectChangeRequest(change.change_id, note.trim()))}
              >
                {t("changes.reject_confirm")}
              </Button>
              <Button variant="quiet" size="sm" disabled={busy} onClick={() => setRejecting(false)}>
                {t("changes.cancel")}
              </Button>
            </>
          )}
          {change.may_withdraw && (
            <Button variant="quiet" size="sm" disabled={busy} onClick={() => act(() => api.withdrawChangeRequest(change.change_id))}>
              {t("changes.withdraw")}
            </Button>
          )}
        </div>
      )}
    </article>
  );
}

export function PendingChangesPanel({ t }: { t: Translate }) {
  const { i18n } = useTranslation();
  const zh = (i18n.language ?? "").toLowerCase().startsWith("zh");
  const [view, setView] = useState<View>("pending");
  const pendingRead = useCachedRead(PENDING_CHANGES_KEY, () => api.changeRequests("pending"));
  const decidedRead = useCachedRead(view === "decided" ? "/portfolio/change-requests?state=decided" : null, () =>
    api.changeRequests("decided"),
  );
  const read = view === "pending" ? pendingRead : decidedRead;
  const changes = useMemo(() => orderChanges(read.data?.data.changes ?? []), [read.data]);
  const pendingCount = (pendingRead.data?.data.changes ?? []).length;
  const fourEyes = pendingRead.data?.data.four_eyes ?? [];
  const switchedOff = fourEyes.filter((write) => !write.required);
  const refresh = () => {
    pendingRead.refresh();
    decidedRead.refresh();
  };

  return (
    <Panel
      className="span-3 pending-changes-panel"
      title={t("changes.title")}
      meta={pendingCount > 0 ? <StatusBadge tone="watch">{t("changes.pending_count", { count: pendingCount })}</StatusBadge> : null}
      actions={
        <>
          <UpdatingMark active={read.updating} label={t("status.updating")} />
          <Segmented<View>
            label={t("changes.view")}
            value={view}
            onChange={setView}
            options={[
              { value: "pending", label: t("changes.view_pending") },
              { value: "decided", label: t("changes.view_decided") },
            ]}
          />
        </>
      }
    >
      <p className="pending-changes-purpose">{t("changes.purpose")}</p>
      {switchedOff.length > 0 && (
        <p className="pending-changes-off" data-four-eyes-off="true">
          {t("changes.switched_off", { writes: switchedOff.map((write) => (zh ? write.label_zh : write.label)).join(", ") })}
        </p>
      )}
      {read.error && !read.data ? (
        <p className="pending-change-error" role="alert">
          {t("changes.load_failed")}
        </p>
      ) : null}
      {read.data && changes.length === 0 && (
        <p className="pending-changes-empty">{t(view === "pending" ? "changes.empty_pending" : "changes.empty_decided")}</p>
      )}
      <div className="pending-changes-list" data-pending-changes="true">
        {changes.map((change) => (
          <ChangeCard key={change.change_id} change={change} t={t} zh={zh} onDone={refresh} />
        ))}
      </div>
    </Panel>
  );
}
