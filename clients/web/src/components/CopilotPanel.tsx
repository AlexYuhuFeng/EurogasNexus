/**
 * Copilot surface (Architecture V2 Wave 7).
 *
 * The one place the five canonical AI actions are invoked. It is a *surface*, not a
 * page: V2 section 4 of `08_DECISION_APPLICATION_AI.md` makes AI cross-workspace,
 * so it is hosted by the shell element that is already reachable from every
 * workspace (the command palette) instead of earning a new top-level navigation
 * entry.
 *
 * `CopilotPanel` is presentational: it renders the controller's state and calls
 * back. `CopilotHost` is the thin container a shell mounts - it resolves the Active
 * Context and the evidence references, runs one `useCopilot` controller and passes
 * the existing backend route as the transport.
 *
 * Three things are rendered on purpose and may not be dropped:
 * - the posture, what each action produces and the evidence references it will
 *   carry, *before* the user invokes it;
 * - the run record: what was asked, on which context, with which references;
 * - the qualification of the output: interpretation rather than calculation, no
 *   numeric authority, and `research_only` / `human_review_required` from the
 *   response `meta` kept visible.
 */

import { useTranslation } from "react-i18next";

import { api, type AnalysisRequestDTO, type AnalysisResultDTO, type ApiResponse } from "@/api/client";
import { describeApiError, presentError } from "@/app/experience/errorPresentation";
import type { AiActionKind } from "@/app/experience/vocabulary";
import {
  COPILOT_CONTEXT_FIELDS,
  COPILOT_REQUEST_ROUTE,
  copilotContextFieldLabelKey,
  copilotContextFieldValue,
  copilotGapLabelKey,
} from "@/app/model/copilotModel";
import { useCopilot, useCopilotSources, type CopilotController } from "@/app/hooks/useCopilot";
import "./copilot-panel.css";

type Translate = (key: string) => string;

export interface CopilotPanelProps extends CopilotController {
  t: Translate;
  /** Leave the Copilot and return to the command list. */
  onClose: () => void;
  /** Switch canonical action without leaving the surface. */
  onSelectAction: (action: AiActionKind) => void;
}

export function CopilotPanel({
  t,
  onClose,
  onSelectAction,
  action,
  context,
  evidenceRefs,
  offers,
  selected,
  state,
  canRun,
  question,
  setQuestion,
  run,
  output,
  runRecord,
  error,
}: CopilotPanelProps) {
  const activeContext = context.activeContext;
  // Resolution lives in one place: a presentation key the vocabulary does not cover yet
  // falls back to the family's wording rather than printing a raw `errors.…` key.
  const failureText = presentError(t, error ?? describeApiError(null));
  return (
    <section
      className="copilot-panel"
      data-copilot-surface="copilot"
      aria-label={t("experience.copilot.title")}
    >
      <header className="copilot-panel-header">
        <div>
          <span className="eyebrow">{t("experience.copilot.title")}</span>
          <h2>{t("experience.copilot.subtitle")}</h2>
        </div>
        <div className="copilot-panel-header-actions">
          <button type="button" onClick={onClose}>
            {t("experience.copilot.back")}
          </button>
          <button type="button" aria-label={t("experience.copilot.close")} onClick={onClose}>
            ×
          </button>
        </div>
      </header>

      <p className="copilot-boundary">{t("experience.copilot.boundary")}</p>

      <section className="copilot-context" aria-label={t("experience.copilot.context")}>
        <h3>{t("experience.copilot.context")}</h3>
        <dl className="copilot-context-facts">
          {COPILOT_CONTEXT_FIELDS.map((field) => (
            <div key={field}>
              <dt>{t(copilotContextFieldLabelKey(field))}</dt>
              <dd>
                {copilotContextFieldValue(activeContext, field) ?? t("experience.copilot.field_missing")}
              </dd>
            </div>
          ))}
          <div>
            <dt>{t("experience.copilot.context_key")}</dt>
            <dd>
              <code>{context.contextKey}</code>
            </dd>
          </div>
        </dl>
        <p className="copilot-context-state">
          {context.complete
            ? t("experience.copilot.context_complete")
            : t("experience.copilot.context_incomplete")}
        </p>
        {context.missingFields.length > 0 && (
          <ul className="copilot-context-missing">
            {context.missingFields.map((field) => (
              <li key={field}>{t(copilotContextFieldLabelKey(field))}</li>
            ))}
          </ul>
        )}
        <p className="copilot-context-note">
          {context.reproducible
            ? t("experience.copilot.context_reproducible")
            : t("experience.copilot.context_not_reproducible")}
        </p>
        {context.gaps.length > 0 && (
          <ul className="copilot-context-gaps">
            {context.gaps.map((gap) => (
              <li key={gap}>{t(copilotGapLabelKey(gap))}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="copilot-evidence" aria-label={t("experience.copilot.evidence")}>
        <h3>{t("experience.copilot.evidence")}</h3>
        {evidenceRefs.length > 0 ? (
          <ul className="copilot-evidence-list">
            {evidenceRefs.map((ref) => (
              <li key={`${ref.kind}:${ref.ref}`}>
                <span className="copilot-evidence-kind">{t(`experience.inspect.${ref.kind}`)}</span>
                <code>{ref.ref}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p className="copilot-evidence-empty" role="status">
            {t("experience.copilot.evidence_none")}
          </p>
        )}
      </section>

      <section className="copilot-actions" aria-label={t("experience.copilot.actions")}>
        <h3>{t("experience.copilot.actions")}</h3>
        <ul className="copilot-action-list">
          {offers.map((offer) => (
            <li
              key={offer.action}
              className={`copilot-action${offer.action === action ? " selected" : ""}${
                offer.available ? "" : " withheld"
              }`}
            >
              <button
                type="button"
                aria-pressed={offer.action === action}
                disabled={!offer.available}
                onClick={() => onSelectAction(offer.action)}
              >
                <span className="copilot-action-label">{t(offer.labelKey)}</span>
                <span className="copilot-action-posture">
                  {t("experience.copilot.posture")}: {t(offer.postureKey)}
                </span>
              </button>
              <p className="copilot-action-produces">
                {t("experience.copilot.produces")}: {t(offer.producesKey)}
              </p>
              <p className="copilot-action-carries">
                <span className="copilot-action-carries-label">{t("experience.copilot.carries")}</span>
                {offer.evidenceRefs.length > 0
                  ? offer.evidenceRefs.map((ref) => (
                      <code key={`${ref.kind}:${ref.ref}`}>{`${ref.kind}:${ref.ref}`}</code>
                    ))
                  : t("experience.copilot.carries_none")}
              </p>
              {offer.withheldReasonKey && (
                <p className="copilot-action-withheld-reason" role="status">
                  {t(offer.withheldReasonKey)}
                </p>
              )}
            </li>
          ))}
        </ul>
      </section>

      {selected?.available && (
        <section className="copilot-invoke" aria-label={t("experience.copilot.question")}>
          <label className="copilot-question">
            <span>{t("experience.copilot.question")}</span>
            <textarea
              value={question}
              rows={3}
              placeholder={t("experience.copilot.question_placeholder")}
              onChange={(event) => setQuestion(event.target.value)}
            />
          </label>
          <p className="copilot-question-note">{t("experience.copilot.question_default")}</p>
          <div className="copilot-invoke-actions">
            <button type="button" className="primary-button" disabled={!canRun} onClick={() => void run()}>
              {state === "running" ? t("experience.copilot.running") : t("experience.copilot.run")}
            </button>
            <span className="copilot-invoke-route">
              <code>
                {t("experience.copilot.run_route")}: {COPILOT_REQUEST_ROUTE}
              </code>
            </span>
          </div>
        </section>
      )}

      {runRecord && (
        <section className="copilot-record" aria-label={t("experience.copilot.run_record")}>
          <h3>{t("experience.copilot.run_record")}</h3>
          <dl className="copilot-record-facts">
            <div>
              <dt>{t("experience.copilot.run_asked")}</dt>
              <dd>
                <pre>{runRecord.question}</pre>
              </dd>
            </div>
            <div>
              <dt>{t("experience.copilot.run_context")}</dt>
              <dd>
                <code>{runRecord.contextKey}</code>
              </dd>
            </div>
            <div>
              <dt>{t("experience.copilot.run_evidence")}</dt>
              <dd>
                {runRecord.evidenceRefs.length > 0
                  ? runRecord.evidenceRefs
                      .map((ref) => `${ref.kind}:${ref.ref}`)
                      .join(", ")
                  : t("experience.copilot.carries_none")}
              </dd>
            </div>
            <div>
              <dt>{t("experience.copilot.run_at")}</dt>
              <dd>{runRecord.recordedAtUtc}</dd>
            </div>
          </dl>
        </section>
      )}

      {output && (
        <section className="copilot-result" aria-label={t("experience.copilot.result")}>
          <h3>{t("experience.copilot.result")}</h3>
          <p className="copilot-result-interpretation">
            {t("experience.copilot.result_interpretation")}
          </p>
          <p className="copilot-result-authority">
            {t("experience.copilot.result_numeric_authority")}
          </p>
          <dl className="copilot-result-facts">
            <div>
              <dt>{t("experience.copilot.research_only")}</dt>
              <dd>
                {output.researchOnly
                  ? t("experience.copilot.flag.yes")
                  : t("experience.copilot.flag.no")}
              </dd>
            </div>
            <div>
              <dt>{t("experience.copilot.human_review_required")}</dt>
              <dd>
                {output.humanReviewRequired
                  ? t("experience.copilot.flag.yes")
                  : t("experience.copilot.flag.no")}
              </dd>
            </div>
            <div>
              <dt>{t("experience.copilot.provider_status")}</dt>
              <dd>
                <code>{output.providerStatus || t("experience.copilot.not_reported")}</code>
              </dd>
            </div>
            <div>
              <dt>{t("experience.copilot.snapshot")}</dt>
              <dd>
                <code>{output.snapshotId ?? t("experience.copilot.not_reported")}</code>
              </dd>
            </div>
          </dl>
          <p className="copilot-result-provider">
            {output.providerInvoked
              ? t("experience.copilot.provider_invoked")
              : t("experience.copilot.provider_not_invoked")}
          </p>
          <p className="copilot-result-answer">{output.answer}</p>
          {output.missingInputs.length > 0 && (
            <div className="copilot-result-block">
              <h4>{t("experience.copilot.missing_inputs")}</h4>
              <ul>
                {output.missingInputs.map((item) => (
                  <li key={item}>
                    <code>{item}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {output.citations.length > 0 && (
            <div className="copilot-result-block">
              <h4>{t("experience.copilot.citations")}</h4>
              <ul>
                {output.citations.map((citation) => (
                  <li key={citation}>
                    <code>{citation}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {output.warnings.length > 0 && (
            <div className="copilot-result-block">
              <h4>{t("experience.copilot.warnings")}</h4>
              <ul>
                {output.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {error && (
        <div className="copilot-error" role="alert">
          <strong>{t("experience.copilot.error_title")}</strong>
          {error.message && <p>{error.message}</p>}
          <p>{failureText.impact}</p>
          <p>{failureText.cause}</p>
          <p>{failureText.action}</p>
          <p className="copilot-error-code">
            <code>{error.code}</code>
            {failureText.correlationId && <code>{failureText.correlationId}</code>}
          </p>
        </div>
      )}
    </section>
  );
}

export interface CopilotHostProps {
  /** The canonical action to open on, or null when the surface is closed. */
  action: AiActionKind | null;
  t: Translate;
  onClose: () => void;
  onSelectAction: (action: AiActionKind) => void;
}

/**
 * The mounted Copilot: it resolves the Active Context from the canonical sources,
 * runs one controller and wires the existing backend analysis route as the only
 * transport. A host that already holds the context can mount `CopilotPanel` with
 * its own `useCopilot` output instead.
 */
export function CopilotHost({ action, t, onClose, onSelectAction }: CopilotHostProps) {
  const { i18n } = useTranslation();
  const sources = useCopilotSources();
  const copilot = useCopilot({
    action,
    sources,
    language: i18n.language,
    runAnalysis: (body: AnalysisRequestDTO): Promise<ApiResponse<AnalysisResultDTO>> =>
      api.analysisQuery(body),
  });
  return <CopilotPanel {...copilot} t={t} onClose={onClose} onSelectAction={onSelectAction} />;
}
