/**
 * The answer bar's rows inside the command palette: the answer row (tier 1 or 2), the Ask
 * row, and the Ask panel (tier 3). Presentational: `useAnswerBar` owns the state.
 *
 * Trader-first: the value first, in tabular figures and the desk's unit, a simulated figure
 * marked beside the number as the hub board marks it, and the provenance (as-of, source, FX
 * fix, calorific value) on one quiet line under it.
 */

import i18next from "i18next";
import { useTranslation } from "react-i18next";

import { formatGasDay } from "@/app/time/timeFormat";

import type { AskAnswerDTO } from "@/api/client";
import type { AnswerFact, AnswerTarget, AnswerText, AnswerView } from "@/app/answer/answerModel";
import type { AskState } from "@/app/hooks/useAnswerBar";
import { KeyFigure } from "@/components/ui/KeyFigure";
import "./AnswerBar.css";

export const ANSWER_ROW_ID = "palette-answer";
export const ASK_ROW_ID = "palette-ask";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export function answerText(text: string | AnswerText | null | undefined, t: Translate): string {
  if (!text) return "";
  if (typeof text === "string") return text;
  if (!text.values) return t(text.key);
  // A day carried as an ISO date is written as the app writes days in the reader's language.
  const values = Object.fromEntries(Object.entries(text.values).map(([name, value]) =>
    [name, typeof value === "string" && ISO_DAY.test(value) ? formatGasDay(value, i18next.language ?? "en") : value]));
  return t(text.key, values);
}

/** What a screen reader hears when the answer appears: label, value, unit, simulated. */
export function answerAnnouncement(answer: AnswerView, t: Translate): string {
  const parts = [answerText(answer.label, t)];
  if (answer.value) parts.push(`${answer.value}${answer.unit ? ` ${answerText(answer.unit, t)}` : ""}`);
  if (answer.sentence) parts.push(answerText(answer.sentence, t));
  for (const fact of answer.facts ?? []) parts.push(`${answerText(fact.label, t)} ${answerText(fact.value, t)}`);
  if (answer.simulated) parts.push(t("today.simulated_long"));
  return parts.filter(Boolean).join(", ");
}

interface AnswerRowProps {
  answer: AnswerView;
  active: boolean;
  onHover: () => void;
  onChoose: () => void;
}

/** A several-part answer's figures (the portfolio at a glance), one cell each. */
function AnswerFacts({ facts, t }: { facts: readonly AnswerFact[]; t: Translate }) {
  return (
    <dl className="answer-facts">
      {facts.map((fact, index) => (
        <div key={index} className="answer-fact" data-tone={fact.tone}>
          <dt>{answerText(fact.label, t)}</dt>
          <dd>
            <strong>{answerText(fact.value, t)}</strong>
            {fact.detail && <small>{answerText(fact.detail, t)}</small>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function AnswerRow({ answer, active, onHover, onChoose }: AnswerRowProps) {
  const { t } = useTranslation();
  const label = answerText(answer.label, t);
  const lines = answer.lines.map((line) => answerText(line, t)).filter(Boolean);
  const detail = lines.length ? <>{lines.map((line) => <span key={line} className="answer-line">{line}</span>)}</> : null;
  const facts = answer.facts?.length ? <AnswerFacts facts={answer.facts} t={t} /> : null;
  // A live figure pulses once when it changes (keyed on the value); still under reduced motion.
  const liveMark = answer.live ? <span key={answer.value ?? ""} className="answer-live-mark" aria-hidden="true" /> : undefined;
  const hint = answer.target ? t("answer.hint.open") : answer.copy ? t("answer.hint.copy") : null;
  return (
    <li role="presentation">
      <div
        id={ANSWER_ROW_ID}
        role="option"
        aria-selected={active}
        className={`answer-row${active ? " active" : ""}`}
        data-answer-kind={answer.kind}
        data-answer-simulated={answer.simulated ? "true" : undefined}
        data-answer-live={answer.live ? "true" : undefined}
        onMouseEnter={onHover}
        onClick={onChoose}
      >
        <span className="command-palette-group">{t(`answer.tag.${answer.kind}`)}</span>
        <div className="answer-body">
          {answer.value !== null ? (
            <KeyFigure
              className="answer-figure"
              size="lg"
              label={label}
              value={<span data-answer-value>{answer.value}</span>}
              unit={answer.unit ? answerText(answer.unit, t) : undefined}
              delta={answer.delta ?? undefined}
              marker={answer.simulated ? (
                <>
                  <span className="ds-cell-mark" data-state="simulated" title={t("today.simulated_long")}>
                    {t("today.simulated_short")}
                  </span>
                  {liveMark}
                </>
              ) : liveMark}
              detail={detail ?? undefined}
            />
          ) : (
            <div className="answer-sentence-block">
              <span className="answer-label">{label}</span>
              {answer.sentence && <span className="answer-sentence">{answerText(answer.sentence, t)}</span>}
              {!facts && detail && <small className="answer-detail">{detail}</small>}
            </div>
          )}
          {facts}
          {facts && answer.value === null && detail && <small className="answer-detail">{detail}</small>}
        </div>
        {hint && <span className="answer-hint">{hint}</span>}
      </div>
    </li>
  );
}

interface AskRowProps {
  question: string;
  aiAllowed: boolean;
  active: boolean;
  onHover: () => void;
  onChoose: () => void;
}

export function AskRow({ question, aiAllowed, active, onHover, onChoose }: AskRowProps) {
  const { t } = useTranslation();
  return (
    <li role="presentation">
      <div
        id={ASK_ROW_ID}
        role="option"
        aria-selected={active}
        className={`answer-row answer-ask-row${active ? " active" : ""}`}
        data-answer-kind="ask"
        onMouseEnter={onHover}
        onClick={onChoose}
      >
        <span className="command-palette-group">{t("answer.tag.ask")}</span>
        <div className="answer-sentence-block">
          <span className="answer-ask-question">{question}</span>
          <small className="answer-detail">{aiAllowed ? t("answer.ask.offer") : t("answer.ask.offer_off")}</small>
        </div>
        <span className="answer-hint">{t("answer.hint.ask")}</span>
      </div>
    </li>
  );
}

const TOPIC_TARGET: Record<string, AnswerTarget> = {
  prices: { kind: "task", mode: "desk", task: "prices" },
  outages: { kind: "task", mode: "desk", task: "events" },
  supply: { kind: "task", mode: "desk", task: "today" },
  alerts: { kind: "task", mode: "desk", task: "today" },
  book: { kind: "task", mode: "book", task: "position" },
};

function shortAsOf(value: string | null): string {
  if (!value) return "";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/** The newest as-of among the figures an answer used. */
function latestAsOf(result: AskAnswerDTO): string | null {
  return result.lines.reduce<string | null>((latest, line) => (line.as_of && (!latest || line.as_of > latest) ? line.as_of : latest), null);
}

interface AskPanelProps {
  state: Exclude<AskState, { status: "idle" }>;
  onCancel: () => void;
  onRetry: () => void;
  onOpen: (target: AnswerTarget) => void;
  onOpenReport: (question: string) => void;
}

/** Tier 3: the asked question's answer, its facts and where they live. */
export function AskPanel({ state, onCancel, onRetry, onOpen, onOpenReport }: AskPanelProps) {
  const { t } = useTranslation();
  const result: AskAnswerDTO | null = state.status === "done" ? state.result : null;
  const topics = result ? [...new Set(result.topics.map((topic) => TOPIC_TARGET[topic] ? topic : "supply"))] : [];
  return (
    <section className="answer-ask-panel" aria-labelledby="answer-ask-title" aria-busy={state.status === "running"}>
      <header className="answer-ask-head">
        <h2 id="answer-ask-title">{state.question}</h2>
        {result && (
          <span className="answer-ask-basis" data-answer-basis={result.basis}>
            {result.basis === "model" ? `${t("answer.ask.ai_summary")} · ${t("why.basis_model")}` : t("answer.ask.facts_only")}
            {latestAsOf(result) && ` · ${t("answer.as_of", { as_of: shortAsOf(latestAsOf(result)) })}`}
          </span>
        )}
      </header>

      {state.status === "running" && (
        <div className="answer-ask-progress" role="status">
          <span className="answer-ask-spinner" aria-hidden="true" />
          <span>{state.stage === "reading" ? t("answer.ask.reading") : t("answer.ask.writing")}</span>
          <button type="button" className="answer-ask-link" onClick={onCancel}>{t("answer.ask.cancel")}</button>
        </div>
      )}

      {state.status === "error" && (
        <div className="answer-ask-progress" role="alert">
          <span>{t("answer.ask.failed")}</span>
          <button type="button" className="answer-ask-link" onClick={onRetry}>{t("answer.ask.retry")}</button>
        </div>
      )}

      {result && (
        <>
          {result.simulated && (
            <p className="answer-ask-simulated" data-answer-simulated="true">{t("answer.ask.simulated")}</p>
          )}
          {result.answer ? (
            <p className="answer-ask-text">{result.answer}</p>
          ) : (
            <p className="answer-ask-note">
              {result.ai === "off" ? t("answer.ask.ai_off") : result.ai === "refused" ? t("answer.ask.ai_refused") : result.lines.length ? t("answer.ask.ai_failed") : t("answer.ask.no_facts")}
            </p>
          )}
          {result.lines.length > 0 && (
            <details className="answer-ask-facts" open={!result.answer}>
              <summary>{t("answer.ask.facts", { count: result.lines.length })}</summary>
              <ul>
                {result.lines.map((line) => (
                  <li key={`${line.source}:${line.text}`}>
                    <span>{line.text}</span>
                    <small>{shortAsOf(line.as_of)}</small>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <div className="answer-ask-actions">
            {topics.map((topic) => (
              <button key={topic} type="button" className="answer-ask-link" onClick={() => onOpen(TOPIC_TARGET[topic])}>
                {t(`answer.ask.open.${topic}`)}
              </button>
            ))}
            <button type="button" className="answer-ask-link" onClick={() => onOpenReport(state.question)}>
              {t("answer.ask.open_report")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
