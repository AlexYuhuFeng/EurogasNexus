import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Instant } from "@/components/ui";
import {
  api,
  type MonitoringAlertDTO,
  type MonitoringAnalysisDTO,
  type MonitoringSummaryDTO,
} from "@/api/client";
import { aiActionContract, aiActionIsAvailable } from "@/app/experience/aiActions";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  alertCounts,
  applyReaderAction,
  categoryKey,
  groupAlerts,
  memberIds,
  type AlertGroup,
  type AlertReaderAction,
  type AlertReaderMarks,
} from "@/app/alerts/alertCenterModel";
import { WhyButton } from "./WhyButton";
import { useAiAvailability } from "@/app/model/aiAvailability";
import { ReportLink } from "./ReportLink";
import { IconButton } from "./ui/Button";
import { JobActivityIndicator, JobNotifications } from "./JobNotifications";
import { Icon } from "@/components/ui/Icon";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface AlertCenterProps {
  alerts: MonitoringAlertDTO[];
  /** Kept for callers; the counts on the bar come from the same list the drawer shows. */
  summary?: MonitoringSummaryDTO;
  analysisByAlert: Record<string, MonitoringAnalysisDTO>;
  busyAlertId: string | null;
  language: string;
  t: Translate;
  onAcknowledge: (alertId: string) => Promise<void>;
  onAnalyze: (alertId: string, question: string, language: "en" | "zh-CN") => Promise<void>;
}

type View = "active" | "dismissed";

interface ReaderFailure {
  action: AlertReaderAction | "load";
  ids: string[];
  title: string;
  hint: string;
}

/**
 * The canonical action an alert question runs as.
 *
 * Wave 7 convergence: this surface used to offer its own provider-branded question button
 * with no gating, which is exactly the competing magic-AI entry point the V2 AI contract
 * forbids. It is now the declared `ask` action - same contract, same posture copy, same
 * evidence rule - over the alert-analysis route.
 *
 * The alert analysis composes from the persisted alert snapshot the backend loads by id,
 * so the alert itself is the invocation context; what a question still needs is evidence,
 * and an alert without source references has none. That is why only the evidence
 * requirement is applied here, and why it is applied rather than assumed.
 */
const ALERT_ASK_ACTION = "ask" as const;

/**
 * The desk's alert centre.
 *
 * Alerts are shared and their acknowledgement is audited; reading and dismissing are the
 * reader's own (`/api/me/alert-state`) and lapse when an alert escalates or comes back.
 * Repeats of one condition are one row, the list is ordered by what needs the reader first,
 * and the number on the bar counts the unread rows of that same list, so the two agree.
 */
export function AlertCenter({
  alerts,
  analysisByAlert,
  busyAlertId,
  language,
  t,
  onAcknowledge,
  onAnalyze,
}: AlertCenterProps) {
  // AI off (small-desk 3.6): the Ask control is not offered; Why? still answers by rule.
  const aiOn = useAiAvailability().available;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("active");
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [activeAlertId, setActiveAlertId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [marks, setMarks] = useState<AlertReaderMarks>({});
  const [failure, setFailure] = useState<ReaderFailure | null>(null);
  const [pending, setPending] = useState(false);
  const drawerRef = useRef<HTMLElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const isChinese = language === "zh-CN";

  const groups = useMemo(() => groupAlerts(alerts, marks), [alerts, marks]);
  const counts = useMemo(() => alertCounts(groups), [groups]);
  const shown = useMemo(
    () => groups.filter((group) => (view === "dismissed" ? group.dismissed : !group.dismissed)),
    [groups, view],
  );
  const alertKey = useMemo(
    () =>
      alerts
        .filter((alert) => alert.status !== "resolved")
        .map((alert) => `${alert.alert_id}:${alert.severity}`)
        .sort()
        .join(","),
    [alerts],
  );

  const explain = useCallback(
    (cause: unknown, action: ReaderFailure["action"], ids: string[]) => {
      const text = presentError(t, describeFailure(cause));
      setFailure({
        action,
        ids,
        title: t(`alerts.error.${action}`),
        hint: `${text.cause} ${text.action}`.trim(),
      });
    },
    [t],
  );

  const loadMarks = useCallback(async () => {
    try {
      const response = await api.alertReaderState();
      setMarks(response.data.alerts ?? {});
      setFailure((current) => (current?.action === "load" ? null : current));
    } catch (caught) {
      explain(caught, "load", []);
    }
  }, [explain]);

  // The marks follow the list: a new, returning or escalated alert has none until read.
  useEffect(() => {
    if (!alertKey) return;
    void loadMarks();
  }, [alertKey, loadMarks]);

  // Escape closes the drawer and gives focus back to the bar.
  useEffect(() => {
    if (!open) return undefined;
    drawerRef.current?.querySelector<HTMLButtonElement>(".alert-drawer-header button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function mark(action: AlertReaderAction, ids: string[]) {
    if (ids.length === 0) return;
    const before = marks;
    // The answer shows at once; the server's record replaces it, or a failure puts it back.
    setMarks(applyReaderAction(marks, action, ids, new Date().toISOString()));
    setPending(true);
    try {
      const response = await api.markAlerts(action, ids);
      setMarks((current) => ({ ...current, ...(response.data.alerts ?? {}) }));
      setFailure(null);
    } catch (caught) {
      setMarks(before);
      explain(caught, action, ids);
    } finally {
      setPending(false);
    }
  }

  function retry() {
    if (!failure) return;
    if (failure.action === "load") void loadMarks();
    else void mark(failure.action, failure.ids);
  }

  function toggleRow(group: AlertGroup) {
    const next = expandedKey === group.key ? null : group.key;
    setExpandedKey(next);
    if (next && group.unread) void mark("read", group.members.map((member) => member.alert_id));
  }

  function startDiscussion(alert: MonitoringAlertDTO) {
    const nextActive = activeAlertId === alert.alert_id ? null : alert.alert_id;
    setActiveAlertId(nextActive);
    setQuestion(nextActive ? t("alerts.ask.default_question") : "");
  }

  async function acknowledgeGroup(group: AlertGroup) {
    for (const member of group.members) {
      if (member.status === "open") await onAcknowledge(member.alert_id);
    }
  }

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  const unreadIds = memberIds(shown.filter((group) => group.unread));
  const triggerClass = [
    "alert-trigger",
    counts.unread > 0 ? "active" : "",
    counts.unreadCritical > 0 ? "critical" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className="alert-center">
      <button
        ref={triggerRef}
        className={triggerClass}
        type="button"
        aria-expanded={open}
        aria-label={t("alerts.trigger_label", { count: counts.unread })}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="alert-trigger-mark" aria-hidden="true" />
        <Icon name="alerts" className="alert-trigger-icon" />
        <span>{t("alerts.title")}</span>
        {counts.unread > 0 && <strong>{counts.unread}</strong>}
        <JobActivityIndicator t={t} />
      </button>

      {open && (
        <aside ref={drawerRef} className="alert-drawer" aria-label={t("alerts.drawer_label")}>
          <div className="alert-drawer-header">
            <div>
              <span>{t("alerts.kicker")}</span>
              <strong>{t("alerts.title")}</strong>
            </div>
            <IconButton label={t("alerts.close")} icon="close" onClick={close} />
          </div>
          {/* Nothing held at all: one empty line, not three zero tiles and four disabled buttons. */}
          {counts.active + counts.dismissed > 0 && (<>
          <div className="alert-summary-strip">
            <span><strong>{counts.unread}</strong>{t("alerts.count.unread")}</span>
            <span><strong>{counts.critical}</strong>{t("alerts.count.critical")}</span>
            <span><strong>{counts.warning}</strong>{t("alerts.count.warning")}</span>
          </div>
          <div className="alert-toolbar">
            <div className="alert-view-switch" role="group" aria-label={t("alerts.view.label")}>
              <button type="button" aria-pressed={view === "active"} onClick={() => setView("active")}>
                {t("alerts.view.active", { count: counts.active })}
              </button>
              <button type="button" aria-pressed={view === "dismissed"} onClick={() => setView("dismissed")}>
                {t("alerts.view.dismissed", { count: counts.dismissed })}
              </button>
            </div>
            <div className="alert-bulk-actions">
              {view === "active" ? (
                <>
                  <button
                    type="button"
                    disabled={pending || unreadIds.length === 0}
                    onClick={() => void mark("read", unreadIds)}
                  >
                    {t("alerts.action.mark_all_read")}
                  </button>
                  <button
                    type="button"
                    disabled={pending || shown.length === 0}
                    title={t("alerts.dismiss_hint")}
                    onClick={() => void mark("dismiss", memberIds(shown))}
                  >
                    {t("alerts.action.dismiss_all")}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  disabled={pending || shown.length === 0}
                  onClick={() => void mark("restore", memberIds(shown))}
                >
                  {t("alerts.action.restore_all")}
                </button>
              )}
            </div>
          </div>
          </>)}
          {failure && (
            <div className="alert-reader-error" role="alert">
              <strong>{failure.title}</strong>
              <span>{failure.hint}</span>
              <button type="button" onClick={retry}>{t("alerts.action.retry")}</button>
            </div>
          )}

          <div className="alert-list">
            <JobNotifications t={t} onNavigate={() => setOpen(false)} />
            {shown.map((group) => {
              const alert = group.lead;
              const expanded = expandedKey === group.key;
              const analysis = analysisByAlert[alert.alert_id];
              const discussing = activeAlertId === alert.alert_id;
              const title = isChinese ? alert.title_zh_cn : alert.title_en;
              const message = isChinese ? alert.message_zh_cn : alert.message_en;
              const llmSummary = isChinese ? alert.llm_summary_zh_cn : alert.llm_summary_en;
              const ids = group.members.map((member) => member.alert_id);
              const anyOpen = group.members.some((member) => member.status === "open");
              const busy = group.members.some((member) => member.alert_id === busyAlertId);
              // The canonical action contract decides whether the action may be offered,
              // so an alert with no evidence reference withholds it instead of letting the
              // model guess.
              const contract = aiActionContract(ALERT_ASK_ACTION);
              const evidenceRefs = alert.source_refs ?? [];
              const askAvailable =
                contract.action === ALERT_ASK_ACTION &&
                aiActionIsAvailable(ALERT_ASK_ACTION, {
                  activeContextComplete: true,
                  evidenceRefCount: evidenceRefs.length,
                });
              const rowClass = [
                "monitoring-alert",
                `severity-${group.severity}`,
                group.unread ? "unread" : "read",
              ].join(" ");
              return (
                <article key={group.key} className={rowClass}>
                  <div className="monitoring-alert-heading">
                    <span>
                      {t(categoryKey(alert.category))} · {t(`alerts.severity.${group.severity}`)}
                    </span>
                    <Instant value={alert.event_time_utc} />
                  </div>
                  <button
                    type="button"
                    className="monitoring-alert-title"
                    aria-expanded={expanded}
                    onClick={() => toggleRow(group)}
                  >
                    {group.unread && (
                      <span className="monitoring-alert-unread" role="img" aria-label={t("alerts.unread")} />
                    )}
                    <span>{title}</span>
                  </button>
                  {(group.members.length > 1 || group.acknowledged || group.simulated) && (
                    <div className="monitoring-alert-flags">
                      {group.members.length > 1 && (
                        <span>
                          {t("alerts.notices", { count: group.members.length })} · {t("alerts.since")}{" "}
                          <Instant value={group.since} />
                        </span>
                      )}
                      {group.acknowledged && <span>{t("alerts.acknowledged")}</span>}
                      {group.simulated && <span>{t("alerts.simulated_input")}</span>}
                    </div>
                  )}
                  {expanded && (
                    <>
                      <p>{message}</p>
                      {llmSummary && (
                        <div className="alert-ai-summary">
                          {/* The stored summary names the provider the backend used. */}
                          <strong>{alert.llm_provider_id}</strong>
                          <p>{llmSummary}</p>
                        </div>
                      )}
                      <div className="monitoring-alert-actions">
                        <WhyButton subject="alert" id={alert.alert_id} label={title} language={language} t={t} />
                        <ReportLink subject={{ kind: "alert", id: alert.alert_id }} label={title} t={t} />
                        {aiOn && <button
                          type="button"
                          disabled={!askAvailable}
                          title={askAvailable ? undefined : t("experience.copilot.withheld_evidence")}
                          onClick={() => startDiscussion(alert)}
                        >
                          {t("experience.ai.ask")}
                        </button>}
                        {anyOpen && (
                          <button
                            type="button"
                            disabled={busy}
                            title={t("alerts.acknowledge_hint")}
                            onClick={() => void acknowledgeGroup(group)}
                          >
                            {t("alerts.action.acknowledge")}
                          </button>
                        )}
                        {group.dismissed ? (
                          <button type="button" disabled={pending} onClick={() => void mark("restore", ids)}>
                            {t("alerts.action.restore")}
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={pending}
                            title={t("alerts.dismiss_hint")}
                            onClick={() => void mark("dismiss", ids)}
                          >
                            {t("alerts.action.dismiss")}
                          </button>
                        )}
                      </div>
                      {discussing && askAvailable && (
                        <div className="alert-action-contract">
                          <span>{t("experience.copilot.posture")}: {t(`experience.copilot.posture.${contract.posture}`)}</span>
                          <span>{t("experience.copilot.produces")}: {t(`experience.copilot.produces.${contract.action}`)}</span>
                          <span>
                            {t("experience.copilot.evidence")}:{" "}
                            {evidenceRefs.length > 0
                              ? evidenceRefs.join(", ")
                              : t("experience.copilot.carries_none")}
                          </span>
                        </div>
                      )}
                      {!askAvailable && (
                        <p className="alert-action-withheld">{t("experience.copilot.withheld_evidence")}</p>
                      )}
                      {discussing && askAvailable && (
                        <div className="alert-discussion">
                          <textarea
                            value={question}
                            maxLength={2000}
                            onChange={(event) => setQuestion(event.target.value)}
                            aria-label={t("experience.copilot.question")}
                          />
                          <button
                            type="button"
                            disabled={!question.trim() || busyAlertId === alert.alert_id}
                            onClick={() => void onAnalyze(
                              alert.alert_id,
                              question.trim(),
                              isChinese ? "zh-CN" : "en",
                            )}
                          >
                            {busyAlertId === alert.alert_id
                              ? t("experience.copilot.running")
                              : t("experience.copilot.run")}
                          </button>
                          {analysis && (
                            <div className={`alert-analysis-result status-${analysis.provider_status}`}>
                              {/* Provenance, not branding: the backend reports which provider answered. */}
                              <strong>{analysis.provider_id} · {analysis.provider_status}</strong>
                              <p>{analysis.answer ?? t("experience.copilot.error_title")}</p>
                            </div>
                          )}
                          {analysis && (
                            <p className="alert-action-contract">
                              {t("experience.copilot.result_interpretation")}
                            </p>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </article>
              );
            })}
            {shown.length === 0 && (
              <div className="alert-empty-state">
                <strong>{t(view === "dismissed" ? "alerts.empty.dismissed" : "alerts.empty.active")}</strong>
                <span>{t(view === "dismissed" ? "alerts.empty.dismissed_hint" : "alerts.empty.active_hint")}</span>
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
