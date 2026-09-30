import {
  dayBoardCountdown,
  dayBoardCountdownMeasure,
  dayBoardSummary,
  type DayBoardModel,
  type DayBoardSummaryState,
} from "@/app/model/dayBoardModel";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";

type Translate = (key: string) => string;

interface DayBoardPanelProps {
  readonly t: Translate;
  /** The composed board. The panel renders it; it fetches, orders and counts nothing itself. */
  readonly model: DayBoardModel;
  /** The task a row hands the trader to. The board navigates; it never computes or records. */
  readonly onOpenTask: (task: "nomination" | "review") => void;
  /** Where the alert pointer goes, when the shell can open the alert centre's workspace. */
  readonly onOpenAlerts?: () => void;
}

/**
 * The countdown as the surface states it: the word for the state, the whole measure, and the
 * qualifier that names the clock it was measured against. The state is also the element's class,
 * because a deadline that has passed has to look like one.
 */
function Countdown({
  deadlineUtc,
  measuredAtUtc,
  t,
}: {
  deadlineUtc: string;
  measuredAtUtc: string;
  t: Translate;
}) {
  const countdown = dayBoardCountdown(deadlineUtc, measuredAtUtc);
  return (
    <em className={`day-board-countdown is-${countdown.state}`}>
      {dayBoardCountdownMeasure(countdown, t)}
      <small className="day-board-qualifier">{t("day_board.countdown.browser_clock")}</small>
    </em>
  );
}

/**
 * One always-visible state of the strip: its name, its composed value and the tone that value
 * carries. It is a span - the summary is the disclosure control, so anything interactive inside
 * it would swallow the toggle - and it renders only what `dayBoardSummary` composed.
 */
function SummaryState({ state, t }: { state: DayBoardSummaryState; t: Translate }) {
  return (
    <span className={`day-board-state is-${state.tone}`}>
      <small>{t(state.labelKey)}</small>
      <strong>{state.value}</strong>
    </span>
  );
}

/**
 * The day board: a compact, unframed status strip above the Decision workspace's tasks.
 *
 * The desk had no surface for the clock - what must be acted on today, and by when - so this panel
 * composes three reads that already existed and says, for each, what the read actually
 * established:
 *
 * - the nomination windows the deployment declares, with the deadline instant the API resolved
 *   (`closes_at_utc`) as the primary value. The "in 42 min" beside it is measured against the
 *   browser's clock and is labelled as such, because those are two different clocks and confusing
 *   them would move a deadline;
 * - the actionable opportunities with no recorded decision, handed to the review task. When the
 *   review register was not read the section says so and claims nothing;
 * - a measured pointer into the alert centre. The alert list stays in the top bar: this section is
 *   counts plus the newest movement instant, and it links there.
 *
 * Every count here is either measured or absent. A section that was not read says so, and a section
 * that measured zero says zero - `0` is never a stand-in for "we did not ask".
 *
 * The strip's default state is one line of state, not the evidence behind it: window availability,
 * the outstanding decision count (`unknown` when the register was not read, never a zero), the
 * nearest deadline with its countdown, and the measured alert counts including critical severity.
 * The evidence - the window rows, the opportunities, the alert pointer and every UTC instant and
 * provenance line - stays in the native details/summary disclosure, which the keyboard toggles
 * like any other disclosure. Urgency is not hidden: an overdue or imminent deadline and a critical
 * alert are stated in the summary itself, in the tone that marks them.
 */
export function DayBoardPanel({ t, model, onOpenTask, onOpenAlerts }: DayBoardPanelProps) {
  const { clock, decisions, alerts, measuredAtUtc } = model;
  // The always-visible states. Derived from the same composition the details render, so the strip
  // and the evidence cannot disagree about a count or about a deadline.
  const summary = dayBoardSummary(model, t);

  /** A declared number, or the honest word for a field the row does not declare. */
  function declared(value: number | null, format: (item: number) => string): string {
    if (value === null || !Number.isFinite(value)) return t("day_board.not_declared");
    return format(value);
  }

  function changeLimit(mwh: number | null, pct: number | null): string {
    const parts = [
      mwh === null || !Number.isFinite(mwh) ? null : `${mwh.toLocaleString()} MWh`,
      pct === null || !Number.isFinite(pct) ? null : `${pct}%`,
    ].filter((part): part is string => part !== null);
    return parts.length > 0 ? parts.join(" · ") : t("day_board.not_declared");
  }

  return (
    <section className="day-board" aria-label={t("day_board.title")}>
      <details className="day-board-disclosure">
        <summary className="day-board-summary">
          <strong className="day-board-summary-title">{t("day_board.title")}</strong>
          <span className="day-board-states">
            <SummaryState state={summary.windows} t={t} />
            <SummaryState state={summary.decisions} t={t} />
            <SummaryState state={summary.alerts} t={t} />
          </span>
          <span className="day-board-summary-hint">
            {t("day_board.summary.details")}
            <span className="day-board-chevron" aria-hidden="true" />
          </span>
        </summary>

        <div className="day-board-detail">
          {/* Whose instants these are, whose clock the countdowns are measured against, and when
              the read happened - the provenance line stays with the evidence, not in the strip. */}
          <p className="day-board-note day-board-basis">
            {t("day_board.basis")} <strong>{formatUtcTimestamp(measuredAtUtc)}</strong>
          </p>

          <div className="day-board-section day-board-clock">
            <div className="section-heading">
              <span className="eyebrow">{t("day_board.clock.eyebrow")}</span>
              {clock.posture === "measured" && clock.mastersDeclared !== null && (
                <strong>
                  {t("day_board.clock.masters_declared")}: {clock.mastersDeclared}
                </strong>
              )}
            </div>

            {clock.posture === "not-read" ? (
              <p className="day-board-empty">{t("day_board.clock.not_read")}</p>
            ) : clock.posture === "runtime-db-not-configured" ? (
              <div className="day-board-unavailable">
                <strong>{t("day_board.clock.not_configured")}</strong>
                {clock.missingInputs.length > 0 && (
                  <span>
                    {t("day_board.clock.missing_inputs")}: {clock.missingInputs.join(", ")}
                  </span>
                )}
              </div>
            ) : clock.rows.length === 0 ? (
              // A measured read that carried no window: the deployment's own reason when it
              // declared one, the measurement itself when it did not.
              <p className="day-board-empty">
                {clock.noWindowsReason === "NOMINATION_WINDOWS_MISSING"
                  ? t("day_board.clock.no_masters")
                  : t("day_board.clock.none_today")}
              </p>
            ) : (
              <ul className="day-board-list">
                {clock.rows.map((row) => (
                  <li key={`${row.gasDay}-${row.windowId}`}>
                    <button
                      type="button"
                      className="day-board-row"
                      onClick={() => onOpenTask("nomination")}
                    >
                      <span className="day-board-row-main">
                        <strong>{row.name || row.windowId}</strong>
                        <small>
                          {row.country ? `${row.country} · ` : ""}
                          {row.windowId} · {t("day_board.clock.gas_day")} {row.gasDay}
                        </small>
                        <small>
                          {t("day_board.clock.opens_at")}: {formatUtcTimestamp(row.opensAtUtc)}
                        </small>
                      </span>
                      <span className="day-board-deadline">
                        <small>{t("day_board.clock.closes_at")}</small>
                        <strong>{formatUtcTimestamp(row.closesAtUtc)}</strong>
                        <Countdown
                          deadlineUtc={row.closesAtUtc}
                          measuredAtUtc={measuredAtUtc}
                          t={t}
                        />
                        {/*
                          Once this gas day's window has closed, the instant the desk is actually
                          waiting for is the next occurrence of the same daily rule - and the API
                          resolved it, so the row states it rather than leaving the trader to add a
                          day to a clock. Only shown when the window can no longer be used, so a row
                          that is still open is not carrying a line about tomorrow.
                        */}
                        {dayBoardCountdown(row.closesAtUtc, measuredAtUtc).state === "overdue" &&
                          row.nextOpensAtUtc && (
                            <small className="day-board-next-window">
                              {t("day_board.clock.next_window")}:{" "}
                              {formatUtcTimestamp(row.nextOpensAtUtc)}
                              {row.nextClosesAtUtc
                                ? ` – ${formatUtcTimestamp(row.nextClosesAtUtc)}`
                                : ""}
                            </small>
                          )}
                      </span>
                      <span className="day-board-limit">
                        <small>{t("day_board.clock.maximum_change")}</small>
                        <strong>{changeLimit(row.maximumChangeMwh, row.maximumChangePct)}</strong>
                      </span>
                      <span className="day-board-evidence">
                        <small>{t("day_board.evidence")}</small>
                        <strong>
                          {row.sourceReference ?? row.sourceSystem ?? t("day_board.not_declared")}
                        </strong>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {clock.gasDay && (
              <p className="day-board-note">
                {t("day_board.clock.time_basis")}: {clock.timeBasis ?? t("day_board.not_declared")}
                {clock.calendar ? ` · ${clock.calendar}` : ""}
                {clock.assessedAtUtc
                  ? ` · ${t("day_board.clock.assessed_at")}: ${formatUtcTimestamp(
                      clock.assessedAtUtc,
                    )}`
                  : ""}
              </p>
            )}
            {clock.gasDay && <p className="day-board-note">{t("day_board.clock.time_basis_help")}</p>}
          </div>

          <div className="day-board-section day-board-decisions">
            <div className="section-heading">
              <span className="eyebrow">{t("day_board.decisions.eyebrow")}</span>
              {decisions.posture === "measured" && decisions.decidedCount !== null && (
                <strong>
                  {decisions.actionableCount} {t("day_board.decisions.actionable")} ·{" "}
                  {decisions.decidedCount} {t("day_board.decisions.decided")}
                </strong>
              )}
            </div>

            {decisions.posture === "not-read" ? (
              <p className="day-board-empty">{t("day_board.decisions.not_read")}</p>
            ) : decisions.rows.length === 0 ? (
              // Zero outstanding is not the same statement as "all decided": a read that published
              // no actionable opportunity and a register that cleared every one are different
              // facts.
              <p className="day-board-empty">
                {decisions.actionableCount > 0
                  ? t("day_board.decisions.all_decided")
                  : t("day_board.decisions.none_actionable")}
              </p>
            ) : (
              <ul className="day-board-list">
                {decisions.rows.map((row) => (
                  <li key={row.opportunityId}>
                    <button
                      type="button"
                      className="day-board-row"
                      onClick={() => onOpenTask("review")}
                    >
                      <span className="day-board-row-main">
                        <strong>{row.routeName}</strong>
                        <small>
                          {row.opportunityId}
                          {row.simulated ? ` · ${t("market.simulated_source")}` : ""}
                        </small>
                      </span>
                      <span className="day-board-deadline">
                        <small>{t("day_board.decisions.deadline")}</small>
                        <strong>{formatUtcTimestamp(row.validUntilUtc)}</strong>
                        <Countdown
                          deadlineUtc={row.validUntilUtc}
                          measuredAtUtc={measuredAtUtc}
                          t={t}
                        />
                      </span>
                      <span className="day-board-limit">
                        <small>{t("day_board.decisions.margin")}</small>
                        <strong>
                          {declared(row.netMargin, (value) => value.toFixed(2))}
                        </strong>
                        <small>
                          {t("day_board.decisions.max_quantity")}:{" "}
                          {declared(row.maxQuantityMwh, (value) => `${value.toLocaleString()} MWh`)}
                        </small>
                        <small>
                          {t("day_board.decisions.confidence")}:{" "}
                          {(row.confidenceScore * 100).toFixed(0)}%
                        </small>
                      </span>
                      <span className="day-board-evidence">
                        <small>{t("day_board.evidence")}</small>
                        <strong>
                          {row.sourceRefs.length > 0
                            ? row.sourceRefs.join(", ")
                            : t("day_board.not_declared")}
                        </strong>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="day-board-section day-board-alerts">
            <div className="section-heading">
              <span className="eyebrow">{t("day_board.alerts.eyebrow")}</span>
              {alerts.posture === "measured" && (
                <strong>
                  {alerts.openCount} {t("day_board.alerts.open")}
                </strong>
              )}
            </div>

            {alerts.posture !== "measured" ? (
              // Nothing was measured, so no count is shown - not even a zero.
              <p className="day-board-empty">{t("day_board.alerts.not_read")}</p>
            ) : (
              <>
                {/* The open count heads the section, so the row below states the two severities
                    the pointer is asking the trader to look at rather than repeating it. */}
                <p className="day-board-counts">
                  <span>
                    {alerts.criticalCount} {t("day_board.alerts.critical")}
                  </span>
                  <span>
                    {alerts.warningCount} {t("day_board.alerts.warning")}
                  </span>
                </p>
                <p className="day-board-note">
                  {alerts.movedCount === null || alerts.movedCount === 0
                    ? t("day_board.alerts.no_movement")
                    : `${t("day_board.alerts.moved")}: ${alerts.movedCount}`}
                  {alerts.latestMovementUtc
                    ? ` · ${t("day_board.alerts.latest_movement")}: ${formatUtcTimestamp(
                        alerts.latestMovementUtc,
                      )}`
                    : ""}
                </p>
              </>
            )}

            <p className="day-board-pointer">
              {t("day_board.alerts.pointer")}{" "}
              {onOpenAlerts && (
                <button type="button" onClick={onOpenAlerts}>
                  {t("day_board.alerts.open_centre")}
                </button>
              )}
            </p>
          </div>
        </div>
      </details>
    </section>
  );
}
