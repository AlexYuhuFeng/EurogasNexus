/**
 * Fold: detail folded under one line, opened on demand (owner: "you can fold it"). The one
 * disclosure every page uses instead of styling its own `<details>`: the summary line is the
 * label and, quieter, what is inside ("5 supplies · 7 warnings"); the body keeps the page's
 * spacing. `framed` gives the fold a panel border (a section of its own on the page).
 *
 * Uncontrolled by default; pass `open` (and `onToggle`) to drive it, for example to open it on
 * a blocker. `onToggle` reports only the reader's own toggles, never one caused by `open`.
 */
import type { HTMLAttributes, ReactNode } from "react";

export interface FoldProps extends Omit<HTMLAttributes<HTMLDetailsElement>, "onToggle" | "children"> {
  summary: ReactNode;
  /** Quieter text after the summary: a count, a current choice. */
  meta?: ReactNode;
  children: ReactNode;
  open?: boolean;
  onToggle?: (open: boolean) => void;
  framed?: boolean;
  /** Small, muted summary (a fold inside a list item or a form). */
  quiet?: boolean;
}

export function Fold({ summary, meta, children, open, onToggle, framed = false, quiet = false, className, ...rest }: FoldProps) {
  const classes = ["ds-fold", framed ? "ds-fold-framed" : "", quiet ? "ds-fold-quiet" : "", className].filter(Boolean).join(" ");
  return (
    <details
      {...rest}
      className={classes}
      open={open}
      onToggle={(event) => {
        const now = (event.currentTarget as HTMLDetailsElement).open;
        if (onToggle && now !== open) onToggle(now);
      }}
    >
      <summary className="ds-fold-summary">
        <span className="ds-fold-label">{summary}</span>
        {meta !== undefined && meta !== null && meta !== "" && <span className="ds-fold-meta">{meta}</span>}
      </summary>
      <div className="ds-fold-body">{children}</div>
    </details>
  );
}
