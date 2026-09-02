import type { ReactNode } from "react";
import { statusBadgeClass, type StatusBadgeVariant } from "./statusBadgeClass";

interface StatusBadgeProps {
  variant: StatusBadgeVariant;
  status: string;
  children: ReactNode;
  className?: string;
}

export function StatusBadge({ variant, status, children, className }: StatusBadgeProps) {
  const classes = [statusBadgeClass(variant, status), className].filter(Boolean).join(" ");
  return <span className={classes}>{children}</span>;
}
