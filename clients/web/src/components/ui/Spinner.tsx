/**
 * The busy ring (UX_REFERENCE rule 18): a small circle that says "working" without words, for
 * places too small for Skeleton rows or WorkProgress stages (a busy button, a picker's trigger, a
 * panel title while it re-reads).
 *
 * - Unknown progress (no `value`): a quarter arc turns once per `--ds-duration-loop`.
 * - Known progress (`value` 0 to 1): the arc fills to it and stands still; it never shows more
 *   than the work has done.
 *
 * Under reduced motion the arc stands still. With a `label`, assistive technology hears it once
 * (a live status, or a progressbar with its value); without one the ring is decoration and the
 * control around it says it is busy (`aria-busy`). Colours and sizes come from the tokens.
 */
export interface SpinnerProps {
  /** What is being worked on, in words, for assistive technology. Omit inside a busy control. */
  label?: string;
  /** Known progress from 0 to 1; omit (or null) when progress is unknown. */
  value?: number | null;
  /** `xs` 12 px beside small text, `sm` 16 px in controls (default), `md` 20 px beside a heading. */
  size?: "xs" | "sm" | "md";
  className?: string;
}

export function Spinner({ label, value, size = "sm", className }: SpinnerProps) {
  const known = typeof value === "number" && Number.isFinite(value);
  const fraction = known ? Math.min(1, Math.max(0, value)) : 0.25;
  const percent = Math.round(fraction * 100);
  const classes = ["ds-spinner", className].filter(Boolean).join(" ");
  const ring = (
    <svg className="ds-spinner-ring" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <circle className="ds-spinner-track" cx="8" cy="8" r="6" pathLength={100} />
      <circle className="ds-spinner-arc" cx="8" cy="8" r="6" pathLength={100} strokeDasharray={`${percent} 100`} />
    </svg>
  );
  const common = { className: classes, "data-size": size, "data-progress": known ? "known" : "unknown" } as const;
  if (!label) return <span {...common} aria-hidden="true">{ring}</span>;
  if (known) {
    return (
      <span {...common} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        {ring}
      </span>
    );
  }
  return (
    <span {...common} role="status" aria-live="polite">
      {ring}
      <span className="ds-visually-hidden">{label}</span>
    </span>
  );
}
