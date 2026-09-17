import { useMemo, useState } from "react";
import type {
  MonitoringAlertDTO,
  MonitoringAnalysisDTO,
  MonitoringSummaryDTO,
} from "@/api/client";
import { aiActionContract, aiActionIsAvailable } from "@/app/experience/aiActions";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface AlertCenterProps {
  alerts: MonitoringAlertDTO[];
  summary: MonitoringSummaryDTO;
  analysisByAlert: Record<string, MonitoringAnalysisDTO>;
  busyAlertId: string | null;
  language: string;
  t: Translate;
  onAcknowledge: (alertId: string) => Promise<void>;
  onAnalyze: (alertId: string, question: string, language: "en" | "zh-CN") => Promise<void>;
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

export function AlertCenter({
  alerts,
  summary,
  analysisByAlert,
  busyAlertId,
  language,
  t,
  onAcknowledge,
  onAnalyze,
}: AlertCenterProps) {
  const [open, setOpen] = useState(false);
  const [activeAlertId, setActiveAlertId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const isChinese = language === "zh-CN";
  const activeAlerts = useMemo(
    () => alerts.filter((alert) => alert.status !== "resolved"),
    [alerts],
  );

  function startDiscussion(alert: MonitoringAlertDTO) {
    const nextActive = activeAlertId === alert.alert_id ? null : alert.alert_id;
    setActiveAlertId(nextActive);
    setQuestion(
      nextActive
        ? isChinese
          ? "请结合证据解释影响、缺失信息和交易员下一步应核查的事项。"
          : "Explain the impact, missing evidence, and the trader checks required next."
        : "",
    );
  }

  return (
    <div className="alert-center">
      <button
        className={summary.open_count > 0 ? "alert-trigger active" : "alert-trigger"}
        type="button"
        aria-expanded={open}
        aria-label={isChinese ? "打开实时告警" : "Open live alerts"}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="alert-trigger-mark" aria-hidden="true" />
        <span>{isChinese ? "告警" : "Alerts"}</span>
        <strong>{summary.open_count}</strong>
      </button>

      {open && (
        <aside className="alert-drawer" aria-label={isChinese ? "实时监控告警" : "Live monitoring alerts"}>
          <div className="alert-drawer-header">
            <div>
              <span>{isChinese ? "实时监控" : "LIVE MONITORING"}</span>
              <strong>{isChinese ? "决策告警" : "Decision alerts"}</strong>
            </div>
            <button type="button" aria-label={isChinese ? "关闭" : "Close"} onClick={() => setOpen(false)}>×</button>
          </div>
          <div className="alert-summary-strip">
            <span><strong>{summary.critical_count}</strong>{isChinese ? " 严重" : " critical"}</span>
            <span><strong>{summary.warning_count}</strong>{isChinese ? " 警告" : " warning"}</span>
            <span><strong>{summary.llm_pending_count}</strong>{isChinese ? " 待分析" : " awaiting AI"}</span>
          </div>

          <div className="alert-list">
            {activeAlerts.map((alert) => {
              const analysis = analysisByAlert[alert.alert_id];
              const discussing = activeAlertId === alert.alert_id;
              const title = isChinese ? alert.title_zh_cn : alert.title_en;
              const message = isChinese ? alert.message_zh_cn : alert.message_en;
              const llmSummary = isChinese ? alert.llm_summary_zh_cn : alert.llm_summary_en;
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
              return (
                <article key={alert.alert_id} className={`monitoring-alert severity-${alert.severity}`}>
                  <div className="monitoring-alert-heading">
                    <span>{alert.category.replace(/_/g, " ")}</span>
                    <time>{new Date(alert.updated_at_utc).toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit" })}</time>
                  </div>
                  <h2>{title}</h2>
                  <p>{message}</p>
                  <div className="monitoring-alert-flags">
                    <span>{alert.severity}</span>
                    <span>{alert.status}</span>
                    {alert.simulated && <span>{isChinese ? "模拟价格输入" : "simulated price input"}</span>}
                    <span>{alert.occurrence_count}×</span>
                  </div>
                  {llmSummary && (
                    <div className="alert-ai-summary">
                      {/* The stored summary names the provider the backend used. */}
                      <strong>{alert.llm_provider_id}</strong>
                      <p>{llmSummary}</p>
                    </div>
                  )}
                  <div className="monitoring-alert-actions">
                    <button
                      type="button"
                      disabled={!askAvailable}
                      title={askAvailable ? undefined : t("experience.copilot.withheld_evidence")}
                      onClick={() => startDiscussion(alert)}
                    >
                      {t("experience.ai.ask")}
                    </button>
                    {alert.status === "open" && (
                      <button
                        type="button"
                        disabled={busyAlertId === alert.alert_id}
                        onClick={() => void onAcknowledge(alert.alert_id)}
                      >
                        {isChinese ? "确认" : "Acknowledge"}
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
                </article>
              );
            })}
            {activeAlerts.length === 0 && (
              <div className="alert-empty-state">
                <strong>{isChinese ? "当前无活动告警" : "No active alerts"}</strong>
                <span>{isChinese ? "监控服务每 10 秒检查数据库事件。" : "The monitor checks database events every 10 seconds."}</span>
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
