/**
 * Percentile strip (F.1 "where today sits in history"): a 0–100 bar with a marker, the window it
 * is measured in stated beside it. Never a z-score alone. Inline HTML with tokens; the strip is
 * an image with its own words for screen readers.
 */
type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface PercentileStripProps {
  /** 0–100: the marker's position (a percentile rank, or the place in a min–max range). */
  position: number;
  /** Beyond the range: the marker sits at the end and the caption says so. */
  outside?: "below" | "above" | null;
  /** "62nd percentile", "in the 5-yr range": what the position means. */
  caption: string;
  /** The window ("5-yr range 2021/22–2025/26"); stated, never implied. */
  window: string;
  lowLabel?: string;
  highLabel?: string;
  t: Translate;
}

export function PercentileStrip({ position, outside = null, caption, window, lowLabel, highLabel, t }: PercentileStripProps) {
  const at = Math.min(100, Math.max(0, position));
  const words = outside ? t(`chart.percentile.${outside}`, { window }) : `${caption} · ${window}`;
  return (
    <span className="ds-percentile" role="img" aria-label={words} data-percentile={Math.round(at)} data-percentile-outside={outside ?? undefined}>
      <span className="ds-percentile-track" aria-hidden="true">
        <span className="ds-percentile-mid" />
        <span className={`ds-percentile-marker${outside ? " is-outside" : ""}`} style={{ ["--ds-percentile-at" as string]: `${at}%` }} />
      </span>
      <span className="ds-percentile-ends" aria-hidden="true">
        <span>{lowLabel ?? "0"}</span>
        <span>{highLabel ?? "100"}</span>
      </span>
      <span className="ds-percentile-caption" aria-hidden="true">{words}</span>
    </span>
  );
}
