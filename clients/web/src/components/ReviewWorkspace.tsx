import { useEffect, useState } from "react";
import { warningLabel } from "@/app/warningLabel";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import { reviewEvidenceFor } from "@/app/model/reviewContextModel";
import { copilotOffers } from "@/app/model/copilotModel";
import { useCopilotSources } from "@/app/hooks/useCopilot";
import { CopilotHost } from "@/components/CopilotPanel";
import type { AiActionKind } from "@/app/experience/vocabulary";
import { EvidenceBlock } from "@/components/ui";
import type {
  AnalysisResultDTO,
  PortfolioOptimizationResultDTO,
  PortfolioSaleOptionDTO,
  ReviewContextProjectionDTO,
  ReviewDecisionDTO,
  ReviewDecisionInputDTO,
} from "@/api/client";

type Translate = (key: string) => string;

interface ReviewWorkspaceProps {
  allocations: PortfolioOptimizationResultDTO["allocations"];
  saleOptionById: Map<string, PortfolioSaleOptionDTO>;
  reviewWarnings: string[];
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  analysisResult: AnalysisResultDTO | null;
  language: string;
  reviewDecisions: ReviewDecisionDTO[];
  /** The review projection, when its on-demand read has landed. */
  reviewProjection: ReviewContextProjectionDTO | null;
  reviewMessage: string | null;
  latestStrategyRunId: string | null;
  carriedStrategyRunId: string | null;
  t: Translate;
  onGenerateReport: () => void;
  onRecordDecision: (body: ReviewDecisionInputDTO) => Promise<void>;
  onInspectEvidence: (ref: string, label: string) => void;
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
  return formatUtcTimestamp(value, value);
}

export function ReviewWorkspace({
  allocations,
  saleOptionById,
  reviewWarnings,
  resourcePoolResult,
  analysisResult,
  language,
  reviewDecisions,
  reviewProjection,
  reviewMessage,
  latestStrategyRunId,
  carriedStrategyRunId,
  t,
  onGenerateReport,
  onRecordDecision,
  onInspectEvidence,
}: ReviewWorkspaceProps) {
  const [actor, setActor] = useState("operator");
  const [entityType, setEntityType] = useState<ReviewDecisionInputDTO["entity_type"]>("strategy_run");
  const [entityId, setEntityId] = useState(carriedStrategyRunId ?? latestStrategyRunId ?? "");
  const [note, setNote] = useState("");
  // The Copilot reads the canonical sources the shell and the palette use, so an action
  // offered here carries the context and evidence a run would actually use.
  const [aiAction, setAiAction] = useState<AiActionKind | null>(null);
  const copilotSources = useCopilotSources();

  useEffect(() => {
    if (carriedStrategyRunId) {
      setEntityId(carriedStrategyRunId);
      setEntityType("strategy_run");
      return;
    }
    if (!entityId && latestStrategyRunId) setEntityId(latestStrategyRunId);
  }, [carriedStrategyRunId, entityId, latestStrategyRunId]);

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
      {carriedStrategyRunId && (
        <div className="workspace-panel span-3 review-context-banner" role="status" aria-live="polite">
          <span><small>{t("review.carried_strategy_run")}</small><strong>{carriedStrategyRunId}</strong></span>
        </div>
      )}
      <div className="workspace-panel span-2">
        <div className="section-heading">
          <span className="eyebrow">{t("nav.review")}</span>
          <strong>{t("review.title")}</strong>
        </div>
        <p className="panel-copy">{t("review.subtitle")}</p>
        <div className="data-table" tabIndex={0}>
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
        <h2>{t("review.warning_register")}</h2>
        <div className="review-warning-list">
          {reviewWarnings.length > 0
            ? reviewWarnings.slice(0, 6).map((warning) => <span key={`review-warning-${warning}`}>{warningLabel(warning, t)}</span>)
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
          <div className="review-evidence-grid" aria-label={t("review.evidence_pack")}>
            <div className="review-evidence-row">
              <span className="review-evidence-key">{t("review.status")}</span>
              <strong className="review-evidence-value">{resourcePoolResult.status}</strong>
            </div>
            <div className="review-evidence-row">
              <span className="review-evidence-key">{t("review.algorithm")}</span>
              <strong className="review-evidence-value">{resourcePoolResult.algorithm}</strong>
            </div>
            <div className="review-evidence-row">
              <span className="review-evidence-key">{t("review.optimality")}</span>
              <strong className="review-evidence-value">{resourcePoolResult.optimality}</strong>
            </div>
            <div className="review-evidence-row">
              <span className="review-evidence-key">{t("review.allocated_volume")}</span>
              <strong className="review-evidence-value">{resourcePoolResult.total_allocated_mwh_per_day.toLocaleString()} MWh/d</strong>
            </div>
            <div className="review-evidence-row review-evidence-row-full">
              <span className="review-evidence-key">{t("review.missing_inputs")}</span>
              <ul className="review-evidence-list">
                {resourcePoolResult.missing_inputs.length > 0
                  ? resourcePoolResult.missing_inputs.map((item) => <li className="review-evidence-item" key={`missing-${item}`}>{item}</li>)
                  : <li className="review-evidence-item">{t("review.none")}</li>}
              </ul>
            </div>
            <div className="review-evidence-row review-evidence-row-full">
              <span className="review-evidence-key">{t("review.assumptions")}</span>
              <ul className="review-evidence-list">
                {resourcePoolResult.assumptions.length > 0
                  ? resourcePoolResult.assumptions.map((item) => <li className="review-evidence-item" key={`assumption-${item}`}>{item}</li>)
                  : <li className="review-evidence-item">{t("review.none")}</li>}
              </ul>
            </div>
            <div className="review-evidence-row review-evidence-row-full">
              <EvidenceBlock
                className="review-governance-evidence"
                ariaLabel={t("review.evidence_pack")}
                items={[
                  {
                    label: t("evidence.lineage"),
                    value: resourcePoolResult.source_refs.length > 0
                      ? resourcePoolResult.source_refs.slice(0, 8).join(" · ")
                      : t("review.none"),
                    wide: true,
                  },
                  {
                    label: t("evidence.review_boundary"),
                    value: resourcePoolResult.human_review_required
                      ? t("settings.human_review")
                      : t("review.none"),
                  },
                  {
                    label: t("evidence.research_boundary"),
                    value: resourcePoolResult.research_only
                      ? t("settings.decision_support_only")
                      : t("review.none"),
                  },
                ]}
              />
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
        <div className="data-table" tabIndex={0}>
          <div className="data-table-row header four"><span>{t("review.entity_id")}</span><span>{t("review.decision")}</span><span>{t("review.decision_time")}</span><span>{t("review.evidence")}</span></div>
          {reviewDecisions.slice(0, 12).map((row) => {
            const entityRef = `${row.entity_type}:${row.entity_id}`;
            const resolved = reviewEvidenceFor(reviewProjection, row.entity_type, row.entity_id);
            return (
              <div key={`review-history-${row.decision_id}`} className="data-table-row four">
                <strong>{entityRef}</strong>
                <span className={`review-decision-badge review-decision-${row.decision}`}>
                  {row.decision} / {row.actor}
                </span>
                <span>{formatDecisionTime(row.created_at_utc)}</span>
                <span>
                  {/* Wave 9: the evidence behind a decision is an object, so it is handed to
                      the Inspector. The action exists only when the projection resolved an
                      entry for this entity; an unresolved entity is not dressed up. */}
                  {resolved ? (
                    <button
                      type="button"
                      className="text-action"
                      onClick={() => onInspectEvidence(entityRef, `${row.entity_type}: ${row.entity_id}`)}
                    >
                      {t("review.inspect_evidence")}
                    </button>
                  ) : (
                    t("review.evidence_unavailable")
                  )}
                </span>
              </div>
            );
          })}
          {reviewDecisions.length === 0 && (
            <div className="data-table-row four"><strong>{t("review.no_decisions")}</strong><span>n/a</span><span>n/a</span><span>n/a</span></div>
          )}
        </div>
      </div>
      <div className="workspace-panel span-3 analysis-panel review-report-panel">
        <h2>{t("analysis.report")}</h2>
        <p className="panel-copy">{t("review.report_help")}</p>
        <div className="action-row">
          <button type="button" onClick={onGenerateReport}>{t("analysis.report")}</button>
        </div>
        {analysisResult && (
          <div className="analysis-result">
            <strong>{analysisResult.provider_id}: {analysisResult.provider_status}</strong>
            <p>{language.startsWith("zh") ? analysisResult.answer_zh_cn : analysisResult.answer_en}</p>
          </div>
        )}
      </div>
      <div className="workspace-panel span-3 review-copilot-panel" aria-label={t("experience.copilot.title")}>
        <h2>{t("experience.copilot.title")}</h2>
        <p className="panel-copy">{t("experience.copilot.subtitle")}</p>
        {/* Wave 7 convergence: this panel used to carry its own question box and an
            "invoke the provider" switch, which made a sixth AI entry point beside the
            canonical five. The five declared actions are offered here instead, gated by the
            offer the contract produced; AI drafting is the `draft` action, and the report
            above is the deterministic backend run it always was. */}
        <div className="action-row">
          {copilotOffers(copilotSources.context, copilotSources.evidenceRefs).map((offer) => (
            <button
              key={offer.action}
              type="button"
              disabled={!offer.available}
              title={offer.withheldReasonKey ? t(offer.withheldReasonKey) : undefined}
              onClick={() => setAiAction(offer.action)}
            >
              {t(offer.labelKey)}
            </button>
          ))}
        </div>
      </div>
      {aiAction && (
        <CopilotHost
          action={aiAction}
          t={t}
          onClose={() => setAiAction(null)}
          onSelectAction={setAiAction}
        />
      )}
    </div>
  );
}
