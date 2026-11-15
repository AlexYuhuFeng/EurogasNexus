import type { ReactNode } from "react";
import { statusBadgeClass, type StatusBadgeVariant } from "./statusBadgeClass";

/**
 * The state of a record or a figure, in a short sentence-case label (UX-02).
 *
 * `tone` is the design-system status: ok, watch, breach, info, simulated, stale or neutral. Each
 * has its own colour role (tokens.css) whose text meets AA on its soft background, and the label
 * always says the state in words, so colour is never the only signal.
 *
 * The older `variant` + `status` form maps a domain's lifecycle constant onto its existing class
 * family (source, pipeline, readiness, job) and stays supported for those call sites.
 */
export type StatusTone = "ok" | "watch" | "breach" | "info" | "simulated" | "stale" | "neutral";

interface CommonProps {
  children: ReactNode;
  className?: string;
  /**
   * Detail the badge has no room for: what the state refers to, or which store
   * served it. The UI constitution allows a title as the second signal beside
   * visible text - never as a replacement for the state itself.
   */
  title?: string;
}

interface ToneProps extends CommonProps {
  tone: StatusTone;
  variant?: never;
  status?: never;
}

interface VariantProps extends CommonProps {
  variant: StatusBadgeVariant;
  status: string;
  tone?: never;
}

export type StatusBadgeProps = ToneProps | VariantProps;

export function StatusBadge(props: StatusBadgeProps) {
  const { children, className, title } = props;
  if (props.tone) {
    const classes = ["status-badge", "ds-status", className].filter(Boolean).join(" ");
    return (
      <span className={classes} data-tone={props.tone} title={title}>
        {children}
      </span>
    );
  }
  const classes = [statusBadgeClass(props.variant, props.status), className].filter(Boolean).join(" ");
  return (
    <span className={classes} title={title}>
      {children}
    </span>
  );
}
