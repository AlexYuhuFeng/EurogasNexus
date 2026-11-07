/**
 * One calm data-status chip for the top bar, with the detail one hover, focus or tap away.
 *
 * A trader needs to know whether the figures in front of them can be trusted, not how the
 * plumbing is doing. The chip says that in two words and a coloured dot; everything else
 * (market-data age, sources needing action, the push connection, the runtime store) sits
 * in the panel it opens. The panel opens on hover for a mouse, on focus for a keyboard and
 * on a tap for touch, and closes on Escape or when the pointer leaves.
 */
import { useEffect, useRef, useState } from "react";
import { StatusBadge } from "@/components/ui";
import type { SourceSummary } from "@/app/workspaceDerivedData";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export type DataHealth = "ok" | "attention" | "down" | "checking";

/** The one word the chip shows: worst of the store and the sources. */
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
  /** Only whoever administers sources sees their count on the bar; others see it inside. */
  showSourceCounts?: boolean;
  /** The server values positions with simulated demo prices: say so on every screen. */
  demoPrices?: boolean;
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
  useEffect(() => {
    if (!open) return undefined;
    const close = (event: KeyboardEvent | PointerEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !rootRef.current?.contains(event.target as Node)) {
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

  const chipLabel =
    health === "attention" && showSourceCounts && sourceSummary.showCounts && sourceSummary.issues > 0
      ? t("status.chip.attention_count", { count: sourceSummary.issues })
      : t(`status.chip.${health}`);
  return (
    <div
      ref={rootRef}
      className={`topbar-status is-${health}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onKeyUp={(event) => {
        if (event.key === "Tab") setHovered(true);
      }}
      onBlur={(event) => {
        if (!rootRef.current?.contains(event.relatedTarget as Node)) setOpen(false);
      }}
    >
      {demoPrices && (
        <span className="topbar-demo-chip" title={t("status.demo_prices_help")}>
          <span className="tab-label-full">{t("status.demo_prices")}</span>
          <span className="tab-label-short" aria-hidden="true">{t("status.demo_prices_short")}</span>
        </span>
      )}
      <button
        type="button"
        className="topbar-status-chip"
        // At compact width only the dot shows; the words stay the button's name.
        aria-label={chipLabel}
        aria-expanded={open}
        aria-controls="topbar-status-panel"
        onClick={() => setPinned((value) => !value)}
      >
        <i aria-hidden="true" />
        <span>{chipLabel}</span>
      </button>
      {open && (
        <div id="topbar-status-panel" className="topbar-status-panel" role="dialog" aria-label={t("status.panel_title")}>
          <dl>
            <div>
              <dt>{t("status.market_data")}</dt>
              <dd>
                {marketLastUpdatedAtUtc
                  ? `${t("context.updated")} ${formatUtcTimestamp(marketLastUpdatedAtUtc)}`
                  : t("context.no_market_update")}
              </dd>
            </div>
            <div>
              <dt>{t("status.sources")}</dt>
              <dd>
                {sourceSummary.viewState === "partial" && sourceSummary.showCounts && sourceSummary.issues > 0
                  ? t("context.sources_need_action", { count: sourceSummary.issues })
                  : t(`context.sources_${sourceSummary.viewState}`)}
                {sourceSummary.showCounts && (
                  <small>
                    {sourceSummary.active}/{sourceSummary.total} {t("context.active")}
                  </small>
                )}
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
          {onReportProblem && health !== "ok" && health !== "checking" && (
            <button type="button" className="link-button" onClick={onReportProblem}>
              {t("support.hint")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
