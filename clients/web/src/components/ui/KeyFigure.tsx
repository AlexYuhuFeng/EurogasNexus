import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useScreenFreshness } from "@/app/data/connection";
import { useInstantFormatter } from "@/app/time/useInstant";

import { pnlClass } from "@/app/model/pnlColor";
import type { ConvertedText } from "@/app/time/valueFormat";
import { ConvertedValue } from "./ConvertedValue";
import type { SortValue } from "./dataGridModel";
import { LiveValue } from "./LiveValue";

/**
 * One headline number (UX-02): a label, the value in tabular numerals, its unit, and optionally
 * the change and how current it is. Prices first, provenance on demand: the state appears only
 * when the figure is not current, and the age is one short line.
 *
 * The structure (span label, strong value, small unit) is the one `metric-grid` and
 * `position-summary` already lay out, so existing strips adopt it without a layout change.
 */
export type FigureState = "current" | "delayed" | "late" | "stale" | "simulated" | "manual" | "never";

export interface KeyFigureProps {
  label: ReactNode;
  /** Already formatted. A missing value is "–", never zero. */
  value: ReactNode;
  unit?: ReactNode;
  /** The change, formatted, and its sign for colour (profit/loss convention: pnlColor.ts). */
  delta?: { text: ReactNode; value: number | null | undefined };
  /** How old the figure is ("2 min", "1d"). */
  age?: ReactNode;
  /** Anything but current is said in words beside the value. */
  state?: FigureState;
  stateLabel?: ReactNode;
  /** Emphasis: `lg` uses the key-figure size (20 px); the default sits in dense strips. */
  size?: "md" | "lg";
  /** Colour class for the value itself (a P&L or long/short figure). */
  valueClassName?: string;
  /** Tooltip on the value: the definition or basis. */
  title?: string;
  /** Extra line under the value (MetricStrip's `detail`). */
  detail?: ReactNode;
  /** Anything that is not a note: a link under the figure ("1 breach · 3 watch"). */
  action?: ReactNode;
  /**
   * Note triggers ("Why", "Method") as quiet inline links beside the label, so a figure keeps
   * one height whether or not it has them (pass the triggers with `inline`).
   */
  notes?: ReactNode;
  /** Shown beside the value itself (the simulated marker): never only in a banner. */
  marker?: ReactNode;
  /**
   * The value in the reader's reporting currency or energy unit, with its rate, date and method
   * (design basis G3; app/time/useConversion.ts). `hover` shows on hover, focus or tap; `line`
   * is always visible (reporting contexts). The native value stays the figure.
   */
  converted?: ConvertedText | null;
  convertedMode?: "hover" | "line";
  /**
   * A figure that updates in place (UX R2): a neutral flash when `watch` changes and its
   * direction as a glyph until the next change. `identity` names what the figure is (a hub and
   * product, a book): a change of it is a different figure, not a tick.
   */
  live?: { watch: SortValue; identity: string };
  className?: string;
}

export function KeyFigure({
  label,
  value,
  unit,
  delta,
  age,
  state = "current",
  stateLabel,
  size = "md",
  valueClassName,
  title,
  detail,
  action,
  notes,
  marker,
  converted,
  convertedMode = "hover",
  live,
  className,
}: KeyFigureProps) {
  const labelId = useId();
  const convertedId = useId();
  const freshness = useScreenFreshness();
  const { t } = useTranslation();
  const format = useInstantFormatter();
  if (live && !freshness.current && state === "current") {
    // Small-desk plan 3.7: a live figure on a screen that is not current keeps its last
    // value, says "stale" and the time it was last known (app/data/connection.ts).
    state = "stale";
    stateLabel = t("stale.label");
    age = freshness.since !== null ? format(freshness.since)?.text ?? age : age;
  }
  const hoverConverted = converted && convertedMode === "hover";
  const classes = ["key-figure", size === "lg" ? "key-figure-lg" : "", className].filter(Boolean).join(" ");
  return (
    <div className={classes} role="group" aria-labelledby={labelId} data-state={state === "current" ? undefined : state}>
      {notes ? (
        <span className="key-figure-head">
          <span id={labelId} title={typeof label === "string" ? label : undefined}>{label}</span>
          <span className="key-figure-notes">{notes}</span>
        </span>
      ) : (
        <span id={labelId}>{label}</span>
      )}
      <strong
        className={valueClassName}
        title={title}
        tabIndex={hoverConverted ? 0 : undefined}
        aria-describedby={converted ? convertedId : undefined}
        data-converted-host={hoverConverted ? "" : undefined}
      >
        {live ? (
          <LiveValue watch={live.watch} identity={live.identity}>
            {value}
          </LiveValue>
        ) : (
          value
        )}
        {unit ? <small className="metric-strip-unit key-figure-unit">{unit}</small> : null}
        {marker}
      </strong>
      <ConvertedValue converted={converted ?? null} mode={convertedMode} id={convertedId} />
      {delta ? <small className={`key-figure-delta ${pnlClass(delta.value)}`.trim()}>{delta.text}</small> : null}
      {state !== "current" || age ? (
        <small className="key-figure-age">
          {state !== "current" ? <span className="key-figure-state">{stateLabel ?? state}</span> : null}
          {age ? <span>{age}</span> : null}
        </small>
      ) : null}
      {detail !== undefined && detail !== null ? <small>{detail}</small> : null}
      {action ? <div className="key-figure-action">{action}</div> : null}
    </div>
  );
}
