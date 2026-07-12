import type {
  AnalysisResultDTO,
  PortfolioOptimizationResultDTO,
  PortfolioSaleOptionDTO,
} from "@/api/client";

type Translate = (key: string) => string;

interface ReviewWorkspaceProps {
  allocations: PortfolioOptimizationResultDTO["allocations"];
  saleOptionById: Map<string, PortfolioSaleOptionDTO>;
  reviewWarnings: string[];
  analysisQuestion: string;
  invokeDeepSeek: boolean;
  analysisResult: AnalysisResultDTO | null;
  language: string;
  t: Translate;
  onAnalysisQuestionChange: (value: string) => void;
  onInvokeDeepSeekChange: (value: boolean) => void;
  onAnalyze: () => void;
  onGenerateReport: () => void;
}

export function ReviewWorkspace({
  allocations,
  saleOptionById,
  reviewWarnings,
  analysisQuestion,
  invokeDeepSeek,
  analysisResult,
  language,
  t,
  onAnalysisQuestionChange,
  onInvokeDeepSeekChange,
  onAnalyze,
  onGenerateReport,
}: ReviewWorkspaceProps) {
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
                <span>{allocation.total_cost_gbp_mwh.toFixed(2)} EUR/MWh</span>
                <span>EUR {Math.round(allocation.net_pnl_gbp_per_day).toLocaleString()}</span>
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
