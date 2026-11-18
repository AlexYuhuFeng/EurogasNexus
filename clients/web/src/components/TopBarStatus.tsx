/**
 * The data-status indicator on the top bar: a dot, and a count when something needs attention.
 *
 * It replaced the banner that sat above every page ("5 affected endpoints …") and could not be
 * dismissed (docs/product/UX_REFERENCE.md, "Problems are listed, not pinned"). The dot says
 * whether the figures on screen can be trusted; the count says how many things are affected; the
 * panel it opens names each one, says why in plain words and offers the action: retry the reads
 * that did not load, go to the figure that is not current, open Data sources (whoever administers
 * them) or report a problem. The plumbing (store, push connection, last market update) is one
 * quiet block at the bottom.
 *
 * The first time a set of problems appears in a session the shell also shows a dismissible line
 * under the bar (DataProblemNotice); a lost data store stays a blocking notice. The panel opens on
 * hover for a mouse, on focus for a keyboard and on a tap for touch, and closes on Escape.
 */
import { useEffect, useRef, useState } from "react";
import { Button, Instant, StatusBadge } from "@/components/ui";
import type { SourceSummary } from "@/app/workspaceDerivedData";
import type { DeskTodayDTO } from "@/api/client";
import type { EndpointFailureSurface, EndpointRetrySurface } from "@/app/model/endpointFailures";
import { StaleFigureList } from "./TodayScreen";
import { useCloseOnNavigation } from "@/app/shell/navigationKey";
import { dataProblemCount } from "@/app/model/dataProblems";

export { dataProblemCount };

type Translate = (key: string, options?: Record<string, unknown>) => string;

export type DataHealth = "ok" | "attention" | "down" | "checking";

/** Opens the status panel from elsewhere in the shell (the inline notice's "Details"). */
export const OPEN_DATA_STATUS_EVENT = "eurogas:open-data-status";

/** The one word the indicator stands for: worst of the store and the sources. */
export function dataHealth(sourceSummary: SourceSummary, storeState: string, loading: boolean): DataHealth {
  if (loading || sourceSummary.viewState === "checking") return "checking";
  if (storeState === "unavailable" || sourceSummary.viewState === "unavailable") return "down";
  if (storeState !== "ready" || sourceSummary.viewState !== "ready") return "attention";
  return "ok";
}

export function TopBarStatus({
  t,
  health,
  sourceSummary,
  storeLabel,
  storeDetail,
  storeState,
  streamingActive,
  marketLastUpdatedAtUtc,
  onReportProblem,
  showSourceCounts = false,
  demoPrices = false,
  staleFigures = [],
  nowMs = Date.now(),
  onOpenFigure,
  endpointFailures,
  endpointRetry,
  onRetry,
  onOpenDataSources,
  heldSources = 0,
}: {
  t: Translate;
  health: DataHealth;
  sourceSummary: SourceSummary;
  storeLabel: string;
  storeDetail: string;
  storeState: string;
  streamingActive: boolean;
  marketLastUpdatedAtUtc: string | null;
  onReportProblem?: () => void;
  /** Only whoever administers sources counts them; others see the sources line inside. */
  showSourceCounts?: boolean;
  /** The server values positions with simulated demo prices. */
  demoPrices?: boolean;
  /** Today's figures that are not current (the same list as Today's "N figures not current"). */
  staleFigures?: DeskTodayDTO["stale_figures"];
  nowMs?: number;
  /** Go to a named figure (on Today). */
  onOpenFigure?: (key: string) => void;
  /** The reads that did not load, bounded and translated (app/model/endpointFailures.ts). */
  endpointFailures?: EndpointFailureSurface;
  endpointRetry?: EndpointRetrySurface;
  onRetry?: () => void;
  /** Administration → Data sources, for whoever administers them. */
  onOpenDataSources?: () => void;
  /** Public sources the approval gate holds back: one calm line for those who cannot act. */
  heldSources?: number;
}) {
  // Hover previews the panel; a click or tap pins it until Escape or a click elsewhere.
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hovered || pinned;
  const setOpen = (value: boolean) => {
    setHovered(value);
    if (!value) setPinned(false);
  };
  const rootRef = useRef<HTMLDivElement | null>(null);
  // The panel does not follow the reader to another page (UX_REFERENCE rule 22).
  useCloseOnNavigation(open, () => setOpen(false));
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (event: KeyboardEvent | PointerEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !rootRef.current?.contains(event.target as Node)) {
        if (event instanceof KeyboardEvent && rootRef.current?.contains(document.activeElement)) buttonRef.current?.focus();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", close);
    window.addEventListener("pointerdown", close);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("pointerdown", close);
    };
  }, [open]);
  useEffect(() => {
    const show = () => {
      setPinned(true);
      buttonRef.current?.focus();
    };
    window.addEventListener(OPEN_DATA_STATUS_EVENT, show);
    return () => window.removeEventListener(OPEN_DATA_STATUS_EVENT, show);
  }, []);

  const failures = endpointFailures?.total ?? 0;
  const sourceIssues = showSourceCounts && sourceSummary.showCounts ? sourceSummary.issues : 0;
  // A demo desk's static store is the demo, not an incident: its figures are not counted stale.
  const staleCount = demoPrices ? 0 : staleFigures.length;
  const count = dataProblemCount({ endpointFailures: failures, staleFigures: staleCount, sourceIssues });
  const shown: DataHealth =
    health === "down" || health === "checking" ? health : count > 0 || health === "attention" ? "attention" : "ok";
  const name =
    count > 0
      ? t("status.indicator_count", { count })
      : t(`status.chip.${shown}`);

  return (
    <div
      ref={rootRef}
      className={`topbar-status is-${shown}`}
      data-topbar-status={shown}
      data-problem-count={count}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onKeyUp={(event) => {
        if (event.key === "Tab") setHovered(true);
      }}
      onBlur={(event) => {
        if (!rootRef.current?.contains(event.relatedTarget as Node)) setOpen(false);
      }}
    >
      <button
        ref={buttonRef}
        type="button"
        className="topbar-status-chip"
        aria-label={`${t("status.panel_title")}: ${name}`}
        title={`${t("status.panel_title")}: ${name}`}
        aria-expanded={open}
        aria-controls="topbar-status-panel"
        onClick={() => setPinned((value) => !value)}
      >
        <i aria-hidden="true" />
        {count > 0 ? <span className="topbar-status-count" aria-hidden="true">{count}</span> : null}
      </button>
      {open && (
        <div id="topbar-status-panel" className="topbar-status-panel" role="dialog" aria-label={t("status.panel_title")}>
          <header className="topbar-status-head">
            <strong>{t("status.panel_title")}</strong>
            <span>{count > 0 ? name : t(`status.chip.${shown}`)}</span>
          </header>

          {failures > 0 && endpointFailures ? (
            <section className="topbar-status-section" data-status-section="reads">
              <h3>{t("status.reads_title")}</h3>
              <ul className="topbar-status-list">
                {endpointFailures.entries.map((entry) => (
                  <li key={entry.key} data-endpoint-failure={entry.code}>
                    <span>{entry.label}</span>
                    <small>{entry.message}</small>
                  </li>
                ))}
              </ul>
              {endpointFailures.truncatedSummary ? <p className="topbar-status-more">{endpointFailures.truncatedSummary}</p> : null}
              <div className="topbar-status-actions">
                {onRetry ? (
                  <Button size="sm" variant="secondary" loading={endpointRetry?.busy} onClick={onRetry}>
                    {endpointRetry?.busy ? t("workspace.retry_in_progress") : t("workspace.retry_failed")}
                  </Button>
                ) : null}
                {onOpenDataSources ? (
                  <Button size="sm" variant="quiet" onClick={() => { setOpen(false); onOpenDataSources(); }}>
                    {t("status.open_data_sources")}
                  </Button>
                ) : onReportProblem ? (
                  <Button size="sm" variant="quiet" onClick={() => { setOpen(false); onReportProblem(); }}>
                    {t("topbar.report_problem")}
                  </Button>
                ) : null}
              </div>
            </section>
          ) : null}

          {staleCount > 0 ? (
            <section className="topbar-status-section" data-status-section="stale">
              <h3>{t("today.stale_title")}</h3>
              <StaleFigureList
                figures={staleFigures}
                t={t}
                nowMs={nowMs}
                onChoose={(key) => {
                  setOpen(false);
                  onOpenFigure?.(key);
                }}
              />
            </section>
          ) : null}

          {sourceIssues > 0 ? (
            <section className="topbar-status-section" data-status-section="sources">
              <h3>{t("status.sources")}</h3>
              <p>{t("context.sources_need_action", { count: sourceIssues })}</p>
              {onOpenDataSources ? (
                <div className="topbar-status-actions">
                  <Button size="sm" variant="quiet" onClick={() => { setOpen(false); onOpenDataSources(); }}>
                    {t("status.open_data_sources")}
                  </Button>
                </div>
              ) : null}
            </section>
          ) : null}

          {heldSources > 0 && !onOpenDataSources ? (
            <p className="topbar-status-calm" data-status-section="held-sources">{t("status.sources_held", { count: heldSources })}</p>
          ) : null}

          {count === 0 && shown === "ok" ? <p className="topbar-status-calm">{t("status.all_clear")}</p> : null}

          {demoPrices ? <p className="topbar-status-demo">{t("topbar.demo_mode")}</p> : null}

          <dl className="topbar-status-facts">
            <div>
              <dt>{t("status.market_data")}</dt>
              <dd>
                {marketLastUpdatedAtUtc ? <Instant value={marketLastUpdatedAtUtc} /> : t("context.no_market_update")}
              </dd>
            </div>
            <div>
              <dt>{t("status.updates")}</dt>
              <dd>{streamingActive ? t("stream.live") : t("stream.polling_fallback")}</dd>
            </div>
            <div>
              <dt>{t("data.runtime_store")}</dt>
              <dd>
                <StatusBadge variant="runtime-readiness-state" status={storeState} className="topbar-status-store" title={storeDetail}>
                  {storeLabel}
                </StatusBadge>
              </dd>
            </div>
          </dl>
          {onReportProblem && !failures && shown !== "ok" && shown !== "checking" ? (
            <button type="button" className="link-button" onClick={onReportProblem}>
              {t("support.hint")}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}
