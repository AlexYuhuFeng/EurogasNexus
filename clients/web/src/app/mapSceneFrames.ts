/**
 * Frame behaviour of the animated map scene (MAP-1): the intervals between animation frames,
 * summarised as the median and 95th percentile in ms. At 60 Hz a frame is 16.7 ms; a p95 above
 * 33 ms means the scene drops below 30 frames a second for one frame in twenty.
 */
export interface FrameSummary {
  frames: number;
  medianMs: number;
  p95Ms: number;
  /** Share of intervals longer than two 60 Hz frames (a visible stutter). */
  longShare: number;
}

export const LONG_FRAME_MS = 33.4;

export function frameSummary(intervals: readonly number[]): FrameSummary {
  const sorted = intervals.filter((value) => Number.isFinite(value) && value >= 0).sort((a, b) => a - b);
  if (sorted.length === 0) return { frames: 0, medianMs: 0, p95Ms: 0, longShare: 0 };
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
  const round = (value: number) => Math.round(value * 10) / 10;
  return {
    frames: sorted.length,
    medianMs: round(at(0.5)),
    p95Ms: round(at(0.95)),
    longShare: round(sorted.filter((value) => value > LONG_FRAME_MS).length / sorted.length),
  };
}
