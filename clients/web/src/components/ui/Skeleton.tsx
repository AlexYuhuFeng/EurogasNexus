/**
 * Loading placeholder (UX-02): grey bars where rows will be, so content does not pop in and the
 * layout does not jump. No spinner over content. The shimmer runs only when the user allows
 * motion; otherwise the bars are still.
 *
 * Screen readers hear one "loading" status (`label`), not the bars.
 */
export interface SkeletonProps {
  /** What is loading, in words: "Loading position ladder". */
  label: string;
  rows?: number;
  /** Row height: a table row (default) or a line of text. */
  variant?: "row" | "text";
  className?: string;
}

const WIDTHS = ["100%", "92%", "96%", "88%", "94%", "90%"];

export function Skeleton({ label, rows = 3, variant = "row", className }: SkeletonProps) {
  return (
    <div className={["ds-skeleton-group", className].filter(Boolean).join(" ")} role="status" aria-busy="true" aria-live="polite">
      <span className="ds-visually-hidden">{label}</span>
      {Array.from({ length: Math.max(1, rows) }, (_, index) => (
        <span
          key={index}
          className={`ds-skeleton ds-skeleton-${variant}`}
          aria-hidden="true"
          style={{ width: WIDTHS[index % WIDTHS.length] }}
        />
      ))}
    </div>
  );
}
