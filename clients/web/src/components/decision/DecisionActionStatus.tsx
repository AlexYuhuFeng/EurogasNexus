import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import type { DecisionActionState } from "@/app/model/decisionActionModel";

type Translate = (key: string) => string;

interface DecisionActionStatusProps {
  readonly t: Translate;
  /** The action this status belongs to, for the pending copy. */
  readonly labelKey: string;
  readonly state: DecisionActionState;
  /** The gate's explanation when the action may not start; null when it may. */
  readonly blockerKey: string | null;
  /** Whether a result exists at all for this action. */
  readonly hasResult: boolean;
  /** Whether that result was computed for the trading context on screen. */
  readonly resultCurrent: boolean;
}

/**
 * One governed compute's lifecycle, rendered next to the action and the result it produced.
 *
 * The workspace header's primary control is the action; this is what says what happened to it.
 * A refusal or failure is explained through the product error taxonomy
 * (`app/experience/errorPresentation.ts`) - never a raw exception string - with the backend's
 * own correlation id when it supplied one, so a user always has something to quote. When the
 * action cannot start, the reason is rendered as text rather than left in a `title`: a disabled
 * button cannot be focused, so a tooltip would not reach a keyboard user. Result currency is a
 * statement about the *run*, not about the click: it is stated only after a successful
 * matching-context response, and a stale payload is named as stale.
 */
export function DecisionActionStatus({
  t,
  labelKey,
  state,
  blockerKey,
  hasResult,
  resultCurrent,
}: DecisionActionStatusProps) {
  const failure = state.error ? presentError(t, describeFailure(state.error)) : null;
  const pending = state.phase === "pending";
  // Currency is a statement about the run, so it is made only once one has settled and there is
  // a payload to speak about - and it stays visible under a later failure, because the retained
  // result is still the older run's.
  const currencyText = !pending && hasResult
    ? (resultCurrent ? t("decision.action.result_current") : t("decision.action.result_stale"))
    : null;
  const blockerText = blockerKey && !pending ? t(blockerKey) : null;

  if (!failure && !pending && !currencyText && !blockerText) return null;

  if (failure) {
    return (
      <div className="alert decision-action-status" role="alert">
        <strong>{failure.title}</strong>
        <p>{failure.impact}</p>
        <p>{failure.cause}</p>
        <p>{failure.action}</p>
        {currencyText && <p className="muted">{currencyText}</p>}
        {failure.correlationId && (
          <p className="muted">
            {t("errors.correlation_id")}: <code>{failure.correlationId}</code>
          </p>
        )}
        {blockerText && <p className="muted">{blockerText}</p>}
      </div>
    );
  }

  return (
    <p className="decision-action-status muted" role="status" aria-live="polite">
      {pending && <span>{`${t("decision.action.pending")} · ${t(labelKey)}`}</span>}
      {currencyText && <span>{currencyText}</span>}
      {currencyText && blockerText && " "}
      {blockerText && <span>{blockerText}</span>}
    </p>
  );
}
