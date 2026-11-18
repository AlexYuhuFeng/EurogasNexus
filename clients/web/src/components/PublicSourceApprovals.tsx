/**
 * Public-source approvals on Admin → Connectors.
 *
 * ENTSOG and GIE are read only after an administrator approves them for the firm (the
 * fail-closed ingestion gate). A fresh installation therefore shows here, in plain words, what
 * stands between it and live data: "Not approved yet", "Approved, waiting for key", "Running" or
 * "Failing" with the reason. Before approving, the administrator reads each provider's terms
 * summary (docs/legal/DATA_SOURCE_TERMS.md) and states a reason; the server records who, when and
 * why, audits it and runs the bounded live validation. The product never accepts terms itself,
 * and only an ADMIN may approve: the server checks it, the button here only mirrors it.
 */

import { useEffect, useState } from "react";

import { api, type SourceSystemDTO } from "@/api/client";
import { Button, PanelHeader, StatusBadge } from "@/components/ui";
import type { StatusTone } from "@/components/ui/StatusBadge";
import { useApiStore } from "@/stores/api";
import "./public-source-approvals.css";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const TONE: Record<string, StatusTone> = {
  not_approved: "watch",
  approved_waiting_for_key: "watch",
  approved: "info",
  running: "ok",
  failing: "breach",
};

/** Approval-required sources, in registry order. */
export function approvalSources(sources: readonly SourceSystemDTO[]): SourceSystemDTO[] {
  return sources.filter((source) => source.approval?.required);
}

export function openApprovals(sources: readonly SourceSystemDTO[]): SourceSystemDTO[] {
  return approvalSources(sources).filter((source) => source.approval?.state === "not_approved");
}

export function PublicSourceApprovals({ sources, t }: { sources: readonly SourceSystemDTO[]; t: Translate }) {
  const currentUser = useApiStore((state) => state.currentUser);
  const isAdmin = Boolean(currentUser?.roles?.includes("ADMIN") || currentUser?.role === "ADMIN");
  const [pending, setPending] = useState<readonly string[] | null>(null);
  // The same form approves or, for an approved source, revokes (with its own confirmation).
  const [mode, setMode] = useState<"approve" | "revoke">("approve");
  const [reason, setReason] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const listed = approvalSources(sources);
  if (listed.length === 0) return null;
  const open = openApprovals(sources);
  const chosen = listed.filter((source) => pending?.includes(source.source_id));

  const start = (ids: readonly string[], next: "approve" | "revoke" = "approve") => {
    setMode(next);
    setPending(ids);
    setReason("");
    setAccepted(false);
    setMessage(null);
  };

  const submit = async () => {
    if (!pending || !reason.trim() || !accepted) return;
    setBusy(true);
    setMessage(null);
    const results: string[] = [];
    for (const sourceId of pending) {
      try {
        if (mode === "revoke") {
          const response = await api.revokeSourceApproval(sourceId, reason.trim());
          results.push(`${sourceId}: ${t(`source_approval.state.${response.data.state}`)}`);
          continue;
        }
        const response = await api.approveSource(sourceId, reason.trim(), true);
        const failure = response.data.failure ? ` (${response.data.failure})` : "";
        results.push(`${sourceId}: ${t(`source_approval.state.${response.data.state}`)}${failure}`);
      } catch {
        results.push(`${sourceId}: ${t(mode === "revoke" ? "source_approval.revoke_failed" : "source_approval.failed")}`);
      }
    }
    setBusy(false);
    setPending(null);
    setMessage(results.join(" · "));
    // Re-read the registry so each source shows its new state (an administrator has no market
    // lane to refresh it with).
    try {
      const response = await api.sources();
      useApiStore.setState({ sources: response.data });
    } catch {
      // The next workspace read shows it; the result line above already says what happened.
    }
  };

  return (
    <section
      className="workspace-panel span-3 public-source-approvals"
      aria-labelledby="public-source-approvals-title"
      data-record="public-source-approvals"
    >
      <PanelHeader
        headingId="public-source-approvals-title"
        title={t("source_approval.title")}
        meta={t("source_approval.meta")}
        actions={
          isAdmin && open.length > 1 ? (
            <Button size="sm" variant="secondary" onClick={() => start(open.map((source) => source.source_id))}>
              {t("source_approval.approve_all", { count: open.length })}
            </Button>
          ) : undefined
        }
      />
      <ul className="public-source-approval-list">
        {listed.map((source) => {
          const approval = source.approval!;
          return (
            <li key={source.source_id} data-record-id={source.source_id} data-approval-state={approval.state}>
              <strong>{approval.terms?.provider ?? source.source_system}</strong>
              <StatusBadge tone={TONE[approval.state] ?? "neutral"}>
                {t(`source_approval.state.${approval.state}`)}
              </StatusBadge>
              <span className="muted">
                {approval.state === "failing" && approval.reason
                  ? approval.reason
                  : approval.approved_by
                    ? t("source_approval.approved_by", {
                        name: approval.approved_by,
                        when: (approval.approved_at_utc ?? "").slice(0, 10),
                      })
                    : t(`source_approval.next.${approval.state}`)}
              </span>
              {isAdmin && approval.state !== "not_approved" && (
                <Button size="sm" variant="quiet" onClick={() => start([source.source_id], "revoke")}>
                  {t("source_approval.revoke")}
                </Button>
              )}
              {approval.state === "not_approved" && (isAdmin ? (
                <Button size="sm" onClick={() => start([source.source_id])}>
                  {t("source_approval.approve")}
                </Button>
              ) : (
                <span className="muted">{t("source_approval.ask_admin")}</span>
              ))}
            </li>
          );
        })}
      </ul>
      {pending && chosen.length > 0 && (
        <form
          className="public-source-approval-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <p>{t(mode === "revoke" ? "source_approval.revoke_intro" : "source_approval.terms_intro")}</p>
          {mode === "approve" && chosen.map((source) => (
            <div key={source.source_id} className="public-source-approval-terms">
              <strong>{source.approval?.terms?.provider}</strong>
              <p>{source.approval?.terms?.summary}</p>
              <p className="muted">
                {t("source_approval.attribution")}: {source.approval?.terms?.attribution} ·{" "}
                <a href={source.approval?.terms?.terms_url} target="_blank" rel="noreferrer">
                  {t("source_approval.terms_link")}
                </a>
              </p>
            </div>
          ))}
          <label htmlFor="public-source-approval-reason">{t("source_approval.reason")}</label>
          <input
            id="public-source-approval-reason"
            value={reason}
            maxLength={512}
            required
            onChange={(event) => setReason(event.target.value)}
          />
          <label className="settings-checkbox">
            <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
            {t(mode === "revoke" ? "source_approval.revoke_accept" : "source_approval.accept")}
          </label>
          <div className="public-source-approval-actions">
            <Button
              type="submit"
              variant={mode === "revoke" ? "danger" : "primary"}
              disabled={busy || !reason.trim() || !accepted}
            >
              {busy
                ? t(mode === "revoke" ? "source_approval.revoking" : "source_approval.approving")
                : t(mode === "revoke" ? "source_approval.revoke_confirm" : "source_approval.confirm", { count: chosen.length })}
            </Button>
            <Button variant="quiet" onClick={() => setPending(null)} disabled={busy}>
              {t("source_approval.cancel")}
            </Button>
          </div>
        </form>
      )}
      {message && <p role="status" className="public-source-approval-result">{message}</p>}
    </section>
  );
}

const DATA_KEY: Record<string, string> = {
  "src-entsog": "source_approval.data.entsog",
  "src-gie": "source_approval.data.gie",
};

/**
 * One line on the data screens for each public source the gate holds back: "ENTSOG flows: source
 * not approved — Admin → Connectors", with the link. Nothing when every source reads.
 */
export function SourceApprovalNotice({
  sources,
  t,
  onOpen,
}: {
  sources: readonly SourceSystemDTO[];
  t: Translate;
  onOpen: () => void;
}) {
  const held = approvalSources(sources).filter((source) =>
    ["not_approved", "approved_waiting_for_key", "failing"].includes(source.approval?.state ?? ""),
  );
  if (held.length === 0) return null;
  return (
    <p className="source-approval-notice" role="status" data-record="source-approval-notice">
      {held.map((source) => (
        <span key={source.source_id} data-record-id={source.source_id}>
          {DATA_KEY[source.source_id] ? t(DATA_KEY[source.source_id]) : source.source_system}:{" "}
          {t(`source_approval.held.${source.approval?.state}`)}
        </span>
      ))}
      <Button size="sm" variant="quiet" onClick={onOpen}>
        {t("source_approval.open_connectors")}
      </Button>
    </p>
  );
}

interface CatchUpProgress {
  running?: boolean;
  done?: number;
  total?: number;
  step?: string;
}

/**
 * The demo's first live-data catch-up, stated to those who run sources (ADMIN, OPERATOR) and
 * never to traders: "Live data is catching up - 6 of 16 sources done". The server sends it only
 * on the demo profile and only to them; this line polls while a round runs.
 */
export function DemoCatchUpLine({ t }: { t: Translate }) {
  const currentUser = useApiStore((state) => state.currentUser);
  const runsSources = Boolean(currentUser?.roles?.some((role) => role === "ADMIN" || role === "OPERATOR"));
  const [progress, setProgress] = useState<CatchUpProgress | null>(null);
  useEffect(() => {
    if (!runsSources) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const read = async () => {
      try {
        const response = await api.sources();
        const meta = (response.meta ?? {}) as { demo_catch_up?: CatchUpProgress };
        if (cancelled) return;
        setProgress(meta.demo_catch_up ?? null);
        if (meta.demo_catch_up?.running) timer = window.setTimeout(read, 30_000);
      } catch {
        if (!cancelled) timer = window.setTimeout(read, 60_000);
      }
    };
    void read();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [runsSources]);
  if (!runsSources || !progress?.running) return null;
  return (
    <p className="source-approval-notice span-3" role="status" data-record="demo-catch-up">
      {t("source_approval.catch_up", { done: progress.done ?? 0, total: progress.total ?? 0 })}
      {progress.step ? ` · ${progress.step}` : ""}
    </p>
  );
}
