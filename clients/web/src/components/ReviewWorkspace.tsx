import { useEffect, useState } from "react";
import type {
  AnalysisResultDTO,
  PortfolioOptimizationResultDTO,
  PortfolioSaleOptionDTO,
  ReviewDecisionDTO,
  ReviewDecisionInputDTO,
} from "@/api/client";

type Translate = (key: string) => string;

interface ReviewWorkspaceProps {
  allocations: PortfolioOptimizationResultDTO["allocations"];
  saleOptionById: Map<string, PortfolioSaleOptionDTO>;
  reviewWarnings: string[];
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  analysisQuestion: string;
  invokeDeepSeek: boolean;
  analysisResult: AnalysisResultDTO | null;
  language: string;
  reviewDecisions: ReviewDecisionDTO[];
  reviewMessage: string | null;
  latestStrategyRunId: string | null;
  t: Translate;
  onAnalysisQuestionChange: (value: string) => void;
  onInvokeDeepSeekChange: (value: boolean) => void;
  onAnalyze: () => void;
  onGenerateReport: () => void;
  onRecordDecision: (body: ReviewDecisionInputDTO) => Promise<void>;
}

const REVIEW_DECISIONS: ReviewDecisionInputDTO["decision"][] = [
  "accepted",
  "rejected",
  "needs_attention",
];

const REVIEW_ENTITY_TYPES: ReviewDecisionInputDTO["entity_type"][] = [
  "strategy_run",
  "intraday_opportunity",
  "generated_report",
];

function formatDecisionTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ReviewWorkspace({
  allocations,
  saleOptionById,
  reviewWarnings,
  resourcePoolResult,
  analysisQuestion,
  invokeDeepSeek,
  analysisResult,
  language,
  reviewDecisions,
  reviewMessage,
  latestStrategyRunId,
  t,
  onAnalysisQuestionChange,
  onInvokeDeepSeekChange,
  onAnalyze,
  onGenerateReport,
  onRecordDecision,
}: ReviewWorkspaceProps) {
  const [actor, setActor] = useState("operator");
  const [entityType, setEntityType] = useState<ReviewDecisionInputDTO["entity_type"]>("strategy_run");
  const [entityId, setEntityId] = useState(latestStrategyRunId ?? "");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!entityId && latestStrategyRunId) setEntityId(latestStrategyRunId);
  }, [entityId, latestStrategyRunId]);

  const submitDecision = (decision: ReviewDecisionInputDTO["decision"]) => {
    const trimmedId = entityId.trim();
    if (!trimmedId) return;
    void onRecordDecision({
      entity_type: entityType,
      entity_id: trimmedId,
      actor: actor.trim() || "operator",
      decision,
      note: note.trim() ? note.trim() : null,
    });
  };

  return (
    <div className="workspace-grid review-page">
      <div className="workspace-panel span-2">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.review")}</span>
          <strong>{t("review.title")}</strong>
        </div>
        <p className="panel-copy">{t("review.subtitle")}</p>
        <div className="data-table">
          <div className="data-table-row header four"><span>{t("result.optimal")}</span><span>{t("home.allocated")}</span><span>{t("result.route_cost")}</span><span>PnL</span></div>
          {allocations.map((allocation) => {
            const option = saleOptionById.get(allocation.option_id);
            return (
              <div key={`review-pool-${allocation.resource_id}-${allocation.option_id}`} className="data-table-row four">
                <strong>{option?.label ?? allocation.option_id}</strong>
                <span>{allocation.allocated_quantity_mwh_per_day.toLocaleString()} MWh/d</span>
                <span>{allocation.total_cost_gbp_mwh.toFixed(2)} GBP/MWh</span>
                <span>GBP {Math.round(allocation.net_pnl_gbp_per_day).toLocaleString()}</span>
              </div>
            );
          })}
          {allocations.length === 0 && (
            <div className="data-table-row four"><strong>{t("home.pending")}</strong><span>n/a</span><span>n/a</span><span>{t("home.run_pool_optimizer")}</span></div>
          )}
        </div>
      </div>
      <div className="workspace-panel">
        <h3>{t("review.warning_register")}</h3>
        <div className="review-warning-list">
          {reviewWarnings.length > 0
            ? reviewWarnings.slice(0, 6).map((warning) => <span key={`review-warning-${warning}`}>{warning}</span>)
            : <span>{t("review.no_warnings")}</span>}
        </div>
      </div>
      <div className="workspace-panel span-2 review-evidence-panel">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.review")}</span>
          <strong>{t("review.evidence_pack")}</strong>
        </div>
        <p className="panel-copy">{t("review.evidence_help")}</p>
        {resourcePoolResult ? (
          <div className="review-evidence-grid">
            <div><span>{t("review.status")}</span><strong>{resourcePoolResult.status}</strong></div>
            <div><span>{t("review.algorithm")}</span><strong>{resourcePoolResult.algorithm}</strong></div>
            <div><span>{t("review.optimality")}</span><strong>{resourcePoolResult.optimality}</strong></div>
            <div><span>{t("review.allocated_volume")}</span><strong>{resourcePoolResult.total_allocated_mwh_per_day.toLocaleString()} MWh/d</strong></div>
            <div className="review-evidence-full">
              <span>{t("review.missing_inputs")}</span>
              <div className="review-evidence-list">
                {resourcePoolResult.missing_inputs.length > 0
                  ? resourcePoolResult.missing_inputs.map((item) => <span key={`missing-${item}`}>{item}</span>)
                  : <span>{t("review.none")}</span>}
              </div>
            </div>
            <div className="review-evidence-full">
              <span>{t("review.assumptions")}</span>
              <div className="review-evidence-list">
                {resourcePoolResult.assumptions.length > 0
                  ? resourcePoolResult.assumptions.map((item) => <span key={`assumption-${item}`}>{item}</span>)
                  : <span>{t("review.none")}</span>}
              </div>
            </div>
            <div className="review-evidence-full">
              <span>{t("review.source_refs")}</span>
              <div className="review-evidence-list">
                {resourcePoolResult.source_refs.length > 0
                  ? resourcePoolResult.source_refs.slice(0, 8).map((ref) => <span key={`ref-${ref}`}>{ref}</span>)
                  : <span>{t("review.none")}</span>}
              </div>
            </div>
          </div>
        ) : (
          <p className="panel-copy">{t("review.no_pool_result")}</p>
        )}
      </div>
      <div className="workspace-panel span-2">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.review")}</span>
          <strong>{t("review.decision_recorder")}</strong>
        </div>
        <p className="panel-copy">{t("review.actor_not_authenticated")}</p>
        <div className="review-decision-form">
          <label>
            <span>{t("review.entity_type")}</span>
            <select
              value={entityType}
              onChange={(event) => setEntityType(event.target.value as ReviewDecisionInputDTO["entity_type"])}
            >
              {REVIEW_ENTITY_TYPES.map((type) => (
                <option key={`review-entity-type-${type}`} value={type}>{type}</option>
              ))}
            </select>
          </label>
          <label>
            <span>{t("review.entity_id")}</span>
            <input
              value={entityId}
              placeholder={t("review.entity_id_placeholder")}
              onChange={(event) => setEntityId(event.target.value)}
            />
          </label>
          <label>
            <span>{t("review.actor")}</span>
            <input
              value={actor}
              maxLength={64}
              onChange={(event) => setActor(event.target.value)}
            />
          </label>
        </div>
        <div className="review-decision-actions">
          {REVIEW_DECISIONS.map((decision) => (
            <button
              key={`review-decision-${decision}`}
              type="button"
              className={`review-decision-button review-decision-${decision}`}
              disabled={!entityId.trim()}
              onClick={() => submitDecision(decision)}
            >
              {t(`review.decision_${decision}`)}
            </button>
          ))}
        </div>
        <textarea
          value={note}
          rows={2}
          placeholder={t("review.note_placeholder")}
          onChange={(event) => setNote(event.target.value)}
        />
        {reviewMessage && <p className="panel-copy review-decision-message">{reviewMessage}</p>}
      </div>
      <div className="workspace-panel">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.review")}</span>
          <strong>{t("review.decision_history")}</strong>
        </div>
        <div className="data-table">
          <div className="data-table-row header three"><span>{t("review.entity_id")}</span><span>{t("review.decision")}</span><span>{t("review.decision_time")}</span></div>
          {reviewDecisions.slice(0, 12).map((row) => (
            <div key={`review-history-${row.decision_id}`} className="data-table-row three">
              <strong>{row.entity_type}:{row.entity_id}</strong>
              <span className={`review-decision-badge review-decision-${row.decision}`}>
                {row.decision} / {row.actor}
              </span>
              <span>{formatDecisionTime(row.created_at_utc)}</span>
            </div>
          ))}
          {reviewDecisions.length === 0 && (
            <div className="data-table-row three"><strong>{t("review.no_decisions")}</strong><span>n/a</span><span>n/a</span></div>
          )}
        </div>
      </div>
      <div className="workspace-panel span-3 analysis-panel review-report-panel">
        <h3>{t("panel.analysis")}</h3>
        <textarea value={analysisQuestion} onChange={(event) => onAnalysisQuestionChange(event.target.value)} rows={4} />
        <label className="checkbox-row">
          <input type="checkbox" checked={invokeDeepSeek} onChange={(event) => onInvokeDeepSeekChange(event.target.checked)} />
          {t("analysis.invoke_deepseek")}
        </label>
        <div className="action-row">
          <button type="button" onClick={onAnalyze}>{t("analysis.ask")}</button>
          <button type="button" onClick={onGenerateReport}>{t("analysis.report")}</button>
        </div>
        {analysisResult && (
          <div className="analysis-result">
            <strong>{analysisResult.provider_id}: {analysisResult.provider_status}</strong>
            <p>{language.startsWith("zh") ? analysisResult.answer_zh_cn : analysisResult.answer_en}</p>
          </div>
        )}
      </div>
    </div>
  );
}
