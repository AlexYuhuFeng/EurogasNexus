import { useState } from "react";
import {
  AGENT_REVIEW_DECISIONS,
  agentConfirmationBusy,
  agentConfirmationNotice,
  type AgentConfirmationState,
  type AgentReviewDecisionValue,
  type AgentReviewGate,
} from "@/app/model/agentReplayModel";
import { PanelHeader, StatusBadge } from "@/components/ui";

type Translate = (key: string) => string;

interface AgentReviewGateProps {
  gate: AgentReviewGate;
  state: AgentConfirmationState;
  reviewerIdentity: string;
  t: Translate;
  onConfirm: (decision: AgentReviewDecisionValue, note: string) => void;
}

const UNAVAILABLE_KEYS: Record<string, string> = {
  no_review_pack: "agents.gate.unavailable_no_pack",
  no_artifact_id: "agents.gate.unavailable_no_id",
  no_identity: "agents.gate.unavailable_no_identity",
};

/**
 * Human gate for one persisted review pack.
 *
 * The control records ``accepted | rejected | needs_attention`` through the
 * existing review-decision endpoint and shows the decisions the backend holds.
 * It never executes, schedules or nominates anything: it is the persisted human
 * confirmation of evidence that already exists.
 */
export function AgentReviewGate({
  gate,
  state,
  reviewerIdentity,
  t,
  onConfirm,
}: AgentReviewGateProps) {
  const [note, setNote] = useState("");
  const busy = agentConfirmationBusy(state);
  const notice = agentConfirmationNotice(state);
  const absent = t("agents.value_absent");
  const disabled = !gate.available || busy;

  return (
    <div className="agents-gate">
      <PanelHeader title={t("agents.gate.title")} meta={gate.entityType} />
      <p className="panel-copy">{t("agents.gate.help")}</p>

      {!gate.available && gate.unavailableReason && (
        <p className="alert">{t(UNAVAILABLE_KEYS[gate.unavailableReason])}</p>
      )}

      <div className="agents-fact-grid">
        <div className="agents-fact">
          <span className="agents-fact-key">{t("agents.gate.entity_type")}</span>
          <span className="agents-fact-value">
            <code>{gate.entityType}</code>
          </span>
        </div>
        <div className="agents-fact">
          <span className="agents-fact-key">{t("agents.gate.entity_id")}</span>
          <span className="agents-fact-value">{gate.entityId || absent}</span>
        </div>
        <div className="agents-fact">
          <span className="agents-fact-key">{t("agents.gate.reviewer")}</span>
          <span className="agents-fact-value">{reviewerIdentity || absent}</span>
        </div>
        <div className="agents-fact">
          <span className="agents-fact-key">{t("agents.gate.produced_by")}</span>
          <span className="agents-fact-value">{gate.producedBy || absent}</span>
        </div>
        {gate.policyBoundary !== "" && (
          <div className="agents-fact">
            <span className="agents-fact-key">{t("agents.rights.boundary")}</span>
            <span className="agents-fact-value">{gate.policyBoundary}</span>
          </div>
        )}
      </div>

      <label className="field-label" htmlFor="agents-gate-note">
        {t("agents.gate.note")}
      </label>
      <textarea
        id="agents-gate-note"
        className="textarea"
        rows={2}
        maxLength={2000}
        value={note}
        disabled={disabled}
        placeholder={t("agents.gate.note_placeholder")}
        onChange={(event) => setNote(event.target.value)}
      />

      <div className="agents-gate-actions">
        {AGENT_REVIEW_DECISIONS.map((decision) => (
          <button
            key={decision}
            type="button"
            className={`review-decision-button review-decision-${decision}`}
            disabled={disabled}
            onClick={() => onConfirm(decision, note.trim())}
          >
            {t(`agents.gate.${decision}`)}
          </button>
        ))}
      </div>
      <p className="muted">{t("agents.gate.submit_hint")}</p>

      <div className="agents-gate-notice" role="status" aria-live="polite">
        {busy && <span className="muted">{t("agents.gate.in_flight")}</span>}
        {!busy && notice && (
          <span className={notice.tone === "refused" ? "alert" : "muted"}>
            {t(notice.key)}
            {notice.decisionId !== "" && (
              <>
                {" "}
                <code>{notice.decisionId}</code>
              </>
            )}
          </span>
        )}
      </div>

      <p className="muted">{t("agents.gate.boundary")}</p>

      <div className="data-table agents-gate-decisions">
        <div className="data-table-row header four">
          <span>{t("agents.gate.decision")}</span>
          <span>{t("agents.gate.decision_actor")}</span>
          <span>{t("agents.gate.decision_time")}</span>
          <span>{t("agents.gate.decision_note")}</span>
        </div>
        {gate.decisions.map((decision) => (
          <div key={decision.decisionId} className="data-table-row four">
            <span>
              <StatusBadge variant="source" status={decision.decision.toLowerCase() || "unknown"}>
                {decision.decision || absent}
              </StatusBadge>
            </span>
            <span>{decision.actor || absent}</span>
            <span>{decision.createdAtUtc || absent}</span>
            <span>{decision.note || t("agents.gate.no_note")}</span>
          </div>
        ))}
        {gate.decisions.length === 0 && (
          <div className="data-table-row four">
            <span className="muted">{t("agents.gate.no_decisions")}</span>
            <span className="muted">{absent}</span>
            <span className="muted">{absent}</span>
            <span className="muted">{absent}</span>
          </div>
        )}
      </div>
    </div>
  );
}
