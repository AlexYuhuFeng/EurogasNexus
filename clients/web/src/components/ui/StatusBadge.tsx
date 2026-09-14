import type { ReactNode } from "react";
import { statusBadgeClass, type StatusBadgeVariant } from "./statusBadgeClass";

interface StatusBadgeProps {
  variant: StatusBadgeVariant;
  status: string;
  children: ReactNode;
  className?: string;
  /**
   * Detail the badge has no room for: what the state refers to, or which store
   * served it. The UI constitution allows a title as the second signal beside
   * visible text - never as a replacement for the state itself.
   */
  title?: string;
}

export function StatusBadge({ variant, status, children, className, title }: StatusBadgeProps) {
  const classes = [statusBadgeClass(variant, status), className].filter(Boolean).join(" ");
  return (
    <span className={classes} title={title}>
      {children}
    </span>
  );
}
