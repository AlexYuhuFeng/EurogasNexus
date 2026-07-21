import { useMemo, useState } from "react";
import type {
  MonitoringAlertDTO,
  MonitoringAnalysisDTO,
  MonitoringSummaryDTO,
} from "@/api/client";

interface AlertCenterProps {
  alerts: MonitoringAlertDTO[];
  summary: MonitoringSummaryDTO;
  analysisByAlert: Record<string, MonitoringAnalysisDTO>;
  busyAlertId: string | null;
  language: string;
  onAcknowledge: (alertId: string) => Promise<void>;
  onAnalyze: (alertId: string, question: string, language: "en" | "zh-CN") => Promise<void>;
}

export function AlertCenter({
  alerts,
  summary,
  analysisByAlert,
  busyAlertId,
  language,
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
              return (
                <article key={alert.alert_id} className={`monitoring-alert severity-${alert.severity}`}>
                  <div className="monitoring-alert-heading">
                    <span>{alert.category.replace(/_/g, " ")}</span>
                    <time>{new Date(alert.updated_at_utc).toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit" })}</time>
                  </div>
                  <h3>{title}</h3>
                  <p>{message}</p>
                  <div className="monitoring-alert-flags">
                    <span>{alert.severity}</span>
                    <span>{alert.status}</span>
                    {alert.simulated && <span>{isChinese ? "模拟价格输入" : "simulated price input"}</span>}
                    <span>{alert.occurrence_count}×</span>
                  </div>
                  {llmSummary && (
                    <div className="alert-ai-summary">
                      <strong>DeepSeek</strong>
                      <p>{llmSummary}</p>
                    </div>
                  )}
                  <div className="monitoring-alert-actions">
                    <button type="button" onClick={() => startDiscussion(alert)}>
                      {discussing ? (isChinese ? "收起" : "Hide") : (isChinese ? "询问 DeepSeek" : "Ask DeepSeek")}
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
                  {discussing && (
                    <div className="alert-discussion">
                      <textarea
                        value={question}
                        maxLength={2000}
                        onChange={(event) => setQuestion(event.target.value)}
                        aria-label={isChinese ? "向 DeepSeek 提问" : "Question for DeepSeek"}
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
                          ? (isChinese ? "分析中" : "Analyzing")
                          : (isChinese ? "发送" : "Send")}
                      </button>
                      {analysis && (
                        <div className={`alert-analysis-result status-${analysis.provider_status}`}>
                          <strong>DeepSeek · {analysis.provider_status}</strong>
                          <p>{analysis.answer ?? (isChinese ? "未返回分析。请检查密钥和网络。" : "No analysis returned. Check the key and network.")}</p>
                        </div>
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
